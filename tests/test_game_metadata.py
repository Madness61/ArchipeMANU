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
                               genres="Action, Puzzle, action")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            row = db.query("SELECT * FROM game_metadata", one=True)
            self.assertEqual(db.loads(row["genres"]), ["Action", "Puzzle"])
            db.execute("UPDATE game_metadata SET tags=?", (db.dumps(["AltbestandStichwort"]),))
        url = "/games/test_world/metadata/edit"
        self.assertEqual(self.friend.get(url).status_code, 200)
        self.assertEqual(self.post(self.friend, url, {
            "description": "Neue Beschreibung <script>alert(1)</script>",
            "genres": "Adventure"}).status_code, 302)
        page = self.host.get("/games?tag=not-a-tag&genre=Adventure&q=Neue").get_data(as_text=True)
        self.assertIn("1 von 1 Spielen", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("AltbestandStichwort", page)
        self.assertNotIn('name="tag"', page)
        self.assertIn("0 von 1 Spielen", self.host.get("/games?q=AltbestandStichwort").get_data(as_text=True))
        self.assertEqual(self.upload(self.friend, version="2.0").status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT tags FROM game_metadata", one=True)["tags"],
                             db.dumps(["AltbestandStichwort"]))
            self.assertEqual(len(community.all_games()[0]["versions"]), 2)
        # Pending/inactive worlds also expose the edit action without needing a schema.
        with patch.object(ap_bridge, "index", return_value={**fixtures.INDEX, "games": {}}):
            page = self.friend.get("/games/test_world/setup").get_data(as_text=True)
            self.assertIn('aria-label="Beschreibung bearbeiten"', page)
            self.assertNotIn('id="game-tags"', page)
            self.assertNotIn("AltbestandStichwort", page)

    def test_edit_permissions_csrf_and_reset(self):
        self.login(self.host, "Host")
        self.login(self.friend, "Friend")
        self.assertEqual(self.upload(self.host, genres="Testgenre").status_code, 302)
        url = "/games/test_world/metadata/edit"
        self.assertEqual(self.friend.get(url).status_code, 403)
        self.assertEqual(self.post(self.friend, url, {"genres": "Forbidden"}).status_code, 403)
        self.assertEqual(self.host.post(url, data={"genres": "No CSRF"}).status_code, 403)
        self.assertEqual(self.app.test_client().get(url).status_code, 302)
        self.assertEqual(self.post(self.host, url, {"_action": "reset"}).status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.query("SELECT * FROM game_metadata", one=True))
            self.assertEqual(len(community.all_games()[0]["versions"]), 1)

    def test_validation_precedes_archive_storage_and_retains_form_values(self):
        self.login(self.host, "Host")
        response = self.upload(self.host, genres="x" * 41, description="Mein Entwurf")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Mein Entwurf", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertFalse(db.query("SELECT * FROM community_games"))
            self.assertFalse(db.query("SELECT * FROM game_metadata"))
        self.assertEqual(self.upload(self.host, genres="Valid").status_code, 302)
        response = self.post(self.host, "/games/test_world/metadata/edit", {
            "description": "x" * 1501, "genres": "Keep this draft"})
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.loads(db.query("SELECT genres FROM game_metadata", one=True)["genres"]), ["Valid"])

    def test_added_game_catalog_is_specific_and_editorial_data_is_immutable(self):
        slugs = ["bloodstained_rotn", "tmc", "tboir", "ss", "RE4R", "pseudoregalia", "borderlands2", "borderlands_tps"]
        for slug in slugs:
            info = game_catalog.details(slug, slug)
            self.assertTrue(info["documented"] and info["genres"])
            self.assertTrue(info["description"] and info["steps"] and info["guide_url"])
        original = game_catalog.details("tmc", "The Minish Cap")
        edited = game_catalog.details("tmc", "The Minish Cap", {
            "description": "Unser Text", "genres": '["Custom"]'})
        self.assertEqual(edited["genres"], ["Custom"])
        self.assertEqual(game_catalog.details("tmc", "The Minish Cap"), original)

    def test_open_overview_for_loaded_and_unloaded_games_preserves_old_bookmarks(self):
        self.login(self.host, "Host")
        self.upload(self.host, description="Unsere Beschreibung", genres="Puzzle")
        library = self.host.get("/games").get_data(as_text=True)
        self.assertNotIn('>Spiel bearbeiten</a>', library)
        self.assertNotIn('>Anleitung &amp; Voraussetzungen</a>', library)
        self.assertIn('href="/games/test_world">Spiel öffnen', library)
        for schema in (fixtures.SCHEMA, None):
            with self.subTest(loaded=bool(schema)), patch.object(ap_bridge, "schema", return_value=schema):
                for path in ("/games/test_world", "/games/test_world/setup"):
                    response = self.host.get(path)
                    self.assertEqual(response.status_code, 200)
                    page = response.get_data(as_text=True)
                    self.assertLess(page.index('id="game-description"'), page.index('id="game-guide"'))
                    self.assertEqual(page.count('class="game-description">Unsere Beschreibung'), 1)
                    self.assertIn('aria-label="Genres bearbeiten"', page)
                    self.assertIn('aria-label="Installationsanleitung bearbeiten"', page)
                    if schema is None:
                        self.assertIn("Checks und Vorlagen sind verfügbar", page)
        self.assertEqual(self.host.get("/games/not_known").status_code, 404)

    def test_single_field_updates_preserve_other_fields_and_reject_posted_neighbors(self):
        self.login(self.host, "Host")
        self.upload(self.host, description="Original", genres="Puzzle")
        url = "/games/test_world/metadata/edit"
        for field, value in (("description", "Neuer Text"), ("genres", "Action")):
            response = self.post(self.host, url, {"_section": field, field: value,
                                                 "author": "999", "ignored": "bad"})
            self.assertEqual(response.location, f"/games/test_world#game-{field}")
        self.post(self.host, url, {"_section": "description", "description": "Letzter Text", "genres": "Stale"})
        self.assertEqual(self.post(self.host, url, {"_section": "tags", "tags": "Stale"}).status_code, 400)
        with self.app.app_context():
            row = db.query("SELECT * FROM game_metadata", one=True)
            self.assertEqual(row["description"], "Letzter Text")
            self.assertEqual(db.loads(row["genres"]), ["Action"])
            self.assertEqual(row["author"], 1)

    def test_partial_edit_keeps_curated_genres(self):
        self.login(self.host, "Host")
        with patch.object(ap_bridge, "index", return_value={**fixtures.INDEX, "games": {
                "borderlands2": {"game": "Borderlands 2", "version": "1"}}}):
            response = self.post(self.host, "/games/borderlands2/metadata/edit", {
                "_section": "description", "description": "Unser Text"})
            self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            row = dict(db.query("SELECT * FROM game_metadata", one=True))
        self.assertEqual(game_catalog.details("borderlands2", "Borderlands 2", row)["genres"],
                         game_catalog.details("borderlands2", "Borderlands 2")["genres"])

    def test_invalid_partial_edit_retains_draft_and_does_not_write_other_fields(self):
        self.login(self.host, "Host")
        self.upload(self.host, description="Original", genres="Puzzle")
        url = "/games/test_world/metadata/edit"
        response = self.post(self.host, url, {"_section": "genres", "genres": "x" * 41})
        self.assertEqual(response.status_code, 400)
        page = response.get_data(as_text=True)
        self.assertIn('name="_section" value="genres"', page)
        self.assertIn("x" * 41, page)
        self.assertNotIn('name="description"', page)
        self.assertEqual(self.post(self.host, url, {"_section": "author", "author": "2"}).status_code, 400)
        with self.app.app_context():
            row = db.query("SELECT * FROM game_metadata", one=True)
            self.assertEqual((row["description"], db.loads(row["genres"])), ("Original", ["Puzzle"]))

    def test_contextual_actions_keep_existing_permissions_and_csrf(self):
        self.login(self.host, "Host")
        self.login(self.friend, "Friend")
        self.upload(self.host)
        page = self.friend.get("/games/test_world").get_data(as_text=True)
        self.assertNotIn('aria-label="Beschreibung bearbeiten"', page)
        self.assertIn('aria-label="Installationsanleitung bearbeiten"', page)
        url = "/games/test_world/metadata/edit"
        self.assertEqual(self.post(self.friend, url, {"_section": "genres", "genres": "Forbidden"}).status_code, 403)
        self.assertEqual(self.host.post(url, data={"_section": "genres", "genres": "No CSRF"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
