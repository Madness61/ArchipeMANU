"""Production single-item path: complete coverage, exact copies and explicit goals."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from progression_model import analyze, Unsupported
from test_progression_core import fixture, RuleState, Location, item


class SingleItemTests(unittest.TestCase):
    def evaluate(self, mw, live, **kwargs):
        with patch.dict('sys.modules', {'BaseClasses': SimpleNamespace(CollectionState=RuleState)}):
            return analyze(mw, live, **kwargs)

    def test_no_pairs_goal_probes_or_full_inventory_sweeps(self):
        mw, live = fixture()
        mw.has_beaten_game = lambda *args: self.fail('Regular help must not evaluate completion')
        with patch('progression.extensions.combinations.analyze', side_effect=AssertionError('Pair engine used')), \
             patch('progression.goals.analyze_goal', side_effect=AssertionError('Goal engine used')):
            result = self.evaluate(mw, live)
        self.assertEqual(result['singles_tested'], 4)
        self.assertNotIn('combinations', result)
        self.assertNotIn('necessity', result)
        self.assertEqual([r['id'] for r in result['reachable']], [1])
        self.assertTrue(all(not r['helpful'] for r in result['singles']))

    def test_all_missing_types_beyond_forty_and_alphabetical_ties(self):
        mw, live = fixture()
        rows = mw.get_filled_locations()
        rows.extend(Location(2, 100+i, str(i), item('Extra %02d' % i, 100+i)) for i in range(55))
        mw.get_filled_locations = lambda pid=None: [r for r in rows if pid is None or r.player == pid]
        result = self.evaluate(mw, live)
        names = [r['items'][0]['name'] for r in result['singles']]
        self.assertEqual(result['candidates_total'], 59)
        self.assertEqual(result['singles_tested'], 59)
        self.assertTrue(result['singles_complete'])
        self.assertEqual(names, sorted(names, key=lambda n: (n.casefold(), n)))

    def test_checks_then_regions_then_name_and_region_only_is_helpful(self):
        mw, live = fixture(gate=lambda s: s.has('A', 1) or s.has('B', 1))
        regions = mw.get_regions(1)
        regions.append(SimpleNamespace(name='Only region', can_reach=lambda s: s.has('C', 1)))
        regions.append(SimpleNamespace(name='Extra B', can_reach=lambda s: s.has('B', 1)))
        result = self.evaluate(mw, live)
        self.assertEqual([r['items'][0]['name'] for r in result['singles']], ['B', 'A', 'C', 'Hammer'])
        self.assertTrue(result['singles'][2]['helpful'])
        self.assertEqual(result['singles'][2]['new_checks'], [])
        self.assertEqual(result['singles'][2]['new_regions'], ['Only region'])

    def test_one_copy_and_verified_receipt_are_reconciled_exactly_once(self):
        mw, live = fixture(starts=[item('Hammer', 13)])
        live['received'] = [dict(item=13, location=-2, player=0, flags=1)]
        result = self.evaluate(mw, live)
        hammer = next(r for r in result['singles'] if r['items'][0]['name'] == 'Hammer')
        self.assertEqual(hammer['new_checks'], [3])
        self.assertEqual(hammer['items'][0]['count'], 1)
        self.assertEqual(len(hammer['items'][0]['locations']), 2)
        mw, live = fixture()
        live['received'] = [dict(item=13, location=13, player=2, flags=1)]
        result = self.evaluate(mw, live)
        hammer = result['singles'][0]
        self.assertEqual(hammer['items'][0]['locations'], [dict(finder=2, location_id=14)])
        self.assertEqual(hammer['new_checks'], [3])
        self.assertEqual(len([r for r in result['singles'] if r['items'][0]['name'] == 'Hammer']), 1)

    def test_explicit_goal_mode_preserves_necessity_and_alternative_paths(self):
        for gate, expected in ((None, {'A', 'B'}), (lambda s: s.has('A', 1) or s.has('C', 1), set())):
            mw, live = fixture(gate=gate)
            result = self.evaluate(mw, live, mode='goal')
            self.assertEqual({r['item'] for r in result['necessity'] if r['verdict'] == 'necessary'}, expected)
            self.assertEqual(result['singles'], [])
            self.assertTrue(result['necessity_complete'])

    def test_budget_reports_only_completed_types_and_does_not_label_untested(self):
        mw, live = fixture()
        result = self.evaluate(mw, live, seconds=-1)
        self.assertEqual(result['singles_tested'], 0)
        self.assertEqual(result['candidates_total'], 4)
        self.assertEqual(result['singles'], [])
        self.assertFalse(result['singles_complete'])

    def test_optional_target_reuses_single_deltas_without_changing_ranking(self):
        mw, live = fixture(gate=lambda s: s.has('A', 1))
        for target in (dict(kind='location', id=2), dict(kind='region', name='Gate')):
            result = self.evaluate(mw, live, target=target)
            self.assertFalse(result['target_reachable'])
            self.assertTrue(result['singles'][0]['target_reached'])
            self.assertEqual(result['singles'][0]['items'][0]['name'], 'A')
            self.assertEqual([r['items'][0]['name'] for r in result['singles']],
                             [r['items'][0]['name'] for r in self.evaluate(mw, live)['singles']])
        live.update(checked=[2], missing=[1, 3])
        result = self.evaluate(mw, live, target=dict(kind='location', id=2))
        self.assertTrue(result['target_reachable'])
        self.assertTrue(all(r['target_reached'] for r in result['singles']))

    def test_current_engine_rejects_unverified_observations(self):
        for reason in ('item_links', 'incomplete_checks', 'unmatched_receipt', 'incomplete_start_inventory',
                       'unmatched_synthetic_item', 'identity'):
            mw, live = fixture()
            if reason == 'item_links': mw.groups = {3: {}}
            if reason == 'incomplete_checks': live['missing'] = [1]
            if reason == 'unmatched_receipt': live['received'] = [dict(item=11, location=10, player=2)]
            if reason == 'incomplete_start_inventory': mw.precollected_items[1] = [item('A', 10)]
            if reason == 'unmatched_synthetic_item': live['received'] = [dict(item=10, location=-2, player=0)]
            if reason == 'identity': live['team'] = 1
            for mode in ('items', 'goal'):
                with self.subTest(reason=reason, mode=mode), self.assertRaisesRegex(Unsupported, reason):
                    self.evaluate(mw, live, mode=mode)
