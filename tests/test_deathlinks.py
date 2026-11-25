"""Durable bounce identity, conservative attribution, gaps and authorized reads."""
import math
import unittest
from concurrent.futures import ThreadPoolExecutor

import test_ap_console as fixtures
from hub import db, recording
from hub.services import deathlinks


class DeathLinkTests(unittest.TestCase):
    setUp = fixtures.ConsoleTests.setUp
    tearDown = fixtures.ConsoleTests.tearDown
    post = fixtures.ConsoleTests.post
    wait_for = fixtures.ConsoleTests.wait_for

    def reader(self, start=False):
        with self.app.app_context():
            build = db.query('SELECT * FROM seed_builds WHERE id=?', (self.bid,), one=True)
            endpoint = db.query('SELECT * FROM hosted_rooms WHERE build_id=?', (self.bid,), one=True)
            if start:
                return recording.ensure(build, endpoint, transport='ws')
            row = dict(actor_id=1, slot='Host', transport='ws', generation=1, uuid='probe', automatic=1)
            reader = recording.Recorder(row, build, endpoint, '')
        reader.state, reader.team = 'connected', 0
        reader.players = {1:dict(name='Host', type=1), 2:dict(name='Friend', type=1),
                          3:dict(name='Group', type=2)}
        return reader

    def payload(self):
        response = self.client.get(f'/sessions/{self.sid}/builds/{self.bid}/live/deathlinks')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def bounce(self, source='Host', stamp=1234567890.125, **data):
        return dict(cmd='Bounced', tags=['DeathLink'], data=dict(source=source, time=stamp, **data))

    def test_durable_identity_concurrent_recipients_reconnect_and_causes(self):
        reader = self.reader()
        packet = self.bounce(cause='Host fell')
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: reader.packet(packet), range(20)))
        # The same death may be repeated with a different cause or recipient.
        reader.packet(self.bounce(cause='different wording'))
        self.reader().packet(packet)
        reader.packet(self.bounce(stamp=1234567890.126))
        reader.packet(self.bounce('Friend'))
        data = self.payload()
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['ranking'], [dict(slot='Host',count=2), dict(slot='Friend',count=1)])
        self.assertEqual(data['recent'][0]['death_time'], 1234567890.126)
        self.assertEqual(next(r['cause'] for r in data['recent'] if r['source']=='Host' and r['cause']), 'Host fell')
        self.assertFalse(any(p['cmd'] in ('Bounce','Say','ConnectUpdate') for p in self.server.packets))

    def test_alias_collision_unknown_group_case_and_malformed_data(self):
        reader = self.reader()
        reader.deathlink_aliases = {1:'Hero',2:'Host'}
        for source in ('Hero','Host','Unknown','Group','host'):
            reader.packet(self.bounce(source))
        data = self.payload()
        self.assertEqual(data['ranking'], [dict(slot='Host',count=1)])
        self.assertEqual({r['source'] for r in data['unresolved']}, {'Host','Unknown','Group','host'})
        deathlinks.coverage(reader)
        for stamp in (True, None, '123', math.nan, math.inf, -1, 253402300800, 10**400):
            reader.packet(self.bounce(stamp=stamp))
        reader.packet(self.bounce(''))
        reader.packet(dict(cmd='Bounced',tags=['DeathLink'],data=[]))
        reader.packet(self.bounce('\ud800'))
        reader.packet(self.bounce(cause='bad surrogate \ud800'))
        reader.packet(dict(cmd='Bounced',tags='DeathLink',data={}))
        reader.packet(dict(cmd='Bounced',tags=['Other'],data={}))
        reader.state = 'authenticating'
        reader.packet(self.bounce('Before authentication'))
        data = self.payload()
        self.assertEqual(data['total'], 5)
        self.assertEqual(data['invalid_events'], 12)

    def test_coverage_restart_stale_heartbeat_and_idempotent_additive_migration(self):
        reader = self.reader()
        with self.app.app_context():
            deathlinks.migrate(); deathlinks.migrate()
            self.assertEqual(db.query('SELECT COUNT(*) AS n FROM users', one=True)['n'], 2)
        deathlinks.coverage(reader, 100)
        deathlinks.coverage(reader, 105)
        reader.state = 'reconnecting'
        deathlinks.coverage(reader, 109)
        reader.state = 'connected'
        deathlinks.coverage(reader, 110)
        with self.app.app_context():
            build = db.query('SELECT * FROM seed_builds', one=True)
            active = deathlinks.presentation(build, now=114)
            stale = deathlinks.presentation(build, now=140)
            finished = deathlinks.presentation(dict(build,completed_at='1970-01-01T00:01:48+00:00'),now=140)
        self.assertEqual(active['state'], 'recording')
        self.assertEqual(active['gaps'], [dict(start=105,end=110)])
        self.assertEqual(stale['state'], 'waiting')
        self.assertEqual(stale['gaps'][-1], dict(start=110,end=None))
        self.assertEqual(finished['gaps'], [dict(start=105,end=108)])
        deathlinks.coverage(reader, 141)
        with self.app.app_context():
            self.assertEqual(deathlinks.presentation(build,now=142)['gaps'][-1], dict(start=110,end=141))

    def test_permissions_race_and_completed_round(self):
        reader = self.reader(); reader.packet(self.bounce())
        url = f'/sessions/{self.sid}/builds/{self.bid}/live/deathlinks'
        self.assertIn(self.app.test_client().get(url).status_code, (302,401))
        with self.app.app_context():
            db.execute('DELETE FROM lobby_members WHERE user_id=2')
        self.assertEqual(self.friend.get(url).status_code, 403)
        with self.app.app_context():
            build = db.query('SELECT snapshot FROM seed_builds',one=True)
            snapshot = db.loads(build['snapshot']); snapshot['race'] = True
            db.execute('UPDATE seed_builds SET snapshot=?', (db.dumps(snapshot),))
        self.assertIsNone(self.payload()['total'])
        self.assertEqual(self.payload()['recent'], [])
        with self.app.app_context():
            snapshot['race'] = False
            db.execute("UPDATE seed_builds SET snapshot=?, completed_at='today'", (db.dumps(snapshot),))
        self.assertEqual(self.payload()['state'], 'completed')
        self.assertEqual(self.payload()['total'], 1)

    def test_shared_socket_packet_and_reconnect(self):
        reader = self.reader(start=True)
        self.wait_for(lambda:reader.state=='connected' and reader.catalog_ready)
        login = next(p for p in self.server.packets if p['cmd']=='Connect')
        self.assertCountEqual(login['tags'], ['Tracker','ArchipeMANU-Reader','DeathLink'])
        self.server.send(self.server.clients[0], [self.bounce('Friend', cause='<script>unsafe</script>')]*3)
        self.wait_for(lambda:self.payload()['total']==1)
        previous = reader.connected_at
        self.server.clients[0].close()
        self.wait_for(lambda:reader.state=='connected' and reader.connected_at > previous)
        self.server.send(self.server.clients[-1], [self.bounce('Friend'), self.bounce('Unknown')])
        self.wait_for(lambda:self.payload()['total']==2)
        data = self.payload()
        self.assertEqual(data['ranking'], [dict(slot='Friend',count=1)])
        self.assertGreaterEqual(data['gap_count'], 1)
        self.assertFalse(any(p['cmd']=='Bounce' for p in self.server.packets))
