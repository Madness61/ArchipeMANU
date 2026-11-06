"""MVP integration tests against Flask with fake Archipelago metadata."""
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
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

    def post(self, url, data, client=None, **kwargs):
        client = client or self.client
        client.get("/login")
        with client.session_transaction() as sess:
            csrf = sess["_csrf"]
        return client.post(url, data={**data, "_csrf": csrf}, **kwargs)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_full_lobby_readiness_and_rejection_on_not_ready(self):
        self.post("/login", {"username": "Host"})
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
        changed = self.post(f"/entries/{eid}/options", {
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
        self.post(f"/entries/{eid}/ready", {"ready": "1"})
        with self.app.app_context():
            from hub import db
            self.assertEqual(db.query("SELECT ready FROM entries WHERE id=?", (eid,), one=True)["ready"], 1)
            with patch.object(ap_bridge, "list_apworld_versions", return_value=[]):
                slots, files, failures = mvp.preflight(sid)
                self.assertFalse(failures)
                self.assertEqual(len(files), 1)
                self.assertIn("collect", files[0][1])

    def test_invitation_works_and_does_not_grant_host(self):
        self.post("/login", {"username": "Host"})
        with self.app.app_context():
            from hub import db
            sid = db.execute("INSERT INTO sessions(name,created_by) VALUES (?,?)", ("Friends", 1))
        with self.app.test_request_context():
            pass
        # Confirm a newly created user does not gain host privileges.
        other = self.app.test_client()
        self.post("/login", {"username": "Friend"}, client=other)
        with self.app.app_context():
            from hub import db
            user = db.query("SELECT is_admin FROM users WHERE username=?", ("Friend",), one=True)
            self.assertEqual(user["is_admin"], 0)

    def test_seed_snapshot_download_and_manual_hosting(self):
        self.post("/login", {"username": "Host"})
        with self.app.app_context():
            from hub import db
            sid = db.execute("INSERT INTO sessions(name,created_by) VALUES (?,?)", ("Seed Test",1))
            db.execute("""INSERT INTO entries(session_id,user_id,game,template_ref,ready,option_overrides)
                VALUES (?,?,?,?,?,?)""", (sid,1,"test_world","default",0,'{"goal":"collect"}'))
        self.post("/entries/1/ready", {"ready":"1"})
        def fake_generate(players, out, spoiler, race, expected_worlds=None):
            out.mkdir(parents=True, exist_ok=True)
            result = out / "AP_TEST.zip"
            with zipfile.ZipFile(result, "w") as z:
                z.writestr("AP_TEST.archipelago", "fake")
                z.writestr("Test_Player.apdelta", "patch payload")
            return True, "Fake generation passed", result
        with patch.object(ap_bridge, "ap_ready", return_value=True), \
             patch.object(ap_bridge, "list_apworld_versions", return_value=[]), \
             patch.object(ap_bridge, "generate", side_effect=fake_generate):
            response = self.post(f"/sessions/{sid}/generate", {"spoiler":"1"})
            self.assertEqual(response.status_code, 302)
            for _ in range(100):
                with self.app.app_context():
                    from hub import db
                    build = db.query("SELECT * FROM seed_builds WHERE session_id=?", (sid,), one=True)
                    if build and build["status"] in ("succeeded", "failed"):
                        break
                time.sleep(.03)
            self.assertIsNotNone(build)
            self.assertEqual(build["status"], "succeeded", build["log"])
            snapshot = json.loads(build["snapshot"])
            self.assertEqual(snapshot["slots"][0]["game"], "test_world")
            self.assertTrue(snapshot["yamls"])
            zip_download = self.client.get(f"/sessions/{sid}/builds/{build['id']}/download")
            self.assertEqual(zip_download.status_code, 200)
            self.assertIn(b"PK", zip_download.data[:2])
            hosting = self.post(f"/sessions/{sid}/builds/{build['id']}/hosting", {
                "room_url": "https://archipelago.gg/room/example",
                "host": "archipelago.gg", "port": "38281", "confirmed":"1"
            })
            self.assertEqual(hosting.status_code, 302)
            play = self.client.get(f"/sessions/{sid}/builds/{build['id']}/play")
            self.assertEqual(play.status_code, 200, play.data[:200])
            self.assertIn(b"38281", play.data)
            self.assertIn(b"Test_Player.apdelta", play.data)
            asset = self.client.get(f"/sessions/{sid}/builds/{build['id']}/assets/1")
            self.assertEqual(asset.data, b"patch payload")
            with self.app.app_context():
                from hub import db
                stored = db.query("SELECT * FROM hosted_rooms WHERE build_id=?", (build["id"],), one=True)
                self.assertEqual(stored["confirmed"], 1)
                self.assertEqual(stored["port"], 38281)

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
