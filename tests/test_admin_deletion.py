"""Deletion only touches disposable test data, including artifact rollback."""
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.exceptions import Conflict

from hub import admin_deletion, ap_bridge, auth, config, db
from hub.app import create_app
from auth_helpers import provision_user, TEST_PASSWORD


class AdminDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(config, key, value) for key, value in {
            "DATA": self.root, "DB_PATH": self.root / "hub.db", "APWORLDS": self.root / "apworlds",
            "SCHEMAS": self.root / "schemas", "SESSIONS": self.root / "sessions"}.items()]
        self.patches += [patch.object(ap_bridge, "ap_ready", return_value=False),
                         patch.object(ap_bridge, "index", return_value={"games": {}, "failed": {}, "ap_version": "test"})]
        for item in self.patches:
            item.start()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        provision_user(self.app, "Admin", is_admin=True)
        provision_user(self.app, "Other")
        provision_user(self.app, "Victim")
        self.admin = self.app.test_client()
        self.player = self.app.test_client()
        self.post(self.admin, "/login", {"username": "Admin", "password": TEST_PASSWORD})
        self.post(self.player, "/login", {"username": "Victim", "password": TEST_PASSWORD})
        with self.app.app_context():
            self.aid = db.query("SELECT id FROM users WHERE username='Admin'", one=True)["id"]
            self.uid = db.query("SELECT id FROM users WHERE username='Victim'", one=True)["id"]
            self.other = db.query("SELECT id FROM users WHERE username='Other'", one=True)["id"]
            self.sid = db.execute("INSERT INTO sessions(name,created_by) VALUES ('Delete round',?)", (self.uid,))
            db.execute("INSERT INTO lobby_members(session_id,user_id) VALUES (?,?)", (self.sid, self.uid))
            db.execute("INSERT INTO entries(session_id,user_id,game) VALUES (?,?,'test')", (self.sid, self.uid))
            self.bid = self.seed()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def post(self, client, url, data=None):
        client.get("/login")
        with client.session_transaction() as state:
            csrf = state["_csrf"]
        return client.post(url, data={"_csrf": csrf, **(data or {})})

    def seed(self, status="succeeded"):
        bid = db.execute("""INSERT INTO seed_builds(session_id,status,snapshot,created_at)
            VALUES (?,?,?,?)""", (self.sid, status, db.dumps({"slots": [{"player_id": self.uid}]}), "2026-11-08"))
        db.execute("""INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at)
            VALUES (?,'localhost',38281,?,'2026-11-08')""", (bid, self.uid))
        path = config.SESSIONS / "_seeds" / str(bid) / "output"
        path.mkdir(parents=True)
        (path / "seed.zip").write_bytes(b"test archive")
        return bid

    def test_only_admin_post_with_csrf_can_delete(self):
        urls = [f"/admin/users/{self.uid}/delete", f"/admin/sessions/{self.sid}/delete",
                f"/admin/seeds/{self.bid}/delete"]
        for url in urls:
            self.assertEqual(self.post(self.player, url).status_code, 403)
            self.assertEqual(self.admin.post(url).status_code, 403)
            self.assertEqual(self.admin.get(url).status_code, 405)
        self.assertEqual(self.post(self.admin, f"/admin/users/{self.aid}/delete").status_code, 409)
        self.assertEqual(self.post(self.admin, "/admin/seeds/9999/delete").status_code, 404)
        self.assertEqual(self.post(self.admin, "/admin/sessions/9999/delete").status_code, 404)
        self.assertEqual(self.post(self.admin, "/admin/users/9999/delete").status_code, 404)

    def test_single_seed_removes_artifacts_and_hosting_but_preserves_round(self):
        with self.app.app_context():
            other_bid = self.seed()
        response = self.post(self.admin, f"/admin/seeds/{self.bid}/delete")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.query("SELECT * FROM seed_builds WHERE id=?", (self.bid,), one=True))
            self.assertFalse(db.query("SELECT * FROM hosted_rooms WHERE build_id=?", (self.bid,)))
            self.assertIsNotNone(db.query("SELECT * FROM sessions WHERE id=?", (self.sid,), one=True))
            self.assertIsNotNone(db.query("SELECT * FROM seed_builds WHERE id=?", (other_bid,), one=True))
            self.assertFalse(db.query("PRAGMA foreign_key_check"))
        self.assertFalse((config.SESSIONS / "_seeds" / str(self.bid)).exists())
        self.assertTrue((config.SESSIONS / "_seeds" / str(other_bid) / "output/seed.zip").exists())

    def test_round_deletion_removes_all_children_and_legacy_files(self):
        legacy = config.SESSIONS / str(self.sid)
        legacy.mkdir()
        (legacy / "old.zip").write_bytes(b"legacy")
        with self.app.app_context():
            other_bid = self.seed("failed")
            db.execute("INSERT INTO lobby_invites VALUES ('invite',?,'2099-01-01',?)", (self.sid, self.uid))
        self.assertEqual(self.post(self.admin, f"/sessions/{self.sid}/delete").status_code, 302)
        with self.app.app_context():
            for table in ("sessions", "entries", "lobby_members", "lobby_invites", "seed_builds", "hosted_rooms"):
                self.assertFalse(db.query(f"SELECT * FROM {table}"), table)
            self.assertFalse(db.query("PRAGMA foreign_key_check"))
        self.assertFalse(legacy.exists())
        self.assertFalse((config.SESSIONS / "_seeds" / str(other_bid)).exists())

    def test_account_delete_revokes_login_transfers_content_and_does_not_reuse_id(self):
        with self.app.app_context():
            tid = db.execute("INSERT INTO templates(game,name,created_by) VALUES ('test','Shared',?)", (self.uid,))
            db.execute("INSERT INTO community_games(sha256,module,display_name,created_by) VALUES ('hash','test','Test',?)", (self.uid,))
            db.execute("INSERT INTO game_guides(slug,updated_at,author) VALUES ('test','2026-11-08',?)", (self.uid,))
            db.execute("INSERT INTO entries(session_id,user_id,game,ready,ready_hash) VALUES (?,?,'test',1,'old')", (self.sid, self.other))
            db.execute("INSERT INTO account_setup VALUES ('setup',?,?)", (self.uid, time.time() + 60))
            original = db.query("SELECT snapshot FROM seed_builds WHERE id=?", (self.bid,), one=True)["snapshot"]
        self.assertEqual(self.post(self.admin, f"/admin/users/{self.uid}/delete").status_code, 302)
        self.assertEqual(self.player.get("/profile").status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.query("SELECT * FROM users WHERE id=?", (self.uid,), one=True))
            for table in ("entries", "lobby_members", "auth_sessions", "account_setup"):
                self.assertFalse(db.query(f"SELECT * FROM {table} WHERE user_id=?", (self.uid,)))
            self.assertEqual(db.query("SELECT created_by FROM sessions WHERE id=?", (self.sid,), one=True)[0], self.aid)
            self.assertEqual(db.query("SELECT created_by FROM templates WHERE id=?", (tid,), one=True)[0], self.aid)
            self.assertEqual(db.query("SELECT created_by FROM community_games", one=True)[0], self.aid)
            self.assertEqual(db.query("SELECT author FROM game_guides", one=True)[0], self.aid)
            self.assertEqual(db.query("SELECT entered_by FROM hosted_rooms", one=True)[0], self.aid)
            self.assertEqual(db.query("SELECT ready FROM entries", one=True)[0], 0)
            self.assertEqual(db.query("SELECT snapshot FROM seed_builds WHERE id=?", (self.bid,), one=True)[0], original)
            self.assertFalse(db.query("PRAGMA foreign_key_check"))
        fresh = self.app.test_client()
        self.assertEqual(self.post(fresh, "/register", {"username": "NewPlayer", "password": TEST_PASSWORD}).status_code, 302)
        with self.app.app_context():
            new_id = db.query("SELECT id FROM users WHERE username='NewPlayer'", one=True)[0]
            self.assertGreater(new_id, self.uid)

    def test_running_build_blocks_affected_deletions(self):
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET status='running' WHERE id=?", (self.bid,))
        for url in [f"/admin/seeds/{self.bid}/delete", f"/admin/sessions/{self.sid}/delete",
                    f"/admin/users/{self.uid}/delete"]:
            self.assertEqual(self.post(self.admin, url).status_code, 409)
        self.assertTrue((config.SESSIONS / "_seeds" / str(self.bid) / "output/seed.zip").exists())

    def test_database_failure_restores_staged_files(self):
        with self.app.app_context():
            db.execute("""CREATE TRIGGER prevent_round_delete BEFORE DELETE ON sessions
                BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")
            with self.assertRaises(sqlite3.IntegrityError):
                admin_deletion.delete_round(self.sid)
            self.assertIsNotNone(db.query("SELECT id FROM seed_builds WHERE id=?", (self.bid,), one=True))
        self.assertTrue((config.SESSIONS / "_seeds" / str(self.bid) / "output/seed.zip").exists())
        self.assertFalse(list(config.SESSIONS.glob(".delete-*")))

    def test_artifact_paths_cannot_escape_sessions(self):
        with self.assertRaises(Conflict):
            with admin_deletion._artifacts([self.root]):
                self.fail("must not reach deletion")
        self.assertTrue(self.root.is_dir())

    def test_admin_overview_has_all_management_actions(self):
        page = self.admin.get("/admin")
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'/admin/users/{self.uid}/delete'.encode(), page.data)
        self.assertNotIn(f'/admin/users/{self.aid}/delete'.encode(), page.data)
        self.assertIn(f'/admin/sessions/{self.sid}/delete'.encode(), page.data)
        self.assertIn(f'/admin/seeds/{self.bid}/delete'.encode(), page.data)
        self.assertIn(b'data-confirm=', page.data)


if __name__ == "__main__":
    unittest.main()
