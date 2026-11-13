"""Individual credentials, revocable sessions and additive legacy-account setup.

CLI commands operate locally; they never load Archipelago or migrate seed jobs.
"""
import argparse
import hashlib
import re
import secrets
import sqlite3
import time
from datetime import timedelta

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import config, db, yamlgen

bp = Blueprint("auth", __name__)
SESSION_SECONDS = 8 * 60 * 60
SETUP_SECONDS = 24 * 60 * 60
RATE_WINDOW = 15 * 60
LOGIN_IP_LIMIT = 30
LOGIN_ACCOUNT_LIMIT = 10
# Unknown and legacy accounts perform the same password work as valid accounts.
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32), method="scrypt")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def migrate():
    with db.transaction() as conn:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "password_hash" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS auth_sessions(
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS account_setup(
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_attempts(
            key TEXT PRIMARY KEY, started REAL NOT NULL, attempts INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)


def next_user_id(conn):
    """Do not reuse deleted account IDs still present in seed snapshots."""
    current = conn.execute("SELECT COALESCE(MAX(id),0) FROM users").fetchone()[0]
    reserved = conn.execute("SELECT value FROM auth_settings WHERE key='user_id_high_water'").fetchone()
    return max(current, int(reserved[0]) if reserved else 0) + 1


def configure(app):
    app.config.update(SESSION_COOKIE_NAME="archipemanu_session", SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=config.COOKIE_SECURE,
                      PERMANENT_SESSION_LIFETIME=timedelta(seconds=SESSION_SECONDS),
                      SESSION_REFRESH_EACH_REQUEST=False)


def load_user():
    g.user = None
    token = session.get("auth_token")
    uid = session.get("uid")
    if not token or not isinstance(token, str) or not isinstance(uid, int):
        if uid is not None or token is not None:
            session.clear()
        return
    user = db.query("""SELECT u.* FROM users u JOIN auth_sessions s ON s.user_id=u.id
        WHERE s.token_hash=? AND s.user_id=? AND s.expires_at>? AND u.password_hash!=''""",
        (digest(token), uid, time.time()), one=True)
    if user:
        g.user = user
    else:
        session.clear()


def consume_attempt(scope, value, limit):
    """Atomic fixed window in SQLite, shared across server threads/processes."""
    now = time.time()
    key = digest(scope + "\0" + value)
    with db.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM auth_attempts WHERE started<=?", (now - RATE_WINDOW,))
        row = conn.execute("SELECT * FROM auth_attempts WHERE key=?", (key,)).fetchone()
        if row and row["attempts"] >= limit:
            response = render_template("auth_limited.html")
            return response, 429, {"Retry-After": str(max(1, int(row["started"] + RATE_WINDOW - now) + 1))}
        conn.execute("""INSERT INTO auth_attempts(key,started,attempts) VALUES (?,?,1)
            ON CONFLICT(key) DO UPDATE SET attempts=attempts+1""", (key, now))
    return None


def password_error(password, confirmation=None):
    if not password:
        return "Bitte gib ein Passwort ein."
    if len(password) > 1024:
        return "Das Passwort darf höchstens 1024 Zeichen lang sein."
    if confirmation is not None and password != confirmation:
        return "Die Passwörter stimmen nicht überein."
    return ""


def begin_session(user_id):
    old = session.get("auth_token")
    token = secrets.token_urlsafe(32)
    now = time.time()
    with db.transaction() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (now,))
        if isinstance(old, str):
            conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest(old),))
        conn.execute("INSERT INTO auth_sessions VALUES (?,?,?)", (digest(token), user_id, now + SESSION_SECONDS))
    session.clear()
    session.update(uid=user_id, auth_token=token, _csrf=secrets.token_urlsafe(32))
    session.permanent = True


def safe_next(target):
    # Backslashes and controls can turn apparently relative URLs into redirects to another host.
    return (target if target.startswith("/") and not target.startswith("//")
            and "\\" not in target and not any(ord(c) < 32 for c in target) else url_for("index"))


def login_required_response():
    """Cookie authentication needs a login page, not a Basic-Auth error document."""
    endpoint = request.endpoint or ""
    is_api = (request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"
              or request.blueprint in ("console", "logic") and endpoint not in ("console.page", "logic.page")
              or endpoint in ("live.data", "live.refresh", "mvp.build_status", "session_status"))
    args = request.view_args or {}
    if not is_api and request.method == "GET":
        target = safe_next(request.full_path.rstrip("?"))
    elif args.get("sid") is not None:
        target = url_for("session_view", sid=args["sid"], build=args.get("build_id"), _anchor="play")
    elif args.get("slug"):
        target = url_for("game", slug=args["slug"])
    else:
        target = url_for("index")
    login_url = url_for("login", next=target)
    if is_api:
        return jsonify(error="Deine Anmeldung fehlt oder ist nicht mehr gültig. Bitte melde dich erneut an.",
                       authentication_required=True, login_url=login_url), 401, {"Cache-Control": "no-store"}
    flash("Bitte melde dich an, um die gewünschte Seite zu öffnen.", "info")
    response = redirect(login_url)
    response.headers["Cache-Control"] = "no-store"
    return response


def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        limited = consume_attempt("login-ip", request.remote_addr or "unknown", LOGIN_IP_LIMIT)
        if limited:
            return limited
        limited = consume_attempt("login-account", username.lower()[:32], LOGIN_ACCOUNT_LIMIT)
        if limited:
            return limited
        user = db.query("SELECT * FROM users WHERE username=?", (username,), one=True) if len(username) <= 32 else None
        valid = check_password_hash(user["password_hash"] if user and user["password_hash"] else DUMMY_HASH,
                                    password) if len(password) <= 1024 else False
        if user and user["password_hash"] and valid:
            begin_session(user["id"])
            return redirect(safe_next(request.args.get("next", "")))
        flash("Benutzername oder Passwort ist falsch. Bestehende Konten benötigen gegebenenfalls zuerst einen Einrichtungscode vom Host.", "error")
        return render_template("login.html"), 401
    return render_template("login.html")


def logout():
    token = session.get("auth_token")
    if isinstance(token, str):
        db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest(token),))
    session.clear()
    return redirect(url_for("login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        limited = consume_attempt("register-ip", request.remote_addr or "unknown", 10)
        if limited:
            return limited
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        error = password_error(password)
        if not re.fullmatch(r"[\w.-]{3,32}", username):
            error = "Benutzername: 3 bis 32 Buchstaben, Ziffern oder die Zeichen _, . und -."
        if not error:
            password_hash = generate_password_hash(password, method="scrypt")
            try:
                # Serialize the empty-install check: exactly one first account becomes admin.
                with db.transaction() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    first_account = not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
                    uid = conn.execute("""INSERT INTO users(id,username,slot_name,password_hash,is_admin)
                        VALUES (?,?,?,?,?)""", (next_user_id(conn), username, yamlgen.clean_slot_name(username),
                                             password_hash, int(first_account))).lastrowid
            except sqlite3.IntegrityError:
                error = "Dieser Benutzername ist bereits vergeben. Bestehende Konten bitte über einen Einrichtungscode einrichten."
            else:
                begin_session(uid)
                return redirect(url_for("index"))
        flash(error, "error")
        return render_template("register.html"), 400
    return render_template("register.html")


def issue_setup(user_id, reset=False):
    token = secrets.token_urlsafe(32)
    with db.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user or (user["password_hash"] and not reset):
            raise ValueError("Konto existiert nicht oder besitzt bereits ein Passwort.")
        conn.execute("DELETE FROM account_setup WHERE user_id=?", (user_id,))
        conn.execute("INSERT INTO account_setup VALUES (?,?,?)", (digest(token), user_id, time.time() + SETUP_SECONDS))
    return token


@bp.route("/account/setup", methods=["GET", "POST"])
def setup_password():
    if request.method == "POST":
        limited = consume_attempt("setup-ip", request.remote_addr or "unknown", 10)
        if limited:
            return limited
        token = request.form.get("code", "")
        password = request.form.get("password", "")
        error = password_error(password, request.form.get("password_confirm", ""))
        if not error:
            # Hash before opening the write transaction; consume the code atomically with the update.
            password_hash = generate_password_hash(password, method="scrypt")
            with db.transaction() as conn:
                conn.execute("BEGIN IMMEDIATE")
                setup = conn.execute("SELECT * FROM account_setup WHERE token_hash=? AND expires_at>?",
                                     (digest(token), time.time())).fetchone()
                if setup:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, setup["user_id"]))
                    conn.execute("DELETE FROM account_setup WHERE user_id=?", (setup["user_id"],))
                    conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (setup["user_id"],))
                else:
                    error = "Einrichtungscode ungültig oder abgelaufen. Bitte beim Host einen neuen anfordern."
            if not error:
                session.clear()
                flash("Passwort gespeichert. Melde dich jetzt mit deinem Benutzernamen und Passwort an.", "info")
                return redirect(url_for("login"))
        flash(error, "error")
        return render_template("account_setup.html"), 400
    return render_template("account_setup.html")


def main():
    parser = argparse.ArgumentParser(description="Lokale Kontoeinrichtung; keine Passwörter als Kommandozeilenargumente.")
    sub = parser.add_subparsers(dest="command", required=True)
    bootstrap = sub.add_parser("bootstrap-admin", help="Ersten Admin nur bei vollständig leerer Benutzerliste anlegen")
    bootstrap.add_argument("username")
    setup = sub.add_parser("setup-account", help="Einmalcode für ein bestehendes Konto ohne Passwort")
    setup.add_argument("username")
    reset = sub.add_parser("reset-account", help="Einmalcode zur lokalen Passwortwiederherstellung")
    reset.add_argument("username")
    args = parser.parse_args()
    config.ensure_dirs()
    db.init()
    migrate()
    # DB helpers only need an application context, not the full app startup and AP worker.
    from flask import Flask
    local = Flask(__name__)
    local.teardown_appcontext(db.close)
    with local.app_context():
        try:
            if args.command == "bootstrap-admin":
                if not re.fullmatch(r"[\w.-]{3,32}", args.username):
                    raise ValueError("Ungültiger Benutzername (3 bis 32 Buchstaben/Ziffern/_.-).")
                with db.transaction() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                        raise ValueError("Benutzer existieren bereits. Vorhandenen Admin mit setup-account einrichten.")
                    uid = conn.execute("INSERT INTO users(id,username,slot_name,is_admin) VALUES (?,?,?,1)",
                                       (next_user_id(conn), args.username, yamlgen.clean_slot_name(args.username))).lastrowid
            else:
                user = db.query("SELECT id FROM users WHERE username=?", (args.username,), one=True)
                if not user:
                    raise ValueError("Benutzer nicht gefunden.")
                uid = user["id"]
            code = issue_setup(uid, reset=args.command == "reset-account")
            print("Konto:", args.username)
            print("Einmaliger Einrichtungscode (24 Stunden gültig):", code)
            print("Im Browser /account/setup öffnen und dort Code sowie neues Passwort eingeben.")
        except ValueError as exc:
            parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
