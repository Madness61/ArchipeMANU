"""Opt-in real AP generations in an isolated copy, never the Hub's data directory.

Run: python -m unittest discover -s integration_tests -v
Requires the local AP checkout and its venv; standard CI deliberately uses mocks.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
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
        for folder in ('worlds','data','rule_builder','apmw'):
            if (AP_SOURCE/folder).is_dir():
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
        self.assertNotIn('combinations',result)
        self.assertNotIn('necessity',result)
        self.assertEqual(gains,sorted(gains,reverse=True))
        self.assertEqual(result['singles_tested'],len(result['singles']))
        self.assertEqual(result['singles_complete'],result['singles_tested']==result['candidates_total'])
        # Separate real reconstruction and completion analysis, explicitly requested.
        goal_request=dict(request,mode='goal')
        goal=subprocess.run([str(AP_PYTHON),str(PROJECT/'progression_worker.py')],input=json.dumps(goal_request).encode(),
                            cwd=self.source,env=env,capture_output=True,timeout=100)
        (self.artifacts/(slug+'-goal.json')).write_bytes(goal.stdout)
        goal_data=json.loads(goal.stdout)
        self.assertEqual(goal_data['state'],'ready',goal_data)
        self.assertIn('necessity',goal_data)
        self.assertEqual(goal_data['singles'],[])
        self.report.append(dict(game=game,static=manifest['static']['state'],checks=len(checks),reachable=len(result['reachable']),
                                best_single=max(gains,default=0),single_complete=result['singles_complete'],
                                types_tested=result['singles_tested'],types_total=result['candidates_total'],
                                necessary=sum(r['verdict']=='necessary' for r in goal_data['necessity']),verified=result['verified_model']))
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

    def test_04_dark_souls_basin_redundancy_with_real_access_options(self):
        if not (self.source/'worlds'/'dark_souls_3').is_dir():
            self.skipTest('Dark Souls III APWorld not installed')
        env={k:v for k,v in os.environ.items() if not k.startswith(('HUB_','AP_'))}
        env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        process=subprocess.run([str(AP_PYTHON),str(PROJECT/'integration_tests'/'ds3_recommendations_probe.py')],
            input=json.dumps(dict(root=str(self.root/'ds3-probe'))).encode(),cwd=self.source,env=env,
            capture_output=True,timeout=180)
        (self.artifacts/'ds3-probe.log').write_bytes(process.stderr)
        self.assertEqual(process.returncode,0,process.stderr[-3000:])
        data=json.loads(process.stdout)
        (self.artifacts/'ds3-recommendations.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
        self.assertEqual(len(data),2)

    def test_05_shared_console_with_real_archipelago_multiserver(self):
        """Real AP seed/server, one reader and two automatically mapped writers."""
        from hub import config,db,ap_bridge,ap_console,recording
        from hub.app import create_app
        from werkzeug.security import generate_password_hash
        root=self.root/'console-protocol';root.mkdir()
        players=root/'players';players.mkdir();output=root/'output';output.mkdir()
        for name in ('NativeA','NativeB'):
            (players/(name+'.yaml')).write_text(f'name: {name}\ngame: ChecksFinder\nChecksFinder: {{}}\n',encoding='utf-8')
        env={k:v for k,v in os.environ.items() if not k.startswith(('HUB_','AP_'))}
        env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        generated=subprocess.run([str(AP_PYTHON),str(PROJECT/'ap_runner.py'),'generate','--players',str(players),
                                  '--out',str(output),'--seed','20261118','--spoiler','0'],cwd=self.source,
                                 env=env,capture_output=True,timeout=180)
        (self.artifacts/'console-generation.log').write_bytes(generated.stdout+generated.stderr)
        self.assertEqual(generated.returncode,0,generated.stderr[-2000:])
        seed=next(output.glob('AP_*.zip'))
        model=json.loads((output/'progression_seed.json').read_text(encoding='utf-8'))['model']
        target=next(location for location in model['locations'] if location['player']==2 and location['item']
                    and location['item']['player']==2 and type(location['item']['id']) is int)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        data=root/'hub-data'
        overrides=dict(DATA=data,DB_PATH=data/'hub.db',SESSIONS=data/'sessions',SCHEMAS=data/'schemas',
                       APWORLDS=data/'apworlds',AP_SOURCE=self.source,AP_PYTHON=AP_PYTHON)
        with (self.artifacts/'console-native-server.log').open('wb') as log:
            server=subprocess.Popen([str(AP_PYTHON),str(self.source/'MultiServer.py'),str(seed),'--host','127.0.0.1',
                                     '--port',str(port),'--hint_cost','0','--disable_save'],cwd=self.source,env=env,
                                    stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT)
            try:
                with patch.multiple(config,**overrides),patch.object(ap_bridge,'start_extract'):
                    app=create_app();app.config.update(TESTING=True)
                    with app.app_context():
                        for name in ('SiteA','SiteB'):
                            db.execute('INSERT INTO users(username,slot_name,password_hash) VALUES (?,?,?)',
                                       (name,name,generate_password_hash('p')))
                        sid=db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Native console',1,1)")
                        db.execute('INSERT INTO lobby_members(session_id,user_id) VALUES (?,2)',(sid,))
                        snapshot=dict(slots=[dict(slot='NativeA',game='checksFinder',game_name='ChecksFinder',player_id=1),
                                             dict(slot='NativeB',game='checksFinder',game_name='ChecksFinder',player_id=2)])
                        bid=db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at,seed_name) VALUES (?,'succeeded',?,'today',?)",
                                       (sid,db.dumps(snapshot),seed.stem))
                        db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,'127.0.0.1',?,1,'today')",(bid,port))
                        endpoint = db.query('SELECT * FROM hosted_rooms',one=True)
                        db.execute('''INSERT INTO console_recordings(build_id,hosted_id,actor_id,slot,uuid,transport,automatic,updated_at)
                                      VALUES (?,?,1,'NativeB','saved-reader','ws',1,0)''', (bid,endpoint['id']))
                        reader=recording.ensure(db.query('SELECT * FROM seed_builds',one=True),db.query('SELECT * FROM hosted_rooms',one=True),transport='ws')
                    def wait(predicate):
                        deadline=time.monotonic()+30
                        while time.monotonic()<deadline:
                            if predicate():return
                            self.assertIsNone(server.poll(),'Native AP server stopped unexpectedly')
                            time.sleep(.05)
                        self.fail('Native AP protocol timed out: '+reader.state+' '+reader.error)
                    wait(lambda:reader.state=='connected' and reader.catalog_ready and reader.hint_seen is not None)
                    self.assertEqual((reader.slot_name,reader.slot,reader.uuid), ('NativeA',1,'saved-reader'))
                    clients=[app.test_client(),app.test_client()]
                    def post(client,path,body):
                        client.get('/login')
                        with client.session_transaction() as session:csrf=session['_csrf']
                        return client.post(path,data=dict(_csrf=csrf,**body))
                    base=f'/sessions/{sid}/builds/{bid}/console'
                    self.assertEqual(post(clients[0],'/login',dict(username='SiteA',password='p')).status_code,302)
                    self.assertEqual(post(clients[1],'/login',dict(username='SiteB',password='p')).status_code,302)
                    def events():
                        return clients[0].get(base+'/data').json['events']
                    self.assertEqual(sum('Itemaufzeichnung gestartet' in row['text'] for row in events()), 1)
                    handshake = dict(cmd='Connect', password=None, game='', name='ArchipeMANU',
                                     uuid='real-protocol-probe', version=dict(major=0,minor=6,build=8,**{'class':'Version'}),
                                     items_handling=0, tags=['Tracker'], slot_data=False)
                    with ap_console.open_socket('127.0.0.1', port, False) as wire:
                        self.assertEqual(json.loads(wire.recv(timeout=5))[0]['cmd'], 'RoomInfo')
                        wire.send(json.dumps([handshake]))
                        refusal, = json.loads(wire.recv(timeout=5))
                        self.assertEqual(refusal['cmd'], 'ConnectionRefused')
                        self.assertIn('InvalidSlot', refusal['errors'])
                        wire.send(json.dumps([{**handshake, 'name':'NativeA', 'game':'ChecksFinder', 'tags':['AP']}]))
                        wait(lambda:any('NativeA (Team #1) playing ChecksFinder has joined' in row['text'] for row in events()))
                        previous = reader.connected_at
                        reader.wire.close(1012)
                        presence = {}
                        deadline = time.monotonic() + 15
                        while presence.keys() != {'Join', 'Part'} and time.monotonic() < deadline:
                            for packet in json.loads(wire.recv(timeout=max(.1, deadline-time.monotonic()))):
                                if ap_console.reader_presence(packet):
                                    presence[packet['type']] = packet
                        self.assertEqual(set(presence), {'Join', 'Part'})
                        self.assertCountEqual(presence['Join']['tags'], ['Tracker', 'ArchipeMANU-Reader', 'DeathLink'])
                        self.assertIn('NativeA (Team #1) tracking ChecksFinder has joined', presence['Join']['data'][0]['text'])
                        self.assertNotIn('tags', presence['Part'])
                        self.assertIn('NativeA (Team #1) has stopped tracking the game', presence['Part']['data'][0]['text'])
                        wait(lambda: reader.catalog_ready and reader.connected_at > previous and reader.hint_seen is not None)
                    wait(lambda:any('NativeA (Team #1) has left the game' in row['text'] for row in events()))
                    self.assertFalse(any(ap_console.READER_TAGS[1] in row['text'] or row.get('connection_role') == 'reader'
                                         for row in events()))
                    self.assertEqual(sum('Itemaufzeichnung unterbrochen' in row['text'] for row in events()), 1)
                    with ap_console.open_socket('127.0.0.1', port, False) as wire:
                        self.assertEqual(json.loads(wire.recv(timeout=5))[0]['cmd'], 'RoomInfo')
                        wire.send(json.dumps([{**handshake, 'name':'NativeB', 'game':'ChecksFinder', 'tags':['AP','DeathLink']}]))
                        def receive(kind):
                            deadline = time.monotonic() + 10
                            while time.monotonic() < deadline:
                                for packet in json.loads(wire.recv(timeout=max(.1, deadline-time.monotonic()))):
                                    if packet.get('type')==kind or packet.get('cmd')==kind:
                                        return packet
                            self.fail(f'No real AP packet for {kind}')
                        receive('Connected')
                        # Only disposable test clients send bounces. The Hub reader receives only.
                        death_url = f'/sessions/{sid}/builds/{bid}/live/deathlinks'
                        def deaths():
                            return clients[0].get(death_url).json
                        bounce = dict(cmd='Bounce', tags=['DeathLink'],
                                      data=dict(source='NativeB',time=1800000000.125,cause='NativeB fell'))
                        with ap_console.open_socket('127.0.0.1',port,False) as other:
                            json.loads(other.recv(timeout=5))
                            other.send(json.dumps([{**handshake, 'name':'NativeA','game':'ChecksFinder',
                                                    'uuid':'other-game-client','tags':['AP','DeathLink']}]))
                            def other_receive(cmd):
                                deadline=time.monotonic()+10
                                while time.monotonic()<deadline:
                                    for packet in json.loads(other.recv(timeout=5)):
                                        if packet.get('cmd')==cmd:return packet
                                self.fail('Missing second recipient packet: '+cmd)
                            other_receive('Connected')
                            wire.send(json.dumps([bounce]))
                            self.assertEqual(receive('Bounced')['data'],bounce['data'])
                            self.assertEqual(other_receive('Bounced')['data'],bounce['data'])
                            wait(lambda:deaths()['total']==1)
                            wire.send(json.dumps([bounce,bounce]))
                            receive('Bounced');receive('Bounced')
                            other.send(json.dumps([{**bounce,'data':dict(source='NativeA',time=1800000000.125)}]))
                            receive('Bounced')
                            wait(lambda:deaths()['total']==2)
                            self.assertCountEqual(deaths()['ranking'],[dict(slot='NativeA',count=1),dict(slot='NativeB',count=1)])
                            wire.send(json.dumps([{**bounce,'data':dict(source='In-game character',time=1800000001)}]))
                            receive('Bounced')
                            wait(lambda:deaths()['total']==3)
                            previous=reader.connected_at
                            reader.wire.close(1012)
                            wait(lambda:reader.state!='connected')
                            wire.send(json.dumps([{**bounce,'data':dict(source='Missed while offline',time=1800000002)}]))
                            receive('Bounced')
                            wait(lambda:reader.state=='connected' and reader.connected_at>previous and reader.hint_seen is not None)
                            wire.send(json.dumps([bounce,{**bounce,'data':dict(source='NativeB',time=1800000003)}]))
                            receive('Bounced');receive('Bounced')
                            wait(lambda:deaths()['total']==4)
                            self.assertEqual(deaths()['ranking'][0],dict(slot='NativeB',count=2))
                            self.assertEqual(deaths()['unresolved'],[dict(source='In-game character',count=1)])
                            self.assertGreaterEqual(deaths()['gap_count'],1)
                            self.assertEqual(clients[1].get(death_url).json['total'],4)
                            wire.send(json.dumps([dict(cmd='Say',text='!alias NativeAlias')]))
                            wait(lambda:reader.deathlink_aliases.get(2)=='NativeAlias (NativeB)')
                            wire.send(json.dumps([{**bounce,'data':dict(source='NativeAlias (NativeB)',time=1800000004)}]))
                            receive('Bounced')
                            wait(lambda:deaths()['total']==5)
                            self.assertEqual(deaths()['ranking'][0],dict(slot='NativeB',count=3))
                            wire.send(json.dumps([dict(cmd='Say',text='!alias')]))
                            wait(lambda:reader.deathlink_aliases.get(2)=='NativeB')
                            self.report.append(dict(protocol='real MultiServer DeathLink',recipients=3,recorded=5,
                                                    deduplicated=True,reconnect_gap=True,unresolved=1))
                        item_name=target['item']['name']
                        invalid='ThisIsNotARealChecksFinderItemABCXYZ'
                        for text, result in ((f'!hint {item_name}','Hint'), (f'!hint {invalid}','CommandResult'),
                                             ('!players','CommandResult')):
                            wire.send(json.dumps([dict(cmd='Say',text=text)]))
                            reply=receive(result)
                            if text.endswith(invalid):
                                external_error=reply['data'][0]['text']
                        wire.send(json.dumps([dict(cmd='Say',text=None)]))
                        receive('InvalidPacket')
                        wait(lambda:any(row.get('packet_type')=='CommandResult' for row in events()))
                        expected_hint=f"[Hint]: NativeB's {item_name} is at {target['name']} in NativeB's World"
                        for client in clients:
                            rows=client.get(base+'/data').json['events']
                            hint, = [row for row in rows if row.get('packet_type')=='Hint' and row['text']==expected_hint]
                            request, = [row for row in rows if row['text']==f'NativeB: !hint {item_name}']
                            roster, = [row for row in rows if row.get('packet_type')=='CommandResult']
                            self.assertEqual(hint['visibility'], 'team')
                            self.assertEqual(roster['visibility'], 'team')
                            self.assertLess(request['id'], hint['id'])
                            self.assertLess(hint['id'], roster['id'])
                            self.assertFalse(any(row['text']==external_error or row.get('packet_type')=='InvalidPacket'
                                                 for row in rows))
                        self.assertEqual(sum(value.thread.is_alive() for value in ap_console._clients.values()),1)
                    for client,slot in zip(clients,('NativeA','NativeB')):
                        self.assertEqual(post(client,base+'/command',dict(text=f'/hint {invalid}')).status_code,202)
                        wait(lambda:any(row.get('packet_type')=='CommandResult' and row.get('actor',{}).get('slot')==slot
                                        for row in client.get(base+'/data').json['events']))
                        self.assertTrue(any(row['text']==external_error and row['visibility']=='personal'
                                            for row in client.get(base+'/data').json['events']))
                    own=[{row['id'] for row in client.get(base+'/data').json['events'] if row['visibility']=='personal'} for client in clients]
                    self.assertFalse(own[0]&own[1])
                    self.assertEqual(post(clients[1],base+'/command',dict(text='native shared chat')).status_code,202)
                    wait(lambda:any('native shared chat' in row['text'] for row in clients[0].get(base+'/data').json['events']))
                    for client in clients:
                        chat=[row for row in client.get(base+'/data').json['events'] if 'native shared chat' in row['text'] and row['kind']=='chat']
                        self.assertEqual(len(chat),1);self.assertEqual(chat[0]['visibility'],'team')
                    self.assertEqual(sum(value.thread.is_alive() for value in ap_console._clients.values()),3)
                    with self.assertRaises(ValueError):reader.handle_command('forbidden')
                    self.report.append(dict(game='ChecksFinder x2',protocol='real MultiServer',readers=1,authorized_writers=2,
                                            shared_hint_and_roster=True, private_replies=True,
                                            neutral_slot_rejected=True, real_same_slot_join_and_part=True))
            finally:
                ap_console.stop_all()
                server.terminate()
                try:server.wait(5)
                except subprocess.TimeoutExpired:server.kill();server.wait(5)
                if server.stdin:server.stdin.close()
