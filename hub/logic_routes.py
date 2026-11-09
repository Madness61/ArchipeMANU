"""Per-player logic API, isolated from the public spoiler-free live metrics."""
from flask import Blueprint, abort, g, jsonify, render_template, request, session

from . import auth, config, console_routes, db, logic_tracker, mvp
from werkzeug.exceptions import HTTPException

bp = Blueprint("logic", __name__)
PREFIX = "/sessions/<int:sid>/builds/<int:build_id>/live/logic"


@bp.errorhandler(HTTPException)
def api_error(error):
    if request.path.endswith("/logic"):
        return error
    return jsonify(error=str(error.description)), error.code


def own_access(sid, build_id):
    room, build, own = console_routes.access(sid, build_id)
    if not own:
        abort(403, "Für den Logik-Tracker brauchst du einen eigenen Slot in diesem Seed.")
    return room, build, own


@bp.route(PREFIX)
def page(sid, build_id):
    room, build, own = own_access(sid, build_id)
    return render_template("logic_tracker.html", room=room, build=build, own=own,
                           engine_ready=logic_tracker.engine_ready())


@bp.route(PREFIX + "/data")
@bp.route(PREFIX + "/refresh", methods=["POST"])
def data(sid, build_id):
    _, build, own = own_access(sid, build_id)
    slot_name = request.values.get("slot", own[0]["slot"])
    slot = next((s for s in own if s["slot"] == slot_name), None)
    if not slot:
        abort(403)
    if request.method == "POST":
        limited = auth.consume_attempt("logic-refresh", str(g.user["id"]), 90)
        if limited:
            return limited
    client = console_routes.client(build_id)
    value, error = logic_tracker.evaluation_input(build, slot, client)
    if error:
        result = error
    else:
        result = logic_tracker.status((str(config.DB_PATH), build_id, g.user["id"],
            auth.digest(session["auth_token"]), client.endpoint["id"], slot_name), value, request.method == "POST")
    # Never merge placement data into normal logic responses.
    response = jsonify(**result, slot=slot_name)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route(PREFIX + "/placements", methods=["POST"])
def placements(sid, build_id):
    _, build, own = own_access(sid, build_id)
    if not db.loads(build["snapshot"]).get("spoiler"):
        abort(403, "Für diesen Seed sind Spoiler deaktiviert.")
    slot_name = request.form.get("slot", own[0]["slot"])
    if slot_name not in {s["slot"] for s in own}:
        abort(403)
    distribution = mvp._build_distribution(build)
    players = {p['id']:p for p in distribution.get('players', [])} if distribution else {}
    selected = next((p for p in players.values() if p['name'] == slot_name), None)
    rows = mvp._build_placements(build, distribution)
    if rows is None or selected is None:
        abort(409, "Für diesen Seed sind keine verifizierten Itemplatzierungen gespeichert.")
    response = jsonify(placements=[dict(id=row["location_id"], item=row["item"],
        recipient=players[row['recipient']]['name']) for row in rows if row["finder"] == selected['id']])
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route(PREFIX + "/install", methods=["POST"])
def install(sid, build_id):
    own_access(sid, build_id)
    if not g.user["is_admin"]:
        abort(403)
    try:
        logic_tracker.install_engine()
    except (OSError, ValueError):
        return jsonify(error="Die geprüfte Universal-Tracker-Version konnte nicht eingerichtet werden."), 409
    return jsonify(installed=True)
