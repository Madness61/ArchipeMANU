"""Persistent shared API cache, room observations and resumable collection."""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import datetime, timezone

from . import config, db, live_api, live_metrics
from . import i18n
from .services.console_journal import record_goal

POLL_SECONDS = 60
LEASE_SECONDS = 55
WAKE_WINDOW = 150
WAKE_RETRY = 60
_collector_lock = threading.Lock()
_collector = None
_stop = threading.Event()
_wake = threading.Event()


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds") if timestamp else None


def migrate():
    with db.transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS live_rooms(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
            room_id TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            tracker_id TEXT NOT NULL DEFAULT '', auto_host INTEGER NOT NULL DEFAULT 0,
            entered_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            room_json TEXT NOT NULL DEFAULT '{}', latest_json TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'pending', error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL, last_success REAL, next_poll REAL NOT NULL DEFAULT 0,
            lease_until REAL NOT NULL DEFAULT 0,
            UNIQUE(build_id,room_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS live_one_current_room ON live_rooms(build_id) WHERE active=1;
        CREATE TABLE IF NOT EXISTS live_api_cache(
            endpoint TEXT NOT NULL, identifier TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '', fetched_at REAL,
            next_attempt REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '', error_kind TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(endpoint,identifier)
        );
        CREATE TABLE IF NOT EXISTS live_snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            live_id INTEGER NOT NULL REFERENCES live_rooms(id) ON DELETE CASCADE,
            observed_at REAL NOT NULL, source_at REAL NOT NULL,
            segment INTEGER NOT NULL DEFAULT 1, payload TEXT NOT NULL,
            UNIQUE(live_id,source_at)
        );
        CREATE INDEX IF NOT EXISTS live_snapshot_time ON live_snapshots(live_id,observed_at);
        CREATE TABLE IF NOT EXISTS live_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            live_id INTEGER NOT NULL REFERENCES live_rooms(id) ON DELETE CASCADE,
            snapshot_id INTEGER NOT NULL REFERENCES live_snapshots(id) ON DELETE CASCADE,
            observed_at REAL NOT NULL, since_at REAL,
            kind TEXT NOT NULL, player_key TEXT, message TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS live_event_time ON live_events(live_id,id DESC);
        CREATE TABLE IF NOT EXISTS live_room_wake(
            room_id TEXT PRIMARY KEY, live_id INTEGER NOT NULL REFERENCES live_rooms(id) ON DELETE CASCADE,
            deadline REAL NOT NULL, next_check REAL NOT NULL, lease_until REAL NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0, last_wake REAL NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'checking', error TEXT NOT NULL DEFAULT ''
        );
        """)
        # Adopt previously saved valid room links without issuing network calls.
        rows = conn.execute("""SELECT h.* FROM hosted_rooms h JOIN seed_builds b ON b.id=h.build_id
            WHERE b.status='succeeded' AND b.completed_at IS NULL AND h.id=(
              SELECT MAX(h2.id) FROM hosted_rooms h2 JOIN seed_builds b2 ON b2.id=h2.build_id
              WHERE b2.session_id=b.session_id AND b2.status='succeeded')
            AND NOT EXISTS (SELECT 1 FROM live_rooms l WHERE l.build_id=b.id)""").fetchall()
        for row in rows:
            try:
                identifier = live_api.room_id(row["room_url"])
            except ValueError:
                continue
            conn.execute("INSERT OR IGNORE INTO live_rooms(build_id,room_id,entered_by,created_at) VALUES (?,?,?,?)",
                         (row["build_id"], identifier, row["entered_by"], time.time()))


def attach(build_id, url, actor, auto_host=False, *, connection=None):
    identifier = live_api.room_id(url)
    now = time.time()
    if connection is None:
        with db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return attach(build_id, url, actor, auto_host, connection=conn)
    conn = connection
    conn.execute("UPDATE live_rooms SET active=0 WHERE build_id=?", (build_id,))
    conn.execute("""INSERT INTO live_rooms(build_id,room_id,entered_by,auto_host,created_at)
        VALUES (?,?,?,?,?) ON CONFLICT(build_id,room_id) DO UPDATE SET
        active=1,entered_by=excluded.entered_by,auto_host=excluded.auto_host,
        created_at=excluded.created_at,next_poll=0""",
                 (build_id, identifier, actor, int(auto_host), now))
    return conn.execute("SELECT id FROM live_rooms WHERE build_id=? AND active=1", (build_id,)).fetchone()["id"]


def current(build_id):
    return db.query("SELECT * FROM live_rooms WHERE build_id=? AND active=1", (build_id,), one=True)


def official_address(room_url, host, identifier=None):
    """Only an official room can supply the port of archipelago.gg itself."""
    if host != "archipelago.gg":
        return False
    try:
        actual = live_api.room_id(room_url)
        return identifier is None or actual == identifier
    except ValueError:
        return False


def wake_eligible(conn, build_id):
    row = conn.execute("""SELECT l.*,b.snapshot,b.seed_name,h.host AS saved_host,h.room_url AS saved_url
        FROM live_rooms l JOIN seed_builds b ON b.id=l.build_id JOIN sessions s ON s.id=b.session_id
        LEFT JOIN hosted_rooms h ON h.id=(SELECT MAX(id) FROM hosted_rooms WHERE build_id=b.id)
        WHERE l.build_id=? AND l.active=1
        AND s.locked=1 AND s.completed_at IS NULL AND b.completed_at IS NULL AND b.status='succeeded'
        AND b.id=(SELECT MAX(latest.id) FROM seed_builds latest WHERE latest.session_id=s.id)""",
        (build_id,)).fetchone()
    if row and (row['auto_host'] or official_address(row['saved_url'], row['saved_host'], row['room_id'])):
        return row
    return None


def request_wake(build_id, now=None):
    """Coalesce authorized round openings into a short, per-room observation window."""
    now = time.time() if now is None else now
    with db.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        linked = wake_eligible(conn, build_id)
        if not linked:
            return False
        conn.execute("""INSERT INTO live_room_wake(room_id,live_id,deadline,next_check) VALUES (?,?,?,?)
            ON CONFLICT(room_id) DO UPDATE SET live_id=excluded.live_id,deadline=excluded.deadline,
            next_check=excluded.next_check,lease_until=0,attempts=0,last_wake=0,state='checking',error=''
            WHERE live_room_wake.deadline<=? AND live_room_wake.next_check<=? AND live_room_wake.lease_until<=?""",
            (linked['room_id'], linked['id'], now + WAKE_WINDOW, now, now, now, now))
    return True


def wake_status(build_id):
    linked = wake_eligible(db.get(), build_id)
    row = linked and db.query('SELECT state,error FROM live_room_wake WHERE live_id=?', (linked['id'],), one=True)
    return dict(row) if row else None


def run_wake(room_id, now):
    with db.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("""SELECT w.*,l.build_id FROM live_room_wake w JOIN live_rooms l ON l.id=w.live_id
            WHERE w.room_id=? AND w.state IN ('checking','starting') AND w.next_check<=? AND w.lease_until<=?""",
            (room_id, now, now)).fetchone()
        if not job:
            return
        linked = wake_eligible(conn, job['build_id'])
        if not linked or linked['id'] != job['live_id']:
            conn.execute("DELETE FROM live_room_wake WHERE room_id=?", (room_id,))
            return
        conn.execute("UPDATE live_room_wake SET lease_until=? WHERE room_id=?", (now + LEASE_SECONDS, room_id))
    state, error, next_check = job['state'], '', now + 5
    attempts = job['attempts']
    try:
        if now >= job['deadline']:
            raise live_api.APIError("Der Archipelago-Server war nach dem Startversuch nicht erreichbar.", "wake_timeout")
        room_data, _ = cached_api("room_status", room_id, now)
        slots = db.loads(linked['snapshot']).get('slots', [])
        if not slots or seed_matches(room_data, slots) is not True:
            raise live_api.APIError("Die Spieler des Servers passen nicht zu dieser Runde. Es wurden keine Befehle gesendet.", "wrong_seed")
        activity = live_metrics.stamp(room_data.get('last_activity'))
        timeout = live_metrics.number(room_data.get('timeout'), 1)
        paused = activity and timeout and now > datetime.fromisoformat(activity).timestamp() + timeout + 5
        server_ready = live_api.reachable(room_data.get('last_port'), linked['seed_name'])
        with db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = wake_eligible(conn, job['build_id'])
            if not current or current['id'] != job['live_id']:
                conn.execute("DELETE FROM live_room_wake WHERE room_id=?", (room_id,))
                return
            _update_address(conn, current, room_data, now)
            should_wake = not server_ready and paused and attempts < 2 and now >= job['last_wake'] + WAKE_RETRY
            if should_wake:
                attempts += 1
                state = 'starting'
                conn.execute("UPDATE live_room_wake SET attempts=?,last_wake=?,state=? WHERE room_id=?",
                             (attempts, now, state, room_id))
        if should_wake:
            live_api.wake_room(room_id)
            # One early room-status observation can pick up the newly assigned port.
            # An upstream Retry-After or an in-flight fetch always takes precedence.
            with db.transaction() as conn:
                conn.execute("""UPDATE live_api_cache SET next_attempt=MIN(next_attempt,?) WHERE endpoint='room_status'
                    AND identifier=? AND error='' AND lease_until<=?""", (next_check, room_id, now))
        elif server_ready:
            state, next_check = 'reachable', job['deadline']
        elif not live_metrics.number(room_data.get('last_port'), 1) or attempts:
            state = 'starting'
        else:
            state = 'checking'
    except live_api.APIError as exc:
        error = str(exc)
        next_check = now + exc.retry_after
        with db.transaction() as conn:
            cached = conn.execute("""SELECT next_attempt FROM live_api_cache
                WHERE endpoint='room_status' AND identifier=? AND error!=''""", (room_id,)).fetchone()
            if cached:
                next_check = max(next_check, cached['next_attempt'])
        if next_check >= job['deadline'] or attempts >= 2 or exc.kind in ('wrong_seed', 'not_found', 'protected'):
            state = 'error'
    with db.transaction() as conn:
        conn.execute("UPDATE live_room_wake SET state=?,error=?,next_check=?,lease_until=0 WHERE room_id=?",
                     (state, error, next_check, room_id))


def seed_matches(room_info, slots):
    players = room_info.get('players')
    if not isinstance(players, list) or not all(isinstance(row, list) and len(row) == 2
            and all(isinstance(value, str) for value in row) for row in players):
        return None
    return sorted(tuple(row) for row in players) == sorted((s['slot'], s['game_name']) for s in slots)


def cached_api(endpoint, identifier, now):
    """SQLite leases coalesce requests across browser tabs, workers and rooms."""
    with db.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO live_api_cache(endpoint,identifier) VALUES (?,?)", (endpoint, identifier))
        row = conn.execute("SELECT * FROM live_api_cache WHERE endpoint=? AND identifier=?",
                           (endpoint, identifier)).fetchone()
        if row["next_attempt"] > now or row["lease_until"] > now:
            if row["error"]:
                raise live_api.APIError(row["error"], row["error_kind"])
            if row["payload"]:
                return json.loads(row["payload"]), row["fetched_at"]
            raise live_api.APIError("Ein anderer Abruf läuft gerade.", "pending", 5)
        conn.execute("UPDATE live_api_cache SET lease_until=? WHERE endpoint=? AND identifier=?",
                     (now + LEASE_SECONDS, endpoint, identifier))
    try:
        payload = live_api.fetch(endpoint, identifier)
    except live_api.APIError as exc:
        with db.transaction() as conn:
            conn.execute("""UPDATE live_api_cache SET error=?,error_kind=?,next_attempt=?,lease_until=0
                WHERE endpoint=? AND identifier=?""",
                         (str(exc), exc.kind, now + exc.retry_after, endpoint, identifier))
        raise
    with db.transaction() as conn:
        conn.execute("""UPDATE live_api_cache SET payload=?,fetched_at=?,next_attempt=?,lease_until=0,error='',error_kind=''
            WHERE endpoint=? AND identifier=?""",
                     (db.dumps(payload), now, now + live_api.ENDPOINTS[endpoint], endpoint, identifier))
    return payload, now


def refresh(live_id, now=None):
    """One observation; holds no SQLite write transaction during network I/O."""
    now = time.time() if now is None else now
    with db.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""SELECT l.*,b.completed_at FROM live_rooms l JOIN seed_builds b ON b.id=l.build_id
            WHERE l.id=? AND l.active=1""", (live_id,)).fetchone()
        if not row or row["completed_at"] or row["next_poll"] > now or row["lease_until"] > now:
            return False
        room = dict(row)
        conn.execute("UPDATE live_rooms SET lease_until=? WHERE id=?", (now + LEASE_SECONDS, live_id))
    room_data = None
    try:
        room_data, _ = cached_api("room_status", room["room_id"], now)
        # Port discovery must not wait for (or depend on) a working tracker.
        with db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _update_address(conn, room, room_data, now)
        tracker_id = room_data.get("tracker")
        try:
            live_api.suuid(tracker_id)
        except ValueError:
            raise live_api.APIError("Der Raum hat noch keine gültige Trackerinformation.", "no_tracker")
        static, _ = cached_api("static_tracker", tracker_id, now)
        dynamic, source_at = cached_api("tracker", tracker_id, now)
        try:
            metrics = live_metrics.aggregate(room_data, static, dynamic)
        except (ValueError, KeyError, TypeError, OverflowError):
            raise live_api.APIError("Der Tracker ist noch nicht bereit oder liefert unvollständige Daten.", "incomplete")
        with db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute("""SELECT l.active,b.completed_at FROM live_rooms l
                JOIN seed_builds b ON b.id=l.build_id WHERE l.id=?""", (live_id,)).fetchone()
            if not active or not active["active"] or active["completed_at"]:
                return False
            previous = conn.execute("SELECT * FROM live_snapshots WHERE live_id=? ORDER BY id DESC LIMIT 1",
                                    (live_id,)).fetchone()
            if not previous or previous["source_at"] != source_at:
                point = live_metrics.history_point(metrics)
                before = json.loads(previous["payload"]) if previous else None
                events, reset = live_metrics.changes(before, point)
                if previous and room["tracker_id"] and room["tracker_id"] != tracker_id:
                    reset = True
                    events = [dict(kind="reset", player=None, text="Die Trackerkennung hat sich geändert. Neuer Verlaufabschnitt.")]
                segment = (previous["segment"] if previous else 1) + int(reset)
                snapshot_id = conn.execute("""INSERT INTO live_snapshots(live_id,observed_at,source_at,segment,payload)
                    VALUES (?,?,?,?,?)""", (live_id, now, source_at, segment, db.dumps(point))).lastrowid
                for event in events:
                    conn.execute("""INSERT INTO live_events(live_id,snapshot_id,observed_at,since_at,kind,player_key,message)
                        VALUES (?,?,?,?,?,?,?)""",
                                 (live_id, snapshot_id, now, previous["observed_at"] if previous else None,
                                  event["kind"], event["player"], event["text"]))
                if not reset and before:
                    _record_tracker_goals(conn, room, room_data, before, point)
            conn.execute("""UPDATE live_rooms SET tracker_id=?,room_json=?,latest_json=?,state='ready',
                error='',last_success=?,next_poll=?,lease_until=0 WHERE id=?""",
                         (tracker_id, db.dumps(room_data), db.dumps(metrics), source_at, now + POLL_SECONDS, live_id))
        return True
    except live_api.APIError as exc:
        # An unavailable tracker must not slow down a healthy room-status feed.
        # cached_api still honors each upstream endpoint's own Retry-After.
        retry_after = min(POLL_SECONDS, exc.retry_after) if room_data else exc.retry_after
        with db.transaction() as conn:
            conn.execute("""UPDATE live_rooms SET state=?,error=?,next_poll=?,lease_until=0,
                room_json=COALESCE(?,room_json) WHERE id=? AND active=1""",
                         (exc.kind, str(exc), now + retry_after,
                          db.dumps(room_data) if room_data else None, live_id))
        return False
    except Exception:
        logging.exception("Live collector failed for local connection %s", live_id)
        with db.transaction() as conn:
            conn.execute("""UPDATE live_rooms SET state='unavailable',error='Die Aktualisierung ist fehlgeschlagen.',
                next_poll=?,lease_until=0 WHERE id=?""", (now + POLL_SECONDS, live_id))
        return False


def _update_address(conn, linked, room_data, now):
    """Only link-only connections use API ports; manual addresses stay manual."""
    port = live_metrics.number(room_data.get("last_port"), 1)
    if not linked["auto_host"] or port is None or port > 65535:
        return
    active = conn.execute("""SELECT l.active,l.auto_host,l.entered_by,b.completed_at FROM live_rooms l
        JOIN seed_builds b ON b.id=l.build_id WHERE l.id=?""", (linked["id"],)).fetchone()
    if not active or not active["active"] or not active["auto_host"] or active["completed_at"]:
        return
    previous = conn.execute("SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1",
                            (linked["build_id"],)).fetchone()
    link = f"{live_api.ORIGIN}/room/{linked['room_id']}"
    if previous and official_address(previous["room_url"], previous["host"], linked["room_id"]):
        # Same room, same journal identity. A port rotation isn't a new room.
        # Manual saves and actual room changes still create a new endpoint ID.
        if previous["port"] != port:
            conn.execute("UPDATE hosted_rooms SET port=?,confirmed=0 WHERE id=?", (port, previous["id"]))
            conn.execute("""UPDATE console_recordings SET state='connecting',error='',lease_until=0
                WHERE build_id=? AND hosted_id=? AND state='action_required' AND password_required=0""",
                (linked['build_id'], previous['id']))
        return
    actor = conn.execute("SELECT id FROM users WHERE id=?", (active["entered_by"],)).fetchone()
    if not actor:
        actor = conn.execute("SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
    if actor:
        conn.execute("""INSERT INTO hosted_rooms(build_id,room_url,host,port,confirmed,entered_by,created_at)
            VALUES (?,?,?, ?,0,?,?)""", (linked["build_id"], link, "archipelago.gg", port, actor["id"], iso(now)))


def _record_tracker_goals(conn, room, room_data, before, point):
    previous = {player['key']: player['goal'] for player in before['players']}
    reached = [player for player in point['players']
               if player['goal'] is True and previous.get(player['key']) is False]
    if not reached:
        return
    build = conn.execute('SELECT snapshot FROM seed_builds WHERE id=?', (room['build_id'],)).fetchone()
    metadata = db.loads(build['snapshot'])
    endpoint = conn.execute('SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1',
                            (room['build_id'],)).fetchone()
    if (metadata.get('race') or not seed_matches(room_data, metadata.get('slots', [])) or not endpoint
            or not official_address(endpoint['room_url'], endpoint['host'], room['room_id'])):
        return
    names = room_data['players']
    for player in reached:
        team, slot = map(int, player['key'].split(':'))
        if team == 0 and 1 <= slot <= len(names) and player['game'] == names[slot - 1][1]:
            record_goal(config.DB_PATH, room['build_id'], endpoint['id'], names[slot - 1][0], transaction=conn)


def collect_due():
    now = time.time()
    with db.transaction() as conn:
        wakes = conn.execute("""SELECT room_id FROM live_room_wake WHERE state IN ('checking','starting')
            AND next_check<=? AND lease_until<=? ORDER BY next_check LIMIT 2""", (now, now)).fetchall()
        rows = conn.execute("""SELECT l.id FROM live_rooms l JOIN seed_builds b ON b.id=l.build_id
            WHERE l.active=1 AND b.completed_at IS NULL AND b.status='succeeded'
            AND l.next_poll<=? AND l.lease_until<=? ORDER BY l.next_poll LIMIT 20""",
                            (time.time(), time.time())).fetchall()
    for wake in wakes:
        if not _stop.is_set():
            run_wake(wake['room_id'], time.time())
    for row in rows:
        if _stop.is_set():
            break
        refresh(row["id"])


def start_collector():
    global _collector
    with _collector_lock:
        if _collector and _collector.is_alive():
            _wake.set()
            return
        _stop.clear()
        def run():
            while not _stop.is_set():
                try:
                    collect_due()
                except Exception:
                    logging.exception("Live collection cycle failed")
                _wake.wait(5)
                _wake.clear()
        _collector = threading.Thread(target=run, name="live-collector", daemon=True)
        _collector.start()


def round_summary(linked, build):
    """Verified per-slot snapshots for the round. History stays in the dashboard."""
    metadata = db.loads(build['snapshot'])
    slots = metadata.get('slots', [])
    race = bool(metadata.get('race'))
    room = db.loads(linked['room_json']) if linked else {}
    matches = seed_matches(room, slots)
    tracker = db.loads(linked['latest_json']) if matches else {}
    tracker_players = {
        room['players'][p['slot'] - 1][0]: p for p in tracker.get('players', [])
        if p['team'] == 0 and 1 <= p['slot'] <= len(room['players'])
        and p['game'] == room['players'][p['slot'] - 1][1]
    }
    current_port = db.query('SELECT id FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1', (build['id'],), one=True)
    hosted_id = current_port['id'] if current_port else -1
    snapshots = {row['slot_name']: row for row in db.query(
        'SELECT * FROM progression_live WHERE build_id=? AND hosted_id=?', (build['id'], hosted_id))}
    goals = {row['slot']: row['at'] for row in db.query("""SELECT json_extract(payload,'$.player_slot') AS slot,MAX(observed_at) AS at
        FROM console_events WHERE build_id=? AND hosted_id=? AND user_id IS NULL AND kind='system'
        AND json_extract(payload,'$.public_type')='Goal' GROUP BY slot""", (build['id'], hosted_id))}
    updated = []
    players = []
    for slot in slots:
        name = slot['slot']
        observed = tracker_players.get(name, {})
        checks, total, goal = observed.get('checks'), observed.get('total'), observed.get('goal')
        received = observed.get('received')
        at = linked['last_success'] if observed else None
        local = snapshots.get(name)
        if local:
            payload = db.loads(local['payload'])
            checked, missing = set(payload.get('checked', [])), set(payload.get('missing', []))
            local_total = len(checked | missing)
            if checks is None or (local['observed_at'] > (at or 0) and total in (None, local_total)):
                checks, total = len(checked), local_total
                received = len(payload.get('received', []))
                at = local['observed_at']
        if at:
            updated.append(at)
        if name in goals and (goal is None or goals[name] >= (linked['last_success'] if observed else 0)):
            goal = True
        players.append(dict(name=name, game=slot['game_name'], checks=checks, total=total, goal=goal,
                            progress=live_metrics.percent(checks, total), received=None if race else received))
    checks = sum(p['checks'] for p in players) if players and all(p['checks'] is not None for p in players) else None
    total = sum(p['total'] for p in players) if players and all(p['total'] is not None for p in players) else None
    last_item = None if race else db.query("""SELECT MAX(id) AS id FROM console_events
        WHERE build_id=? AND hosted_id=? AND kind='items' AND user_id IS NULL""", (build['id'], hosted_id), one=True)['id']
    return dict(players=players, checks=checks, total=total, progress=live_metrics.percent(checks, total),
                goals=sum(p['goal'] is True for p in players), known_goals=sum(p['goal'] is not None for p in players),
                updated_at=iso(max(updated)) if updated else None, seed_matches=matches,
                item_version=[hosted_id, max(updated, default=None), last_item])


def presentation(linked, build, window="6h", now=None):
    now = time.time() if now is None else now
    data = json.loads(linked["latest_json"]) if linked["latest_json"] else None
    metadata = db.loads(build["snapshot"])
    race = bool(metadata.get("race"))
    cutoff = {"1h": now - 3600, "6h": now - 21600, "24h": now - 86400, "all": 0}.get(window, now - 21600)
    count = db.query("SELECT COUNT(*) AS n FROM live_snapshots WHERE live_id=? AND observed_at>=?",
                     (linked["id"], cutoff), one=True)["n"]
    stride = max(1, math.ceil(count / 420))
    rows = db.query("""WITH numbered AS (
        SELECT *, ROW_NUMBER() OVER (ORDER BY id) AS sample FROM live_snapshots
        WHERE live_id=? AND observed_at>=?)
        SELECT * FROM numbered WHERE (sample-1)%?=0 OR sample=? ORDER BY id""",
                    (linked["id"], cutoff, stride, count))
    history = [dict(id=r["id"], at=iso(r["observed_at"]), segment=r["segment"],
                    **json.loads(r["payload"])) for r in rows]
    first = db.query("SELECT observed_at FROM live_snapshots WHERE live_id=? ORDER BY id LIMIT 1",
                     (linked["id"],), one=True)
    latest = db.query("SELECT * FROM live_snapshots WHERE live_id=? ORDER BY id DESC LIMIT 1",
                      (linked["id"],), one=True)
    delta = {}
    recent_delta = {}
    recent_since = None
    since = None
    if latest:
        previous = db.query("SELECT * FROM live_snapshots WHERE live_id=? AND id<? AND segment=? ORDER BY id DESC LIMIT 1",
                            (linked["id"], latest["id"], latest["segment"]), one=True)
        if previous:
            recent_since = iso(previous["observed_at"])
            old_recent = {p["key"]: p for p in json.loads(previous["payload"])["players"]}
            for p in (data or {}).get("players", []):
                old_count = old_recent.get(p["key"], {}).get("checks")
                recent_delta[p["key"]] = p["checks"] - old_count if p["checks"] is not None and old_count is not None else None
        baseline = db.query("""SELECT * FROM live_snapshots WHERE live_id=? AND segment=?
            AND observed_at<=? ORDER BY id DESC LIMIT 1""",
                            (linked["id"], latest["segment"], now - 3600), one=True)
        if not baseline:
            baseline = db.query("SELECT * FROM live_snapshots WHERE live_id=? AND segment=? ORDER BY id LIMIT 1",
                                (linked["id"], latest["segment"]), one=True)
        if baseline:
            since = iso(baseline["observed_at"])
            old = {p["key"]: p for p in json.loads(baseline["payload"])["players"]}
            for p in (data or {}).get("players", []):
                previous = old.get(p["key"], {}).get("checks")
                delta[p["key"]] = p["checks"] - previous if p["checks"] is not None and previous is not None else None
    events = [dict(id=r["id"], at=iso(r["observed_at"]), since=iso(r["since_at"]),
                   kind=r["kind"], player=r["player_key"], text=r["message"]) for r in db.query(
        "SELECT * FROM live_events WHERE live_id=? ORDER BY id DESC LIMIT 100", (linked["id"],))]
    names={p['key']:p['name'] for p in (data or {}).get('players',[])}
    for event in events:
        prefix=names.get(event['player'],'')+': '
        if event['player'] in names and event['text'].startswith(prefix):
            event['text']=prefix+i18n.t(event['text'][len(prefix):])
        else:
            event['text']=i18n.t(event['text'])
    room_info = db.loads(linked["room_json"])
    matches = seed_matches(room_info, metadata.get("slots", []))
    if race:
        for entry in ([data] if data else []) + history:
            entry["received"] = None
            for p in entry["players"]:
                for field in ("received", "categories", "own_items", "foreign_items", "sent_to_others", "unattributed"):
                    p[field] = None
        if data:
            for field in ("interactions", "attributed", "foreign", "own"):
                data[field] = None
        events = [event for event in events if event["kind"] != "items"]
    return dict(connection_id=linked["id"], room_id=linked["room_id"], tracker_id=linked["tracker_id"] or None,
                room_url=f"{live_api.ORIGIN}/room/{linked['room_id']}", state=linked["state"],
                error=linked["error"] or None, stale=linked["state"] != "ready" or not linked["last_success"]
                or (not build["completed_at"] and now - linked["last_success"] > 120), completed=bool(build["completed_at"]),
                updated_at=iso(linked["last_success"]), next_update=iso(max(now, linked["next_poll"])),
                refresh_pending=linked["next_poll"] <= now and not build["completed_at"],
                recording_since=iso(first["observed_at"]) if first else None, interval=POLL_SECONDS,
                room=dict(port=live_metrics.number(room_info.get("last_port"), 1),
                          last_activity=live_metrics.stamp(room_info.get("last_activity"))),
                seed_matches=matches, race=race, metrics=data, history=history,
                recent_gains=recent_delta, recent_since=recent_since,
                events=events, gains=delta, gains_since=since, history_sampled=stride > 1)
