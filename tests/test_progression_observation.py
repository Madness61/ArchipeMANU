"""Production snapshot hook with a real local WebSocket and a temporary database."""
import json
import unittest
import test_ap_console as fixtures
from hub import db


class ObservationTests(unittest.TestCase):
    setUp,tearDown,post=fixtures.ConsoleTests.setUp,fixtures.ConsoleTests.tearDown,fixtures.ConsoleTests.post
    wait_for,state,connect=fixtures.ConsoleTests.wait_for,fixtures.ConsoleTests.state,fixtures.ConsoleTests.connect

    def payload(self):
        with self.app.app_context():
            row=db.query("SELECT payload FROM progression_live WHERE build_id=? AND slot_name='Host'",(self.bid,),one=True)
            return db.loads(row['payload']) if row else None

    def test_full_inventory_check_updates_and_disconnect_invalidate_dynamic_state(self):
        self.connect()
        self.wait_for(lambda:self.payload() is not None)
        self.assertTrue(self.payload()['synchronized'])
        self.assertEqual(self.payload()['received'][0]['item'],501)
        with self.server.lock:
            wire=self.server.clients[0]
        wire.send(json.dumps([dict(cmd='RoomUpdate',checked_locations=[1002])]))
        self.wait_for(lambda:1002 in self.payload()['checked'])
        self.assertNotIn(1002,self.payload()['missing'])
        self.post(self.url+'/disconnect',{})
        self.wait_for(lambda:not self.payload()['synchronized'])
