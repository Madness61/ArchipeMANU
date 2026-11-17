"""Application assembly. Routes, services and integrations have separate owners."""
from flask import Flask
from hub.web import app
from hub import config, db, auth, mvp, community, live_store, live_routes, ap_console, console_routes, logic_routes, ap_bridge
from hub.routes import rounds, security, overview, library, templates, accounts, lobbies, admin
from hub.services.selection import (get_schema, group_default_ref, resolve_template, uploaded_preset, capture_template, entry_preset, can_edit_template, template_info, templates_for, open_sessions, user_values, session_entries, session_yamls, entry_yaml, get_session, can_manage_session)
from hub.routes.lobbies import session_view

def create_app() -> Flask:
    from hub import recording
    from hub import progression, progression_routes
    config.ensure_dirs()
    db.init()
    auth.migrate()
    mvp.migrate()
    community.migrate()
    live_store.migrate()
    ap_console.migrate()
    recording.migrate()
    progression.migrate()
    if "mvp" not in app.blueprints:
        app.register_blueprint(mvp.bp)
    if "community" not in app.blueprints:
        app.register_blueprint(community.bp)
    if "auth" not in app.blueprints:
        app.register_blueprint(auth.bp)
    if "live" not in app.blueprints:
        app.register_blueprint(live_routes.bp)
    if "console" not in app.blueprints:
        app.register_blueprint(console_routes.bp)
    if "logic" not in app.blueprints:
        app.register_blueprint(logic_routes.bp)
    if "progression" not in app.blueprints:
        app.register_blueprint(progression_routes.bp)
    app.jinja_env.globals['progression_enabled'] = True
    app.secret_key = config.secret_key()
    auth.configure(app)
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
    if ap_bridge.ap_ready() and not (config.SCHEMAS / "index.json").exists():
        ap_bridge.start_extract()
    return app
