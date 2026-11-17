"""Recording consent, restart recovery and evidence from real localhost AP sockets."""
import json
import time
import unittest
from unittest.mock import patch

import test_ap_console as fixtures
import test_live_dashboard as live_fixtures
from hub import ap_console, db, live_api, live_store, recording


class RecordingTests(unittest.TestCase):
    setUp,tearDown,post=fixtures.ConsoleTests.setUp,fixtures.ConsoleTests.tearDown,fixtures.ConsoleTests.post
    wait_for,state,connect=fixtures.ConsoleTests.wait_for,fixtures.ConsoleTests.state,fixtures.ConsoleTests.connect

    def enable(self, **fields):
        response=self.post(self.url+'/recording/start',dict(slot='Host',transport='ws',consent='1',**fields))
        self.assertEqual(response.status_code,202,response.data)
        current=recording.worker(self.bid)
        self.wait_for(lambda:current.state in ('connected','action_required','reconnecting'))
        return current

    def test_host_consent_uses_own_slot_and_survives_logout_without_browser(self):
        self.assertFalse(self.server.packets)
        self.assertEqual(self.client.post(self.url+'/recording/start').status_code,403)
        self.assertEqual(self.post(self.url+'/recording/start',dict(slot='Host')).status_code,400)
        self.assertEqual(self.post(self.url+'/recording/start',dict(slot='Friend',consent='1')).status_code,403)
        self.assertEqual(self.post(self.url+'/recording/start',dict(slot='Friend',consent='1'),client=self.friend).status_code,403)
        current=self.enable()
        self.assertEqual(current.slot_name,'Host')
        self.assertFalse(next(p for p in self.server.packets if p['cmd']=='Connect')['slot_data'])
        self.post('/logout',{})
        self.assertTrue(current.valid())
        self.server.interrupt()
        self.wait_for(lambda:len([p for p in self.server.packets if p['cmd']=='Connect'])>=2)
        self.wait_for(lambda:current.state=='connected')
        self.assertFalse(any(p['cmd'] in ('Say','LocationChecks','StatusUpdate','LocationScouts','Get','Set') for p in self.server.packets))

    def test_new_event_does_not_delete_history_past_old_ten_thousand_boundary(self):
        with self.app.app_context():
            endpoint=db.query('SELECT id FROM hosted_rooms WHERE build_id=?',(self.bid,),one=True)['id']
        with db.transaction() as conn:
            conn.executemany("INSERT INTO console_events(build_id,kind,payload,observed_at,hosted_id) VALUES (?,'items',?,1,?)",
                             [(self.bid,json.dumps(dict(text=f'event {i}')),endpoint) for i in range(10020)])
        ap_console.record(self.path/'hub.db',self.bid,None,'items',dict(text='new event'),hosted_id=endpoint)
        with self.app.app_context():
            self.assertEqual(db.query('SELECT COUNT(*) AS n FROM console_events',one=True)['n'],10021)
        self.assertEqual(len(self.state()['events']),100)
        self.assertEqual(self.state()['journal_limit'],None)

    def test_duplicate_start_and_multiple_readers_keep_single_event(self):
        current=self.enable()
        self.assertIs(self.enable(),current)
        self.connect();self.connect(client=self.friend)
        self.server.broadcast_item();self.server.broadcast_item()
        self.wait_for(lambda:len(self.server.clients)==3)
        self.assertEqual(len(self.state(query='?kind=items')['events']),1)
        self.assertEqual(len([p for p in self.server.packets if p['cmd']=='Connect']),3)
        self.assertEqual(self.state()['recording']['state'],'active')

    def test_legacy_delivery_and_changed_flags_do_not_duplicate_the_same_check(self):
        with self.app.app_context():
            endpoint=db.query('SELECT id FROM hosted_rooms',one=True)['id']
        ap_console.record(self.path/'hub.db',self.bid,None,'items',dict(type='item',sender='Friend',
            sender_game='Test World',recipient='Host',recipient_game='Test World',item_id=501,location_id=1001),
            key='historical-flags-based-key',hosted_id=endpoint)
        current=self.enable()
        self.wait_for(lambda:current.items_synced)
        current.packet(dict(cmd='PrintJSON',type='ItemSend',receiving=1,item=dict(item=501,location=1001,player=2,flags=0)))
        self.assertEqual(len(self.state(query='?kind=items')['events']),1)

    def test_extended_outage_marks_gap_and_eventually_resumes_without_replaying(self):
        original=ap_console.connect_transport
        outage=[False]
        failures=[]
        def connect(host,port,secure):
            if outage[0]:
                failures.append(time.time())
                raise ConnectionRefusedError()
            return original(host,port,secure)
        with patch.object(ap_console,'connect_transport',side_effect=connect),patch.object(ap_console,'RETRY_BASE',.01),patch.object(ap_console,'RETRY_MAX',.03):
            current=self.enable()
            self.wait_for(lambda:current.items_synced)
            outage[0]=True
            self.server.interrupt()
            self.wait_for(lambda:len(failures)>=6)
            self.assertEqual(current.state,'temporarily_unavailable')
            self.assertEqual(self.state()['recording']['state'],'interrupted')
            outage[0]=False
            self.wait_for(lambda:current.state=='connected' and current.items_synced)
            self.assertEqual(len(self.state(query='?kind=items')['events']),1)
            self.assertTrue(any('Itemaufzeichnung unterbrochen' in e['text'] for e in self.state()['events']))
            self.assertFalse(any(p['cmd']=='Say' for p in self.server.packets))

    def test_recorder_drops_chat_hints_and_private_server_messages(self):
        current=self.enable()
        self.wait_for(lambda:bool(self.server.clients))
        self.server.send(self.server.clients[0],[dict(cmd='PrintJSON',type='Hint',data=[dict(text='PRIVATE HINT')]),
                                                dict(cmd='PrintJSON',type='Chat',data=[dict(text='PRIVATE CHAT')]),
                                                dict(cmd='Print',text='PRIVATE PRINT')])
        self.post(self.url+'/command',dict(text='hello'))  # No personal text session is active.
        time.sleep(.2)
        with self.app.app_context():
            stored=' '.join(r['payload'] for r in db.query('SELECT payload FROM console_events'))
        self.assertNotIn('PRIVATE',stored)
        self.assertFalse(any(p['cmd']=='Say' for p in self.server.packets))
        self.assertTrue(current.valid())

    def test_resume_after_hub_restart_keeps_history_and_uses_existing_consent_only(self):
        first=self.enable()
        self.wait_for(lambda:first.items_synced)
        self.wait_for(lambda:len(self.state(query='?kind=items')['events'])==1)
        original=self.state(query='?kind=items')['events'][0]['id']
        ap_console.stop_all()
        self.assertIsNone(first.password)
        self.server.history[1].append([502,1002,2,0])  # Evidence available on the next sync, no live event.
        self.server.emit_live=False
        with patch.object(ap_console,'PROCESS_ID','new-isolated-hub-process'):
            with self.app.app_context():
                db.execute('UPDATE console_recordings SET lease_until=0 WHERE build_id=?',(self.bid,))
            recording.resume_due()
            current=recording.worker(self.bid)
            self.wait_for(lambda:current.state=='connected' and current.items_synced)
            self.assertEqual(current.uuid,first.uuid)
            # ReceivedItems and DataPackage are independent protocol packets.
            # A synchronized inventory can still display an honest ID fallback
            # until the catalogue is received, especially on slow CI runners.
            self.wait_for(lambda:any(e.get('delivery',{}).get('item')=='Potion'
                                     for e in self.state(query='?kind=items')['events']))
            events=self.state(query='?kind=items')['events']
            self.assertEqual([e['id'] for e in events[:1]],[original])
            self.assertEqual(len(events),2)
            restored=events[1]
            self.assertEqual((restored['source'],restored['receipt_index']),('received_items',1))
            self.assertEqual(restored['delivery']['item'],'Potion')
            self.assertGreaterEqual(restored['at'],first.connected_at)
            self.assertTrue(any('Lücke' in e['text'] for e in self.state()['events']))
            ap_console.stop_all()

    def test_password_is_memory_only_and_restart_requires_explicit_reentry(self):
        self.server.password='secret room password'
        first=self.enable(password=self.server.password)
        self.wait_for(lambda:first.items_synced)
        ap_console.stop_all()
        with self.app.app_context():
            row=dict(db.query('SELECT * FROM console_recordings',one=True))
            serialized=json.dumps(row)+' '.join(r['payload'] for r in db.query('SELECT payload FROM console_events'))
        self.assertNotIn(self.server.password,serialized)
        count=len(self.server.packets)
        recording.resume_due()
        self.assertEqual(len(self.server.packets),count)
        data=self.state()['recording']
        self.assertEqual(data['console_state'],'action_required')
        self.assertIn('Raumpasswort',data['error'])
        self.assertIsNone(first.password)
        self.assertEqual(self.enable(password=self.server.password).state,'connected')

    def test_recording_lease_does_not_create_parallel_workers(self):
        self.enable()
        ap_console.stop_all()
        with self.app.app_context():
            db.execute("UPDATE console_recordings SET lease_owner='another-process',lease_until=?",(time.time()+60,))
        count=len(self.server.packets)
        recording.resume_due()
        self.assertEqual(len(self.server.packets),count)
        self.assertIsNone(recording.worker(self.bid))

    def test_persisted_connection_is_not_live_proof_after_hub_restart(self):
        self.enable()
        ap_console.stop_all()
        before_boot=time.time()-1
        with self.app.app_context():
            db.execute("UPDATE console_streams SET state='connected',heartbeat=?",(before_boot,))
            db.execute("UPDATE console_recordings SET state='connected'")
        with patch.object(ap_console,'PROCESS_STARTED',time.time()):
            status=self.state()['recording']
        self.assertEqual(status['state'],'interrupted')
        self.assertEqual(status['console_state'],'reconnecting')

    def test_switching_active_recording_actor_requires_explicit_stop(self):
        current=self.enable()
        with self.app.app_context():
            db.execute('UPDATE users SET is_admin=1 WHERE id=2')
        response=self.post(self.url+'/recording/start',dict(slot='Friend',transport='ws',consent='1'),client=self.friend)
        self.assertEqual(response.status_code,409)
        self.assertEqual(recording.worker(self.bid),current)

    def test_explicit_stop_never_resumes_and_releases_password(self):
        current=self.enable()
        self.assertEqual(self.post(self.url+'/recording/stop',{},client=self.friend).status_code,403)
        self.assertEqual(self.post(self.url+'/recording/stop',{}).status_code,200)
        self.wait_for(lambda:not current.thread.is_alive())
        recording.resume_due()
        self.assertFalse(self.state()['recording']['enabled'])
        self.assertIsNone(current.password)
        self.assertEqual(self.state()['recording']['state'],'interrupted')

    def test_room_change_or_completed_seed_never_reuses_recording_consent(self):
        with patch.object(ap_console,'GUARD_SECONDS',.05):
            current=self.enable()
            with self.app.app_context():
                db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,'127.0.0.1',12345,1,'later')",(self.bid,))
            self.wait_for(lambda:not current.thread.is_alive())
            recording.resume_due()
            with self.app.app_context():
                self.assertEqual(db.query('SELECT state FROM console_recordings',one=True)['state'],'action_required')
            self.assertEqual(len([p for p in self.server.packets if p['cmd']=='Connect']),1)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET completed_at='done' WHERE id=?",(self.bid,))
        self.assertEqual(self.post(self.url+'/recording/start',dict(slot='Host',consent='1')).status_code,409)

    def test_race_or_missing_host_slot_cannot_enable_recording(self):
        with self.app.app_context():
            metadata=db.loads(db.query('SELECT snapshot FROM seed_builds WHERE id=?',(self.bid,),one=True)['snapshot'])
            metadata['slots']=metadata['slots'][1:]
            db.execute('UPDATE seed_builds SET snapshot=? WHERE id=?',(db.dumps(metadata),self.bid))
        self.assertEqual(self.post(self.url+'/recording/start',dict(slot='Friend',consent='1')).status_code,403)
        with self.app.app_context():
            metadata['race']=True
            db.execute('UPDATE seed_builds SET snapshot=? WHERE id=?',(db.dumps(metadata),self.bid))
        self.assertEqual(self.post(self.url+'/recording/start',dict(slot='Host',consent='1')).status_code,403)
        self.assertFalse(self.server.packets)

    def test_api_failure_and_console_state_remain_independent(self):
        self.connect()
        live_id=live_store.attach(self.bid,live_fixtures.ROOM_URL,1,auto_host=False)
        payloads=live_fixtures.responses()
        now=time.time()
        with patch.object(live_api,'fetch',side_effect=lambda endpoint,identifier:payloads[endpoint]):
            self.assertTrue(live_store.refresh(live_id,now))
        with patch.object(live_api,'fetch',side_effect=live_api.APIError('API unavailable','rate_limited',300)):
            self.assertFalse(live_store.refresh(live_id,now+61))
        data=self.state()
        self.assertEqual(data['state'],'connected')
        self.assertEqual(data['recording']['state'],'active')
        self.assertEqual(data['webhost']['state'],'rate_limited')
        self.assertTrue(data['webhost']['stale'])
        self.assertIsNotNone(data['webhost']['last_success'])
        self.assertGreaterEqual(data['webhost']['next_update'],now+361)

    def test_working_api_never_claims_live_socket_is_connected(self):
        live_id=live_store.attach(self.bid,live_fixtures.ROOM_URL,1,auto_host=False)
        payloads=live_fixtures.responses()
        with patch.object(live_api,'fetch',side_effect=lambda endpoint,identifier:payloads[endpoint]):
            live_store.refresh(live_id)
        with patch.object(ap_console,'connect_transport',side_effect=ConnectionRefusedError()):
            self.connect()
            data=self.state()
            self.assertEqual(data['state'],'reconnecting')
            self.assertEqual(data['webhost']['state'],'ready')
            self.assertFalse(data['webhost']['stale'])
            self.assertEqual(data['recording']['state'],'not_started')

    def test_history_sync_deduplicates_and_ignores_synthetic_or_out_of_order_items(self):
        self.server.emit_live=False
        current=self.enable()
        self.wait_for(lambda:current.items_synced)
        self.wait_for(lambda:len(self.state(query='?kind=items')['events'])==1)
        before=self.state(query='?kind=items')['events'][0]
        self.server.send(self.server.clients[0],[dict(cmd='ReceivedItems',index=8,items=[[502,1002,2,0]])])
        self.wait_for(lambda:any(p['cmd']=='Sync' for p in self.server.packets))
        self.server.send(self.server.clients[0],[dict(cmd='ReceivedItems',index=0,items=[[501,1001,2,1],[502,-2,0,0]])])
        self.wait_for(lambda:len(current.received)==2)
        events=self.state(query='?kind=items')['events']
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['id'],before['id'])

    def test_localized_hub_commands_do_not_translate_native_server_text_or_item_names(self):
        self.connect()
        self.post('/preferences',dict(language='en',theme='dark'))
        self.post(self.url+'/command',dict(text='/help'))
        self.assertTrue(any('Show all supported commands' in e['text'] for e in self.state()['events']))
        self.post(self.url+'/command',dict(text='/received'))
        self.wait_for(lambda:any('matches' in e['text'] and 'Progression Key' in e['text'] for e in self.state()['events']))
        self.post(self.url+'/command',dict(text='Speichern {v1}'))
        self.wait_for(lambda:any(e['kind']=='sent' and e['text']=='Sent to Archipelago: Speichern {v1}' for e in self.state()['events']))
        self.wait_for(lambda:any(e['kind']=='chat' and 'Host: Speichern {v1}'==e['text'] for e in self.state()['events']))
        self.assertEqual(self.post(self.url+'/recording/start',dict(slot='Friend',consent='1')).json['error'],
                         'Recording requires the host to have their own slot in this active round.')
