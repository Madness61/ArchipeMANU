"""Shared game library for all logged-in group members.

Uploads from authenticated group members are activated automatically. Archive
validation never imports code; option extraction runs in the background.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import re
from urllib.parse import urlsplit

import yaml
from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from . import ap_bridge, apworld_library, config, db

bp = Blueprint("community", __name__)
YAML_LIMIT = 512 * 1024


def migrate():
    with db.transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS community_games(
            sha256 TEXT PRIMARY KEY,
            module TEXT NOT NULL,
            display_name TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL REFERENCES users(id),
            yaml_file TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS community_game_modules ON community_games(module);
        """)


def all_games(search=""):
    """Installed game list plus community uploads not yet loaded into AP."""
    installed = ap_bridge.index().get("games", {})
    uploads = db.query("""SELECT cg.*, u.username FROM community_games cg
        JOIN users u ON u.id=cg.created_by ORDER BY cg.created_at DESC""")
    library = {}
    for slug, item in installed.items():
        library[slug] = {
            "slug": slug, "name": item.get("game", slug), "version": item.get("version", ""),
            "installed": True, "custom": item.get("custom", False),
            "added_by": "", "pending": False, "versions": [],
        }
    for row in uploads:
        key = row["module"]
        if key not in library:
            library[key] = {"slug": key, "name": row["display_name"],
                            "version": row["version"], "installed": False,
                            "custom": True, "added_by": row["username"],
                            "pending": True, "versions": []}
        library[key]["versions"].append(dict(row))
        if not library[key]["added_by"]:
            library[key]["added_by"] = row["username"]
    # Include legacy Admin uploads and older versions in the same shared library.
    tracked = {v["sha256"] for info in library.values() for v in info["versions"]}
    active_modules = set()
    active_hashes = set()
    for version in ap_bridge.list_apworld_versions():
        module = version["module"]
        if version["active"]:
            active_modules.add(module)
            active_hashes.add(version["sha256"])
        if module not in library:
            library[module] = {"slug": module, "name": version["game"] or module,
                               "version": version["version"], "installed": False,
                               "custom": True, "added_by": "Legacy-Upload",
                               "pending": not version["active"], "versions": []}
        if version["sha256"] not in tracked:
            library[module]["versions"].append({
                "sha256": version["sha256"], "version": version["version"],
                "username": "Legacy/Admin", "approved": bool(version["active"]),
                "yaml_file": "", "source_url": version.get("source_url", ""),
            })
    for module, item in library.items():
        item["active"] = module in active_modules
        for version in item["versions"]:
            version["active"] = version["sha256"] in active_hashes
    return sorted([v for v in library.values() if
                   search.casefold() in (v["name"] + " " + v["slug"] + " " + v["added_by"]).casefold()],
                  key=lambda v: v["name"].casefold())


def valid_yaml(data: bytes, game_name: str):
    if not data:
        return ""
    if len(data) > YAML_LIMIT:
        raise ValueError("YAML-Vorlage ist größer als 512 KiB.")
    try:
        text = data.decode("utf-8-sig")
        parsed = yaml.safe_load(text)
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("Die YAML-Vorlage ist ungültig oder nicht UTF-8.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Die YAML-Vorlage muss ein YAML-Objekt enthalten.")
    if "name" not in parsed or "game" not in parsed:
        raise ValueError("Die YAML-Vorlage benötigt name und game.")
    if parsed["game"] != game_name:
        raise ValueError("Der game-Eintrag muss zum hinterlegten APWorld-Spielnamen passen.")
    return text


@bp.route("/games/community/add", methods=["GET", "POST"])
def game_add():
    if g.user is None:
        return redirect(url_for("login", next=request.path))
    if request.method == "GET":
        return render_template("community_add.html")
    archive = request.files.get("apworld")
    if not archive or not archive.filename.lower().endswith(".apworld"):
        flash("Bitte eine .apworld-Datei auswählen.", "error")
        return render_template("community_add.html"), 400
    source = request.form.get("source_url", "").strip()
    label = request.form.get("name", "").strip()
    try:
        data = archive.stream.read(apworld_library.MAX_UPLOAD + 1)
        info = apworld_library.inspect_bytes(data)
        if not label:
            label = info["game"] or info["module"]
        if len(label) > 100:
            raise ValueError("Spielname ist zu lang.")
        if source:
            u = urlsplit(source)
            if u.scheme != "https" or not u.hostname or u.username or u.password or len(source) > 500:
                raise ValueError("Die Quelle muss eine gültige HTTPS-URL sein.")
        yaml_upload = request.files.get("yaml")
        yaml_data = b""
        if yaml_upload and yaml_upload.filename:
            if not yaml_upload.filename.lower().endswith((".yaml", ".yml")):
                raise ValueError("YAML-Datei muss auf .yaml oder .yml enden.")
            yaml_data = yaml_upload.stream.read(YAML_LIMIT + 1)
            valid_yaml(yaml_data, info["game"] or label)
        # Save only after all inputs pass validation.
        with ap_bridge.ap_lock:
            if db.query("SELECT 1 FROM community_games WHERE sha256=?", (info["sha256"],), one=True):
                raise ValueError("Diese APWorld-Version ist bereits in der Bibliothek vorhanden.")
            apworld_library.store(data, source_url=source, activate=True)
            yaml_relative = ""
            if yaml_data:
                folder = config.DATA / "community" / info["sha256"]
                folder.mkdir(parents=True, exist_ok=True)
                with (folder / "options.yaml").open("xb") as original:
                    original.write(yaml_data)
                yaml_relative = info["sha256"]
            db.execute("""INSERT INTO community_games
                     (sha256,module,display_name,version,created_by,yaml_file,source_url,approved)
                     VALUES (?,?,?,?,?,?,?,1)""",
                       (info["sha256"], info["module"], label, info["version"],
                        g.user["id"], yaml_relative, source))
    except (ValueError, OSError) as exc:
        flash(str(exc), "error")
        return render_template("community_add.html"), 400
    ap_bridge.start_extract()
    flash(f"{label} aktiviert. Die Spieloptionen werden automatisch eingelesen.", "info")
    return redirect(url_for("games"))


@bp.route("/games/community/<sha256>/yaml")
def download_yaml(sha256):
    if g.user is None:
        abort(401)
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        abort(404)
    row = db.query("SELECT yaml_file FROM community_games WHERE sha256=?", (sha256,), one=True)
    if not row or row["yaml_file"] != sha256:
        abort(404)
    path = config.DATA / "community" / sha256 / "options.yaml"
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name="options.yaml",
                     mimetype="text/yaml")


@bp.route("/games/community/<sha256>/apworld")
def download_apworld(sha256):
    if g.user is None:
        abort(401)
    try:
        path = ap_bridge.archived_apworld(sha256)
    except ValueError:
        abort(404)
    module = apworld_library.inspect_bytes(path.read_bytes())["module"]
    return send_file(path, as_attachment=True, download_name=module + ".apworld",
                     mimetype="application/octet-stream")


@bp.route("/games/community/<sha256>/approve", methods=["POST"])
def approve(sha256):
    # Keep the old URL compatible; activation no longer requires admin approval.
    if not g.user:
        abort(401)
    row = db.query("SELECT * FROM community_games WHERE sha256=?", (sha256,), one=True)
    if row is None:
        abort(404)
    if not ap_bridge.trusted_custom_execution():
        flash("Aktivierung benötigt HUB_TRUSTED_APWORLDS=1. Eine Python-Sandbox ist nicht vorhanden.", "error")
        return redirect(url_for("games"))
    try:
        with ap_bridge.ap_lock:
            ap_bridge.activate_apworld(sha256)
        db.execute("UPDATE community_games SET approved=1 WHERE sha256=?", (sha256,))
        ap_bridge.start_extract()
        flash(f"{row['display_name']} aktiviert. Spieloptionen werden eingelesen.", "info")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("games"))
