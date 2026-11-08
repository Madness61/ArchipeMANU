"""Settings, all overridable via environment variables."""
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Where setup.ps1 / setup.sh put the Archipelago source and its Python env.
AP_HOME = Path(os.environ.get("AP_HOME", Path.home() / ".ap-yaml-hub"))
AP_SOURCE = Path(os.environ.get("AP_SOURCE", AP_HOME / "Archipelago"))
AP_PYTHON = Path(os.environ.get(
    "AP_PYTHON",
    AP_HOME / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"),
))

DATA = Path(os.environ.get("HUB_DATA", ROOT / "data"))
APWORLDS = DATA / "apworlds"
SCHEMAS = DATA / "schemas"
SESSIONS = DATA / "sessions"
DB_PATH = DATA / "hub.db"

# Registration is open; legacy HUB_PASSWORD/HUB_INVITE_CODE values are ignored.
COOKIE_SECURE = os.environ.get("HUB_COOKIE_SECURE", "0") == "1"

GENERATE_TIMEOUT = int(os.environ.get("HUB_GENERATE_TIMEOUT", 15 * 60))
EXTRACT_TIMEOUT = int(os.environ.get("HUB_EXTRACT_TIMEOUT", 10 * 60))

SLOT_NAME_MAX = 16


def secret_key() -> str:
    key_file = DATA / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    return key_file.read_text(encoding="utf-8").strip()


def ensure_dirs() -> None:
    for path in (DATA, APWORLDS, SCHEMAS, SESSIONS):
        path.mkdir(parents=True, exist_ok=True)
