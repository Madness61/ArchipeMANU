"""Round lifecycle, readiness, immutable builds and generation jobs."""
from __future__ import annotations
import hashlib
import json
import re
import secrets
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from flask import abort, flash, g, redirect, url_for
from hub import ap_bridge, config, db, stats, yamlgen
from hub.routes.registry import rounds as bp
from hub.services.selection import slot_fingerprint

_LOCK = threading.RLock()

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migrate() -> None:
    """Additive migrations only, never rewrite the existing tables or user data."""
    config.ensure_dirs()
    with db.transaction() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(entries)")}
        if "option_overrides" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN option_overrides TEXT NOT NULL DEFAULT '{}'")
        if "ready" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN ready INTEGER NOT NULL DEFAULT 0")
        if "ready_hash" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN ready_hash TEXT NOT NULL DEFAULT ''")
        if "selected_apworld_sha" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN selected_apworld_sha TEXT NOT NULL DEFAULT ''")
        if "template_snapshot" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN template_snapshot TEXT NOT NULL DEFAULT ''")
        template_cols = {r["name"] for r in conn.execute("PRAGMA table_info(templates)")}
        for name, declaration in (("source_yaml","TEXT NOT NULL DEFAULT ''"),
                                  ("source_sha256","TEXT NOT NULL DEFAULT ''"),
                                  ("requirements","TEXT NOT NULL DEFAULT '{}'"),
                                  ("immutable","INTEGER NOT NULL DEFAULT 0")):
            if name not in template_cols:
                conn.execute(f"ALTER TABLE templates ADD COLUMN {name} {declaration}")
        # Freeze existing database presets without rewriting any saved option values.
        for row in conn.execute("""SELECT e.id,e.template_ref,t.game,t.name,t.vals,t.requirements
            FROM entries e JOIN templates t ON e.template_ref='t:' || t.id
            WHERE e.template_snapshot='' AND e.game=t.game""").fetchall():
            snapshot = {"ref":row["template_ref"],"game":row["game"],"label":f"Vorlage „{row['name']}“",
                        "values":db.loads(row["vals"]),"requires":db.loads(row["requirements"])}
            conn.execute("UPDATE entries SET template_snapshot=? WHERE id=?",(db.dumps(snapshot),row["id"]))
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "description" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "completed_at" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN completed_at TEXT")
        build_cols = {r["name"] for r in conn.execute("PRAGMA table_info(seed_builds)")}
        if build_cols and "stats_json" not in build_cols:
            conn.execute("ALTER TABLE seed_builds ADD COLUMN stats_json TEXT NOT NULL DEFAULT ''")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS lobby_members(
            session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(session_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS lobby_invites(
            token_hash TEXT PRIMARY KEY,
            session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS seed_builds(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id),
            status TEXT NOT NULL, snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL, finished_at TEXT,
            log TEXT NOT NULL DEFAULT '', zip_name TEXT NOT NULL DEFAULT '',
            seed_name TEXT NOT NULL DEFAULT '', location_counts TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS hosted_rooms(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            build_id INTEGER NOT NULL REFERENCES seed_builds(id),
            room_url TEXT NOT NULL DEFAULT '', host TEXT NOT NULL, port INTEGER NOT NULL,
            confirmed INTEGER NOT NULL DEFAULT 0, entered_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS game_guides(
            slug TEXT PRIMARY KEY, verified_version TEXT NOT NULL DEFAULT '',
            game_version TEXT NOT NULL DEFAULT '', mod_url TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '', steps TEXT NOT NULL DEFAULT '',
            trouble TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
            author INTEGER NOT NULL REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS seed_completions(
            build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            finished_at TEXT NOT NULL,
            PRIMARY KEY(build_id,user_id)
        );
        """)
        build_cols = {r["name"] for r in conn.execute("PRAGMA table_info(seed_builds)")}
        if "stats_json" not in build_cols:
            conn.execute("ALTER TABLE seed_builds ADD COLUMN stats_json TEXT NOT NULL DEFAULT ''")
        if "completed_at" not in build_cols:
            conn.execute("ALTER TABLE seed_builds ADD COLUMN completed_at TEXT")
        conn.execute("""UPDATE seed_builds SET status='failed',
            log='Generierung durch Neustart des Servers unterbrochen.',
            finished_at=? WHERE status IN ('running','queued')""", (utc_now(),))


def _user():
    if g.user is None:
        abort(401)
    return g.user


def _session(sid: int):
    row = db.query("SELECT * FROM sessions WHERE id=?", (sid,), one=True)
    if row is None:
        abort(404)
    return row


def _manager(room) -> bool:
    return bool(g.user and (g.user["is_admin"] or room["created_by"] == g.user["id"]))


def _allowed(room) -> bool:
    # Every authenticated group member can view an open community lobby.
    if not room["locked"] and g.user is not None:
        return True
    if _manager(room):
        return True
    return bool(db.query(
        "SELECT 1 FROM lobby_members WHERE session_id=? AND user_id=? UNION "
        "SELECT 1 FROM entries WHERE session_id=? AND user_id=?",
        (room["id"], g.user["id"], room["id"], g.user["id"]), one=True))


def _assert_access(room):
    _user()
    if not _allowed(room):
        abort(403)


def _entry(eid: int):
    row = db.query("SELECT * FROM entries WHERE id=?", (eid,), one=True)
    if row is None:
        abort(404)
    room = _session(row["session_id"])
    if row["user_id"] != g.user["id"] and not _manager(room):
        abort(403)
    return row, room


def update_open_entry(eid, assignments, args):
    """A concurrent seed start must reject late edits, even after the page was read."""
    conn = db.get()
    changed = conn.execute(f"UPDATE entries SET {assignments} WHERE id=? AND session_id IN "
                           "(SELECT id FROM sessions WHERE locked=0)",(*args,eid)).rowcount
    conn.commit()
    if changed != 1:
        abort(409,"Die Lobby wurde inzwischen gesperrt. Die Einstellungen wurden nicht verändert.")


def _join_url(token: str):
    return url_for("mvp.invite_accept", token=token, _external=True)


def invite_create(sid: int):
    room = _session(sid)
    if not _manager(room):
        abort(403)
    if room["locked"]:
        flash("Die Lobby ist gesperrt.", "error")
        return redirect(url_for("session_view", sid=sid))
    token = secrets.token_urlsafe(30)
    digest = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
    db.execute("INSERT INTO lobby_invites(token_hash,session_id,expires_at,created_by) VALUES (?,?,?,?)",
               (digest, sid, expires, g.user["id"]))
    flash("Einladungslink (7 Tage gültig): " + _join_url(token), "info")
    return redirect(url_for("session_view", sid=sid))


def preflight(sid: int) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    """Build an immutable list of slot settings and fail closed on missing worlds."""
    from hub.services.selection import session_entries, session_yamls
    entries = session_entries(sid)
    failures = []
    if not entries:
        failures.append("Keine Spieler-Spiele konfiguriert.")
    # Joining a lobby is not enough: every joined member must choose a game.
    selected_players = {entry["user_id"] for entry in entries}
    joined = db.query("""SELECT lm.user_id, u.username FROM lobby_members lm
        JOIN users u ON u.id=lm.user_id WHERE lm.session_id=?""", (sid,))
    for member in joined:
        if member["user_id"] not in selected_players:
            failures.append(f"{member['username']} hat noch kein Spiel gewählt.")
    known_slots = {}
    for entry in entries:
        if not entry["installed"]:
            failures.append(f"{entry['username']}: {entry['game']} ist nicht installiert.")
            continue
        if entry["world_error"]:
            failures.append(f"{entry['username']}: {entry['world_error']}")
        if not entry.get("template_found"):
            failures.append(f"{entry['username']}: gespeicherte Vorlage ist nicht mehr vorhanden.")
        if not entry["ready"]:
            failures.append(f"{entry['username']} – {entry['game_name']}: noch nicht bereit.")
        elif not entry.get("ready_valid"):
            failures.append(f"{entry['username']}: Einstellungen seit der Bereitmeldung verändert.")
        if entry.get("requested_world_sha") != entry.get("active_world_sha"):
            failures.append(f"{entry['username']}: gewählte APWorld-Version ist nicht aktiv.")
        original = yamlgen.clean_slot_name(entry["slot_name"]).casefold()
        previous = known_slots.get(original)
        if previous is not None and previous != entry["user_id"]:
            failures.append(f"Slotname „{entry['slot_name']}“ ist mehrfach vergeben.")
        known_slots[original] = entry["user_id"]
        schema = entry["_schema"]
        for key, error in yamlgen.validate_values(schema, entry["values"]).items():
            failures.append(f"{entry['username']} – {entry['game_name']} – {key}: {error}")
        for key,error in yamlgen.validate_requirements(schema,entry["requirements"],ap_bridge.index().get("ap_version","0.0.0")).items():
            failures.append(f"{entry['username']} – {key}: {error}")
    files = [] if failures else session_yamls(entries)
    if not failures and len(files) != len(entries):
        failures.append("Die Anzahl erzeugter YAML-Dateien stimmt nicht mit der Spieleranzahl überein.")
    active_worlds = {v["module"]: v for v in ap_bridge.list_apworld_versions() if v["active"]}
    games = ap_bridge.index()["games"]
    selected = []
    for entry in entries:
        if not entry["installed"]:
            continue
        world = active_worlds.get(entry["game"])
        selected.append({
            "slot": entry["slot"], "player_id": entry["user_id"], "game": entry["game"],
            "game_name": entry["game_name"], "game_version": entry["game_version"],
            "apworld_sha256": entry.get("requested_world_sha") or None,
            "ready": bool(entry["ready"]),
            "values":entry["values"],"requires":entry["requirements"],
            "configuration_hash":slot_fingerprint(entry),
        })
    # Block custom world execution unless host explicitly opts into the trusted-only mode.
    if any(v["apworld_sha256"] for v in selected) and not ap_bridge.trusted_custom_execution():
        failures.append("Custom APWorlds sind gesperrt. Erst vertrauenswürdige Quellen prüfen und HUB_TRUSTED_APWORLDS=1 setzen; keine Sandbox vorhanden.")
    return selected, files, failures


def _generate_job(build_id: int, snapshot: dict, files: list[tuple[str, str]]):
    root = config.SESSIONS / "_seeds" / str(build_id)
    players = root / "players"
    output = root / "output"
    try:
        players.mkdir(parents=True, exist_ok=False)
        output.mkdir(parents=True, exist_ok=False)
        for filename, contents in files:
            (players / filename).write_bytes(contents.encode("utf-8"))
        with db.transaction() as conn:
            conn.execute("UPDATE seed_builds SET status='running' WHERE id=?", (build_id,))
        # Never re-read user options or templates while generating a snapshot.
        active = {v["module"]: v["sha256"] for v in ap_bridge.list_apworld_versions() if v["active"]}
        for slot in snapshot["slots"]:
            h = slot["apworld_sha256"]
            if h and active.get(slot["game"]) != h:
                raise ValueError(f"{slot['game']}: APWorld-Version wurde seit dem Snapshot verändert.")
        expected = {slot["game"]: slot["apworld_sha256"] for slot in snapshot["slots"]
                    if slot["apworld_sha256"]}
        ok, log, archive = ap_bridge.generate(
            players, output, snapshot["spoiler"], snapshot["race"], expected_worlds=expected)
        if not ok or archive is None:
            raise ValueError(log[-12000:] or "Archipelago hat keine Seed-ZIP erzeugt.")
        stats_path = output / "item_distribution.json"
        stats_json = ""
        if not snapshot["race"] and stats_path.is_file() and stats_path.stat().st_size <= 2 * 1024 * 1024:
            try:
                data = json.loads(stats_path.read_text(encoding="utf-8"))
                if stats.valid_distribution(data):
                    stats_json = json.dumps(data, ensure_ascii=False)
            except (OSError, ValueError, TypeError):
                pass
        with db.transaction() as conn:
            conn.execute("""UPDATE seed_builds SET status='succeeded', log=?, zip_name=?,
                seed_name=?, stats_json=?, finished_at=? WHERE id=?""",
                (log[-30000:], archive.name, archive.stem, stats_json, utc_now(), build_id))
    except Exception as exc:
        with db.transaction() as conn:
            conn.execute("UPDATE seed_builds SET status='failed', log=?, finished_at=? WHERE id=?",
                         (str(exc)[-15000:], utc_now(), build_id))


def begin_build(sid: int, spoiler: int, race: bool) -> tuple[int | None, list[str]]:
    room = _session(sid)
    if not _manager(room):
        abort(403)
    if not ap_bridge.ap_ready():
        return None, ["Archipelago-Worker nicht eingerichtet (setup.ps1 ausführen)."]
    with _LOCK:
        conn = db.get()
        conn.execute("BEGIN IMMEDIATE")
        try:
            running = db.query("SELECT id FROM seed_builds WHERE session_id=? AND status IN ('queued','running')",
                               (sid,), one=True)
            if running:
                conn.rollback()
                return None, ["Für diese Session läuft bereits eine Generierung."]
            selected, files, errors = preflight(sid)
            if errors:
                conn.rollback()
                return None, errors
            snapshot = {
                "version": 2, "session_id": sid, "archipelago_version": ap_bridge.index().get("ap_version"),
                "slots": selected, "yamls": {name: hashlib.sha256(txt.encode("utf-8")).hexdigest() for name,txt in files},
                "spoiler": spoiler, "race": race, "created_at": utc_now(),
            }
            bid = conn.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,?,?,?)",
                               (sid, "queued", json.dumps(snapshot, ensure_ascii=False), utc_now())).lastrowid
            conn.execute("UPDATE sessions SET locked=1,completed_at=NULL WHERE id=?",(sid,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        threading.Thread(target=_generate_job, args=(bid, snapshot, files), daemon=True).start()
        return bid, []


def builds(sid: int):
    return db.query("SELECT * FROM seed_builds WHERE session_id=? ORDER BY id DESC", (sid,))


def active_connections():
    """Latest configured successful seed per room, limited to actual participants/hosts.

    A saved address is not a network probe or a claim that its server is online.
    """
    if g.user is None:
        return []
    return db.query("""WITH sources AS (
        SELECT h.id,h.build_id,h.room_url,h.host,h.port,h.confirmed,h.created_at,
            CAST(strftime('%s',h.created_at) AS REAL) AS stamp FROM hosted_rooms h
        UNION ALL
        SELECT l.id,l.build_id,'https://archipelago.gg/room/' || l.room_id,
            COALESCE(h.host,'archipelago.gg'),h.port,COALESCE(h.confirmed,0),l.created_at,l.created_at
            FROM live_rooms l LEFT JOIN hosted_rooms h ON h.id=(
                SELECT MAX(h2.id) FROM hosted_rooms h2 WHERE h2.build_id=l.build_id)
            WHERE l.active=1),
        ranked AS (
          SELECT src.*,b.session_id,b.completed_at,s.name AS session_name,s.created_by,
            ROW_NUMBER() OVER (PARTITION BY b.session_id ORDER BY src.stamp DESC,src.id DESC) AS position
          FROM sources src JOIN seed_builds b ON b.id=src.build_id JOIN sessions s ON s.id=b.session_id
          WHERE b.status='succeeded')
        SELECT * FROM ranked s WHERE position=1 AND completed_at IS NULL
        AND (? OR s.created_by=?
            OR EXISTS (SELECT 1 FROM lobby_members lm WHERE lm.session_id=s.session_id AND lm.user_id=?)
            OR EXISTS (SELECT 1 FROM entries e WHERE e.session_id=s.session_id AND e.user_id=?))
        ORDER BY stamp DESC""", (g.user["is_admin"], g.user["id"], g.user["id"], g.user["id"]))


def completion_state(build):
    """Manual goal confirmations, one per account in the immutable seed snapshot.

    Current lobby selections may already belong to the next round. Deleted
    accounts remain visible in the old snapshot but cannot block its completion.
    """
    players = {}
    for slot in db.loads(build["snapshot"]).get("slots", []):
        uid = slot["player_id"]
        player = players.setdefault(uid, {"id": uid, "slots": [], "games": []})
        player["slots"].append(slot["slot"])
        player["games"].append(slot["game_name"])
    users = {row["id"]: row["username"] for row in db.query("SELECT id,username FROM users")}
    confirmations = {row["user_id"]: row["finished_at"] for row in db.query(
        "SELECT user_id,finished_at FROM seed_completions WHERE build_id=?", (build["id"],))}
    for uid, player in players.items():
        player.update(name=users.get(uid, ", ".join(player["slots"])),
                      deleted=uid not in users, finished=uid in confirmations,
                      finished_at=confirmations.get(uid))
    eligible = [p for p in players.values() if not p["deleted"]]
    own = players.get(g.user["id"]) if g.user else None
    return dict(players=list(players.values()), total=len(eligible),
                finished_count=sum(p["finished"] for p in eligible),
                own=own, completed_at=build["completed_at"])


def artifact_files(build_id: int, zip_name: str) -> list[dict]:
    """List only files actually present in the generated Archipelago package."""
    archive_path = config.SESSIONS / "_seeds" / str(build_id) / "output" / zip_name
    if not archive_path.is_file():
        return []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            result = []
            for idx, info in enumerate(archive.infolist()):
                if info.is_dir() or info.filename.endswith(".archipelago"):
                    continue
                if (info.file_size <= 0 or info.file_size > 64 * 1024 * 1024
                        or "\\" in info.filename or info.filename.startswith("/")
                        or ".." in Path(info.filename).parts
                        or (info.compress_size and info.file_size / info.compress_size > 1000)):
                    continue
                result.append({"index": idx, "name": info.filename, "size": info.file_size})
            return result
    except (zipfile.BadZipFile, OSError):
        return []


def parse_room_form(form) -> tuple[str, str, int]:
    """No scraping or external availability claims: only validate host-supplied connection data."""
    room_url = form.get("room_url", "").strip()
    host = form.get("host", "").strip().lower()
    port = form.get("port", "").strip()
    if room_url:
        u = urlsplit(room_url)
        if u.scheme != "https" or u.hostname not in ("archipelago.gg", "www.archipelago.gg") or u.username or u.password:
            raise ValueError("Bitte einen gültigen HTTPS-Raumlink von archipelago.gg verwenden.")
        if not re.fullmatch(r"/(?:room|connect|tracker)/[A-Za-z0-9_-]+/?", u.path):
            raise ValueError("Unbekannter Raumlink-Pfad. Bitte den vollständigen offiziellen Raumlink prüfen.")
    if not host or not re.fullmatch(r"[a-z0-9.-]{1,253}", host) or ".." in host:
        raise ValueError("Server-Host fehlt oder enthält ungültige Zeichen.")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("Port muss zwischen 1 und 65535 liegen.")
    return room_url, host, int(port)


def _build_distribution(build, metadata=None):
    metadata = json.loads(build["snapshot"]) if metadata is None else metadata
    if metadata.get("race") or build["status"] != "succeeded" or not build["stats_json"]:
        return None
    try:
        candidate = json.loads(build["stats_json"])
        return candidate if stats.valid_distribution(candidate) else None
    except (ValueError, TypeError):
        return None


def _build_placements(build, distribution):
    if distribution is None:
        return None
    path = config.SESSIONS / "_seeds" / str(build["id"]) / "output" / "item_placements.json"
    try:
        if path.is_file() and path.stat().st_size <= 32 * 1024 * 1024:
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if stats.valid_item_details(candidate, distribution):
                return candidate["placements"]
    except (OSError, ValueError, TypeError):
        pass
    return None


def play_context(sid, build_id):
    from hub import game_catalog
    from hub import live_store
    room = _session(sid)
    _assert_access(room)
    build = db.query("SELECT * FROM seed_builds WHERE id=? AND session_id=?", (build_id, sid), one=True)
    if not build:
        abort(404)
    hosted = db.query("SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1",
                      (build_id,), one=True)
    snapshot = json.loads(build["snapshot"])
    own = [slot for slot in snapshot["slots"] if slot["player_id"] == g.user["id"]]
    guides = {}
    for slot in snapshot["slots"]:
        guide = db.query("SELECT * FROM game_guides WHERE slug=?", (slot["game"],), one=True)
        guides[slot["game"]] = dict(guide) if guide else None
    assets = artifact_files(build_id, build["zip_name"]) if build["status"] == "succeeded" else []
    distribution = _build_distribution(build, snapshot)
    metadata = {row["module"]: dict(row) for row in db.query("SELECT * FROM game_metadata")}
    from hub import rounds
    return dict(personal_files=rounds.personal_files(build, own, assets, distribution), room=room, build=build, hosted=hosted,
                           live_connection=live_store.current(build_id),
                           completion=completion_state(build),
                           can_manage_session=_manager(room),
                           setup_infos={slot["game"]: game_catalog.details(slot["game"], slot["game_name"], metadata.get(slot["game"])) for slot in own},
                           stats=distribution, race=bool(snapshot.get("race")),
                           overview=stats.game_overview(distribution) if distribution else [],
                           slots=snapshot["slots"], own=own, guides=guides, assets=assets)
