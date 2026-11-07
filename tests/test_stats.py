"""Overview semantics and spoiler data from the generator, without real APWorlds."""
from enum import IntFlag
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ap_runner
from hub import stats


class OverviewTests(unittest.TestCase):
    def test_same_game_slots_are_grouped_and_world_counts_stay_distinct(self):
        data = stats.aggregate_placements([
            {"id":1, "name":"A", "game":"Sekiro"},
            {"id":2, "name":"B", "game":"Sekiro"},
            {"id":3, "name":"C", "game":"Borderlands 2"},
        ], [(1, 3, "progression"), (1, 3, "filler"), (2, 1, "trap"), (3, 2, "useful")])
        games = {g["name"]: g for g in stats.game_overview(data)}
        self.assertEqual(games["Sekiro"]["items"], 2)
        self.assertEqual(games["Sekiro"]["locations"], 3)
        self.assertEqual(len(games["Sekiro"]["players"]), 2)
        self.assertEqual(games["Borderlands 2"]["items"], 2)
        self.assertEqual(games["Borderlands 2"]["locations"], 1)
        self.assertEqual(sum(g["share"] for g in games.values()), 100)

    def test_empty_seed_has_zero_shares(self):
        data = stats.aggregate_placements([{"id":1,"name":"A","game":"Test"}], [])
        self.assertEqual(stats.game_overview(data)[0]["share"], 0)


class RunnerStatisticsTests(unittest.TestCase):
    def test_named_placements_match_summary_and_race_writes_no_analytics(self):
        class Classification(IntFlag):
            filler = 0
            progression = 1
            useful = 2
            trap = 4

        def location(address, finder, recipient, code, category):
            return SimpleNamespace(address=address, player=finder, name="Hidden chest",
                                   item=SimpleNamespace(player=recipient, code=code, name="Secret sword",
                                                        classification=category))

        world = SimpleNamespace(
            player_ids=[1, 2], game={1:"Game A",2:"Game B"}, get_player_name=lambda p: f"Player {p}",
            get_filled_locations=lambda: [
                location(10, 1, 2, 20, Classification.progression | Classification.useful),
                location(11, 2, 1, 21, Classification.trap),
                location(None, 1, 2, 22, Classification.filler),
                location(12, 1, 2, None, Classification.filler),
                location(13, 1, 3, 23, Classification.useful),
                location(14, 3, 1, 24, Classification.filler),
            ])
        modules = {
            "Utils":SimpleNamespace(init_logging=lambda *a, **k: None),
            "Generate":SimpleNamespace(main=lambda: (SimpleNamespace(), 123)),
            "Main":SimpleNamespace(main=lambda args, seed: world),
            "BaseClasses":SimpleNamespace(ItemClassification=Classification),
        }
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, modules), patch.object(sys, "argv", []):
            ap_runner.generate("players", folder, 1, False)
            summary = json.loads((Path(folder) / "item_distribution.json").read_text())
            details = json.loads((Path(folder) / "item_placements.json").read_text())
            self.assertTrue(stats.valid_distribution(summary))
            self.assertTrue(stats.valid_item_details(details, summary))
            self.assertEqual(summary["total_placements"], 2)
            self.assertEqual(details["placements"][0]["category"], "progression")
            details["placements"][0]["recipient"] = 1
            self.assertFalse(stats.valid_item_details(details, summary))
            race = Path(folder) / "race"
            race.mkdir()
            ap_runner.generate("players", str(race), 1, True)
            self.assertEqual(list(race.iterdir()), [])
