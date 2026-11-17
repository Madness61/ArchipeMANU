"""Shared, versioned reference counts. Never count the static location catalogue."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time

from . import ap_bridge, apworld_library, config, yamlgen

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="standard-checks")
_lock = threading.Lock()
_jobs = {}


@lru_cache(maxsize=128)
def _digest(path, size, stamp):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def specification(slug, fresh=False):
    schema = ap_bridge.schema(slug)
    if not schema:
        raise ValueError("Die Spieloptionen müssen zuerst eingelesen werden.")
    issue = ap_bridge.world_error(slug)
    if issue:
        raise ValueError(issue)
    if not ap_bridge.ap_ready():
        raise ValueError("Die Archipelago-Laufzeit ist noch nicht eingerichtet.")
    version = ap_bridge.index().get("ap_version", "0.0.0")
    text = yamlgen.player_yaml("StandardCheck", schema, {}, "Spiel-Standard ohne Profil oder Gruppen-Vorlage", version)
    worlds = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest() if fresh else
              _digest(str(p), p.stat().st_size, p.stat().st_mtime_ns)) for p in config.APWORLDS.glob("*.apworld")}
    stamps = {name: (config.AP_SOURCE / name).stat().st_mtime_ns
              for name in ("Main.py", "Generate.py") if (config.AP_SOURCE / name).exists()}
    content = dict(yaml=text, worlds=worlds, version=version, source=str(config.AP_SOURCE),
                   stamps=stamps, runner=hashlib.sha256(ap_bridge.RUNNER.read_bytes()).hexdigest())
    key = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    return dict(key=key, slug=slug, game=schema["game"], **content)


def cache_path(spec):
    return config.DATA / "check_previews" / (spec["key"] + ".json")


def evaluate(spec):
    # Do not delay a running generation or schema extraction with a preview.
    if not ap_bridge.ap_lock.acquire(blocking=False):
        return dict(state="busy", error="Archipelago arbeitet gerade an einer Runde oder an Spieloptionen. Bitte später erneut prüfen.")
    try:
        if specification(spec["slug"], fresh=True)["key"] != spec["key"]:
            return dict(state="stale", error="Die Spielversion hat sich geändert. Bitte erneut prüfen.")
        ap_bridge._sync_custom_worlds()
        workspace = config.DATA / "check_previews" / "_work"
        workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="probe-", dir=workspace) as folder:
            players, output = Path(folder) / "players", Path(folder) / "output"
            players.mkdir(); output.mkdir()
            (players / "standard.yaml").write_text(spec["yaml"], encoding="utf-8")
            ok, _log = ap_bridge._run(["preview", "--players", str(players), "--out", str(output)], 120)
            path = output / "check_preview.json"
            if not ok or not path.is_file() or path.stat().st_size > 4096:
                return dict(state="unavailable", error="Die Standardkonfiguration konnte nicht berechnet werden. Manche APWorlds benötigen zusätzliche Dateien oder unterstützen keinen Einzelspiel-Probelauf. Spielanleitung und Host-Einrichtung prüfen.")
            data = json.loads(path.read_text(encoding="utf-8"))
            if (data.get("source") != "archipelago_standard_probe" or data.get("game") != spec["game"]
                    or type(data.get("checks")) is not int or not 0 <= data["checks"] <= 1000000
                    or data.get("seed") != 20261110):
                raise ValueError("Invalid preview result")
        result = dict(state="ready", checks=data["checks"], seed=data["seed"], measured_at=time.time())
        apworld_library._write_atomic(cache_path(spec), json.dumps(result).encode())
        return result
    except Exception:
        return dict(state="unavailable", error="Die Check-Vorschau ist für diese Spielversion nicht verfügbar. Es wird keine Anzahl geschätzt.")
    finally:
        ap_bridge.ap_lock.release()


def status(slug, start=False):
    try:
        spec = specification(slug)
    except (ValueError, OSError) as exc:
        return dict(state="unavailable", error=str(exc) if isinstance(exc, ValueError) else "Die Spielversion konnte nicht gelesen werden.")
    try:
        path = cache_path(spec)
        if path.is_file() and path.stat().st_size < 4096:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict) and saved.get("state") == "ready" and type(saved.get("checks")) is int and 0 <= saved["checks"] <= 1000000:
                return saved
    except (ValueError, OSError, TypeError):
        pass
    identity = (str(config.DATA), spec["key"])
    with _lock:
        job = _jobs.get(identity)
        if job and not job.done():
            return dict(state="loading", error="Standard-Checks werden berechnet …")
        if job and not start:
            return job.result()
        if not start:
            return dict(state="idle")
        if sum(not j.done() for j in _jobs.values()) >= 4:
            return dict(state="busy", error="Es laufen bereits Check-Vorschauen. Bitte kurz warten.")
        for old in list(_jobs):
            if _jobs[old].done():
                del _jobs[old]
        _jobs[identity] = _pool.submit(evaluate, spec)
        return dict(state="loading", error="Standard-Checks werden berechnet …")
