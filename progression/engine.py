"""Single-item deltas only. Never evaluates pairs or completion counterfactuals."""
import time
from progression.inventory import prepare_inventory

ANALYSIS_VERSION = 3

def analyze(mw, live, target=None, seconds=12, sphere_order=None, mode='items'):
    deadline = time.monotonic() + seconds
    pid, own, checked, state, events, candidates = prepare_inventory(mw, live)
    def reach(current):
        current.sweep_for_advancements(events)
        return ({loc.address for loc in own if loc.address not in checked and loc.can_reach(current)},
                {region.name for region in mw.get_regions(pid) if region.can_reach(current)})
    baseline, base_regions = reach(state)
    result = dict(state='ready', mode=mode,
        reachable=[dict(id=loc.address, name=loc.name, region=loc.parent_region.name)
                   for loc in own if loc.address in baseline],
        regions=sorted(base_regions), targets=[dict(id=loc.address, name=loc.name, region=loc.parent_region.name)
                   for loc in own if loc.address not in checked],
        singles=[], candidates_total=len(candidates), singles_tested=0, singles_complete=False)
    if mode == 'goal':
        from progression.goals import analyze_goal
        result.update(analyze_goal(mw, pid, state, candidates, deadline))
        return result
    if mode != 'items':
        raise ValueError('analysis_mode')
    # Spheres affect scheduling only if the budget expires, never the ranking.
    spheres = sphere_order or {}
    names = sorted(candidates, key=lambda name: (
        min((spheres.get((loc.player,loc.address),10**9) for loc in candidates[name]), default=10**9),
        name.casefold(), name))
    for name in names:
        if time.monotonic() >= deadline:
            break
        current = state.copy()
        current.collect(candidates[name][0].item, True)  # Exactly one additional copy.
        checks, regions = reach(current)
        new_checks, new_regions = sorted(checks-baseline), sorted(regions-base_regions)
        result['singles'].append(dict(items=[dict(name=name, count=1,
            locations=[dict(finder=loc.player,location_id=loc.address) for loc in candidates[name]])],
            new_checks=new_checks, new_regions=new_regions, helpful=bool(new_checks or new_regions)))
    result['singles'].sort(key=lambda row: (-len(row['new_checks']), -len(row['new_regions']),
                                           row['items'][0]['name'].casefold(), row['items'][0]['name']))
    result.update(singles_tested=len(result['singles']), singles_complete=len(result['singles'])==len(candidates))
    return result
