"""Read-only official WebHost API client. Never follows user-controlled URLs."""
from __future__ import annotations

import base64
import json
import re
import time
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ORIGIN = "https://archipelago.gg"
TIMEOUT = 8
MAX_BYTES = 12 * 1024 * 1024
ENDPOINTS = {"room_status": 60, "tracker": 60, "static_tracker": 300}


class APIError(Exception):
    def __init__(self, message, kind="unavailable", retry_after=60):
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


def retry_delay(headers, default=60):
    """Honor both Retry-After formats without retrying faster than the API TTL."""
    value = headers.get("Retry-After", "") if headers else ""
    try:
        delay = int(value) if str(value).isdigit() else parsedate_to_datetime(value).timestamp() - time.time()
        return max(60, min(86400, delay))
    except (ValueError, TypeError, OverflowError):
        return default


def suuid(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{22}", value):
        raise ValueError("Die Raum-ID muss eine gültige Archipelago-ID mit 22 Zeichen sein.")
    decoded = base64.urlsafe_b64decode(value + "==")
    if len(decoded) != 16 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value:
        raise ValueError("Ungültige Archipelago-ID.")
    return value


def room_id(url):
    try:
        parsed = urlsplit(url.strip())
        if (parsed.scheme != "https" or parsed.netloc not in ("archipelago.gg", "www.archipelago.gg")
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError()
        match = re.fullmatch(r"/room/([A-Za-z0-9_-]{22})/?", parsed.path)
        if not match:
            raise ValueError()
        return suuid(match[1])
    except (ValueError, AttributeError):
        raise ValueError("Bitte einen vollständigen Raumlink wie https://archipelago.gg/room/… verwenden.") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(endpoint, identifier):
    """Only three fixed HTTPS endpoints; no cookies, room wakeups, or commands."""
    if endpoint not in ENDPOINTS:
        raise ValueError("Unbekannter API-Endpunkt.")
    identifier = suuid(identifier)
    request = Request(f"{ORIGIN}/api/{endpoint}/{identifier}",
                      headers={"Accept": "application/json", "User-Agent": "MultiworldHub-Live/1.0"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=TIMEOUT) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise APIError("Die API-Antwort ist zu groß.", "invalid")
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise APIError("Die API liefert derzeit kein JSON.", "invalid")
            payload = json.loads(body)
    except HTTPError as exc:
        delay = retry_delay(exc.headers, 300 if exc.code == 429 else 60)
        exc.close()
        if exc.code == 404:
            raise APIError("Raum oder Tracker nicht gefunden; möglicherweise entfernt.", "not_found", 300) from None
        if exc.code in (401, 403):
            raise APIError("Diese Tracker-Daten sind nicht öffentlich verfügbar.", "protected", 300) from None
        if exc.code == 429:
            raise APIError("Archipelago begrenzt gerade die Abrufe. Wir warten vor dem nächsten Versuch.",
                           "rate_limited", delay) from None
        raise APIError("Die Archipelago-API ist vorübergehend nicht erreichbar.", retry_after=delay) from None
    except (URLError, TimeoutError, OSError):
        raise APIError("Die Archipelago-API ist vorübergehend nicht erreichbar.") from None
    except (ValueError, UnicodeError, RecursionError):
        raise APIError("Die API-Antwort konnte nicht gelesen werden.", "invalid") from None
    if not isinstance(payload, dict):
        raise APIError("Das API-Antwortformat hat sich geändert.", "invalid")
    return sanitize(endpoint, payload)


def sanitize(endpoint, payload):
    """Do not even persist hints, downloads, datapackages or arbitrary slot data."""
    fields = {
        "room_status": ("tracker", "players", "last_port", "last_activity", "timeout"),
        "static_tracker": ("groups", "player_locations_total", "player_game"),
        "tracker": ("aliases", "player_checks_done", "player_items_received",
                    "activity_timers", "connection_timers", "player_status"),
    }[endpoint]
    return {key: payload[key] for key in fields if key in payload}
