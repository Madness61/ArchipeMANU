"""Set-based presentation of already evaluated AP rules; no game-specific rules."""
import hashlib
import json

ANALYSIS_VERSION = 2


def helpful(row):
    return bool(row['new_checks'] or row['new_regions'] or row['goal_gain'] or row['target_gain'])


def rank(row):
    """Within each section: target, completion, check gains, then region gains."""
    synergy = row.get('synergy', {})
    return (-int(row['target_gain']), -int(row['goal_gain']),
            -len(synergy.get('checks', row['new_checks'])),
            -len(synergy.get('regions', row['new_regions'])),
            -len(row['new_checks']), -len(row['new_regions']),
            tuple(sorted((i['name'], i['count']) for i in row['items'])))


def refine(result):
    """Do not recommend CAB unless it improves on CA union CB, not just C0.

    Input new_checks/new_regions already excludes C0. Thus subtracting the union
    of the two single-item deltas is exactly CAB - (CA union CB).
    """
    baseline_goal = bool(result.get('goal_reachable'))
    baseline_target = bool(result.get('target_reachable'))
    singles = result.get('singles', [])
    by_name = {}
    def annotate(row):
        row['goal_gain'] = bool(row.get('goal_reachable') and not baseline_goal)
        row['target_gain'] = bool(row.get('target_reached') and not baseline_target)
        row['helpful'] = helpful(row)
    for row in singles:
        annotate(row)
        by_name[row['items'][0]['name']] = row
    retained, identities = [], set()
    for row in result.get('combinations', []):
        identity = tuple(sorted((i['name'],i['count']) for i in row['items']))
        if identity in identities:
            continue
        identities.add(identity)
        # Both single trials must exist. Missing trials are not evidence of zero.
        components = [by_name.get(i['name']) for i in row['items']]
        if not components or any(part is None for part in components):
            continue
        annotate(row)
        check_union = set().union(*(set(part['new_checks']) for part in components))
        region_union = set().union(*(set(part['new_regions']) for part in components))
        row['synergy'] = dict(checks=sorted(set(row['new_checks'])-check_union),
                              regions=sorted(set(row['new_regions'])-region_union),
                              goal=row['goal_gain'] and not any(part['goal_gain'] for part in components),
                              target=row['target_gain'] and not any(part['target_gain'] for part in components))
        if any(row['synergy'].values()):
            retained.append(row)
    # Group by actual IDs/region names and goal effects, never by their counts.
    for row in singles + retained:
        effect = dict(checks=sorted(row['new_checks']),regions=sorted(row['new_regions']),
                      goal=row['goal_gain'],target=row['target_gain'],synergy=row.get('synergy'))
        row['effect_key'] = hashlib.sha256(json.dumps(effect,sort_keys=True).encode()).hexdigest()
    result.update(singles=sorted(singles,key=rank),combinations=sorted(retained,key=rank),
                  recommendation_version=ANALYSIS_VERSION)
    return result
