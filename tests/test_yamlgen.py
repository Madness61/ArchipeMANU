"""python -m unittest discover tests"""
import unittest

import yaml
from werkzeug.datastructures import MultiDict

from hub import yamlgen

SCHEMA = {
    "game": "Test Game",
    "slug": "test_game",
    "version": "1.2.0",
    "presets": {},
    "items": ["Sword", "Shield", "Bombs"],
    "locations": ["Chest 1", "Boss"],
    "options": [
        {"key": "goal", "name": "Goal", "kind": "choice", "default": "boss",
         "choices": [["boss", "Boss"], ["all_chests", "All Chests"]], "group": "Game Options", "simple": True},
        {"key": "death_link", "name": "Death Link", "kind": "toggle", "default": False, "group": "Game Options",
         "simple": True},
        {"key": "progression_balancing", "name": "Progression Balancing", "kind": "range", "default": 50,
         "min": 0, "max": 99, "special": {"normal": 50, "disabled": 0}, "group": "Game Options", "simple": True},
        {"key": "start_inventory", "name": "Start Inventory", "kind": "counter", "default": {}, "min": 0,
         "max": None, "valid_keys": [], "items": True, "locations": False, "group": "Item & Location Options",
         "simple": True},
        {"key": "exclude_locations", "name": "Exclude Locations", "kind": "set", "default": [], "valid_keys": [],
         "items": False, "locations": True, "group": "Item & Location Options", "simple": True},
    ],
}


class LayerTests(unittest.TestCase):
    def test_overrides_win_and_defaults_are_dropped(self):
        values = yamlgen.layer(SCHEMA, {"goal": "all_chests", "death_link": True}, {"death_link": False})
        self.assertEqual(values, {"goal": "all_chests"})

    def test_global_overrides_only_for_known_options(self):
        result = yamlgen.global_overrides_for(SCHEMA, {"death_link": True, "progression_balancing": 120})
        self.assertEqual(result, {"death_link": True})


class SlotNameTests(unittest.TestCase):
    def test_duplicates_get_numbers_within_16_chars(self):
        entries = [{"id": 1, "slot_name": "Max"}, {"id": 2, "slot_name": "max"},
                   {"id": 3, "slot_name": "Sixteen_Chars_AB"}, {"id": 4, "slot_name": "Sixteen_Chars_AB"}]
        names = yamlgen.assign_slot_names(entries)
        self.assertEqual(names, {1: "Max", 2: "max2", 3: "Sixteen_Chars_AB", 4: "Sixteen_Chars_A2"})


class FormTests(unittest.TestCase):
    def test_parse_form_keeps_unrendered_and_validates(self):
        form = MultiDict([("_r", "goal"), ("o.goal", "all_chests"), ("_r", "progression_balancing"),
                          ("o.progression_balancing", "disabled"), ("_r", "start_inventory"),
                          ("o.start_inventory", "Sword: 2\nBombs")])
        values, errors = yamlgen.parse_form(SCHEMA, form, {"death_link": True})
        self.assertEqual(errors, {})
        self.assertEqual(values, {"death_link": True, "goal": "all_chests", "progression_balancing": 0,
                                  "start_inventory": {"Sword": 2, "Bombs": 1}})

    def test_unknown_item_is_an_error(self):
        form = MultiDict([("_r", "exclude_locations"), ("o.exclude_locations", "Chest 1\nNope")])
        _values, errors = yamlgen.parse_form(SCHEMA, form, {})
        self.assertIn("exclude_locations", errors)

    def test_range_bounds(self):
        form = MultiDict([("_r", "progression_balancing"), ("o.progression_balancing", "150")])
        _values, errors = yamlgen.parse_form(SCHEMA, form, {})
        self.assertIn("progression_balancing", errors)


class YamlTests(unittest.TestCase):
    def test_player_yaml_roundtrip(self):
        text = yamlgen.player_yaml("Max", SCHEMA, {"goal": "all_chests"}, "Test", "0.6.8")
        doc = yaml.safe_load(text)
        self.assertEqual(doc["name"], "Max")
        self.assertEqual(doc["game"], "Test Game")
        self.assertEqual(doc["requires"], {"version": "0.6.8", "game": {"Test Game": "1.2.0"}})
        self.assertEqual(doc["Test Game"], {"goal": "all_chests"})

    def test_import_collapses_template_weights(self):
        text = """
name: Someone
description: Mein Setup
game: Test Game
Test Game:
  goal:
    boss: 0
    all_chests: 50
  death_link:
    'true': 50
    'false': 0
  progression_balancing:
    random: 0
    normal: 50
  unknown_option: 3
---
name: Other
game:
  Test Game: 1
  Not Installed: 1
Test Game:
  goal:
    boss: 30
    all_chests: 70
"""
        games = {"test_game": {"game": "Test Game"}}
        results, errors = yamlgen.import_yaml(text, games, lambda slug: SCHEMA)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["name"], "Mein Setup")
        self.assertEqual(results[0]["values"], {"goal": "all_chests", "death_link": True})
        self.assertTrue(any("unknown_option" in w for w in results[0]["warnings"]))
        self.assertEqual(results[1]["values"], {"goal": {"boss": 30, "all_chests": 70}})
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
