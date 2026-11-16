"""Opt-in real AP generations in an isolated copy, never the Hub's data directory.

Run: python -m unittest discover -s integration_tests -v
Requires the local AP checkout and its venv; standard CI deliberately uses mocks.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
AP_SOURCE=Path(os.environ.get('AP_SOURCE',Path.home()/'.ap-yaml-hub'/'Archipelago'))
AP_PYTHON=Path(os.environ.get('AP_PYTHON',Path.home()/'.ap-yaml-hub'/'venv'/'Scripts'/'python.exe'))


@unittest.skipUnless(AP_SOURCE.is_dir() and AP_PYTHON.is_file(),'Installed AP runtime required')
class RealProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='archipemanu-progression-integration-')
        cls.root=Path(cls.temporary.name)
        cls.source=cls.root/'ap';cls.source.mkdir()
        for p in AP_SOURCE.iterdir():
            if p.is_file() and (p.suffix in ('.py','.json') or p.name=='requirements.txt'):
                shutil.copy2(p,cls.source/p.name)
        for folder in ('worlds','data','rule_builder'):
            shutil.copytree(AP_SOURCE/folder,cls.source/folder,ignore=shutil.ignore_patterns('__pycache__','test','tests','*.pyc'))
        (cls.source/'custom_worlds').mkdir()
        cls.custom=AP_SOURCE/'custom_worlds'/'pseudoregalia.apworld'
        if cls.custom.is_file():
            shutil.copy2(cls.custom,cls.source/'custom_worlds'/cls.custom.name)
        (cls.source/'host.yaml').write_text('{}',encoding='utf-8')
        cls.artifacts=PROJECT/'test-results'/'progression-real';cls.artifacts.mkdir(parents=True,exist_ok=True)
        cls.report=[]

    @classmethod
    def tearDownClass(cls):
        (cls.artifacts/'results.json').write_text(json.dumps(cls.report,indent=2),encoding='utf-8')
        cls.temporary.cleanup()

    def run_game(self,game,slug):
        root=self.root/slug;root.mkdir()
        players=root/'players';players.mkdir()
        (players/'probe.yaml').write_text('name: Probe\ngame: '+game+'\n'+game+': {}\n',encoding='utf-8')
        output=root/'output';output.mkdir()
        env={k:v for k,v in os.environ.items() if not k.startswith(('HUB_','AP_'))}
        env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        args=[str(AP_PYTHON),str(PROJECT/'ap_runner.py'),'generate','--players',str(players),'--out',str(output),'--seed','20261116','--spoiler','0']
        generated=subprocess.run(args,cwd=self.source,env=env,capture_output=True,timeout=180)
        (self.artifacts/(slug+'-generation.log')).write_bytes(generated.stdout+generated.stderr)
        self.assertEqual(generated.returncode,0,generated.stdout[-2000:]+generated.stderr[-2000:])
        self.assertTrue(list(output.glob('AP_*.zip')))
        manifest=json.loads((output/'progression_seed.json').read_text(encoding='utf-8'))
        model=manifest['model']
        checks=[l['id'] for l in model['locations'] if type(l['id']) is int and l['item'] and type(l['item']['id']) is int]
        live=dict(slot=1,team=0,checked=[],missing=checks,received=[dict(item=i['id'],location=-2,player=0,flags=i['flags'])
             for i in model['precollected']['1'] if type(i['id']) is int])
        request=dict(manifest=manifest,players=str(players),output=str(root/'replay'),live=live,hide=[])
        replay=subprocess.run([str(AP_PYTHON),str(PROJECT/'progression_worker.py')],input=json.dumps(request).encode(),
                              cwd=self.source,env=env,capture_output=True,timeout=100)
        (self.artifacts/(slug+'-worker.json')).write_bytes(replay.stdout)
        (self.artifacts/(slug+'-worker.log')).write_bytes(replay.stderr)
        self.assertEqual(replay.returncode,0,replay.stderr[-2000:])
        result=json.loads(replay.stdout)
        if result['state']!='ready':
            # A diagnostic evaluation uses the same isolated source, never a live room.
            diagnostic=subprocess.run([str(AP_PYTHON),'-c',
                'import sys,json;sys.path.insert(0,'+repr(str(PROJECT))+');from progression_worker import evaluate;evaluate(json.load(sys.stdin))'],
                input=json.dumps(request).encode(),cwd=self.source,env=env,capture_output=True,timeout=100)
            (self.artifacts/(slug+'-diagnostic.log')).write_bytes(diagnostic.stdout+diagnostic.stderr)
            if result.get('reason')=='runtime_changed':
                diff=subprocess.run([str(AP_PYTHON),'-c',
                    'import sys,json,os;sys.path.insert(0,'+repr(str(PROJECT))+');from progression_model import runtime_details;json.dump(runtime_details(os.getcwd()),sys.stdout)'],
                    cwd=self.source,env=env,capture_output=True,timeout=30)
                actual=json.loads(diff.stdout);expected=manifest.get('runtime_details',{})
                (self.artifacts/(slug+'-runtime-difference.json')).write_text(json.dumps({k:dict(expected=expected.get(k),actual=actual[k]) for k in actual if actual[k]!=expected.get(k)},indent=2),encoding='utf-8')
        self.assertEqual(result['state'],'ready',result)
        self.assertEqual(result['verified_model'],manifest['model_hash'])
        gains=[len(r['new_checks']) for r in result['singles']]
        self.report.append(dict(game=game,static=manifest['static']['state'],checks=len(checks),reachable=len(result['reachable']),
                                best_single=max(gains,default=0),best_pair=max((len(r['new_checks']) for r in result['combinations']),default=0),
                                single_complete=result['singles_complete'],pairs_complete=result['combinations_complete'],
                                necessary=sum(r['verdict']=='necessary' for r in result['necessity']),verified=result['verified_model']))
        if slug=='checksFinder':
            self.verify_hub_api(root,players,output,manifest,live)
        # The reconstructed seed must refuse changed original evidence.
        bad=dict(request,manifest={**manifest,'model_hash':'0'*64})
        invalid=subprocess.run([str(AP_PYTHON),str(PROJECT/'progression_worker.py')],input=json.dumps(bad).encode(),cwd=self.source,env=env,capture_output=True,timeout=100)
        self.assertEqual(json.loads(invalid.stdout)['reason'],'reconstruction_mismatch')
        if slug=='pseudoregalia':
            installed=self.source/'custom_worlds'/'pseudoregalia.apworld'
            disabled=installed.with_suffix('.disabled')
            installed.rename(disabled)
            try:
                missing=subprocess.run([str(AP_PYTHON),str(PROJECT/'progression_worker.py')],input=json.dumps(request).encode(),cwd=self.source,env=env,capture_output=True,timeout=100)
                self.assertEqual(json.loads(missing.stdout)['reason'],'runtime_changed')
            finally:
                disabled.rename(installed)

    def verify_hub_api(self,root,players,output,manifest,live):
        from hub import config,db,progression,ap_bridge
        from hub.app import create_app
        from werkzeug.security import generate_password_hash
        data=root/'hub-data'
        overrides=dict(DATA=data,DB_PATH=data/'hub.db',SESSIONS=data/'sessions',SCHEMAS=data/'schemas',
                       APWORLDS=data/'apworlds',AP_SOURCE=self.source,AP_PYTHON=AP_PYTHON)
        with patch.multiple(config,**overrides),patch.object(ap_bridge,'start_extract'):
            app=create_app();app.config.update(TESTING=True)
            with app.app_context():
                uid=db.execute("INSERT INTO users(username,slot_name,password_hash,is_admin) VALUES ('Probe','Probe',?,1)",(generate_password_hash('p'),))
                sid=db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Real integration',?,1)",(uid,))
                snapshot=dict(race=False,yamls=manifest['yamls'],slots=[dict(slot='Probe',player_id=uid,game='checksFinder',game_name='ChecksFinder')])
                stats=json.loads((output/'item_distribution.json').read_text(encoding='utf-8'))
                bid=db.execute("INSERT INTO seed_builds(session_id,status,snapshot,stats_json,created_at) VALUES (?,'succeeded',?,?,'today')",(sid,db.dumps(snapshot),db.dumps(stats)))
                hid=db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,'127.0.0.1',1234,?,'today')",(bid,uid))
                db.execute('INSERT INTO progression_live VALUES (?,?,?,?,?,?)',(bid,'Probe',hid,uid,db.dumps(live),time.time()))
            folder=config.SESSIONS/'_seeds'/str(bid)
            shutil.copytree(players,folder/'players');shutil.copytree(output,folder/'output')
            client=app.test_client();client.get('/login')
            with client.session_transaction() as cookie:csrf=cookie['_csrf']
            def post(url,values):return client.post(url,data={**values,'_csrf':csrf})
            self.assertEqual(post('/login',dict(username='Probe',password='p')).status_code,302)
            # Login rotates CSRF/session credentials.
            with client.session_transaction() as cookie:csrf=cookie['_csrf']
            url=f'/sessions/{sid}/builds/{bid}/progression'
            self.assertEqual(post(url+'/consent',dict(reveal='1')).status_code,200)
            self.assertEqual(client.get(url+'/analysis').json['state'],'idle')
            self.assertEqual(post(url+'/analysis',{}).json['state'],'loading')
            deadline=time.monotonic()+110
            while time.monotonic()<deadline:
                value=client.get(url+'/analysis').json
                if value['state']!='loading':break
                time.sleep(.1)
            self.assertEqual(value['state'],'ready',value)
            self.assertEqual(len(value['reachable']),5)
            self.assertTrue(value['singles'][0]['items'][0]['placements'])
            self.assertEqual(client.get(url+'/analysis').json['verified_model'],manifest['model_hash'])
            # A genuinely received placed item changes the inventory cache key.
            loc=next(l for l in manifest['model']['locations'] if l['item'] and l['item']['flags']&1 and type(l['id']) is int)
            updated={**live,'received':live['received']+[dict(item=loc['item']['id'],location=loc['id'],player=1,flags=loc['item']['flags'])],
                     'checked':[loc['id']],'missing':[i for i in live['missing'] if i!=loc['id']]}
            with app.app_context():
                db.execute('UPDATE progression_live SET payload=? WHERE build_id=?',(db.dumps(updated),bid))
            self.assertEqual(client.get(url+'/analysis').json['state'],'idle')
            self.assertEqual(post(url+'/analysis',{}).json['state'],'loading')
            deadline=time.monotonic()+110
            while time.monotonic()<deadline:
                fresh=client.get(url+'/analysis').json
                if fresh['state']!='loading':break
                time.sleep(.1)
            self.assertEqual(fresh['state'],'ready',fresh)
            self.assertEqual(len(fresh['reachable']),len(value['reachable']))

    def test_01_checks_finder(self):
        self.run_game('ChecksFinder','checksFinder')

    def test_02_meritous(self):
        self.run_game('Meritous','meritous')

    def test_03_custom_pseudoregalia(self):
        if not self.custom.is_file():
            self.skipTest('Pseudoregalia custom APWorld not installed')
        self.run_game('Pseudoregalia','pseudoregalia')
