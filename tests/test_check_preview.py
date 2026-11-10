"""Counts must come from generation, never from the static schema location list."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

import ap_runner
import test_mvp as fixtures
from hub import ap_bridge, check_preview, config, db


class CheckPreviewTests(unittest.TestCase):
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    post = fixtures.MVPTests.post

    def test_api_is_read_only_until_explicit_post_and_requires_auth_and_csrf(self):
        self.assertEqual(self.client.get('/api/games/test_world/checks').status_code,302)
        self.post('/login',{'username':'Host'})
        with patch.object(ap_bridge,'ap_ready',return_value=True), patch.object(check_preview._pool,'submit') as submit:
            response=self.client.get('/api/games/test_world/checks')
            self.assertEqual(response.json['state'],'idle')
            submit.assert_not_called()
            self.assertEqual(self.client.post('/api/games/test_world/checks').status_code,403)
            self.post('/api/games/test_world/checks',{})
            submit.assert_called_once()
        with self.app.app_context():
            for table in ('sessions','entries','seed_builds'):
                self.assertEqual(db.query('SELECT COUNT(*) AS n FROM '+table,one=True)['n'],0)
        # Remove only this test's unfinished mock future.
        with check_preview._lock:
            for key in list(check_preview._jobs):
                if key[0]==str(config.DATA):del check_preview._jobs[key]

    def test_cache_matches_version_and_standard_without_profile(self):
        with patch.object(ap_bridge,'ap_ready',return_value=True):
            spec=check_preview.specification('test_world')
            self.assertIn('difficulty: 3',spec['yaml'])
            self.assertIn('StandardCheck',spec['yaml'])
            def run(args,timeout):
                self.assertEqual(args[0],'preview')
                out=Path(args[args.index('--out')+1])
                (out/'check_preview.json').write_text(json.dumps(dict(source='archipelago_standard_probe',checks=42,game='Test World',seed=20261110)))
                return True,''
            with patch.object(ap_bridge,'_sync_custom_worlds'),patch.object(ap_bridge,'_run',side_effect=run) as runner:
                result=check_preview.evaluate(spec)
                self.assertEqual(result['checks'],42)
                self.assertEqual(check_preview.status('test_world')['checks'],42)
                runner.assert_called_once()
            with patch.object(ap_bridge,'index',return_value={**fixtures.INDEX,'ap_version':'0.6.9'}):
                self.assertEqual(check_preview.status('test_world')['state'],'idle')

    def test_busy_error_and_invalid_result_never_invent_a_count(self):
        with patch.object(ap_bridge,'ap_ready',return_value=True):
            spec=check_preview.specification('test_world')
            with ap_bridge.ap_lock:
                self.assertEqual(check_preview.evaluate(spec)['state'],'busy')
            with patch.object(ap_bridge,'_sync_custom_worlds'),patch.object(ap_bridge,'_run',return_value=(False,'PRIVATE LOCAL PATH')):
                failed=check_preview.evaluate(spec)
                self.assertEqual(failed['state'],'unavailable')
                self.assertNotIn('checks',failed)
                self.assertNotIn('PRIVATE',failed['error'])
            self.assertFalse(check_preview.cache_path(spec).exists())

    def test_runner_counts_only_addressed_locations_with_network_items(self):
        locations=[SimpleNamespace(player=1,address=address,item=SimpleNamespace(code=code))
                   for address,code in ((1,10),(2,11),(None,12),(3,None))]
        world=SimpleNamespace(player_ids=[1],game={1:'Test World'},get_filled_locations=lambda:locations)
        seen=[]
        def main():
            seen.extend(sys.argv)
            return SimpleNamespace(),20261110
        modules={'settings':SimpleNamespace(),'Generate':SimpleNamespace(main=main),
                 'Main':SimpleNamespace(main=lambda args,seed:world)}
        with tempfile.TemporaryDirectory() as folder,patch.dict(sys.modules,modules),patch.object(sys,'argv',[]),patch.object(ap_runner,'validate_player_files'):
            ap_runner.preview_checks('players',folder)
            self.assertIn('--skip_output',seen)
            files=list(Path(folder).iterdir())
            self.assertEqual([p.name for p in files],['check_preview.json'])
            result=json.loads(files[0].read_text())
            self.assertEqual(result['checks'],2)
            self.assertNotIn('locations',result)
