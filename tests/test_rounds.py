"""Central round navigation and conservative personal patch attribution."""
import io
import json
import zipfile
import unittest

import test_mvp as fixtures
from hub import config, db, mvp, rounds


class RoundTests(unittest.TestCase):
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    post = fixtures.MVPTests.post

    def seed(self):
        self.post('/login', {'username':'Host'})
        self.post('/sessions', {'name':'One central round'})
        with self.app.app_context():
            slots=[dict(slot='Host',player_id=1,game='test_world',game_name='Test World',game_version='1.0')]
            bid=db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at,seed_name,zip_name) VALUES (1,'succeeded',?,CURRENT_TIMESTAMP,'AP_TEST','AP_TEST.zip')",(json.dumps({'slots':slots}),))
            db.execute('UPDATE sessions SET locked=1 WHERE id=1')
        return bid, slots

    def test_one_dashboard_card_three_main_links_and_old_urls(self):
        bid,slots=self.seed()
        page=self.client.get('/').get_data(as_text=True)
        self.assertEqual(page.count('data-round-id="1"'),1)
        nav=page.split('id="main-navigation"',1)[1].split('</nav>',1)[0]
        self.assertEqual(nav.count('<a '),3)
        for url in ('/rounds','/lobbies',f'/sessions/1',f'/sessions/1/builds/{bid}/play'):
            self.assertEqual(self.client.get(url).status_code,200,url)
        for url in ('/sessions/1',f'/sessions/1/builds/{bid}/play'):
            page=self.client.get(url).get_data(as_text=True)
            self.assertIn('id="round-center"',page)
            self.assertEqual(page.count('data-round-panel='),4)
            self.assertIn('id="slot-1">Host',page)

    def test_reopened_lobby_prioritizes_preparation_and_explicit_history_keeps_seed(self):
        bid,_=self.seed()
        self.post('/sessions/1/lock',{})
        page=self.client.get('/sessions/1').get_data(as_text=True)
        self.assertIn('data-phase="preparation"',page)
        self.assertIn('id="game-selection"',page)
        self.assertIn('data-phase="running"',self.client.get(f'/sessions/1?build={bid}').get_data(as_text=True))
        self.assertEqual(self.client.get('/sessions/1?build=999').status_code,404)

    def test_patch_identity_uses_manifest_or_exact_generator_name_never_substrings(self):
        bid,slots=self.seed()
        output=config.SESSIONS/'_seeds'/str(bid)/'output'
        output.mkdir(parents=True)
        def patch(name,player=17):
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as z:
                z.writestr('archipelago.json',json.dumps(dict(game='Test World',player=player,player_name=name)))
            return data.getvalue()
        with zipfile.ZipFile(output/'AP_TEST.zip','w') as archive:
            archive.writestr('renamed.apssr',patch('Host'))
            archive.writestr('someone-Host.apssr',patch('Other'))
            archive.writestr('AP_TEST_P17_Host.apdelta',b'legacy patch')
            archive.writestr('AP_TEST_P1_Host.apdelta',b'wrong player id')
            archive.writestr('Host_Spoiler.txt',b'SECRET')
        with self.app.app_context():
            build=db.query('SELECT * FROM seed_builds WHERE id=?',(bid,),one=True)
            files=mvp.artifact_files(bid,build['zip_name'])
            result=rounds.personal_files(build,slots,files,dict(players=[dict(id=17,name='Host',game='Test World')]))
            self.assertEqual([a['name'] for a in result['Host']],['renamed.apssr','AP_TEST_P17_Host.apdelta'])

    def test_completed_round_has_no_prepare_or_host_connection_forms(self):
        bid,_=self.seed()
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET completed_at='done' WHERE id=?",(bid,))
        page=self.client.get('/sessions/1').get_data(as_text=True)
        self.assertIn('data-phase="completed"',page)
        self.assertNotIn('id="select-game"',page)
        self.assertNotIn('id="round-host-connection"',page)
        self.assertNotIn('id="round-slot-connect"',page)
        self.assertIn('Gemeinsame Spieldateien',page)
