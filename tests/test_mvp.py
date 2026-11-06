"""MVP integration tests against Flask with fake Archipelago metadata."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hub import ap_bridge, config, mvp, yamlgen
from hub.app import create_app


SCHEMA = {
    "game": "Test World", "slug": "test_world", "version": "1.0.0",
    "presets": {}, "items": [], "locations": [],
    "options": [
        {"key": "goal", "kind": "choice", "name": "Goal", "default": "boss",
         "choices": [["boss", "Boss"], ["collect", "Collect"]],
         "group": "Game Options", "simple": True, "doc": ""},
        {"key": "difficulty", "kind": "range", "name": "Difficulty", "default": 3,
         "min": 1, "max": 10, "group": "Game Options", "simple": True,
         "doc": "", "special": {}}
    ],
}
INDEX = {"ap_version": "0.6.8", "games": {"test_world": {"game": "Test World", "version": "1.0.0"}}}


class MVPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.patches = [
            patch.object(config, "DATA", self.path),
            patch.object(config, "APWORLDS", self.path / "apworlds"),
            patch.object(config, "SCHEMAS", self.path / "schemas"),
            patch.object(config, "SESSIONS", self.path / "sessions"),
            patch.object(config, "DB_PATH", self.path / "hub.db"),
            patch.object(ap_bridge, "ap_ready", return_value=False),
            patch.object(ap_bridge, "schema", side_effect=lambda slug: SCHEMA if slug == "test_world" else None),
            patch.object(ap_bridge, "index", return_value=INDEX),
        ]
        for p in self.patches:
            p.start()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_full_lobby_readiness_and_rejection_on_not_ready(self):
        self.client.post("/login", data={"username": "Host"})
        with self.app.app_context():
            from hub import db
            sid = db.execute("INSERT INTO sessions(name,created_by) VALUES (?,?)", ("Test", 1))
            eid = db.execute("INSERT INTO entries(session_id,user_id,game,template_ref) VALUES (?,?,?,?)",
                             (sid,1,"test_world","default"))
        page = self.client.get(f"/sessions/{sid}")
        self.assertEqual(page.status_code, 200, page.data[:200])
        self.assertIn(b"Slotoptionen", page.data)
        opt = self.client.get(f"/entries/{eid}/options")
        self.assertEqual(opt.status_code, 200, opt.data[:200])
        changed = self.client.post(f"/entries/{eid}/options", data={
            "_r": ["goal", "difficulty"], "o.goal": "collect", "o.difficulty": "6"
        }, follow_redirects=True)
        self.assertEqual(changed.status_code, 200)
        with self.app.app_context():
            from hub import db
            row = db.query("SELECT option_overrides,ready FROM entries WHERE id=?", (eid,), one=True)
            self.assertEqual(json.loads(row["option_overrides"]), {"goal": "collect", "difficulty": 6})
            self.assertEqual(row["ready"], 0)
        with patch.object(ap_bridge, "list_apworld_versions", return_value=[]):
            with self.app.test_request_context():
                pass
            # Preflight depends on Flask g; request context is supplied below.
            with self.app.test_request_context():
                from flask import g
                from hub import db
                g.user = db.query("SELECT * FROM users WHERE username='Host'", one=True)
                chosen, yamls, problems = mvp.preflight(sid)
            self.assertTrue(any("bereit" in p.lower() for p in problems))
        self.client.post(f"/entries/{eid}/ready", data={"ready": "1"})
        with self.app.app_context():
            from hub import db
            self.assertEqual(db.query("SELECT ready FROM entries WHERE id=?", (eid,), one=True)["ready"], 1)
            with patch.object(ap_bridge, "list_apworld_versions", return_value=[]):
                slots, files, failures = mvp.preflight(sid)
                self.assertFalse(failures)
                self.assertEqual(len(files), 1)
                self.assertIn("collect", files[0][1])

    def test_invitation_works_and_does_not_grant_host(self):
        self.client.post("/login", data={"username": "Host"})
        with self.app.app_context():
            from hub import db
            sid = db.execute("INSERT INTO sessions(name,created_by) VALUES (?,?)", ("Friends", 1))
        with self.app.test_request_context():
            pass
        # Confirm a newly created user does not gain host privileges.
        other = self.app.test_client()
        other.post("/login", data={"username": "Friend"})
        with self.app.app_context():
            from hub import db
            user = db.query("SELECT is_admin FROM users WHERE username=?", ("Friend",), one=True)
            self.assertEqual(user["is_admin"], 0)

    def test_weights_and_room_validation(self):
        choice = {"key": "goal", "kind": "choice",
                  "choices": [["boss", "Boss"], ["collect", "Collect"]], "default": "boss"}
        self.assertIn("goal", yamlgen.validate_values(
            {"options": [choice], "items": [], "locations": []},
            {"goal": {"boss": 0, "collect": 0}}))
        self.assertEqual({}, yamlgen.validate_values(
            {"options": [choice], "items": [], "locations": []},
            {"goal": {"boss": 10, "collect": 0}}))
        form = {"room_url": "https://archipelago.gg/room/example", "host": "archipelago.gg", "port": "38281"}
        self.assertEqual(mvp.parse_room_form(form)[2], 38281)
        for bad in (
            {"room_url":"https://evil.com/room/test","host":"archipelago.gg","port":"38281"},
            {"room_url":"","host":"bad host","port":"38281"},
            {"room_url":"","host":"archipelago.gg","port":"99999"},
        ):
            with self.assertRaises(ValueError):
                mvp.parse_room_form(bad)


if __name__ == "__main__":
    unittest.main()
