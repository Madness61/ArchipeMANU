"""Real local sockets; no external room or player is contacted."""
import time
import unittest
from unittest.mock import patch
import test_ap_console as console_fixtures
from hub import ap_console, auth, db, live_api


class ReliabilityTests(unittest.TestCase):
    setUp, tearDown, post = console_fixtures.ConsoleTests.setUp, console_fixtures.ConsoleTests.tearDown, console_fixtures.ConsoleTests.post
    wait_for, state, connect = console_fixtures.ConsoleTests.wait_for, console_fixtures.ConsoleTests.state, console_fixtures.ConsoleTests.connect
    def current(self):
        with self.app.app_context(), self.client.session_transaction() as session:
            return ap_console.current(self.bid, 1, auth.digest(session['auth_token']))

    def test_background_over_thirty_minutes_keeps_explicit_connection(self):
        self.connect()
        client=self.current()
        client.last_seen=time.monotonic()-7200
        time.sleep(.7)
        self.assertTrue(client.thread.is_alive())
        self.assertEqual(client.state,'connected')

    def test_plain_websocket_does_not_keep_tcp_connect_timeout(self):
        self.connect(transport='ws')
        self.assertIsNone(self.current().wire.socket.gettimeout())

    def test_reconnect_resynchronizes_deduplicates_and_never_replays_say(self):
        with patch.object(ap_console,'RETRY_BASE',.1), patch.object(ap_console,'RETRY_MAX',.2):
            self.connect()
            self.post(self.url+'/command',{'text':'one explicit message'})
            self.wait_for(lambda:any(p.get('text')=='one explicit message' for p in self.server.packets))
            self.server.interrupt()
            self.wait_for(lambda:len([p for p in self.server.packets if p['cmd']=='Connect'])>=2)
            client=self.current()
            self.wait_for(lambda:client.state=='connected' and client.items_synced)
            self.wait_for(lambda:len(client.received)==1)
            self.assertEqual(len([p for p in self.server.packets if p.get('text')=='one explicit message']),1)
            self.assertEqual(len(self.state(query='?kind=items')['events']),1)
            self.assertTrue(any('Lücke' in e['text'] for e in self.state()['events']))
            self.assertEqual(self.state()['game_client_connection'],'unknown')

    def test_disconnect_and_revocation_stop_retry_and_clear_password(self):
        with patch.object(ap_console,'RETRY_BASE',2):
            self.connect()
            client=self.current()
            self.server.interrupt()
            self.wait_for(lambda:client.state=='reconnecting')
            self.post(self.url+'/disconnect',{})
            self.wait_for(lambda:not client.thread.is_alive())
            count=len(self.server.packets)
            time.sleep(.3)
            self.assertEqual(len(self.server.packets),count)
            self.assertIsNone(client.password)

    def test_authorization_change_while_waiting_prevents_new_connection(self):
        with patch.object(ap_console,'RETRY_BASE',.3):
            self.connect()
            client=self.current()
            self.server.interrupt()
            self.wait_for(lambda:client.state=='reconnecting')
            with self.app.app_context():
                db.execute('UPDATE seed_builds SET completed_at=? WHERE id=?',('done',self.bid))
            self.wait_for(lambda:not client.thread.is_alive())
            self.assertEqual(len([p for p in self.server.packets if p['cmd']=='Connect']),1)

    def test_ping_timeout_reconnects_without_polling(self):
        from unittest.mock import Mock
        self.connect()
        client=self.current()
        missing_pong=Mock()
        missing_pong.wait.return_value=False
        with patch.object(ap_console,'PING_SECONDS',.05), patch.object(ap_console,'RETRY_BASE',1), patch.object(client.wire,'ping',return_value=missing_pong):
            self.wait_for(lambda:client.state=='reconnecting')
        self.wait_for(lambda:client.state=='connected' and client.items_synced)
        self.assertGreaterEqual(len([p for p in self.server.packets if p['cmd']=='Connect']),2)

    def test_new_endpoint_revokes_old_worker(self):
        with patch.object(ap_console,'GUARD_SECONDS',.1):
            self.connect()
            client=self.current()
            with self.app.app_context():
                db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,'127.0.0.1',1234,1,'later')",(self.bid,))
            self.wait_for(lambda:not client.thread.is_alive())
            self.assertIsNone(client.password)
            self.assertEqual(client.state,'disconnected')


class RetryHeaderTests(unittest.TestCase):
    def test_retry_after_seconds_date_and_malformed(self):
        from email.utils import formatdate
        self.assertEqual(live_api.retry_delay({'Retry-After':'120'}),120)
        with patch.object(live_api.time,'time',return_value=1000):
            self.assertEqual(live_api.retry_delay({'Retry-After':formatdate(1300,usegmt=True)}),300)
        self.assertEqual(live_api.retry_delay({'Retry-After':'nonsense'},300),300)
        self.assertEqual(live_api.retry_delay({'Retry-After':'0'}),60)
