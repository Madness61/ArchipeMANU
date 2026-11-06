"""Everything that touches the Archipelago install: APWorld files, option extraction, generation."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from . import config, apworld_library

RUNNER = config.ROOT / "ap_runner.py"


def trusted_custom_execution() -> bool:
    """Explicit local opt-in for trusted custom worlds; NOT a sandbox."""
    return os.environ.get("HUB_TRUSTED_APWORLDS", "0") == "1"


# Extraction and generation both rewrite AP's custom_worlds folder, so they never run in parallel.
ap_lock = threading.Lock()


# --- APWorld files -----------------------------------------------------------------------------

def apworld_info(path: Path) -> dict:
    """Read module name and manifest from an .apworld without importing it."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            modules = {n.split("/")[0] for n in names if n.count("/") == 1 and n.endswith(("__init__.py", "__init__.pyc"))}
            manifest = {}
            for n in names:
                if n.endswith("archipelago.json"):
                    manifest = json.loads(zf.read(n).decode("utf-8"))
                    break
    except zipfile.BadZipFile:
        raise ValueError("Die Datei ist kein gültiges Zip/.apworld.")
    if len(modules) != 1:
        raise ValueError("Die .apworld muss genau einen Welt-Ordner mit __init__.py enthalten.")
    return {
        "module": modules.pop(),
        "game": manifest.get("game", ""),
        "version": manifest.get("world_version", ""),
        "file": path.name,
        "size": path.stat().st_size,
        "mtime": path.stat().st_mtime,
    }


def store_apworld(data: bytes, source_url: str = "") -> dict:
    """Persist new versions without discarding previous APWorld releases."""
    info = apworld_library.store(data, source_url=source_url)
    return {**info, "mtime": (config.APWORLDS / info["file"]).stat().st_mtime}


def list_apworlds() -> list[dict]:
    """Legacy active-file view used by older UI routes."""
    return [dict(module=v["module"], game=v["game"], version=v["version"],
                 file=v["module"] + ".apworld", sha256=v["sha256"],
                 size=v["size"], active=True)
            for v in apworld_library.list_versions() if v["active"]]


def list_apworld_versions() -> list[dict]:
    return apworld_library.list_versions()


def activate_apworld(sha256: str) -> dict:
    return apworld_library.activate(sha256)


def deactivate_apworld(module: str) -> None:
    apworld_library.deactivate(module)


def archived_apworld(sha256: str) -> Path:
    return apworld_library.archived_file(sha256)


def delete_apworld(module: str) -> None:
    # Retain the historical versions even when an APWorld is deactivated.
    deactivate_apworld(module)


def _sync_custom_worlds() -> None:
    """Mirror trusted data/apworlds into AP's custom_worlds folder."""
    if any(config.APWORLDS.glob("*.apworld")) and not trusted_custom_execution():
        raise ValueError("Custom APWorld-Code ist nicht isoliert. Nur geprüfte Quellen und HUB_TRUSTED_APWORLDS=1 erlauben.")
    target = config.AP_SOURCE / "custom_worlds"
    target.mkdir(exist_ok=True)
    wanted = {p.name: p for p in config.APWORLDS.glob("*.apworld")}
    if any(target.glob("*.apworld")) and not trusted_custom_execution():
        raise ValueError("Bereits installierte Custom APWorlds erfordern eine ausdrückliche Vertrauensfreigabe.")
    # Never delete manually installed worlds from the user's Archipelago installation.
    for name, src in wanted.items():
        dst = target / name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size or dst.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dst)


def _hidden_builtins() -> list[str]:
    """Uploaded APWorlds replace built-in worlds of the same module name."""
    builtin = config.AP_SOURCE / "worlds"
    return [p.stem for p in config.APWORLDS.glob("*.apworld") if (builtin / p.stem).is_dir()]


def ap_ready() -> bool:
    return config.AP_PYTHON.exists() and (config.AP_SOURCE / "Generate.py").exists()


def _run(args: list[str], timeout: int) -> tuple[bool, str]:
    # Pass a minimal environment; HUB_PASSWORD and other host secrets must not be exposed.
    safe_keys = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
                 "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG",
                 "LC_ALL", "LD_LIBRARY_PATH", "VIRTUAL_ENV")
    env = {name: os.environ[name] for name in safe_keys if name in os.environ}
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    hide = ",".join(_hidden_builtins())
    cmd = [str(config.AP_PYTHON), str(RUNNER), *args] + (["--hide", hide] if hide else [])
    try:
        proc = subprocess.run(cmd, cwd=config.AP_SOURCE, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        return False, f"Abgebrochen nach {timeout}s.\n{e.stdout or ''}"
    except OSError as e:
        return False, f"Archipelago konnte nicht gestartet werden: {e}"
    return proc.returncode == 0, (proc.stdout + "\n" + proc.stderr).strip()


# --- Option extraction -------------------------------------------------------------------------

STATUS_FILE = config.DATA / "extract_status.json"


def extract_status() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "never"}


def _write_status(**status) -> None:
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")


def extract() -> bool:
    with ap_lock:
        _write_status(status="running", started=time.time())
        try:
            _sync_custom_worlds()
        except ValueError as exc:
            _write_status(status="error", finished=time.time(), log=str(exc))
            return False
        tmp = config.DATA / "schemas.new"
        shutil.rmtree(tmp, ignore_errors=True)
        ok, log = _run(["extract", "--out", str(tmp)], config.EXTRACT_TIMEOUT)
        if ok and (tmp / "index.json").exists():
            shutil.rmtree(config.SCHEMAS, ignore_errors=True)
            tmp.rename(config.SCHEMAS)
        _write_status(status="ok" if ok else "error", finished=time.time(), log=log[-20000:])
        _schema_cache.clear()
        return ok


def start_extract() -> None:
    if extract_status().get("status") != "running" or not ap_lock.locked():
        threading.Thread(target=extract, daemon=True).start()


# --- Schema access (cached per file mtime) -----------------------------------------------------

_schema_cache: dict[str, tuple[float, dict]] = {}


def _load_json(path: Path) -> dict | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _schema_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    _schema_cache[str(path)] = (mtime, data)
    return data


def index() -> dict:
    return _load_json(config.SCHEMAS / "index.json") or {"games": {}, "failed": {}, "ap_version": "?"}


def schema(slug: str) -> dict | None:
    if slug not in index()["games"]:
        return None
    return _load_json(config.SCHEMAS / f"{slug}.json")


# --- Generation --------------------------------------------------------------------------------

def generate(yaml_dir: Path, out_dir: Path, spoiler: int, race: bool,
             expected_worlds: dict[str, str] | None = None) -> tuple[bool, str, Path | None]:
    with ap_lock:
        # Check the exact active archive bytes while holding the same lock used
        # by upload/activation routes. Version switches cannot race a build.
        for module, expected_sha in (expected_worlds or {}).items():
            file = config.APWORLDS / (module + ".apworld")
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected_sha:
                return False, f"{module}: APWorld wurde seit dem Seed-Snapshot verändert.", None
        try:
            _sync_custom_worlds()
        except ValueError as exc:
            return False, str(exc), None
        out_dir.mkdir(parents=True, exist_ok=True)
        args = ["generate", "--players", str(yaml_dir), "--out", str(out_dir), "--spoiler", str(spoiler)]
        ok, log = _run(args + (["--race"] if race else []), config.GENERATE_TIMEOUT)
    zips = sorted(out_dir.glob("AP_*.zip"), key=lambda p: p.stat().st_mtime)
    return ok and bool(zips), log, (zips[-1] if zips else None)
