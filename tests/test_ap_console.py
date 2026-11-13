"""Actual localhost WebSocket tests, isolated SQLite and authenticated HTTP API."""
import json
import socket
import ssl
import time
import unittest
from unittest.mock import patch

from browser_tests.fake_ap import FakeAP
from hub import ap_console, auth, db
import test_mvp as fixtures


class ConsoleTests(unittest.TestCase):
    post = fixtures.MVPTests.post

    def setUp(self):
        fixtures.MVPTests.setUp(self)
        self.server = FakeAP()
        self.server.__enter__()
        self.post("/login",{"username":"Host"})
        self.friend = self.app.test_client()
        self.post("/login",{"username":"Friend"},client=self.friend)
        with self.app.app_context():
            sid = db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Console',1,1)")
            snapshot = {"slots":[{"slot":"Host","game_name":"Test World","game":"test_world","player_id":1},
                                 {"slot":"Friend","game_name":"Test World","game":"test_world","player_id":2}],"race":False}
            self.bid = db.execute("""INSERT INTO seed_builds(session_id,status,snapshot,created_at,seed_name)
                VALUES (?,'succeeded',?,'today','AP_CONSOLE_TEST')""",(sid,db.dumps(snapshot)))
            db.execute("INSERT INTO lobby_members(session_id,user_id) VALUES (?,2)",(sid,))
            db.execute("""INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at)
                VALUES (?,'127.0.0.1',?,1,'today')""",(self.bid,self.server.port))
        self.sid = sid
        self.url = f"/sessions/{sid}/builds/{self.bid}/console"

    def tearDown(self):
        ap_console.stop_all()
        self.server.__exit__(None,None,None)
        fixtures.MVPTests.tearDown(self)

    def wait_for(self, predicate):
        deadline = time.monotonic()+10
        while time.monotonic()<deadline:
            result = predicate()
            if result:
                return result
            time.sleep(.03)
        self.fail("Timed out waiting for local test WebSocket")

    def state(self, client=None, query=""):
        return (client or self.client).get(self.url+"/data"+query).get_json()

    def connect(self, client=None, **fields):
        fields.setdefault("transport", "ws")  # Local protocol fixture deliberately has no TLS.
        response = self.post(self.url+"/connect",fields,client=client)
        self.assertEqual(response.status_code,202,response.data)
        self.wait_for(lambda:self.state(client)["state"] in ("connected","action_required","reconnecting","temporarily_unavailable"))
        return self.state(client)

    def test_real_handshake_delivery_names_and_duplicate_item_packets(self):
        self.assertEqual(self.connect()["state"],"connected")
        self.wait_for(lambda: any("Progression Key" in e["text"] for e in self.state()["events"]))
        self.assertEqual(self.connect(client=self.friend)["state"],"connected")
        self.server.broadcast_item()
        self.wait_for(lambda: len(self.server.clients)==2)
        items = self.state(query="?kind=items")["events"]
        self.assertEqual(len(items),1)
        delivery = items[0]["delivery"]
        self.assertEqual(delivery["sender"],{"name":"Friend","game":"Test World"})
        self.assertEqual(delivery["recipient"]["name"],"Host")
        self.assertEqual(delivery["item"],"Progression Key")
        self.assertEqual(delivery["location"]["name"],"Old Fortress - Chest")
        friend_items=self.friend.get(self.url+"/data?kind=items").get_json()["events"]
        self.assertEqual([(e['id'],e['text'],e['delivery']) for e in friend_items],[(e['id'],e['text'],e['delivery']) for e in items])
        self.assertTrue(items[0]['for_me']);self.assertTrue(friend_items[0]['from_me'])
        hello = next(p for p in self.server.packets if p["cmd"]=="Connect")
        self.assertEqual((hello["game"],hello["tags"],hello["items_handling"],hello["slot_data"]),("",["TextOnly"],7,True))
        self.assertFalse(any(p["cmd"] in ("LocationChecks","StatusUpdate","LocationScouts") for p in self.server.packets))

    def test_default_automatic_transport_and_ws_fallback_before_authentication(self):
        original = ap_console.open_socket
        def negotiate(host, port, secure):
            if secure:
                self.assertFalse(self.server.packets)
                raise ssl.SSLError("local fixture has no TLS")
            return original(host, port, secure)
        with patch.object(ap_console, "open_socket", side_effect=negotiate) as opened:
            # The API default is automatic even when older callers omit transport.
            response = self.post(self.url+"/connect", {})
            self.assertEqual(response.status_code, 202)
            self.wait_for(lambda: self.state()["state"] in ("connected", "action_required"))
            self.assertEqual(self.state()["state"], "connected")
            self.assertEqual(self.state()["transport"], "ws")
            self.assertEqual([c.args[2] for c in opened.call_args_list], [True, False])
        page = self.client.get(self.url).get_data(as_text=True)
        self.assertIn('<option value="auto">Automatisch (empfohlen)</option>', page)

    def test_explicit_ws_failure_has_actionable_error(self):
        with patch.object(ap_console, "open_socket", side_effect=EOFError("private transport internals")):
            state = self.connect(transport="ws")
        self.assertEqual(state["state"], "reconnecting")
        self.assertIn("Automatisch", state["error"])
        self.assertNotIn("private transport internals", state["error"])

    def test_commands_private_hints_and_received_items(self):
        self.connect()
        self.wait_for(lambda: self.state()["catalog_version"]>0)
        self.assertEqual(self.post(self.url+"/command",{"text":"/hint Progression Key"}).status_code,202)
        self.wait_for(lambda:any("Privater Hinweis für Host" in e["text"] for e in self.state()["events"]))
        self.assertFalse(any("Privater Hinweis" in e["text"] for e in self.state(self.friend)["events"]))
        self.assertTrue(any(p.get("cmd")=="Say" and p.get("text")=="!hint Progression Key" for p in self.server.packets))
        self.post(self.url+"/command",{"text":"/received"})
        self.wait_for(lambda:any("Progression Key ← Friend" in e["text"] for e in self.state()["events"]))
        self.post(self.url+"/command",{"text":"/missing Cave"})
        self.wait_for(lambda:any("Deep Cave - Boss" in e["text"] and "/missing" in e["text"] for e in self.state()["events"]))
        self.post(self.url+"/command",{"text":"/items Potion"})
        self.wait_for(lambda:any("Potion" in e["text"] and "/items" in e["text"] for e in self.state()["events"]))

    def test_password_failure_seed_mismatch_and_no_plaintext_persistence(self):
        self.server.password = "Room-secret"
        self.assertEqual(self.connect(password="Wrong-secret")["state"],"action_required")
        self.assertIn("Raumpasswort",self.state()["error"])
        ap_console.stop_all()
        self.assertEqual(self.connect(password="Room-secret")["state"],"connected")
        with self.app.app_context():
            serialized = " ".join(r["payload"] for r in db.query("SELECT payload FROM console_events"))
        self.assertNotIn("Room-secret",serialized)
        self.assertNotIn("Wrong-secret",serialized)
        ap_console.stop_all()
        self.server.seed = "OTHER_SEED"
        self.assertEqual(self.connect(password="Room-secret")["state"],"action_required")
        self.assertIn("anderen Seed",self.state()["error"])

    def test_identity_csrf_race_and_command_restrictions(self):
        self.assertEqual(self.client.post(self.url+"/connect",data={}).status_code,403)
        self.assertEqual(self.post(self.url+"/connect",{"slot":"Friend"}).status_code,403)
        self.assertEqual(self.app.test_client().get(self.url+"/data").status_code,401)
        outsider = self.app.test_client()
        self.post("/login",{"username":"Outsider"},client=outsider)
        self.assertEqual(outsider.get(self.url+"/data").status_code,403)
        for text in ("!admin login secret", "!getitem Sword", "/connect http://metadata", "/unknown", "a\nb"):
            self.assertEqual(self.post(self.url+"/command",{"text":text}).status_code,400)
        self.assertEqual(self.post(self.url+"/command",{"text":"/received"}).status_code,409)
        with self.app.app_context():
            row = db.query("SELECT snapshot FROM seed_builds WHERE id=?",(self.bid,),one=True)
            metadata = db.loads(row["snapshot"]); metadata["race"] = True
            db.execute("UPDATE seed_builds SET snapshot=? WHERE id=?",(db.dumps(metadata),self.bid))
        for suffix in ("", "/data", "/commands"):
            self.assertEqual(self.client.get(self.url+suffix).status_code,403)
        self.assertEqual(self.post(self.url+"/connect",{}).status_code,403)

    def test_journal_pagination_retention_and_address_change(self):
        with self.app.app_context():
            path = db.get().execute("PRAGMA database_list").fetchone()[2]
            endpoint = db.query("SELECT id FROM hosted_rooms",one=True)["id"]
        with patch.object(ap_console,"MAX_EVENTS",120):
            for i in range(130):
                ap_console.record(path,self.bid,None,"items",{"text":f"event-{i}"},hosted_id=endpoint)
        batch = self.state()["events"]
        self.assertEqual(len(batch),100)
        self.assertEqual(batch[-1]["text"],"event-129")
        older = self.state(query=f"?before={batch[0]['id']}")["events"]
        self.assertEqual(len(older),20)
        self.assertEqual(older[0]["text"],"event-10")
        self.assertEqual(self.state(query=f"?after={batch[-1]['id']}")["events"],[])
        with self.app.app_context():
            db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,'127.0.0.1',1234,1,'later')",(self.bid,))
        self.assertEqual(self.state()["events"],[])

    def test_logout_closes_connection_and_keeps_journal(self):
        self.connect()
        with self.app.app_context():
            with self.client.session_transaction() as session:
                token = auth.digest(session["auth_token"])
            current = ap_console.current(self.bid,1,token)
        self.post("/logout",{})
        self.wait_for(lambda:not current.valid())
        self.wait_for(lambda:not current.thread.is_alive())
        self.assertEqual(self.client.get(self.url+"/data").status_code,401)

    def test_package_arriving_during_render_keeps_old_version_for_invalidation(self):
        with self.app.app_context():
            ap_console.record(self.path/'hub.db',self.bid,None,'items',dict(type='item',
                sender='Friend',recipient='Host',sender_game='Test World',recipient_game='Test World',
                item_id=501,location_id=1001))
        real_events=ap_console.events
        def arriving_package(*args,**kwargs):
            rows=real_events(*args,**kwargs)
            db.execute('INSERT INTO console_packages(build_id,game,items,locations,updated_at) VALUES (?,?,?,?,?)',
                       (self.bid,'Test World',db.dumps({'501':'Progression Key'}),db.dumps({'1001':'Chest'}),123))
            return rows
        with patch.object(ap_console,'events',side_effect=arriving_package):
            first=self.state()
        self.assertEqual(first['catalog_version'],0)
        self.assertIn('Item #501',first['events'][0]['text'])
        next_state=self.state()
        self.assertEqual(next_state['catalog_version'],123)
        self.assertIn('Progression Key',next_state['events'][0]['text'])


class SocketAddressTests(unittest.TestCase):
    def test_automatic_prefers_tls_without_opening_plaintext_connection(self):
        sentinel = object()
        with patch.object(ap_console, "open_socket", return_value=sentinel) as opened:
            self.assertEqual(ap_console.connect_transport("room.example", 1234), (sentinel, "wss"))
            opened.assert_called_once_with("room.example", 1234, True)

    def test_invalid_certificate_never_falls_back_to_plaintext(self):
        with patch.object(ap_console, "open_socket", side_effect=ssl.SSLCertVerificationError("bad cert")) as opened:
            with self.assertRaises(ssl.SSLCertVerificationError):
                ap_console.connect_transport("room.example", 1234)
            self.assertEqual(opened.call_count, 1)

    def test_explicit_transport_does_not_fallback(self):
        for secure in (True, False):
            with self.subTest(secure=secure), patch.object(ap_console, "open_socket", side_effect=EOFError) as opened:
                with self.assertRaises(EOFError):
                    ap_console.connect_transport("room.example", 1234, secure)
                opened.assert_called_once_with("room.example", 1234, secure)

    def test_connection_diagnostics_do_not_expose_exception_contents(self):
        for exc, fragment in ((socket.gaierror("secret"), "aufgelöst"),
                              (ConnectionRefusedError("secret"), "aktuellen Port"),
                              (TimeoutError("secret"), "nicht rechtzeitig"),
                              (ssl.SSLCertVerificationError("secret"), "TLS-Zertifikat")):
            message = ap_console.connection_error(exc)
            self.assertIn(fragment, message)
            self.assertNotIn("secret", message)

    def test_metadata_addresses_are_rejected_before_socket_creation(self):
        for target in ("169.254.169.254", "224.0.0.1", "0.0.0.0", "fe80::1", "::ffff:169.254.169.254"):
            with patch("hub.ap_console.socket.getaddrinfo",return_value=[(2,1,6,"",(target,38281))]), \
                    patch("hub.ap_console.socket.socket") as raw:
                with self.subTest(target=target):
                    with self.assertRaises(ValueError):
                        ap_console.open_socket("untrusted.example",38281,False)
                    raw.assert_not_called()
