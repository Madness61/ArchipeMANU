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

POLL_SECONDS = 60
LEASE_SECONDS = 55
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
                events, reset = live_metrics.changes(json.loads(previous["payload"]) if previous else None, point)
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
        return
    actor = conn.execute("SELECT id FROM users WHERE id=?", (active["entered_by"],)).fetchone()
    if not actor:
        actor = conn.execute("SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
    if actor:
        conn.execute("""INSERT INTO hosted_rooms(build_id,room_url,host,port,confirmed,entered_by,created_at)
            VALUES (?,?,?, ?,0,?,?)""", (linked["build_id"], link, "archipelago.gg", port, actor["id"], iso(now)))


def collect_due():
    with db.transaction() as conn:
        rows = conn.execute("""SELECT l.id FROM live_rooms l JOIN seed_builds b ON b.id=l.build_id
            WHERE l.active=1 AND b.completed_at IS NULL AND b.status='succeeded'
            AND l.next_poll<=? AND l.lease_until<=? ORDER BY l.next_poll LIMIT 20""",
                            (time.time(), time.time())).fetchall()
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
    expected = sorted((s["slot"], s["game_name"]) for s in metadata.get("slots", []))
    actual = room_info.get("players")
    seed_matches = (sorted(tuple(v) for v in actual) == expected
                    if isinstance(actual, list) and all(isinstance(v, list) and len(v) == 2 for v in actual) else None)
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
                seed_matches=seed_matches, race=race, metrics=data, history=history,
                recent_gains=recent_delta, recent_since=recent_since,
                events=events, gains=delta, gains_since=since, history_sampled=stride > 1)
