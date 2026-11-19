"""Seed finder, observed inventory and bounded reconstruction jobs. No AP imports."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

from progression_model import digest
from progression.engine import ANALYSIS_VERSION
from hub import ap_bridge, config, db

from hub.services.item_finder import placements, manifest, observations, find

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='progression')
_lock = threading.Lock()
_futures = set()
JOB_TIMEOUT = 90


def migrate():
    with db.transaction() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS progression_live(
          build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
          slot_name TEXT NOT NULL, hosted_id INTEGER NOT NULL REFERENCES hosted_rooms(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          payload TEXT NOT NULL, observed_at REAL NOT NULL,
          PRIMARY KEY(build_id,slot_name));
        CREATE TABLE IF NOT EXISTS progression_jobs(
          id INTEGER PRIMARY KEY, build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          slot_name TEXT NOT NULL, signature TEXT NOT NULL, state TEXT NOT NULL,
          result TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL, finished_at REAL,
          UNIQUE(build_id,user_id,slot_name,signature));
        ''')


def observe(client):
    """Called only by the existing, identity-checked TextOnly receiver thread."""
    from hub.ap_console import connection
    if not client.items_synced or client.state != 'connected':
        last_observation = getattr(client, 'progression_observed_at', None)
        if last_observation is None:
            return
        with connection(client.path) as conn:
            conn.execute("""UPDATE progression_live SET payload=json_set(payload,'$.synchronized',0)
                WHERE build_id=? AND slot_name=? AND hosted_id=? AND observed_at=?""",
                         (client.build_id,client.slot_name,client.endpoint['id'],last_observation))
        client.progression_observed_at = None
        return
    payload = dict(slot=client.slot, team=client.team, received=list(client.received),
                   checked=sorted(client.checked), missing=sorted(client.missing),synchronized=True)
    observed_at = time.time()
    with connection(client.path) as conn:
        conn.execute('''INSERT OR REPLACE INTO progression_live(build_id,slot_name,hosted_id,user_id,payload,observed_at)
                     VALUES (?,?,?,?,?,?)''', (client.build_id,client.slot_name,client.endpoint['id'],client.user_id,
                                               db.dumps(payload),observed_at))
    client.progression_observed_at = observed_at


def run_worker(request):
    """One isolated process, hard time/memory caps, bounded output via files."""
    environment = {k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','HOME','USERPROFILE','APPDATA','LOCALAPPDATA') if k in os.environ}
    environment.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    try:
        with tempfile.TemporaryDirectory(prefix='archipemanu-progression-') as tmp:
            root = Path(tmp)
            players = root/'players'; players.mkdir()
            for name, text in request.pop('yamls').items():
                if Path(name).name != name or not name.endswith('.yaml'):
                    raise ValueError('yaml_filename')
                (players/name).write_bytes(text.encode('utf-8'))
            payload = dict(request, players=str(players), output=str(root/'output'))
            with (root/'stdout').open('w+b') as stdout:
                process = subprocess.run([str(config.AP_PYTHON),str(config.ROOT/'progression_worker.py')],
                    input=db.dumps(payload).encode(),stdout=stdout,stderr=subprocess.DEVNULL,cwd=config.AP_SOURCE,env=environment,
                    timeout=JOB_TIMEOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if process.returncode or stdout.tell()>8*1024**2:
                    return dict(state='unsupported',reason='worker_failed')
                stdout.seek(0)
                value = json.load(stdout)
                if value.get('state') not in ('ready','unsupported'):
                    raise ValueError('worker_result')
                return value
    except subprocess.TimeoutExpired:
        return dict(state='unsupported',reason='timeout')
    except (OSError,ValueError,TypeError):
        return dict(state='unsupported',reason='worker_failed')


def prepare(build, slot):
    evidence = manifest(build)
    if evidence is None:
        return None, 'historical_seed'
    summary, rows = placements(build)
    if rows is None:
        return None, 'placements_missing'
    model = evidence['model']
    if model.get('groups'):
        return None,'item_links'
    expected = sorted((s['slot'],s['game_name']) for s in db.loads(build['snapshot'])['slots'])
    if sorted((p['name'],p['game']) for p in model['players']) != expected:
        return None,'reconstruction_mismatch'
    # Evidence and the separately validated existing item-placement export agree.
    actual = sorted((r['player'],r['id'],r['item']['player'],r['item']['id']) for r in model['locations']
                    if type(r['id']) is int and r['item'] and type(r['item']['id']) is int
                    and r['player'] in {p['id'] for p in summary['players']} and r['item']['player'] in {p['id'] for p in summary['players']})
    if actual != sorted((r['finder'],r['location_id'],r['recipient'],r['item_id']) for r in rows):
        return None,'reconstruction_mismatch'
    player = next((p for p in summary['players'] if p['name']==slot['slot'] and p['game']==slot['game_name']),None)
    if not player:
        return None,'identity'
    observed = observations(build,summary['players'],rows).get(player['id'])
    if not observed or time.time()-observed[1]>300:
        return None,'inventory_missing'
    live, at, source = observed
    if not live.get('synchronized',True):
        return None,'inventory_missing'
    if source == 'webhost':
        if not live.get('received_complete'):
            return None,'inventory_missing'
        locations = {r['location_id'] for r in rows if r['finder']==player['id']}
        live['missing'] = sorted(locations-set(live['checked']))
    folder = config.SESSIONS/'_seeds'/str(build['id'])/'players'
    yamls = {}
    for name, sha in evidence['yamls'].items():
        if Path(name).name != name:
            return None,'yaml_changed'
        path = folder/name
        if not path.is_file() or path.stat().st_size>512*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            return None,'yaml_changed'
        yamls[name] = path.read_bytes().decode('utf-8')
    snapshot = db.loads(build['snapshot'])
    if snapshot.get('yamls') != evidence['yamls']:
        return None,'yaml_changed'
    return dict(manifest=evidence, yamls=yamls, live=live, observed_at=at,
                hide=ap_bridge._hidden_builtins()), None


def job(build, slot, user_id, start=False, target=None, mode='items'):
    if mode not in ('items','goal'):
        raise ValueError('analysis_mode')
    data, reason = prepare(build,slot)
    if reason:
        return dict(state='unsupported',reason=reason)
    data['mode'] = mode
    data['target'] = target
    data['analysis_version'] = ANALYSIS_VERSION
    at = data.pop('observed_at')
    # Cache changes only with relevant inventory/checks/target/seed state.
    signature = digest(data)
    with _lock, db.transaction() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("UPDATE progression_jobs SET state='unsupported',result=?,finished_at=? WHERE state='loading' AND created_at<?",
                     (db.dumps(dict(state='unsupported',reason='timeout')),time.time(),time.time()-240))
        old = conn.execute('SELECT * FROM progression_jobs WHERE build_id=? AND user_id=? AND slot_name=? AND signature=?',
                           (build['id'],user_id,slot['slot'],signature)).fetchone()
        if old:
            if start and old['state']=='unsupported' and old['finished_at'] and time.time()-old['finished_at']>15:
                conn.execute('DELETE FROM progression_jobs WHERE id=?',(old['id'],))
            else:
                return dict(state='loading',observed_at=at) if old['state']=='loading' else {**db.loads(old['result']), 'observed_at':at}
        if not start:
            return dict(state='idle',observed_at=at)
        if conn.execute("SELECT COUNT(*) FROM progression_jobs WHERE state='loading'").fetchone()[0]>=4:
            return dict(state='busy')
        jid = conn.execute('''INSERT INTO progression_jobs(build_id,user_id,slot_name,signature,state,created_at)
                             VALUES (?,?,?,?,'loading',?)''',(build['id'],user_id,slot['slot'],signature,time.time())).lastrowid
    path = config.DB_PATH.resolve()
    source = config.AP_SOURCE.resolve()
    def work():
        from hub.ap_console import connection
        # Serialize against mutation of APWorld files by generation/extraction.
        try:
            acquired=ap_bridge.ap_lock.acquire(timeout=2)
            try:
                if not acquired:
                    result = dict(state='unsupported',reason='busy')
                elif not ap_bridge.trusted_custom_execution() or not ap_bridge.ap_ready() or config.AP_SOURCE.resolve()!=source:
                    result = dict(state='unsupported',reason='runtime_changed')
                else:
                    result = run_worker(data)
            finally:
                if acquired:
                    ap_bridge.ap_lock.release()
            with connection(path) as conn:
                conn.execute('UPDATE progression_jobs SET state=?,result=?,finished_at=? WHERE id=?',
                             (result['state'],db.dumps(result),time.time(),jid))
        except Exception:
            # Never propagate worker errors into console or generation threads.
            with connection(path) as conn:
                conn.execute("UPDATE progression_jobs SET state='unsupported',result=?,finished_at=? WHERE id=?",
                             (db.dumps(dict(state='unsupported',reason='worker_failed')),time.time(),jid))
    future = _pool.submit(work)
    _futures.add(future)
    future.add_done_callback(_futures.discard)
    return dict(state='loading',observed_at=at)
