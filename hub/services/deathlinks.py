"""Observed DeathLink bounces; source is client supplied, never a sender ID."""
import hashlib
import time
from datetime import datetime, timezone

from hub import db
from hub.services.console_journal import connection

STALE_SECONDS = 15


def migrate():
    with db.transaction() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS deathlink_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
            event_key TEXT NOT NULL, source TEXT NOT NULL, death_time REAL NOT NULL,
            cause TEXT, slot TEXT, observed_at REAL NOT NULL,
            UNIQUE(build_id,event_key)
        );
        CREATE INDEX IF NOT EXISTS deathlink_history ON deathlink_events(build_id,death_time,id);
        CREATE TABLE IF NOT EXISTS deathlink_coverage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            build_id INTEGER NOT NULL REFERENCES seed_builds(id) ON DELETE CASCADE,
            hosted_id INTEGER NOT NULL REFERENCES hosted_rooms(id) ON DELETE CASCADE,
            stream_id TEXT NOT NULL, started_at REAL NOT NULL, heartbeat REAL NOT NULL,
            ended_at REAL, invalid_events INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS deathlink_coverage_build ON deathlink_coverage(build_id,id);
        CREATE UNIQUE INDEX IF NOT EXISTS deathlink_active_stream
            ON deathlink_coverage(stream_id) WHERE ended_at IS NULL;
        ''')


def coverage(reader, now=None):
    now = time.time() if now is None else now
    with connection(reader.path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        # A crashed process cannot close its interval. Preserve the last heartbeat.
        conn.execute('''UPDATE deathlink_coverage SET ended_at=heartbeat
            WHERE build_id=? AND ended_at IS NULL AND heartbeat<?''',
                     (reader.build_id, now - STALE_SECONDS))
        if reader.state == 'connected':
            conn.execute('''INSERT INTO deathlink_coverage(build_id,hosted_id,stream_id,started_at,heartbeat)
                VALUES (?,?,?,?,?) ON CONFLICT(stream_id) WHERE ended_at IS NULL
                DO UPDATE SET heartbeat=excluded.heartbeat''',
                         (reader.build_id, reader.endpoint['id'], reader.stream_id, now, now))
        else:
            conn.execute('''UPDATE deathlink_coverage SET ended_at=heartbeat
                WHERE stream_id=? AND ended_at IS NULL''', (reader.stream_id,))


def observe(reader, packet):
    if reader.state != 'connected' or reader.team != 0:
        return
    tags = packet.get('tags')
    if not isinstance(tags, list) or 'DeathLink' not in tags:
        return
    data = packet.get('data')
    data = data if isinstance(data, dict) else {}
    source, stamp = data.get('source'), data.get('time')
    cause = data.get('cause')
    cause = cause[:12000] if isinstance(cause, str) and cause else None
    try:
        (source if isinstance(source, str) else '').encode('utf-8')
        (cause or '').encode('utf-8')
        valid_text = True
    except UnicodeError:
        valid_text = False
    if (not isinstance(source, str) or not source.strip() or len(source) > 1000
            or not valid_text or type(stamp) not in (int, float)
            or not 0 < stamp < 253402300800):
        with connection(reader.path) as conn:
            conn.execute('''UPDATE deathlink_coverage SET invalid_events=invalid_events+1
                WHERE stream_id=? AND ended_at IS NULL''', (reader.stream_id,))
        return
    # Keep the full, case-sensitive source. Cause and recipient aren't identity.
    key = hashlib.sha256(db.dumps([reader.team, source, float(stamp).hex()]).encode()).hexdigest()
    candidates = {p['name'] for slot, p in reader.players.items() if p['type'] == 1
                  and source in (p['name'], reader.deathlink_aliases.get(slot))}
    slot = next(iter(candidates)) if len(candidates) == 1 else None
    with connection(reader.path) as conn:
        conn.execute('''INSERT OR IGNORE INTO deathlink_events
            (build_id,event_key,source,death_time,cause,slot,observed_at) VALUES (?,?,?,?,?,?,?)''',
                     (reader.build_id, key, source, stamp, cause, slot, time.time()))


def presentation(build, now=None):
    now = time.time() if now is None else now
    completed_at = None
    if build['completed_at']:
        try:
            completed = datetime.fromisoformat(build['completed_at'].replace('Z', '+00:00'))
            completed_at = (completed if completed.tzinfo else completed.replace(tzinfo=timezone.utc)).timestamp()
            now = min(now, completed_at)
        except (ValueError, TypeError):
            pass
    if db.loads(build['snapshot']).get('race'):
        return dict(state='race', total=None, ranking=[], unresolved=[], recent=[], gaps=[])
    conn = db.get()
    args = (build['id'],)
    total = conn.execute('SELECT COUNT(*) FROM deathlink_events WHERE build_id=?', args).fetchone()[0]
    ranking = [dict(r) for r in conn.execute('''SELECT slot,COUNT(*) AS count FROM deathlink_events
        WHERE build_id=? AND slot IS NOT NULL GROUP BY slot ORDER BY count DESC,slot''', args)]
    unresolved = [dict(r) for r in conn.execute('''SELECT source,COUNT(*) AS count FROM deathlink_events
        WHERE build_id=? AND slot IS NULL GROUP BY source ORDER BY count DESC,source''', args)]
    recent = [dict(r) for r in conn.execute('''SELECT source,death_time,cause,slot,observed_at
        FROM deathlink_events WHERE build_id=? ORDER BY death_time DESC,id DESC LIMIT 50''', args)]
    periods = conn.execute('''SELECT * FROM deathlink_coverage
        WHERE build_id=? AND started_at<=? ORDER BY started_at,id''', (*args, now)).fetchall()
    gaps, until = [], None
    for period in periods:
        if until is not None and period['started_at'] > until:
            gaps.append(dict(start=until, end=period['started_at']))
        end = period['ended_at'] if period['ended_at'] is not None else (
            now if period['heartbeat'] >= now - STALE_SECONDS else period['heartbeat'])
        end = min(end, now)
        until = max(until or end, end)
    active = any(p['ended_at'] is None and p['heartbeat'] >= now - STALE_SECONDS for p in periods)
    if until is not None and not active and (completed_at is None or until < now):
        gaps.append(dict(start=until, end=completed_at))
    return dict(state='completed' if build['completed_at'] else 'recording' if active else 'waiting',
                total=total, ranking=ranking, unresolved=unresolved, recent=recent,
                since=periods[0]['started_at'] if periods else None,
                gaps=gaps[-10:], gap_count=len(gaps), invalid_events=sum(p['invalid_events'] for p in periods))
