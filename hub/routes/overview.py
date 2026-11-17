"""Overview HTTP handlers. Stable public endpoints."""
import hashlib
from flask import g, render_template, url_for
from hub import ap_bridge, config, db, mvp, live_store
from hub.web import app
from hub.services.selection import session_entries, can_manage_session
from hub.routes.security import login_required

ITEM_LOC_GROUP = "Item & Location Options"

@app.context_processor
def inject_globals():
    return {"app_name": config.APP_NAME, "ap_ready": ap_bridge.ap_ready(), "extract": ap_bridge.extract_status(),
            "active_connections": mvp.active_connections(),
            "games_index": ap_bridge.index()["games"],
            "status_labels":{"queued":"Wird vorbereitet", "running":"Wird generiert", "succeeded":"Generiert",
                             "failed":"Fehlgeschlagen", "done":"Generiert", "error":"Fehlgeschlagen"}}


@app.template_filter("game_hue")
def game_hue(value):
    return int(hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8], 16) % 360


@app.route("/")
@login_required
def index():
    from hub import rounds
    focus, others = rounds.dashboard()
    action, target, live = None, None, None
    if focus:
        entries = session_entries(focus["id"])
        member_ids = {r["user_id"] for r in db.query("SELECT user_id FROM lobby_members WHERE session_id=?",(focus["id"],))} | {e["user_id"] for e in entries}
        focus["ready_count"] = sum(any(e["user_id"] == uid for e in entries) and all(
            e["ready_valid"] and e["template_found"] for e in entries if e["user_id"] == uid) for uid in member_ids)
        focus["member_count"] = len(member_ids)
        own = next((e for e in entries if e["user_id"] == g.user["id"]), None)
        build = focus["latest_build"]
        anchor = "play"
        if focus["phase"] == "completed":
            action = "Rückblick öffnen"
        elif focus["phase"] == "running":
            linked = live_store.current(build["id"])
            configured = db.query("SELECT 1 FROM hosted_rooms WHERE build_id=?",(build["id"],),one=True)
            action = "Konsole öffnen" if configured and not db.loads(build["snapshot"]).get("race") else "Jetzt spielen"
            anchor = "play"
            if linked and linked["latest_json"]:
                live = db.loads(linked["latest_json"])
        elif build and build["status"] in ("queued","running"):
            action = "Generierung ansehen"
        elif own and own["ready_valid"]:
            action = "Seed generieren" if can_manage_session(focus) and focus["ready_count"] == len(member_ids) else "Zur Runde"
            anchor = "host-controls" if action == "Seed generieren" else "play"
        else:
            action = "Bereit melden" if own else "Spiel auswählen"
        target = url_for("session_view",sid=focus["id"],_anchor=anchor)
    return render_template("overview.html",focus=focus,other_rounds=others,
                           focus_action=action,focus_url=target,focus_live=live)
