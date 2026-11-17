"""Shared editing, authenticated attribution and additive guide migration."""
import unittest
from unittest.mock import patch

import test_mvp as fixtures
from hub import ap_bridge, db, admin_deletion
from hub.services import guides


class SharedGuideTests(unittest.TestCase):
    setUpBase,tearDown,post=fixtures.MVPTests.setUp,fixtures.MVPTests.tearDown,fixtures.MVPTests.post

    def setUp(self):
        self.setUpBase()
        self.post('/login',{'username':'Host'})
        self.friend=self.app.test_client()
        self.post('/login',{'username':'Friend'},client=self.friend)
        self.url='/games/test_world/guide'

    def test_every_player_can_edit_and_attribution_comes_from_session(self):
        self.assertEqual(self.friend.get(self.url).status_code,200)
        self.assertEqual(self.post(self.url,dict(steps='Install this client',author='1',author_name='Host'),client=self.friend).status_code,302)
        with self.app.app_context():
            saved=guides.get('test_world')
            self.assertEqual((saved['author'],saved['author_display']),(2,'Friend'))
        for path in ('/games/test_world','/games/test_world/setup',self.url):
            page=self.client.get(path).get_data(as_text=True)
            self.assertIn('Zuletzt bearbeitet von',page)
            self.assertIn('<strong>Friend</strong>',page)
        self.post(self.url,dict(steps='Updated by host'))
        with self.app.app_context():self.assertEqual(guides.get('test_world')['author_display'],'Host')
        self.assertIn('Updated by host',self.friend.get(self.url).get_data(as_text=True))
        with self.app.app_context():
            sid=db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Guide round',1,1)")
            db.execute('INSERT INTO lobby_members(session_id,user_id) VALUES (?,2)',(sid,))
            snapshot=dict(slots=[dict(slot='Friend',player_id=2,game='test_world',game_name='Test World')])
            bid=db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,'succeeded',?,'today')",(sid,db.dumps(snapshot)))
        page=self.friend.get(f'/sessions/{sid}/builds/{bid}/play').get_data(as_text=True)
        self.assertIn('Zuletzt bearbeitet von',page)
        self.assertIn('Updated by host',page)

    def test_legacy_url_csrf_unknown_games_and_unsafe_links(self):
        self.assertEqual(self.friend.get('/admin/guides/test_world').status_code,200)
        self.assertIn(self.app.test_client().get(self.url).status_code,(302,401))
        self.assertEqual(self.friend.post(self.url,data={'steps':'No CSRF'}).status_code,403)
        self.assertEqual(self.post('/games/not_a_game/guide',dict(steps='Unknown'),client=self.friend).status_code,404)
        for value in ('javascript:alert(1)','http:incomplete','http://['):
            self.assertEqual(self.post(self.url,dict(source_url=value),client=self.friend).status_code,400)
        with self.app.app_context():self.assertIsNone(guides.get('test_world'))

    def test_inactive_game_is_editable_and_markup_is_escaped(self):
        with patch.object(ap_bridge,'schema',return_value=None):
            self.assertEqual(self.friend.get(self.url).status_code,200)
            self.assertEqual(self.post(self.url,dict(steps='<script>fake()</script>'),client=self.friend,follow_redirects=True).status_code,200)
        page=self.client.get('/games/test_world').get_data(as_text=True)
        self.assertIn('&lt;script&gt;fake()&lt;/script&gt;',page)
        self.assertNotIn('<script>fake()</script>',page)

    def test_additive_migration_retains_original_guide_and_editor(self):
        with self.app.app_context(),db.transaction() as conn:
            conn.execute('DROP TABLE game_guides')
            conn.execute("""CREATE TABLE game_guides(slug TEXT PRIMARY KEY,verified_version TEXT DEFAULT '',
                game_version TEXT DEFAULT '',mod_url TEXT DEFAULT '',source_url TEXT DEFAULT '',
                steps TEXT DEFAULT '',trouble TEXT DEFAULT '',updated_at TEXT,author INTEGER REFERENCES users(id))""")
            conn.execute("INSERT INTO game_guides(slug,steps,trouble,updated_at,author) VALUES ('test_world','Original text','Known issue','2026-01-01',2)")
            guides.migrate(conn);guides.migrate(conn)
            row=conn.execute('SELECT * FROM game_guides').fetchone()
            self.assertEqual((row['steps'],row['trouble'],row['updated_at'],row['author'],row['author_name']),
                             ('Original text','Known issue','2026-01-01',2,'Friend'))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM game_guides').fetchone()[0],1)

    def test_deleting_account_preserves_writer_name_until_another_edit(self):
        self.post(self.url,dict(steps='Written by friend'),client=self.friend)
        with self.app.app_context():
            admin_deletion.delete_account(2,1)
            row=guides.get('test_world')
            self.assertEqual((row['author'],row['author_display']),(1,'Friend'))
        self.assertIn('<strong>Friend</strong>',self.client.get('/games/test_world').get_data(as_text=True))
        self.post(self.url,dict(steps='Revised by host'))
        with self.app.app_context():self.assertEqual(guides.get('test_world')['author_display'],'Host')
