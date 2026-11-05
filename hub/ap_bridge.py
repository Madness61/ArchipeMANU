"""Everything that touches the Archipelago install: APWorld files, option extraction, generation."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from . import config

RUNNER = config.ROOT / "ap_runner.py"

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


def store_apworld(data: bytes) -> dict:
    """Save an uploaded .apworld as <module>.apworld; an older file for the same module goes to _old/."""
    with tempfile.NamedTemporaryFile(suffix=".apworld", delete=False, dir=config.DATA) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        info = apworld_info(tmp_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    target = config.APWORLDS / f"{info['module']}.apworld"
    if target.exists():
        old_dir = config.APWORLDS / "_old"
        old_dir.mkdir(exist_ok=True)
        shutil.move(target, old_dir / f"{info['module']}-{time.strftime('%Y%m%d-%H%M%S')}.apworld")
    shutil.move(tmp_path, target)
    return apworld_info(target)


def list_apworlds() -> list[dict]:
    result = []
    for path in sorted(config.APWORLDS.glob("*.apworld")):
        try:
            result.append(apworld_info(path))
        except ValueError as e:
            result.append({"module": path.stem, "file": path.name, "error": str(e)})
    return result


def delete_apworld(module: str) -> None:
    path = config.APWORLDS / f"{module}.apworld"
    if path.parent == config.APWORLDS and path.exists():
        path.unlink()


def _sync_custom_worlds() -> None:
    """Mirror data/apworlds into AP's custom_worlds folder."""
    target = config.AP_SOURCE / "custom_worlds"
    target.mkdir(exist_ok=True)
    wanted = {p.name: p for p in config.APWORLDS.glob("*.apworld")}
    for existing in target.glob("*.apworld"):
        if existing.name not in wanted:
            existing.unlink()
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
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
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
        _sync_custom_worlds()
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

def generate(yaml_dir: Path, out_dir: Path, spoiler: int, race: bool) -> tuple[bool, str, Path | None]:
    with ap_lock:
        _sync_custom_worlds()
        out_dir.mkdir(parents=True, exist_ok=True)
        args = ["generate", "--players", str(yaml_dir), "--out", str(out_dir), "--spoiler", str(spoiler)]
        ok, log = _run(args + (["--race"] if race else []), config.GENERATE_TIMEOUT)
    zips = sorted(out_dir.glob("AP_*.zip"), key=lambda p: p.stat().st_mtime)
    return ok and bool(zips), log, (zips[-1] if zips else None)
