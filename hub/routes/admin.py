"""Admin HTTP handlers. Stable public endpoints."""
from flask import abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from hub import ap_bridge, db, auth
from hub.web import app
from hub.routes.security import admin_required

ITEM_LOC_GROUP = "Item & Location Options"

@app.route("/admin")
@admin_required
def admin():
    users = db.query("SELECT * FROM users ORDER BY username")
    rounds = db.query("""SELECT s.*,u.username AS owner,
        (SELECT COUNT(*) FROM seed_builds b WHERE b.session_id=s.id) AS seed_count,
        (SELECT COUNT(*) FROM seed_builds b WHERE b.session_id=s.id AND b.status IN ('queued','running')) AS busy
        FROM sessions s LEFT JOIN users u ON u.id=s.created_by ORDER BY s.id DESC""")
    seeds = db.query("""SELECT b.id,b.session_id,b.status,b.created_at,s.name AS session_name
        FROM seed_builds b JOIN sessions s ON s.id=b.session_id ORDER BY b.id DESC""")
    return render_template("admin.html", apworlds=ap_bridge.list_apworlds(),
                           admin_rounds=rounds, admin_seeds=seeds,
                           apworld_versions=ap_bridge.list_apworld_versions(), users=users,
                           failed=ap_bridge.index().get("failed", {}), status=ap_bridge.extract_status(),
                           ap_version=ap_bridge.index().get("ap_version"))


@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
@admin_required
def admin_delete_account(uid):
    from hub import admin_deletion
    name = admin_deletion.delete_account(uid, g.user["id"])
    flash(f"Konto „{name}“ gelöscht und alle Anmeldungen widerrufen. Gemeinsame Inhalte wurden dir übertragen; betroffene Runden müssen ihre Einstellungen erneut bestätigen.", "info")
    return redirect(url_for("admin", _anchor="accounts"))


@app.route("/admin/sessions/<int:sid>/delete", methods=["POST"])
@admin_required
def admin_delete_round(sid):
    from hub import admin_deletion
    name = admin_deletion.delete_round(sid)
    flash(f"Runde „{name}“ samt Seeds, Verbindungsdaten und lokalen Dateien gelöscht.", "info")
    return redirect(url_for("admin", _anchor="rounds"))


@app.route("/admin/seeds/<int:bid>/delete", methods=["POST"])
@admin_required
def admin_delete_seed(bid):
    from hub import admin_deletion
    admin_deletion.delete_seed(bid)
    flash(f"Seed #{bid} samt Analyse, Verbindungsdaten und lokalen Dateien gelöscht. Die Lobby bleibt erhalten.", "info")
    return redirect(url_for("admin", _anchor="seeds"))


@app.route("/admin/apworlds", methods=["POST"])
@admin_required
def admin_upload():
    uploaded = 0
    source_url = request.form.get("source_url", "").strip()
    for f in request.files.getlist("files"):
        if not f.filename:
            continue
        if not f.filename.lower().endswith(".apworld"):
            flash(f"{f.filename}: nur .apworld-Dateien.", "error")
            continue
        try:
            payload = f.stream.read(ap_bridge.apworld_library.MAX_UPLOAD + 1)
            with ap_bridge.ap_lock:
                info = ap_bridge.store_apworld(payload, source_url=source_url)
            uploaded += 1
            flash(f"{f.filename} gespeichert ({info['game'] or info['module']}).", "info")
        except ValueError as e:
            flash(f"{f.filename}: {e}", "error")
    if uploaded:
        ap_bridge.start_extract()
    return redirect(url_for("admin"))


@app.route("/admin/apworlds/<module>/delete", methods=["POST"])
@admin_required
def admin_delete_apworld(module):
    with ap_bridge.ap_lock:
        ap_bridge.delete_apworld(module)
    ap_bridge.start_extract()
    flash(f"{module}.apworld entfernt.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/apworlds/versions/<sha256>/activate", methods=["POST"])
@admin_required
def admin_activate_apworld(sha256):
    try:
        with ap_bridge.ap_lock:
            info = ap_bridge.activate_apworld(sha256)
        flash(f"{info['module']}: gewählte APWorld-Version aktiviert.", "info")
        ap_bridge.start_extract()
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin"))


@app.route("/admin/apworlds/versions/<sha256>/download")
@admin_required
def admin_download_apworld(sha256):
    try:
        path = ap_bridge.archived_apworld(sha256)
    except ValueError as exc:
        abort(404, description=str(exc))
    return send_file(path, as_attachment=True,
                     download_name=f"{next((v['module'] for v in ap_bridge.list_apworld_versions() if v['sha256'] == sha256), 'world')}.apworld",
                     mimetype="application/octet-stream")


@app.route("/admin/extract", methods=["POST"])
@admin_required
def admin_extract():
    ap_bridge.start_extract()
    flash("Optionen werden neu eingelesen …", "info")
    return redirect(url_for("admin"))


@app.route("/admin/users/<int:uid>/admin", methods=["POST"])
@admin_required
def admin_toggle(uid):
    if uid == g.user["id"]:
        flash("Du kannst dir selbst die Admin-Rechte nicht nehmen.", "error")
    else:
        db.execute("UPDATE users SET is_admin = 1 - is_admin WHERE id = ?", (uid,))
    return redirect(url_for("admin"))


@app.route("/admin/status")
@admin_required
def admin_status():
    return jsonify(ap_bridge.extract_status())


@app.route("/admin/users/<int:uid>/setup", methods=["POST"])
@admin_required
def admin_setup_account(uid):
    user = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not user:
        abort(404)
    token = auth.issue_setup(uid, reset=True)
    return render_template("account_code.html", code=token, account=user)
