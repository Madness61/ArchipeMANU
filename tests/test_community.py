"""Community library, open lobby and generated statistics integration tests."""
import io
import json
import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from hub import ap_bridge, community, config, db, stats
from hub.app import create_app
from auth_helpers import provision_user, TEST_PASSWORD

SCHEMA = {
    "game":"Test World", "slug":"test_world", "version":"1.0",
    "presets":{}, "items":[], "locations":[], "options":[],
}
INDEX = {"games":{"test_world":{"game":"Test World","version":"1.0","custom":False}},
         "ap_version":"0.6.8", "failed":{}}


def world_bytes(version="1.0"):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("test_world/__init__.py", "pass")
        archive.writestr("test_world/archipelago.json",
                         json.dumps({"game":"Test World", "world_version":version}))
    return out.getvalue()


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.dict(os.environ, {"HUB_TRUSTED_APWORLDS": "0"}),
            patch.object(config,"DATA",root),
            patch.object(config,"APWORLDS",root/"apworlds"),
            patch.object(config,"SCHEMAS",root/"schemas"),
            patch.object(config,"SESSIONS",root/"sessions"),
            patch.object(config,"DB_PATH",root/"hub.db"),
            patch.object(ap_bridge,"index",return_value=INDEX),
            patch.object(ap_bridge,"schema",side_effect=lambda slug: SCHEMA if slug=="test_world" else None),
            patch.object(ap_bridge,"ap_ready",return_value=False),
            patch.object(ap_bridge,"start_extract"),
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
        provision_user(self.app, name, is_admin=name == "Host")
        response=self.post(client,"/login",{"username":name,"password":TEST_PASSWORD})
        self.assertEqual(response.status_code,302)

    def test_open_lobby_join_then_game_selection_without_player_limit(self):
        self.login(self.host,"Host")
        response=self.post(self.host,"/sessions",{"name":"Offene Runde"})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            lobby=db.query("SELECT * FROM sessions ORDER BY id DESC LIMIT 1",one=True)
            sid=lobby["id"]
        self.assertEqual(f"/sessions/{sid}",response.location)
        self.login(self.friend,"Friend")
        self.assertEqual(self.friend.get("/lobbies").status_code,200)
        self.assertEqual(self.friend.get(f"/sessions/{sid}").status_code,200)
        self.assertEqual(self.friend.get(f"/sessions/{sid}/choose").status_code,302)
        joined=self.post(self.friend,f"/sessions/{sid}/join")
        self.assertEqual(joined.status_code,302)
        self.assertEqual(joined.location,f"/sessions/{sid}")
        self.assertEqual(self.friend.get(f"/sessions/{sid}/choose").location,f"/sessions/{sid}#game-selection")
        chosen=self.friend.get(f"/sessions/{sid}")
        self.assertIn(b"Deine Spielauswahl",chosen.data)
        with self.app.app_context():
            self.assertFalse(db.query("SELECT * FROM entries WHERE session_id=?",(sid,)))
        self.assertEqual(self.post(self.friend,f"/sessions/{sid}/entries",{"game":"test_world"}).status_code,302)
        self.assertEqual(self.post(self.friend,f"/sessions/{sid}/entries",{"game":"test_world"}).status_code,302)
        with self.app.app_context():
            friend=db.query("SELECT id FROM users WHERE username='Friend'",one=True)
            count=db.query("SELECT count(*) AS n FROM entries WHERE session_id=? AND user_id=?",
                           (sid,friend["id"]),one=True)["n"]
            self.assertEqual(count,1)

    def test_world_progress_is_authenticated_and_does_not_leak_admin_logs(self):
        self.assertEqual(self.friend.get("/api/worlds/status").status_code,302)
        self.login(self.host,"Host")
        self.login(self.friend,"Friend")
        with patch.object(ap_bridge,"extract_status",return_value={"status":"queued","log":"private worker details"}):
            response = self.friend.get("/api/worlds/status")
            self.assertEqual(response.get_json(),{"status":"queued"})
        self.assertEqual(self.friend.get("/admin/status").status_code,403)

    def test_ui_dashboard_uses_joined_members_and_own_round_access(self):
        self.login(self.host,"Host")
        self.login(self.friend,"Friend")
        self.post(self.host,"/sessions",{"name":"Our open round"})
        self.post(self.friend,"/sessions/1/join")
        with self.app.app_context():
            sid = db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Private closed round',2,1)")
            db.execute("INSERT INTO lobby_members(session_id,user_id) VALUES (?,2)",(sid,))
        host_page = self.host.get("/")
        self.assertEqual(host_page.status_code,200)
        self.assertIn(b"Our open round",host_page.data)
        self.assertIn(b"2 Teilnehmer",host_page.data)
        self.assertNotIn(b"Private closed round",host_page.data)
        self.assertEqual(re.findall(rb'class="metric">(\d+)</div>',host_page.data),[b"1",b"1",b"2"])
        self.assertIn(b"Private closed round",self.friend.get("/").data)

    def test_ui_library_combines_search_type_and_status_filters(self):
        self.login(self.host,"Host")
        rows = [dict(slug="one",name="Built-in One",version="1",installed=True,custom=False,added_by="",versions=[],active=False),
                dict(slug="two",name="Custom Ready",version="2",installed=True,custom=True,added_by="Host",versions=[],active=True),
                dict(slug="three",name="Custom Waiting",version="3",installed=False,custom=True,added_by="Friend",versions=[],active=False)]
        with patch.object(community,"all_games",side_effect=lambda search="":[r for r in rows if search.lower() in r["name"].lower()]):
            page = self.host.get("/games?q=Custom&kind=custom&state=ready")
            self.assertEqual(page.status_code,200)
            self.assertIn(b"Custom Ready",page.data)
            cards = re.findall(r'<article\b([^>]*)>(.*?)</article>', page.get_data(as_text=True), re.S)
            visible = [body for attrs, body in cards if ' hidden' not in attrs]
            self.assertEqual(len(visible), 1)
            self.assertIn("Custom Ready", visible[0])
            self.assertIn(b"1 von 3 Spielen",page.data)
            self.assertIn(b"Keine passenden Spiele",self.host.get("/games?q=Custom&kind=builtin").data)
            self.assertEqual(self.host.get("/games?state=invalid").status_code,400)

    def test_library_genres_setup_filters_and_inactive_setup_page(self):
        self.login(self.host, "Host")
        rows = [dict(slug="smw", name="Super Mario World", version="1", installed=True,
                     custom=False, added_by="", versions=[], active=True),
                dict(slug="aquaria", name="Aquaria", version="1", installed=True,
                     custom=False, added_by="", versions=[], active=True),
                dict(slug="unknown", name="Future Game", version="1", installed=False,
                     custom=True, added_by="Friend", active=False,
                     versions=[dict(sha256="a" * 64, version="1", username="Friend", active=False,
                                    yaml_file="", source_url="https://example.org/future-setup")])]
        with patch.object(community, "all_games", return_value=rows):
            page = self.host.get("/games?genre=Metroidvania&setup=mod&state=loaded")
            self.assertEqual(page.status_code, 200)
            cards = re.findall(r'<article\b([^>]*)>(.*?)</article>', page.get_data(as_text=True), re.S)
            visible = [body for attrs, body in cards if ' hidden' not in attrs]
            self.assertEqual(len(visible), 1)
            self.assertIn("Aquaria", visible[0])
            self.assertIn(b"1 von 3 Spielen", page.data)
            self.assertNotIn(b">Spielbereit<", page.data)
            self.assertEqual(self.host.get("/games?genre=imaginary").status_code, 400)
            self.assertEqual(self.host.get("/games?setup=imaginary").status_code, 400)
            setup = self.host.get("/games/smw/setup")
            self.assertIn(b"Super Mario World (USA).sfc", setup.data)
            self.assertIn(b"Generator-Rechner", setup.data)
            unknown = self.host.get("/games/unknown/setup")
            self.assertEqual(unknown.status_code, 200)
            self.assertIn(b"https://example.org/future-setup", unknown.data)
            self.assertIn(b"Einrichtung noch", unknown.data)
            self.assertEqual(self.host.get("/games/nonexistent/setup").status_code, 404)

    def test_ui_host_waits_for_player_without_game_and_members_have_no_host_controls(self):
        self.login(self.host,"Host")
        self.login(self.friend,"Friend")
        self.post(self.host,"/sessions",{"name":"UI readiness"})
        self.post(self.friend,"/sessions/1/join")
        self.post(self.host,"/sessions/1/entries",{"game":"test_world"})
        with self.app.app_context():
            eid = db.query("SELECT id FROM entries",one=True)["id"]
        self.post(self.host,f"/entries/{eid}/ready",{"ready":"1"})
        host_page = self.host.get("/sessions/1")
        self.assertIn(b"1 von 2 bereit",host_page.data)
        self.assertIn(b"Friend: Spiel fehlt",host_page.data)
        self.assertRegex(host_page.get_data(as_text=True),r'<button class="primary" disabled>Runde generieren</button>')
        member_page = self.friend.get("/sessions/1")
        self.assertNotIn(b'id="host-controls"',member_page.data)
        self.assertNotIn(b"Lobby verwalten",member_page.data)
        self.assertEqual(self.post(self.friend,"/sessions/1/generate").status_code,403)

    def test_ui_game_page_displays_saved_guide_and_presets(self):
        self.login(self.host,"Host")
        with self.app.app_context():
            db.execute("INSERT INTO game_guides(slug,steps,updated_at,author) VALUES ('test_world',?,'today',1)",
                       ("Install the test client and connect.",))
        page = self.host.get("/games/test_world")
        self.assertEqual(page.status_code,200)
        self.assertIn(b"Install the test client and connect.",page.data)
        self.assertIn(b"Vorlagen f",page.data)
        self.assertIn(b"Standard",page.data)

    def test_member_upload_activates_and_loads_without_admin_approval(self):
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
            self.assertEqual(row["approved"],1)
            self.assertEqual((config.APWORLDS/"test_world.apworld").read_bytes(),payload)
            sha=row["sha256"]
        ap_bridge.start_extract.assert_called_once_with()
        listed=self.host.get("/games")
        self.assertEqual(listed.status_code,200)
        self.assertIn(b"Test World",listed.data)
        with self.friend.get(f"/games/community/{sha}/apworld") as response:
            self.assertEqual(response.data,payload)
        with self.friend.get(f"/games/community/{sha}/yaml") as response:
            self.assertIn(b"name: Friend",response.data)
        with patch.dict(os.environ,{"HUB_TRUSTED_APWORLDS":"1"}), patch.object(ap_bridge,"start_extract"):
            response=self.post(self.friend,f"/games/community/{sha}/approve")
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

    def test_duplicate_upload_preserves_original_yaml_and_owner(self):
        self.login(self.host, "Host")
        self.login(self.friend, "Friend")
        original = b"\xef\xbb\xbfname: Host\r\ngame: Test World\r\n"
        def upload(client, content):
            return self.post(client, "/games/community/add", {
                "apworld": (io.BytesIO(payload), "test_world.apworld"),
                "yaml": (io.BytesIO(content), "options.yaml"),
            }, content_type="multipart/form-data")
        payload = world_bytes()
        self.assertEqual(upload(self.host, original).status_code, 302)
        self.assertEqual(upload(self.friend, b"name: Friend\ngame: Test World\n").status_code, 400)
        with self.app.app_context():
            row = db.query("SELECT * FROM community_games", one=True)
            self.assertEqual(row["created_by"], 1)
            self.assertEqual((config.DATA / "community" / row["sha256"] / "options.yaml").read_bytes(), original)
        self.assertEqual(ap_bridge.start_extract.call_count, 1)

    def test_invalid_and_anonymous_uploads_do_not_activate_or_load(self):
        response = self.post(self.friend, "/games/community/add", {
            "apworld": (io.BytesIO(world_bytes()), "test_world.apworld"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)
        self.login(self.friend, "Friend")
        response = self.post(self.friend, "/games/community/add", {
            "apworld": (io.BytesIO(world_bytes()), "test_world.apworld"),
            "yaml": (io.BytesIO(b"name: Friend\ngame: Wrong Game\n"), "options.yaml"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        ap_bridge.start_extract.assert_not_called()
        self.assertFalse((config.APWORLDS / "test_world.apworld").exists())
        with self.app.app_context():
            self.assertFalse(db.query("SELECT * FROM community_games"))

    def test_member_version_update_preserves_archives_and_can_restore_old_version(self):
        self.login(self.host, "Host")
        self.login(self.friend, "Friend")
        payloads = [world_bytes("1.0"), world_bytes("2.0")]
        for payload in payloads:
            response = self.post(self.friend, "/games/community/add", {
                "apworld": (io.BytesIO(payload), "test_world.apworld"),
            }, content_type="multipart/form-data")
            self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            from hub import community
            versions = ap_bridge.list_apworld_versions()
            old = next(v for v in versions if v["version"] == "1.0")
            self.assertEqual(len(versions), 2)
            self.assertEqual((config.APWORLDS / "test_world.apworld").read_bytes(), payloads[1])
            for version in versions:
                self.assertTrue(ap_bridge.archived_apworld(version["sha256"]).is_file())
            item = next(i for i in community.all_games() if i["slug"] == "test_world")
            self.assertEqual([v["version"] for v in item["versions"] if v["active"]], ["2.0"])
        with patch.dict(os.environ, {"HUB_TRUSTED_APWORLDS":"1"}):
            response = self.post(self.friend, f"/games/community/{old['sha256']}/approve")
            self.assertEqual(response.status_code, 302)
        self.assertEqual((config.APWORLDS / "test_world.apworld").read_bytes(), payloads[0])
        self.assertEqual(ap_bridge.start_extract.call_count, 3)

    def test_admin_upload_and_activation_start_loading_without_confirmation(self):
        self.login(self.host, "Host")
        self.login(self.friend, "Friend")
        with patch.object(ap_bridge, "start_extract") as load:
            response = self.post(self.host, "/admin/apworlds", {
                "files": (io.BytesIO(world_bytes()), "test_world.apworld"),
            }, content_type="multipart/form-data")
            self.assertEqual(response.status_code, 302)
            load.assert_called_once_with()
        with self.app.app_context():
            sha = ap_bridge.list_apworld_versions()[0]["sha256"]
        with patch.object(ap_bridge, "start_extract") as load:
            response = self.post(self.host, f"/admin/apworlds/versions/{sha}/activate")
            self.assertEqual(response.status_code, 302)
            load.assert_called_once_with()
            response = self.post(self.friend, f"/admin/apworlds/versions/{sha}/activate")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(load.call_count, 1)

    def test_community_activation_starts_loading_without_confirmation(self):
        self.login(self.host, "Host")
        self.post(self.host, "/games/community/add", {
            "apworld": (io.BytesIO(world_bytes()), "test_world.apworld"),
        }, content_type="multipart/form-data")
        with self.app.app_context():
            sha = db.query("SELECT sha256 FROM community_games", one=True)["sha256"]
        with patch.dict(os.environ, {"HUB_TRUSTED_APWORLDS": "1"}), \
                patch.object(ap_bridge, "start_extract") as load:
            response = self.post(self.host, f"/games/community/{sha}/approve")
            self.assertEqual(response.status_code, 302)
            load.assert_called_once_with()

    def test_clone_preserves_members_without_games_and_blocks_outsiders(self):
        self.login(self.host, "Host")
        self.post(self.host, "/sessions", {"name": "Original"})
        self.login(self.friend, "Friend")
        self.post(self.friend, "/sessions/1/join")
        self.post(self.friend, "/sessions/1/entries", {"game": "test_world"})
        self.post(self.host, "/sessions/1/clone")
        with self.app.app_context():
            self.assertEqual(len(db.query("SELECT * FROM lobby_members WHERE session_id=2")), 2)
            from hub import mvp
            _, _, failures = mvp.preflight(2)
            self.assertTrue(any("Host" in failure and "kein Spiel" in failure for failure in failures))
            db.execute("UPDATE sessions SET locked=1 WHERE id=1")
        outsider = self.app.test_client()
        self.login(outsider, "Outsider")
        self.assertEqual(self.post(outsider, "/sessions/1/clone").status_code, 403)

    def test_delete_preserves_seed_history_and_deletes_empty_invited_lobby(self):
        self.login(self.host, "Host")
        self.post(self.host, "/sessions", {"name": "History"})
        with self.app.app_context():
            db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (1,'failed','{}','today')")
        self.assertEqual(self.post(self.host, "/sessions/1/delete").status_code, 302)
        with self.app.app_context():
            self.assertIsNotNone(db.query("SELECT * FROM sessions WHERE id=1", one=True))
            self.assertEqual(len(db.query("SELECT * FROM seed_builds")), 1)
        self.post(self.host, "/sessions", {"name": "Empty"})
        self.post(self.host, "/sessions/2/invite")
        self.assertEqual(self.post(self.host, "/sessions/2/delete").status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.query("SELECT * FROM sessions WHERE id=2", one=True))

    def test_incomplete_statistics_fall_back_without_error(self):
        self.login(self.host, "Host")
        self.post(self.host, "/sessions", {"name": "Stats"})
        with self.app.app_context():
            bid = db.execute("""INSERT INTO seed_builds(session_id,status,snapshot,created_at,stats_json)
                VALUES (1,'succeeded','{}','today',?)""", ('{"source":"archipelago_generated_multiworld"}',))
        for payload in ([], None, {"source": "archipelago_generated_multiworld"}):
            with self.app.app_context():
                db.execute("UPDATE seed_builds SET stats_json=? WHERE id=?", (json.dumps(payload), bid))
            response = self.host.get(f"/sessions/1/builds/{bid}/stats")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Keine verifizierten Statistikdaten".encode(), response.data)

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

    def test_generated_lobby_can_be_reopened_by_host(self):
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
            self.assertEqual(db.query("SELECT locked FROM sessions WHERE id=?", (sid,),one=True)["locked"],0)
            self.assertEqual(db.query("SELECT count(*) AS n FROM seed_builds WHERE session_id=?", (sid,),one=True)["n"],1)
        self.login(self.friend,"Friend")
        self.assertEqual(self.post(self.friend,f"/sessions/{sid}/lock").status_code,403)
        self.post(self.host,f"/sessions/{sid}/lock")
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
        self.assertIn("Wie viele Items hat jedes Spiel?".encode(),response.data)
        self.assertIn(b"<b>2</b>", response.data)
        self.assertNotIn(b"built-in method", response.data)
        self.assertNotIn(b"Crossworld",response.data)
        self.assertNotIn(b'class="matrix"',response.data)
        revealed = self.host.get(f"/sessions/{sid}/builds/{bid}/stats?spoilers=1")
        self.assertIn(b"Crossworld", revealed.data)
        self.assertIn(b'class="matrix"', revealed.data)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET snapshot=? WHERE id=?",
                       (json.dumps({"slots":[],"race":True}),bid))
        race=self.host.get(f"/sessions/{sid}/builds/{bid}/stats?spoilers=1")
        self.assertEqual(race.status_code,200)
        self.assertIn("Race-Modus".encode(),race.data)
        self.assertNotIn(b"50.0",race.data)

    def analytics_fixture(self, rows):
        players = [{"id":1,"name":"Host","game":"Game A"},
                   {"id":2,"name":"Friend","game":"Game B"}]
        distribution = stats.aggregate_placements(players,
                            [(r["finder"],r["recipient"],r["category"]) for r in rows])
        with self.app.app_context():
            sid = db.execute("INSERT INTO sessions(name,created_by,locked) VALUES ('Drilldown',1,1)")
            bid = db.execute("""INSERT INTO seed_builds(session_id,status,snapshot,created_at,stats_json)
                VALUES (?,'succeeded','{"slots":[]}','today',?)""", (sid,json.dumps(distribution)))
        folder = config.SESSIONS / "_seeds" / str(bid) / "output"
        folder.mkdir(parents=True)
        path = folder / "item_placements.json"
        path.write_text(json.dumps({"source":distribution["source"],"placements":rows}), encoding="utf-8")
        return f"/sessions/{sid}/builds/{bid}/stats", bid, path

    def test_spoiler_drilldown_filters_and_checks_access_and_race(self):
        self.login(self.host,"Host")
        self.login(self.friend,"Friend")
        rows = [
            {"finder":1,"recipient":2,"item":"Spoiler Sword","location":"Secret Chest",
             "category":"progression","item_id":10,"location_id":20},
            {"finder":2,"recipient":1,"item":"Secret Key","location":"<script>Hidden</script>",
             "category":"useful","item_id":11,"location_id":21},
        ]
        base, bid, path = self.analytics_fixture(rows)
        overview = self.host.get(base)
        self.assertIn(b"Spoiler Sword",overview.data)
        self.assertNotIn(b"Secret Chest",overview.data)
        self.assertNotIn(b"in der Welt von",overview.data)
        self.assertNotIn(b'class="matrix"',overview.data)
        detail_url = base + "/items/1"
        detail = self.host.get(detail_url)
        self.assertEqual(detail.status_code,200)
        self.assertIn(b"Secret Key",detail.data)
        self.assertNotIn(b"Spoiler Sword",detail.data)
        self.assertIn(b"&lt;script&gt;Hidden&lt;/script&gt;",detail.data)
        finder = self.host.get(detail_url + "?direction=finder")
        self.assertIn(b"Spoiler Sword",finder.data)
        self.assertNotIn(b"Secret Key",finder.data)
        filtered = self.host.get(detail_url + "?q=not-present")
        self.assertIn(b"Keine passenden Items",filtered.data)
        self.assertEqual(self.friend.get(detail_url).status_code,403)
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get(detail_url).status_code,401)
        self.assertEqual(self.host.get(base + "/items/999").status_code,404)
        self.assertEqual(self.host.get(detail_url + "?direction=wrong").status_code,400)
        self.assertEqual(self.host.get(detail_url + "?page=wrong").status_code,400)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET snapshot=? WHERE id=?", ('{"race":true}',bid))
        self.assertEqual(self.host.get(detail_url).status_code,403)
        self.assertNotIn(b"Secret Key",self.host.get(base + "?spoilers=1").data)

    def test_missing_or_invalid_item_details_keep_legacy_summary(self):
        self.login(self.host,"Host")
        rows = [{"finder":1,"recipient":2,"item":"Spoiler Sword","location":"Secret Chest",
                 "category":"progression","item_id":10,"location_id":20}]
        base, bid, path = self.analytics_fixture(rows)
        path.unlink()
        for content in (None, "[]", "{", '{"source":"archipelago_generated_multiworld","placements":[]}'):
            if content is not None:
                path.write_text(content,encoding="utf-8")
            response = self.host.get(base + "/items/1")
            self.assertEqual(response.status_code,200)
            self.assertIn(b"Keine konkreten Itemdaten",response.data)
            self.assertIn("Wie viele Items hat jedes Spiel?".encode(),self.host.get(base).data)
            self.assertIn("keine vollständige, verifizierte Itemliste".encode(),self.host.get(base).data)
            self.assertEqual(self.host.get(base + "/progression/0").status_code,404)

    def test_progression_reveals_worlds_on_demand_and_protects_race_and_access(self):
        self.login(self.host,"Host")
        self.login(self.friend,"Friend")
        rows = [
            {"finder":2,"recipient":1,"category":"progression","item_id":10,"item":"Progression Key",
             "location_id":20,"location":"Hidden Boss"},
            {"finder":1,"recipient":1,"category":"progression","item_id":10,"item":"Progression Key",
             "location_id":21,"location":"<script>Hidden Chest</script>"},
            {"finder":1,"recipient":2,"category":"useful","item_id":11,"item":"Useful Potion",
             "location_id":22,"location":"Secret Room"},
        ]
        base,bid,path = self.analytics_fixture(rows)
        overview = self.host.get(base)
        self.assertIn(b"Progression Key",overview.data)
        self.assertNotIn(b"Useful Potion",overview.data)
        self.assertNotIn(b"Hidden Boss",overview.data)
        self.assertNotIn(b"in der Welt von",overview.data)
        reveal = base + "/progression/0"
        response = self.host.get(reveal,headers={"Accept":"application/json"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json(),{"worlds":[
            {"id":2,"name":"Friend","game":"Game B","count":1,"locations":[{"id":20,"name":"Hidden Boss"}]},
            {"id":1,"name":"Host","game":"Game A","count":1,"locations":[{"id":21,"name":"<script>Hidden Chest</script>"}]}]})
        self.assertEqual(response.headers["Cache-Control"],"no-store")
        self.assertIn(b"Hidden Boss",response.data)
        fallback = self.host.get(reveal)
        self.assertIn(b"Hidden Boss",fallback.data)
        self.assertIn(b"&lt;script&gt;Hidden Chest&lt;/script&gt;",fallback.data)
        self.assertNotIn(b"<script>Hidden Chest</script>",fallback.data)
        self.assertIn(b"Game B",fallback.data)
        self.assertEqual(self.host.get(base + "/progression/2").status_code,404)
        self.assertEqual(self.host.get(base + "/progression/999").status_code,404)
        self.assertEqual(self.app.test_client().get(reveal).status_code,401)
        self.assertEqual(self.friend.get(reveal).status_code,403)
        with self.app.app_context():
            sid = db.query("SELECT session_id FROM seed_builds WHERE id=?",(bid,),one=True)["session_id"]
            db.execute("INSERT INTO lobby_members(session_id,user_id) VALUES (?,2)",(sid,))
        self.assertEqual(self.friend.get(reveal).status_code,200)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET snapshot=? WHERE id=?",('{"race":true,"slots":[]}',bid))
        self.assertEqual(self.host.get(reveal).status_code,403)
        self.assertNotIn(b"Progression Key",self.host.get(base).data)

    def test_play_page_uses_verified_counts_and_handles_missing_data_and_race(self):
        self.login(self.host,"Host")
        rows = [{"finder":2,"recipient":1,"category":"progression","item_id":10,"item":"Key",
                 "location_id":20,"location":"Secret Chest"}]
        base,bid,path = self.analytics_fixture(rows)
        play = base.removesuffix("/stats") + "/play"
        page = self.host.get(play)
        self.assertEqual(page.status_code,200)
        self.assertIn(b'id="check-analysis"',page.data)
        self.assertIn(b"Checks mit platziertem Item",page.data)
        self.assertIn(b"1 platzierte Items insgesamt",page.data)
        self.assertNotIn(b"Exakte Check-Zahlen",page.data)
        self.assertNotIn(b"Secret Chest",page.data)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET stats_json='invalid' WHERE id=?",(bid,))
        missing = self.host.get(play)
        self.assertIn(b"keine verifizierten Statistikdaten gespeichert",missing.data)
        self.assertNotIn(b'id="check-analysis"',missing.data)
        with self.app.app_context():
            db.execute("UPDATE seed_builds SET snapshot=? WHERE id=?",('{"race":true,"slots":[]}',bid))
        race = self.host.get(play)
        self.assertIn(b"Race-Modus",race.data)
        self.assertNotIn(b'id="check-analysis"',race.data)

    def test_item_details_paginate_and_search_all_rows(self):
        self.login(self.host,"Host")
        rows = [{"finder":1,"recipient":1,"item":f"Item {i:03}","location":f"Location {i}",
                 "category":"filler","item_id":i,"location_id":i} for i in range(61)]
        base, bid, path = self.analytics_fixture(rows)
        first = self.host.get(base + "/items/1")
        self.assertIn(b"Item 049",first.data)
        self.assertNotIn(b"Item 050",first.data)
        second = self.host.get(base + "/items/1?page=2")
        self.assertIn(b"Item 060",second.data)
        self.assertNotIn(b"Item 049",second.data)
        search = self.host.get(base + "/items/1?q=060")
        self.assertIn(b"Item 060",search.data)
        self.assertNotIn(b"Item 001",search.data)


if __name__=="__main__":
    unittest.main()
