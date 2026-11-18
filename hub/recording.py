"""One managed read-only room connection; SQLite leases survive Hub restarts.

Legacy explicit recordings retain their API. Room credentials stay in memory.
"""
import threading
import time

from . import ap_console, config, db, i18n

LEASE_SECONDS = 20
_thread = None
_lock = threading.Lock()
_stop = threading.Event()
_room_lock = threading.RLock()
PUBLIC_TYPES = ap_console.PUBLIC_TYPES


def migrate():
    with db.transaction() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS console_recordings(
            build_id INTEGER PRIMARY KEY REFERENCES seed_builds(id) ON DELETE CASCADE,
            hosted_id INTEGER NOT NULL REFERENCES hosted_rooms(id) ON DELETE CASCADE,
            actor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            slot TEXT NOT NULL, uuid TEXT NOT NULL, transport TEXT NOT NULL DEFAULT 'auto',
            enabled INTEGER NOT NULL DEFAULT 1, generation INTEGER NOT NULL DEFAULT 1,
            password_required INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'connecting', error TEXT NOT NULL DEFAULT '',
            lease_owner TEXT NOT NULL DEFAULT '', lease_until REAL NOT NULL DEFAULT 0,
            last_contact REAL, next_retry_at REAL, updated_at REAL NOT NULL
        );''')
        if 'automatic' not in {r['name'] for r in conn.execute('PRAGMA table_info(console_recordings)')}:
            conn.execute('ALTER TABLE console_recordings ADD COLUMN automatic INTEGER NOT NULL DEFAULT 0')


def identity(build_id):
    return ap_console.key(build_id, 'recording')


def worker(build_id):
    with ap_console._lock:
        return ap_console._clients.get(identity(build_id))


def permitted(conn, row):
    build = conn.execute('''SELECT b.*,s.created_by,u.is_admin FROM seed_builds b
        JOIN sessions s ON s.id=b.session_id JOIN users u ON u.id=? WHERE b.id=?''',
        (row['actor_id'],row['build_id'])).fetchone()
    endpoint = conn.execute('SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1',
                            (row['build_id'],)).fetchone()
    if not build or build['status']!='succeeded' or build['completed_at'] or not endpoint or endpoint['id']!=row['hosted_id']:
        return False
    snapshot = db.loads(build['snapshot'])
    automatic = bool(dict(row).get('automatic'))
    return bool(not snapshot.get('race') and (build['created_by']==row['actor_id'] or build['is_admin'])
                and any((automatic or s['player_id']==row['actor_id']) and s['slot']==row['slot']
                        for s in snapshot.get('slots',[])))


class Recorder(ap_console.Client):
    def __init__(self, row, build, endpoint, password):
        super().__init__(config.DB_PATH.resolve(),build,row['actor_id'],None,dict(endpoint),row['slot'],password,
                         {'auto':None,'ws':False,'wss':True}[row['transport']])
        self.generation = row['generation']
        self.uuid = row['uuid']
        self.request_slot_data = False
        self.automatic = bool(row['automatic'])
        if self.automatic:
            self.user_id = next(s['player_id'] for s in self.expected if s['slot']==self.slot_name)
        self.thread.name = f"ap-recording-{self.build_id}"

    def authorized(self, conn):
        row = conn.execute('SELECT * FROM console_recordings WHERE build_id=?',(self.build_id,)).fetchone()
        if not row or not row['enabled'] or row['generation']!=self.generation or row['lease_owner']!=ap_console.PROCESS_ID or not permitted(conn,row):
            return False
        conn.execute('UPDATE console_recordings SET lease_until=? WHERE build_id=? AND generation=?',
                     (time.time()+LEASE_SECONDS,self.build_id,self.generation))
        return True

    def persist(self):
        with ap_console.connection(self.path) as conn:
            conn.execute('''UPDATE console_recordings SET state=?,error=?,last_contact=?,next_retry_at=?,
                updated_at=? WHERE build_id=? AND generation=? AND lease_owner=? AND enabled=1''',
                (self.state,self.error,self.last_contact,self.next_retry_at,time.time(),self.build_id,self.generation,ap_console.PROCESS_ID))

    def stream_state(self):
        super().stream_state()
        self.persist()

    def note(self, text, kind='system', origin='hub', values=None):
        # Recording has no chat/command surface and never publishes private replies.
        if origin=='hub' and kind=='system':
            if self.automatic and text.startswith('Als '):
                text='Gemeinsame Liveverbindung hergestellt. Öffentliche Meldungen werden für alle gespeichert.'
            ap_console.record(self.path,self.build_id,None,kind,dict(text=text,origin='hub'),hosted_id=self.endpoint['id'])

    def packet(self, packet):
        cmd = packet.get('cmd')
        if self.automatic and cmd=='PrintJSON' and packet.get('type') in PUBLIC_TYPES:
            # Only explicitly public protocol types are shared. Hints, prints and
            # command replies arriving at the service slot remain private.
            self.public_event(packet)
            return
        if cmd=='RoomInfo':
            seed=str(packet.get('seed_name',''))
            if self.expected_seed and seed not in (self.expected_seed,self.expected_seed.removeprefix('AP_')):
                raise ValueError('Der Server gehört zu einem anderen Seed. Bitte die gespeicherte Verbindung prüfen.')
            with ap_console.connection(self.path) as conn:
                conn.execute('UPDATE console_recordings SET password_required=? WHERE build_id=? AND generation=?',
                             (int(bool(packet.get('password'))),self.build_id,self.generation))
            if packet.get('password') and not self.password:
                raise ValueError('Der Host muss das Raumpasswort für die gemeinsame Liveansicht hinterlegen.' if self.automatic else
                                 'Für die Rundenaufzeichnung das Raumpasswort erneut eingeben. Es wird nicht gespeichert.')
        if cmd in ('RoomInfo','Connected','ConnectionRefused','ReceivedItems','DataPackage','RoomUpdate') or (cmd=='PrintJSON' and packet.get('type')=='ItemSend'):
            super().packet(packet)

    def public_event(self, packet):
        if self.state != 'connected':
            return
        parts = self.message_parts(packet)
        ap_console.record(self.path,self.build_id,None,
                          'chat' if packet['type'] in ('Chat','ServerChat') else 'system',
                          dict(parts=parts,public_type=packet['type']),hosted_id=self.endpoint['id'])

    def handle_command(self, text):
        raise ValueError('Die Rundenaufzeichnung kann keine Chatnachrichten oder Befehle senden.')


def enable(build, endpoint, actor, slot, password='', transport='auto'):
    now = time.time()
    with db.transaction() as conn:
        conn.execute('BEGIN IMMEDIATE')
        candidate = dict(build_id=build['id'],hosted_id=endpoint['id'],actor_id=actor,slot=slot)
        if not permitted(conn,candidate):
            raise ValueError('Die Rundenaufzeichnung benötigt einen eigenen Slot des Hosts in dieser laufenden Runde.')
        existing = conn.execute('SELECT * FROM console_recordings WHERE build_id=?',(build['id'],)).fetchone()
        if existing and existing['enabled'] and existing['lease_until']>now:
            active = worker(build['id'])
            if active and active.thread.is_alive() and active.state not in ('action_required','disconnected'):
                if active.user_id!=actor or active.slot_name!=slot:
                    raise ValueError('Bitte zuerst die bestehende Rundenaufzeichnung beenden.')
                return active
            if existing['lease_owner']!=ap_console.PROCESS_ID:
                raise ValueError('Die Rundenaufzeichnung läuft bereits in einem anderen Hub-Prozess.')
        conn.execute('''INSERT INTO console_recordings(build_id,hosted_id,actor_id,slot,uuid,transport,lease_owner,lease_until,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(build_id) DO UPDATE SET hosted_id=excluded.hosted_id,
            actor_id=excluded.actor_id,slot=excluded.slot,transport=excluded.transport,enabled=1,
            generation=console_recordings.generation+1,state='connecting',error='',password_required=0,
            lease_owner=excluded.lease_owner,lease_until=excluded.lease_until,updated_at=excluded.updated_at''',
            (build['id'],endpoint['id'],actor,slot,ap_console.secrets.token_hex(16),transport,ap_console.PROCESS_ID,now+LEASE_SECONDS,now))
        row = conn.execute('SELECT * FROM console_recordings WHERE build_id=?',(build['id'],)).fetchone()
    return ap_console.launch(Recorder(row,build,endpoint,password),identity(build['id']))


def disable(build_id):
    with db.transaction() as conn:
        conn.execute("UPDATE console_recordings SET enabled=0,generation=generation+1,state='disconnected',error='',lease_until=0 WHERE build_id=?",(build_id,))
    current = worker(build_id)
    if current:
        current.close()


def ensure(build, endpoint, password=None, transport='auto', force=False):
    """Register/claim one room reader, without tying it to a browser login.

    The AP protocol requires a real slot for TextOnly clients. The service uses
    a seed-verified slot solely to read; user commands never reach this client.
    """
    with _room_lock:
        now = time.time()
        active = worker(build['id'])
        with db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            parent = conn.execute('SELECT created_by FROM sessions WHERE id=?',(build['session_id'],)).fetchone()
            slots = db.loads(build['snapshot']).get('slots',[])
            if not parent or not slots or build['completed_at'] or build['status']!='succeeded' or db.loads(build['snapshot']).get('race'):
                return None
            row = conn.execute('SELECT * FROM console_recordings WHERE build_id=?',(build['id'],)).fetchone()
            if row and row['lease_owner']!=ap_console.PROCESS_ID and row['lease_until']>now:
                return None
            changed = not row or row['hosted_id']!=endpoint['id'] or not row['automatic']
            if row and not changed and not force:
                if not row['enabled']:
                    return None
                if active and active.thread.is_alive():
                    return active
                if row['state']=='action_required':
                    return None
                if not active and row['lease_until']>now:
                    return None
            if changed or force:
                # Credentials for a previous room are never carried across endpoints.
                conn.execute('''INSERT INTO console_recordings(build_id,hosted_id,actor_id,slot,uuid,transport,automatic,updated_at)
                    VALUES (?,?,?,?,?,?,1,?) ON CONFLICT(build_id) DO UPDATE SET hosted_id=excluded.hosted_id,
                    actor_id=excluded.actor_id,slot=excluded.slot,transport=excluded.transport,automatic=1,
                    enabled=1,generation=console_recordings.generation+1,password_required=0,
                    state='connecting',error='',lease_owner='',lease_until=0,updated_at=excluded.updated_at''',
                    (build['id'],endpoint['id'],parent['created_by'],slots[0]['slot'],ap_console.secrets.token_hex(16),transport,now))
                row = conn.execute('SELECT * FROM console_recordings WHERE build_id=?',(build['id'],)).fetchone()
            if not permitted(conn,row):
                return None
            if row['password_required'] and password is None:
                conn.execute("UPDATE console_recordings SET state='action_required',error=?,lease_until=0 WHERE build_id=?",
                             ('Der Host muss das Raumpasswort für die gemeinsame Liveansicht hinterlegen.',build['id']))
                return None
            conn.execute("UPDATE console_recordings SET state='connecting',lease_owner=?,lease_until=?,updated_at=? WHERE build_id=?",
                         (ap_console.PROCESS_ID,now+LEASE_SECONDS,now,build['id']))
            row = conn.execute('SELECT * FROM console_recordings WHERE build_id=?',(build['id'],)).fetchone()
        return ap_console.launch(Recorder(row,build,endpoint,password or ''),identity(build['id']))


def resume_due(automatic=False):
    """Resume leased readers; the supervisor also registers configured rounds."""
    if automatic:
        with db.transaction() as conn:
            builds = conn.execute("SELECT * FROM seed_builds WHERE status='succeeded' AND completed_at IS NULL").fetchall()
            endpoints = {row['build_id']:row for row in conn.execute('''SELECT * FROM hosted_rooms h WHERE
                h.id=(SELECT MAX(latest.id) FROM hosted_rooms latest WHERE latest.build_id=h.build_id)''')}
        for build in builds:
            if build['id'] in endpoints:
                try:
                    ensure(build,endpoints[build['id']])
                except ValueError:
                    continue  # Bounded pool; lease prevents a busy retry loop.
    with db.transaction() as conn:
        rows = conn.execute("SELECT * FROM console_recordings WHERE enabled=1 AND state!='action_required'").fetchall()
    for previous in rows:
        current = worker(previous['build_id'])
        if current and current.thread.is_alive():
            continue
        now = time.time()
        with db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM console_recordings WHERE build_id=?',(previous['build_id'],)).fetchone()
            if not row or not row['enabled'] or row['state']=='action_required' or (row['lease_owner']!=ap_console.PROCESS_ID and row['lease_until']>now):
                continue
            error = ('Die Rundenaufzeichnung wurde angehalten. Eigenen Slot, Berechtigung und Raum prüfen.' if not permitted(conn,row) else
                     'Für die Rundenaufzeichnung das Raumpasswort erneut eingeben. Es wird nicht gespeichert.' if row['password_required'] else '')
            if error:
                conn.execute("UPDATE console_recordings SET state='action_required',error=?,lease_until=0 WHERE build_id=?",(error,row['build_id']))
                continue
            conn.execute("UPDATE console_recordings SET state='connecting',lease_owner=?,lease_until=?,updated_at=? WHERE build_id=?",
                         (ap_console.PROCESS_ID,now+LEASE_SECONDS,now,row['build_id']))
            build = conn.execute('SELECT * FROM seed_builds WHERE id=?',(row['build_id'],)).fetchone()
            endpoint = conn.execute('SELECT * FROM hosted_rooms WHERE id=?',(row['hosted_id'],)).fetchone()
        try:
            ap_console.launch(Recorder(row,build,endpoint,''),identity(row['build_id']))
        except ValueError:
            # Bounded worker pool: leave the lease to expire rather than busy-loop.
            continue


def start_supervisor():
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return
        _stop.clear()
        def run():
            while not _stop.is_set():
                try:
                    resume_due(automatic=True)
                except Exception:
                    ap_console._state_logger.exception('Recording supervisor failed')
                _stop.wait(5)
        _thread = threading.Thread(target=run,daemon=True,name='ap-recording-supervisor')
        _thread.start()


def status(build_id, endpoint):
    conn = db.get()
    row = conn.execute('SELECT * FROM console_recordings WHERE build_id=?',(build_id,)).fetchone()
    hosted_id = endpoint['id'] if endpoint else -1
    last = conn.execute("SELECT MAX(observed_at) AS at FROM console_events WHERE build_id=? AND hosted_id=? AND kind='items' AND user_id IS NULL",(build_id,hosted_id)).fetchone()['at']
    started = conn.execute('SELECT 1 FROM console_streams WHERE build_id=? AND hosted_id=? AND connected_at IS NOT NULL',(build_id,hosted_id)).fetchone()
    active = conn.execute("SELECT 1 FROM console_streams WHERE build_id=? AND hosted_id=? AND state='connected' AND heartbeat>?",(build_id,hosted_id,max(ap_console.PROCESS_STARTED,time.time()-15))).fetchone()
    current = worker(build_id)
    state = current.state if current and current.thread.is_alive() else row['state'] if row else 'not_started'
    if row and row['enabled'] and not active and not (current and current.thread.is_alive()) and state in ('connected','authenticating'):
        state='reconnecting'
    return dict(state='active' if active else 'interrupted' if started else 'not_started',last_event=last,
                enabled=bool(row and row['enabled']),console_state=state,
                automatic=bool(row and row['automatic']),
                error=i18n.t(row['error']) if row else '',password_required=bool(row and row['password_required']))
