"""Recommendation regressions: compare exact effects, never just their sizes."""
import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from progression_recommendations import refine
from progression_model import analyze
from test_progression_core import fixture, RuleState, Location, item


def trial(names,checks=(),regions=(),goal=False,target=False):
    return dict(items=[dict(name=n,count=c,locations=[]) for n,c in names],
                new_checks=list(checks),new_regions=list(regions),goal_reachable=goal,target_reached=target)


def single(name,**kwargs):return trial([(name,1)],**kwargs)
def pair(a,b,**kwargs):return trial([(a,2)] if a==b else [(a,1),(b,1)],**kwargs)
def result(singles,pairs,**kwargs):return refine(dict(singles=singles,combinations=pairs,goal_reachable=False,**kwargs))


class EffectTests(unittest.TestCase):
    def test_dominant_single_item_makes_every_superfluous_pair_redundant(self):
        values=[single('Basin',checks=range(10),regions=['Castle'])]+[single(name) for name in ('Orb','Hammer','Tome')]
        pairs=[pair('Basin',name,checks=range(10),regions=['Castle']) for name in ('Orb','Hammer','Tome')]
        data=result(values,pairs)
        self.assertEqual(data['combinations'],[])
        self.assertEqual([r['items'][0]['name'] for r in data['singles'] if r['helpful']],['Basin'])

    def test_independent_and_overlapping_single_effects_are_not_synergy(self):
        for a,b in (([1,2],[3]),([1,2],[2,3])):
            with self.subTest(a=a,b=b):
                self.assertEqual(result([single('A',checks=a),single('B',checks=b)],
                    [pair('A','B',checks=set(a)|set(b))])['combinations'],[])

    def test_zero_singles_and_partial_synergy_report_exclusive_location_ids(self):
        for a,b,total,expected in (([],[],[8,9],[8,9]),([1,2],[3],[1,2,3,8,9],[8,9])):
            with self.subTest(a=a):
                row=result([single('A',checks=a),single('B',checks=b)],[pair('A','B',checks=total)])['combinations'][0]
                self.assertEqual(row['new_checks'],total)
                self.assertEqual(row['synergy']['checks'],expected)

    def test_same_counts_different_location_sets_are_not_grouped(self):
        data=result([single(n) for n in 'ABC'],[pair('A','B',checks=[1,2]),pair('A','C',checks=[3,4])])
        self.assertEqual(len(data['combinations']),2)
        self.assertNotEqual(*[r['effect_key'] for r in data['combinations']])
        data=result([single(n) for n in 'ABC'],[pair('A','B',checks=[1,2]),pair('A','C',checks=[2,1])])
        self.assertEqual(*[r['effect_key'] for r in data['combinations']])

    def test_region_only_goal_only_and_target_only_synergy(self):
        for field,value,exclusive in (('regions',['Secret'],'regions'),('goal',True,'goal'),('target',True,'target')):
            with self.subTest(field=field):
                row=result([single('A'),single('B')],[pair('A','B',**{field:value})])['combinations'][0]
                self.assertTrue(row['synergy'][exclusive])
                # A single item providing the very same effect makes this pair redundant.
                self.assertEqual(result([single('A',**{field:value}),single('B')],
                    [pair('A','B',**{field:value})])['combinations'],[])

    def test_already_reachable_goal_or_target_is_not_a_new_effect(self):
        data=refine(dict(goal_reachable=True,target_reachable=True,singles=[single('A',goal=True,target=True),single('B')],
                         combinations=[pair('A','B',goal=True,target=True)]))
        self.assertEqual(data['combinations'],[])
        self.assertTrue(all(not r['helpful'] for r in data['singles']))

    def test_duplicate_recipes_and_missing_single_evidence(self):
        row=pair('A','B',checks=[8]);reverse=copy.deepcopy(row);reverse['items'].reverse()
        self.assertEqual(len(result([single('A'),single('B')],[row,reverse])['combinations']),1)
        self.assertEqual(result([single('A')],[pair('A','B',checks=[8])])['combinations'],[])

    def test_goal_and_selected_target_precede_larger_optional_check_gains(self):
        rows=[single('Optional',checks=range(100)),single('Goal',goal=True),single('Target',target=True)]
        data=result(rows,[])
        self.assertEqual([r['items'][0]['name'] for r in data['singles']],['Target','Goal','Optional'])


class SchedulingTests(unittest.TestCase):
    def evaluate(self,mw,live,**kwargs):
        with patch.dict('sys.modules',{'BaseClasses':SimpleNamespace(CollectionState=RuleState)}):
            return analyze(mw,live,**kwargs)

    def test_late_named_zero_effect_keys_are_selected_for_known_target(self):
        mw,live=fixture(gate=lambda s:s.has('Z key a',1) and s.has('Z key b',1))
        rows=mw.get_filled_locations()
        next(l for l in rows if l.address==10).item.name='Z key a'
        next(l for l in rows if l.address==11).item.name='Z key b'
        rows.extend(Location(2,100+i,'Remote '+str(i),item('AA unused '+str(i),100+i)) for i in range(18))
        mw.get_filled_locations=lambda pid=None:[l for l in rows if pid is None or l.player==pid]
        priorities={(2,100+i):0 for i in range(18)}
        data=self.evaluate(mw,live,target=dict(kind='location',id=2),sphere_order=priorities)
        self.assertIn('Z key a',data['combination_candidates']);self.assertIn('Z key b',data['combination_candidates'])
        self.assertTrue(any(row['synergy']['target'] for row in data['combinations']))
        self.assertFalse(data['combinations_complete'])
        self.assertLess(data['combinations_tested'],data['combinations_total'])
        self.assertEqual(data['combination_candidates'],self.evaluate(mw,live,target=dict(kind='location',id=2),sphere_order=priorities)['combination_candidates'])

    def test_progressive_double_copy_and_exact_valid_pair_coverage(self):
        mw,live=fixture();data=self.evaluate(mw,live)
        hammer=next(r for r in data['combinations'] if r['items'][0]['name']=='Hammer' and r['items'][0]['count']==2)
        self.assertEqual(hammer['synergy']['checks'],[3])
        self.assertEqual(data['combinations_total'],7)  # Four types: six distinct pairs + one valid self-pair.
        self.assertEqual(data['combinations_tested'],7)
        self.assertTrue(data['combinations_complete'])
        short=self.evaluate(mw,live,max_pairs=1)
        self.assertEqual(short['combinations_tested'],1)
        self.assertFalse(short['combinations_complete'])

    def test_budget_expiring_during_pair_search_retains_only_completed_evidence(self):
        mw,live=fixture();clock=SimpleNamespace(now=0)
        regions=mw.get_regions(1)
        def progressive(state):
            if state.has('Hammer',1,2) and not state.has('A',1) and not state.has('B',1):clock.now=100
            return state.has('Hammer',1,2)
        regions[2].can_reach=progressive
        with patch('progression_model.time.monotonic',side_effect=lambda:clock.now):
            data=self.evaluate(mw,live,seconds=10)
        self.assertGreater(data['combinations_tested'],0)
        self.assertLess(data['combinations_tested'],data['combinations_total'])
        self.assertFalse(data['combinations_complete'])
        self.assertTrue(all(any(r['synergy'].values()) for r in data['combinations']))
