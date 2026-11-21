"""Seed-wide finder, consent/identity guards, observations and bounded job cache."""
from concurrent.futures import Future
import hashlib
import json
import subprocess
import time
from unittest.mock import patch
import unittest

import test_mvp as fixtures
from hub import ap_bridge, config, db, progression


class FinderTests(unittest.TestCase):
    setUpBase,tearDown,post=fixtures.MVPTests.setUp,fixtures.MVPTests.tearDown,fixtures.MVPTests.post

    def setUp(self):
        self.setUpBase()
        self.post('/login',{'username':'Host'})
        self.friend=self.app.test_client(); self.post('/login',{'username':'Friend'},client=self.friend)
        self.outsider=self.app.test_client(); self.post('/login',{'username':'Other'},client=self.outsider)
        self.players=[dict(id=1,name='Host',game='Game A'),dict(id=2,name='Friend',game='Game B')]
        self.rows=[dict(finder=f,recipient=r,location_id=n,item_id=i,category=c,item=item,location=loc)
                   for f,r,n,i,c,item,loc in [(1,2,10,50,'progression','Key','Tower'),
                       (2,1,20,51,'progression','Sword','Cave'),(2,1,21,51,'progression','Sword','Garden'),
                       (1,1,11,52,'useful','Potion','Village'),(2,2,22,53,'trap','Boo','Basement'),
                       (2,2,23,54,'filler','Coin','Roof')]]
        from hub.stats import aggregate_placements
        summary=aggregate_placements(self.players,[(r['finder'],r['recipient'],r['category']) for r in self.rows])
        with self.app.app_context():
            self.sid=db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Finder',1,1)")
            db.execute('INSERT INTO lobby_members(session_id,user_id) VALUES (?,2)',(self.sid,))
            snap=dict(slots=[dict(slot='Host',game_name='Game A',game='a',player_id=1),
                             dict(slot='Friend',game_name='Game B',game='b',player_id=2)],race=False)
            self.bid=db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at,stats_json) VALUES (?,'succeeded',?,'today',?)",(self.sid,db.dumps(snap),db.dumps(summary)))
            self.hid=db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,'127.0.0.1',1234,1,'today')",(self.bid,))
        self.output=config.SESSIONS/'_seeds'/str(self.bid)/'output';self.output.mkdir(parents=True)
        self.output.joinpath('item_placements.json').write_text(db.dumps(dict(source=summary['source'],placements=self.rows)),encoding='utf-8')
        self.url=f'/sessions/{self.sid}/builds/{self.bid}/progression'

    def grant(self,client=None):
        self.assertEqual(self.post(self.url+'/consent',{'reveal':'1'},client=client).status_code,200)

    def test_global_search_all_fields_filters_copies_and_no_implicit_spoilers(self):
        with patch.object(progression._pool,'submit') as submit:
            page=self.client.get(self.url)
            self.assertEqual(page.status_code,200)
            self.assertNotIn(b'Garden',page.data)
            self.assertEqual(self.client.get(self.url+'/items').status_code,403)
            self.grant()
            for text,count in [('Sword',2),('Game B',5),('Garden',1),('Friend',5),('not present',0)]:
                data=self.client.get(self.url+'/items',query_string={'q':text}).json
                self.assertEqual(data['total'],count,text)
            self.assertEqual(self.client.get(self.url+'/items?owner=mine').json['total'],3)
            for category,count in [('progression',3),('useful',1),('filler',1),('trap',1)]:
                self.assertEqual(self.client.get(self.url+'/items?category='+category).json['total'],count)
            self.assertEqual(self.friend.get(self.url+'/items').status_code,403)
            submit.assert_not_called()

    def test_compact_search_pagination_is_bounded_and_spoiler_gated(self):
        self.assertEqual(self.client.get(self.url+'/items?limit=2').status_code,403)
        self.grant()
        first=self.client.get(self.url+'/items?limit=2').json
        second=self.client.get(self.url+'/items?limit=2&page=2').json
        self.assertEqual((first['total'],first['pages'],len(first['rows'])),(6,3,2))
        self.assertFalse({row['id'] for row in first['rows']} & {row['id'] for row in second['rows']})
        for value in ('-1','0','51','abc'):
            self.assertEqual(self.client.get(self.url+'/items?limit='+value).status_code,400)

    def test_player_sheet_groups_exact_copies_and_preserves_spoiler_permissions(self):
        with self.app.app_context():
            inventory = dict(checked=[10], missing=[11], received=[dict(item=51, location=20, player=2, flags=1)])
            db.execute('INSERT INTO progression_live VALUES (?,?,?,?,?,?)',
                       (self.bid, 'Host', self.hid, 1, db.dumps(inventory), time.time()))
        url = self.url + '/items?recipient=Host'
        grouped = self.friend.get(url).json['rows']
        self.assertEqual(grouped, [dict(name='Sword', total=2, received=1, not_received=1, unknown=0,found=0,recipient='Host')])
        self.assertEqual(self.friend.get(url + '&q=Cave').json['total'], 0)
        self.assertEqual(self.friend.get(url + '&receipt=not_received').json['rows'], grouped)
        self.assertEqual(self.friend.get(url + '&receipt=unknown').json['rows'], [])
        self.assertEqual(self.outsider.get(url).status_code, 403)
        self.assertEqual(self.client.get(self.url + '/items?recipient=Unknown').status_code, 400)
        self.grant(self.friend)
        copies = self.friend.get(url).json['rows'][0]['copies']
        self.assertEqual([(copy['finder'], copy['location'], copy['status']) for copy in copies],
                         [('Friend', 'Cave', 'received'), ('Friend', 'Garden', 'not_received')])
        self.assertNotIn('copies', self.client.get(url).json['rows'][0])
        self.assertEqual(self.friend.get(self.url + '/analysis?slot=Host').status_code, 403)
        with self.app.app_context():
            snapshot = db.loads(db.query('SELECT snapshot FROM seed_builds WHERE id=?', (self.bid,), one=True)['snapshot'])
            snapshot['race'] = True
            db.execute('UPDATE seed_builds SET snapshot=? WHERE id=?', (db.dumps(snapshot), self.bid))
        self.assertEqual(self.friend.get(url).status_code, 403)

    def test_help_and_found_views_are_spoiler_gated_and_never_start_analysis(self):
        from hub.services.console_journal import record
        with self.app.app_context():
            record(config.DB_PATH, self.bid,None,'items',
                dict(type='item',sender='Friend',recipient='Host',sender_game='Game B',recipient_game='Game A',
                     item_id=51,location_id=20,source='live'),hosted_id=self.hid)
        url = self.url+'/items?recipient=Friend&focus=help'
        with patch.object(progression._pool,'submit') as submit:
            hidden=self.client.get(url).json
            self.assertEqual(hidden['rows'],[])
            self.assertNotIn('help',hidden['counts'])
            self.grant()
            help_rows=self.client.get(url).json['rows']
            self.assertEqual(help_rows[0]['recipient'],'Host')
            self.assertEqual(help_rows[0]['found'],1)
            found=self.client.get(self.url+'/items?recipient=Host&focus=found').json
            self.assertEqual(found['rows'][0]['name'],'Sword')
            self.assertTrue(all(copy['check_status']=='checked' for copy in found['rows'][0]['copies']))
            submit.assert_not_called()
    def test_observed_checks_and_exact_receipts_are_distinct_and_copies_stay_separate(self):
        now=time.time()
        with self.app.app_context():
            for name,pid,payload in [('Host',1,dict(slot=1,team=0,received=[dict(item=51,location=20,player=2,flags=1)],checked=[10],missing=[11])),
                                     ('Friend',2,dict(slot=2,team=0,received=[],checked=[20,21],missing=[22,23]))]:
                db.execute('INSERT INTO progression_live VALUES (?,?,?,?,?,?)',(self.bid,name,self.hid,pid,db.dumps(payload),now))
        self.grant()
        data=self.client.get(self.url+'/items?q=Sword').json['rows']
        self.assertEqual([r['check_status'] for r in data],['checked','checked'])
        self.assertEqual([r['receipt_status'] for r in data],['received','not_received'])
        self.assertTrue(all(r['check_at']==now for r in data))
        self.assertEqual(self.client.get(self.url+'/items?status=checked').json['total'],3)
        self.assertEqual(self.client.get(self.url+'/items?status=unchecked').json['total'],3)
        with self.app.app_context():
            db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,'127.0.0.1',3456,1,'later')",(self.bid,))
        self.assertEqual(self.client.get(self.url+'/items?status=unknown').json['total'],6)

    def test_historical_missing_corrupt_placements_and_completed_round(self):
        self.grant()
        self.assertEqual(self.client.get(self.url+'/analysis').json['reason'],'historical_seed')
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET completed_at='today' WHERE id=?",(self.bid,))
        self.assertEqual(self.client.get(self.url+'/items').json['total'],6)
        self.output.joinpath('item_placements.json').write_text('{"placements":[]}',encoding='utf-8')
        self.assertFalse(self.client.get(self.url+'/items').json['available'])

    def test_cross_world_journal_proves_a_find_and_only_exact_receipts(self):
        from hub.services.console_journal import record
        with self.app.app_context():
            base = dict(type='item', sender='Friend', recipient='Host', item_id=51)
            record(config.DB_PATH, self.bid, None, 'items', dict(base, location_id=20, source='live'),
                   hosted_id=self.hid)
            record(config.DB_PATH, self.bid, None, 'items', dict(base, location_id=21, source='received_items'),
                   hosted_id=self.hid)
            record(config.DB_PATH, self.bid, None, 'items', dict(base, location_id=22, item_id=53, source='live'),
                   hosted_id=self.hid)  # The recorded recipient does not match this placement.
        self.grant()
        rows = self.client.get(self.url + '/items?q=Sword').json['rows']
        self.assertEqual([row['check_status'] for row in rows], ['checked', 'checked'])
        self.assertEqual([row['receipt_status'] for row in rows], ['unknown', 'received'])
        self.assertEqual(self.client.get(self.url + '/items?q=Boo').json['rows'][0]['check_status'], 'unknown')
        with self.app.app_context():
            db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,'127.0.0.1',3456,1,'later')",(self.bid,))
        self.assertEqual(self.client.get(self.url + '/items?status=unknown').json['total'], 6)

    def test_auth_csrf_own_slot_consent_revocation_race_and_direct_urls(self):
        self.assertEqual(self.app.test_client().get(self.url+'/items').status_code,401)
        self.assertEqual(self.outsider.get(self.url+'/state').status_code,403)
        self.assertEqual(self.client.post(self.url+'/consent',data={'reveal':'1'}).status_code,403)
        self.grant()
        self.assertEqual(self.client.get(self.url+'/analysis?slot=Friend').status_code,403)
        self.assertEqual(self.client.post(self.url+'/analysis').status_code,403)
        for args in ('category=bad','status=bad','owner=bad','page=0','page=x'):
            self.assertEqual(self.client.get(self.url+'/items?'+args).status_code,400)
        self.post(self.url+'/consent',{'reveal':'0'})
        self.assertEqual(self.client.get(self.url+'/items').status_code,403)
        self.grant()
        with self.app.app_context():
            snap=db.loads(db.query('SELECT snapshot FROM seed_builds WHERE id=?',(self.bid,),one=True)['snapshot']);snap['race']=True
            db.execute('UPDATE seed_builds SET snapshot=? WHERE id=?',(db.dumps(snap),self.bid))
        for suffix in ('','/state','/items','/analysis'):
            self.assertEqual(self.client.get(self.url+suffix).status_code,403)
        self.assertEqual(self.post(self.url+'/analysis',{}).status_code,403)

    def test_cache_invalidates_on_inventory_or_target_and_get_never_starts_job(self):
        self.grant()
        data=dict(manifest={'seed':1},yamls={},live={'received':[]},observed_at=time.time())
        def submit(fn):
            future=Future();fn();future.set_result(None);return future
        with patch.object(progression,'prepare',side_effect=lambda *a:(dict(data),None)), \
             patch.object(progression,'manifest',return_value=None), \
             patch.object(progression._pool,'submit',side_effect=submit) as submitted, \
             patch.object(progression,'run_worker',return_value=dict(state='unsupported',reason='item_links')) as worker, \
             patch.object(ap_bridge,'ap_ready',return_value=True),patch.object(ap_bridge,'trusted_custom_execution',return_value=True):
            self.assertEqual(self.client.get(self.url+'/analysis').json['state'],'idle')
            submitted.assert_not_called()
            self.assertEqual(self.post(self.url+'/analysis',{}).json['state'],'loading')
            self.assertEqual(self.client.get(self.url+'/analysis').json['reason'],'item_links')
            self.post(self.url+'/analysis',{})
            self.assertEqual(worker.call_count,1)
            data['live']={'received':[{'item':1}]}
            self.assertEqual(self.client.get(self.url+'/analysis').json['state'],'idle')
            self.post(self.url+'/analysis',{})
            self.post(self.url+'/analysis',{'target_kind':'location','target_id':'20'})
            self.assertEqual(worker.call_count,3)

    def test_worker_timeout_returns_safe_fallback_without_details(self):
        with patch('hub.progression.subprocess.run',side_effect=subprocess.TimeoutExpired('private command',90)):
            result=progression.run_worker(dict(yamls={},manifest={}))
        self.assertEqual(result,dict(state='unsupported',reason='timeout'))

    def test_goal_mode_requires_explicit_post_and_has_independent_cache(self):
        self.grant()
        data=dict(manifest={'seed':1},yamls={},live={'received':[]},observed_at=time.time())
        def submit(fn):
            future=Future();fn();future.set_result(None);return future
        def evaluate(payload):
            return dict(state='ready',mode=payload['mode'],singles=[],necessity=[])
        with patch.object(progression,'prepare',side_effect=lambda *a:(dict(data),None)), \
             patch.object(progression,'manifest',return_value=None), \
             patch.object(progression._pool,'submit',side_effect=submit) as submitted, \
             patch.object(progression,'run_worker',side_effect=evaluate) as worker, \
             patch.object(ap_bridge,'ap_ready',return_value=True),patch.object(ap_bridge,'trusted_custom_execution',return_value=True):
            self.assertEqual(self.client.get(self.url+'/analysis?mode=goal').json['state'],'idle')
            submitted.assert_not_called()
            self.assertEqual(self.post(self.url+'/analysis',{}).json['state'],'loading')
            self.assertEqual(self.client.get(self.url+'/analysis').json['mode'],'items')
            self.assertEqual(self.client.get(self.url+'/analysis?mode=goal').json['state'],'idle')
            self.assertEqual(worker.call_count,1)
            self.assertEqual(self.post(self.url+'/analysis',{'mode':'goal'}).json['state'],'loading')
            self.assertEqual(self.client.get(self.url+'/analysis?mode=goal').json['mode'],'goal')
            self.assertEqual(self.client.get(self.url+'/analysis').json['mode'],'items')
            self.assertEqual(worker.call_count,2)
            self.assertEqual(self.client.get(self.url+'/analysis?mode=pairs').status_code,400)
            self.assertEqual(self.post(self.url+'/analysis',{'mode':'pairs'}).status_code,400)

    def test_old_algorithm_cache_is_not_reused_for_current_recommendations(self):
        from progression_model import digest
        data=dict(manifest={'seed':1},yamls={},live={'received':[]},observed_at=time.time())
        old={k:v for k,v in data.items() if k!='observed_at'};old['target']=None
        with self.app.app_context():
            db.execute('''INSERT INTO progression_jobs(build_id,user_id,slot_name,signature,state,result,created_at,finished_at)
                          VALUES (?,1,'Host',?,'ready',?,?,?)''',
                       (self.bid,digest(old),db.dumps(dict(state='ready',old_algorithm=True)),time.time(),time.time()))
        self.grant()
        with patch.object(progression,'prepare',side_effect=lambda *args:(dict(data),None)), \
             patch.object(progression,'manifest',return_value=None),patch.object(progression._pool,'submit') as start:
            response=self.client.get(self.url+'/analysis').json
            self.assertEqual(response['state'],'idle')
            self.assertNotIn('old_algorithm',response)
            start.assert_not_called()

    def test_verified_webhost_cache_supplies_checks_and_receipts_without_polling(self):
        now=time.time()
        with self.app.app_context():
            db.execute("INSERT INTO live_rooms(build_id,room_id,tracker_id,active,room_json,created_at) VALUES (?,'room','tracker',1,?,?)",
                       (self.bid,db.dumps(dict(players=[[p['name'],p['game']] for p in self.players])),now))
            static=dict(player_game=[dict(team=0,player=p['id'],game=p['game']) for p in self.players],
                        player_locations_total=[dict(team=0,player=1,total_locations=2),dict(team=0,player=2,total_locations=4)])
            dynamic=dict(player_checks_done=[dict(team=0,player=1,locations=[10]),dict(team=0,player=2,locations=[20])],
                player_items_received=[dict(team=0,player=1,items=[[51,20,2,1]]),dict(team=0,player=2,items=[])])
            for name,payload in [('static_tracker',static),('tracker',dynamic)]:
                db.execute('INSERT INTO live_api_cache(endpoint,identifier,payload,fetched_at) VALUES (?,?,?,?)',(name,'tracker',db.dumps(payload),now))
        self.grant()
        from hub import live_api
        with patch.object(live_api,'fetch') as network:
            data=self.client.get(self.url+'/items?q=Sword').json['rows']
            self.assertEqual([r['check_status'] for r in data],['checked','unchecked'])
            self.assertEqual([r['receipt_status'] for r in data],['received','not_received'])
            with self.app.app_context():
                db.execute('UPDATE live_rooms SET room_json=?',(db.dumps(dict(players=[['Wrong','Game A'],['Friend','Game B']])),))
            self.assertTrue(all(r['check_status']=='unknown' for r in self.client.get(self.url+'/items').json['rows']))
            network.assert_not_called()

    def test_static_manifest_checksum_and_missing_yaml_fail_closed(self):
        from progression_model import digest
        model=dict(players=self.players,locations=[dict(player=r['finder'],id=r['location_id'],item=dict(player=r['recipient'],id=r['item_id'])) for r in self.rows])
        evidence=dict(version=1,source='archipelago_generated_logic',seed=123,model=model,model_hash=digest(model),yamls={'a.yaml':hashlib.sha256(b'test').hexdigest()})
        self.output.joinpath('progression_seed.json').write_text(db.dumps(evidence),encoding='utf-8')
        with self.app.app_context():
            self.assertIsNotNone(progression.manifest(db.query('SELECT * FROM seed_builds WHERE id=?',(self.bid,),one=True)))
        evidence['model']['players'][0]['name']='Changed'
        self.output.joinpath('progression_seed.json').write_text(db.dumps(evidence),encoding='utf-8')
        with self.app.app_context():
            self.assertIsNone(progression.manifest(db.query('SELECT * FROM seed_builds WHERE id=?',(self.bid,),one=True)))
