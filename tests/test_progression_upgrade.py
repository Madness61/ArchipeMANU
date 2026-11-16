"""New templates must remain usable in a still-running pre-upgrade backend."""
import unittest
from unittest.mock import patch
from flask import url_for
from werkzeug.routing import BuildError
import test_rounds as fixtures


class ProgressionUpgradeTests(unittest.TestCase):
    setUp,tearDown,post=fixtures.RoundTests.setUp,fixtures.RoundTests.tearDown,fixtures.RoundTests.post
    seed=fixtures.RoundTests.seed

    def test_old_backend_with_current_templates_keeps_running_round_and_console(self):
        bid,_=self.seed()
        self.post(f'/sessions/1/builds/{bid}/hosting',dict(host='127.0.0.1',port='1234'))
        def legacy_url(endpoint,**values):
            if endpoint.startswith('progression.'):
                raise BuildError(endpoint,values,None)
            return url_for(endpoint,**values)
        with patch.dict(self.app.jinja_env.globals,{'url_for':legacy_url}):
            self.app.jinja_env.globals.pop('progression_enabled',None)
            for path in ('/sessions/1',f'/sessions/1/builds/{bid}/console'):
                page=self.client.get(path)
                self.assertEqual(page.status_code,200)
                self.assertIn(b'id="ap-console"',page.data)
                self.assertNotIn(b'id="progression-panel"',page.data)
                self.assertNotIn(b'data-progression-open=',page.data)
        page=self.client.get('/sessions/1')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'id="progression-panel"',page.data)
