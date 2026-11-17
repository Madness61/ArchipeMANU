"""Library HTTP handlers. Stable public endpoints."""
import io
from flask import abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from hub import ap_bridge, db, yamlgen, community, auth
from hub import game_catalog
from hub.web import app
from hub.services.selection import get_schema, capture_template, template_info, templates_for, open_sessions, user_values
from hub.routes.security import login_required, admin_required
from hub.services import guides

ITEM_LOC_GROUP = "Item & Location Options"

@app.route("/games")
@login_required
def games():
    from hub import game_catalog
    q = request.args.get("q", "").strip()
    library = game_catalog.enrich(community.all_games())
    kind = request.args.get("kind", "all")
    state = request.args.get("state", "all")
    # Preserve old bookmarks without continuing to call installed options 'ready'.
    state = {"ready": "loaded", "pending": "unloaded"}.get(state, state)
    genre = request.args.get("genre", "all")
    tag = request.args.get("tag", "all")
    setup = request.args.get("setup", "all")
    genres = sorted({g for row in library for g in row["catalog"]["genres"]})
    tags = sorted({tag for row in library for tag in row["catalog"]["tags"]}, key=str.casefold)
    setup_types = {key: label for key, label in game_catalog.SETUP_TYPES.items()
                   if any(row["catalog"]["setup_type"] == key for row in library)}
    if (kind not in ("all", "builtin", "custom")
            or state not in ("all", "unloaded", *game_catalog.SUPPORT_STATES)
            or genre not in ("all", *genres) or tag not in ("all", *tags) or setup not in ("all", *setup_types)):
        abort(400, "Unbekannter Spielefilter.")
    rows = [row for row in library if game_catalog.matches(
        row, q, kind, "all" if state == "unloaded" else state, genre, setup, tag)
        and (state != "unloaded" or not row["installed"])]
    return render_template("games.html", rows=rows, library=library, q=q, kind=kind,
                           state=state, genre=genre, tag=tag, tags=tags, setup=setup, genres=genres,
                           setup_types=setup_types, support_states=game_catalog.SUPPORT_STATES,
                           total=len(library))


@app.route("/games/<slug>/setup")
@login_required
def game_setup(slug):
    from hub import game_catalog
    item = next((row for row in game_catalog.enrich(community.all_games()) if row["slug"] == slug), None)
    if item is None:
        abort(404)
    return render_template("game_setup.html", item=item, game_info=item["catalog"],
                           support_label=game_catalog.SUPPORT_STATES[item["support_state"]],
                           guide=guides.get(slug))


@app.route("/games/<slug>")
@login_required
def game(slug):
    from hub import game_catalog
    schema = get_schema(slug)
    item = next((row for row in game_catalog.enrich(community.all_games()) if row["slug"] == slug), None)
    return render_template("game.html", schema=schema, item=item, templates=templates_for(schema), sessions=open_sessions(),
                           game_info=item["catalog"] if item else game_catalog.details(slug, schema["game"]),
                           guide=guides.get(slug),
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


@app.route("/api/games/<slug>/checks", methods=["GET", "POST"])
@login_required
def game_check_preview(slug):
    from hub import check_preview
    get_schema(slug)
    if request.method == "POST":
        limited = auth.consume_attempt("standard-check-preview", str(g.user["id"]), 12)
        if limited:
            return limited
    response = jsonify(check_preview.status(slug, start=request.method == "POST"))
    response.headers["Cache-Control"] = "no-store"
    return response
