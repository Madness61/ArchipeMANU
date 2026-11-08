"""Admin deletion with relational cleanup and bounded artifact paths.

Callers enforce admin authentication and CSRF. No action contacts remote hosts.
"""
import shutil
import uuid
from contextlib import contextmanager

from flask import abort

from . import config, db, mvp


@contextmanager
def _change():
    # Serialize with begin_build; SQLite also serializes other server processes.
    with mvp._LOCK, db.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        yield conn


def _require_idle(conn, sid):
    room = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if room is None:
        abort(404)
    if room["gen_status"] == "running" or conn.execute(
            "SELECT 1 FROM seed_builds WHERE session_id=? AND status IN ('queued','running')", (sid,)).fetchone():
        abort(409, "Für diese Runde läuft eine Generierung. Bitte warte bis zum Abschluss.")
    return room


@contextmanager
def _artifacts(paths):
    """Stage files, restore on rollback, and purge only after the database commit."""
    root = config.SESSIONS.resolve()
    trash = root / (".delete-" + uuid.uuid4().hex)
    staged = []
    try:
        for path in paths:
            # IDs are integers supplied by the database. Still reject symlink escapes.
            if path.is_symlink() or not path.resolve().is_relative_to(root) or path.resolve() == root:
                abort(409, "Dateipfad liegt außerhalb des Rundenverzeichnisses. Löschen abgebrochen.")
            if path.exists():
                trash.mkdir(exist_ok=True)
                target = trash / str(len(staged))
                path.rename(target)
                staged.append((path, target))
        yield
    except BaseException:
        for original, staged_path in reversed(staged):
            staged_path.rename(original)
        if trash.exists():
            trash.rmdir()
        raise
    else:
        if trash.exists():
            shutil.rmtree(trash)


def delete_seed(bid):
    # The artifact context surrounds the commit so a failed transaction restores files.
    with mvp._LOCK:
        with db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            seed = conn.execute("SELECT * FROM seed_builds WHERE id=?", (bid,)).fetchone()
            if seed is None:
                abort(404)
            if seed["status"] in ("queued", "running"):
                abort(409, "Ein Seed wird gerade generiert und kann noch nicht gelöscht werden.")
            with _artifacts([config.SESSIONS / "_seeds" / str(bid)]):
                conn.execute("DELETE FROM hosted_rooms WHERE build_id=?", (bid,))
                conn.execute("DELETE FROM seed_builds WHERE id=?", (bid,))
                conn.commit()
    return seed["session_id"]


def delete_round(sid):
    with mvp._LOCK:
        with db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            room = _require_idle(conn, sid)
            builds = conn.execute("SELECT id FROM seed_builds WHERE session_id=?", (sid,)).fetchall()
            paths = [config.SESSIONS / str(sid),
                     *(config.SESSIONS / "_seeds" / str(row["id"]) for row in builds)]
            with _artifacts(paths):
                conn.execute("DELETE FROM hosted_rooms WHERE build_id IN (SELECT id FROM seed_builds WHERE session_id=?)", (sid,))
                conn.execute("DELETE FROM seed_builds WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
                conn.commit()
    return room["name"]


def delete_account(uid, admin_id):
    if uid == admin_id:
        abort(409, "Du kannst dein eigenes Admin-Konto nicht löschen.")
    with _change() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if user is None:
            abort(404)
        affected = conn.execute("""SELECT id FROM sessions WHERE created_by=?
            OR id IN (SELECT session_id FROM entries WHERE user_id=?)
            OR id IN (SELECT session_id FROM lobby_members WHERE user_id=?)""", (uid, uid, uid)).fetchall()
        for room in affected:
            _require_idle(conn, room["id"])
        # Preserve historical snapshot IDs: a new account must never inherit a deleted slot.
        high_water = max(uid, conn.execute("SELECT COALESCE(MAX(id),0) FROM users").fetchone()[0])
        old = conn.execute("SELECT value FROM auth_settings WHERE key='user_id_high_water'").fetchone()
        if old:
            high_water = max(high_water, int(old[0]))
        conn.execute("INSERT OR REPLACE INTO auth_settings(key,value) VALUES ('user_id_high_water',?)", (str(high_water),))
        # Shared content survives, but the deleted account no longer owns it.
        for table, column in (("sessions", "created_by"), ("templates", "created_by"),
                              ("community_games", "created_by"), ("game_guides", "author"),
                              ("hosted_rooms", "entered_by")):
            conn.execute(f"UPDATE {table} SET {column}=? WHERE {column}=?", (admin_id, uid))
        conn.execute("DELETE FROM lobby_invites WHERE created_by=?", (uid,))
        for room in affected:
            conn.execute("UPDATE entries SET ready=0,ready_hash='' WHERE session_id=?", (room["id"],))
        conn.execute("DELETE FROM entries WHERE user_id=?", (uid,))
        # auth_sessions, setup codes and memberships have ON DELETE CASCADE.
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
    return user["username"]
