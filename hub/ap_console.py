"""Bounded Archipelago TextOnly clients. No game checks, cheats, or remote code."""
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import logging
from pathlib import Path
import queue
import random
import secrets
import socket
import sqlite3
import ssl
import threading
import time

from . import config, db
from . import i18n

MAX_EVENTS = 10000
MAX_FRAME = 16 * 1024 * 1024
IDLE_SECONDS = 30 * 60  # Historical constant; browser inactivity no longer ends a connection.
RETRY_BASE = 2
RETRY_MAX = 60
GUARD_SECONDS = 5
PING_SECONDS = 25
COMMANDS = [
    ("/help", "Alle unterstützten Befehle anzeigen"),
    ("/connect", "Mit dem gespeicherten Server und deinem Slot verbinden"),
    ("/disconnect", "Textverbindung trennen; dein Spielclient bleibt verbunden"),
    ("/received", "Vom Server gemeldete Items für deinen Slot anzeigen"),
    ("/missing [Filter]", "Noch offene Checks deines Slots laut Server anzeigen"),
    ("/items [Filter]", "Itemnamen deines Spiels durchsuchen"),
    ("/locations [Filter]", "Check-Namen deines Spiels durchsuchen"),
    ("/hint [Item]", "Hinweis anfragen; der Server entscheidet über Kosten und Verfügbarkeit"),
    ("/hint_location [Check]", "Hinweis zu einem Check anfragen"),
    ("/status", "Serverstatus abfragen"), ("/players", "Mitspieler abfragen"),
    ("!remaining", "Verbleibende Items abfragen; abhängig von den Serverregeln"),
    ("!countdown [Sekunden]", "Countdown im Archipelago-Chat anfragen"),
]
SERVER_COMMANDS = {"!help", "!hint", "!hint_location", "!status", "!players", "!remaining", "!countdown"}
_clients = {}
_lock = threading.RLock()
_wire_logger = logging.getLogger("hub.ap_console.wire")
_wire_logger.setLevel(logging.WARNING)  # Never log Connect frames containing a room password.
_state_logger = logging.getLogger("hub.ap_console.state")


def migrate():
    with db.transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS console_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, payload TEXT NOT NULL, observed_at REAL NOT NULL,
            event_key TEXT, hosted_id INTEGER REFERENCES hosted_rooms(id) ON DELETE CASCADE,
            UNIQUE(build_id,event_key)
        );
        CREATE INDEX IF NOT EXISTS console_event_build ON console_events(build_id,id);
        CREATE TABLE IF NOT EXISTS console_packages(
            build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
            game TEXT NOT NULL, items TEXT NOT NULL, locations TEXT NOT NULL, updated_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(build_id,game)
        );
        """)
        if "hosted_id" not in {r["name"] for r in conn.execute("PRAGMA table_info(console_events)")}:
            conn.execute("ALTER TABLE console_events ADD COLUMN hosted_id INTEGER REFERENCES hosted_rooms(id) ON DELETE CASCADE")
        if "updated_at" not in {r["name"] for r in conn.execute("PRAGMA table_info(console_packages)")}:
            conn.execute("ALTER TABLE console_packages ADD COLUMN updated_at REAL NOT NULL DEFAULT 0")


@contextmanager
def connection(path):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def record(path, build_id, user_id, kind, payload, key=None, hosted_id=None):
    with connection(path) as conn:
        conn.execute("INSERT OR IGNORE INTO console_events(build_id,user_id,kind,payload,observed_at,event_key,hosted_id) VALUES (?,?,?,?,?,?,?)",
                     (build_id, user_id, kind, db.dumps(payload), time.time(), key, hosted_id))
        conn.execute("""DELETE FROM console_events WHERE build_id=? AND id < COALESCE(
            (SELECT id FROM console_events WHERE build_id=? ORDER BY id DESC LIMIT 1 OFFSET ?),0)""",
                     (build_id, build_id, MAX_EVENTS - 1))


def catalog(conn, build_id):
    return {row["game"]: {"items": db.loads(row["items"]), "locations": db.loads(row["locations"])}
            for row in conn.execute("SELECT * FROM console_packages WHERE build_id=?", (build_id,))}


def named(packages, game, kind, identifier):
    return packages.get(game, {}).get(kind, {}).get(str(identifier), f"{'Item' if kind == 'items' else 'Check'} #{identifier}")


def render_payload(payload, packages):
    if payload.get("type") == "item":
        item = named(packages, payload["recipient_game"], "items", payload["item_id"])
        check = named(packages, payload["sender_game"], "locations", payload["location_id"])
        return f"{payload['sender']} → {payload['recipient']}: {item} · {check} ({payload['sender_game']})"
    if "parts" in payload:
        return "".join(named(packages, part["game"], part["kind"], part["id"]) if "kind" in part
                       else part["text"] for part in payload["parts"])[:12000]
    return payload.get("text", "")


def events(build_id, user_id, after=0, kind="all", before=0):
    conn = db.get()
    packages = catalog(conn, build_id)
    args = [build_id, user_id]
    scope = "build_id=? AND (user_id IS NULL OR user_id=?)"
    endpoint = conn.execute("SELECT id FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1", (build_id,)).fetchone()
    scope += " AND (hosted_id IS NULL OR hosted_id=?)"
    args.append(endpoint["id"] if endpoint else -1)
    snapshot=conn.execute('SELECT snapshot FROM seed_builds WHERE id=?',(build_id,)).fetchone()
    own=[s['slot'] for s in db.loads(snapshot['snapshot']).get('slots',[]) if s.get('player_id')==user_id] if snapshot else []
    if kind in ('for_me','from_me','others'):
        names=','.join('?' for _ in own) or 'NULL'
        scope += " AND kind='items' AND json_extract(payload,'$.type')='item'"
        if not own:
            scope += ' AND 0' if kind!='others' else ''
        elif kind=='others':
            scope += f" AND json_extract(payload,'$.recipient') NOT IN ({names}) AND json_extract(payload,'$.sender') NOT IN ({names})"
            args.extend(own+own)
        else:
            field='recipient' if kind=='for_me' else 'sender'
            scope += f" AND json_extract(payload,'$.{field}') IN ({names})"
            args.extend(own)
    elif kind != "all":
        scope += " AND kind=?"
        args.append(kind)
    if after:
        rows = conn.execute(f"SELECT * FROM console_events WHERE {scope} AND id>? ORDER BY id LIMIT 100", (*args, after)).fetchall()
    elif before:
        rows = list(reversed(conn.execute(f"SELECT * FROM console_events WHERE {scope} AND id<? ORDER BY id DESC LIMIT 100", (*args, before)).fetchall()))
    else:
        rows = list(reversed(conn.execute(f"SELECT * FROM console_events WHERE {scope} ORDER BY id DESC LIMIT 100", args).fetchall()))
    result = []
    for row in rows:
        payload = db.loads(row["payload"])
        text=render_payload(payload,packages)
        if payload.get('origin')=='hub':
            first,separator,rest=text.partition('\n')
            text=i18n.t(first)+(separator+rest if separator else '')
        entry = dict(id=row["id"], kind=row["kind"], at=row["observed_at"], text=text,
                     visibility="team" if row["user_id"] is None else "personal")
        if payload.get("type") == "item":
            entry['for_me'],entry['from_me']=payload['recipient'] in own,payload['sender'] in own
            entry["delivery"] = dict(item_id=payload["item_id"], item=named(packages,payload["recipient_game"],"items",payload["item_id"]),
                sender=dict(name=payload["sender"],game=payload["sender_game"]),
                recipient=dict(name=payload["recipient"],game=payload["recipient_game"]),
                location=dict(id=payload["location_id"],name=named(packages,payload["sender_game"],"locations",payload["location_id"])))
        result.append(entry)
    return result


def open_socket(host, port, secure):
    """Use only the saved endpoint; pin DNS and exclude metadata/link-local targets."""
    from websockets.sync.client import connect
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("Serveradresse konnte nicht aufgelöst werden.")
    for _, _, _, _, address in addresses:
        ip = ipaddress.ip_address(address[0])
        ip = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip
        if not ip.is_loopback and (ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            raise ValueError("Diese Serveradresse ist für eine Archipelago-Verbindung nicht zulässig.")
    family, socktype, proto, _, address = addresses[0]
    raw = socket.socket(family, socktype, proto)
    try:
        raw.settimeout(8)
        raw.connect(address)
        # A supplied socket is not reset by websockets 13.x for plain WS.
        # Keep the TCP deadline separate from the lifetime of the reader thread.
        raw.settimeout(None)
        target = f"[{host}]" if ":" in host else host
        return connect(f"{'wss' if secure else 'ws'}://{target}:{port}", sock=raw,
                       open_timeout=8, close_timeout=2, max_size=MAX_FRAME, compression="deflate", logger=_wire_logger)
    except Exception:
        raw.close()
        raise


def connect_transport(host, port, secure=None):
    """Negotiate transport before sending any AP login or room password."""
    if secure is not None:
        return open_socket(host, port, secure), "wss" if secure else "ws"
    try:
        return open_socket(host, port, True), "wss"
    except ssl.SSLCertVerificationError:
        # An invalid certificate must never silently downgrade the connection.
        raise
    except (ssl.SSLError, EOFError, ConnectionError, TimeoutError):
        return open_socket(host, port, False), "ws"


def connection_error(exc):
    """Useful diagnostics without echoing packets, passwords or server text."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "Das TLS-Zertifikat des Servers konnte nicht überprüft werden. Bitte Serveradresse und Zertifikat prüfen."
    if isinstance(exc, socket.gaierror):
        return "Die Serveradresse konnte nicht aufgelöst werden. Bitte die gespeicherte Adresse prüfen."
    if isinstance(exc, ConnectionRefusedError):
        return "Der Server lehnt die Verbindung ab. Bitte den Raum auf der Archipelago-Webseite starten und den aktuellen Port prüfen."
    if isinstance(exc, TimeoutError):
        return "Der Server antwortet nicht rechtzeitig. Bitte Raumstatus, aktuellen Port und Erreichbarkeit prüfen."
    if isinstance(exc, (ssl.SSLError, EOFError, ConnectionResetError)):
        return "Der Verbindungsaufbau wurde abgebrochen. Bitte die Verbindungsart Automatisch verwenden; archipelago.gg benötigt WSS."
    return "Die Textverbindung wurde unterbrochen. Bitte Raumstatus und aktuellen Port prüfen und erneut verbinden."


def integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit() and len(value) < 24:
        return int(value)
    raise ValueError("Ungültige Protokoll-ID.")


def network_item(value):
    if isinstance(value, dict):
        return {key: integer(value[key]) for key in ("item", "location", "player", "flags")}
    if isinstance(value, list) and len(value) >= 4:
        return dict(zip(("item", "location", "player", "flags"), map(integer, value[:4])))
    raise ValueError("Ungültiges NetworkItem.")


class Client:
    def __init__(self, path, build, user_id, token_hash, endpoint, slot, password, secure):
        self.path, self.build_id, self.user_id = Path(path), build["id"], user_id
        self.token_hash, self.endpoint = token_hash, endpoint
        self.expected = db.loads(build["snapshot"])["slots"]
        self.expected_seed = build["seed_name"] or ""
        self.slot_name, self.password, self.secure = slot, password, secure
        self.transport = None
        self.state, self.error = "connecting", ""
        self.retry_attempt = 0
        self.failure_streak = 0
        self.stable_since = None
        self.next_retry_at = self.last_contact = self.connected_at = self.interrupted_at = None
        self.reason = ""
        self.uuid = secrets.token_hex(16)
        self.stop = threading.Event()
        self.outbox = queue.Queue(maxsize=30)
        self.wire = None
        self.team, self.slot, self.game = None, None, ""
        self.players, self.received, self.missing, self.checked = {}, [], set(), set()
        self.slot_data = None
        self.items_synced = False
        self.last_seen = time.monotonic()
        self.thread = threading.Thread(target=self.run, daemon=True, name=f"ap-console-{self.build_id}-{user_id}")

    def note(self, text, kind="system", origin="hub"):
        record(self.path, self.build_id, self.user_id, kind, {"text": text,"origin":origin}, hosted_id=self.endpoint["id"])

    def valid(self):
        with connection(self.path) as conn:
            authorized = conn.execute("""SELECT 1 FROM auth_sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.user_id=? AND s.expires_at>?""",
                                      (self.token_hash, self.user_id, time.time())).fetchone()
            row = conn.execute("SELECT completed_at,snapshot FROM seed_builds WHERE id=?", (self.build_id,)).fetchone()
            endpoint = conn.execute("SELECT id FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1", (self.build_id,)).fetchone()
            membership = conn.execute("""SELECT 1 FROM seed_builds b JOIN sessions l ON l.id=b.session_id
                JOIN users u ON u.id=? WHERE b.id=? AND (u.is_admin=1 OR l.created_by=u.id
                OR EXISTS (SELECT 1 FROM lobby_members lm WHERE lm.session_id=l.id AND lm.user_id=u.id)
                OR EXISTS (SELECT 1 FROM entries e WHERE e.session_id=l.id AND e.user_id=u.id))""",
                                      (self.user_id, self.build_id)).fetchone()
            return bool(authorized and row and not row["completed_at"] and not db.loads(row["snapshot"]).get("race")
                        and membership and endpoint and endpoint["id"] == self.endpoint["id"])

    def run(self):
        """One worker owns all sockets, retries and commands for this explicit login."""
        try:
            while not self.stop.is_set() and self.valid():
                self.items_synced = False
                self.received, self.players, self.slot_data = [], {}, None
                try:
                    self.wire, self.transport = connect_transport(self.endpoint["host"], self.endpoint["port"], self.secure)
                    if self.stop.is_set() or not self.valid():
                        break
                    self.state = "authenticating"
                    self.serve()
                    break
                except (ValueError, ssl.SSLCertVerificationError) as exc:
                    if not self.stop.is_set():
                        self.error = str(exc) if isinstance(exc, ValueError) else connection_error(exc)
                        self.transition("action_required", "authentication_or_protocol")
                    break
                except Exception as exc:
                    if self.stop.is_set():
                        break
                    from websockets.exceptions import ConnectionClosed, InvalidHandshake
                    if not isinstance(exc, (OSError, EOFError, ConnectionClosed, InvalidHandshake)):
                        self.error = "Die Textverbindung konnte nicht sicher fortgesetzt werden. Bitte erneut verbinden."
                        self.transition("action_required", "internal")
                        break
                    self.error = connection_error(exc)
                    self.interrupted_at = self.interrupted_at or time.time()
                    if self.stable_since and time.monotonic() - self.stable_since > 60:
                        self.failure_streak = 0
                    self.stable_since = None
                    self.failure_streak += 1
                    self.retry_attempt = self.failure_streak
                    delay = min(RETRY_MAX, RETRY_BASE * 2 ** min(self.retry_attempt - 1, 10))
                    delay = min(RETRY_MAX, delay * random.uniform(1, 1.2))
                    self.next_retry_at = time.time() + delay
                    self.transition("reconnecting" if self.retry_attempt < 5 else "temporarily_unavailable", type(exc).__name__)
                finally:
                    if self.wire:
                        self.wire.close()
                        self.wire = None
                    self.discard_commands()
                while not self.stop.is_set() and time.time() < (self.next_retry_at or 0):
                    if not self.valid():
                        return
                    self.stop.wait(min(GUARD_SECONDS, max(0, self.next_retry_at - time.time())))
        finally:
            self.password = None
            self.items_synced = False
            self.next_retry_at = None
            self.discard_commands()
            if self.wire:
                self.wire.close()
                self.wire = None
            if self.state != "action_required":
                self.transition("disconnected", "stopped_or_authorization_changed")

    def transition(self, state, reason):
        self.state, self.reason = state, reason
        _state_logger.info("build=%s user=%s state=%s reason=%s", self.build_id, self.user_id, state, reason)
        message = {
            "reconnecting": "Textverbindung unterbrochen. Automatische Wiederverbindung; während der Lücke können Itemmeldungen fehlen.",
            "temporarily_unavailable": "Textserver vorübergehend nicht erreichbar. Weitere Versuche folgen automatisch.",
            "action_required": self.error,
            "disconnected": "Textverbindung beendet. Spielclient und WebHost-API werden separat betrieben.",
        }.get(state)
        if message:
            try:
                self.note(message)
            except sqlite3.Error:
                pass  # The authorized user, build or endpoint may have been deleted.

    def discard_commands(self):
        discarded = False
        while not self.outbox.empty():
            try:
                self.outbox.get_nowait()
                discarded = True
            except queue.Empty:
                break
        if discarded:
            try:
                self.note("Ausstehende Befehle wurden verworfen. Bitte bei Bedarf ausdrücklich erneut senden.")
            except sqlite3.Error:
                pass

    def serve(self):
        started, last_guard, last_ping = time.monotonic(), 0, time.monotonic()
        while not self.stop.is_set():
            now = time.monotonic()
            if now - last_guard > GUARD_SECONDS:
                if not self.valid():
                    return
                last_guard = now
            if self.state != "connected" and now - started > 20:
                raise TimeoutError("handshake timeout")
            while self.state == "connected" and not self.outbox.empty():
                if not self.valid():
                    return
                self.handle_command(self.outbox.get_nowait())
            if now - last_ping > PING_SECONDS:
                if not self.wire.ping().wait(5):
                    raise TimeoutError("ping timeout")
                self.last_contact = time.time()
                last_ping = now
            try:
                frame = self.wire.recv(timeout=0.5)
            except TimeoutError:
                continue
            data = json.loads(frame)
            self.last_contact = time.time()
            if not isinstance(data, list) or len(data) > 5000:
                raise ValueError("Ungültiges Archipelago-Paket.")
            for packet in data:
                if not isinstance(packet, dict):
                    raise ValueError("Ungültiges Archipelago-Paket.")
                self.packet(packet)

    def packet(self, packet):
        cmd = packet.get("cmd")
        if cmd == "RoomInfo":
            if self.state != "authenticating":
                raise ValueError("Unerwarteter erneuter Anmeldevorgang des Servers. Bitte erneut verbinden.")
            seed = str(packet.get("seed_name", ""))
            if self.expected_seed and seed not in {self.expected_seed, self.expected_seed.removeprefix("AP_")}:
                raise ValueError("Der Server gehört zu einem anderen Seed. Bitte die gespeicherte Verbindung prüfen.")
            self.wire.send(db.dumps([dict(cmd="Connect", password=self.password or None, game="", name=self.slot_name,
                                         uuid=self.uuid, version={"major":0,"minor":6,"build":8,"class":"Version"},
                                         items_handling=7, tags=["TextOnly"], slot_data=True)]))
        elif cmd == "ConnectionRefused":
            errors = packet.get("errors", [])
            reason = ("Das Raumpasswort ist falsch oder fehlt." if "InvalidPassword" in errors else
                      "Der Slotname passt nicht zum Archipelago-Raum." if "InvalidSlot" in errors else
                      "Der Archipelago-Server lehnt die Textanmeldung ab. Bitte Serverversion und Slot prüfen.")
            raise ValueError(reason)
        elif cmd == "Connected":
            self.team, self.slot = integer(packet["team"]), integer(packet["slot"])
            self.players = {}
            for key, value in packet["slot_info"].items():
                if isinstance(value, dict):
                    self.players[integer(key)] = dict(name=str(value["name"])[:100], game=str(value["game"])[:200], type=integer(value["type"]))
                else:
                    self.players[integer(key)] = dict(name=str(value[0])[:100], game=str(value[1])[:200], type=integer(value[2]))
            actual = sorted((v["name"], v["game"]) for v in self.players.values() if v["type"] == 1)
            expected = sorted((s["slot"], s["game_name"]) for s in self.expected)
            if self.team != 0 or actual != expected or self.players.get(self.slot, {}).get("name") != self.slot_name:
                raise ValueError("Die Spieler des Servers passen nicht zu dieser Runde. Es wurden keine Befehle gesendet.")
            self.game = self.players[self.slot]["game"]
            slot_data = packet.get("slot_data")
            if isinstance(slot_data, dict) and len(db.dumps(slot_data)) <= 2 * 1024 * 1024:
                self.slot_data = slot_data
            self.missing = set(map(integer, packet.get("missing_locations", [])))
            self.checked = set(map(integer, packet.get("checked_locations", [])))
            self.state = "connected"
            self.error, self.reason = "", "connected"
            self.connected_at, self.next_retry_at, self.retry_attempt = time.time(), None, 0
            self.stable_since = time.monotonic()
            if self.interrupted_at:
                self.note("Textverbindung wiederhergestellt. Empfangsliste und Checks werden synchronisiert; verpasste Itemmeldungen werden nicht rekonstruiert.")
                self.interrupted_at = None
            self.wire.send(db.dumps([{"cmd": "GetDataPackage", "games": sorted({v["game"] for v in self.players.values() if v["type"] == 1})}]))
            self.note(f"Als {self.slot_name} mit Archipelago verbunden. Der Spielclient bleibt unabhängig davon verbunden.")
        elif self.state != "connected":
            return
        elif cmd == "DataPackage":
            for game, content in packet["data"]["games"].items():
                if game not in {p["game"] for p in self.players.values()}:
                    continue
                maps = []
                for field in ("item_name_to_id", "location_name_to_id"):
                    if not isinstance(content[field], dict) or len(content[field]) > 250000:
                        raise ValueError("Der Datenkatalog des Spiels ist zu groß oder ungültig.")
                    maps.append({str(integer(value)): str(name)[:500] for name, value in content[field].items()})
                with connection(self.path) as conn:
                    conn.execute("INSERT OR REPLACE INTO console_packages(build_id,game,items,locations,updated_at) VALUES (?,?,?,?,?)",
                                 (self.build_id, game, db.dumps(maps[0]), db.dumps(maps[1]), time.time()))
        elif cmd == "ReceivedItems":
            index = integer(packet["index"])
            items = [network_item(item) for item in packet["items"]]
            if index == 0:
                self.received = items
                self.items_synced = True
            elif index == len(self.received):
                self.received.extend(items)
            else:
                self.items_synced = False
                self.wire.send('[{"cmd":"Sync"}]')
            if len(self.received) > 250000:
                raise ValueError("Die Empfangsliste überschreitet das unterstützte Limit.")
        elif cmd == "RoomUpdate":
            checks = set(map(integer, packet.get("checked_locations", [])))
            self.checked.update(checks)
            self.missing.difference_update(checks)
        elif cmd == "PrintJSON":
            if packet.get("type") == "ItemSend":
                item = network_item(packet["item"])
                sender, recipient = self.players.get(item["player"]), self.players.get(integer(packet["receiving"]))
                if sender and recipient:
                    payload = dict(type="item", item_id=item["item"], location_id=item["location"],
                                   sender=sender["name"], sender_game=sender["game"], recipient=recipient["name"], recipient_game=recipient["game"])
                    key = hashlib.sha256(db.dumps((self.endpoint["id"], self.team, item, packet["receiving"])).encode()).hexdigest() if item["location"] >= 0 else None
                    record(self.path, self.build_id, None, "items", payload, key, self.endpoint["id"])
            else:
                parts = []
                remaining = 12000
                for part in packet.get("data", [])[:200]:
                    if remaining <= 0:
                        break
                    text, kind = str(part.get("text", ""))[:min(2000,remaining)], part.get("type")
                    remaining -= len(text)
                    if kind == "player_id":
                        parts.append({"text": self.players.get(integer(text), {}).get("name", f"Spieler #{text}")})
                    elif kind in ("item_id", "location_id"):
                        player = self.players.get(integer(part.get("player", self.slot)), {})
                        parts.append({"game": player.get("game", ""), "kind": "items" if kind == "item_id" else "locations", "id": integer(text)})
                    else:
                        parts.append({"text": text})
                # Hints and command replies stay private; only structured ItemSend is shared.
                record(self.path, self.build_id, self.user_id,
                       "chat" if packet.get("type") == "Chat" else "system", {"parts": parts},
                       hosted_id=self.endpoint["id"])
        elif cmd in ("Print", "InvalidPacket"):
            self.note(str(packet.get("text", "Servermeldung"))[:12000], origin='server')

    def handle_command(self, text):
        command, _, argument = text.partition(" ")
        if command in ("/received", "/missing", "/items", "/locations"):
            with connection(self.path) as conn:
                packages = catalog(conn, self.build_id)
            if command == "/received":
                lines = [f"{named(packages,self.game,'items',item['item'])} ← {self.players.get(item['player'],{}).get('name','Archipelago')}"
                         for item in self.received]
            elif command == "/missing":
                lines = [named(packages,self.game,"locations",identifier) for identifier in sorted(self.missing)]
            else:
                lines = sorted(packages.get(self.game, {}).get("items" if command == "/items" else "locations", {}).values())
            lines = [line for line in lines if argument.casefold() in line.casefold()]
            self.note(f"{command}: {len(lines)} Treffer (Serverstand; keine Prüfung des lokalen Spielstands).\n" + "\n".join(lines[:200])
                      + ("\nBitte mit einem Filter eingrenzen." if len(lines) > 200 else ""))
        else:
            if command in ("/hint", "/hint_location", "/status", "/players"):
                text = "!" + command[1:] + (" " + argument if argument else "")
            self.wire.send(db.dumps([{"cmd": "Say", "text": text}]))
            self.note("An Archipelago gesendet: " + text, "sent")

    def close(self):
        self.stop.set()
        self.password = None
        if self.wire:
            self.wire.close()


def key(build_id, user_id):
    return str(config.DB_PATH.resolve()), build_id, user_id


def current(build_id, user_id, token_hash):
    with _lock:
        client = _clients.get(key(build_id, user_id))
        if client and client.token_hash == token_hash:
            client.last_seen = time.monotonic()
            return client
    return None


def start(build, user_id, token_hash, endpoint, slot, password="", secure=None):
    client = Client(config.DB_PATH.resolve(), build, user_id, token_hash, dict(endpoint), slot, password, secure)
    with _lock:
        old = _clients.get(key(build["id"], user_id))
        if old:
            old.close()
            old.thread.join(2)
            if old.thread.is_alive():
                raise ValueError("Die vorherige Textverbindung wird noch beendet. Bitte kurz warten.")
        _clients[key(build["id"], user_id)] = client
        # Bound closed objects and concurrent worker creation to this server process.
        for identity, item in list(_clients.items()):
            if item is not client and not item.thread.is_alive():
                _clients.pop(identity, None)
        if sum(c.thread.is_alive() for c in _clients.values()) >= 32:
            _clients.pop(key(build["id"], user_id), None)
            raise ValueError("Zu viele Textverbindungen. Bitte zuerst eine Verbindung trennen.")
        client.thread.start()
    return client


def stop_all():
    with _lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        client.close()
    for client in clients:
        client.thread.join(5)
