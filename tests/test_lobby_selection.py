"""Lobby drafts use temporary data and cannot alter a saved slot before Apply."""
from copy import deepcopy
import html
import io
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from werkzeug.datastructures import MultiDict
import yaml

from hub import ap_bridge, config, db
from hub.app import create_app, session_entries
from auth_helpers import provision_user, TEST_PASSWORD
from test_mvp import SCHEMA


class LobbySelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.schema = deepcopy(SCHEMA)
        self.patches = [patch.object(config, key, value) for key, value in {
            "DATA": root, "DB_PATH": root / "hub.db", "APWORLDS": root / "apworlds",
            "SCHEMAS": root / "schemas", "SESSIONS": root / "sessions"}.items()]
        self.patches += [patch.object(ap_bridge, "ap_ready", return_value=False),
            patch.object(ap_bridge, "schema", side_effect=lambda slug: self.schema if slug == "test_world" else None),
            patch.object(ap_bridge, "index", return_value={"ap_version": "0.6.8", "failed": {}, "games": {
                "test_world": {"game": "Test World", "version": "1.0.0", "custom": False}}})]
        for p in self.patches:
            p.start()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()
        provision_user(self.app, "Host", is_admin=True)
        self.post("/login", {"username": "Host", "password": TEST_PASSWORD})
        response = self.post("/sessions", {"name": "Draft lobby"})
        self.sid = int(response.location.rsplit("/", 1)[1])
        self.url = f"/sessions/{self.sid}"

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def post(self, path, fields=None, client=None):
        client = client or self.client
        client.get("/login")
        with client.session_transaction() as state:
            csrf = state["_csrf"]
        data = MultiDict(fields or {})
        data["_csrf"] = csrf
        return client.post(path, data=data)

    def draft(self, ref="default"):
        response = self.client.get(self.url, query_string={"game": "test_world", "ref": ref})
        self.assertEqual(response.status_code, 200)
        return self.token(response), response

    def token(self, response):
        match = re.search(r'name="_draft" value="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match, response.data)
        return html.unescape(match.group(1))

    def preview(self, response):
        match = re.search(r'<pre class="log">(.*?)</pre>', response.get_data(as_text=True), re.S)
        self.assertIsNotNone(match, response.data)
        return html.unescape(match.group(1))

    def apply(self, token, action="apply", difficulty="7", goal="collect"):
        return self.post(self.url + "/selection", MultiDict([
            ("_draft", token), ("_action", action), ("_r", "goal"), ("o.goal", goal),
            ("_r", "difficulty"), ("o.difficulty", difficulty)]))

    def entries(self):
        with self.app.app_context():
            return [dict(row) for row in db.query("SELECT * FROM entries ORDER BY id")]

    def test_reopen_generated_lobby_preserves_seed_and_resets_readiness(self):
        token, _ = self.draft()
        self.apply(token)
        with self.app.app_context():
            db.execute("UPDATE entries SET ready=1,ready_hash='old' WHERE session_id=?", (self.sid,))
            db.execute("UPDATE sessions SET locked=1 WHERE id=?", (self.sid,))
            bid = db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,?,?,?)",
                             (self.sid, "succeeded", '{}', '2026-11-08'))
        response = self.post(self.url + "/lock")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertFalse(db.query("SELECT locked FROM sessions WHERE id=?", (self.sid,), one=True)["locked"])
            self.assertEqual(db.query("SELECT status FROM seed_builds WHERE id=?", (bid,), one=True)["status"], "succeeded")
        self.assertFalse(self.entries()[0]["ready"])
        self.assertEqual(self.entries()[0]["ready_hash"], "")

    def test_reopen_blocked_while_generating(self):
        with self.app.app_context():
            db.execute("UPDATE sessions SET locked=1 WHERE id=?", (self.sid,))
            db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,?,?,?)",
                       (self.sid, "running", '{}', '2026-11-08'))
        self.post(self.url + "/lock")
        with self.app.app_context():
            self.assertTrue(db.query("SELECT locked FROM sessions WHERE id=?", (self.sid,), one=True)["locked"])

    def test_direct_base_selection_saves_template_and_profile_without_editor(self):
        self.schema["options"].append({"key": "death_link", "kind": "toggle", "name": "Death Link",
                                      "default": False, "group": "Game Options", "simple": True, "doc": ""})
        with self.app.app_context():
            tid = db.execute("INSERT INTO templates(game,name,vals,created_by) VALUES ('test_world','Collect on easy',?,1)",
                             (db.dumps({"goal": "collect", "difficulty": 2}),))
            db.execute("UPDATE users SET overrides=? WHERE id=1", (db.dumps({"death_link": True}),))
        response = self.post(self.url + "/selection/start", {"game": "test_world", "ref": f"t:{tid}", "_action": "base"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("participants-section", response.location)
        page = self.client.get(response.location)
        self.assertNotIn(b'id="selection-editor"', page.data)
        saved = self.entries()[0]
        self.assertFalse(saved["ready"])
        self.assertEqual(db.loads(saved["option_overrides"]), {})
        with self.app.app_context():
            entry = session_entries(self.sid)[0]
            self.assertEqual(entry["values"]["goal"], "collect")
            self.assertEqual(entry["values"]["difficulty"], 2)
            self.assertTrue(entry["values"]["death_link"])

    def test_direct_defaults_replace_old_edits_and_require_new_readiness(self):
        token, _ = self.draft()
        self.apply(token)
        eid = self.entries()[0]["id"]
        self.post(f"/entries/{eid}/ready", {"ready": "1"})
        response = self.post(self.url + "/selection/start", {"game": "test_world", "ref": "default", "_action": "base"})
        self.assertEqual(response.status_code, 302)
        entry = self.entries()[0]
        self.assertEqual(entry["id"], eid)
        self.assertEqual(db.loads(entry["option_overrides"]), {})
        self.assertEqual(entry["ready"], 0)
        self.assertEqual(entry["ready_hash"], "")

    def test_edit_choice_does_not_commit_and_direct_choice_requires_membership(self):
        response = self.post(self.url + "/selection/start", {"game": "test_world", "ref": "default", "_action": "edit"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(b'id="selection-editor"', self.client.get(response.location).data)
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.client.post(self.url + "/selection/start", data={"game": "test_world", "_action": "base"}).status_code, 403)
        self.post(self.url + "/lock")
        self.assertEqual(self.post(self.url + "/selection/start", {"game": "test_world", "_action": "base"}).status_code, 409)
        self.post(self.url + "/lock")
        self.post(self.url + "/leave")
        self.assertEqual(self.post(self.url + "/selection/start", {"game": "test_world", "_action": "base"}).status_code, 403)

    def test_direct_selection_still_validates_world_and_template(self):
        with patch.object(ap_bridge, "world_error", return_value="World missing"):
            response = self.post(self.url + "/selection/start", {"game": "test_world", "_action": "base"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.entries(), [])
        response = self.post(self.url + "/selection/start", {"game": "test_world", "ref": "t:99999", "_action": "base"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.entries(), [])

    def test_single_value_reset_previews_without_committing_other_changes(self):
        token, _ = self.draft()
        self.apply(token)
        before = self.entries()
        token, page = self.draft()
        self.assertNotIn(b'name="_inherit"', page.data)
        response = self.post(self.url + "/selection", MultiDict([
            ("_draft", token), ("_reset_option", "difficulty"), ("_r", "goal"), ("o.goal", "collect"),
            ("_r", "difficulty"), ("o.difficulty", "999")]))
        self.assertEqual(response.status_code, 200)
        values = yaml.safe_load(self.preview(response))["Test World"]
        self.assertEqual(values["difficulty"], 3)
        self.assertEqual(values["goal"], "collect")
        self.assertEqual(self.entries(), before)
        self.assertEqual(self.post(self.url + "/selection", {"_draft": self.token(response), "_action": "apply"}).status_code, 302)
        self.assertEqual(db.loads(self.entries()[0]["option_overrides"]), {"goal": "collect"})

    def test_template_api_explains_actual_differences(self):
        self.schema["presets"]["Collect"] = {"goal": "collect", "difficulty": 2}
        templates = self.client.get("/api/games/test_world/templates").get_json()
        preset = next(t for t in templates if t["ref"] == "preset:Collect")
        self.assertIn("2 Abweichungen", preset["description"])
        self.assertEqual(len(preset["summary"]), 2)
        self.assertTrue(any(name == "Goal" for name, _ in preset["summary"]))

    def test_join_and_create_enter_lobby_without_a_game(self):
        friend = self.app.test_client()
        provision_user(self.app, "Friend")
        self.post("/login", {"username": "Friend", "password": TEST_PASSWORD}, client=friend)
        joined = self.post(self.url + "/join", client=friend)
        self.assertEqual(joined.location, self.url)
        page = friend.get(joined.location)
        self.assertIn(b"Deine Spielauswahl", page.data)
        self.assertIn(b"Friend", page.data)
        self.assertNotIn(b"Welches Spiel spielst du?", page.data)
        self.assertEqual(self.entries(), [])

    def test_preview_download_and_apply_preserve_exact_yaml(self):
        token, _ = self.draft()
        self.assertEqual(self.entries(), [])
        response = self.apply(token, "preview")
        self.assertEqual(response.status_code, 200)
        preview = self.preview(response)
        self.assertEqual(yaml.safe_load(preview)["Test World"]["difficulty"], 7)
        self.assertEqual(self.entries(), [])
        token = self.token(response)
        downloaded = self.apply(token, "download")
        self.assertEqual(downloaded.data, preview.encode("utf-8"))
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.apply(token).status_code, 302)
        saved = self.entries()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["ready"], 0)
        self.assertEqual(db.loads(saved[0]["option_overrides"]), {"goal": "collect", "difficulty": 7})
        download = self.client.get(self.url + "/yamls.zip")
        self.assertEqual(download.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
            self.assertEqual(archive.read("Host.yaml"), preview.encode("utf-8"))

    def test_game_library_opens_draft_instead_of_saving_a_slot(self):
        response = self.post("/games/test_world/play", {"session": str(self.sid), "ref": "default"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("game=test_world", response.location)
        self.assertIn(b"selection-editor", self.client.get(response.location).data)
        self.assertEqual(self.entries(), [])

    def test_invalid_draft_reset_and_cancel_preserve_saved_ready_selection(self):
        token, _ = self.draft()
        self.apply(token)
        eid = self.entries()[0]["id"]
        self.post(f"/entries/{eid}/ready", {"ready": "1"})
        before = self.entries()
        token, _ = self.draft()
        bad = self.apply(token, difficulty="999")
        self.assertEqual(bad.status_code, 400)
        self.assertIn(b"Muss zwischen 1 und 10", bad.data)
        self.assertEqual(self.entries(), before)
        reset = self.apply(token, "reset")
        self.assertEqual(yaml.safe_load(self.preview(reset))["Test World"]["difficulty"], 3)
        self.client.get(self.url)  # Abbrechen
        self.assertEqual(self.entries(), before)
        self.assertEqual(self.apply(token, difficulty="4").status_code, 302)
        self.assertEqual(self.entries()[0]["id"], eid)
        self.assertEqual(self.entries()[0]["ready"], 0)
        self.assertEqual(self.entries()[0]["ready_hash"], "")

    def test_template_is_frozen_during_draft_and_weighted_values_survive(self):
        with self.app.app_context():
            tid = db.execute("""INSERT INTO templates(game,name,vals,created_by) VALUES
                ('test_world','Weighted',?,1)""", (db.dumps({"goal": {"boss": 20, "collect": 80}}),))
        token, page = self.draft(f"t:{tid}")
        before = self.preview(page)
        with self.app.app_context():
            db.execute("UPDATE templates SET vals=? WHERE id=?", (db.dumps({"goal": "boss"}), tid))
        response = self.post(self.url + "/selection", {"_draft": token, "_action": "apply"})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            entry = session_entries(self.sid)[0]
            self.assertEqual(entry["values"]["goal"], {"boss": 20, "collect": 80})
        download = self.client.get(self.url + "/yamls.zip")
        with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
            self.assertEqual(archive.read("Host.yaml"), before.encode("utf-8"))

    def test_signed_draft_cannot_be_tampered_with_reused_or_applied_by_another_player(self):
        token, _ = self.draft()
        self.assertEqual(self.apply("invalid." + token).status_code, 409)
        self.assertEqual(self.client.post(self.url + "/selection", data={"_draft": token}).status_code, 403)
        friend = self.app.test_client()
        provision_user(self.app, "Friend")
        self.post("/login", {"username": "Friend", "password": TEST_PASSWORD}, client=friend)
        self.post(self.url + "/join", client=friend)
        denied = self.post(self.url + "/selection", {"_draft": token}, client=friend)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.apply(token).status_code, 302)
        self.assertEqual(self.apply(token).status_code, 409)
        self.assertEqual(len(self.entries()), 1)

    def test_changing_game_keeps_old_selection_until_apply_and_reuses_the_slot(self):
        token, _ = self.draft()
        self.apply(token)
        before = self.entries()
        other = {**deepcopy(self.schema), "slug": "other", "game": "Other World"}
        with patch.object(ap_bridge, "schema", side_effect=lambda slug: other if slug == "other" else self.schema):
            page = self.client.get(self.url, query_string={"game": "other", "ref": "default"})
            self.assertEqual(page.status_code, 200)
            self.assertEqual(self.entries(), before)
            token = self.token(page)
            response = self.post(self.url + "/selection", {"_draft": token, "_action": "apply"})
        self.assertEqual(response.status_code, 302)
        after = self.entries()
        self.assertEqual(after[0]["id"], before[0]["id"])
        self.assertEqual(after[0]["game"], "other")
        self.assertEqual(db.loads(after[0]["option_overrides"]), {})
        self.assertEqual(len(after), 1)

    def test_explicit_group_default_does_not_keep_a_different_existing_preset(self):
        with self.app.app_context():
            tid = db.execute("""INSERT INTO templates(game,name,vals,created_by) VALUES
                ('test_world','Other preset',?,1)""", (db.dumps({"goal": "collect"}),))
        token, _ = self.draft(f"t:{tid}")
        self.post(self.url + "/selection", {"_draft": token, "_action": "apply"})
        response = self.client.get(self.url, query_string={"game": "test_world", "ref": ""})
        self.assertEqual(yaml.safe_load(self.preview(response))["Test World"]["goal"], "boss")

    def test_changed_profile_or_schema_requires_reopening_draft(self):
        token, _ = self.draft()
        self.schema["version"] = "2.0.0"
        self.assertEqual(self.apply(token).status_code, 409)
        token, _ = self.draft()
        with self.app.app_context():
            db.execute("UPDATE users SET slot_name='Changed' WHERE id=1")
        self.assertEqual(self.apply(token).status_code, 409)
        self.assertEqual(self.entries(), [])

    def test_locked_lobby_and_removed_membership_reject_draft(self):
        token, _ = self.draft()
        self.post(self.url + "/lock")
        self.assertEqual(self.apply(token).status_code, 409)
        self.post(self.url + "/lock")
        self.post(self.url + "/leave")
        self.assertEqual(self.apply(token).status_code, 403)
        self.assertEqual(self.entries(), [])

    def test_unavailable_world_blocks_apply_and_creates_no_slot(self):
        token, _ = self.draft()
        with patch.object(ap_bridge, "world_error", return_value="APWorld-Version fehlt"):
            response = self.apply(token)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"APWorld-Version fehlt", response.data)
        self.assertEqual(self.entries(), [])
