"""Independent connection facts, using existing caches without upstream requests."""
import time

from . import db, i18n, live_store


def webhost(build):
    linked = live_store.current(build['id'])
    if not linked:
        return dict(state='not_linked',last_success=None,next_update=None,stale=False,error='',endpoints=[])
    identifiers = [('room_status',linked['room_id'])]
    if linked['tracker_id']:
        identifiers += [('tracker',linked['tracker_id']),('static_tracker',linked['tracker_id'])]
    now = time.time()
    endpoints = []
    for name,identifier in identifiers:
        row = db.query('SELECT * FROM live_api_cache WHERE endpoint=? AND identifier=?',(name,identifier),one=True)
        if row:
            endpoints.append(dict(endpoint=name,last_success=row['fetched_at'],next_attempt=row['next_attempt'],
                                  state='error' if row['error'] else 'updating' if row['lease_until']>now else
                                  'fresh' if row['next_attempt']>now else 'due',error=i18n.t(row['error'])))
    successes = [row['last_success'] for row in endpoints if row['last_success'] is not None]
    return dict(state=linked['state'],last_success=max(successes) if successes else None,
                next_update=None if build['completed_at'] else max(now,linked['next_poll']),
                stale=linked['state']!='ready' or not linked['last_success'] or
                (not build['completed_at'] and now-linked['last_success']>120),
                error=i18n.t(linked['error']),endpoints=endpoints)
