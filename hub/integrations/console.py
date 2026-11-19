"""Bounded Archipelago TextOnly clients. No game checks, cheats, or remote code."""
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

from hub import config, db, live_store
from hub.integrations.console_commands import COMMANDS, SERVER_COMMANDS

from hub.services.console_journal import migrate, connection, record, catalog, named, render_payload, events

PROCESS_ID = secrets.token_hex(16)
PROCESS_STARTED = time.time()
MAX_FRAME = 16 * 1024 * 1024
IDLE_SECONDS = 30 * 60  # Historical constant; browser inactivity no longer ends a connection.
COMMAND_IDLE_SECONDS = 120
RETRY_BASE = 2
RETRY_MAX = 60
GUARD_SECONDS = 5
PING_SECONDS = 25
PUBLIC_TYPES = frozenset(('Chat','ServerChat','Join','Part','TagsChanged','Goal','Countdown','Release','Collect','ItemCheat'))
_clients = {}
_lock = threading.RLock()
_wire_logger = logging.getLogger("hub.ap_console.wire")
_wire_logger.setLevel(logging.WARNING)  # Never log Connect frames containing a room password.
_state_logger = logging.getLogger("hub.ap_console.state")


class PortChanged(OSError):
    """An API-confirmed port rotation for the same explicitly connected room."""


def open_socket(host, port, secure, *, timeout=8):
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
        raw.settimeout(timeout)
        raw.connect(address)
        # A supplied socket is not reset by websockets 13.x for plain WS.
        # Keep the TCP deadline separate from the lifetime of the reader thread.
        raw.settimeout(None)
        target = f"[{host}]" if ":" in host else host
        return connect(f"{'wss' if secure else 'ws'}://{target}:{port}", sock=raw,
                       open_timeout=timeout, close_timeout=2, max_size=MAX_FRAME, compression="deflate", logger=_wire_logger)
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


def matches_seed(expected, actual):
    return not expected or actual in (expected, expected.removeprefix('AP_'))


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
        self.stream_id = secrets.token_hex(16)
        self.stop = threading.Event()
        self.outbox = queue.Queue(maxsize=30)
        self.wire = None
        self.team, self.slot, self.game = None, None, ""
        self.players, self.received, self.missing, self.checked = {}, [], set(), set()
        self.slot_data = None
        self.request_slot_data = True
        self.managed = False
        self.catalog_ready = False
        self.sync_pending = False
        self.items_synced = False
        self.command_lock = threading.Lock()
        self.last_command = time.monotonic()
        self.thread = threading.Thread(target=self.run, daemon=True, name=f"ap-console-{self.build_id}-{user_id}")

    def note(self, text, kind="system", origin="hub", values=None):
        if self.managed and kind=='system' and origin=='hub' and text.startswith('Als '):
            return  # Automatic authentication is not a second user-facing step.
        payload = dict(text=text,origin=origin,actor_slot=self.slot_name)
        if values is not None:
            payload['values']=values
        record(self.path, self.build_id, self.user_id, kind, payload, hosted_id=self.endpoint["id"])

    def target(self, conn):
        endpoint = conn.execute("SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1", (self.build_id,)).fetchone()
        if not endpoint or any(endpoint[key] != self.endpoint[key] for key in ("id", "host", "room_url")):
            return None
        linked = conn.execute("SELECT * FROM live_rooms WHERE build_id=? AND active=1", (self.build_id,)).fetchone()
        if linked and linked["auto_host"]:
            if not live_store.official_address(endpoint["room_url"], endpoint["host"], linked["room_id"]):
                return None
        elif endpoint["port"] != self.endpoint["port"]:
            return None
        return endpoint

    def sync_port(self):
        """Only the socket's worker switches ports; commands never cross sockets."""
        with connection(self.path) as conn:
            target = self.target(conn)
        if not target or target["port"] == self.endpoint["port"]:
            return False
        self.endpoint["port"] = target["port"]
        self.error = ""
        self.failure_streak = self.retry_attempt = 0
        self.note("Archipelago hat einen neuen Port gemeldet. Die Textkonsole verbindet sich automatisch neu.")
        return True

    def valid(self):
        if self.managed:
            with self.command_lock:
                if time.monotonic() - self.last_command > COMMAND_IDLE_SECONDS and self.outbox.empty():
                    self.stop.set()
                if self.stop.is_set():
                    return False
        with connection(self.path) as conn:
            row = conn.execute("SELECT completed_at,snapshot FROM seed_builds WHERE id=?", (self.build_id,)).fetchone()
            endpoint = self.target(conn)
            return bool(self.authorized(conn) and row and not row["completed_at"] and not db.loads(row["snapshot"]).get("race")
                        and endpoint)

    def authorized(self, conn):
        authorized = conn.execute("""SELECT 1 FROM auth_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.user_id=? AND s.expires_at>?""",
                                  (self.token_hash, self.user_id, time.time())).fetchone()
        membership = conn.execute("""SELECT 1 FROM seed_builds b JOIN sessions l ON l.id=b.session_id
                JOIN users u ON u.id=? WHERE b.id=? AND (u.is_admin=1 OR l.created_by=u.id
                OR EXISTS (SELECT 1 FROM lobby_members lm WHERE lm.session_id=l.id AND lm.user_id=u.id)
                OR EXISTS (SELECT 1 FROM entries e WHERE e.session_id=l.id AND e.user_id=u.id))""",
                                      (self.user_id, self.build_id)).fetchone()
        return bool(authorized and membership)

    def stream_state(self):
        """Persist coverage transitions atomically across all explicit readers."""
        if self.managed:
            return
        now = time.time()
        fresh_after = max(PROCESS_STARTED,now-15)
        with connection(self.path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope = (self.build_id, self.endpoint['id'])
            active_sql = "SELECT 1 FROM console_streams WHERE build_id=? AND hosted_id=? AND state='connected' AND heartbeat>?"
            before = conn.execute(active_sql, (*scope, fresh_after)).fetchone()
            previous = conn.execute('SELECT 1 FROM console_streams WHERE build_id=? AND hosted_id=? AND connected_at IS NOT NULL', scope).fetchone()
            conn.execute('''INSERT INTO console_streams(id,build_id,hosted_id,state,heartbeat,connected_at,last_contact)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,
                heartbeat=excluded.heartbeat,connected_at=COALESCE(console_streams.connected_at,excluded.connected_at),
                last_contact=excluded.last_contact''',
                (self.stream_id,*scope,self.state,now,self.connected_at,self.last_contact))
            after = conn.execute(active_sql, (*scope, fresh_after)).fetchone()
            message = None
            if before and not after:
                message = 'Itemaufzeichnung unterbrochen. Während der Lücke können Sendungen fehlen.'
            elif not before and after:
                message = ('Itemaufzeichnung fortgesetzt. Eine mögliche Lücke ist nicht vollständig rekonstruierbar.' if previous else
                           'Itemaufzeichnung gestartet. Frühere Sendungen sind möglicherweise unvollständig.')
            if message:
                conn.execute('''INSERT INTO console_events(build_id,kind,payload,observed_at,hosted_id)
                    VALUES (?,'system',?,?,?)''',
                    (self.build_id,db.dumps(dict(text=message,origin='hub')),now,self.endpoint['id']))

    def run(self):
        """One worker owns all sockets, retries and commands for this explicit login."""
        try:
            while not self.stop.is_set() and self.valid():
                self.items_synced = False
                self.catalog_ready = False
                self.sync_pending = False
                self.received, self.players, self.slot_data = [], {}, None
                try:
                    self.sync_port()
                    self.wire, self.transport = connect_transport(self.endpoint["host"], self.endpoint["port"], self.secure)
                    if self.stop.is_set() or not self.valid():
                        break
                    if self.sync_port():
                        raise PortChanged()
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
                    self.error = "" if isinstance(exc, PortChanged) else connection_error(exc)
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
                    if self.sync_port():
                        self.next_retry_at = time.time()
                        break
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
        self.observe_progression()
        try:
            self.stream_state()
        except sqlite3.Error:
            pass  # A deleted build/endpoint must still let its worker stop.
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
                if self.sync_port():
                    raise PortChanged()
                self.stream_state()
                last_guard = now
            if self.state != "connected" and now - started > 20:
                raise TimeoutError("handshake timeout")
            while self.state == "connected" and not self.outbox.empty():
                if self.managed and not (self.items_synced and self.catalog_ready):
                    break  # Local commands must not report a partial initial inventory.
                if not self.valid():
                    return
                if self.sync_port():
                    raise PortChanged()
                self.handle_command(self.outbox.get_nowait())
            if now - last_ping > PING_SECONDS:
                if not self.wire.ping().wait(5):
                    raise TimeoutError("ping timeout")
                self.last_contact = time.time()
                self.observe_progression()
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
            if not matches_seed(self.expected_seed, seed):
                raise ValueError("Der Server gehört zu einem anderen Seed. Bitte die gespeicherte Verbindung prüfen.")
            self.wire.send(db.dumps([dict(cmd="Connect", password=self.password or None, game="", name=self.slot_name,
                                         uuid=self.uuid, version={"major":0,"minor":6,"build":8,"class":"Version"},
                                         items_handling=7, tags=["TextOnly"], slot_data=self.request_slot_data)]))
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
            self.stream_state()
            if self.interrupted_at:
                self.note("Textverbindung wiederhergestellt. Empfangsliste und Checks werden synchronisiert. Belegte Empfänge werden ergänzt; ein vollständiger Verlauf lässt sich daraus nicht rekonstruieren.")
                self.interrupted_at = None
            commands=[{"cmd":"GetDataPackage","games":sorted({v['game'] for v in self.players.values() if v['type']==1})}]
            if self.managed:
                # AP suppresses empty ReceivedItems, including for Sync. The
                # following DataPackage response is an ordered server barrier.
                self.sync_pending = True
                commands.insert(0,dict(cmd='Sync'))
            self.wire.send(db.dumps(commands))
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
                    conn.execute("""INSERT INTO console_packages(build_id,game,items,locations,updated_at)
                        VALUES (?,?,?,?,?) ON CONFLICT(build_id,game) DO UPDATE SET
                        items=excluded.items,locations=excluded.locations,updated_at=excluded.updated_at
                        WHERE console_packages.items<>excluded.items OR console_packages.locations<>excluded.locations""",
                                 (self.build_id, game, db.dumps(maps[0]), db.dumps(maps[1]), time.time()))
            self.catalog_ready = self.catalog_ready or self.game in packet['data']['games']
            if self.managed and self.sync_pending and self.catalog_ready:
                self.items_synced = True
                self.sync_pending = False
                self.observe_progression()
        elif cmd == "ReceivedItems":
            index = integer(packet["index"])
            items = [network_item(item) for item in packet["items"]]
            if index<0 or len(items)>250000 or (index and len(self.received)+len(items)>250000):
                raise ValueError("Die Empfangsliste überschreitet das unterstützte Limit.")
            if index == 0:
                self.received = items
                self.items_synced = True
                self.confirm_receipts(items, 0)
            elif index == len(self.received):
                self.received.extend(items)
                self.confirm_receipts(items, index)
            else:
                self.items_synced = False
                self.wire.send('[{"cmd":"Sync"}]')
            if len(self.received) > 250000:
                raise ValueError("Die Empfangsliste überschreitet das unterstützte Limit.")
            self.observe_progression()
        elif cmd == "RoomUpdate":
            checks = set(map(integer, packet.get("checked_locations", [])))
            self.checked.update(checks)
            self.missing.difference_update(checks)
            self.observe_progression()
        elif cmd == "PrintJSON":
            if packet.get("type") == "ItemSend":
                if self.managed:
                    return
                item = network_item(packet["item"])
                self.delivery(item, integer(packet['receiving']), 'live')
            else:
                if self.managed and packet.get('type') in PUBLIC_TYPES:
                    return  # The sole room reader journals public events once.
                parts = self.message_parts(packet)
                # Hints and command replies stay private; only structured ItemSend is shared.
                record(self.path, self.build_id, self.user_id,
                       "chat" if packet.get("type") == "Chat" else "system", {"parts": parts, "actor_slot": self.slot_name,
                       "message_type":str(packet.get('type',''))[:64]},
                       hosted_id=self.endpoint["id"])
        elif cmd in ("Print", "InvalidPacket"):
            self.note(str(packet.get("text", "Servermeldung"))[:12000], origin='server')

    def message_parts(self, packet):
        parts, remaining = [], 12000
        for part in packet.get('data', [])[:200]:
            if remaining <= 0:
                break
            text, kind = str(part.get('text', ''))[:min(2000, remaining)], part.get('type')
            remaining -= len(text)
            if kind == 'player_id':
                player = self.players.get(integer(text))
                parts.append(dict(text=player['name'],player_slot=player['name']) if player else dict(fallback_player=integer(text)))
            elif kind in ('item_id','location_id'):
                player = self.players.get(integer(part.get('player',self.slot)),{})
                parts.append(dict(game=player.get('game',''),kind='items' if kind=='item_id' else 'locations',id=integer(text)))
            else:
                parts.append(dict(text=text))
        return parts

    def observe_progression(self):
        try:
            from hub.progression import observe
            observe(self)
        except Exception:
            _state_logger.warning('Optional inventory snapshot could not be saved.')

    def delivery(self, item, receiving, source, receipt_index=None, transaction=None):
        sender, recipient = self.players.get(item['player']), self.players.get(receiving)
        # Negative locations represent synthetic/start items without a check identity.
        if item['location'] < 0 or not sender or not recipient:
            return
        payload = dict(type='item',item_id=item['item'],location_id=item['location'],
                       sender=sender['name'],sender_game=sender['game'],recipient=recipient['name'],
                       recipient_game=recipient['game'],source=source,receipt_index=receipt_index)
        identity = hashlib.sha256(db.dumps((self.endpoint['id'],self.team,item['player'],item['location'],receiving,item['item'])).encode()).hexdigest()
        def insert(conn):
            # Older journals used flags in their hashes. Flags classify an item;
            # they aren't another delivery. Keep those rows and recognize them.
            existing=conn.execute('''SELECT 1 FROM console_events WHERE build_id=? AND hosted_id=? AND kind='items'
                AND json_extract(payload,'$.sender')=? AND json_extract(payload,'$.recipient')=?
                AND json_extract(payload,'$.location_id')=? AND json_extract(payload,'$.item_id')=?''',
                (self.build_id,self.endpoint['id'],payload['sender'],payload['recipient'],item['location'],item['item'])).fetchone()
            if not existing:
                record(self.path,self.build_id,None,'items',payload,identity,self.endpoint['id'],transaction=conn)
        if transaction is not None:
            insert(transaction)
        else:
            with connection(self.path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                insert(conn)

    def confirm_receipts(self, items, index):
        if self.managed:
            return
        with connection(self.path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            for offset,item in enumerate(items):
                self.delivery(item,self.slot,'received_items',index+offset,transaction=conn)

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
            record(self.path,self.build_id,self.user_id,'system',dict(origin='hub',
                   text='{v0}: {v1} Treffer (Serverstand; keine Prüfung des lokalen Spielstands).',actor_slot=self.slot_name,
                   values=dict(v0=command,v1=len(lines)),number_values=['v1'],lines=lines[:200],truncated=len(lines)>200),
                   hosted_id=self.endpoint['id'])
        else:
            if command in ("/hint", "/hint_location", "/status", "/players"):
                text = "!" + command[1:] + (" " + argument if argument else "")
            self.wire.send(db.dumps([{"cmd": "Say", "text": text}]))
            if not self.managed or text.startswith('!'):
                self.note('An Archipelago gesendet: {v0}', 'sent', values=dict(v0=text))

    def submit(self, text):
        with self.command_lock:
            if self.stop.is_set() or self.state not in ('connected', 'connecting', 'authenticating'):
                return False
            self.outbox.put_nowait(text)
            self.last_command = time.monotonic()
            return True

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
            return client
    return None


def start(build, user_id, token_hash, endpoint, slot, password="", secure=None, *, managed=False):
    with _lock:
        if managed:
            old = _clients.get(key(build['id'],user_id))
            if old and old.managed and old.token_hash==token_hash and old.slot_name==slot and old.endpoint['id']==endpoint['id'] and old.secure==secure and old.password==password and old.thread.is_alive() and not old.stop.is_set() and old.state in ('connecting','authenticating','connected','reconnecting','temporarily_unavailable'):
                return old
        client = Client(config.DB_PATH.resolve(), build, user_id, token_hash, dict(endpoint), slot, password, secure)
        client.managed = managed
        return launch(client, key(build['id'],user_id))


def launch(client, identity):
    with _lock:
        old = _clients.get(identity)
        if old:
            old.close()
            old.thread.join(2)
            if old.thread.is_alive():
                raise ValueError("Die vorherige Textverbindung wird noch beendet. Bitte kurz warten.")
        _clients[identity] = client
        # Bound closed objects and concurrent worker creation to this server process.
        for existing_identity, item in list(_clients.items()):
            if item is not client and not item.thread.is_alive():
                _clients.pop(existing_identity, None)
        if sum(c.thread.is_alive() for c in _clients.values()) >= 32:
            _clients.pop(identity, None)
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
