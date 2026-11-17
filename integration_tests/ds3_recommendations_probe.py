"""Actual DS3 rules and deterministic seeds; no real game client or online room."""
import contextlib
import json
import os
from pathlib import Path
import sys


def run(request):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0,os.getcwd())
    import settings
    settings.no_gui=True;settings.skip_autosave=True
    import Generate
    from Main import main
    from BaseClasses import CollectionState
    from progression_recommendations import refine
    names=['Basin of Vows','Black Eye Orb','Blacksmith Hammer','Braille Divine Tome of Carim','Braille Divine Tome of Lothric']
    results=[]
    for option in ('off','after_small_doll'):
        root=Path(request['root'])/option;players=root/'players';players.mkdir(parents=True)
        (players/'ds3.yaml').write_text('name: Probe\ngame: Dark Souls III\nDark Souls III:\n  late_basin_of_vows: '+option+'\n  enable_dlc: false\n',encoding='utf-8')
        sys.argv=['Generate.py','--player_files_path',str(players),'--outputpath',str(root/'output'),'--seed','20261116','--spoiler','0','--skip_output']
        args,seed=Generate.main();mw=main(args,seed)
        locations=[l for l in mw.get_filled_locations(1) if type(l.address) is int and l.item and type(l.item.code) is int]
        events=[l for l in mw.get_filled_locations(1) if l.address is None and l.item and l.item.code is None]
        base=CollectionState(mw)
        # An explicit rule-test inventory, not a claimed live ReceivedItems state.
        # All other generated items remove unrelated access bottlenecks.
        for loc in locations:
            if loc.item.name not in names:base.collect(loc.item,True)
        base.sweep_for_advancements(events)
        def effect(current):
            current.sweep_for_advancements(events)
            return ({l.address for l in locations if l.can_reach(current)},
                    {r.name for r in mw.get_regions(1) if r.can_reach(current)},bool(mw.has_beaten_game(current,1)))
        checks,regions,goal=effect(base)
        def simulate(selected):
            state=base.copy()
            for name in selected:state.collect(mw.worlds[1].create_item(name),True)
            new,areas,beaten=effect(state)
            return dict(items=[dict(name=name,count=1) for name in selected],new_checks=sorted(new-checks),
                        new_regions=sorted(areas-regions),goal_reachable=beaten,target_reached='Lothric Castle' in areas)
        singles=[simulate([name]) for name in names]
        pairs=[simulate([names[0],name]) for name in names[1:]]
        corrected=refine(dict(singles=singles,combinations=pairs,goal_reachable=goal,target_reachable='Lothric Castle' in regions))
        kept={row['items'][1]['name']:row for row in corrected['combinations']}
        for pair in pairs:
            extra=pair['items'][1]['name']
            a,b=singles[0],next(s for s in singles if s['items'][0]['name']==extra)
            exclusive=set(pair['new_checks'])-(set(a['new_checks'])|set(b['new_checks']))
            exclusive_regions=set(pair['new_regions'])-(set(a['new_regions'])|set(b['new_regions']))
            goal_only=pair['goal_reachable'] and not (goal or a['goal_reachable'] or b['goal_reachable'])
            target_only=pair['target_reached'] and not ('Lothric Castle' in regions or a['target_reached'] or b['target_reached'])
            assert (extra in kept)==bool(exclusive or exclusive_regions or goal_only or target_only)
            if extra in kept:
                assert set(kept[extra]['synergy']['checks'])==exclusive
                assert set(kept[extra]['synergy']['regions'])==exclusive_regions
        assert singles[0]['new_checks'] and len(kept)<len(pairs)
        without_doll=CollectionState(mw)
        for loc in locations:
            if loc.item.name not in names and loc.item.name!='Small Doll':without_doll.collect(loc.item,True)
        without_doll.collect(mw.worlds[1].create_item('Basin of Vows'),True)
        castle_without_doll='Lothric Castle' in effect(without_doll)[1]
        assert castle_without_doll == (option=='off')
        results.append(dict(option=option,checks=len(locations),basin_checks=len(singles[0]['new_checks']),basin_regions=singles[0]['new_regions'],
                            castle_without_small_doll=castle_without_doll,
                            kept=[dict(item=name,extra_checks=len(row['synergy']['checks']),extra_regions=len(row['synergy']['regions'])) for name,row in kept.items()],
                            suppressed=[name for name in names[1:] if name not in kept]))
    return results


if __name__=='__main__':
    output=sys.stdout
    with contextlib.redirect_stdout(sys.stderr):result=run(json.load(sys.stdin))
    json.dump(result,output)
