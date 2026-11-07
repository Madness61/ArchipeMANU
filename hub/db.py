import json
import sqlite3
from contextlib import contextmanager

from flask import g

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY,
    username   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    slot_name  TEXT NOT NULL,
    is_admin   INTEGER NOT NULL DEFAULT 0,
    overrides  TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Option values only store what differs from the APWorld default.
CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY,
    game        TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    vals        TEXT NOT NULL DEFAULT '{}',
    created_by  INTEGER REFERENCES users(id),
    shared      INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- template_ref: 'default' | 'preset:<name>' | 't:<template id>'
CREATE TABLE IF NOT EXISTS game_defaults (
    game         TEXT PRIMARY KEY,
    template_ref TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked     INTEGER NOT NULL DEFAULT 0,
    spoiler    INTEGER NOT NULL DEFAULT 1,
    race       INTEGER NOT NULL DEFAULT 0,
    gen_status TEXT NOT NULL DEFAULT '',
    gen_log    TEXT NOT NULL DEFAULT '',
    gen_file   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS entries (
    id           INTEGER PRIMARY KEY,
    session_id   INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    game         TEXT NOT NULL,
    template_ref TEXT NOT NULL DEFAULT 'default',
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect()
    return g.db


@contextmanager
def transaction():
    """Commit/roll back a standalone transaction and always close its connection."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def close(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init() -> None:
    with transaction() as conn:
        conn.executescript(SCHEMA)


def query(sql: str, args=(), one=False):
    rows = get().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql: str, args=()) -> int:
    conn = get()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def loads(text: str | None) -> dict:
    return json.loads(text) if text else {}


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
