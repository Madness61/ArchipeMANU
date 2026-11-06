"""Versioned APWorld storage. Archives are inspected, never imported here.

APWorld Python code is still executed by the legacy Archipelago runner when
extracting/generating. This library does NOT sandbox untrusted code.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
import re
import sqlite3
import tempfile
import threading
import zipfile

from . import config

MAX_UPLOAD = 20 * 1024 * 1024
MAX_UNCOMPRESSED = 150 * 1024 * 1024
MAX_FILES = 5000
_LOCK = threading.RLock()
_MODULE = re.compile(r"[a-z0-9_]+\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _versions() -> Path:
    return config.APWORLDS / "_versions"


def _db_path() -> Path:
    return config.DATA / "apworld_versions.sqlite3"


def inspect_bytes(data: bytes) -> dict:
    """Verify archive structure without extracting or executing code."""
    if not isinstance(data, bytes) or not data or len(data) > MAX_UPLOAD:
        raise ValueError("APWorld ist leer oder größer als 20 MiB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_FILES:
                raise ValueError("APWorld enthält zu viele Dateien.")
            if sum(x.file_size for x in members) > MAX_UNCOMPRESSED:
                raise ValueError("APWorld überschreitet das entpackte Größenlimit.")
            modules = set()
            for entry in members:
                name = entry.filename
                parts = PurePosixPath(name).parts
                if (not name or name.startswith("/") or "\\" in name or
                    not parts or any(p in (".", "..") for p in parts) or
                    re.match(r"^[A-Za-z]:", name) or "\x00" in name):
                    raise ValueError("Unsicherer Pfad im APWorld-Archiv.")
                if entry.file_size and (entry.compress_size == 0 or
                    entry.file_size / entry.compress_size > 1000):
                    raise ValueError("Verdächtig hohe Kompression im APWorld-Archiv.")
                if ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError("Symlinks in APWorlds sind nicht zugelassen.")
                if len(parts) == 2 and parts[1] == "__init__.py":
                    modules.add(parts[0])
            if len(modules) != 1:
                raise ValueError("APWorld benötigt genau einen Modulordner mit __init__.py.")
            module = modules.pop()
            if not _MODULE.fullmatch(module):
                raise ValueError("APWorld-Modulname darf nur a-z, 0-9 und _ enthalten.")
            meta = {}
            filename = f"{module}/archipelago.json"
            if filename in archive.namelist():
                info = archive.getinfo(filename)
                if info.file_size > 256 * 1024:
                    raise ValueError("APWorld-Manifest ist zu groß.")
                try:
                    meta = json.loads(archive.read(filename))
                except (UnicodeError, ValueError) as exc:
                    raise ValueError("Ungültiges archipelago.json.") from exc
                if not isinstance(meta, dict):
                    raise ValueError("archipelago.json muss ein JSON-Objekt sein.")
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("Ungültiges APWorld-ZIP-Archiv.") from exc
    return {
        "module": module,
        "game": str(meta.get("game") or "")[:180],
        "version": str(meta.get("world_version") or "")[:100],
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "file": f"{module}.apworld",
    }


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".upload-", delete=False) as fp:
        temp = Path(fp.name)
        try:
            fp.write(data)
            fp.flush()
            os.fsync(fp.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def _db():
    config.DATA.mkdir(parents=True, exist_ok=True)
    config.APWORLDS.mkdir(parents=True, exist_ok=True)
    _versions().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS apworld_versions (
            sha256 TEXT PRIMARY KEY, module TEXT NOT NULL, game TEXT NOT NULL,
            version TEXT NOT NULL, size INTEGER NOT NULL,
            added_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS apworld_by_module ON apworld_versions(module,active)")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(apworld_versions)")}
        if "source_url" not in columns:
            conn.execute("ALTER TABLE apworld_versions ADD COLUMN source_url TEXT NOT NULL DEFAULT ''")
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _register(conn, info: dict) -> None:
    conn.execute("""INSERT OR IGNORE INTO apworld_versions
        (sha256,module,game,version,size,added_at,active)
        VALUES (?,?,?,?,?,?,0)""", (
        info["sha256"], info["module"], info["game"], info["version"],
        info["size"], datetime.now(timezone.utc).isoformat(timespec="seconds"),
    ))


def _bootstrap(conn) -> None:
    """Migrate existing flat uploads and historical _old files without removing any."""
    files = list(config.APWORLDS.glob("*.apworld"))
    old_dir = config.APWORLDS / "_old"
    if old_dir.is_dir():
        files += list(old_dir.glob("*.apworld"))
    for file in files:
        try:
            data = file.read_bytes()
            info = inspect_bytes(data)
        except (OSError, ValueError):
            continue  # Keep invalid legacy files for manual investigation.
        target = _versions() / f"{info['sha256']}.apworld"
        if not target.is_file():
            _write_atomic(target, data)
        _register(conn, info)
        # Flat files are the active versions; legacy _old entries are archival.
        if file.parent == config.APWORLDS:
            conn.execute("UPDATE apworld_versions SET active=0 WHERE module=?", (info["module"],))
            conn.execute("UPDATE apworld_versions SET active=1 WHERE sha256=?", (info["sha256"],))


def store(data: bytes, source_url: str = "") -> dict:
    info = inspect_bytes(data)
    source_url = source_url.strip()
    if source_url:
        parsed = urlsplit(source_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or len(source_url) > 500:
            raise ValueError("Quellenlink muss eine gültige HTTPS-URL sein.")
    with _LOCK, _db() as conn:
        _bootstrap(conn)
        archive = _versions() / f"{info['sha256']}.apworld"
        if not archive.is_file():
            _write_atomic(archive, data)
        _write_atomic(config.APWORLDS / info["file"], data)
        _register(conn, info)
        if source_url:
            conn.execute("UPDATE apworld_versions SET source_url=? WHERE sha256=?", (source_url,info["sha256"]))
        conn.execute("UPDATE apworld_versions SET active=0 WHERE module=?", (info["module"],))
        conn.execute("UPDATE apworld_versions SET active=1 WHERE sha256=?", (info["sha256"],))
    return {**info, "active": True}


def list_versions() -> list[dict]:
    with _LOCK, _db() as conn:
        _bootstrap(conn)
        return [dict(r) for r in conn.execute("""SELECT * FROM apworld_versions
            ORDER BY module, active DESC, added_at DESC, sha256""")]


def activate(sha256: str) -> dict:
    if not _DIGEST.fullmatch(sha256):
        raise ValueError("Ungültige APWorld-Version-ID.")
    with _LOCK, _db() as conn:
        _bootstrap(conn)
        row = conn.execute("SELECT * FROM apworld_versions WHERE sha256=?", (sha256,)).fetchone()
        if not row:
            raise ValueError("APWorld-Version nicht gefunden.")
        archive = _versions() / f"{sha256}.apworld"
        if not archive.is_file():
            raise ValueError("APWorld-Datei fehlt im Versionsarchiv.")
        data = archive.read_bytes()
        info = inspect_bytes(data)
        if info["sha256"] != sha256 or info["module"] != row["module"]:
            raise ValueError("APWorld-Version stimmt nicht mit der gespeicherten Prüfsumme überein.")
        _write_atomic(config.APWORLDS / f"{row['module']}.apworld", data)
        conn.execute("UPDATE apworld_versions SET active=0 WHERE module=?", (row["module"],))
        conn.execute("UPDATE apworld_versions SET active=1 WHERE sha256=?", (sha256,))
        return {**dict(row), "active": True}


def deactivate(module: str) -> None:
    if not _MODULE.fullmatch(module):
        raise ValueError("Ungültiger Modulname.")
    with _LOCK, _db() as conn:
        _bootstrap(conn)
        (config.APWORLDS / f"{module}.apworld").unlink(missing_ok=True)
        conn.execute("UPDATE apworld_versions SET active=0 WHERE module=?", (module,))


def archived_file(sha256: str) -> Path:
    if not _DIGEST.fullmatch(sha256):
        raise ValueError("Ungültige APWorld-Version-ID.")
    with _LOCK, _db() as conn:
        _bootstrap(conn)
        row = conn.execute("SELECT 1 FROM apworld_versions WHERE sha256=?", (sha256,)).fetchone()
        if row is None:
            raise ValueError("APWorld-Version nicht gefunden.")
        path = _versions() / f"{sha256}.apworld"
        if not path.is_file():
            raise ValueError("APWorld-Datei fehlt im Versionsarchiv.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise ValueError("Die archivierte APWorld stimmt nicht mit ihrem Hash überein.")
        return path
