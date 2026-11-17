"""Accounts HTTP handlers. Stable public endpoints."""
from flask import flash, g, redirect, render_template, request, url_for
from hub import db, yamlgen
from hub.web import app
from hub.routes.security import login_required

ITEM_LOC_GROUP = "Item & Location Options"

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    overrides = db.loads(g.user["overrides"])
    if request.method == "POST":
        slot = yamlgen.clean_slot_name(request.form.get("slot_name", ""))
        overrides = dict(overrides)
        overrides.pop("death_link",None)
        overrides.pop("progression_balancing",None)
        if request.form.get("death_link") in ("on", "off"):
            overrides["death_link"] = request.form["death_link"] == "on"
        pb = request.form.get("progression_balancing", "").strip()
        if pb:
            try:
                value = int(pb)
                if not 0 <= value <= 99:
                    raise ValueError()
                overrides["progression_balancing"] = value
            except ValueError:
                flash("Progression Balancing muss eine Zahl zwischen 0 und 99 sein.", "error")
                return redirect(url_for("profile"))
        db.execute("UPDATE users SET slot_name = ?, overrides = ? WHERE id = ?",
                   (slot, db.dumps(overrides), g.user["id"]))
        db.execute("""UPDATE entries SET ready=0,ready_hash='' WHERE session_id IN
            (SELECT e.session_id FROM entries e JOIN sessions s ON s.id=e.session_id
             WHERE s.locked=0 AND e.user_id=?)""",(g.user["id"],))
        flash("Profil gespeichert.", "info")
        return redirect(url_for("profile"))
    mine = db.query("SELECT * FROM templates WHERE created_by = ? ORDER BY game, name", (g.user["id"],))
    return render_template("profile.html", overrides=overrides, mine=mine)
