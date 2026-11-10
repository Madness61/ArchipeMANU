"""Authentication and migration tests only use disposable data directories."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash

from hub import ap_bridge, auth, config, db
from hub.app import create_app
from auth_helpers import PASSWORD_HASH, TEST_PASSWORD


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(config,"DATA",self.root),
                        patch.object(config,"DB_PATH",self.root/"hub.db"),
                        patch.object(config,"APWORLDS",self.root/"apworlds"),
                        patch.object(config,"SCHEMAS",self.root/"schemas"),
                        patch.object(config,"SESSIONS",self.root/"sessions"),
                        patch.object(config,"COOKIE_SECURE",False),
                        patch.object(ap_bridge,"ap_ready",return_value=False),
                        patch.object(ap_bridge,"index",return_value={"games":{},"failed":{},"ap_version":"test"})]
        for p in self.patches:
            p.start()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def post(self, path, data=None, client=None, **kwargs):
        client = client or self.client
        client.get("/login")
        with client.session_transaction() as state:
            token = state["_csrf"]
        return client.post(path, data={"_csrf":token, **(data or {})}, **kwargs)

    def register(self, name="Player", client=None, **extra):
        return self.post("/register", {"username":name,"password":TEST_PASSWORD, **extra},client=client)

    def login(self, name="Player", password=TEST_PASSWORD, client=None, path="/login"):
        return self.post(path,{"username":name,"password":password},client=client)

    def user(self, username):
        with self.app.app_context():
            row = db.query("SELECT * FROM users WHERE username=?", (username,), one=True)
            return dict(row) if row else None

    def existing_admin(self):
        with self.app.app_context():
            return db.execute("INSERT INTO users(username,slot_name,is_admin,password_hash) VALUES ('Admin','Admin',1,?)", (PASSWORD_HASH,))

    def test_registration_hashes_password_and_never_grants_admin(self):
        self.existing_admin()
        response = self.register(is_admin="1", role="admin")
        self.assertEqual(response.status_code,302)
        user = self.user("Player")
        self.assertEqual(user["is_admin"],0)
        self.assertTrue(user["password_hash"].startswith("scrypt:"))
        self.assertNotEqual(user["password_hash"],TEST_PASSWORD)
        self.assertTrue(check_password_hash(user["password_hash"],TEST_PASSWORD))
        self.assertNotIn(TEST_PASSWORD.encode(),response.data)
        self.assertEqual(self.client.get("/profile").status_code,200)
        self.assertEqual(self.client.get("/admin").status_code,403)

    def test_first_registration_becomes_admin_and_later_accounts_are_players(self):
        self.assertEqual(self.register("First", is_admin="0").status_code,302)
        self.assertEqual(self.user("First")["is_admin"],1)
        self.assertEqual(self.client.get("/admin").status_code,200)
        self.post("/logout")
        self.assertEqual(self.register("Second", is_admin="1").status_code,302)
        self.assertEqual(self.user("Second")["is_admin"],0)
        self.assertEqual(self.client.get("/admin").status_code,403)

    def test_parallel_first_registrations_create_exactly_one_admin(self):
        def register_player(name):
            return self.register(name, client=self.app.test_client()).status_code
        with ThreadPoolExecutor(max_workers=2) as workers:
            statuses = list(workers.map(register_player, ("FirstPlayer", "SecondPlayer")))
        self.assertEqual(statuses,[302,302])
        with self.app.app_context():
            users = db.query("SELECT is_admin FROM users")
            self.assertEqual(len(users),2)
            self.assertEqual(sum(u["is_admin"] for u in users),1)

    def test_existing_accounts_without_admin_do_not_promote_next_registration(self):
        with self.app.app_context():
            db.execute("INSERT INTO users(username,slot_name,is_admin) VALUES ('Legacy','Legacy',0)")
        self.assertEqual(self.register().status_code,302)
        self.assertEqual(self.user("Player")["is_admin"],0)

    def test_registration_requires_nonempty_bounded_password_and_unique_name(self):
        for fields in ({"password":""},{"username":"ab"},{"password":"x"*1025}):
            self.assertEqual(self.register(**fields).status_code,400)
        self.assertIsNone(self.user("Player"))
        self.assertEqual(self.register().status_code,302)
        self.post("/logout")
        self.assertEqual(self.register("player").status_code,400)
        with self.app.app_context():
            self.assertEqual(len(db.query("SELECT * FROM users")),1)

    def test_login_verifies_individual_password_and_does_not_create_unknown_accounts(self):
        self.register()
        self.post("/logout")
        for name, password in (("Player","wrong"),("Player","old-shared-password"),("Unknown",TEST_PASSWORD)):
            self.assertEqual(self.login(name,password).status_code,401)
            self.assertEqual(self.client.get("/profile").status_code,302)
        self.assertIsNone(self.user("Unknown"))
        self.assertEqual(self.login("player").status_code,302)
        self.assertEqual(self.client.get("/profile").status_code,200)

    def test_login_rotates_state_and_logout_revokes_copied_cookie(self):
        self.register()
        with self.client.session_transaction() as state:
            first_token, first_csrf = state["auth_token"], state["_csrf"]
            state["untrusted_state"] = "discard"
        self.login()
        with self.client.session_transaction() as state:
            self.assertNotEqual(state["auth_token"],first_token)
            self.assertNotEqual(state["_csrf"],first_csrf)
            self.assertNotIn("untrusted_state",state)
            token = state["auth_token"]
        cookie = self.client.get_cookie(self.app.config["SESSION_COOKIE_NAME"]).value
        with self.app.app_context():
            rows = db.query("SELECT * FROM auth_sessions")
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["token_hash"],auth.digest(token))
        self.assertEqual(self.post("/logout").status_code,302)
        self.client.set_cookie(self.app.config["SESSION_COOKIE_NAME"],cookie)
        self.assertEqual(self.client.get("/profile").status_code,302)
        with self.app.app_context():
            self.assertFalse(db.query("SELECT * FROM auth_sessions"))

    def test_old_uid_only_deleted_user_and_expired_sessions_are_rejected(self):
        self.existing_admin()
        with self.client.session_transaction() as state:
            state["uid"] = 1
        self.assertEqual(self.client.get("/admin").status_code,302)
        self.login("Admin")
        with self.app.app_context():
            db.execute("UPDATE auth_sessions SET expires_at=0")
        self.assertEqual(self.client.get("/admin").status_code,302)
        self.login("Admin")
        with self.app.app_context():
            db.execute("DELETE FROM users WHERE id=1")
        self.assertEqual(self.client.get("/admin").status_code,302)

    def test_round_pages_require_login_with_return_url_instead_of_english_401(self):
        from urllib.parse import parse_qs,urlsplit
        for path in ('/rounds','/lobbies','/seeds','/active-lobby','/games/community/add'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,302,path)
            self.assertEqual(urlsplit(response.location).path,'/login')
            self.assertEqual(parse_qs(urlsplit(response.location).query)['next'],[path])
            page=self.client.get(response.location).get_data(as_text=True)
            self.assertIn('Bitte melde dich an',page)
            self.assertNotIn('The server could not verify',page)

    def test_api_missing_auth_is_json_and_never_redirects_to_post_action(self):
        from urllib.parse import parse_qs,urlsplit
        self.register()
        with self.app.app_context():
            sid=db.execute("INSERT INTO sessions(name,created_by) VALUES ('Round',1)")
            bid=db.execute("INSERT INTO seed_builds(session_id,status,snapshot,created_at) VALUES (?,'succeeded','{\"slots\":[]}',CURRENT_TIMESTAMP)",(sid,))
        self.post('/logout')
        for path in (f'/sessions/{sid}/builds/{bid}/console/data',f'/sessions/{sid}/builds/{bid}/live/logic/data',
                     '/api/games/test_world/checks'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,401)
            self.assertTrue(response.json['authentication_required'])
            self.assertEqual(urlsplit(response.json['login_url']).path,'/login')
        response=self.post(f'/sessions/{sid}/builds/{bid}/console/connect')
        self.assertEqual(response.status_code,401)
        self.assertTrue(response.json['authentication_required'])
        target=parse_qs(urlsplit(response.json['login_url']).query)['next'][0]
        self.assertTrue(target.startswith(f'/sessions/{sid}?build={bid}'))
        self.assertNotIn('/connect',target)

    def test_expired_round_session_can_login_and_return_to_same_round(self):
        self.register()
        with self.app.app_context():
            sid=db.execute("INSERT INTO sessions(name,created_by) VALUES ('Return to round',1)")
            db.execute('INSERT INTO lobby_members(session_id,user_id) VALUES (?,1)',(sid,))
            db.execute('UPDATE auth_sessions SET expires_at=0')
        response=self.client.get(f'/sessions/{sid}')
        self.assertEqual(response.status_code,302)
        login_url=response.location
        self.client.get(login_url)
        resumed=self.login(path=login_url)
        self.assertEqual(resumed.location,f'/sessions/{sid}')
        self.assertEqual(self.client.get(resumed.location).status_code,200)

    def test_player_session_cannot_claim_admin_id_or_use_forged_cookie(self):
        self.existing_admin()
        self.register()
        with self.client.session_transaction() as state:
            state["uid"] = 1  # Even a correctly signed cookie needs a matching server token.
        self.assertEqual(self.client.get("/admin").status_code,302)
        self.login("Player")
        cookie_name = self.app.config["SESSION_COOKIE_NAME"]
        cookie = self.client.get_cookie(cookie_name).value
        self.client.set_cookie(cookie_name,"invalid."+cookie)
        self.assertEqual(self.client.get("/profile").status_code,302)

    def test_forwarded_headers_cannot_bypass_ip_limit(self):
        with patch.object(auth,"LOGIN_IP_LIMIT",2), patch.object(auth,"check_password_hash",return_value=False):
            for i in range(2):
                response = self.post("/login",{"username":f"Name{i}","password":"wrong"},
                                     headers={"X-Forwarded-For":f"10.0.0.{i}"})
                self.assertEqual(response.status_code,401)
            response = self.post("/login",{"username":"Another","password":"wrong"},
                                 headers={"X-Forwarded-For":"10.0.0.99"})
            self.assertEqual(response.status_code,429)

    def test_cookie_flags_expiry_and_sensitive_response_caching(self):
        self.app.config["SESSION_COOKIE_SECURE"] = True
        response = self.client.get("/login",base_url="https://localhost")
        cookie = response.headers["Set-Cookie"]
        for flag in ("HttpOnly","Secure","SameSite=Lax","Path=/"):
            self.assertIn(flag,cookie)
        self.assertEqual(response.headers["Cache-Control"],"no-store")
        self.assertEqual(response.headers["Referrer-Policy"],"no-referrer")
        self.assertEqual(int(self.app.permanent_session_lifetime.total_seconds()),auth.SESSION_SECONDS)
        self.app.config["SESSION_COOKIE_SECURE"] = False

    def test_csrf_on_register_login_logout_setup_and_admin(self):
        for path in ("/register","/login","/logout","/account/setup","/admin/users/1/setup"):
            self.assertEqual(self.client.post(path,data={}).status_code,403)
            self.assertEqual(self.client.post(path,data={"_csrf":"ä-invalid"}).status_code,403)
        self.register()
        self.assertEqual(self.client.get("/logout").status_code,405)

    def test_account_and_ip_login_limits_and_window_expiry(self):
        with patch.object(auth,"check_password_hash",return_value=False), patch.object(auth.time,"time",return_value=1000):
            for i in range(auth.LOGIN_ACCOUNT_LIMIT):
                response = self.post("/login",{"username":"Player","password":"wrong"},
                                     environ_overrides={"REMOTE_ADDR":f"10.0.0.{i}"})
                self.assertEqual(response.status_code,401)
            response = self.login("PLAYER","wrong")
            self.assertEqual(response.status_code,429)
            self.assertIn("Retry-After",response.headers)
        with patch.object(auth,"check_password_hash",return_value=False), patch.object(auth.time,"time",return_value=2000):
            self.assertEqual(self.login("Player","wrong").status_code,401)
            for i in range(auth.LOGIN_IP_LIMIT-1):
                self.assertEqual(self.login(f"Other{i}","wrong").status_code,401)
            self.assertEqual(self.login("Another","wrong").status_code,429)
            with patch.object(auth.time,"time",return_value=3000):
                self.assertEqual(self.login("Another","wrong").status_code,401)

    def test_registration_and_setup_rate_limits(self):
        for path in ("/register","/account/setup"):
            for _ in range(10):
                self.assertEqual(self.post(path).status_code,400)
            self.assertEqual(self.post(path).status_code,429)

    def test_open_registration_cannot_claim_legacy_admin(self):
        with self.app.app_context():
            db.execute("INSERT INTO users(username,slot_name,is_admin,overrides) VALUES ('Manu','Old Slot',1,?)", ('{"death_link":false}',))
        self.assertEqual(self.register("manu").status_code,400)
        self.assertEqual(self.login("Manu","old-shared-password").status_code,401)
        user = self.user("Manu")
        self.assertEqual(user["password_hash"],"")
        self.assertEqual(user["is_admin"],1)
        self.assertEqual(user["slot_name"],"Old Slot")

    def test_setup_code_is_hashed_single_use_expiring_and_preserves_admin_identity(self):
        with self.app.app_context():
            uid = db.execute("INSERT INTO users(username,slot_name,is_admin) VALUES ('Manu','Original',1)")
            first = auth.issue_setup(uid)
            code = auth.issue_setup(uid)
            stored = db.query("SELECT * FROM account_setup",one=True)
            self.assertEqual(stored["token_hash"],auth.digest(code))
            self.assertNotEqual(stored["token_hash"],code)
        fields = {"password":TEST_PASSWORD,"password_confirm":TEST_PASSWORD}
        self.assertEqual(self.post("/account/setup",{**fields,"code":first}).status_code,400)
        self.assertEqual(self.post("/account/setup",{**fields,"code":code}).status_code,302)
        self.assertEqual(self.post("/account/setup",{**fields,"code":code}).status_code,400)
        user = self.user("Manu")
        self.assertEqual((user["id"],user["slot_name"],user["is_admin"]),(uid,"Original",1))
        self.assertEqual(self.login("Manu").status_code,302)
        self.assertEqual(self.client.get("/admin").status_code,200)
        with self.app.app_context():
            expired = auth.issue_setup(uid,reset=True)
            db.execute("UPDATE account_setup SET expires_at=0")
        self.assertEqual(self.post("/account/setup",{**fields,"code":expired}).status_code,400)

    def test_admin_only_issues_codes_and_reset_revokes_every_session(self):
        self.existing_admin()
        self.login("Admin")
        player = self.app.test_client()
        self.register(client=player)
        uid = self.user("Player")["id"]
        denied = self.post(f"/admin/users/{uid}/setup",client=player)
        self.assertEqual(denied.status_code,403)
        old_cookie = player.get_cookie(self.app.config["SESSION_COOKIE_NAME"]).value
        response = self.post(f"/admin/users/{uid}/setup")
        self.assertEqual(response.status_code,200)
        code = re.search(rb'id="account-code">([^<]+)',response.data).group(1).decode()
        self.assertEqual(response.headers["Cache-Control"],"no-store")
        with self.client.session_transaction() as state:
            self.assertNotIn(code,json.dumps(dict(state)))
        new_password = "A new personal password 43!"
        self.assertEqual(self.post("/account/setup",{"code":code,"password":new_password,
                                    "password_confirm":new_password},client=player).status_code,302)
        player.set_cookie(self.app.config["SESSION_COOKIE_NAME"],old_cookie)
        self.assertEqual(player.get("/profile").status_code,302)
        self.assertEqual(self.login("Player",TEST_PASSWORD,client=player).status_code,401)
        self.assertEqual(self.login("Player",new_password,client=player).status_code,302)

    def test_registration_accepts_short_password_without_invite_or_confirmation(self):
        for index, password in enumerate(("x", "kurz", "ä🔑")):
            with self.subTest(password=password):
                name = f"Player{index}"
                self.assertEqual(self.register(name,password=password).status_code,302)
                self.assertTrue(check_password_hash(self.user(name)["password_hash"],password))
                self.assertEqual(self.client.get("/profile").status_code,200)
                self.post("/logout")
                self.assertEqual(self.login(name,password).status_code,302)
                self.post("/logout")

    def test_legacy_invite_settings_do_not_restrict_registration(self):
        with self.app.app_context():
            db.execute("INSERT INTO auth_settings(key,value) VALUES ('invite_hash',?)", (auth.digest("obsolete"),))
        with patch.dict("os.environ", {"HUB_INVITE_CODE":"obsolete", "HUB_PASSWORD":"obsolete"}):
            self.assertEqual(self.register().status_code,302)
        page = self.client.get("/register").get_data(as_text=True)
        self.assertNotIn('name="invite_code"',page)
        self.assertNotIn('name="password_confirm"',page)
        self.assertNotIn('minlength="12"',page)

    def test_legacy_password_setup_accepts_short_password_but_checks_confirmation(self):
        with self.app.app_context():
            uid = db.execute("INSERT INTO users(username,slot_name,is_admin) VALUES ('Manu','Original',1)")
            code = auth.issue_setup(uid)
        fields = {"code":code,"password":"x","password_confirm":"different"}
        self.assertEqual(self.post("/account/setup",fields).status_code,400)
        self.assertEqual(self.post("/account/setup",{**fields,"password_confirm":"x"}).status_code,302)
        self.assertEqual(self.login("Manu","x").status_code,302)
        self.assertEqual(self.client.get("/admin").status_code,200)

    def test_redirects_are_local_and_role_changes_are_checked_on_next_request(self):
        self.existing_admin()
        for target in ("https://evil.example","//evil.example",r"/\evil.example"):
            response = self.login("Admin",path="/login?next="+target)
            self.assertEqual(response.location,"/")
        self.assertEqual(self.login("Admin",path="/login?next=/profile").location,"/profile")
        with self.app.app_context():
            db.execute("UPDATE users SET is_admin=0 WHERE username='Admin'")
        self.assertEqual(self.client.get("/admin").status_code,403)
        self.assertEqual(self.post("/admin/users/1/admin").status_code,403)

    def test_local_bootstrap_does_not_promote_existing_users_and_setup_cli_is_not_web_claim(self):
        output = io.StringIO()
        with patch.object(sys,"argv",["auth","bootstrap-admin","Manu"]), contextlib.redirect_stdout(output):
            auth.main()
        self.assertEqual(self.user("Manu")["is_admin"],1)
        self.assertIn("Einmaliger Einrichtungscode",output.getvalue())
        self.assertEqual(self.user("Manu")["password_hash"],"")
        with patch.object(sys,"argv",["auth","bootstrap-admin","Another"]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                auth.main()
        self.assertIsNone(self.user("Another"))
        output = io.StringIO()
        with patch.object(sys,"argv",["auth","setup-account","Manu"]), contextlib.redirect_stdout(output):
            auth.main()
        self.assertIn("Einmaliger Einrichtungscode",output.getvalue())


class MigrationTests(unittest.TestCase):
    def test_additive_idempotent_migration_preserves_all_legacy_rows(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(config,"DB_PATH",Path(folder)/"hub.db"):
            db.init()
            with db.transaction() as conn:
                conn.execute("INSERT INTO users(id,username,slot_name,is_admin,overrides) VALUES (7,'Manu','ManuSlot',1,?)", ('{"death_link":false}',))
                conn.execute("INSERT INTO users(id,username,slot_name) VALUES (9,'Player','PlayerSlot')")
                conn.execute("INSERT INTO templates(id,game,name,created_by) VALUES (3,'test','Saved preset',7)")
                conn.execute("INSERT INTO sessions(id,name,created_by) VALUES (4,'Saved lobby',7)")
                conn.execute("INSERT INTO entries(session_id,user_id,game) VALUES (4,9,'test')")
                before = {table:[dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
                          for table in ("users","templates","sessions","entries")}
            auth.migrate()
            auth.migrate()
            with db.transaction() as conn:
                for table, rows in before.items():
                    after = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
                    if table == "users":
                        self.assertTrue(all(r.pop("password_hash") == "" for r in after))
                    self.assertEqual(after,rows)
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[])
