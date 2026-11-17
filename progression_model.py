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


def analyze(mw, live, target=None, seconds=12, sphere_order=None, mode='items'):
    """Stable worker API. Optional completion work requires explicit mode='goal'."""
    from progression.engine import analyze as evaluate
    return evaluate(mw, live, target, seconds, sphere_order, mode)
