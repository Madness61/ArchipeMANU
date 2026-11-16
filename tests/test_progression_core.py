"""Algorithm unit tests with a small AP-compatible rule fixture, not real games."""
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from progression_model import Unsupported, analyze


class RuleState:
    def __init__(self,mw):
        self.mw=mw;self.items={1:Counter(),2:Counter()};self.seen=set()
        for items in mw.precollected_items.values():
            for item in items:self.collect(item,True)
    def has(self,name,pid,count=1):return self.items[pid][name]>=count
    def collect(self,item,prevent_sweep=False):self.items[item.player][item.name]+=1
    def copy(self):
        new=RuleState(self.mw);new.items=deepcopy(self.items);new.seen=set(self.seen);return new
    def sweep_for_advancements(self,locations):
        changed=True
        while changed:
            changed=False
            for loc in locations:
                if loc not in self.seen and loc.can_reach(self):
                    self.seen.add(loc);self.collect(loc.item,True);changed=True


def item(name,code,player=1,advancement=True):
    return SimpleNamespace(name=name,code=code,player=player,advancement=advancement)


class Location:
    def __init__(self,pid,address,name,value,rule=lambda state:True,region='Start'):
        self.player,self.address,self.name,self.item=pid,address,name,value
        self.parent_region=SimpleNamespace(name=region)
        self.can_reach=rule


def fixture(gate=None,starts=None):
    gate=gate or (lambda s:s.has('A',1) and s.has('B',1))
    rows=[Location(1,1,'Open chest',item('Filler',90,advancement=False)),
          Location(1,2,'Locked chest',item('Filler',90,advancement=False),gate,'Gate'),
          Location(1,3,'Progressive chest',item('Filler',90,advancement=False),lambda s:s.has('Hammer',1,2),'Upper'),
          Location(1,None,'Goal event',item('Victory',None),gate,'Gate'),
          Location(2,10,'Remote A',item('A',10)),Location(2,11,'Remote B',item('B',11)),
          Location(2,12,'Remote C',item('C',12)),Location(2,13,'Hammer one',item('Hammer',13)),
          Location(2,14,'Hammer two',item('Hammer',13))]
    regions=[SimpleNamespace(name='Start',can_reach=lambda s:True),SimpleNamespace(name='Gate',can_reach=gate),
             SimpleNamespace(name='Upper',can_reach=lambda s:s.has('Hammer',1,2))]
    mw=SimpleNamespace(groups={},player_ids=(1,2),precollected_items={1:starts or [],2:[]})
    mw.get_filled_locations=lambda pid=None:[r for r in rows if pid is None or r.player==pid]
    mw.get_regions=lambda pid:regions
    mw.has_beaten_game=lambda state,pid:state.has('Victory',pid)
    live=dict(slot=1,team=0,received=[],checked=[],missing=[1,2,3])
    return mw,live


class GenericRuleTests(unittest.TestCase):
    def evaluate(self,mw,live,**kwargs):
        with patch.dict('sys.modules',{'BaseClasses':SimpleNamespace(CollectionState=RuleState)}):
            return analyze(mw,live,**kwargs)

    def test_pair_opens_gate_without_collecting_unsent_remote_items(self):
        mw,live=fixture();result=self.evaluate(mw,live)
        self.assertEqual([r['id'] for r in result['reachable']],[1])
        singles={r['items'][0]['name']:r for r in result['singles']}
        self.assertEqual(singles['A']['new_checks'],[]);self.assertEqual(singles['B']['new_checks'],[])
        pair=next(r for r in result['combinations'] if {i['name'] for i in r['items']}=={'A','B'})
        self.assertEqual(pair['new_checks'],[2]);self.assertEqual(pair['new_regions'],['Gate'])
        self.assertTrue(pair['goal_reachable'])

    def test_progressive_copies_and_start_inventory_counted_once(self):
        mw,live=fixture(starts=[item('Hammer',13)])
        live['received']=[dict(item=13,location=-2,player=0,flags=1)]
        result=self.evaluate(mw,live)
        self.assertEqual([r['id'] for r in result['reachable']],[1])
        hammer=next(r for r in result['singles'] if r['items'][0]['name']=='Hammer')
        self.assertEqual(hammer['new_checks'],[3])
        mw,live=fixture();result=self.evaluate(mw,live)
        pair=next(r for r in result['combinations'] if r['items']==[dict(name='Hammer',count=2,locations=[dict(finder=2,location_id=13),dict(finder=2,location_id=14)])])
        self.assertEqual(pair['new_checks'],[3])

    def test_received_remote_items_events_completed_checks_and_target(self):
        mw,live=fixture();live['received']=[dict(item=10,location=10,player=2,flags=1),dict(item=11,location=11,player=2,flags=1)]
        live['checked']=[1];live['missing']=[2,3]
        result=self.evaluate(mw,live,target=dict(kind='location',id=3))
        self.assertTrue(result['goal_reachable'])
        self.assertEqual([r['id'] for r in result['reachable']],[2])
        self.assertNotIn('A',[r['items'][0]['name'] for r in result['singles']])
        hammer=next(r for r in result['combinations'] if r['items'][0]['name']=='Hammer' and r['items'][0]['count']==2)
        self.assertTrue(hammer['target_reached'])

    def test_necessity_uses_reachable_chains_and_alternative_paths(self):
        mw,live=fixture();result=self.evaluate(mw,live)
        self.assertEqual({r['item'] for r in result['necessity'] if r['verdict']=='necessary'},{'A','B'})
        mw,live=fixture(gate=lambda s:s.has('A',1) or s.has('C',1));result=self.evaluate(mw,live)
        verdict={r['item']:r['verdict'] for r in result['necessity']}
        self.assertEqual(verdict['A'],'replaceable_copy');self.assertEqual(verdict['C'],'replaceable_copy')

    def test_item_links_unknown_checks_receipts_and_missing_start_fail_closed(self):
        for reason in ('item_links','incomplete_checks','unmatched_receipt','incomplete_start_inventory','unmatched_synthetic_item'):
            mw,live=fixture()
            if reason=='item_links':mw.groups={3:{'players':{1,2}}}
            if reason=='incomplete_checks':live['missing']=[1]
            if reason=='unmatched_receipt':live['received']=[dict(item=11,location=10,player=2,flags=1)]
            if reason=='incomplete_start_inventory':mw.precollected_items[1]=[item('A',10)]
            if reason=='unmatched_synthetic_item':live['received']=[dict(item=10,location=-2,player=0,flags=1)]
            with self.subTest(reason=reason),self.assertRaisesRegex(Unsupported,reason):self.evaluate(mw,live)

    def test_limits_report_incomplete_instead_of_claiming_no_solution(self):
        mw,live=fixture();result=self.evaluate(mw,live,seconds=-1)
        self.assertFalse(result['singles_complete']);self.assertFalse(result['combinations_complete'])
        self.assertFalse(result['necessity_complete']);self.assertEqual(result['singles'],[])
