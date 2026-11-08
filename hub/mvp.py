"""MVP extensions for invites, per-slot settings, immutable builds, hosting and guides.

Deliberately separate from the older Flask handlers so existing SQLite rows and
uploaded APWorlds continue to work. This is NOT a sandbox for custom APWorld code.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from . import ap_bridge, config, db, stats, yamlgen

bp = Blueprint("mvp", __name__)
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
        """)
        build_cols = {r["name"] for r in conn.execute("PRAGMA table_info(seed_builds)")}
        if "stats_json" not in build_cols:
            conn.execute("ALTER TABLE seed_builds ADD COLUMN stats_json TEXT NOT NULL DEFAULT ''")
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


def slot_fingerprint(entry: dict) -> str:
    record = {
        "slot": entry["slot"], "game": entry["game"],
        "values": entry.get("values", {}),
        "game_version": entry.get("game_version", ""),
        "world_sha256": entry.get("requested_world_sha") or "",
        "template_snapshot":entry.get("template_snapshot", ""),
        "requires":entry.get("requirements",{}),
        "schema":entry.get("schema_fingerprint",""),
    }
    raw = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@bp.route("/entries/<int:eid>/apworld", methods=["POST"])
def entry_world_version(eid):
    _user()
    entry, room = _entry(eid)
    if room["locked"]:
        abort(409)
    chosen = request.form.get("sha256", "").strip()
    options = {v["sha256"] for v in ap_bridge.list_apworld_versions() if v["module"] == entry["game"]}
    if chosen and chosen not in options:
        abort(400, "APWorld-Version nicht vorhanden.")
    update_open_entry(eid,"selected_apworld_sha=?, ready=0, ready_hash=''",(chosen,))
    flash("Version gewählt. Prüfe danach Optionen und Bereitschaft.", "info")
    return redirect(url_for("session_view", sid=room["id"]))


@bp.route("/seeds")
def seed_list():
    _user()
    rows = db.query("""SELECT b.id, b.session_id, b.status, b.created_at,
        s.name AS session_name FROM seed_builds b
        JOIN sessions s ON s.id=b.session_id
        WHERE (?=1 OR s.created_by=? OR EXISTS (
            SELECT 1 FROM lobby_members lm WHERE lm.session_id=s.id AND lm.user_id=?
        ) OR EXISTS (
            SELECT 1 FROM entries e WHERE e.session_id=s.id AND e.user_id=?
        )) ORDER BY b.id DESC LIMIT 100""",
        (g.user["is_admin"],g.user["id"],g.user["id"],g.user["id"]))
    return render_template("seeds.html", builds=rows)


@bp.route("/lobbies")
def lobby_list():
    _user()
    rows = db.query("""SELECT s.*, u.username AS host_name,
        (SELECT COUNT(*) FROM lobby_members lm WHERE lm.session_id=s.id) AS member_count,
        (SELECT COUNT(*) FROM entries e WHERE e.session_id=s.id) AS game_count,
        (s.created_by=? OR EXISTS (SELECT 1 FROM lobby_members lm WHERE lm.session_id=s.id AND lm.user_id=?)
         OR EXISTS (SELECT 1 FROM entries e WHERE e.session_id=s.id AND e.user_id=?)) AS is_member
        FROM sessions s LEFT JOIN users u ON u.id=s.created_by
        ORDER BY s.locked, s.id DESC""",(g.user["id"],)*3)
    return render_template("lobbies.html", rooms=rows)


@bp.route("/sessions/<int:sid>/join", methods=["POST"])
def join_open_lobby(sid):
    _user()
    room = _session(sid)
    if room["locked"]:
        abort(409, "Die Lobby ist bereits geschlossen.")
    db.execute("INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)",
               (sid, g.user["id"]))
    flash("Du bist der Lobby beigetreten. Unter „Deine Spielauswahl“ kannst du dein Spiel und die YAML-Einstellungen festlegen.", "info")
    return redirect(url_for("session_view", sid=sid))


@bp.route("/sessions/<int:sid>/leave", methods=["POST"])
def leave_lobby(sid):
    _user()
    room = _session(sid)
    if room["locked"]:
        abort(409, "Nach der Seed-Generierung ist die Lobby geschlossen.")
    db.execute("DELETE FROM entries WHERE session_id=? AND user_id=?",
               (sid, g.user["id"]))
    db.execute("DELETE FROM lobby_members WHERE session_id=? AND user_id=?",
               (sid, g.user["id"]))
    flash("Du hast die Lobby verlassen.", "info")
    return redirect(url_for("mvp.lobby_list"))


@bp.route("/sessions/<int:sid>/members/<int:uid>/remove", methods=["POST"])
def remove_member(sid, uid):
    _user()
    room = _session(sid)
    if not _manager(room):
        abort(403)
    if room["locked"]:
        abort(409)
    if uid == room["created_by"]:
        abort(400, "Host kann sich nur selbst über „Lobby verlassen“ entfernen.")
    db.execute("DELETE FROM entries WHERE session_id=? AND user_id=?", (sid, uid))
    db.execute("DELETE FROM lobby_members WHERE session_id=? AND user_id=?", (sid, uid))
    flash("Teilnehmer entfernt. Der Slot blockiert die Generierung nicht mehr.", "info")
    return redirect(url_for("session_view", sid=sid))


@bp.route("/sessions/<int:sid>/choose")
def choose_game(sid):
    _user()
    room = _session(sid)
    if room["locked"]:
        return redirect(url_for("session_view", sid=sid))
    if not _manager(room) and not db.query(
        "SELECT 1 FROM lobby_members WHERE session_id=? AND user_id=?",
        (sid, g.user["id"]), one=True):
        return redirect(url_for("mvp.lobby_list"))
    return redirect(url_for("session_view", sid=sid, _anchor="game-selection"))


@bp.route("/sessions/<int:sid>/selection", methods=["POST"])
def lobby_selection_submit(sid):
    _user()
    from . import lobby_selection
    return lobby_selection.submit(sid)


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


@bp.route("/sessions/<int:sid>/invite", methods=["POST"])
def invite_route(sid):
    _user()
    return invite_create(sid)


@bp.route("/invite/<token>", methods=["GET", "POST"])
def invite_accept(token):
    if len(token) > 100:
        abort(404)
    digest = hashlib.sha256(token.encode()).hexdigest()
    invite = db.query("SELECT * FROM lobby_invites WHERE token_hash=?", (digest,), one=True)
    if not invite or invite["expires_at"] < utc_now():
        abort(404, "Einladung ungültig oder abgelaufen.")
    room = _session(invite["session_id"])
    if not g.user:
        return redirect(url_for("login", next=request.path))
    if room["locked"]:
        abort(409, "Diese Runde nimmt keine neuen Teilnehmer mehr auf.")
    if request.method == "POST":
        db.execute("INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)",
                   (room["id"], g.user["id"]))
        flash("Du bist jetzt in der Lobby. Wähle ein Spiel aus.", "info")
        return redirect(url_for("session_view", sid=room["id"]))
    return render_template("invite.html", room=room)


@bp.route("/entries/<int:eid>/options", methods=["GET", "POST"])
def entry_options(eid):
    _user()
    entry, room = _entry(eid)
    if room["locked"]:
        abort(409, "Session ist bereits gesperrt. Für Änderungen eine neue Runde erstellen.")
    schema = ap_bridge.schema(entry["game"])
    if schema is None:
        abort(404, "Diese APWorld ist nicht verfügbar.")
    issue = ap_bridge.world_error(entry["game"],entry["selected_apworld_sha"])
    if issue:
        abort(409,issue)
    from .app import entry_preset, user_values, session_entries, entry_yaml
    _,template_values,found,requirements = entry_preset(schema,entry)
    overrides = db.loads(entry["option_overrides"])
    owner = db.query("SELECT * FROM users WHERE id=?", (entry["user_id"],), one=True)
    baseline = user_values(schema,template_values,owner)
    effective = user_values(schema,template_values,owner,overrides)
    errors = yamlgen.validate_values(schema,effective)
    errors.update(yamlgen.validate_requirements(schema,requirements,ap_bridge.index().get("ap_version","0.0.0")))
    if not found:
        errors["_template"] = "Die gewählte Vorlage fehlt oder wurde verändert. Bitte eine gültige Vorlage wählen."
    pending = False
    if request.method == "POST":
        if request.form.get("_action") == "reset":
            updated,field_errors = {},yamlgen.validate_values(schema,baseline)
        else:
            updated, field_errors = yamlgen.parse_lobby_form(schema,request.form,overrides,baseline)
        errors = {k:v for k,v in errors.items() if k in ("_template","requires")}
        errors.update(field_errors)
        pending = True
        if not errors and request.form.get("_action") != "preview":
            update_open_entry(eid,"option_overrides=?, ready=0, ready_hash=''",(db.dumps(updated),))
            flash("Deine Einstellungen wurden gespeichert; bitte erneut als bereit markieren.", "info")
            return redirect(url_for("session_view", sid=room["id"]))
        effective = user_values(schema,template_values,owner,updated)
        if errors:
            flash("Bitte fehlerhafte Optionen korrigieren. Es wurde nichts gespeichert.", "error")
    groups = {}
    expert = request.args.get("expert") == "1"
    for option in schema["options"]:
        if expert or option["key"] in overrides or effective.get(option["key"]) != option.get("default") or (
            option.get("simple") and option.get("group") != "Item & Location Options"
            and option.get("kind") != "raw"
        ):
            groups.setdefault(option["group"], []).append(option)
    selected = next(e for e in session_entries(room["id"]) if e["id"] == eid)
    selected["values"] = effective
    yaml_preview = entry_yaml(selected,schema,ap_bridge.index().get("ap_version","0.0.0")) if not errors else ""
    return render_template("entry_options.html", entry=entry, room=room, schema=schema,
                           groups=groups, values=effective, errors=errors, yg=yamlgen,
                           expert=expert, yaml_preview=yaml_preview, pending=pending,lobby=True)


@bp.route("/entries/<int:eid>/ready", methods=["POST"])
def entry_ready(eid):
    _user()
    entry, room = _entry(eid)
    if entry["user_id"] != g.user["id"]:
        abort(403, "Nur der Slot-Besitzer kann sich bereit melden.")
    if room["locked"]:
        abort(409)
    new = request.form.get("ready") == "1"
    if new:
        schema = ap_bridge.schema(entry["game"])
        if not schema:
            flash("Die APWorld ist nicht installiert.", "error")
            return redirect(url_for("session_view", sid=room["id"]))
        from .app import entry_preset, capture_template, session_entries
        if not entry["template_snapshot"]:
            try:
                snapshot = capture_template(schema,entry["template_ref"])
            except ValueError as exc:
                flash(str(exc),"error")
                return redirect(url_for("session_view",sid=room["id"]))
            update_open_entry(eid,"template_snapshot=?",(snapshot,))
        selected = next(e for e in session_entries(room["id"]) if e["id"] == eid)
        found = selected["template_found"]
        if not found:
            flash("Die ausgewählte Vorlage existiert nicht mehr.", "error")
            return redirect(url_for("session_view", sid=room["id"]))
        errors = yamlgen.validate_values(schema,selected["values"])
        errors.update(yamlgen.validate_requirements(schema,selected["requirements"],ap_bridge.index().get("ap_version","0.0.0")))
        if errors:
            flash("Optionen ungültig: " + "; ".join(f"{k}: {v}" for k,v in errors.items())[:700], "error")
            return redirect(url_for("mvp.entry_options", eid=eid))
    fingerprint = ""
    if new:
        from .app import session_entries
        selected = next(e for e in session_entries(room["id"]) if e["id"] == eid)
        if selected["world_error"]:
            flash(selected["world_error"], "error")
            return redirect(url_for("session_view", sid=room["id"]))
        fingerprint = slot_fingerprint(selected)
    update_open_entry(eid,"ready=?, ready_hash=?",(int(new),fingerprint))
    return redirect(url_for("session_view", sid=room["id"]))


def preflight(sid: int) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    """Build an immutable list of slot settings and fail closed on missing worlds."""
    from .app import session_entries, session_yamls
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
            conn.execute("UPDATE sessions SET locked=1 WHERE id=?",(sid,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        threading.Thread(target=_generate_job, args=(bid, snapshot, files), daemon=True).start()
        return bid, []


def builds(sid: int):
    return db.query("SELECT * FROM seed_builds WHERE session_id=? ORDER BY id DESC", (sid,))


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/status")
def build_status(sid, build_id):
    _assert_access(_session(sid))
    row = db.query("SELECT * FROM seed_builds WHERE id=? AND session_id=?", (build_id, sid), one=True)
    if row is None:
        abort(404)
    return jsonify({"status": row["status"], "log": row["log"][-9000:]})


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/download")
def build_download(sid, build_id):
    _assert_access(_session(sid))
    row = db.query("SELECT * FROM seed_builds WHERE id=? AND session_id=?", (build_id, sid), one=True)
    if not row or row["status"] != "succeeded":
        abort(404)
    path = config.SESSIONS / "_seeds" / str(build_id) / "output" / row["zip_name"]
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=row["zip_name"])


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


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/assets/<int:file_index>")
def build_asset(sid, build_id, file_index):
    _assert_access(_session(sid))
    build = db.query("SELECT * FROM seed_builds WHERE id=? AND session_id=?", (build_id, sid), one=True)
    if not build or build["status"] != "succeeded":
        abort(404)
    allowed = {entry["index"]: entry for entry in artifact_files(build_id, build["zip_name"])}
    if file_index not in allowed:
        abort(404)
    archive_path = config.SESSIONS / "_seeds" / str(build_id) / "output" / build["zip_name"]
    with zipfile.ZipFile(archive_path) as archive:
        payload = archive.read(archive.infolist()[file_index])
    safe_name = Path(allowed[file_index]["name"]).name[:150]
    return send_file(io.BytesIO(payload), as_attachment=True, download_name=safe_name,
                     mimetype="application/octet-stream")


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


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/hosting", methods=["POST"])
def save_hosting(sid, build_id):
    room = _session(sid)
    if not _manager(room):
        abort(403)
    build = db.query("SELECT * FROM seed_builds WHERE session_id=? AND id=?", (sid, build_id), one=True)
    if not build or build["status"] != "succeeded":
        abort(409, "Nur erfolgreiche Seeds können gehostet werden.")
    try:
        link, host, port = parse_room_form(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("session_view", sid=sid))
    db.execute("""INSERT INTO hosted_rooms(build_id,room_url,host,port,confirmed,entered_by,created_at)
                  VALUES (?,?,?,?,?,?,?)""",
               (build_id, link, host, port, int(request.form.get("confirmed") == "1"),
                g.user["id"], utc_now()))
    flash("Raumadresse diesem Seed zugeordnet. Alle Teilnehmer können sie unter „Jetzt spielen“ sehen.", "info")
    return redirect(url_for("mvp.play_page", sid=sid, build_id=build_id))


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


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/stats")
def build_stats(sid, build_id):
    room = _session(sid)
    _assert_access(room)
    build = db.query("SELECT * FROM seed_builds WHERE id=? AND session_id=?", (build_id,sid),one=True)
    if not build:
        abort(404)
    metadata = json.loads(build["snapshot"])
    # Race mode intentionally never presents spoiler-based distribution stats.
    payload = _build_distribution(build, metadata)
    placements = _build_placements(build, payload)
    return render_template("seed_stats.html", room=room, build=build,
                           hosted=db.query("SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1",(build_id,),one=True),
                           stats=payload, race=bool(metadata.get("race")),
                           overview=stats.game_overview(payload) if payload else [],
                           progression=stats.progression_items(payload, placements) if placements is not None else [],
                           progression_available=placements is not None,
                           reveal=request.args.get("spoilers") == "1")


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/stats/progression/<int:placement_id>")
def reveal_progression_world(sid, build_id, placement_id):
    room = _session(sid)
    _assert_access(room)
    build = db.query("SELECT * FROM seed_builds WHERE id=? AND session_id=?", (build_id, sid), one=True)
    if not build:
        abort(404)
    metadata = json.loads(build["snapshot"])
    if metadata.get("race"):
        abort(403, "Im Race-Modus sind Spoiler gesperrt.")
    distribution = _build_distribution(build, metadata)
    placements = _build_placements(build, distribution)
    if placements is None or placement_id >= len(placements) or placements[placement_id]["category"] != "progression":
        abort(404, "Für dieses Item sind keine verifizierten Progression-Daten verfügbar.")
    worlds = stats.progression_worlds(distribution, placements, placement_id)
    if request.accept_mimetypes.best == "application/json":
        return jsonify(worlds=worlds)
    return render_template("progression_world.html", room=room, build=build,
                           item=placements[placement_id], worlds=worlds)


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/stats/items/<int:player_id>")
def build_item_details(sid, build_id, player_id):
    room = _session(sid)
    _assert_access(room)
    build = db.query("SELECT * FROM seed_builds WHERE id=? AND session_id=?", (build_id, sid), one=True)
    if not build:
        abort(404)
    metadata = json.loads(build["snapshot"])
    if metadata.get("race"):
        abort(403, "Im Race-Modus sind Spoiler gesperrt.")
    if build["status"] != "succeeded":
        abort(404)
    distribution = _build_distribution(build, metadata)
    if distribution is None:
        abort(404)
    players = {p["id"]: p for p in distribution["players"]}
    if player_id not in players:
        abort(404)
    direction = request.args.get("direction", "recipient")
    if direction not in ("recipient", "finder"):
        abort(400)
    search = request.args.get("q", "").strip()[:100]
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        abort(400)
    placements = _build_placements(build, distribution)
    matches = [p for p in (placements or []) if p[direction] == player_id
               and search.casefold() in (p["item"] + " " + p["location"] + " "
                   + players[p["finder"]]["name"] + " " + players[p["recipient"]]["name"]).casefold()]
    pages = max(1, (len(matches) + 49) // 50)
    page = min(page, pages)
    return render_template("seed_items.html", room=room, build=build, player=players[player_id],
                           players=players, available=placements is not None,
                           rows=matches[(page-1)*50:page*50], total=len(matches),
                           page=page, pages=pages, direction=direction, q=search)


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/play")
def play_page(sid, build_id):
    from . import game_catalog
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
    return render_template("play.html", room=room, build=build, hosted=hosted,
                           setup_infos={slot["game"]: game_catalog.details(slot["game"], slot["game_name"]) for slot in own},
                           stats=distribution, race=bool(snapshot.get("race")),
                           overview=stats.game_overview(distribution) if distribution else [],
                           slots=snapshot["slots"], own=own, guides=guides, assets=assets)


@bp.route("/admin/guides/<slug>", methods=["GET", "POST"])
def guide_edit(slug):
    user = _user()
    if not user["is_admin"]:
        abort(403)
    schema = ap_bridge.schema(slug)
    if not schema:
        abort(404)
    old = db.query("SELECT * FROM game_guides WHERE slug=?", (slug,), one=True)
    if request.method == "POST":
        def field(k, n):
            return request.form.get(k, "").strip()[:n]
        url = field("source_url", 450)
        mod = field("mod_url", 450)
        for candidate in (url, mod):
            if candidate and urlsplit(candidate).scheme not in ("https", "http"):
                abort(400, "Nur vollständige HTTP(S)-Links verwenden.")
        db.execute("""INSERT INTO game_guides(slug,verified_version,game_version,mod_url,source_url,steps,trouble,updated_at,author)
                      VALUES (?,?,?,?,?,?,?,?,?)
                      ON CONFLICT(slug) DO UPDATE SET verified_version=excluded.verified_version,
                        game_version=excluded.game_version,mod_url=excluded.mod_url,
                        source_url=excluded.source_url,steps=excluded.steps,trouble=excluded.trouble,
                        updated_at=excluded.updated_at,author=excluded.author""",
                   (slug, field("verified_version", 100), field("game_version", 100),
                    mod, url, field("steps", 8000), field("trouble", 4000), utc_now(), user["id"]))
        flash("Guide gespeichert.", "info")
        return redirect(url_for("game", slug=slug))
    return render_template("guide_edit.html", schema=schema, guide=old)
