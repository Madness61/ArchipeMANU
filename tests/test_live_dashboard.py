"""Official API-shaped fixtures; no Archipelago server is contacted."""
from copy import deepcopy
import io
import json
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import test_mvp as fixtures
from hub import db, live_api, live_metrics, live_store

ROOM_ID = "AAECAwQFBgcICQoLDA0ODw"
TRACKER_ID = "EBESExQVFhcYGRobHB0eHw"
ROOM_URL = "https://archipelago.gg/room/" + ROOM_ID


def responses():
    return {
        "room_status": {"tracker": TRACKER_ID, "players": [["Host", "Test World"], ["Friend", "Test World"]],
                        "last_port": 38281, "timeout": 7200, "last_activity": "Sun, 08 Nov 2026 13:00:00 GMT"},
        "static_tracker": {
            "groups": [{"slot": 3, "name": "Item Link", "members": [1, 2]}],
            "player_locations_total": [{"team": 0, "player": p, "total_locations": 5} for p in (1, 2)],
            "player_game": [{"team": 0, "player": p, "game": "Test World"} for p in (1, 2)]},
        "tracker": {
            "aliases": [{"team": 0, "player": p, "alias": None} for p in (1, 2)],
            "player_checks_done": [{"team": 0, "player": p, "locations": [p * 1000 + 1]} for p in (1, 2)],
            "player_items_received": [
                {"team": 0, "player": 1, "items": [[501, 2001, 2, 1], [511, -2, 0, 0]]},
                {"team": 0, "player": 2, "items": [[502, 1001, 1, 2]]}],
            "player_status": [{"team": 0, "player": p, "status": 20} for p in (1, 2)],
            "activity_timers": [{"team": 0, "player": p, "time": None} for p in (1, 2)],
            "connection_timers": [], "hints": [{"future_location": "DO NOT EXPOSE"}]},
    }


class APIClientTests(unittest.TestCase):
    def test_strict_room_ids_and_ssrf_inputs(self):
        self.assertEqual(live_api.room_id(ROOM_URL + "/"), ROOM_ID)
        for url in ("http://archipelago.gg/room/" + ROOM_ID, "https://evil.test/room/" + ROOM_ID,
                    ROOM_URL + "?url=http://127.0.0.1", ROOM_URL + "#fragment",
                    "https://archipelago.gg:443/room/" + ROOM_ID,
                    "https://archipelago.gg@localhost/room/" + ROOM_ID,
                    "https://archipelago.gg.evil.test/room/" + ROOM_ID,
                    "https://archipelago.gg/tracker/" + ROOM_ID, ROOM_URL + "/../x",
                    "https://archipelago.gg/room/example", "https://archipelago.gg/room/" + "a" * 22):
            with self.subTest(url=url), self.assertRaises(ValueError):
                live_api.room_id(url)
        with self.assertRaises(ValueError):
            live_api.fetch("slot_data_tracker", ROOM_ID)
        with self.assertRaises(ValueError):
            live_api.fetch("tracker", "http://127.0.0.1")

    def test_bounded_json_client_and_no_spoiler_persistence(self):
        response = io.BytesIO(json.dumps(responses()["tracker"]).encode())
        response.headers = {"Content-Type": "application/json"}
        with patch("hub.live_api.build_opener") as opener:
            opener.return_value.open.return_value = response
            data = live_api.fetch("tracker", TRACKER_ID)
            self.assertNotIn("hints", data)
            req = opener.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, "https://archipelago.gg/api/tracker/" + TRACKER_ID)
            self.assertIsNone(req.get_header("Cookie"))
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 8)
        for status, expected in ((404, "not_found"), (403, "protected"), (429, "rate_limited"), (503, "unavailable")):
            with patch("hub.live_api.build_opener") as opener:
                opener.return_value.open.side_effect = HTTPError(ROOM_URL, status, "internal", {}, None)
                with self.assertRaises(live_api.APIError) as error:
                    live_api.fetch("tracker", TRACKER_ID)
                self.assertEqual(error.exception.kind, expected)
        response = io.BytesIO(b"[" + b" " * 64 + b"]"); response.headers = {"Content-Type": "application/json"}
        with patch("hub.live_api.build_opener") as opener, patch.object(live_api, "MAX_BYTES", 32):
            opener.return_value.open.return_value = response
            with self.assertRaises(live_api.APIError):
                live_api.fetch("tracker", TRACKER_ID)
        self.assertIsNone(live_api.NoRedirect().redirect_request(None, None, 302, "", {}, "http://localhost/"))


class MetricsTests(unittest.TestCase):
    def test_received_interactions_use_confirmed_checks_not_seed_distribution(self):
        data = responses()
        result = live_metrics.aggregate(data["room_status"], data["static_tracker"], data["tracker"])
        self.assertEqual((result["checks"], result["total"], result["progress"]), (2, 10, 20))
        self.assertEqual(result["received"], 3)
        self.assertEqual(result["foreign"], 2)
        self.assertEqual(result["players"][0]["unattributed"], 1)
        self.assertEqual(result["players"][0]["name"], "Host")
        # Group deliveries, unconfirmed locations, and repeated records never
        # become additional finder-to-recipient edges.
        data["tracker"]["player_items_received"][0]["items"] += [[501, 2001, 2, 1], [501, 12345, 2, 1], [501, 2001, 3, 1]]
        result = live_metrics.aggregate(data["room_status"], data["static_tracker"], data["tracker"])
        self.assertEqual(result["foreign"], 2)
        self.assertEqual(result["received"], 6)
        self.assertEqual(result["player_count"], 2)

    def test_unknown_fields_are_not_zero_and_teams_do_not_cross(self):
        data = responses()
        del data["tracker"]["player_items_received"]
        data["static_tracker"]["player_locations_total"].pop()
        result = live_metrics.aggregate(data["room_status"], data["static_tracker"], data["tracker"])
        self.assertIsNone(result["received"])
        self.assertIsNone(result["interactions"])
        self.assertIsNone(result["total"])
        self.assertIsNone(result["progress"])
        data = responses()
        for field in ("player_game", "player_locations_total"):
            data["static_tracker"][field] += [{**row, "team": 1} for row in data["static_tracker"][field]]
        for field in ("aliases", "player_checks_done", "player_items_received", "player_status"):
            data["tracker"][field] += [{**row, "team": 1} for row in data["tracker"][field]]
        result = live_metrics.aggregate(data["room_status"], data["static_tracker"], data["tracker"])
        self.assertEqual(result["player_count"], 4)
        self.assertEqual(result["foreign"], 4)
        self.assertTrue(all(e["finder"].split(":")[0] == e["recipient"].split(":")[0] for e in result["interactions"]))


class LiveIntegrationTests(unittest.TestCase):
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    post = fixtures.MVPTests.post

    def seed(self, race=False):
        self.post("/login", {"username": "Host"})
        self.friend = self.app.test_client()
        self.post("/login", {"username": "Friend"}, client=self.friend)
        with self.app.app_context():
            sid = db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Live test',1,1)")
            for uid in (1, 2):
                db.execute("INSERT INTO lobby_members(session_id,user_id) VALUES (?,?)", (sid, uid))
            snapshot = dict(race=race, slots=[dict(player_id=p, slot=name, game="test_world",
                                                  game_name="Test World", game_version="1.0")
                                             for p, name in ((1, "Host"), (2, "Friend"))])
            bid = db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,'succeeded',?,?)",
                             (sid, db.dumps(snapshot), "2026-11-08T13:00:00+00:00"))
        self.payloads = responses(); self.calls = []
        def fetch(endpoint, identifier):
            self.calls.append((endpoint, identifier))
            return live_api.sanitize(endpoint, deepcopy(self.payloads[endpoint]))
        self.fetch_patch = patch.object(live_api, "fetch", side_effect=fetch)
        self.fetch_patch.start(); self.addCleanup(self.fetch_patch.stop)
        self.now = time.time()
        self.live_id = live_store.attach(bid, ROOM_URL, 1, auto_host=True)
        self.sid, self.bid = sid, bid
        self.url = f"/sessions/{sid}/builds/{bid}/live"
        return sid, bid

    def data(self, client=None):
        response = (client or self.client).get(self.url + "/data")
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_collection_shared_cache_and_persistent_history(self):
        self.seed()
        self.assertTrue(live_store.refresh(self.live_id, self.now))
        self.assertEqual(len(self.calls), 3)
        first = self.data()
        self.assertEqual(first["metrics"]["checks"], 2)
        self.assertEqual(len(first["history"]), 1)
        self.assertEqual([e["kind"] for e in first["events"]], ["start"])
        for client in (self.client, self.friend, self.client, self.friend):
            self.data(client)
            self.post(self.url + "/refresh", {}, client=client)
        self.assertFalse(live_store.refresh(self.live_id, self.now + 30))
        self.assertEqual(len(self.calls), 3)
        self.payloads["tracker"]["player_checks_done"][0]["locations"].append(1002)
        self.payloads["tracker"]["player_status"][1]["status"] = 30
        self.payloads["tracker"]["player_items_received"][1]["items"].append([503, 1002, 1, 0])
        self.assertTrue(live_store.refresh(self.live_id, self.now + 61))
        second = self.data()
        self.assertEqual((second["metrics"]["checks"], second["metrics"]["goals"]), (3, 1))
        self.assertEqual(len(second["history"]), 2)
        self.assertEqual(second["recent_gains"], {"0:1": 1, "0:2": 0})
        self.assertEqual(len(self.calls), 5)  # static data remains cached for 300s
        self.assertNotIn("DO NOT EXPOSE", json.dumps(second))
        event_count = len(second["events"])
        self.assertTrue(live_store.refresh(self.live_id, self.now + 122))
        self.assertEqual(len(self.data()["events"]), event_count)
        # Reopening storage / running migrations must not invent or discard history.
        live_store.migrate()
        self.assertEqual(len(self.data()["history"]), 3)
        with self.app.app_context():
            address = db.query("SELECT * FROM hosted_rooms WHERE build_id=?", (self.bid,), one=True)
            self.assertEqual(address["port"], 38281)
            cache = db.query("SELECT payload FROM live_api_cache WHERE endpoint='tracker'", one=True)["payload"]
            self.assertNotIn("hints", cache)

    def test_missing_tracker_gone_and_transient_failure_keep_last_good_state(self):
        self.seed()
        self.payloads["room_status"]["tracker"] = None
        self.assertFalse(live_store.refresh(self.live_id, self.now))
        self.assertEqual(self.data()["state"], "no_tracker")
        self.assertIsNone(self.data()["metrics"])
        self.payloads = responses()
        self.assertTrue(live_store.refresh(self.live_id, self.now + 61))
        count = len(self.data()["history"])
        with patch.object(live_api, "fetch", side_effect=live_api.APIError("API kurz nicht erreichbar.")):
            self.assertFalse(live_store.refresh(self.live_id, self.now + 122))
        stale = self.data()
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["metrics"]["checks"], 2)
        self.assertEqual(len(stale["history"]), count)
        with patch.object(live_api, "fetch", side_effect=live_api.APIError("Nicht gefunden.", "not_found", 300)):
            self.assertFalse(live_store.refresh(self.live_id, self.now + 183))
        self.assertEqual(self.data()["state"], "not_found")
        self.assertEqual(self.data()["metrics"]["checks"], 2)

    def test_unstarted_room_real_zero_and_unknown_item_values(self):
        self.seed()
        self.payloads["room_status"]["last_port"] = 0
        for record in self.payloads["tracker"]["player_checks_done"]: record["locations"] = []
        self.payloads["tracker"].pop("player_items_received")
        self.assertTrue(live_store.refresh(self.live_id, self.now))
        data = self.data()
        self.assertEqual(data["metrics"]["checks"], 0)
        self.assertIsNone(data["metrics"]["received"])
        self.assertIsNone(data["room"]["port"])

    def test_permissions_csrf_and_race_no_spoiler_backdoor(self):
        self.seed(race=True)
        live_store.refresh(self.live_id, self.now)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        data = self.data()
        self.assertIsNone(data["metrics"]["interactions"])
        self.assertIsNone(data["metrics"]["received"])
        self.assertTrue(all(p["received"] is None for point in data["history"] for p in point["players"]))
        self.assertEqual(data["metrics"]["checks"], 2)
        stranger = self.app.test_client()
        self.post("/login", {"username": "Visitor"}, client=stranger)
        with self.app.app_context():
            db.execute("UPDATE sessions SET locked=0 WHERE id=?", (self.sid,))
        for path in (self.url, self.url + "/data"):
            self.assertEqual(stranger.get(path).status_code, 403)
        self.assertEqual(self.client.post(self.url + "/refresh").status_code, 403)
        self.assertEqual(self.post(self.url + "/connect", {"room_url": ROOM_URL}, client=self.friend).status_code, 403)
        self.assertEqual(self.post(self.url + "/refresh", {}, client=stranger).status_code, 403)

    def test_reset_starts_new_segment_and_new_link_does_not_mix_rooms(self):
        self.seed()
        live_store.refresh(self.live_id, self.now)
        self.payloads["tracker"]["player_checks_done"][0]["locations"] = []
        live_store.refresh(self.live_id, self.now + 61)
        data = self.data()
        self.assertEqual([point["segment"] for point in data["history"]], [1, 2])
        self.assertIn("reset", [e["kind"] for e in data["events"]])
        self.assertEqual(data["gains"]["0:1"], 0)
        other = live_store.attach(self.bid, "https://archipelago.gg/room/" + TRACKER_ID, 1)
        self.assertNotEqual(other, self.live_id)
        self.assertEqual(self.data()["history"], [])
        with self.app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS n FROM live_snapshots", one=True)["n"], 2)

    def test_two_simultaneous_collectors_only_one_calls_upstream(self):
        self.seed()
        entered, release = threading.Event(), threading.Event()
        original = live_api.fetch.side_effect
        def slow_fetch(endpoint, identifier):
            if endpoint == "room_status":
                entered.set()
                self.assertTrue(release.wait(3))
            return original(endpoint, identifier)
        results = []
        with patch.object(live_api, "fetch", side_effect=slow_fetch):
            worker = threading.Thread(target=lambda: results.append(live_store.refresh(self.live_id, self.now)))
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertFalse(live_store.refresh(self.live_id, self.now))
            finally:
                release.set(); worker.join(5)
        self.assertEqual(results, [True])
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(self.data()["history"]), 1)

    def test_room_connect_validation_and_completed_round_preserved(self):
        self.seed()
        for invalid in ("https://localhost/room/" + ROOM_ID, ROOM_URL + "?token=secret"):
            result = self.post(self.url + "/connect", {"room_url": invalid})
            self.assertEqual(result.status_code, 302)
            self.assertEqual(self.data()["room_id"], ROOM_ID)
        self.assertEqual(self.post(self.url + "/connect", {"room_url": ROOM_URL}).status_code, 302)
        live_store.refresh(self.live_id, self.now)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET completed_at='done' WHERE id=?", (self.bid,))
        self.assertFalse(live_store.refresh(self.live_id, self.now + 61))
        self.assertEqual(self.post(self.url + "/connect", {"room_url": ROOM_URL}).status_code, 409)
        self.assertTrue(self.data()["completed"])
        self.assertEqual(len(self.data()["history"]), 1)

    def test_manual_address_saved_during_poll_is_not_overwritten(self):
        self.seed()
        original = live_api.fetch.side_effect
        def fetch(endpoint, identifier):
            response = original(endpoint, identifier)
            if endpoint == "room_status":
                with self.app.app_context():
                    db.execute("""INSERT INTO hosted_rooms(build_id,host,port,entered_by,created_at)
                        VALUES (?,'manual.example',12345,1,'2026-11-08T13:00:00+00:00')""", (self.bid,))
                live_store.attach(self.bid, ROOM_URL, 1, auto_host=False)
            return response
        with patch.object(live_api, "fetch", side_effect=fetch):
            live_store.refresh(self.live_id, self.now)
        with self.app.app_context():
            address = db.query("SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1", (self.bid,), one=True)
            self.assertEqual((address["host"], address["port"]), ("manual.example", 12345))

    def test_history_sampling_and_seed_delete_cascade(self):
        self.seed()
        live_store.refresh(self.live_id, self.now)
        with self.app.app_context():
            point = db.query("SELECT payload FROM live_snapshots WHERE live_id=?", (self.live_id,), one=True)["payload"]
            with db.transaction() as conn:
                conn.executemany("""INSERT INTO live_snapshots(live_id,observed_at,source_at,segment,payload)
                    VALUES (?,?,?,1,?)""",
                    [(self.live_id, self.now - i * 60, self.now - i * 60, point) for i in range(1, 1000)])
        data = self.client.get(self.url + "/data?window=all").json
        self.assertTrue(data["history_sampled"])
        self.assertLessEqual(len(data["history"]), 421)
        self.assertEqual(len({p["id"] for p in data["history"]}), len(data["history"]))
        self.assertEqual(self.post(f"/admin/seeds/{self.bid}/delete", {}).status_code, 302)
        with self.app.app_context():
            for table in ("live_rooms", "live_snapshots", "live_events"):
                self.assertEqual(db.query("SELECT COUNT(*) AS n FROM " + table, one=True)["n"], 0)


if __name__ == "__main__":
    unittest.main()
