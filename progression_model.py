"""Versioned JSON evidence from AP's actual generated world; no pickle or adapters."""
from collections import Counter
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import time
import threading
import sys

FORMAT = 1
SOURCE = "archipelago_generated_logic"


def plain(value):
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((plain(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    raise ValueError("Non-JSON seed option")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def runtime_details(root):
    """Hash executable AP sources and every installed APWorld, not timestamps."""
    root = Path(root)
    paths = sorted(p for p in root.rglob("*") if p.is_file()
                   and (p.suffix in (".py", ".apworld") or p.relative_to(root).parts[0] in ('worlds','data','rule_builder')
                        or p.name=='requirements.txt')
                   and not {".git", "__pycache__", "logs", "test", "tests"}.intersection(p.relative_to(root).parts))
    from importlib.metadata import distributions
    import site
    package_paths = site.getsitepackages() + ([site.getusersitepackages()] if site.ENABLE_USER_SITE else [])
    if not paths:
        raise ValueError("AP sources unavailable")
    return dict(python=sys.version,packages=sorted({(p.metadata['Name'],p.version) for p in distributions(path=package_paths)}),
                files={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def runtime_fingerprint(root):
    return digest(runtime_details(root))


def describe(mw):
    players = []
    for pid in mw.player_ids:
        world = mw.worlds[pid]
        players.append(dict(id=pid, name=mw.get_player_name(pid), game=mw.game[pid],
                            module=type(world).__module__.split(".")[1],
                            version=world.world_version.as_simple_string(),
                            options={f.name: plain(getattr(world.options, f.name).value) for f in fields(world.options)}))
        module_path = Path(sys.modules[type(world).__module__].__file__)
        archive = next((p for p in (module_path,*module_path.parents) if p.suffix=='.apworld'),None)
        players[-1]['apworld_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest() if archive else None
    def item(value):
        return None if value is None else dict(name=value.name, id=value.code, player=value.player, flags=int(value.classification))
    locations = [dict(player=loc.player, id=loc.address, name=loc.name, region=loc.parent_region.name,
                      item=item(loc.item)) for loc in mw.get_locations()]
    regions = [dict(player=r.player, name=r.name,
                    exits=sorted((e.name, e.connected_region.name if e.connected_region else None) for e in r.exits))
               for r in mw.get_regions()]
    return dict(players=players, groups={str(g):plain({k:v for k,v in group.items() if k != 'world'}) for g,group in mw.groups.items()},
                precollected={str(p): [item(i) for i in items] for p, items in mw.precollected_items.items()},
                locations=sorted(locations, key=lambda r: (r['player'], r['name'])),
                regions=sorted(regions, key=lambda r: (r['player'], r['name'])))


def rule_probes(mw):
    """Deterministic reachability witnesses, in addition to code/placement hashes.

    These catch hidden randomized rule parameters for the tested inventories.
    They are bounded witnesses, not a proof over every possible inventory.
    """
    from BaseClasses import CollectionState
    locations = sorted(mw.get_filled_locations(), key=lambda l:(l.player,l.name))
    events = [l for l in locations if l.address is None and l.item and l.item.code is None]
    items = [l.item for l in locations if l.item and type(l.item.code) is int]
    result = []
    for selection in ([],items[::2],items[1::2],items):
        state = CollectionState(mw)
        for item in selection:
            state.collect(item,True)
        state.sweep_for_advancements(events)
        result.append(digest(dict(locations=[(l.player,l.name) for l in locations if l.can_reach(state)],
            regions=sorted((r.player,r.name) for r in mw.get_regions() if r.can_reach(state)),
            goals=[bool(mw.has_beaten_game(state,p)) for p in mw.player_ids])))
    return result


def save_seed(mw, seed, players, output, ap_root):
    """Optional generation analytics. Caller must catch all failures."""
    from Utils import __version__
    model = describe(mw)
    runtime = runtime_details(ap_root)
    manifest = dict(version=FORMAT, source=SOURCE, seed=seed, ap_version=__version__,
                    runtime=digest(runtime), runtime_details=runtime, model_hash=digest(model),
                    model=model, yamls={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in Path(players).glob('*.yaml')})
    # Persist reconstruction evidence before attempting optional expensive rules.
    target = Path(output) / 'progression_seed.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    result = []
    def static_analysis():
        started = time.monotonic()
        spheres, complete = [], True
        try:
            probes = rule_probes(mw)
            unreachable = False
            for sphere in mw.get_spheres():
                if not sphere:
                    unreachable = True
                spheres.append(dict(unreachable=unreachable,
                    locations=sorted([dict(player=loc.player, id=loc.address, name=loc.name) for loc in sphere],
                                     key=lambda r: (r['player'], r['name']))))
                if time.monotonic() - started > 4 or len(spheres) >= 1000:
                    complete = False
                    break
            result.append(dict(state='ready', spheres=spheres, complete=complete, rule_probes=probes,
                               goals={str(p):bool(mw.has_beaten_game(mw.get_all_state(False),p)) for p in mw.player_ids}))
        except Exception:
            pass
    # A custom rule can hang even inside one can_reach call. A daemon probe may
    # not hold successful generation hostage; no further seed work uses mw.
    probe = threading.Thread(target=static_analysis,daemon=True,name='optional-static-progression')
    probe.start(); probe.join(5)
    manifest['static'] = result[0] if not probe.is_alive() and result else dict(state='unavailable',spheres=[],complete=False)
    target.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    return manifest


class Unsupported(ValueError):
    pass


def analyze(mw, live, target=None, seconds=12, max_candidates=40, max_pairs=80):
    """Counterfactual inventory checks with the registered APWorld rules only."""
    from BaseClasses import CollectionState
    from itertools import combinations_with_replacement
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
    deadline = time.monotonic() + seconds
    def reach(current):
        current.sweep_for_advancements(events)
        checks = {loc.address for loc in own if loc.address not in checked and loc.can_reach(current)}
        regions = {r.name for r in mw.get_regions(pid) if r.can_reach(current)}
        return checks, regions, bool(mw.has_beaten_game(current, pid))
    baseline, base_regions, goal = reach(state)
    candidates = {}
    for loc in sorted(locations.values(), key=lambda l: (l.item.name if l.item else '', l.player, l.address)):
        if loc.item and type(loc.item.code) is int and loc.item.player == pid and loc.item.advancement and (loc.player, loc.address) not in confirmed:
            candidates.setdefault(loc.item.name, []).append(loc)
    names = list(candidates)[:max_candidates]
    complete = len(names) == len(candidates)
    def simulation(selection):
        counts = Counter(selection)
        if any(count > len(candidates[name]) for name, count in counts.items()):
            return None
        current = state.copy()
        for name, count in counts.items():
            for loc in candidates[name][:count]:
                current.collect(loc.item, True)
        checks, regions, beaten = reach(current)
        target_reached = ((target.get('id') in checks) if target and target.get('kind') == 'location' else
                          (target.get('name') in regions) if target and target.get('kind') == 'region' else None)
        return dict(items=[dict(name=name, count=count, locations=[dict(finder=loc.player,location_id=loc.address)
                           for loc in candidates[name]]) for name, count in counts.items()],
                    new_checks=sorted(checks-baseline), new_regions=sorted(regions-base_regions),
                    goal_reachable=beaten, target_reached=target_reached)
    singles, pairs = [], []
    for name in names:
        if time.monotonic() > deadline:
            complete = False
            break
        singles.append(simulation([name]))
    pair_names = [r['items'][0]['name'] for r in singles][:12]
    pair_attempts, possible = 0, len(pair_names)*(len(pair_names)+1)//2
    for a, b in combinations_with_replacement(pair_names, 2):
        if time.monotonic() > deadline or pair_attempts >= max_pairs:
            break
        pair_attempts += 1
        value = simulation([a, b])
        if value:
            pairs.append(value)
    combinations_complete = len(pair_names) == len(candidates) and pair_attempts == possible
    # Necessary means one exact placed copy was removed and the real reachable
    # item chain could no longer satisfy this slot's completion condition.
    necessity = []
    full = mw.get_filled_locations()
    all_state = CollectionState(mw)
    all_state.sweep_for_advancements(full)
    baseline_goal = bool(mw.has_beaten_game(all_state, pid))
    for name in names:
        for loc in candidates[name]:
            if time.monotonic() > deadline or len(necessity) >= 20:
                break
            without = CollectionState(mw)
            without.sweep_for_advancements([other for other in full if other is not loc])
            necessity.append(dict(finder=loc.player, location_id=loc.address, item=name,
                verdict=('necessary' if not mw.has_beaten_game(without, pid) else 'replaceable_copy') if baseline_goal else 'unknown'))
        if time.monotonic() > deadline or len(necessity) >= 20:
            break
    key = lambda row: (-int(bool(row['target_reached'])), -int(row['goal_reachable'] and not goal), -len(row['new_checks']), -len(row['new_regions']))
    return dict(state='ready', reachable=[dict(id=loc.address, name=loc.name, region=loc.parent_region.name)
                for loc in own if loc.address in baseline],
                regions=sorted(base_regions), goal_reachable=goal, singles=sorted(singles, key=key),
                combinations=sorted(pairs, key=key), candidates_total=len(candidates),
                singles_complete=complete, combinations_complete=combinations_complete,
                necessity=necessity, necessity_complete=len(necessity) == sum(len(v) for v in candidates.values()),
                targets=[dict(id=loc.address, name=loc.name, region=loc.parent_region.name) for loc in own if loc.address not in checked])
