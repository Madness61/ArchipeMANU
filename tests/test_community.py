"""Community library, open lobby and generated statistics integration tests."""
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from hub import ap_bridge, config, db, stats
from hub.app import create_app

SCHEMA = {
    "game":"Test World", "slug":"test_world", "version":"1.0",
    "presets":{}, "items":[], "locations":[], "options":[],
}
INDEX = {"games":{"test_world":{"game":"Test World","version":"1.0","custom":False}},
         "ap_version":"0.6.8", "failed":{}}


def world_bytes():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("test_world/__init__.py", "pass")
        archive.writestr("test_world/archipelago.json",
                         '{"game":"Test World","world_version":"1.0"}')
    return out.getvalue()


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(config,"DATA",root),
            patch.object(config,"APWORLDS",root/"apworlds"),
            patch.object(config,"SCHEMAS",root/"schemas"),
            patch.object(config,"SESSIONS",root/"sessions"),
            patch.object(config,"DB_PATH",root/"hub.db"),
            patch.object(ap_bridge,"index",return_value=INDEX),
            patch.object(ap_bridge,"schema",side_effect=lambda slug: SCHEMA if slug=="test_world" else None),
            patch.object(ap_bridge,"ap_ready",return_value=False),
        ]
        for p in self.patches:
            p.start()
        self.app=create_app()
        self.app.config.update(TESTING=True)
        self.host=self.app.test_client()
        self.friend=self.app.test_client()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def post(self,client,url,body=None,**kwargs):
        client.get("/login")
        with client.session_transaction() as sess:
            token = sess["_csrf"]
        return client.post(url,data={"_csrf":token,**(body or {})},**kwargs)

    def login(self,client,name):
        response=self.post(client,"/login",{"username":name})
        self.assertEqual(response.status_code,302)

    def test_open_lobby_join_then_game_selection_without_player_limit(self):
        self.login(self.host,"Host")
        response=self.post(self.host,"/sessions",{"name":"Offene Runde"})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            lobby=db.query("SELECT * FROM sessions ORDER BY id DESC LIMIT 1",one=True)
            sid=lobby["id"]
        self.assertIn(f"/sessions/{sid}/choose",response.location)
        self.login(self.friend,"Friend")
        self.assertEqual(self.friend.get("/lobbies").status_code,200)
        self.assertEqual(self.friend.get(f"/sessions/{sid}").status_code,200)
        self.assertEqual(self.friend.get(f"/sessions/{sid}/choose").status_code,302)
        self.assertEqual(self.post(self.friend,f"/sessions/{sid}/join").status_code,302)
        chosen=self.friend.get(f"/sessions/{sid}/choose")
        self.assertEqual(chosen.status_code,200)
        self.assertIn(b"Test World",chosen.data)
        self.assertEqual(self.post(self.friend,f"/sessions/{sid}/entries",{"game":"test_world"}).status_code,302)
        self.assertEqual(self.post(self.friend,f"/sessions/{sid}/entries",{"game":"test_world"}).status_code,302)
        with self.app.app_context():
            friend=db.query("SELECT id FROM users WHERE username='Friend'",one=True)
            count=db.query("SELECT count(*) AS n FROM entries WHERE session_id=? AND user_id=?",
                           (sid,friend["id"]),one=True)["n"]
            self.assertEqual(count,1)

    def test_every_user_can_upload_archived_world_but_only_host_can_approve(self):
        self.login(self.host,"Host")
        self.login(self.friend,"Friend")
        payload=world_bytes()
        result=self.post(self.friend,"/games/community/add",{
            "name":"Test World","source_url":"https://example.com/releases",
            "apworld":(io.BytesIO(payload),"test_world.apworld"),
            "yaml":(io.BytesIO(b"name: Friend\ngame: Test World\nTest World: {}\n"),"settings.yaml"),
        },content_type="multipart/form-data")
        self.assertEqual(result.status_code,302)
        with self.app.app_context():
            row=db.query("SELECT * FROM community_games LIMIT 1",one=True)
            self.assertEqual(row["approved"],0)
            self.assertFalse((config.APWORLDS/"test_world.apworld").exists())
            sha=row["sha256"]
        listed=self.host.get("/games")
        self.assertEqual(listed.status_code,200)
        self.assertIn(b"Test World",listed.data)
        self.assertEqual(self.friend.get(f"/games/community/{sha}/apworld").data,payload)
        self.assertIn(b"name: Friend",self.friend.get(f"/games/community/{sha}/yaml").data)
        self.assertEqual(self.post(self.friend,f"/games/community/{sha}/approve",
                                  {"trust_apworlds":"yes"}).status_code,403)
        self.post(self.host,f"/games/community/{sha}/approve",{"trust_apworlds":"yes"})
        with self.app.app_context():
            self.assertFalse((config.APWORLDS/"test_world.apworld").exists())
        with patch.dict(os.environ,{"HUB_TRUSTED_APWORLDS":"1"}), patch.object(ap_bridge,"start_extract"):
            response=self.post(self.host,f"/games/community/{sha}/approve",{"trust_apworlds":"yes"})
            self.assertEqual(response.status_code,302)
        with self.app.app_context():
            self.assertEqual((config.APWORLDS/"test_world.apworld").read_bytes(),payload)
            self.assertEqual(db.query("SELECT approved FROM community_games LIMIT 1",one=True)["approved"],1)

    def test_joined_player_without_game_blocks_seed_preflight(self):
        from hub import mvp
        self.login(self.host,"Host")
        response=self.post(self.host,"/sessions",{"name":"No fixed player count"})
        with self.app.app_context():
            sid=db.query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1",one=True)["id"]
        self.login(self.friend,"Friend")
        self.post(self.friend,f"/sessions/{sid}/join")
        with self.app.app_context():
            selected, files, problems = mvp.preflight(sid)
            self.assertTrue(any("Friend" in problem and "kein Spiel" in problem for problem in problems))
            self.assertTrue(any("Host" in problem and "kein Spiel" in problem for problem in problems))
            self.assertFalse(files)

    def test_player_can_leave_and_host_can_remove(self):
        self.login(self.host,"Host")
        self.post(self.host,"/sessions",{"name":"Flexible"})
        with self.app.app_context():
            sid=db.query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1",one=True)["id"]
        self.login(self.friend,"Friend")
        self.post(self.friend,f"/sessions/{sid}/join")
        self.post(self.friend,f"/sessions/{sid}/entries",{"game":"test_world"})
        left=self.post(self.friend,f"/sessions/{sid}/leave")
        self.assertEqual(left.status_code,302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT count(*) AS n FROM lobby_members WHERE session_id=?",(sid,),one=True)["n"],1)
            self.assertEqual(db.query("SELECT count(*) AS n FROM entries WHERE session_id=?",(sid,),one=True)["n"],0)
        self.post(self.friend,f"/sessions/{sid}/join")
        with self.app.app_context():
            uid=db.query("SELECT id FROM users WHERE username='Friend'",one=True)["id"]
        removed=self.post(self.host,f"/sessions/{sid}/members/{uid}/remove")
        self.assertEqual(removed.status_code,302)
        with self.app.app_context():
            self.assertFalse(db.query("SELECT 1 FROM lobby_members WHERE session_id=? AND user_id=?",
                                      (sid,uid),one=True))

    def test_generated_lobby_stays_closed(self):
        self.login(self.host,"Host")
        self.post(self.host,"/sessions",{"name":"Finished"})
        with self.app.app_context():
            sid=db.query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1",one=True)["id"]
            db.execute("UPDATE sessions SET locked=1 WHERE id=?", (sid,))
            db.execute("""INSERT INTO seed_builds(session_id,status,snapshot,created_at)
                       VALUES (?,?,?,?)""",(sid,"succeeded",json.dumps({"slots":[]}),"2026-11-06"))
        unlock=self.post(self.host,f"/sessions/{sid}/lock")
        self.assertEqual(unlock.status_code,302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT locked FROM sessions WHERE id=?", (sid,),one=True)["locked"],1)
        self.login(self.friend,"Friend")
        self.assertEqual(self.post(self.friend,f"/sessions/{sid}/join").status_code,409)

    def test_real_placement_aggregate_and_race_redaction(self):
        result=stats.aggregate_placements(
            [{"id":1,"name":"Host","game":"Game A"},{"id":2,"name":"Friend","game":"Game B"}],
            [(1,1,"progression"),(1,2,"useful"),(2,1,"trap"),(2,2,"filler")])
        self.assertEqual(result["total_placements"],4)
        self.assertEqual(result["crossworld_placements"],2)
        self.assertEqual(result["crossworld_percent"],50.0)
        self.assertEqual(result["matrix"]["1"]["2"],1)
        self.assertEqual(result["categories"]["1"]["trap"],1)
        self.login(self.host,"Host")
        with self.app.app_context():
            sid=db.execute("INSERT INTO sessions(name,created_by) VALUES (?,?)",("Analytics",1))
            db.execute("""INSERT INTO seed_builds(session_id,status,snapshot,created_at,stats_json)
                       VALUES (?,?,?,?,?)""",
                       (sid,"succeeded",json.dumps({"slots":[],"race":False}),"2026-11-06",json.dumps(result)))
            row=db.query("SELECT id FROM seed_builds WHERE session_id=?", (sid,),one=True)
            bid=row["id"]
        response=self.host.get(f"/sessions/{sid}/builds/{bid}/stats")
        self.assertEqual(response.status_code,200)
        self.assertIn(b"Crossworld",response.data)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET snapshot=? WHERE id=?",
                       (json.dumps({"slots":[],"race":True}),bid))
        race=self.host.get(f"/sessions/{sid}/builds/{bid}/stats")
        self.assertEqual(race.status_code,200)
        self.assertIn("Race-Modus".encode(),race.data)
        self.assertNotIn(b"50.0",race.data)


if __name__=="__main__":
    unittest.main()
