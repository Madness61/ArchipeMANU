"""The highlighted action follows actual membership, readiness and build state."""
import unittest
import test_mvp as fixtures
from hub import db, live_store


class DashboardUITests(unittest.TestCase):
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    post = fixtures.MVPTests.post

    def action(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        return page.get_data(as_text=True).split('id="featured-action"', 1)[1].split("</a>", 1)[0]

    def test_action_tracks_selection_readiness_seed_and_room(self):
        self.post("/login", {"username": "Host"})
        self.post("/sessions", {"name": "Current evening"})
        self.assertIn("Spiel auswählen", self.action())
        self.post("/sessions/1/selection/start", {"game": "test_world", "ref": "default", "_action": "base"})
        self.assertIn("Bereit melden", self.action())
        with self.app.app_context():
            eid = db.query("SELECT id FROM entries WHERE session_id=1", one=True)["id"]
        self.post(f"/entries/{eid}/ready", {"ready": "1"})
        self.assertIn("Seed generieren", self.action())
        with self.app.app_context():
            bid = db.execute("""INSERT INTO seed_builds(session_id,status,snapshot,created_at)
                VALUES (1,'succeeded','{"slots":[]}',CURRENT_TIMESTAMP)""")
            db.execute("UPDATE sessions SET locked=1 WHERE id=1")
        self.assertIn("Jetzt spielen", self.action())
        self.post(f"/sessions/1/builds/{bid}/hosting", {"host": "archipelago.gg", "port": "38281"})
        live_store.attach(bid, "https://archipelago.gg/room/AAECAwQFBgcICQoLDA0ODw", 1)
        self.assertIn("Fortschritt ansehen", self.action())
        # Older active rounds must outrank newer archived rooms.
        with self.app.app_context():
            for i in range(8):
                db.execute("INSERT INTO sessions(name,created_by,locked,completed_at) VALUES (?,1,1,'done')",
                           (f"Archive {i}",))
        self.assertIn("/sessions/1#progress", self.action())

    def test_no_round_has_an_honest_empty_state(self):
        self.post("/login", {"username": "Host"})
        page = self.client.get("/").get_data(as_text=True)
        self.assertNotIn('id="featured-action"', page)
        self.assertIn("Deine erste Runde wartet", page)
        self.assertIn("Noch keine weiteren Runden", page)


if __name__ == "__main__":
    unittest.main()
