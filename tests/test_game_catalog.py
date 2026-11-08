"""Setup facts and filter semantics must not imply a configured player machine."""
import unittest
from urllib.parse import urlsplit

from hub import game_catalog


class GameCatalogTests(unittest.TestCase):
    def row(self, slug, name, **extra):
        return dict(slug=slug, name=name, added_by="Host", installed=True, active=True,
                    custom=False, versions=[], **extra)

    def test_every_documented_game_has_specific_setup_and_sources(self):
        self.assertEqual(set(game_catalog.CATALOG), set(game_catalog._SOURCES))
        self.assertTrue({"borderlands2", "borderlands_tps", "pseudoregalia", "RE4R"} <= set(game_catalog.CATALOG))
        for slug in game_catalog.CATALOG:
            with self.subTest(game=slug):
                info = game_catalog.details(slug, slug)
                self.assertTrue(info["documented"])
                self.assertTrue(info["genres"])
                self.assertNotEqual(info["setup_type"], "unknown")
                self.assertTrue(info["requirements"] and info["steps"])
                self.assertTrue(info["guide_url"] and info["source_url"])
                self.assertTrue(info["links"])
                for url in [info["guide_url"], info["source_url"], *(v["url"] for v in info["links"])]:
                    parsed = urlsplit(url)
                    self.assertIn(parsed.scheme, ("http", "https"))
                    self.assertTrue(parsed.hostname)
                    self.assertFalse(parsed.username)

    def test_rom_and_mod_games_have_distinct_requirements(self):
        smw = game_catalog.details("smw", "Super Mario World")
        aquaria = game_catalog.details("aquaria", "Aquaria")
        self.assertEqual(smw["setup_type"], "rom")
        self.assertIn("Super Mario World (USA).sfc", smw["requirements"][0])
        self.assertIn("Generator-Rechner", smw["steps"][0])
        self.assertEqual(aquaria["setup_type"], "mod")
        self.assertIn("Kopie", aquaria["steps"][0])
        self.assertTrue(any("Aquaria_Randomizer" in link["url"] for link in aquaria["links"]))
        self.assertEqual(game_catalog.details("paint", "Paint")["setup_type"], "browser")

    def test_host_rom_reminders_are_specific_and_deduplicated(self):
        entries = [dict(game="smw", game_name="Super Mario World"),
                   dict(game="smw", game_name="Super Mario World"),
                   dict(game="pokemon_emerald", game_name="Pokemon Emerald"),
                   dict(game="aquaria", game_name="Aquaria")]
        reminders = game_catalog.host_rom_requirements(entries)
        self.assertEqual([v["slug"] for v in reminders], ["smw", "pokemon_emerald"])
        self.assertIn("Super Mario World (USA).sfc", reminders[0]["required"])
        self.assertIsNone(reminders[1]["required"])
        self.assertEqual(game_catalog.SUPPORT_STATES["loaded"], "Für Lobby auswählbar")

    def test_unknown_upload_has_no_invented_genre_or_readiness(self):
        row = self.row("new_world", "New World")
        row.update(custom=True, versions=[{"source_url": "javascript:alert(1)"},
                                         {"source_url": "https://example.org/mod/setup"}])
        enriched = game_catalog.enrich([row])[0]
        self.assertEqual(enriched["support_state"], "loaded")
        self.assertEqual(enriched["catalog"]["setup_type"], "unknown")
        self.assertEqual(enriched["catalog"]["genres"], ["Noch nicht zugeordnet"])
        self.assertFalse(enriched["catalog"]["documented"])
        self.assertEqual(enriched["catalog"]["guide_url"], "https://example.org/mod/setup")

    def test_filters_combine_genre_setup_search_and_support(self):
        rows = game_catalog.enrich([self.row("smw", "Super Mario World"),
                                   self.row("aquaria", "Aquaria"), self.row("paint", "Paint")])
        result = [v["slug"] for v in rows if game_catalog.matches(
            v, q="SUPER", genre="Jump ’n’ Run", setup="rom", state="loaded", kind="builtin")]
        self.assertEqual(result, ["smw"])
        self.assertFalse(game_catalog.matches(rows[0], setup="browser"))
        self.assertFalse(game_catalog.matches(rows[0], genre="Metroidvania"))
        self.assertTrue(game_catalog.matches(rows[1], q="metroidvania"))
        self.assertTrue(game_catalog.matches(rows[2], setup="browser"))


if __name__ == "__main__":
    unittest.main()
