"""Logic privacy, explicit spoilers, immutable inputs and cache invalidation."""
from concurrent.futures import Future
import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
import yaml

from hub import config, db, logic_tracker, mvp
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

    def test_retired_routes_never_evaluate_or_expose_placements(self):
        url, _ = self.seed()
        with patch.object(logic_tracker, 'status') as evaluate, patch.object(logic_tracker, 'install_engine') as install:
            self.assertEqual(self.client.get(url).status_code,410)
            for suffix in ('data','refresh','placements','install'):
                response=self.client.get(url+'/data') if suffix=='data' else self.post(url+'/'+suffix,{})
                self.assertEqual(response.status_code,410)
                self.assertEqual(response.get_json()['state'],'disabled')
                self.assertNotIn('placements',response.get_json())
            evaluate.assert_not_called();install.assert_not_called()
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
        self.assertEqual(self.post(url+'/placements', {}).status_code,410)
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

    def test_skyward_patch_passes_only_layout_for_exact_slot(self):
        fields={key:{} for key in ('Options','Batreaux Rewards','Trial Entrances','Starting Statues','Starting Entrance')}
        fields.update({'Required Dungeons':['Skyview'],'Entrances':[['Exit','Entry']],
                       'Locations':{'Secret chest':'Secret item'},'Hints':['Secret hint'],
                       'Name':'Private name','All Players':['Private players']})
        inner=io.BytesIO()
        with zipfile.ZipFile(inner,'w') as z:
            z.writestr('archipelago.json',json.dumps(dict(player=2,game='Skyward Sword')))
            z.writestr('plando',base64.b64encode(yaml.safe_dump(fields).encode()))
        folder=config.SESSIONS/'_seeds'/'9'/'output';folder.mkdir(parents=True)
        with zipfile.ZipFile(folder/'test.zip','w') as z:z.writestr('player.apssr',inner.getvalue())
        layout=logic_tracker.skyward_layout(dict(id=9,zip_name='test.zip'),2)
        self.assertEqual(layout['Required Dungeons'],['Skyview'])
        encoded=json.dumps(layout)
        for secret in ['Secret item','Secret hint','Private name','Private players','Locations','Hints']:
            self.assertNotIn(secret,encoded)
        self.assertIsNone(logic_tracker.skyward_layout(dict(id=9,zip_name='test.zip'),1))


if __name__ == '__main__':
    unittest.main()
