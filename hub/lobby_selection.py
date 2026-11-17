"""Unsaved lobby selections: preview first, commit game and options together."""
import hashlib
import io

from flask import abort, current_app, flash, g, redirect, request, send_file, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import ap_bridge, db, yamlgen


def _signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="lobby-selection-v1")


def _hash(value):
    return hashlib.sha256(db.dumps(value).encode("utf-8")).hexdigest()


def _existing(sid):
    row = db.query("SELECT * FROM entries WHERE session_id=? AND user_id=? ORDER BY id LIMIT 1",
                   (sid, g.user["id"]), one=True)
    return dict(row) if row else None


def _selection_hash(entry):
    return _hash({key: entry[key] for key in ("id", "game", "template_ref", "template_snapshot",
                  "option_overrides", "selected_apworld_sha")} if entry else None)


def _profile_hash():
    user = db.query("SELECT slot_name,overrides FROM users WHERE id=?", (g.user["id"],), one=True)
    return _hash(dict(user))


def _slot(sid, existing):
    rows = [dict(row) for row in db.query("""SELECT e.id,u.slot_name FROM entries e
        JOIN users u ON u.id=e.user_id WHERE e.session_id=? ORDER BY e.id""", (sid,))]
    eid = existing["id"] if existing else max((row["id"] for row in rows), default=0) + 1
    if not existing:
        rows.append({"id": eid, "slot_name": g.user["slot_name"]})
    return yamlgen.assign_slot_names(rows)[eid]


def _active_sha(slug):
    return next((v["sha256"] for v in ap_bridge.list_apworld_versions()
                 if v["active"] and v["module"] == slug), "")


def _assert_current(state, schema):
    sid = state["sid"]
    room = db.query("SELECT locked FROM sessions WHERE id=?", (sid,), one=True)
    if not room or room["locked"]:
        abort(409, "Die Lobby wurde inzwischen gesperrt.")
    if not db.query("SELECT 1 FROM lobby_members WHERE session_id=? AND user_id=?",
                    (sid, g.user["id"]), one=True):
        abort(403, "Du bist kein Teilnehmer dieser Lobby mehr.")
    existing = _existing(sid)
    if (state["schema_hash"] != _hash(schema) or state["profile_hash"] != _profile_hash()
            or state["selection_hash"] != _selection_hash(existing)
            or state["sha"] != _active_sha(state["game"]) or state["slot"] != _slot(sid, existing)):
        abort(409, "Die Auswahl oder Spieleinstellungen haben sich inzwischen geändert. Bitte die Spielauswahl erneut öffnen.")


def editor(room):
    """GET creates a signed form draft; no entries or readiness flags are written."""
    slug = request.args.get("game", "")
    if not slug:
        return None
    state, schema = _draft_state(room, slug, request.args.get("ref"))
    return _render(state, schema)


def _draft_state(room, slug, selected_ref=None, reuse=True):
    from .app import capture_template, group_default_ref, entry_preset

    schema = ap_bridge.schema(slug)
    if schema is None:
        abort(404, "Diese APWorld ist nicht verfügbar oder noch nicht eingelesen.")
    existing = _existing(room["id"])
    if selected_ref is not None:
        ref = selected_ref or group_default_ref(slug)
    else:
        ref = existing["template_ref"] if existing and existing["game"] == slug else group_default_ref(slug)
    same = reuse and existing and existing["game"] == slug and existing["template_ref"] == ref
    try:
        if same:
            label, values, found, requirements = entry_preset(schema, existing)
            if not found:
                raise ValueError("Die bisherige Vorlage ist nicht mehr verfügbar. Bitte eine andere Vorlage wählen.")
            snapshot = db.dumps({"game": slug, "ref": ref, "label": label, "values": values, "requires": requirements})
        else:
            snapshot = capture_template(schema, ref)
    except ValueError as exc:
        abort(400, str(exc))
    state = {"sid": room["id"], "uid": g.user["id"], "game": slug, "ref": ref,
             "snapshot": snapshot, "overrides": db.loads(existing["option_overrides"]) if same else {},
             "sha": (existing["selected_apworld_sha"] or _active_sha(slug)) if same else _active_sha(slug),
             "schema_hash": _hash(schema), "profile_hash": _profile_hash(),
             "selection_hash": _selection_hash(existing), "slot": _slot(room["id"], existing)}
    return state, schema


def _save(state, updated):
    """Same atomic validation for a signed draft and a direct template selection."""
    with ap_bridge.ap_lock:
        conn = db.get()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _assert_current(state, ap_bridge.schema(state["game"]))
            existing = _existing(state["sid"])
            args = (state["game"], state["ref"], state["sha"], state["snapshot"], db.dumps(updated))
            if existing:
                conn.execute("""UPDATE entries SET game=?,template_ref=?,selected_apworld_sha=?,
                    template_snapshot=?,option_overrides=?,ready=0,ready_hash='' WHERE id=?""", (*args, existing["id"]))
            else:
                conn.execute("""INSERT INTO entries(game,template_ref,selected_apworld_sha,
                    template_snapshot,option_overrides,session_id,user_id) VALUES (?,?,?,?,?,?,?)""",
                             (*args, state["sid"], g.user["id"]))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def start(room):
    """Choose between editing a draft and saving its base values without an editor."""
    from .app import session_view

    action = request.form.get("_action", "edit")
    if action not in ("edit", "base"):
        abort(400)
    slug = request.form.get("game", "")
    state, schema = _draft_state(room, slug, request.form.get("ref", ""), reuse=action == "edit")
    _assert_current(state, schema)
    if action == "edit":
        return redirect(url_for("session_view", sid=room["id"], game=slug, ref=state["ref"], _anchor="game-selection"))
    result = _render(state, schema)
    if result["errors"]:
        return session_view(room["id"], selection=result), 400
    _save(state, {})
    flash("Die Werte aus deiner Auswahl sind gespeichert, ohne die YAML zu öffnen. Melde dich jetzt bei deiner Teilnahme bereit.", "info")
    return redirect(url_for("session_view", sid=room["id"], _anchor="own-readiness"))


def _render(state, schema, errors=None):
    from .app import user_values, entry_yaml, templates_for

    snapshot = db.loads(state["snapshot"])
    values = user_values(schema, snapshot["values"], g.user, state["overrides"])
    issues = yamlgen.validate_values(schema, values)
    issues.update(yamlgen.validate_requirements(schema, snapshot.get("requires", {}),
                                               ap_bridge.index().get("ap_version", "0.0.0")))
    world_error = ap_bridge.world_error(state["game"], state["sha"])
    if world_error:
        issues["_world"] = world_error
    issues.update(errors or {})
    groups = {}
    for option in schema["options"]:
        groups.setdefault(option.get("group", "Optionen"), []).append(option)
    selected = {"slot": state["slot"], "values": values, "template_label": snapshot["label"],
                "requirements": snapshot.get("requires", {})}
    preview = entry_yaml(selected, schema, ap_bridge.index().get("ap_version", "0.0.0")) if not issues else ""
    return {"schema": schema, "values": values, "errors": issues, "groups": groups,
            "baseline": user_values(schema, snapshot["values"], g.user),
            "draft": _signer().dumps(state), "yaml_preview": preview, "ref": state["ref"],
            "templates": templates_for(schema)}


def submit(sid):
    """A signed draft belongs to one player/lobby; only Apply changes the database."""
    from .app import user_values, session_view

    try:
        state = _signer().loads(request.form.get("_draft", ""), max_age=8 * 60 * 60)
    except BadSignature:
        abort(409, "Die Spielauswahl ist abgelaufen oder ungültig. Bitte erneut öffnen.")
    if state["sid"] != sid or state["uid"] != g.user["id"]:
        abort(403)
    schema = ap_bridge.schema(state["game"])
    _assert_current(state, schema)
    action = "preview" if request.form.get("_reset_option") else request.form.get("_action", "apply")
    if action not in ("apply", "preview", "reset", "download"):
        abort(400)
    snapshot = db.loads(state["snapshot"])
    baseline = user_values(schema, snapshot["values"], g.user)
    if action == "reset":
        updated, errors = {}, {}
    else:
        updated, errors = yamlgen.parse_lobby_form(schema, request.form, state["overrides"], baseline)
    state["overrides"] = updated
    result = _render(state, schema, errors)
    if not result["errors"] and action == "apply":
        _save(state, updated)
        flash("Dein Spiel und deine Einstellungen sind gespeichert. Klicke jetzt bei deiner Teilnahme auf „Bereit“.", "info")
        return redirect(url_for("session_view", sid=sid))
    if not result["errors"] and action == "download":
        return send_file(io.BytesIO(result["yaml_preview"].encode("utf-8")), as_attachment=True,
                         download_name=state["slot"] + ".yaml", mimetype="application/yaml")
    return session_view(sid, selection=result), 400 if result["errors"] else 200
