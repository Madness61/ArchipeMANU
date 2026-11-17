"""Retired experimental logic URLs. No engine imports, workers or downloads."""
from flask import Blueprint, abort, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from . import auth, console_routes

bp = Blueprint("logic", __name__)
PREFIX = "/sessions/<int:sid>/builds/<int:build_id>/live/logic"
MESSAGE = "Der experimentelle Logik-Tracker ist deaktiviert. Fortschritt, Itemprotokoll und Archipelago-Befehle bleiben verfügbar."

@bp.errorhandler(HTTPException)
def api_error(error):
    if error.code == 401:
        return auth.login_required_response()
    return jsonify(error=str(error.description)), error.code

@bp.route(PREFIX)
@bp.route(PREFIX + "/data")
@bp.route(PREFIX + "/refresh", methods=["POST"])
@bp.route(PREFIX + "/placements", methods=["POST"])
@bp.route(PREFIX + "/install", methods=["POST"])
def page(sid, build_id):
    room, build, own = console_routes.access(sid, build_id)
    if not own:
        abort(403)
    if request.path.endswith("/logic"):
        return render_template("logic_disabled.html", room=room, build=build, message=MESSAGE), 410
    return jsonify(state="disabled", error=MESSAGE, go_mode=None, reachable=None), 410
