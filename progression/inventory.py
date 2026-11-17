"""Fail-closed receipt reconciliation and immutable current AP inventory."""
from collections import Counter
from progression_model import Unsupported

def prepare_inventory(mw, live):
    from BaseClasses import CollectionState
    pid = live['slot']
    if mw.groups:
        raise Unsupported('item_links')
    if pid not in mw.player_ids or live.get('team') != 0:
        raise Unsupported('identity')
    own = [loc for loc in mw.get_filled_locations(pid) if type(loc.address) is int and loc.item and type(loc.item.code) is int]
    checked, missing = set(live['checked']), set(live['missing'])
    if checked & missing or checked | missing != {loc.address for loc in own}:
        raise Unsupported('incomplete_checks')
    locations = {(loc.player, loc.address): loc for loc in mw.get_filled_locations() if type(loc.address) is int}
    state = CollectionState(mw)
    # AP already collected immutable start inventory. ReceivedItems with handling=7
    # also contains it as negative locations; match those copies exactly once.
    starts = Counter(i.code for i in mw.precollected_items[pid] if type(i.code) is int)
    confirmed = set()
    for received in live['received']:
        code, finder, address = received['item'], received['player'], received['location']
        if address < 0:
            if starts[code]:
                starts[code] -= 1
                continue
            raise Unsupported('unmatched_synthetic_item')
        loc = locations.get((finder, address))
        if not loc or not loc.item or (loc.item.code, loc.item.player) != (code, pid) or (finder, address) in confirmed:
            raise Unsupported('unmatched_receipt')
        confirmed.add((finder, address))
        state.collect(loc.item, True)
    if any(starts.values()):
        raise Unsupported('incomplete_start_inventory')
    # Sweep only addressless events in this player's world. Never silently award
    # real reachable checks or another player's unobserved inventory.
    events = [loc for loc in mw.get_filled_locations(pid) if loc.address is None and loc.item and loc.item.code is None]
    candidates = {}
    for loc in sorted(locations.values(), key=lambda l: (l.player, l.address)):
        if (loc.item and type(loc.item.code) is int and loc.item.player == pid
                and loc.item.advancement and (loc.player, loc.address) not in confirmed):
            candidates.setdefault(loc.item.name, []).append(loc)
    return pid, own, checked, state, events, candidates
