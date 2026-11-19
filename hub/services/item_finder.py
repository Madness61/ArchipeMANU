"""Verified placements and observed check/receipt lookup; no workers."""
import json
from progression_model import digest
from hub import config, db, live_metrics, live_store, mvp
def placements(build):
    summary = mvp._build_distribution(build)
    return summary, mvp._build_placements(build, summary)


def manifest(build):
    path = config.SESSIONS / '_seeds' / str(build['id']) / 'output' / 'progression_seed.json'
    try:
        if path.stat().st_size > 32 * 1024**2:
            return None
        value = json.loads(path.read_text(encoding='utf-8'))
        if (value.get('version') == 1 and value.get('source') == 'archipelago_generated_logic'
                and digest(value['model']) == value['model_hash'] and type(value['seed']) is int
                and isinstance(value.get('yamls'),dict) and isinstance(value['model'].get('players'),list)
                and isinstance(value['model'].get('locations'),list)):
            players=value['model']['players']
            if not players or any(type(p.get('id')) is not int or not isinstance(p.get('name'),str)
                                  or not isinstance(p.get('game'),str) for p in players):
                return None
            if len({p['id'] for p in players})!=len(players) or len({p['name'] for p in players})!=len(players):
                return None
            for loc in value['model']['locations']:
                if (not isinstance(loc,dict) or type(loc.get('player')) is not int
                        or not (loc.get('id') is None or type(loc['id']) is int)
                        or 'item' not in loc or loc['item'] is not None and
                        (not isinstance(loc['item'],dict) or type(loc['item'].get('player')) is not int
                         or not (loc['item'].get('id') is None or type(loc['item']['id']) is int))):
                    return None
            return value
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return None


def observations(build, players, rows=None):
    """Read synchronized sources only. Never poll upstream on search/page visits."""
    endpoint = db.query('SELECT id FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1', (build['id'],), one=True)
    result = {}
    ids = {p['name']: p['id'] for p in players}
    for row in db.query('SELECT * FROM progression_live WHERE build_id=? AND hosted_id=?',
                        (build['id'],endpoint['id'] if endpoint else -1)):
        if row['slot_name'] in ids:
            result[ids[row['slot_name']]] = (db.loads(row['payload']),row['observed_at'],'console')
    linked = live_store.current(build['id'])
    if not linked:
        return result
    room = db.loads(linked['room_json'])
    expected = [[p['name'], p['game']] for p in sorted(players, key=lambda p:p['id'])]
    if room.get('players') != expected:
        return result
    cached = db.query("SELECT * FROM live_api_cache WHERE endpoint='tracker' AND identifier=?", (linked['tracker_id'],), one=True)
    static = db.query("SELECT payload FROM live_api_cache WHERE endpoint='static_tracker' AND identifier=?", (linked['tracker_id'],), one=True)
    if not cached or not cached['payload'] or not cached['fetched_at'] or not static:
        return result
    games = live_metrics.indexed(db.loads(static['payload']), 'player_game')
    if set(games) != {(0,p['id']) for p in players} or any(games[(0,p['id'])].get('game') != p['game'] for p in players):
        return result
    data = db.loads(cached['payload'])
    checks = live_metrics.indexed(data,'player_checks_done')
    receipts = live_metrics.indexed(data,'player_items_received')
    totals=live_metrics.indexed(db.loads(static['payload']),'player_locations_total')
    for player in players:
        pair = (0,player['id'])
        if pair not in checks or not isinstance(checks[pair].get('locations'),list):
            continue
        checked=checks[pair]['locations']
        if any(type(check) is not int for check in checked):
            continue
        at = cached['fetched_at']
        if player['id'] in result and result[player['id']][1] >= at:
            continue
        items = receipts.get(pair, {}).get('items')
        parsed = []
        if isinstance(items,list):
            from hub.integrations.console import network_item
            try:
                parsed = [network_item(i) for i in items]
            except (ValueError, KeyError, TypeError):
                items = None
        remaining={r['location_id'] for r in (rows or []) if r['finder']==player['id']}
        missing=sorted(remaining-set(checked)) if (set(checked)<=remaining and
            totals.get(pair,{}).get('total_locations')==len(remaining)) else []
        result[player['id']] = (dict(slot=player['id'],team=0,checked=checked,missing=missing,
            received=parsed, received_complete=isinstance(items,list)), at,'webhost')
    return result


def find(build, own, query='', category='all', owner='all', status='all', page=1, limit=50, *, recipient_slot=None):
    summary, rows = placements(build)
    if rows is None:
        return dict(available=False, rows=[], total=0, pages=0, page=1)
    players = {p['id']:p for p in summary['players']}
    names = {slot['slot'] for slot in own}
    observed = observations(build,summary['players'],rows)
    checks = {pid: (set(state['checked']), set(state.get('missing', ())), at)
              for pid, (state, at, _) in observed.items()}
    receipts = {
        pid: ({(item['item'], item['location'], item['player']) for item in state['received']},
              state.get('received_complete', True), at)
        for pid, (state, at, _) in observed.items()
    }
    journal = {}
    for event in db.query("""SELECT payload,observed_at FROM console_events
        WHERE build_id=? AND hosted_id=(SELECT MAX(id) FROM hosted_rooms WHERE build_id=?)
        AND user_id IS NULL AND kind='items'""", (build['id'], build['id'])):
        payload = db.loads(event['payload'])
        if payload.get('type') == 'item':
            key = (payload['sender'], payload['location_id'], payload['recipient'], payload['item_id'])
            journal[key] = (event['observed_at'], payload.get('source'))
    query = query.casefold()
    answer = []
    for index, row in enumerate(rows):
        finder, recipient = players[row['finder']], players[row['recipient']]
        if category != 'all' and row['category'] != category:
            continue
        if owner == 'mine' and recipient['name'] not in names:
            continue
        if recipient_slot is not None and recipient['name'] != recipient_slot:
            continue
        text = ' '.join((row['item'],row['location'],finder['name'],finder['game'],recipient['name'],recipient['game']))
        if query not in text.casefold():
            continue
        check, check_at, receipt, receipt_at = 'unknown', None, 'unknown', None
        if row['finder'] in checks:
            found, missing, at = checks[row['finder']]
            if row['location_id'] in found:
                check, check_at = 'checked', at
            elif row['location_id'] in missing:
                check, check_at = 'unchecked', at
        if row['recipient'] in receipts:
            items, complete, at = receipts[row['recipient']]
            matched = (row['item_id'], row['location_id'], row['finder']) in items
            if matched or complete:
                receipt, receipt_at = ('received' if matched else 'not_received'), at
        event = journal.get((finder['name'], row['location_id'], recipient['name'], row['item_id']))
        if event:
            at, source = event
            if check_at is None or at > check_at:
                check, check_at = 'checked', at
            if source == 'received_items' and (receipt_at is None or at > receipt_at):
                receipt, receipt_at = 'received', at
        if status != 'all' and check != status:
            continue
        answer.append(dict(id=index, **row, finder_player=finder, recipient_player=recipient,
                           check_status=check, check_at=check_at, receipt_status=receipt, receipt_at=receipt_at))
    if not limit:
        return dict(available=True,total=len(answer),page=1,pages=1,rows=answer)
    pages = max(1,(len(answer)+limit-1)//limit)
    page = min(page,pages)
    return dict(available=True,total=len(answer),page=page,pages=pages,rows=answer[(page-1)*limit:page*limit])


def player_items(build, own, recipient, query, receipt, reveal, page, limit):
    result = find(build, own, category='progression', limit=0, recipient_slot=recipient)
    groups = {}
    query = query.casefold()
    for row in result['rows']:
        name = row['item']
        if query not in name.casefold():
            continue
        group = groups.setdefault(row['item_id'], dict(name=name, total=0, received=0, not_received=0, unknown=0))
        group['total'] += 1
        group[row['receipt_status']] += 1
        if reveal and receipt in ('all', row['receipt_status']):
            group.setdefault('copies', []).append(dict(
                finder=row['finder_player']['name'], game=row['finder_player']['game'], location=row['location'],
                status=row['receipt_status'], check_status=row['check_status']))
    rows = sorted((group for group in groups.values() if receipt == 'all' or group[receipt]),
                  key=lambda group: group['name'].casefold())
    pages = max(1, (len(rows) + limit - 1) // limit)
    page = min(page, pages)
    return dict(available=result['available'], revealed=reveal, total=len(rows), page=page, pages=pages,
                rows=rows[(page - 1) * limit:page * limit])
