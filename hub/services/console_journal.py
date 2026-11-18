"""Persistent console events, pagination and translated display."""
from contextlib import contextmanager
import sqlite3
import time
from hub import db, i18n
from hub.integrations.console_commands import COMMANDS

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
        CREATE TABLE IF NOT EXISTS console_streams(
            id TEXT PRIMARY KEY, build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
            hosted_id INTEGER NOT NULL REFERENCES hosted_rooms(id) ON DELETE CASCADE,
            state TEXT NOT NULL, heartbeat REAL NOT NULL, connected_at REAL, last_contact REAL
        );
        CREATE INDEX IF NOT EXISTS console_stream_scope ON console_streams(build_id,hosted_id,state);
        """)
        if "hosted_id" not in {r["name"] for r in conn.execute("PRAGMA table_info(console_events)")}:
            conn.execute("ALTER TABLE console_events ADD COLUMN hosted_id INTEGER REFERENCES hosted_rooms(id) ON DELETE CASCADE")
        if "updated_at" not in {r["name"] for r in conn.execute("PRAGMA table_info(console_packages)")}:
            conn.execute("ALTER TABLE console_packages ADD COLUMN updated_at REAL NOT NULL DEFAULT 0")
        conn.execute('''CREATE INDEX IF NOT EXISTS console_delivery_identity ON console_events(
            build_id,hosted_id,kind,json_extract(payload,'$.sender'),json_extract(payload,'$.recipient'),
            json_extract(payload,'$.location_id'),json_extract(payload,'$.item_id'))''')


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


def record(path, build_id, user_id, kind, payload, key=None, hosted_id=None, *, transaction=None):
    if transaction is None:
        with connection(path) as conn:
            return record(path,build_id,user_id,kind,payload,key,hosted_id,transaction=conn)
    # Pagination bounds HTTP responses, not the persistent event history.
    return transaction.execute("INSERT OR IGNORE INTO console_events(build_id,user_id,kind,payload,observed_at,event_key,hosted_id) VALUES (?,?,?,?,?,?,?)",
                               (build_id,user_id,kind,db.dumps(payload),time.time(),key,hosted_id)).rowcount


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
                       else i18n.t('Spieler #{v0}',v0=part['fallback_player']) if 'fallback_player' in part
                       else part["text"] for part in payload["parts"])[:12000]
    return payload.get("text", "")


def identities(build_id):
    conn = db.get()
    build = conn.execute('SELECT snapshot FROM seed_builds WHERE id=?',(build_id,)).fetchone()
    users = {row['id']:row['username'] for row in conn.execute('SELECT id,username FROM users')}
    return [dict(slot=slot['slot'],game=slot['game_name'],user_id=slot.get('player_id'),
                 username=users.get(slot.get('player_id'),''),anchor=f'console-player-{index}')
            for index,slot in enumerate(db.loads(build['snapshot']).get('slots',[]) if build else [])]


def events(build_id, user_id, after=0, kind="all", before=0, *, players=None):
    conn = db.get()
    packages = catalog(conn, build_id)
    args = [build_id, user_id]
    scope = "build_id=? AND (user_id IS NULL OR user_id=?)"
    endpoint = conn.execute("SELECT id FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1", (build_id,)).fetchone()
    scope += " AND (hosted_id IS NULL OR hosted_id=?)"
    args.append(endpoint["id"] if endpoint else -1)
    players = identities(build_id) if players is None else players
    own=[player['slot'] for player in players if player['user_id']==user_id]
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
            if payload.get('type')=='help':
                text='\n'.join(command+' – '+i18n.t(description) for command,description in COMMANDS)
            elif 'values' in payload:
                values=dict(payload['values'])
                for name in payload.get('number_values',[]):
                    values[name]=i18n.format_number(values[name])
                text=i18n.t(payload['text'],**values)
                if payload.get('lines'):
                    text+='\n'+'\n'.join(payload['lines'])
                if payload.get('truncated'):
                    text+='\n'+i18n.t('Bitte mit einem Filter eingrenzen.')
            else:
                first,separator,rest=text.partition('\n')
                text=i18n.t(first)+(separator+rest if separator else '')
        entry = dict(id=row["id"], kind=row["kind"], at=row["observed_at"], text=text,
                     visibility="team" if row["user_id"] is None else "personal")
        if row['user_id'] is not None:
            actor = next((p for p in players if p['user_id']==row['user_id'] and p['slot']==payload.get('actor_slot')),None)
            entry['actor'] = actor
        if payload.get('message_type'):
            entry['packet_type']=payload['message_type']
        if payload.get("type") == "item":
            entry['source'] = payload.get('source', 'live')
            entry['receipt_index'] = payload.get('receipt_index')
            entry['for_me'],entry['from_me']=payload['recipient'] in own,payload['sender'] in own
            entry["delivery"] = dict(item_id=payload["item_id"], item=named(packages,payload["recipient_game"],"items",payload["item_id"]),
                sender=dict(name=payload["sender"],game=payload["sender_game"]),
                recipient=dict(name=payload["recipient"],game=payload["recipient_game"]),
                location=dict(id=payload["location_id"],name=named(packages,payload["sender_game"],"locations",payload["location_id"])))
        result.append(entry)
    return result
