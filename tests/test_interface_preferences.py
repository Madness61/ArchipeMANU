"""Account-scoped presentation without changing YAML, readiness or game names."""
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import g
import test_mvp as fixtures
from hub import db, i18n, game_catalog, yamlgen, ap_console

class InterfaceTests(unittest.TestCase):
    setUp,tearDown,post=fixtures.MVPTests.setUp,fixtures.MVPTests.tearDown,fixtures.MVPTests.post
    def login(self):self.post('/login',{'username':'Host'})

    def test_preferences_require_csrf_and_do_not_change_yaml_or_readiness(self):
        self.login()
        with self.app.app_context():
            sid=db.execute("INSERT INTO sessions(name,created_by) VALUES ('UI',1)")
            db.execute("INSERT INTO entries(session_id,user_id,game,ready,ready_hash) VALUES (?,1,'test_world',1,'unchanged')",(sid,))
            db.execute('UPDATE users SET overrides=? WHERE id=1',(db.dumps(dict(death_link=True,progression_balancing=70)),))
        self.assertEqual(self.client.post('/preferences',data=dict(language='en',theme='light')).status_code,403)
        self.assertEqual(self.post('/preferences',dict(language='xx',theme='invalid')).status_code,400)
        response=self.post('/preferences',dict(language='en',theme='light'))
        self.assertEqual(response.status_code,200)
        with self.app.app_context():
            values=db.loads(db.query('SELECT overrides FROM users WHERE id=1',one=True)['overrides'])
            self.assertTrue(values['death_link']);self.assertEqual(values['progression_balancing'],70)
            self.assertEqual(values['_interface'],dict(language='en',theme='light'))
            row=db.query('SELECT ready,ready_hash FROM entries',one=True)
            self.assertEqual((row['ready'],row['ready_hash']),(1,'unchanged'))
            self.assertNotIn('_interface',yamlgen.global_overrides_for({'options':[]},values))
        page=self.client.get('/profile').get_data(as_text=True)
        self.assertIn('<html lang="en" data-theme="light">',page)
        self.assertIn('Language and appearance',page)
        self.assertIn('Progression Balancing',page)
        self.assertNotIn('>Gilt bei mir immer<',page)

    def test_account_preference_beats_another_accounts_browser_cookie(self):
        self.login();self.post('/preferences',dict(language='en',theme='light'))
        self.post('/logout',{})
        self.post('/login',{'username':'Friend'})
        # An account with no preference should start with its own documented defaults.
        page=self.client.get('/profile').get_data(as_text=True)
        self.assertIn('<html lang="de" data-theme="dark">',page)

    def test_english_validation_and_dynamic_values_remain_escaped_data(self):
        self.login();self.post('/preferences',dict(language='en',theme='dark'))
        response=self.post('/preferences',dict(language='xx',theme='dark'))
        self.assertEqual(response.get_json()['error'],'Invalid language or appearance.')
        with self.app.test_request_context('/'),patch.object(i18n,'language',return_value='en'):
            self.assertEqual(i18n.t('Vorlage „Speichern“ gespeichert.'),'Template “Speichern” saved.')
            self.assertEqual(i18n.t('  Verbunden als '),'  Connected as ')
            self.assertEqual(i18n.t('{v0} von {v1} fertig',v0='{v1}',v1=2),'{v1} of 2 finished')
            self.assertEqual(i18n.t('An unknown item named Speichern'),'An unknown item named Speichern')
            self.assertEqual(game_catalog.details('smw','Super Mario World')['description'],game_catalog._EN['smw']['description'])
            self.assertIn('generator computer',game_catalog.details('smw','Super Mario World')['steps'][0])

    def test_personal_filters_keep_privacy_and_received_flags(self):
        self.login()
        self.post('/login',{'username':'Friend'},client=self.app.test_client())
        with self.app.app_context():
            sid=db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Filters',1,1)")
            bid=db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,'succeeded',?,'today')",(sid,db.dumps(dict(slots=[dict(slot='Host',player_id=1,game_name='Test World')]))))
            for sender,recipient in [('Friend','Host'),('Host','Friend'),('Friend','Friend')]:
                ap_console.record(self.path/'hub.db',bid,None,'items',dict(type='item',sender=sender,recipient=recipient,sender_game='Test World',recipient_game='Test World',item_id=501,location_id=1001))
            ap_console.record(self.path/'hub.db',bid,2,'chat',dict(text='PRIVATE'))
        url=f'/sessions/{sid}/builds/{bid}/console/data'
        for kind in ('for_me','from_me','others'):
            response=self.client.get(url+'?kind='+kind)
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.get_json()['events']),1)
            self.assertNotIn('PRIVATE',response.get_data(as_text=True))
        self.assertTrue(self.client.get(url+'?kind=for_me').get_json()['events'][0]['for_me'])

class CatalogCoverageTests(unittest.TestCase):
    def test_static_translation_calls_have_catalogue_entries(self):
        import ast
        from jinja2 import Environment,nodes
        normal=lambda value:re.sub(r'\s+',' ',value).strip()
        for path in Path('hub/templates').glob('*.html'):
            if path.name=='logic_tracker.html':continue
            for call in Environment().parse(path.read_text(encoding='utf-8')).find_all(nodes.Call):
                if isinstance(call.node,nodes.Name) and call.node.name=='_' and call.args and isinstance(call.args[0],nodes.Const) and isinstance(call.args[0].value,str):
                    self.assertIn(normal(call.args[0].value),i18n.MESSAGES,(str(path),call.args[0].value))
        for path in Path('hub/static').glob('*.js'):
            if path.name=='logic.js':continue
            for token in re.findall(r'''window\.HUB_I18N\.t\(("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''',path.read_text(encoding='utf-8')):
                self.assertIn(normal(ast.literal_eval(token)),i18n.MESSAGES,(str(path),token))

    def test_paired_catalogues_and_all_curated_game_guides(self):
        self.assertEqual(set(i18n.SOURCE),set(i18n.ENGLISH))
        for key,source in i18n.SOURCE.items():
            self.assertEqual(set(re.findall(r'\{v\d+\}',source)),set(re.findall(r'\{v\d+\}',i18n.ENGLISH[key])),key)
        self.assertTrue(set(game_catalog.CATALOG)<=set(game_catalog._EN))
        for slug in game_catalog.CATALOG:
            self.assertTrue(game_catalog._EN[slug]['description'])
            self.assertTrue(game_catalog._EN[slug]['requirements'])
            self.assertTrue(game_catalog._EN[slug]['steps'])
