"""Private, bounded Universal Tracker evaluations, without seed-placement input."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.request import urlopen

import yaml

from . import ap_bridge, apworld_library, config, db

ENGINE_URL = "https://github.com/FarisTheAncient/Archipelago/releases/download/Tracker_v0.3.3/tracker.apworld"
ENGINE_SHA256 = "a909f96404b0009865d39b87cec8bb749446783577d77bd4fa14431cef0c2140"
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hub-logic")
_lock = threading.Lock()
_jobs = {}


def engine_path():
    return config.DATA / "logic_tools" / "tracker.apworld"


def engine_ready():
    path = engine_path()
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == ENGINE_SHA256


def install_engine():
    if not ap_bridge.trusted_custom_execution():
        raise ValueError("Der Host hat das Ausführen zusätzlicher APWorlds deaktiviert.")
    with urlopen(ENGINE_URL, timeout=15) as response:
        data = response.read(512 * 1024 + 1)
    if len(data) > 512 * 1024 or hashlib.sha256(data).hexdigest() != ENGINE_SHA256:
        raise ValueError("Die Logik-Engine entspricht nicht der geprüften Version. Installation abgebrochen.")
    if apworld_library.inspect_bytes(data)["module"] != "tracker":
        raise ValueError("Ungültige Universal-Tracker-Datei.")
    apworld_library._write_atomic(engine_path(), data)


def evaluation_input(build, slot, client):
    if not engine_ready():
        return None, dict(state="engine_missing", error="Universal Tracker ist auf dem Hub noch nicht eingerichtet.")
    if not ap_bridge.ap_ready() or not ap_bridge.trusted_custom_execution():
        return None, dict(state="unavailable", error="Die Archipelago-Laufzeit oder die Freigabe für APWorld-Code fehlt.")
    if client is None or client.state != "connected" or client.slot_name != slot["slot"]:
        return None, dict(state="not_connected", error="Verbinde zuerst genau diesen eigenen Slot in der Archipelago-Konsole.")
    if client.slot_data is None or not client.items_synced:
        return None, dict(state="waiting_for_data", error="Slotdaten oder vollständige Empfangsliste fehlen. Bei älteren Verbindungen bitte die Konsole neu verbinden.")
    archive_sha = slot.get("apworld_sha256")
    if archive_sha:
        archive = config.APWORLDS / (slot["game"] + ".apworld")
        mirrored = config.AP_SOURCE / "custom_worlds" / (slot["game"] + ".apworld")
        if (not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != archive_sha
                or not mirrored.is_file() or hashlib.sha256(mirrored.read_bytes()).hexdigest() != archive_sha):
            return None, dict(state="world_changed", error="Die aktive APWorld-Version passt nicht zum generierten Seed.")
    package = db.query("SELECT items,locations FROM console_packages WHERE build_id=? AND game=?",
                       (build["id"], slot["game_name"]), one=True)
    if not package:
        return None, dict(state="waiting_for_data", error="Der Datenkatalog des Archipelago-Servers wird noch geladen.")
    folder = config.SESSIONS / "_seeds" / str(build["id"]) / "players"
    player_yaml = None
    for path in folder.glob("*.yaml"):
        if path.stat().st_size > 512 * 1024:
            continue
        text = path.read_text(encoding="utf-8")
        content = yaml.safe_load(text)
        if isinstance(content, dict) and content.get("name") == slot["slot"] and content.get("game") == slot["game_name"]:
            expected = db.loads(build["snapshot"]).get("yamls", {}).get(path.name)
            if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                return None, dict(state="unavailable", error="Die Spieler-YAML stimmt nicht mit dem Seed-Snapshot überein.")
            player_yaml = text
            break
    if player_yaml is None:
        return None, dict(state="unavailable", error="Die unveränderliche Spieler-YAML dieses Seeds ist nicht mehr vorhanden.")
    return dict(tracker=str(engine_path().resolve()), game=slot["game_name"], slot=slot["slot"],
                slot_id=client.slot, slot_data=client.slot_data, received=list(client.received),
                missing=sorted(client.missing.copy()), checked=sorted(client.checked.copy()),
                item_names=db.loads(package["items"]), yaml=player_yaml,
                ap_version=db.loads(build["snapshot"]).get("archipelago_version"),
                hide=ap_bridge._hidden_builtins()), None


def run_evaluation(data):
    try:
        with tempfile.TemporaryDirectory(prefix="hub-logic-") as temporary:
            request = {**data, "players": temporary}
            Path(temporary, "player.yaml").write_text(request.pop("yaml"), encoding="utf-8")
            safe_keys = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA")
            environment = {key: os.environ[key] for key in safe_keys if key in os.environ}
            environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            # Same lock as generation/extraction; never race AP's world mirror.
            with ap_bridge.ap_lock:
                result = subprocess.run([str(config.AP_PYTHON), str(config.ROOT / "logic_worker.py")],
                    input=db.dumps(request), capture_output=True, text=True, encoding="utf-8",
                    errors="replace", cwd=config.AP_SOURCE, env=environment, timeout=90,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if result.returncode or len(result.stdout) > 16 * 1024 * 1024:
                raise ValueError()
            value = json.loads(result.stdout)
            if value.get("state") not in ("ready", "unsupported"):
                raise ValueError()
            return {**value, "observed_at": time.time()}
    except subprocess.TimeoutExpired:
        return dict(state="error", error="Die Logikberechnung hat das Zeitlimit erreicht. Bitte später erneut versuchen.")
    except (OSError, ValueError):
        return dict(state="error", error="Die Logikberechnung konnte nicht abgeschlossen werden.")


def status(identity, data, refresh=False):
    signature = hashlib.sha256(db.dumps(data).encode()).hexdigest()
    with _lock:
        entry = _jobs.get(identity)
        if entry and entry["signature"] == signature:
            if entry["future"].done():
                return entry["future"].result()
            return dict(state="loading", error="Die Spielregeln werden ausgewertet …")
        if not refresh:
            return dict(state="stale" if entry else "idle", error="Aktuellen Serverstand berechnen lassen.")
        if entry and not entry["future"].done():
            return dict(state="loading", error="Die vorherige Berechnung läuft noch; anschließend erneut aktualisieren.")
        if sum(not job["future"].done() for job in _jobs.values()) >= 4:
            return dict(state="busy", error="Die Logikberechnung ist ausgelastet. Bitte kurz warten.")
        for key in list(_jobs):
            if len(_jobs) < 64:
                break
            if _jobs[key]["future"].done():
                del _jobs[key]
        _jobs[identity] = dict(signature=signature, future=_pool.submit(run_evaluation, data))
        return dict(state="loading", error="Die Spielregeln werden ausgewertet …")
