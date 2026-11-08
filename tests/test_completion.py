"""Manual goal confirmations belong to seed participants, not mutable lobby entries."""
import json
import unittest
import zipfile

import test_mvp as fixtures
from hub import config, db, mvp


class CompletionTests(unittest.TestCase):
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    post = fixtures.MVPTests.post

    def seed(self, sid=None, hosted=True, status="succeeded", race=False, duplicate=False):
        self.post("/login", {"username": "Host"})
        self.friend = self.app.test_client()
        self.post("/login", {"username": "Friend"}, client=self.friend)
        with self.app.app_context():
            if sid is None:
                sid = db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Finish test',1,1)")
                for uid in (1, 2):
                    db.execute("INSERT INTO lobby_members(session_id,user_id) VALUES (?,?)", (sid, uid))
            slots = [dict(player_id=uid, slot=name, game="test_world", game_name="Test World", game_version="1.0.0")
                     for uid, name in ((1, "Host"), (2, "Friend"))]
            if duplicate:
                slots.append({**slots[0], "slot": "Host2"})
            bid = db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at,zip_name) VALUES (?,?,?,?,?)",
                             (sid, status, json.dumps(dict(slots=slots, race=race)), mvp.utc_now(), "AP_TEST.zip"))
            if hosted:
                db.execute("INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at) VALUES (?,?,?,?,?)",
                           (bid, "archipelago.gg", 38281, 1, mvp.utc_now()))
            folder = config.SESSIONS / "_seeds" / str(bid) / "output"
            folder.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(folder / "AP_TEST.zip", "w") as archive:
                archive.writestr("AP_TEST.archipelago", "test")
        return sid, bid, f"/sessions/{sid}/builds/{bid}"

    def state(self, bid):
        with self.app.app_context():
            return dict(db.query("SELECT * FROM seed_builds WHERE id=?", (bid,), one=True))

    def test_all_players_finish_once_and_round_remains_in_history(self):
        sid, bid, url = self.seed(duplicate=True, race=True)
        page = self.client.get(url + "/play")
        self.assertIn(b"0 von 2 fertig", page.data)
        self.assertIn(b"Ich bin fertig", page.data)
        self.post(url + "/finish", {"finished": "1"})
        self.post(url + "/finish", {"finished": "1"})
        self.assertIsNone(self.state(bid)["completed_at"])
        self.assertIn(b"1 von 2 fertig", self.friend.get(url + "/play").data)
        self.post(url + "/finish", {"finished": "1"}, client=self.friend)
        self.assertTrue(self.state(bid)["completed_at"])
        with self.app.app_context():
            room = db.query("SELECT * FROM sessions WHERE id=?", (sid,), one=True)
            self.assertTrue(room["locked"] and room["completed_at"])
            self.assertEqual(db.query("SELECT COUNT(*) AS n FROM seed_completions", one=True)["n"], 2)
        page = self.client.get(url + "/play")
        self.assertIn(b"Abgeschlossene Runde", page.data)
        self.assertNotIn(b">Ich bin fertig</button>", page.data)
        self.assertNotIn(b">Verbindung speichern</button>", page.data)
        self.assertNotIn(b">Aktive Lobby</a>", self.client.get("/seeds").data)
        self.assertIn(b"Abgeschlossen", self.client.get("/seeds").data)
        self.assertIn(b"Abgeschlossen", self.client.get(f"/sessions/{sid}").data)
        download = self.client.get(url + "/download")
        self.assertEqual(download.status_code, 200)
        download.close()
        # A stale page cannot undo completion or resurrect the seed via hosting.
        self.post(url + "/finish", {"finished": "0"})
        self.assertTrue(self.state(bid)["completed_at"])
        self.assertEqual(self.post(url + "/hosting", {"host": "archipelago.gg", "port": "38281"}).status_code, 409)

    def test_confirmation_can_be_retracted_until_everyone_finishes(self):
        _, bid, url = self.seed()
        self.post(url + "/finish", {"finished": "1"})
        self.post(url + "/finish", {"finished": "0"})
        self.post(url + "/finish", {"finished": "1"}, client=self.friend)
        self.assertIsNone(self.state(bid)["completed_at"])
        self.assertIn(b"1 von 2 fertig", self.client.get(url + "/play").data)

    def test_completion_requires_own_slot_csrf_and_hosted_successful_seed(self):
        sid, _, url = self.seed()
        outsider = self.app.test_client()
        self.post("/login", {"username": "Visitor"}, client=outsider)
        self.assertEqual(self.post(url + "/finish", {"finished": "1"}, client=outsider).status_code, 403)
        self.assertEqual(self.client.post(url + "/finish", data={"finished": "1"}).status_code, 403)
        with self.app.app_context():
            # Even an administrator with room access cannot finish for someone else.
            db.execute("UPDATE users SET is_admin=1 WHERE username='Visitor'")
        self.assertEqual(self.post(url + "/finish", {"finished": "1"}, client=outsider).status_code, 403)
        for kwargs in (dict(hosted=False), dict(status="running"), dict(status="failed")):
            _, _, other = self.seed(sid=sid, **kwargs)
            self.assertEqual(self.post(other + "/finish", {"finished": "1"}).status_code, 409)

    def test_completed_latest_connection_does_not_resurrect_old_seed(self):
        sid, _, old = self.seed()
        _, bid, current = self.seed(sid=sid)
        _, _, another = self.seed()
        self.post(current + "/finish", {"finished": "1"})
        self.post(current + "/finish", {"finished": "1"}, client=self.friend)
        target = self.client.get("/active-lobby")
        self.assertEqual(target.status_code, 302)
        self.assertTrue(target.location.endswith(another + "/play"))
        self.assertTrue(self.state(bid)["completed_at"])
        self.assertEqual(self.client.get(old + "/play").status_code, 200)

    def test_finishing_old_seed_or_reopened_lobby_does_not_close_new_preparation(self):
        sid, bid, old = self.seed()
        _, _, current = self.seed(sid=sid)
        self.post(old + "/finish", {"finished": "1"})
        self.post(old + "/finish", {"finished": "1"}, client=self.friend)
        self.assertTrue(self.state(bid)["completed_at"])
        with self.app.app_context():
            self.assertIsNone(db.query("SELECT completed_at FROM sessions WHERE id=?", (sid,), one=True)["completed_at"])
        self.post(f"/sessions/{sid}/lock", {})
        self.post(current + "/finish", {"finished": "1"})
        self.post(current + "/finish", {"finished": "1"}, client=self.friend)
        with self.app.app_context():
            room = db.query("SELECT locked,completed_at FROM sessions WHERE id=?", (sid,), one=True)
            self.assertFalse(room["locked"])
            self.assertIsNone(room["completed_at"])

    def test_deleted_accounts_do_not_block_and_seed_deletion_cleans_confirmations(self):
        _, bid, url = self.seed()
        with self.app.app_context():
            db.execute("DELETE FROM users WHERE id=2")
        self.post(url + "/finish", {"finished": "1"})
        self.assertTrue(self.state(bid)["completed_at"])
        self.assertIn("Account gelöscht".encode(), self.client.get(url + "/play").data)
        self.assertEqual(self.post(f"/admin/seeds/{bid}/delete", {}).status_code, 302)
        with self.app.app_context():
            self.assertFalse(db.query("SELECT 1 FROM seed_completions WHERE build_id=?", (bid,), one=True))


if __name__ == "__main__":
    unittest.main()
