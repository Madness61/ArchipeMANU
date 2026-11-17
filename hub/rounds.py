"""Task-oriented round navigation; reads existing records without new persistence."""
import io
import json
from pathlib import Path
import zipfile

from flask import g

from . import ap_bridge, config, db


def catalog():
    uid = g.user["id"]
    rows = db.query("""SELECT s.*,u.username AS host_name,
        (SELECT COUNT(DISTINCT user_id) FROM (
            SELECT user_id FROM lobby_members WHERE session_id=s.id
            UNION SELECT user_id FROM entries WHERE session_id=s.id)) AS member_count,
        (SELECT COUNT(*) FROM entries e WHERE e.session_id=s.id) AS game_count,
        (s.created_by=? OR EXISTS(SELECT 1 FROM lobby_members m WHERE m.session_id=s.id AND m.user_id=?)
         OR EXISTS(SELECT 1 FROM entries e WHERE e.session_id=s.id AND e.user_id=?)) AS is_member
        FROM sessions s LEFT JOIN users u ON u.id=s.created_by
        WHERE s.locked=0 OR ?=1 OR s.created_by=?
        OR EXISTS(SELECT 1 FROM lobby_members m WHERE m.session_id=s.id AND m.user_id=?)
        OR EXISTS(SELECT 1 FROM entries e WHERE e.session_id=s.id AND e.user_id=?)
        ORDER BY s.id DESC""", (uid, uid, uid, g.user["is_admin"], uid, uid, uid))
    result = []
    for row in rows:
        room = dict(row)
        build = db.query("SELECT * FROM seed_builds WHERE session_id=? ORDER BY id DESC LIMIT 1", (room["id"],), one=True)
        state, label = phase(room, build if room["locked"] else None)
        room.update(phase=state, phase_label=label, latest_build=build)
        games = ap_bridge.index()["games"]
        room["game_names"] = [games.get(r["game"], {}).get("game", r["game"]) for r in db.query(
            "SELECT DISTINCT game FROM entries WHERE session_id=?", (room["id"],))]
        result.append(room)
    return result


def phase(room, build):
    if (build and build["completed_at"]) or (not build and room["completed_at"]):
        return "completed", "Abgeschlossen"
    if build:
        if build["status"] in ("queued", "running"):
            return "preparation", "Wird generiert"
        if build["status"] == "succeeded":
            configured = db.query("SELECT 1 FROM hosted_rooms WHERE build_id=?", (build["id"],), one=True)
            return "running", "Verbindung hinterlegt" if configured else "Spiel einrichten"
        return "preparation", "Generierung fehlgeschlagen"
    return "preparation", "Vorbereitung" if not room["locked"] else "Lobby geschlossen"


def dashboard():
    rooms = catalog()
    own = [r for r in rooms if r["is_member"]]
    own.sort(key=lambda r: ({"running": 0, "preparation": 1, "completed": 2}[r["phase"]], -r["id"]))
    focus = own[0] if own else None
    others = [r for r in rooms if (r["is_member"] or not r["locked"]) and (not focus or r["id"] != focus["id"])]
    return focus, others[:8]


def selected_build(room, history, explicit=None):
    if explicit is not None:
        from flask import abort
        match = next((b for b in history if b["id"] == explicit), None)
        if match is None:
            abort(404)
        return match
    return history[0] if room["locked"] and history else None


def personal_files(build, slots, assets, distribution):
    """Attribute patches only by container identity or an exact AP-generated filename.

    Never guess by filename substring, game alone, archive order, or lobby entry order.
    Unverified files remain downloadable in the general area.
    """
    result = {slot["slot"]: [] for slot in slots}
    players = {p["name"]: p for p in (distribution or {}).get("players", [])}
    archive_path = config.SESSIONS / "_seeds" / str(build["id"]) / "output" / build["zip_name"]
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for asset in assets:
                name = Path(asset["name"]).name
                if not Path(name).suffix.lower().startswith(".ap"):
                    continue
                manifest = None
                if asset["size"] <= 16 * 1024 * 1024:
                    payload = archive.read(archive.infolist()[asset["index"]])
                    try:
                        with zipfile.ZipFile(io.BytesIO(payload)) as patch:
                            info = patch.getinfo("archipelago.json")
                            if info.file_size <= 64 * 1024 and (not info.compress_size or info.file_size / info.compress_size <= 100):
                                manifest = json.loads(patch.read(info))
                    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeError):
                        pass
                for slot in slots:
                    player = players.get(slot["slot"])
                    matched = False
                    if isinstance(manifest, dict) and manifest.get("game") == slot["game_name"]:
                        if manifest.get("player_name"):
                            matched = manifest["player_name"] == slot["slot"]
                        elif player:
                            matched = manifest.get("player") == player["id"]
                    elif manifest is None and player and build["seed_name"]:
                        matched = name == f"{build['seed_name']}_P{player['id']}_{slot['slot']}{Path(name).suffix}"
                    if matched:
                        result[slot["slot"]].append(asset)
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
        pass
    return result
