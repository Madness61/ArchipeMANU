"""Central round navigation and conservative personal patch attribution."""
import io
import json
import zipfile
import unittest
from unittest.mock import patch

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

    def test_one_dashboard_card_three_main_links_and_four_round_areas(self):
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
            for area in ('data-round-panel="play"','data-round-panel="players"','data-round-panel="setup"','data-round-panel="manage"'):
                self.assertIn(area,page)
            self.assertNotIn('data-round-panel="more"',page)
            self.assertIn('Spieler &amp; Items', page)
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

    def test_successful_round_prioritizes_console_and_race_hides_it(self):
        bid, slots = self.seed()
        waiting = self.client.get('/sessions/1').get_data(as_text=True)
        self.assertIn('id="ap-console"', waiting)
        self.assertIn('id="console-no-server" ', waiting)
        self.post(f'/sessions/1/builds/{bid}/hosting',{'host':'archipelago.gg','port':'49537'})
        page=self.client.get('/sessions/1').get_data(as_text=True)
        self.assertIn('id="ap-console"',page)
        self.assertLess(page.index('id="ap-console"'),page.index('id="prepare-games"'))
        self.assertIn('id="console-command-menu"',page)
        self.assertIn('data-insert-command="/hint "',page)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET snapshot=? WHERE id=?",(json.dumps(dict(slots=[],race=True)),bid))
        self.assertNotIn('id="ap-console"',self.client.get('/sessions/1').get_data(as_text=True))
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET snapshot=?,completed_at='done' WHERE id=?",(json.dumps(dict(slots=slots)),bid))
        archive = self.client.get('/sessions/1').get_data(as_text=True)
        self.assertIn('id="ap-console"', archive)
        self.assertIn('data-archived="1"', archive)
        self.assertNotIn('id="console-command"', archive)

    def test_current_generation_failure_overrides_legacy_success_and_keeps_settings(self):
        bid, slots = self.seed()
        with self.app.app_context():
            failed = db.execute("INSERT INTO seed_builds(session_id,status,snapshot,log,created_at) VALUES (1,'failed',?,?,'now')",
                                (db.dumps(dict(slots=slots, spoiler=3, race=True)), 'FileNotFoundError: missing ROM'))
            db.execute("UPDATE sessions SET gen_status='done',gen_file='old.zip' WHERE id=1")
        page = self.client.get('/sessions/1').get_data(as_text=True)
        self.assertIn('data-build-status="failed"', page)
        self.assertIn('Die Generierung ist fehlgeschlagen. Einstellungen bleiben erhalten.', page)
        self.assertIn('Originaldateien und Pfade auf dem Generator-Rechner', page)
        self.assertIn('value="3" selected', page)
        self.assertIn('name="race" value="1" checked', page)
        self.assertNotIn('id="round-setup"', page)
        self.assertNotIn('old.zip', page)
        self.assertEqual(self.client.get(f'/sessions/1/builds/{failed}/download').status_code, 404)
        with self.app.app_context():
            self.assertEqual(db.query('SELECT status FROM seed_builds WHERE id=?', (bid,), one=True)['status'], 'succeeded')

    def test_generation_redirect_selects_exact_attempt_and_setup(self):
        self.seed()
        with patch.object(mvp, 'begin_build', return_value=(42, [])):
            response = self.post('/sessions/1/generate', {'spoiler':'3'})
        self.assertTrue(response.location.endswith('/sessions/1?build=42#setup'), response.location)

    def test_participant_summary_validates_readiness_and_includes_unselected_members(self):
        self.seed()
        self.post('/login', {'username':'Friend'}, client=self.app.test_client())
        with self.app.app_context():
            db.execute("INSERT INTO entries(session_id,user_id,game,ready,ready_hash) VALUES (1,1,'test_world',1,'stale')")
            db.execute('INSERT INTO lobby_members(session_id,user_id) VALUES (1,2)')
            people = rounds.participants(1)
        self.assertEqual(people, [dict(name='Host', game='Test World', ready=False), dict(name='Friend', game=None, ready=False)])
        page = self.client.get('/rounds').get_data(as_text=True)
        self.assertIn('Host</strong>', page)
        self.assertIn('Friend</strong>', page)
        self.assertIn('Noch kein Spiel ausgewählt', page)

    def test_host_defaults_custom_address_and_global_progress_location(self):
        bid, _ = self.seed()
        page = self.client.get('/sessions/1').get_data(as_text=True)
        self.assertIn('name="host" value="archipelago.gg"', page)
        self.assertLess(page.index('id="round-team-title"'), page.index('id="round-play"'))
        self.assertLess(page.index('id="round-host-connection"'), page.index('id="round-manage"'))
        response = self.post(f'/sessions/1/builds/{bid}/hosting', {'host':'my-server.example','port':'1234'})
        self.assertTrue(response.location.endswith('#play'))
        page = self.client.get('/sessions/1').get_data(as_text=True)
        self.assertIn('name="host" value="my-server.example"', page)

    def test_room_link_can_automatically_resolve_port_without_inventing_one(self):
        bid, _ = self.seed()
        link = 'https://archipelago.gg/room/AAECAwQFBgcICQoLDA0ODw'
        from hub import live_routes, live_store
        with patch.object(live_routes, 'collector'):
            response = self.post(f'/sessions/1/builds/{bid}/hosting', {'host':'archipelago.gg','room_url':link})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertTrue(live_store.current(bid)['auto_host'])
            self.assertIsNone(db.query('SELECT * FROM hosted_rooms WHERE build_id=?', (bid,), one=True))
            for form in ({'host':'custom.example','room_url':link}, {'host':'archipelago.gg','room_url':link,'manual_port':'1'}):
                with self.assertRaises(ValueError):
                    mvp.parse_room_form(form)
