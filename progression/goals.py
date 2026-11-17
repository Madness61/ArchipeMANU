"""Explicit, independently cached completion/copy-necessity analysis."""
import time

def analyze_goal(mw, pid, state, candidates, deadline):
    from BaseClasses import CollectionState
    full = mw.get_filled_locations()
    result = dict(goal_reachable=bool(mw.has_beaten_game(state, pid)), necessity=[], necessity_complete=False,
                  necessity_total=sum(len(v) for v in candidates.values()))
    if time.monotonic() >= deadline:
        return result
    all_state = CollectionState(mw)
    all_state.sweep_for_advancements(full)
    baseline_goal = bool(mw.has_beaten_game(all_state, pid))
    for name in sorted(candidates, key=lambda n:(n.casefold(),n)):
        for loc in candidates[name]:
            if time.monotonic() >= deadline:
                return result
            without = CollectionState(mw)
            without.sweep_for_advancements([other for other in full if other is not loc])
            result['necessity'].append(dict(finder=loc.player, location_id=loc.address, item=name,
                verdict=('necessary' if not mw.has_beaten_game(without,pid) else 'replaceable_copy')
                        if baseline_goal else 'unknown'))
    result['necessity_complete'] = True
    return result
