"""Group catalog edits persist independently of APWorld versions and options."""
import io
import unittest
from unittest.mock import patch

from hub import ap_bridge, community, db, game_catalog
import test_community as fixtures


class GameMetadataTests(unittest.TestCase):
    setUp = fixtures.CommunityTests.setUp
    tearDown = fixtures.CommunityTests.tearDown
    post = fixtures.CommunityTests.post
    login = fixtures.CommunityTests.login

    def upload(self, client, version="1.0", **fields):
        # A new custom game has no extracted options yet.
        with patch.object(ap_bridge, "index", return_value={**fixtures.INDEX, "games": {}}):
            return self.post(client, "/games/community/add", {
                "apworld": (io.BytesIO(fixtures.world_bytes(version)), "test_world.apworld"), **fields},
                content_type="multipart/form-data")

    def test_upload_edit_search_filter_and_version_update_preserve_metadata(self):
        self.login(self.host, "Host")
        self.login(self.friend, "Friend")
        response = self.upload(self.friend, description="Ein Spiel mit Dungeons.",
                               genres="Action, Puzzle, action", tags="2D, Erkundung, erkundung")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            row = db.query("SELECT * FROM game_metadata", one=True)
            self.assertEqual(db.loads(row["genres"]), ["Action", "Puzzle"])
            self.assertEqual(db.loads(row["tags"]), ["2D", "Erkundung"])
        url = "/games/test_world/metadata/edit"
        self.assertEqual(self.friend.get(url).status_code, 200)
        self.assertEqual(self.post(self.friend, url, {
            "description": "Neue Beschreibung <script>alert(1)</script>",
            "genres": "Adventure", "tags": "Gemeinsamer Abend, 3D"}).status_code, 302)
        page = self.host.get("/games?tag=Gemeinsamer+Abend&genre=Adventure&q=abend").get_data(as_text=True)
        self.assertIn("1 von 1 Spielen", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertEqual(self.host.get("/games?tag=not-a-tag").status_code, 400)
        self.assertEqual(self.upload(self.friend, version="2.0").status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT tags FROM game_metadata", one=True)["tags"],
                             db.dumps(["Gemeinsamer Abend", "3D"]))
            self.assertEqual(len(community.all_games()[0]["versions"]), 2)
        # Pending/inactive worlds also expose the edit action without needing a schema.
        with patch.object(ap_bridge, "index", return_value={**fixtures.INDEX, "games": {}}):
            page = self.friend.get("/games/test_world/setup").get_data(as_text=True)
            self.assertIn("Spiel bearbeiten", page)
            self.assertIn("Gemeinsamer Abend", page)

    def test_edit_permissions_csrf_and_reset(self):
        self.login(self.host, "Host")
        self.login(self.friend, "Friend")
        self.assertEqual(self.upload(self.host, tags="Testtag").status_code, 302)
        url = "/games/test_world/metadata/edit"
        self.assertEqual(self.friend.get(url).status_code, 403)
        self.assertEqual(self.post(self.friend, url, {"tags": "Forbidden"}).status_code, 403)
        self.assertEqual(self.host.post(url, data={"tags": "No CSRF"}).status_code, 403)
        self.assertEqual(self.app.test_client().get(url).status_code, 302)
        self.assertEqual(self.post(self.host, url, {"_action": "reset"}).status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.query("SELECT * FROM game_metadata", one=True))
            self.assertEqual(len(community.all_games()[0]["versions"]), 1)

    def test_validation_precedes_archive_storage_and_retains_form_values(self):
        self.login(self.host, "Host")
        response = self.upload(self.host, tags="x" * 41, description="Mein Entwurf")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Mein Entwurf", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertFalse(db.query("SELECT * FROM community_games"))
            self.assertFalse(db.query("SELECT * FROM game_metadata"))
        self.assertEqual(self.upload(self.host, tags="Valid").status_code, 302)
        response = self.post(self.host, "/games/test_world/metadata/edit", {
            "description": "x" * 1501, "tags": "Keep this draft"})
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.loads(db.query("SELECT tags FROM game_metadata", one=True)["tags"]), ["Valid"])

    def test_added_game_catalog_is_specific_and_editorial_data_is_immutable(self):
        slugs = ["bloodstained_rotn", "tmc", "tboir", "ss", "RE4R", "pseudoregalia", "borderlands2", "borderlands_tps"]
        for slug in slugs:
            info = game_catalog.details(slug, slug)
            self.assertTrue(info["documented"] and info["tags"] and info["genres"])
            self.assertTrue(info["description"] and info["steps"] and info["guide_url"])
        original = game_catalog.details("tmc", "The Minish Cap")
        edited = game_catalog.details("tmc", "The Minish Cap", {
            "description": "Unser Text", "genres": '["Custom"]', "tags": '[]'})
        self.assertEqual(edited["genres"], ["Custom"])
        self.assertEqual(game_catalog.details("tmc", "The Minish Cap"), original)


if __name__ == "__main__":
    unittest.main()
