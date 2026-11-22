"""Security HTTP handlers. Stable public endpoints."""
import functools
import hmac
import secrets
from flask import abort, g, jsonify, render_template, request, session
from hub import db, auth
from hub import i18n
from werkzeug.exceptions import HTTPException
from hub.web import app

ITEM_LOC_GROUP = "Item & Location Options"

@app.errorhandler(HTTPException)
def friendly_error(error):
    if not hasattr(g,'user'):
        g.user=None
    if request.path.startswith('/api/') or request.accept_mimetypes.best=='application/json':
        return jsonify(error=i18n.http_error(error)),error.code
    return render_template('error.html',error=error),error.code


@app.context_processor
def interface_context():
    prefs = i18n.preferences()
    return dict(ui_prefs=prefs, ui_messages=i18n.MESSAGES if prefs['language']=='en' else {},ui_patterns=i18n.PATTERNS if prefs['language']=='en' else [])


@app.after_request
def localized_errors(response):
    if response.is_json and i18n.language() == 'en':
        payload = response.get_json(silent=True)
        if isinstance(payload, dict):
            for key in ('error', 'errors', 'message'):
                if key in payload:
                    payload[key] = i18n.error_messages(payload[key])
            response.set_data(app.json.dumps(payload))
    return response


@app.route('/preferences', methods=['POST'])
def save_preferences():
    language, theme = request.form.get('language'), request.form.get('theme')
    if language not in ('de','en') or theme not in ('dark','light','system'):
        return jsonify(error=i18n.t('Ungültige Sprache oder Darstellung.')), 400
    if g.user:
        # Interface preferences never alter YAML values or invalidate readiness.
        with db.transaction() as conn:
            user=conn.execute('SELECT overrides FROM users WHERE id=?',(g.user['id'],)).fetchone()
            if not user:
                abort(401)
            values=db.loads(user['overrides'])
            values['_interface']=dict(language=language,theme=theme)
            conn.execute('UPDATE users SET overrides=? WHERE id=?',(db.dumps(values),g.user['id']))
    else:
        # Only an explicit choice on the login page overrides account settings.
        session['interface_preferences'] = dict(language=language, theme=theme)
    response=jsonify(language=language,theme=theme)
    for key,value in (('ui_language',language),('ui_theme',theme)):
        response.set_cookie(key,value,max_age=31536000,samesite='Lax',secure=app.config.get('SESSION_COOKIE_SECURE',False))
    response.headers['Cache-Control']='no-store'
    return response


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
            return auth.login_required_response()
        return view(*args, **kwargs)
    return wrapped


@app.errorhandler(401)
def missing_authentication(error):
    if getattr(g, "user", None) is None:
        return auth.login_required_response()
    return error


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
