import functools
import hmac
import io
import shutil
import threading
import zipfile

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, session,
                   url_for)

from . import ap_bridge, config, db, yamlgen, mvp

app = Flask(__name__)
app.teardown_appcontext(db.close)

ITEM_LOC_GROUP = "Item & Location Options"


# --- Auth --------------------------------------------------------------------------------------

@app.before_request
def load_user():
    g.user = None
    if "uid" in session:
        g.user = db.query("SELECT * FROM users WHERE id = ?", (session["uid"],), one=True)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or len(username) > 32:
            flash("Bitte einen Namen mit höchstens 32 Zeichen eingeben.", "error")
        elif config.GROUP_PASSWORD and not hmac.compare_digest(password, config.GROUP_PASSWORD):
            flash("Gruppen-Passwort falsch.", "error")
        else:
            user = db.query("SELECT * FROM users WHERE username = ?", (username,), one=True)
            if user is None:
                first = db.query("SELECT COUNT(*) AS n FROM users", one=True)["n"] == 0
                uid = db.execute("INSERT INTO users (username, slot_name, is_admin) VALUES (?, ?, ?)",
                                 (username, yamlgen.clean_slot_name(username), int(first)))
                if first:
                    flash("Du bist der erste Benutzer und damit Admin.", "info")
            else:
                uid = user["id"]
            session.clear()
            session["uid"] = uid
            session.permanent = True
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("index"))
    return render_template("login.html", needs_password=bool(config.GROUP_PASSWORD))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- Helpers -----------------------------------------------------------------------------------

def get_schema(slug: str) -> dict:
    schema = ap_bridge.schema(slug)
    if schema is None:
        abort(404, "Spiel nicht gefunden – ist die APWorld installiert und eingelesen?")
    return schema


def group_default_ref(slug: str) -> str:
    row = db.query("SELECT template_ref FROM game_defaults WHERE game = ?", (slug,), one=True)
    return row["template_ref"] if row else "default"


def resolve_template(schema: dict, ref: str) -> tuple[str, dict, bool]:
    """-> (label, values, found). Missing templates fall back to the APWorld defaults."""
    if ref.startswith("preset:"):
        name = ref[len("preset:"):]
        if name in schema["presets"]:
            return f"APWorld-Preset „{name}“", schema["presets"][name], True
    elif ref.startswith("t:") and ref[2:].isdigit():
        row = db.query("SELECT * FROM templates WHERE id = ? AND game = ?", (int(ref[2:]), schema["slug"]), one=True)
        if row:
            return f"Vorlage „{row['name']}“", db.loads(row["vals"]), True
    elif ref == "default":
        return "Standard (APWorld)", {}, True
    return "Standard (APWorld)", {}, False


def can_edit_template(row) -> bool:
    return g.user["is_admin"] or row["created_by"] == g.user["id"]


def templates_for(schema: dict) -> list[dict]:
    slug = schema["slug"]
    default_ref = group_default_ref(slug)
    result = [{"ref": "default", "name": "Standard", "source": "APWorld",
               "description": "Alle Optionen auf den Standardwerten der APWorld.", "values": {}}]
    for name, values in schema["presets"].items():
        result.append({"ref": f"preset:{name}", "name": name, "source": "APWorld-Preset", "description": "",
                       "values": values})
    rows = db.query(
        "SELECT t.*, u.username FROM templates t LEFT JOIN users u ON u.id = t.created_by "
        "WHERE t.game = ? AND (t.shared = 1 OR t.created_by = ?) ORDER BY t.shared DESC, t.name",
        (slug, g.user["id"]))
    for row in rows:
        result.append({"ref": f"t:{row['id']}", "id": row["id"], "name": row["name"],
                       "source": "Gruppe" if row["shared"] else "Persönlich", "owner": row["username"],
                       "description": row["description"], "values": db.loads(row["vals"]),
                       "editable": can_edit_template(row), "updated_at": row["updated_at"]})
    for t in result:
        t["summary"] = yamlgen.summarize(schema, t["values"])
        t["is_default"] = t["ref"] == default_ref
    result.sort(key=lambda t: not t["is_default"])
    return result


def open_sessions():
    return db.query("SELECT * FROM sessions WHERE locked = 0 ORDER BY id DESC")


def user_values(schema: dict, template_values: dict, user) -> dict:
    overrides = yamlgen.global_overrides_for(schema, db.loads(user["overrides"]))
    return yamlgen.layer(schema, template_values, overrides)


def session_entries(session_id: int) -> list[dict]:
    rows = db.query(
        "SELECT e.*, u.username, u.slot_name, u.overrides FROM entries e JOIN users u ON u.id = e.user_id "
        "WHERE e.session_id = ? ORDER BY e.id", (session_id,))
    entries = [dict(r) for r in rows]
    slots = yamlgen.assign_slot_names(entries)
    games = ap_bridge.index()["games"]
    for e in entries:
        e["slot"] = slots[e["id"]]
        e["installed"] = e["game"] in games
        e["game_name"] = games.get(e["game"], {}).get("game", e["game"])
        if e["installed"]:
            schema = ap_bridge.schema(e["game"])
            e["template_label"], tvalues, e["template_found"] = resolve_template(schema, e["template_ref"])
            e["values"] = user_values(schema, yamlgen.layer(schema, tvalues, db.loads(e["option_overrides"])), e)
        else:
            e["template_label"], e["values"], e["template_found"] = "–", {}, False
    return entries


def session_yamls(entries: list[dict]) -> list[tuple[str, str]]:
    ap_version = ap_bridge.index().get("ap_version", "0.0.0")
    files = []
    for e in entries:
        if not e["installed"]:
            continue
        schema = ap_bridge.schema(e["game"])
        text = yamlgen.player_yaml(e["slot"], schema, e["values"], f"{schema['game']} – {e['template_label']}",
                                   ap_version)
        files.append((f"{e['slot']}.yaml", text))
    return files


def get_session(session_id: int):
    row = db.query("SELECT * FROM sessions WHERE id = ?", (session_id,), one=True)
    if row is None:
        abort(404)
    return row


def can_manage_session(row) -> bool:
    return g.user["is_admin"] or row["created_by"] == g.user["id"]


@app.context_processor
def inject_globals():
    return {"ap_ready": ap_bridge.ap_ready(), "extract": ap_bridge.extract_status(),
            "games_index": ap_bridge.index()["games"]}


# --- Dashboard & games -------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    sessions = db.query(
        "SELECT s.*, u.username, (SELECT COUNT(*) FROM entries e WHERE e.session_id = s.id) AS n "
        "FROM sessions s LEFT JOIN users u ON u.id = s.created_by ORDER BY s.id DESC LIMIT 10")
    return render_template("index.html", sessions=sessions)


@app.route("/games")
@login_required
def games():
    q = request.args.get("q", "").strip().casefold()
    show_all = request.args.get("all") == "1" or bool(q)
    counts = {r["game"]: r["n"] for r in db.query(
        "SELECT game, COUNT(*) AS n FROM templates WHERE shared = 1 OR created_by = ? GROUP BY game",
        (g.user["id"],))}
    played = {r["game"] for r in db.query("SELECT DISTINCT game FROM entries")}
    rows = []
    for slug, info in ap_bridge.index()["games"].items():
        if q and q not in info["game"].casefold():
            continue
        relevant = info["custom"] or slug in counts or slug in played
        if show_all or relevant:
            rows.append({"slug": slug, **info, "templates": counts.get(slug, 0), "relevant": relevant})
    rows.sort(key=lambda r: (not r["relevant"], r["game"].casefold()))
    total = len(ap_bridge.index()["games"])
    return render_template("games.html", rows=rows, q=request.args.get("q", ""), show_all=show_all, total=total)


@app.route("/games/<slug>")
@login_required
def game(slug):
    schema = get_schema(slug)
    return render_template("game.html", schema=schema, templates=templates_for(schema), sessions=open_sessions(),
                           preselect=request.args.get("session", type=int))


@app.route("/games/<slug>/yaml")
@login_required
def game_yaml(slug):
    schema = get_schema(slug)
    label, tvalues, _found = resolve_template(schema, request.args.get("ref", "default"))
    slot = yamlgen.clean_slot_name(g.user["slot_name"])
    text = yamlgen.player_yaml(slot, schema, user_values(schema, tvalues, g.user), f"{schema['game']} – {label}",
                               ap_bridge.index().get("ap_version", "0.0.0"))
    return send_file(io.BytesIO(text.encode("utf-8")), mimetype="text/yaml", as_attachment=True,
                     download_name=f"{slot}-{slug}.yaml")


@app.route("/games/<slug>/default", methods=["POST"])
@admin_required
def set_game_default(slug):
    schema = get_schema(slug)
    ref = request.form.get("ref", "default")
    allowed = {t["ref"] for t in templates_for(schema) if t["source"] != "Persönlich"}
    if ref not in allowed:
        flash("Nur Gruppen-Vorlagen oder APWorld-Presets können Standard werden.", "error")
    else:
        db.execute("INSERT INTO game_defaults (game, template_ref) VALUES (?, ?) "
                   "ON CONFLICT(game) DO UPDATE SET template_ref = excluded.template_ref", (slug, ref))
        flash("Gruppen-Standard gesetzt.", "info")
    return redirect(url_for("game", slug=slug))


@app.route("/api/games/<slug>/templates")
@login_required
def api_templates(slug):
    schema = get_schema(slug)
    return jsonify([{"ref": t["ref"], "name": t["name"], "source": t["source"], "is_default": t["is_default"]}
                    for t in templates_for(schema)])


@app.route("/api/games/<slug>/names")
@login_required
def api_names(slug):
    schema = get_schema(slug)
    return jsonify({"items": schema["items"], "locations": schema["locations"]})


# --- Templates ---------------------------------------------------------------------------------

def visible_options(schema: dict, values: dict, expert: bool) -> list[dict]:
    if expert:
        return schema["options"]
    return [o for o in schema["options"]
            if o["key"] in values
            or (o["simple"] and o["group"] != ITEM_LOC_GROUP and o["kind"] != "raw")]


def render_form(schema, values, *, template=None, errors=None, name="", description="", shared=True):
    expert = request.args.get("expert") == "1"
    groups: dict[str, list] = {}
    for opt in visible_options(schema, values, expert):
        groups.setdefault(opt["group"], []).append(opt)
    hidden = len(schema["options"]) - sum(len(v) for v in groups.values())
    args = request.args.to_dict()
    args.pop("expert", None)
    return render_template("template_form.html", schema=schema, groups=groups, values=values, errors=errors or {},
                           template=template, name=name, description=description, shared=shared, expert=expert,
                           hidden=hidden, yg=yamlgen,
                           simple_url=url_for(request.endpoint, **request.view_args, **args),
                           expert_url=url_for(request.endpoint, **request.view_args, **args, expert=1))


@app.route("/games/<slug>/templates/new", methods=["GET", "POST"])
@login_required
def template_new(slug):
    schema = get_schema(slug)
    base_ref = request.values.get("from", "default")
    base_label, base_values, _found = resolve_template(schema, base_ref)
    if request.method == "POST":
        values, errors = yamlgen.parse_form(schema, request.form, base_values)
        name = request.form.get("name", "").strip()
        shared = request.form.get("shared") == "1"
        if not name:
            errors["_name"] = "Bitte einen Namen vergeben."
        if errors:
            flash("Bitte die markierten Felder korrigieren.", "error")
            return render_form(schema, values, errors=errors, name=name,
                               description=request.form.get("description", ""), shared=shared)
        tid = db.execute("INSERT INTO templates (game, name, description, vals, created_by, shared) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (slug, name, request.form.get("description", ""), db.dumps(values), g.user["id"], int(shared)))
        flash(f"Vorlage „{name}“ gespeichert.", "info")
        return redirect(url_for("game", slug=slug, _anchor=f"t-{tid}"))
    suggested = "" if base_ref == "default" else f"{base_label.split('„')[-1].rstrip('“')} (angepasst)"
    return render_form(schema, dict(base_values), name=suggested)


@app.route("/templates/<int:tid>/edit", methods=["GET", "POST"])
@login_required
def template_edit(tid):
    row = db.query("SELECT * FROM templates WHERE id = ?", (tid,), one=True)
    if row is None:
        abort(404)
    if not can_edit_template(row):
        return redirect(url_for("template_new", slug=row["game"], **{"from": f"t:{tid}"}))
    schema = get_schema(row["game"])
    current = db.loads(row["vals"])
    if request.method == "POST":
        values, errors = yamlgen.parse_form(schema, request.form, current)
        name = request.form.get("name", "").strip()
        shared = request.form.get("shared") == "1"
        if not name:
            errors["_name"] = "Bitte einen Namen vergeben."
        if errors:
            flash("Bitte die markierten Felder korrigieren.", "error")
            return render_form(schema, values, template=row, errors=errors, name=name,
                               description=request.form.get("description", ""), shared=shared)
        db.execute("UPDATE templates SET name = ?, description = ?, vals = ?, shared = ?, "
                   "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                   (name, request.form.get("description", ""), db.dumps(values), int(shared), tid))
        flash("Vorlage gespeichert.", "info")
        return redirect(url_for("game", slug=row["game"], _anchor=f"t-{tid}"))
    return render_form(schema, current, template=row, name=row["name"], description=row["description"],
                       shared=bool(row["shared"]))


@app.route("/templates/<int:tid>/delete", methods=["POST"])
@login_required
def template_delete(tid):
    row = db.query("SELECT * FROM templates WHERE id = ?", (tid,), one=True)
    if row is None or not can_edit_template(row):
        abort(403)
    in_use = db.query("SELECT COUNT(*) AS n FROM entries e JOIN sessions s ON s.id = e.session_id "
                      "WHERE e.template_ref = ? AND s.locked = 0", (f"t:{tid}",), one=True)["n"]
    if in_use:
        flash(f"Die Vorlage wird noch in {in_use} offenen Session-Einträgen benutzt.", "error")
    else:
        db.execute("DELETE FROM templates WHERE id = ?", (tid,))
        db.execute("DELETE FROM game_defaults WHERE template_ref = ?", (f"t:{tid}",))
        flash("Vorlage gelöscht.", "info")
    return redirect(url_for("game", slug=row["game"]))


# --- Import ------------------------------------------------------------------------------------

@app.route("/import", methods=["GET", "POST"])
@login_required
def import_view():
    results, errors = [], []
    if request.method == "POST":
        texts = [f.read().decode("utf-8", errors="replace") for f in request.files.getlist("files") if f.filename]
        if request.form.get("text", "").strip():
            texts.append(request.form["text"])
        shared = request.form.get("shared") == "1"
        index = ap_bridge.index()["games"]
        for text in texts:
            found, errs = yamlgen.import_yaml(text, index, ap_bridge.schema)
            errors += errs
            for r in found:
                r["id"] = db.execute(
                    "INSERT INTO templates (game, name, description, vals, created_by, shared) VALUES (?, ?, ?, ?, ?, ?)",
                    (r["slug"], r["name"][:80], "Importiert", db.dumps(r["values"]), g.user["id"], int(shared)))
                results.append(r)
        if not texts:
            errors.append("Keine Datei und kein Text angegeben.")
    return render_template("import.html", results=results, errors=errors)


# --- Profile -----------------------------------------------------------------------------------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    overrides = db.loads(g.user["overrides"])
    if request.method == "POST":
        slot = yamlgen.clean_slot_name(request.form.get("slot_name", ""))
        overrides = {}
        if request.form.get("death_link") in ("on", "off"):
            overrides["death_link"] = request.form["death_link"] == "on"
        pb = request.form.get("progression_balancing", "").strip()
        if pb:
            try:
                overrides["progression_balancing"] = max(0, min(99, int(pb)))
            except ValueError:
                flash("Progression Balancing muss eine Zahl zwischen 0 und 99 sein.", "error")
        db.execute("UPDATE users SET slot_name = ?, overrides = ? WHERE id = ?",
                   (slot, db.dumps(overrides), g.user["id"]))
        flash("Profil gespeichert.", "info")
        return redirect(url_for("profile"))
    mine = db.query("SELECT * FROM templates WHERE created_by = ? ORDER BY game, name", (g.user["id"],))
    return render_template("profile.html", overrides=overrides, mine=mine)


# --- Sessions ----------------------------------------------------------------------------------

@app.route("/sessions", methods=["POST"])
@login_required
def session_create():
    name = request.form.get("name", "").strip() or "Spielabend"
    sid = db.execute("INSERT INTO sessions (name, created_by) VALUES (?, ?)", (name[:80], g.user["id"]))
    return redirect(url_for("session_view", sid=sid))


@app.route("/sessions/<int:sid>")
@login_required
def session_view(sid):
    row = get_session(sid)
    entries = session_entries(sid)
    for e in entries:
        e["summary"] = yamlgen.summarize(ap_bridge.schema(e["game"]), e["values"]) if e["installed"] else []
    games = sorted(ap_bridge.index()["games"].items(), key=lambda kv: kv[1]["game"].casefold())
    history = mvp.builds(sid)
    guests = db.query("SELECT u.username FROM lobby_members m JOIN users u ON u.id=m.user_id WHERE m.session_id=? ORDER BY u.username", (sid,))
    return render_template("session.html", s=row, entries=entries, games=games,
                           manage=can_manage_session(row), build_history=history, lobby_guests=guests)


@app.route("/games/<slug>/play", methods=["POST"])
@login_required
def game_play(slug):
    """'Ich spiele das' from the game page: join an open session, or start a new one."""
    target = request.form.get("session", "new")
    if target == "new":
        sid = db.execute("INSERT INTO sessions (name, created_by) VALUES (?, ?)", ("Spielabend", g.user["id"]))
    elif target.isdigit():
        sid = int(target)
    else:
        abort(400)
    return entry_add(sid)


@app.route("/sessions/<int:sid>/entries", methods=["POST"])
@login_required
def entry_add(sid):
    row = get_session(sid)
    if row["locked"]:
        flash("Die Session ist gesperrt.", "error")
        return redirect(url_for("session_view", sid=sid))
    slug = request.form.get("game") or request.view_args.get("slug", "")
    schema = get_schema(slug)
    ref = request.form.get("ref") or group_default_ref(slug)
    _label, _values, found = resolve_template(schema, ref)
    if not found:
        abort(400)
    db.execute("INSERT INTO entries (session_id, user_id, game, template_ref) VALUES (?, ?, ?, ?)",
               (sid, g.user["id"], slug, ref))
    db.execute("INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)",
               (sid, g.user["id"]))
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
            db.execute("UPDATE entries SET template_ref = ?, ready=0 WHERE id = ?", (ref, eid))
    return redirect(url_for("session_view", sid=entry["session_id"]))


@app.route("/sessions/<int:sid>/lock", methods=["POST"])
@login_required
def session_lock(sid):
    row = get_session(sid)
    if not can_manage_session(row):
        abort(403)
    db.execute("UPDATE sessions SET locked = ? WHERE id = ?", (0 if row["locked"] else 1, sid))
    return redirect(url_for("session_view", sid=sid))


@app.route("/sessions/<int:sid>/clone", methods=["POST"])
@login_required
def session_clone(sid):
    row = get_session(sid)
    new_id = db.execute("INSERT INTO sessions (name, created_by, spoiler, race) VALUES (?, ?, ?, ?)",
                        (f"{row['name']} (neu)", g.user["id"], row["spoiler"], row["race"]))
    for e in db.query("SELECT * FROM entries WHERE session_id = ? ORDER BY id", (sid,)):
        db.execute("INSERT INTO entries (session_id, user_id, game, template_ref) VALUES (?, ?, ?, ?)",
                   (new_id, e["user_id"], e["game"], e["template_ref"]))
    flash("Session mit denselben Spielern, Spielen und Vorlagen angelegt.", "info")
    return redirect(url_for("session_view", sid=new_id))


@app.route("/sessions/<int:sid>/delete", methods=["POST"])
@login_required
def session_delete(sid):
    row = get_session(sid)
    if not can_manage_session(row):
        abort(403)
    db.execute("DELETE FROM sessions WHERE id = ?", (sid,))
    shutil.rmtree(config.SESSIONS / str(sid), ignore_errors=True)
    flash(f"Session „{row['name']}“ gelöscht.", "info")
    return redirect(url_for("index"))


@app.route("/sessions/<int:sid>/yamls.zip")
@login_required
def session_zip(sid):
    row = get_session(sid)
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
    with db.connect() as conn:
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
        flash(f"Seed-Generierung #{build_id} gestartet; ursprüngliche Einstellungen eingefroren.", "info")
    return redirect(url_for("session_view", sid=sid))


@app.route("/sessions/<int:sid>/status")
@login_required
def session_status(sid):
    row = get_session(sid)
    return jsonify({"status": row["gen_status"]})


@app.route("/sessions/<int:sid>/download")
@login_required
def session_download(sid):
    row = get_session(sid)
    if not row["gen_file"]:
        abort(404)
    return send_file(config.SESSIONS / str(sid) / "output" / row["gen_file"], as_attachment=True)


# --- Admin -------------------------------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin():
    users = db.query("SELECT * FROM users ORDER BY username")
    return render_template("admin.html", apworlds=ap_bridge.list_apworlds(),
                           apworld_versions=ap_bridge.list_apworld_versions(), users=users,
                           failed=ap_bridge.index().get("failed", {}), status=ap_bridge.extract_status(),
                           ap_version=ap_bridge.index().get("ap_version"))


@app.route("/admin/apworlds", methods=["POST"])
@admin_required
def admin_upload():
    if request.form.get("trust_apworlds") != "yes":
        flash("Bitte zuerst bestätigen, dass du den Python-Code der APWorld-Quelle geprüft hast.", "error")
        return redirect(url_for("admin"))
    uploaded = 0
    for f in request.files.getlist("files"):
        if not f.filename:
            continue
        if not f.filename.lower().endswith(".apworld"):
            flash(f"{f.filename}: nur .apworld-Dateien.", "error")
            continue
        try:
            payload = f.stream.read(ap_bridge.apworld_library.MAX_UPLOAD + 1)
            info = ap_bridge.store_apworld(payload)
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
    ap_bridge.delete_apworld(module)
    ap_bridge.start_extract()
    flash(f"{module}.apworld entfernt.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/apworlds/versions/<sha256>/activate", methods=["POST"])
@admin_required
def admin_activate_apworld(sha256):
    if request.form.get("trust_apworlds") != "yes":
        flash("Zum Aktivieren bitte die Vertrauensbestätigung auswählen.", "error")
        return redirect(url_for("admin"))
    try:
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


def create_app() -> Flask:
    config.ensure_dirs()
    db.init()
    mvp.migrate()
    if "mvp" not in app.blueprints:
        app.register_blueprint(mvp.bp)
    app.secret_key = config.secret_key()
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
    if ap_bridge.ap_ready() and not (config.SCHEMAS / "index.json").exists():
        ap_bridge.start_extract()
    return app
