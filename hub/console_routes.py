"""Authenticated, CSRF-protected API for the Archipelago TextOnly console."""
import queue

from flask import Blueprint, abort, g, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException

from . import ap_console, auth, config, db, live_routes, i18n

bp = Blueprint("console", __name__)
PREFIX = "/sessions/<int:sid>/builds/<int:build_id>/console"


@bp.errorhandler(HTTPException)
def api_error(error):
    if error.code == 401:
        return auth.login_required_response()
    if request.path.endswith("/console"):
        return error
    return jsonify(error=str(error.description)), error.code


def access(sid, build_id, mutate=False):
    room, build = live_routes.access(sid, build_id)
    metadata = db.loads(build["snapshot"])
    if metadata.get("race"):
        abort(403, "Im Race-Modus sind Itemprotokoll und Konsolen-Hinweise gesperrt.")
    if mutate and build["completed_at"]:
        abort(409, "Diese Runde ist abgeschlossen. Das gespeicherte Protokoll bleibt lesbar.")
    own = [s for s in metadata.get("slots", []) if s.get("player_id") == g.user["id"]]
    return room, build, own


def client(build_id):
    return ap_console.current(build_id, g.user["id"], auth.digest(session["auth_token"]))


def start(build, own, form):
    if not own:
        abort(403, "Nur Spieler mit eigenem Slot können die Textkonsole verbinden.")
    slot = form.get("slot") or (own[0]["slot"] if len(own) == 1 else "")
    if slot not in {s["slot"] for s in own}:
        abort(403, "Du kannst dich nur mit deinem eigenen Spielslot verbinden.")
    endpoint = db.query("SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1", (build["id"],), one=True)
    if not endpoint:
        abort(409, "Der Host muss zuerst Serveradresse und Port für diesen Seed speichern.")
    transport = form.get("transport", "auto")
    if transport not in ("auto", "ws", "wss"):
        abort(400, "Bitte Automatisch, WS oder WSS auswählen.")
    password = form.get("password", "")
    if len(password) > 1024:
        abort(400, "Das Raumpasswort ist zu lang.")
    current = client(build["id"])
    if current and current.state in ("connecting", "authenticating", "connected", "reconnecting", "temporarily_unavailable"):
        if current.slot_name == slot and current.endpoint["id"] == endpoint["id"]:
            return current
        abort(409, "Bitte zuerst die bestehende Textverbindung trennen.")
    try:
        return ap_console.start(build, g.user["id"], auth.digest(session["auth_token"]), endpoint,
                                slot, password, {"auto": None, "ws": False, "wss": True}[transport])
    except ValueError as exc:
        abort(409, str(exc))


def state(value):
    return dict(state=value.state if value else "disconnected", error=value.error if value else "",
                slot=value.slot_name if value else None, transport=value.transport if value else None,
                last_contact=value.last_contact if value else None,
                connected_at=value.connected_at if value else None,
                next_retry_at=value.next_retry_at if value else None,
                retry_attempt=value.retry_attempt if value else 0,
                reason=value.reason if value else "not_started", game_client_connection="unknown")


@bp.route(PREFIX)
def page(sid, build_id):
    room, build, own = access(sid, build_id)
    endpoint = db.query("SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1", (build_id,), one=True)
    return render_template("console.html", room=room, build=build, own=own, endpoint=endpoint,
                           commands=ap_console.COMMANDS, archived=bool(build["completed_at"]))


@bp.route(PREFIX + "/data")
def data(sid, build_id):
    access(sid, build_id)
    try:
        after = int(request.args.get("after", "0"))
        before = int(request.args.get("before", "0"))
        if after < 0 or before < 0 or (after and before):
            raise ValueError()
    except ValueError:
        abort(400, "Ungültiger Protokoll-Cursor.")
    kind = request.args.get("kind", "all")
    if kind not in ("all", "items", "chat", "system", "sent", "for_me", "from_me", "others"):
        abort(400)
    # Read invalidation metadata first: a package arriving during event rendering
    # must trigger a reload next time, rather than permanently caching raw IDs.
    catalog_version = db.query("SELECT COALESCE(MAX(updated_at),0) AS version FROM console_packages WHERE build_id=?", (build_id,), one=True)["version"]
    endpoint = db.query("SELECT id FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1",(build_id,),one=True)
    rows = ap_console.events(build_id, g.user["id"], after, kind, before)
    return jsonify(**state(client(build_id)), events=rows, cursor=rows[-1]["id"] if rows else after,
                   catalog_version=catalog_version, endpoint_id=endpoint["id"] if endpoint else None,
                   limit=100, journal_limit=ap_console.MAX_EVENTS)


@bp.route(PREFIX + "/commands")
def commands(sid, build_id):
    access(sid, build_id)
    return jsonify(commands=[dict(command=cmd, description=i18n.t(description)) for cmd, description in ap_console.COMMANDS])


@bp.route(PREFIX + "/connect", methods=["POST"])
def connect(sid, build_id):
    _, build, own = access(sid, build_id, mutate=True)
    limited = auth.consume_attempt("console-connect", str(g.user["id"]), 30)
    if limited:
        return limited
    return jsonify(**state(start(build, own, request.form))), 202


@bp.route(PREFIX + "/disconnect", methods=["POST"])
def disconnect(sid, build_id):
    access(sid, build_id)
    current = client(build_id)
    if current:
        current.close()
    return jsonify(state="disconnected", error="")


@bp.route(PREFIX + "/command", methods=["POST"])
def command(sid, build_id):
    _, build, own = access(sid, build_id, mutate=True)
    if not own:
        abort(403, "Nur Spieler mit eigenem Slot können Befehle senden.")
    text = request.form.get("text", "").strip()
    if not text or len(text) > 500 or any(ord(c) < 32 or ord(c) == 127 for c in text):
        abort(400, "Bitte eine einzelne Nachricht mit höchstens 500 Zeichen eingeben.")
    limited = auth.consume_attempt("console-command", str(g.user["id"]), 150)
    if limited:
        return limited
    verb = text.partition(" ")[0].lower()
    allowed = {c.split(" ", 1)[0] for c, _ in ap_console.COMMANDS} | {"/exit"}
    if verb.startswith("/") and verb not in allowed:
        abort(400, "Unbekannter Befehl. Mit /help siehst du die unterstützten Befehle.")
    if verb.startswith("!") and verb not in ap_console.SERVER_COMMANDS:
        abort(400, "Dieser Serverbefehl wird in der Webkonsole nicht unterstützt. Verwende /help oder !help.")
    if verb == "/help":
        ap_console.record(config.DB_PATH, build_id, g.user["id"], "system",
                          {"text": "\n".join(cmd + " – " + description for cmd, description in ap_console.COMMANDS)})
    elif verb == "/connect":
        if text != "/connect":
            abort(400, "Die Konsole verwendet die gespeicherte Serveradresse. Verbinde über das Formular oben.")
        limited = auth.consume_attempt("console-connect", str(g.user["id"]), 30)
        if limited:
            return limited
        return jsonify(**state(start(build, own, request.form))), 202
    elif verb in ("/disconnect", "/exit"):
        current = client(build_id)
        if current:
            current.close()
        return jsonify(state="disconnected")
    else:
        current = client(build_id)
        if not current or current.state != "connected":
            abort(409, "Verbinde zuerst deinen eigenen Slot mit Archipelago.")
        if text.startswith("/"):
            text = verb + text[len(verb):]
        try:
            current.outbox.put_nowait(text)
        except queue.Full:
            abort(429, "Zu viele ausstehende Befehle. Bitte kurz warten.")
    return jsonify(accepted=True), 202
