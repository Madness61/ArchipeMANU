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

from . import ap_bridge, config, db, yamlgen

bp = Blueprint("mvp", __name__)
_LOCK = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migrate() -> None:
    """Additive migrations only, never rewrite the existing tables or user data."""
    config.ensure_dirs()
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(entries)")}
        if "option_overrides" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN option_overrides TEXT NOT NULL DEFAULT '{}'")
        if "ready" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN ready INTEGER NOT NULL DEFAULT 0")
        if "ready_hash" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN ready_hash TEXT NOT NULL DEFAULT ''")
        if "selected_apworld_sha" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN selected_apworld_sha TEXT NOT NULL DEFAULT ''")
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "description" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN description TEXT NOT NULL DEFAULT ''")
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
    from .app import resolve_template, user_values
    _, template_values, _ = resolve_template(schema, entry["template_ref"])
    overrides = db.loads(entry["option_overrides"])
    effective = user_values(schema, yamlgen.layer(schema, template_values, overrides), g.user)
    errors = {}
    if request.method == "POST":
        updated, errors = yamlgen.parse_form(schema, request.form, effective)
        errors.update(yamlgen.validate_values(schema, updated))
        if not errors:
            db.execute("UPDATE entries SET option_overrides=?, ready=0 WHERE id=?",
                       (db.dumps(updated), eid))
            flash("Deine Einstellungen wurden gespeichert; bitte erneut als bereit markieren.", "info")
            return redirect(url_for("session_view", sid=room["id"]))
        effective = updated
        flash("Bitte fehlerhafte Optionen korrigieren.", "error")
    groups = {}
    expert = request.args.get("expert") == "1"
    for option in schema["options"]:
        if expert or option["key"] in effective or (
            option.get("simple") and option.get("group") != "Item & Location Options"
            and option.get("kind") != "raw"
        ):
            groups.setdefault(option["group"], []).append(option)
    yaml_preview = yamlgen.player_yaml(
        yamlgen.clean_slot_name(g.user["slot_name"]), schema, effective,
        "Konfigurationsvorschau", ap_bridge.index().get("ap_version", "0.0.0"))
    return render_template("entry_options.html", entry=entry, room=room, schema=schema,
                           groups=groups, values=effective, errors=errors, yg=yamlgen,
                           expert=expert, yaml_preview=yaml_preview)


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
        from .app import resolve_template, user_values
        _, templ, found = resolve_template(schema, entry["template_ref"])
        if not found:
            flash("Die ausgewählte Vorlage existiert nicht mehr.", "error")
            return redirect(url_for("session_view", sid=room["id"]))
        values = user_values(schema, yamlgen.layer(
            schema, templ, db.loads(entry["option_overrides"])), g.user)
        errors = yamlgen.validate_values(schema, values)
        if errors:
            flash("Optionen ungültig: " + "; ".join(f"{k}: {v}" for k,v in errors.items())[:700], "error")
            return redirect(url_for("mvp.entry_options", eid=eid))
    db.execute("UPDATE entries SET ready=? WHERE id=?", (int(new), eid))
    return redirect(url_for("session_view", sid=room["id"]))


def preflight(sid: int) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    """Build an immutable list of slot settings and fail closed on missing worlds."""
    from .app import session_entries, session_yamls
    entries = session_entries(sid)
    failures = []
    if not entries:
        failures.append("Keine Spieler-Spiele konfiguriert.")
    known_slots = {}
    for entry in entries:
        if not entry["installed"]:
            failures.append(f"{entry['username']}: {entry['game']} ist nicht installiert.")
            continue
        if not entry.get("template_found"):
            failures.append(f"{entry['username']}: gespeicherte Vorlage ist nicht mehr vorhanden.")
        if not entry["ready"]:
            failures.append(f"{entry['username']} – {entry['game_name']}: noch nicht bereit.")
        original = yamlgen.clean_slot_name(entry["slot_name"]).casefold()
        previous = known_slots.get(original)
        if previous is not None and previous != entry["user_id"]:
            failures.append(f"Slotname „{entry['slot_name']}“ ist mehrfach vergeben.")
        known_slots[original] = entry["user_id"]
        schema = ap_bridge.schema(entry["game"])
        for key, error in yamlgen.validate_values(schema, entry["values"]).items():
            failures.append(f"{entry['username']} – {entry['game_name']} – {key}: {error}")
    files = [] if failures else session_yamls(entries)
    if len(files) != len(entries):
        failures.append("Die Anzahl erzeugter YAML-Dateien stimmt nicht mit der Spieleranzahl überein.")
    active_worlds = {v["module"]: v for v in ap_bridge.list_apworld_versions() if v["active"]}
    games = ap_bridge.index()["games"]
    selected = []
    for entry in entries:
        if entry["game"] not in games:
            continue
        world = active_worlds.get(entry["game"])
        selected.append({
            "slot": entry["slot"], "player_id": entry["user_id"], "game": entry["game"],
            "game_name": entry["game_name"], "game_version": ap_bridge.schema(entry["game"])["version"],
            "apworld_sha256": world["sha256"] if world else None,
            "ready": bool(entry["ready"]),
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
            (players / filename).write_text(contents, encoding="utf-8")
        with db.connect() as conn:
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
        with db.connect() as conn:
            conn.execute("""UPDATE seed_builds SET status='succeeded', log=?, zip_name=?,
                seed_name=?, finished_at=? WHERE id=?""",
                (log[-30000:], archive.name, archive.stem, utc_now(), build_id))
    except Exception as exc:
        with db.connect() as conn:
            conn.execute("UPDATE seed_builds SET status='failed', log=?, finished_at=? WHERE id=?",
                         (str(exc)[-15000:], utc_now(), build_id))


def begin_build(sid: int, spoiler: int, race: bool) -> tuple[int | None, list[str]]:
    room = _session(sid)
    if not _manager(room):
        abort(403)
    if not ap_bridge.ap_ready():
        return None, ["Archipelago-Worker nicht eingerichtet (setup.ps1 ausführen)."]
    selected, files, errors = preflight(sid)
    if errors:
        return None, errors
    with _LOCK:
        running = db.query("SELECT id FROM seed_builds WHERE session_id=? AND status IN ('queued','running')",
                           (sid,), one=True)
        if running:
            return None, ["Für diese Session läuft bereits eine Generierung."]
        snapshot = {
            "version": 1, "session_id": sid, "archipelago_version": ap_bridge.index().get("ap_version"),
            "slots": selected, "yamls": {name: hashlib.sha256(txt.encode("utf-8")).hexdigest() for name,txt in files},
            "spoiler": spoiler, "race": race, "created_at": utc_now(),
        }
        bid = db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,?,?,?)",
                         (sid, "queued", json.dumps(snapshot, ensure_ascii=False), utc_now()))
        db.execute("UPDATE sessions SET locked=1 WHERE id=?", (sid,))
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


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/play")
def play_page(sid, build_id):
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
    return render_template("play.html", room=room, build=build, hosted=hosted,
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
