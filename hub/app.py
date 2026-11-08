import functools
import hashlib
import hmac
import io
import re
import secrets
import shutil
import threading
import zipfile

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, session,
                   url_for)

from . import ap_bridge, config, db, yamlgen, mvp, community, auth, live_store, live_routes

app = Flask(__name__)
app.teardown_appcontext(db.close)

ITEM_LOC_GROUP = "Item & Location Options"


# --- Auth --------------------------------------------------------------------------------------

@app.before_request
def check_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    expected = session.get("_csrf", "")
    provided = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    if (not isinstance(expected, str) or not expected or not provided or len(provided) > 128
            or not hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))):
        abort(403, "Ungültiger Sicherheitstoken. Bitte die Seite aktualisieren und erneut versuchen.")


@app.context_processor
def csrf_context():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["_csrf"]}


@app.before_request
def load_user():
    auth.load_user()


@app.after_request
def protect_account_responses(response):
    if (getattr(g, "user", None) is not None or request.endpoint in ("login", "logout", "admin_setup_account")
            or (request.endpoint or "").startswith("auth.")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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
    return auth.login()


@app.route("/logout", methods=["POST"])
def logout():
    return auth.logout()


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
            actor = getattr(g,"user",None)
            if not row["shared"] and not (actor and (actor["is_admin"] or actor["id"] == row["created_by"])):
                return "Persönliche Vorlage nicht zugänglich",{},False
            if row["immutable"]:
                if hashlib.sha256(row["source_yaml"].encode("utf-8")).hexdigest() != row["source_sha256"]:
                    return "Originalvorlage verändert",{},False
                originals,issues = yamlgen.import_yaml(row["source_yaml"],{schema["slug"]:{"game":schema["game"]}},lambda _:schema)
                original = next((p for p in originals if p["slug"] == schema["slug"]
                                 and p["values"] == db.loads(row["vals"])
                                 and p["requires"] == db.loads(row["requirements"])),None)
                if not original:
                    return "Originalvorlage verändert oder inkompatibel",{},False
            return f"Vorlage „{row['name']}“", db.loads(row["vals"]), True
    elif ref.startswith("c:"):
        preset = uploaded_preset(schema,ref[2:])
        if preset:
            return preset["name"],preset["values"],True
    elif ref == "default":
        return "Standard (APWorld)", {}, True
    return "Standard (APWorld)", {}, False


def uploaded_preset(schema, sha):
    if not re.fullmatch(r"[0-9a-f]{64}",sha):
        return None
    row = db.query("SELECT * FROM community_games WHERE sha256=? AND module=? AND yaml_file=sha256",
                   (sha,schema["slug"]),one=True)
    if not row:
        return None
    try:
        data = (config.DATA / "community" / sha / "options.yaml").read_bytes()
        if len(data) > community.YAML_LIMIT or hashlib.sha256(data).hexdigest() != row["yaml_sha256"]:
            return None
        results, errors = yamlgen.import_yaml(data.decode("utf-8"),{schema["slug"]:{"game":schema["game"]}},lambda _:schema)
        if errors or len(results) != 1:
            return None
        return {**results[0],"name":f"Upload · {row['display_name']} · {sha[:8]}"}
    except (OSError,UnicodeError,ValueError):
        return None


def capture_template(schema, ref):
    label, values, found = resolve_template(schema,ref)
    if not found:
        raise ValueError("Die gewählte Vorlage fehlt oder ist nicht mit dem APWorld-Schema kompatibel.")
    requirements = {}
    if ref.startswith("t:"):
        requirements = db.loads(db.query("SELECT requirements FROM templates WHERE id=?",(int(ref[2:]),),one=True)["requirements"])
    elif ref.startswith("c:"):
        requirements = uploaded_preset(schema,ref[2:])["requires"]
    return db.dumps({"ref":ref,"game":schema["slug"],"label":label,"values":values,"requires":requirements})


def entry_preset(schema, entry):
    if entry["template_snapshot"]:
        snapshot = db.loads(entry["template_snapshot"])
        if snapshot.get("ref") == entry["template_ref"] and snapshot.get("game") == entry["game"]:
            return snapshot["label"],snapshot["values"],True,snapshot.get("requires",{})
        return "Ungültiger Vorlagen-Snapshot",{},False,{}
    label,values,found = resolve_template(schema,entry["template_ref"])
    requirements = db.loads(capture_template(schema,entry["template_ref"]))["requires"] if found else {}
    return label,values,found,requirements


def can_edit_template(row) -> bool:
    return g.user["is_admin"] or row["created_by"] == g.user["id"]


def template_info(template):
    return {"ref": template["ref"], "name": template["name"], "source": template["source"],
            "description": template["description"], "summary": template["summary"],
            "is_default": template["is_default"], "compatible": not bool(template["errors"])}


def templates_for(schema: dict) -> list[dict]:
    slug = schema["slug"]
    default_ref = group_default_ref(slug)
    result = [{"ref": "default", "name": "Spiel-Standard", "source": "APWorld",
               "description": "Die Voreinstellungen dieses Spiels, ohne zusätzliche Vorlage. Gespeicherte Profilwerte werden automatisch berücksichtigt.", "values": {}}]
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
                       "editable": can_edit_template(row), "updated_at": row["updated_at"],
                       "has_source":bool(row["source_yaml"]),"source_hash":row["source_sha256"],
                       "requires":db.loads(row["requirements"]),
                       "unavailable":bool(row["immutable"] and not resolve_template(schema,f"t:{row['id']}")[2])})
        result[-1]["editable"] = bool(result[-1]["editable"] and not row["immutable"])
    for row in db.query("SELECT sha256,display_name FROM community_games WHERE module=? AND yaml_file=sha256",(slug,)):
        preset = uploaded_preset(schema,row["sha256"])
        if preset:
            result.append({"ref":"c:"+row["sha256"],"name":preset["name"],"source":"Upload",
                           "description":"Unveränderte hochgeladene YAML-Vorlage", "values":preset["values"],"requires":preset["requires"]})
        else:
            result.append({"ref":"c:"+row["sha256"],"name":"Upload · "+row["display_name"],"source":"Upload",
                           "description":"Original-YAML bleibt in der Spielebibliothek herunterladbar.","values":{},"unavailable":True})
    for t in result:
        t["summary"] = yamlgen.summarize(schema, t["values"])
        if not t["description"]:
            t["description"] = (f"{len(t['summary'])} Abweichungen vom Spiel-Standard. Die konkreten Werte stehen unten."
                                if t["summary"] else "Diese Vorlage entspricht dem Spiel-Standard.")
        t["is_default"] = t["ref"] == default_ref
        t["errors"] = yamlgen.validate_values(schema,t["values"])
        t["errors"].update(yamlgen.validate_requirements(schema,t.get("requires",{}),ap_bridge.index().get("ap_version","0.0.0")))
        if t.get("unavailable"):
            t["errors"]["_source"] = "Die Originalvorlage fehlt, wurde verändert oder passt nicht zum APWorld-Schema."
    result.sort(key=lambda t: not t["is_default"])
    return result


def open_sessions():
    return db.query("SELECT * FROM sessions WHERE locked=0 ORDER BY id DESC")


def user_values(schema: dict, template_values: dict, user, lobby_values=None) -> dict:
    overrides = yamlgen.global_overrides_for(schema, db.loads(user["overrides"]))
    return yamlgen.effective_values(schema, template_values, overrides, lobby_values)


def session_entries(session_id: int) -> list[dict]:
    rows = db.query(
        "SELECT e.*, u.username, u.slot_name, u.overrides FROM entries e JOIN users u ON u.id = e.user_id "
        "WHERE e.session_id = ? ORDER BY e.id", (session_id,))
    entries = [dict(r) for r in rows]
    slots = yamlgen.assign_slot_names(entries)
    games = ap_bridge.index()["games"]
    active = {v["module"]:v["sha256"] for v in ap_bridge.list_apworld_versions() if v["active"]}
    for e in entries:
        e["slot"] = slots[e["id"]]
        schema = ap_bridge.schema(e["game"])
        e["installed"] = e["game"] in games and schema is not None
        e["_schema"] = schema
        e["game_name"] = games.get(e["game"], {}).get("game", e["game"])
        e["game_version"] = (schema or {}).get("version", "")
        e["active_world_sha"] = active.get(e["game"], "")
        e["requested_world_sha"] = e["selected_apworld_sha"] or e["active_world_sha"]
        e["world_error"] = ap_bridge.world_error(e["game"],e["requested_world_sha"])
        e["schema_fingerprint"] = hashlib.sha256(db.dumps(schema or {}).encode("utf-8")).hexdigest()
        e["requirements"] = {}
        if e["installed"]:
            e["template_label"], tvalues, e["template_found"], e["requirements"] = entry_preset(schema,e)
            e["values"] = user_values(schema,tvalues,e,db.loads(e["option_overrides"]))
        else:
            e["template_label"], e["values"], e["template_found"] = "–", {}, False
        e["ready_valid"] = bool(e["ready"] and e["ready_hash"]
            and e["ready_hash"] == mvp.slot_fingerprint(e)
            and not e["world_error"])
    return entries


def session_yamls(entries: list[dict]) -> list[tuple[str, str]]:
    ap_version = ap_bridge.index().get("ap_version", "0.0.0")
    files = []
    for e in entries:
        if not e["installed"]:
            continue
        schema = e.get("_schema") or ap_bridge.schema(e["game"])
        text = entry_yaml(e,schema,ap_version)
        files.append((f"{e['slot']}.yaml", text))
    return files


def entry_yaml(entry,schema,ap_version):
    return yamlgen.player_yaml(entry["slot"],schema,entry["values"],
                              f"{schema['game']} – {entry['template_label']}",ap_version,entry.get("requirements",{}))


def get_session(session_id: int):
    row = db.query("SELECT * FROM sessions WHERE id = ?", (session_id,), one=True)
    if row is None:
        abort(404)
    return row


def can_manage_session(row) -> bool:
    return g.user["is_admin"] or row["created_by"] == g.user["id"]


@app.context_processor
def inject_globals():
    return {"app_name": config.APP_NAME, "ap_ready": ap_bridge.ap_ready(), "extract": ap_bridge.extract_status(),
            "active_connections": mvp.active_connections(),
            "games_index": ap_bridge.index()["games"],
            "status_labels":{"queued":"Wird vorbereitet", "running":"Wird generiert", "succeeded":"Generiert",
                             "failed":"Fehlgeschlagen", "done":"Generiert", "error":"Fehlgeschlagen"}}


# --- Dashboard & games -------------------------------------------------------------------------

@app.template_filter("game_hue")
def game_hue(value):
    return int(hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8], 16) % 360

@app.route("/")
@login_required
def index():
    sessions = db.query("""SELECT s.*,u.username AS host_name,
        (SELECT COUNT(*) FROM lobby_members lm WHERE lm.session_id=s.id) AS member_count,
        (SELECT COUNT(*) FROM entries e WHERE e.session_id=s.id) AS game_count,
        (s.created_by=? OR EXISTS (SELECT 1 FROM lobby_members lm WHERE lm.session_id=s.id AND lm.user_id=?)
         OR EXISTS (SELECT 1 FROM entries e WHERE e.session_id=s.id AND e.user_id=?)) AS is_member
        FROM sessions s LEFT JOIN users u ON u.id=s.created_by
        WHERE s.locked=0 OR s.created_by=? OR EXISTS (
            SELECT 1 FROM lobby_members lm WHERE lm.session_id=s.id AND lm.user_id=?)
            OR EXISTS (SELECT 1 FROM entries e WHERE e.session_id=s.id AND e.user_id=?)
        ORDER BY s.id DESC""", (g.user["id"],)*6)
    own_ids = {s["id"] for s in sessions if s["is_member"]}
    active = [dict(c) for c in mvp.active_connections() if c["session_id"] in own_ids]
    active_ids = {c["session_id"] for c in active}
    own_rooms = sorted([dict(s) for s in sessions if s["is_member"]],
                       key=lambda s: (0 if s["id"] in active_ids else 2 if s["completed_at"] else 1, -s["id"]))[:6]
    for room in own_rooms:
        entries = session_entries(room["id"])
        room["game_names"] = list(dict.fromkeys(e["game_name"] for e in entries))
        member_ids = {r["user_id"] for r in db.query("SELECT user_id FROM lobby_members WHERE session_id=?", (room["id"],))} | {e["user_id"] for e in entries}
        room["member_count"] = len(member_ids)
        room["ready_count"] = sum(bool([e for e in entries if e["user_id"] == uid]) and all(
            e["ready_valid"] and e["template_found"] for e in entries if e["user_id"] == uid) for uid in member_ids)
        room["own_entry"] = next((e for e in entries if e["user_id"] == g.user["id"]), None)
    focus = next((s for s in own_rooms if active and s["id"] == active[0]["session_id"]), None)
    focus = focus or next((s for s in own_rooms if not s["completed_at"]), None)
    focus_action = focus_url = None
    focus_live = None
    if focus:
        build = db.query("SELECT * FROM seed_builds WHERE session_id=? ORDER BY id DESC LIMIT 1", (focus["id"],), one=True)
        connection = next((c for c in active if c["session_id"] == focus["id"]), None)
        if connection:
            linked = live_store.current(connection["build_id"])
            focus_action = "Live-Dashboard öffnen" if linked else "Jetzt spielen"
            focus_url = url_for("live.dashboard" if linked else "mvp.play_page", sid=focus["id"], build_id=connection["build_id"])
            if linked and linked["latest_json"]:
                focus_live = db.loads(linked["latest_json"])
        elif build and build["status"] == "succeeded":
            focus_action = "Jetzt spielen"
            focus_url = url_for("mvp.play_page", sid=focus["id"], build_id=build["id"])
        else:
            own = focus["own_entry"]
            focus_action = ("Generierung ansehen" if build and build["status"] in ("queued", "running")
                            else "Zur Lobby" if focus["locked"] or (own and own["ready_valid"])
                            else "Einstellungen prüfen" if own and (own["world_error"] or not own["template_found"])
                            else "Bereit melden" if own else "Spiel auswählen")
            focus_url = url_for("session_view", sid=focus["id"], _anchor="participants-section" if own else "game-selection")
    recent = db.query("""SELECT b.id,b.session_id,b.created_at,s.name FROM seed_builds b JOIN sessions s ON s.id=b.session_id
        WHERE b.status='succeeded' AND b.completed_at IS NOT NULL AND (s.created_by=?
        OR EXISTS (SELECT 1 FROM lobby_members m WHERE m.session_id=s.id AND m.user_id=?)
        OR EXISTS (SELECT 1 FROM entries e WHERE e.session_id=s.id AND e.user_id=?))
        ORDER BY b.id DESC LIMIT 4""", (g.user["id"],)*3)
    return render_template("index.html", open_rooms=[s for s in sessions if not s["locked"]][:6],
                           own_rooms=own_rooms, focus=focus, focus_action=focus_action, focus_url=focus_url,
                           focus_live=focus_live, own_active=active, recent_rounds=recent,
                           games_total=len(community.all_games()),
                           open_total=db.query("SELECT COUNT(*) AS n FROM sessions WHERE locked=0", one=True)["n"],
                           players_total=db.query("SELECT COUNT(*) AS n FROM users", one=True)["n"])


@app.route("/games")
@login_required
def games():
    from . import game_catalog
    q = request.args.get("q", "").strip()
    library = game_catalog.enrich(community.all_games())
    kind = request.args.get("kind", "all")
    state = request.args.get("state", "all")
    # Preserve old bookmarks without continuing to call installed options 'ready'.
    state = {"ready": "loaded", "pending": "unloaded"}.get(state, state)
    genre = request.args.get("genre", "all")
    setup = request.args.get("setup", "all")
    genres = sorted({g for row in library for g in row["catalog"]["genres"]})
    setup_types = {key: label for key, label in game_catalog.SETUP_TYPES.items()
                   if any(row["catalog"]["setup_type"] == key for row in library)}
    if (kind not in ("all", "builtin", "custom")
            or state not in ("all", "unloaded", *game_catalog.SUPPORT_STATES)
            or genre not in ("all", *genres) or setup not in ("all", *setup_types)):
        abort(400, "Unbekannter Spielefilter.")
    rows = [row for row in library if game_catalog.matches(
        row, q, kind, "all" if state == "unloaded" else state, genre, setup)
        and (state != "unloaded" or not row["installed"])]
    return render_template("games.html", rows=rows, library=library, q=q, kind=kind,
                           state=state, genre=genre, setup=setup, genres=genres,
                           setup_types=setup_types, support_states=game_catalog.SUPPORT_STATES,
                           total=len(library))



@app.route("/games/<slug>/setup")
@login_required
def game_setup(slug):
    from . import game_catalog
    item = next((row for row in game_catalog.enrich(community.all_games()) if row["slug"] == slug), None)
    if item is None:
        abort(404)
    return render_template("game_setup.html", item=item, game_info=item["catalog"],
                           support_label=game_catalog.SUPPORT_STATES[item["support_state"]],
                           guide=db.query("SELECT * FROM game_guides WHERE slug=?", (slug,), one=True))


@app.route("/games/<slug>")
@login_required
def game(slug):
    from . import game_catalog
    schema = get_schema(slug)
    item = next((row for row in game_catalog.enrich(community.all_games()) if row["slug"] == slug), None)
    return render_template("game.html", schema=schema, templates=templates_for(schema), sessions=open_sessions(),
                           game_info=item["catalog"] if item else game_catalog.details(slug, schema["game"]),
                           guide=db.query("SELECT * FROM game_guides WHERE slug=?",(slug,),one=True),
                           preselect=request.args.get("session", type=int))


@app.route("/games/<slug>/yaml")
@login_required
def game_yaml(slug):
    schema = get_schema(slug)
    try:
        preset = db.loads(capture_template(schema,request.args.get("ref","default")))
        issue = ap_bridge.world_error(slug)
        if issue:
            raise ValueError(issue)
        text = yamlgen.player_yaml(yamlgen.clean_slot_name(g.user["slot_name"]),schema,
                   user_values(schema,preset["values"],g.user),f"{schema['game']} – {preset['label']}",
                   ap_bridge.index().get("ap_version","0.0.0"),preset["requires"])
    except ValueError as exc:
        abort(409,str(exc))
    slot = yamlgen.clean_slot_name(g.user["slot_name"])
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
    return jsonify([template_info(t) for t in templates_for(schema)])


@app.route("/api/games/<slug>/names")
@login_required
def api_names(slug):
    schema = get_schema(slug)
    return jsonify({"items": schema["items"], "locations": schema["locations"]})


@app.route("/api/worlds/status")
@login_required
def world_status():
    # Group members need progress only; extraction logs remain admin-only.
    return jsonify(status=ap_bridge.extract_status().get("status","never"))


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
    if not _found:
        abort(409,"Die Ausgangsvorlage fehlt oder ist nicht kompatibel. Es wurde keine Ersatzvorlage verwendet.")
    if request.method == "POST":
        values, errors = yamlgen.parse_form(schema, request.form, base_values,keep_defaults=True)
        name = request.form.get("name", "").strip()
        shared = request.form.get("shared") == "1"
        if not name:
            errors["_name"] = "Bitte einen Namen vergeben."
        if errors:
            flash("Bitte die markierten Felder korrigieren.", "error")
            return render_form(schema, values, errors=errors, name=name,
                               description=request.form.get("description", ""), shared=shared)
        requirements = db.loads(capture_template(schema,base_ref))["requires"]
        tid = db.execute("INSERT INTO templates (game, name, description, vals, created_by, shared,requirements) "
                         "VALUES (?, ?, ?, ?, ?, ?,?)",
                         (slug, name, request.form.get("description", ""), db.dumps(values), g.user["id"], int(shared),db.dumps(requirements)))
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
    if not can_edit_template(row) or row["immutable"]:
        return redirect(url_for("template_new", slug=row["game"], **{"from": f"t:{tid}"}))
    schema = get_schema(row["game"])
    current = db.loads(row["vals"])
    if request.method == "POST":
        values, errors = yamlgen.parse_form(schema, request.form, current, keep_defaults=True)
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


@app.route("/templates/<int:tid>/source")
@login_required
def template_source(tid):
    row = db.query("SELECT * FROM templates WHERE id=?",(tid,),one=True)
    if not row or not row["source_yaml"]:
        abort(404)
    if not row["shared"] and not can_edit_template(row):
        abort(403)
    return send_file(io.BytesIO(row["source_yaml"].encode("utf-8")),as_attachment=True,
                     download_name=f"template-{tid}.yaml",mimetype="text/yaml")


# --- Import ------------------------------------------------------------------------------------

@app.route("/import", methods=["GET", "POST"])
@login_required
def import_view():
    results, errors = [], []
    if request.method == "POST":
        texts = []
        for upload in request.files.getlist("files"):
            if not upload.filename:
                continue
            try:
                data = upload.stream.read(community.YAML_LIMIT+1)
                if len(data) > community.YAML_LIMIT:
                    raise ValueError("YAML-Datei ist größer als 512 KiB.")
                texts.append(data.decode("utf-8"))
            except (ValueError,UnicodeError) as exc:
                errors.append(f"{upload.filename}: {exc}")
        if request.form.get("text", "").strip():
            texts.append(request.form["text"])
        shared = request.form.get("shared") == "1"
        index = ap_bridge.index()["games"]
        for text in texts:
            if len(text.encode("utf-8")) > community.YAML_LIMIT:
                errors.append("YAML-Vorlage ist größer als 512 KiB.")
                continue
            found, errs = yamlgen.import_yaml(text, index, ap_bridge.schema)
            errors += errs
            for r in found:
                r["id"] = db.execute(
                    """INSERT INTO templates (game,name,description,vals,created_by,shared,source_yaml,source_sha256,requirements,immutable)
                       VALUES (?,?,?,?,?,?,?,?,?,1)""",
                    (r["slug"], r["name"][:80], "Unveränderter YAML-Import", db.dumps(r["values"]), g.user["id"], int(shared),
                     text,hashlib.sha256(text.encode("utf-8")).hexdigest(),db.dumps(r["requires"])))
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


# --- Sessions ----------------------------------------------------------------------------------

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
def session_view(sid, selection=None):
    from . import game_catalog
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
        from . import lobby_selection
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
    return render_template("session.html", s=row, entries=entries, games=games,
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


# --- Admin -------------------------------------------------------------------------------------

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
    from . import admin_deletion
    name = admin_deletion.delete_account(uid, g.user["id"])
    flash(f"Konto „{name}“ gelöscht und alle Anmeldungen widerrufen. Gemeinsame Inhalte wurden dir übertragen; betroffene Runden müssen ihre Einstellungen erneut bestätigen.", "info")
    return redirect(url_for("admin", _anchor="accounts"))


@app.route("/admin/sessions/<int:sid>/delete", methods=["POST"])
@admin_required
def admin_delete_round(sid):
    from . import admin_deletion
    name = admin_deletion.delete_round(sid)
    flash(f"Runde „{name}“ samt Seeds, Verbindungsdaten und lokalen Dateien gelöscht.", "info")
    return redirect(url_for("admin", _anchor="rounds"))


@app.route("/admin/seeds/<int:bid>/delete", methods=["POST"])
@admin_required
def admin_delete_seed(bid):
    from . import admin_deletion
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


def create_app() -> Flask:
    config.ensure_dirs()
    db.init()
    auth.migrate()
    mvp.migrate()
    community.migrate()
    live_store.migrate()
    if "mvp" not in app.blueprints:
        app.register_blueprint(mvp.bp)
    if "community" not in app.blueprints:
        app.register_blueprint(community.bp)
    if "auth" not in app.blueprints:
        app.register_blueprint(auth.bp)
    if "live" not in app.blueprints:
        app.register_blueprint(live_routes.bp)
    app.secret_key = config.secret_key()
    auth.configure(app)
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
    if ap_bridge.ap_ready() and not (config.SCHEMAS / "index.json").exists():
        ap_bridge.start_extract()
    return app
