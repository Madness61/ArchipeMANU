"""Logic privacy, explicit spoilers, immutable inputs and cache invalidation."""
from concurrent.futures import Future
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hub import db, logic_tracker, mvp
import test_mvp as fixtures


class LogicTests(unittest.TestCase):
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    post = fixtures.MVPTests.post

    def seed(self, race=False, spoiler=1):
        self.post('/login', {'username': 'Host'})
        with self.app.app_context():
            sid = db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Logic',1,1)")
            bid = db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,'succeeded',?,'today')",
                (sid, db.dumps(dict(race=race, spoiler=spoiler, slots=[dict(slot='Host', player_id=1, game='test_world', game_name='Test World')]))))
        return f'/sessions/{sid}/builds/{bid}/live/logic', bid

    def test_api_is_private_and_spoilers_are_only_explicit(self):
        url, _ = self.seed()
        ready = dict(state='ready', go_mode=False, reachable=1, remaining=2, locations=[dict(id=3,name='A',region='Start',reachable=True,checked=False)], inventory=[])
        with patch('hub.logic_routes.console_routes.client', return_value=SimpleNamespace(endpoint={'id':1})), \
             patch.object(logic_tracker, 'evaluation_input', return_value=({},None)), \
             patch.object(logic_tracker, 'status', return_value=ready):
            response = self.client.get(url+'/data')
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('item', response.get_data(as_text=True))
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertEqual(self.client.get(url+'/data?slot=Friend').status_code,403)
            self.assertEqual(self.client.post(url+'/refresh').status_code,403)
            self.assertEqual(self.post(url+'/refresh', {}).status_code,200)
        with patch.object(mvp,'_build_distribution',return_value={}), \
             patch.object(mvp,'_build_placements',return_value=[dict(finder=1,recipient=1,location_id=3,item='Secret key')]):
            response=self.post(url+'/placements', {})
            self.assertIn('Secret key',response.get_data(as_text=True))
        self.assertEqual(self.app.test_client().get(url+'/data').status_code,401)

    def test_race_no_slot_and_spoiler_setting_are_enforced(self):
        url,bid=self.seed(race=True)
        self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.post(url+'/refresh', {}).status_code,403)
        self.assertEqual(self.post(url+'/placements', {}).status_code,403)
        with self.app.app_context():
            row=db.loads(db.query('SELECT snapshot FROM seed_builds WHERE id=?',(bid,),one=True)['snapshot'])
            row.update(race=False,spoiler=0)
            db.execute('UPDATE seed_builds SET snapshot=? WHERE id=?',(db.dumps(row),bid))
        self.assertEqual(self.post(url+'/placements', {}).status_code,403)
        self.friend=self.app.test_client()
        self.post('/login',{'username':'Friend'},client=self.friend)
        with self.app.app_context():
            db.execute('INSERT INTO lobby_members(session_id,user_id) SELECT session_id,2 FROM seed_builds WHERE id=?',(bid,))
        self.assertEqual(self.friend.get(url+'/data').status_code,403)

    def test_cache_never_reuses_old_logic_for_changed_items_or_endpoint(self):
        identity=('isolated-test',1,1,'auth',1,'slot')
        ready=Future();ready.set_result(dict(state='ready',go_mode=True))
        try:
            with patch.object(logic_tracker._pool,'submit',return_value=ready):
                self.assertEqual(logic_tracker.status(identity,{'items':[]},True)['state'],'loading')
                self.assertTrue(logic_tracker.status(identity,{'items':[]})['go_mode'])
                self.assertEqual(logic_tracker.status(identity,{'items':[1]})['state'],'stale')
                self.assertEqual(logic_tracker.status((*identity[:-2],2,'slot'),{'items':[]})['state'],'idle')
        finally:
            logic_tracker._jobs.pop(identity,None)

    def test_engine_missing_and_disconnected_never_report_go_mode(self):
        with patch.object(logic_tracker,'engine_ready',return_value=False):
            value,error=logic_tracker.evaluation_input({}, {}, None)
            self.assertIsNone(value)
            self.assertEqual(error['state'],'engine_missing')
            self.assertNotIn('go_mode',error)
        with patch.object(logic_tracker,'engine_ready',return_value=True), \
             patch.object(logic_tracker.ap_bridge,'ap_ready',return_value=True), \
             patch.object(logic_tracker.ap_bridge,'trusted_custom_execution',return_value=True):
            _,error=logic_tracker.evaluation_input({}, {'slot':'Host'}, None)
            self.assertEqual(error['state'],'not_connected')


if __name__ == '__main__':
    unittest.main()
