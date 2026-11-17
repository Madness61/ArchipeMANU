"""Lobbies HTTP handlers. Stable public endpoints."""
import io
import shutil
import zipfile
from flask import abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from hub import ap_bridge, config, db, yamlgen, mvp, live_store, ap_console
from hub import game_catalog
from hub.web import app
from hub.services.selection import get_schema, group_default_ref, resolve_template, capture_template, template_info, templates_for, session_entries, session_yamls, get_session, can_manage_session
from hub.routes.security import login_required
from hub.routes.admin import admin_delete_round

ITEM_LOC_GROUP = "Item & Location Options"

@app.route("/sessions", methods=["POST"])
@login_required
def session_create():
    name = request.form.get("name", "").strip() or "Spielabend"
    sid = db.execute("INSERT INTO sessions (name, created_by) VALUES (?, ?)", (name[:80], g.user["id"]))
    db.execute("INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)",
               (sid,g.user["id"]))
    return redirect(url_for("session_view", sid=sid))


@app.route("/sessions/<int:sid>")
@login_required
def session_view(sid, selection=None, build_id=None):
    from hub import game_catalog
    row = get_session(sid)
    mvp._assert_access(row)
    entries = session_entries(sid)
    for e in entries:
        e["summary"] = yamlgen.summarize(ap_bridge.schema(e["game"]), e["values"]) if e["installed"] else []
    games = sorted(ap_bridge.index()["games"].items(), key=lambda kv: kv[1]["game"].casefold())
    history = [dict(build) for build in mvp.builds(sid)]
    hosting = {row["build_id"]: dict(row) for row in db.query("""SELECT h.* FROM hosted_rooms h
        JOIN seed_builds b ON b.id=h.build_id WHERE b.session_id=?
        AND h.id=(SELECT MAX(latest.id) FROM hosted_rooms latest WHERE latest.build_id=h.build_id)""", (sid,))}
    for build in history:
        build["hosting"] = hosting.get(build["id"])
        build["live_connection"] = live_store.current(build["id"])
    check_build = next((b for b in history if b["status"] == "succeeded"), None)
    check_data = mvp._build_distribution(check_build) if check_build else None
    check_snapshot = db.loads(check_build["snapshot"]) if check_data else {}
    for entry in entries:
        entry["generated_checks"] = None
        if check_data:
            slot = next((v for v in check_snapshot.get("slots", [])
                         if v["player_id"] == entry["user_id"] and v["slot"] == entry["slot"]
                         and v["game"] == entry["game"]), None)
            player = next((v for v in check_data["players"] if slot and v["name"] == slot["slot"]
                           and v["game"] == slot["game_name"]), None)
            if player:
                entry["generated_checks"] = check_data["location_totals"][str(player["id"]) ]
                entry["checks_current"] = slot.get("configuration_hash") == mvp.slot_fingerprint(entry)
                entry["checks_build_id"] = check_build["id"]
    guests = db.query("""SELECT u.username, u.id AS user_id, e.id AS entry_id
        FROM lobby_members m JOIN users u ON u.id=m.user_id
        LEFT JOIN entries e ON e.session_id=m.session_id AND e.user_id=m.user_id
        WHERE m.session_id=? GROUP BY u.id ORDER BY u.username""", (sid,))
    is_member = bool(db.query("SELECT 1 FROM lobby_members WHERE session_id=? AND user_id=?",
                              (sid,g.user["id"]),one=True))
    own_entry = next((e for e in entries if e["user_id"] == g.user["id"]), None)
    selected_game = request.args.get("game", own_entry["game"] if own_entry else "")
    if is_member and not row["locked"]:
        from hub import lobby_selection
        if selection is None:
            selection = lobby_selection.editor(row)
    if selection:
        selected_game = selection["schema"]["slug"]
    selected_schema = ap_bridge.schema(selected_game) if selected_game else None
    selection_templates = selection["templates"] if selection else templates_for(selected_schema) if selected_schema else []
    selected_ref = selection["ref"] if selection else own_entry["template_ref"] if own_entry else ""
    template_ref = selected_ref or (group_default_ref(selected_game) if selected_game else "")
    selected_template = next((t for t in selection_templates if t["ref"] == template_ref), None)
    joined_ids = {u["user_id"] for u in guests} | {e["user_id"] for e in entries}
    ready_users = {uid for uid in joined_ids if any(e["user_id"] == uid for e in entries)
                   and all(e["ready_valid"] and e["template_found"] for e in entries if e["user_id"] == uid)}
    waiting = []
    for uid in sorted(joined_ids):
        user_entries = [e for e in entries if e["user_id"] == uid]
        name = next((u["username"] for u in guests if u["user_id"] == uid), user_entries[0]["username"] if user_entries else "Spieler")
        if uid not in ready_users:
            waiting.append({"name":name,"reason":"Spiel fehlt" if not user_entries else "Einstellungen prüfen" if any(e["world_error"] or not e["template_found"] for e in user_entries) else "Noch nicht bereit"})
    all_ready = bool(entries) and not waiting
    step = 2 if selection else 4 if own_entry and own_entry["ready_valid"] else 3 if own_entry else 1
    host_user = db.query("SELECT username FROM users WHERE id=?", (row["created_by"],), one=True)
    from hub import rounds
    explicit = build_id if build_id is not None else request.args.get("build", type=int)
    chosen = rounds.selected_build(row, history, explicit)
    play = mvp.play_context(sid, chosen["id"]) if chosen else {}
    phase, phase_label = rounds.phase(row, chosen)
    console_primary = bool(play and chosen["status"] == "succeeded" and play["hosted"]
                           and not chosen["completed_at"] and not play["race"]
                           and (is_member or can_manage_session(row)))
    return render_template("round.html", round_phase=phase, phase_label=phase_label,
                           console_primary=console_primary,console_commands=ap_console.COMMANDS,
                           play=play, **play, s=row, entries=entries, games=games,
                           host_rom_requirements=game_catalog.host_rom_requirements(entries),
                           manage=can_manage_session(row), build_history=history,
                           host_name=host_user["username"] if host_user else "Nicht mehr vorhanden",
                           lobby_guests=guests, is_member=is_member,
                           selection=selection, selected_game=selected_game, selected_ref=selected_ref,
                           selection_templates=selection_templates, yg=yamlgen,
                           selected_template=selected_template,
                           selection_template_info=[template_info(t) for t in selection_templates],
                           ready_count=len(ready_users), member_count=len(joined_ids), waiting=waiting,
                           all_ready=all_ready, own_entry=own_entry, preparation_step=step,
                           world_versions=ap_bridge.list_apworld_versions())


@app.route("/games/<slug>/play", methods=["POST"])
@login_required
def game_play(slug):
    """Open the lobby draft with this game/preset; only Apply creates a slot."""
    get_schema(slug)
    target = request.form.get("session", "new")
    if target == "new":
        sid = db.execute("INSERT INTO sessions (name, created_by) VALUES (?, ?)", ("Spielabend", g.user["id"]))
        db.execute("INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)",
                   (sid,g.user["id"]))
    elif target.isdigit():
        sid = int(target)
    else:
        abort(400)
    row = get_session(sid)
    mvp._assert_access(row)
    if row["locked"]:
        abort(409, "Die Lobby ist bereits geschlossen.")
    db.execute("INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)",
               (sid, g.user["id"]))
    return redirect(url_for("session_view", sid=sid, game=slug,
                            ref=request.form.get("ref") or group_default_ref(slug), _anchor="game-selection"))


@app.route("/sessions/<int:sid>/entries", methods=["POST"])
@login_required
def entry_add(sid):
    row = get_session(sid)
    mvp._assert_access(row)
    if row["locked"]:
        flash("Die Session ist gesperrt.", "error")
        return redirect(url_for("session_view", sid=sid))
    if not db.query("SELECT 1 FROM lobby_members WHERE session_id=? AND user_id=?",
                    (sid,g.user["id"]),one=True):
        flash("Bitte zuerst der Lobby beitreten.", "error")
        return redirect(url_for("mvp.lobby_list"))
    slug = request.form.get("game") or request.view_args.get("slug", "")
    schema = get_schema(slug)
    ref = request.form.get("ref") or group_default_ref(slug)
    _label, _values, found = resolve_template(schema, ref)
    if not found:
        abort(400)
    snapshot = capture_template(schema,ref)
    sha = next((v["sha256"] for v in ap_bridge.list_apworld_versions()
                if v["active"] and v["module"] == slug), "")
    existing = db.query("SELECT id FROM entries WHERE session_id=? AND user_id=?",
                        (sid,g.user["id"]),one=True)
    if existing:
        mvp.update_open_entry(existing["id"],"""game=?, template_ref=?, selected_apworld_sha=?,
                   template_snapshot=?, option_overrides='{}', ready=0, ready_hash=''""",(slug,ref,sha,snapshot))
    else:
        conn = db.get()
        changed = conn.execute("""INSERT INTO entries
                   (session_id, user_id, game, template_ref, selected_apworld_sha,template_snapshot)
                   SELECT ?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM sessions WHERE id=? AND locked=0)""",
                   (sid, g.user["id"], slug, ref, sha,snapshot,sid)).rowcount
        conn.commit()
        if changed != 1:
            abort(409,"Die Lobby wurde inzwischen gesperrt.")
    flash(f"Du spielst {schema['game']} in „{row['name']}“.", "info")
    return redirect(url_for("session_view", sid=sid))


def _entry_for_edit(eid):
    entry = db.query("SELECT * FROM entries WHERE id = ?", (eid,), one=True)
    if entry is None:
        abort(404)
    s = get_session(entry["session_id"])
    if entry["user_id"] != g.user["id"] and not can_manage_session(s):
        abort(403)
    if s["locked"]:
        flash("Die Session ist gesperrt.", "error")
        return entry, None
    return entry, s


@app.route("/entries/<int:eid>/delete", methods=["POST"])
@login_required
def entry_delete(eid):
    entry, s = _entry_for_edit(eid)
    if s:
        db.execute("DELETE FROM entries WHERE id = ?", (eid,))
    return redirect(url_for("session_view", sid=entry["session_id"]))


@app.route("/entries/<int:eid>/template", methods=["POST"])
@login_required
def entry_template(eid):
    entry, s = _entry_for_edit(eid)
    if s:
        schema = get_schema(entry["game"])
        ref = request.form.get("ref", "default")
        if resolve_template(schema, ref)[2]:
            mvp.update_open_entry(eid,"template_ref=?,template_snapshot=?, ready=0, ready_hash=''",
                                  (ref,capture_template(schema,ref)))
    return redirect(url_for("session_view", sid=entry["session_id"]))


@app.route("/sessions/<int:sid>/lock", methods=["POST"])
@login_required
def session_lock(sid):
    row = get_session(sid)
    if not can_manage_session(row):
        abort(403)
    with mvp._LOCK:
        conn = db.get()
        conn.execute("BEGIN IMMEDIATE")
        try:
            if db.query("SELECT 1 FROM seed_builds WHERE session_id=? AND status IN ('queued','running') LIMIT 1",
                        (sid,), one=True):
                conn.rollback()
                flash("Während der Generierung kann die Lobby nicht geöffnet oder geschlossen werden.", "error")
                return redirect(url_for("session_view", sid=sid))
            locked = db.query("SELECT locked FROM sessions WHERE id=?", (sid,), one=True)["locked"]
            conn.execute("UPDATE sessions SET locked=?,completed_at=NULL WHERE id=?", (0 if locked else 1, sid))
            if locked:
                conn.execute("UPDATE entries SET ready=0,ready_hash='' WHERE session_id=?", (sid,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    if locked:
        flash("Die Lobby ist wieder offen. Spiel und YAML-Einstellungen können geändert werden. Alle müssen sich erneut bereit melden. Vorhandene Seeds bleiben erhalten.", "info")
    return redirect(url_for("session_view", sid=sid))


@app.route("/sessions/<int:sid>/clone", methods=["POST"])
@login_required
def session_clone(sid):
    row = get_session(sid)
    mvp._assert_access(row)
    new_id = db.execute("INSERT INTO sessions (name, created_by, spoiler, race) VALUES (?, ?, ?, ?)",
                        (f"{row['name']} (neu)", g.user["id"], row["spoiler"], row["race"]))
    db.execute("INSERT INTO lobby_members(session_id,user_id) VALUES (?,?)", (new_id,g.user["id"]))
    for member in db.query("SELECT user_id FROM lobby_members WHERE session_id=?", (sid,)):
        db.execute("INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)",
                   (new_id,member["user_id"]))
    for e in db.query("SELECT * FROM entries WHERE session_id = ? ORDER BY id", (sid,)):
        db.execute("INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)",
                   (new_id,e["user_id"]))
        db.execute("""INSERT INTO entries
                   (session_id,user_id,game,template_ref,selected_apworld_sha,option_overrides,template_snapshot)
                   VALUES (?,?,?,?,?,?,?)""",
                   (new_id,e["user_id"],e["game"],e["template_ref"],
                    e["selected_apworld_sha"],e["option_overrides"],e["template_snapshot"]))
    flash("Session mit denselben Spielern, Spielen und Vorlagen angelegt.", "info")
    return redirect(url_for("session_view", sid=new_id))


@app.route("/sessions/<int:sid>/delete", methods=["POST"])
@login_required
def session_delete(sid):
    row = get_session(sid)
    if not can_manage_session(row):
        abort(403)
    if g.user["is_admin"]:
        return admin_delete_round(sid)
    if db.query("SELECT 1 FROM seed_builds WHERE session_id=? LIMIT 1", (sid,), one=True):
        flash("Sessions mit Seed-Historie bleiben erhalten und können nicht gelöscht werden.", "error")
        return redirect(url_for("session_view", sid=sid))
    db.execute("DELETE FROM sessions WHERE id = ?", (sid,))
    shutil.rmtree(config.SESSIONS / str(sid), ignore_errors=True)
    flash(f"Session „{row['name']}“ gelöscht.", "info")
    return redirect(url_for("index"))


@app.route("/sessions/<int:sid>/yamls.zip")
@login_required
def session_zip(sid):
    row = get_session(sid)
    mvp._assert_access(row)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in session_yamls(session_entries(sid)):
            zf.writestr(name, text)
    buf.seek(0)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in row["name"])
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{safe}-yamls.zip")


def _run_generation(sid: int, files: list[tuple[str, str]], spoiler: int, race: bool) -> None:
    base = config.SESSIONS / str(sid)
    players, output = base / "players", base / "output"
    for d in (players, output):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    for name, text in files:
        (players / name).write_text(text, encoding="utf-8")
    ok, log, zip_path = ap_bridge.generate(players, output, spoiler, race)
    with db.transaction() as conn:
        conn.execute("UPDATE sessions SET gen_status = ?, gen_log = ?, gen_file = ? WHERE id = ?",
                     ("done" if ok else "error", log[-30000:], zip_path.name if zip_path else "", sid))


@app.route("/sessions/<int:sid>/generate", methods=["POST"])
@login_required
def session_generate(sid):
    try:
        spoiler = int(request.form.get("spoiler", 1))
    except ValueError:
        spoiler = 1
    if spoiler not in (0, 1, 2, 3):
        abort(400)
    build_id, errors = mvp.begin_build(sid, spoiler, request.form.get("race") == "1")
    if errors:
        for msg in errors[:12]:
            flash(msg, "error")
    else:
        flash(f"Eure Runde wird erstellt (Seed #{build_id}). Eure bestätigten Einstellungen werden dafür verwendet.", "info")
    return redirect(url_for("session_view", sid=sid))


@app.route("/sessions/<int:sid>/status")
@login_required
def session_status(sid):
    row = get_session(sid)
    mvp._assert_access(row)
    return jsonify({"status": row["gen_status"]})


@app.route("/sessions/<int:sid>/download")
@login_required
def session_download(sid):
    row = get_session(sid)
    mvp._assert_access(row)
    if not row["gen_file"]:
        abort(404)
    return send_file(config.SESSIONS / str(sid) / "output" / row["gen_file"], as_attachment=True)
