"""Lobby-authorized dashboard and cached JSON views."""
from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for

from . import db, live_api, live_store, mvp

bp = Blueprint("live", __name__)


def access(sid, build_id):
    room = mvp._session(sid)
    mvp._user()
    member = db.query("""SELECT 1 FROM lobby_members WHERE session_id=? AND user_id=?
        UNION SELECT 1 FROM entries WHERE session_id=? AND user_id=?""",
                      (sid, g.user["id"], sid, g.user["id"]), one=True)
    if not mvp._manager(room) and not member:
        abort(403)
    build = db.query("SELECT * FROM seed_builds WHERE session_id=? AND id=?", (sid, build_id), one=True)
    if not build:
        abort(404)
    if build["status"] != "succeeded":
        abort(409, "Live-Statistiken benötigen einen erfolgreich generierten Seed.")
    return room, build


def collector():
    if not current_app.testing:
        live_store.start_collector()


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/live")
def dashboard(sid, build_id):
    room, build = access(sid, build_id)
    linked = live_store.current(build_id)
    if linked:
        collector()
    return render_template("live_dashboard.html", room=room, build=build, linked=linked,
                           manager=mvp._manager(room))


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/live/data")
def data(sid, build_id):
    _, build = access(sid, build_id)
    linked = live_store.current(build_id)
    if not linked:
        return jsonify({"state": "not_linked", "error": "Noch kein Archipelago-Raum verbunden."}), 404
    collector()
    response = jsonify(live_store.presentation(linked, build, request.args.get("window", "6h")))
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/live/connect", methods=["POST"])
def connect(sid, build_id):
    room, build = access(sid, build_id)
    if not mvp._manager(room):
        abort(403)
    if build["completed_at"]:
        abort(409, "Diese Runde ist abgeschlossen. Für eine neue Runde einen neuen Seed erstellen.")
    try:
        link = request.form.get("room_url", "")
        live_api.room_id(link)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("live.dashboard", sid=sid, build_id=build_id))
    live_store.attach(build_id, link, g.user["id"], auto_host=True)
    collector()
    return redirect(url_for("live.dashboard", sid=sid, build_id=build_id))


@bp.route("/sessions/<int:sid>/builds/<int:build_id>/live/refresh", methods=["POST"])
def refresh(sid, build_id):
    _, build = access(sid, build_id)
    linked = live_store.current(build_id)
    if not linked:
        abort(404)
    # Manual refresh re-reads the shared cache. It never bypasses upstream TTLs.
    collector()
    return jsonify(live_store.presentation(linked, build, request.args.get("window", "6h")))
