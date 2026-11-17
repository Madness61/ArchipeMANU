"""Templates HTTP handlers. Stable public endpoints."""
import hashlib
import io
from flask import abort, flash, g, redirect, render_template, request, send_file, url_for
from hub import ap_bridge, db, yamlgen, community
from hub.web import app
from hub.services.selection import get_schema, resolve_template, capture_template, can_edit_template
from hub.routes.security import login_required

ITEM_LOC_GROUP = "Item & Location Options"

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
