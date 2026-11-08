"""End-to-end option layering, immutable presets and generator input regression tests."""
from copy import deepcopy
import hashlib
import html
import io
import json
from pathlib import Path
import random
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import yaml
from werkzeug.datastructures import MultiDict

import ap_runner
from hub import ap_bridge, config, db, mvp, yamlgen
from hub.app import create_app, session_entries, session_yamls
from auth_helpers import provision_user, TEST_PASSWORD
from test_yamlgen import SCHEMA


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.schema = deepcopy(SCHEMA)
        self.schema["options"].append({"key":"complex", "name":"Complex", "kind":"raw", "container":"dict",
                                      "default":{},"group":"Advanced","simple":False})
        self.index = {"games":{"test_game":{"game":"Test Game","version":"1.2.0","custom":False}},
                      "ap_version":"0.6.8", "failed":{}}
        self.patches = [patch.object(config,"DATA",self.root),patch.object(config,"DB_PATH",self.root/"hub.db"),
                        patch.object(config,"APWORLDS",self.root/"apworlds"),
                        patch.object(config,"SCHEMAS",self.root/"schemas"),
                        patch.object(config,"SESSIONS",self.root/"sessions"),
                        patch.object(ap_bridge,"ap_ready",return_value=False),
                        patch.object(ap_bridge,"start_extract"),
                        patch.object(ap_bridge,"schema",side_effect=lambda slug:self.schema if slug=="test_game" else None),
                        patch.object(ap_bridge,"index",return_value=self.index)]
        for p in self.patches:
            p.start()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        provision_user(self.app,"Host",is_admin=True)
        self.client = self.app.test_client()
        self.post("/login",{"username":"Host","password":TEST_PASSWORD})
        self.post("/sessions",{"name":"Configuration"})
        with self.app.app_context():
            self.sid = db.query("SELECT id FROM sessions",one=True)["id"]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def post(self,url,body=None,**kwargs):
        self.client.get("/login")
        with self.client.session_transaction() as state:
            csrf = state["_csrf"]
        data = body.copy() if isinstance(body,MultiDict) else MultiDict()
        if not isinstance(body,MultiDict):
            for key,value in (body or {}).items():
                data.add(key,value)
        data["_csrf"] = csrf
        return self.client.post(url,data=data,**kwargs)

    def choose(self,ref="default"):
        response = self.post(f"/sessions/{self.sid}/entries",{"game":"test_game","ref":ref})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            self.eid = db.query("SELECT id FROM entries WHERE session_id=?",(self.sid,),one=True)["id"]
        return self.eid

    def preset(self,values,requirements=None):
        with self.app.app_context():
            tid = db.execute("""INSERT INTO templates(game,name,vals,created_by,requirements)
                VALUES ('test_game','Selected preset',?,1,?)""",(db.dumps(values),db.dumps(requirements or {})))
        return tid

    def entry(self):
        with self.app.app_context():
            return next(e for e in session_entries(self.sid) if e["id"]==self.eid)

    def preview(self):
        response = self.client.get(f"/entries/{self.eid}/options?expert=1")
        self.assertEqual(response.status_code,200)
        match = re.search(r'<pre class="log">(.*?)</pre>',response.get_data(as_text=True),re.S)
        self.assertIsNotNone(match,response.data)
        return html.unescape(match.group(1))

    def test_four_layers_default_resets_preview_and_actual_generated_bytes(self):
        tid = self.preset({"goal":"all_chests","death_link":False,"progression_balancing":10})
        with self.app.app_context():
            db.execute("UPDATE users SET overrides=? WHERE id=1",(db.dumps({"death_link":True,"progression_balancing":80}),))
        self.choose(f"t:{tid}")
        self.assertEqual(self.entry()["values"]["progression_balancing"],80)
        form = MultiDict([("_r","goal"),("o.goal","boss"),("_r","death_link"),
                          ("_r","progression_balancing"),("o.progression_balancing","0")])
        self.post(f"/entries/{self.eid}/options",form)
        entry = self.entry()
        self.assertEqual(db.loads(entry["option_overrides"]),{"goal":"boss","death_link":False,"progression_balancing":0})
        preview = self.preview()
        with self.app.app_context():
            self.assertEqual(dict(session_yamls(session_entries(self.sid)))["Host.yaml"],preview)
        self.post(f"/entries/{self.eid}/ready",{"ready":"1"})
        seen = {}

        def fake_generate(players,out,*args,**kwargs):
            for path in players.glob("*.yaml"):
                seen[path.name] = path.read_bytes()
            archive = out/"AP_CONFIG.zip"
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr("AP_CONFIG.archipelago",b"mock")
            return True,"verified input",archive

        class ImmediateThread:
            def __init__(self,target,args,**kwargs):
                self.target,self.args = target,args
            def start(inner):
                with self.app.app_context():
                    # Changes after the snapshot must never alter the worker's YAML.
                    db.execute("UPDATE templates SET vals='{}' WHERE id=?",(tid,))
                    db.execute("UPDATE users SET overrides='{}' WHERE id=1")
                inner.target(*inner.args)

        with patch.object(ap_bridge,"ap_ready",return_value=True), \
                patch.object(ap_bridge,"generate",side_effect=fake_generate),patch.object(mvp.threading,"Thread",ImmediateThread):
            response = self.post(f"/sessions/{self.sid}/generate",{"spoiler":"1"})
            self.assertEqual(response.status_code,302)
        self.assertEqual(seen,{"Host.yaml":preview.encode("utf-8")})
        with self.app.app_context():
            build = db.query("SELECT * FROM seed_builds",one=True)
            self.assertEqual(build["status"],"succeeded",build["log"])
            snapshot = db.loads(build["snapshot"])
            self.assertEqual(snapshot["slots"][0]["values"],yaml.safe_load(preview)["Test Game"])
            self.assertEqual(snapshot["yamls"]["Host.yaml"],hashlib.sha256(seen["Host.yaml"]).hexdigest())

    def test_selected_template_is_frozen_until_explicit_reselection(self):
        tid = self.preset({"goal":"all_chests"})
        self.choose(f"t:{tid}")
        self.post(f"/entries/{self.eid}/ready",{"ready":"1"})
        before = self.preview()
        self.post(f"/templates/{tid}/edit",{"name":"Changed preset","shared":"1","_r":"goal","o.goal":"boss"})
        self.assertEqual(self.preview(),before)
        self.assertTrue(self.entry()["ready_valid"])
        self.post(f"/entries/{self.eid}/template",{"ref":f"t:{tid}"})
        self.assertEqual(self.entry()["values"]["goal"],"boss")
        self.assertEqual(self.entry()["ready"],0)

    def test_preview_uses_the_same_deduplicated_safe_slot_name_as_export(self):
        self.choose()
        with self.app.app_context():
            db.execute("UPDATE users SET slot_name=? WHERE id=1",("Host/\\?:",))
            self.eid = db.execute("INSERT INTO entries(session_id,user_id,game) VALUES (?,1,'test_game')",(self.sid,))
        preview = self.preview()
        self.assertEqual(yaml.safe_load(preview)["name"],"Host2")
        with self.app.app_context():
            files = dict(session_yamls(session_entries(self.sid)))
            self.assertEqual(files["Host2.yaml"],preview)
            self.assertEqual(set(files),{"Host.yaml","Host2.yaml"})

    def test_import_is_immutable_selectable_and_preserves_original_weights_and_complex_values(self):
        original = ("\ufeffname: Someone\r\ngame: Test Game\r\nTest Game:\r\n"
                    "  goal: {boss: 0, all_chests: 50}\r\n  death_link: false\r\n"
                    "  complex: {nested: [one, {two: 2}]}\r\n").encode("utf-8")
        response = self.post("/import",{"files":(io.BytesIO(original),"preset.yaml"),"shared":"1"},content_type="multipart/form-data")
        self.assertEqual(response.status_code,200)
        with self.app.app_context():
            row = db.query("SELECT * FROM templates",one=True)
            tid = row["id"]
            self.assertEqual(row["source_yaml"].encode("utf-8"),original)
            self.assertEqual(row["source_sha256"],hashlib.sha256(original).hexdigest())
            self.assertTrue(row["immutable"])
        refs = self.client.get("/api/games/test_game/templates").get_json()
        self.assertIn(f"t:{tid}",[t["ref"] for t in refs])
        self.choose(f"t:{tid}")
        values = yaml.safe_load(self.preview())["Test Game"]
        self.assertEqual(values["goal"],{"boss":0,"all_chests":50})
        self.assertEqual(values["complex"],{"nested":["one",{"two":2}]})
        self.assertIs(values["death_link"],False)
        self.assertEqual(self.post(f"/templates/{tid}/edit",{"name":"Overwrite"}).status_code,302)
        with self.client.get(f"/templates/{tid}/source") as source:
            self.assertEqual(source.data,original)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT source_sha256 FROM templates WHERE id=?",(tid,),one=True)["source_sha256"],hashlib.sha256(original).hexdigest())

    def test_multiple_documents_for_the_same_game_remain_individually_selectable(self):
        source = ("name: A\ngame: Test Game\nTest Game: {goal: boss}\n---\n"
                  "name: B\ngame: Test Game\nTest Game: {goal: all_chests}\n")
        self.post("/import",{"text":source,"shared":"1"})
        with self.app.app_context():
            rows = db.query("SELECT id,vals FROM templates ORDER BY id")
            self.assertEqual(len(rows),2)
        for row in rows:
            self.choose(f"t:{row['id']}")
            self.assertEqual(self.entry()["values"]["goal"],db.loads(row["vals"])["goal"])

    def test_lobby_weight_editor_preview_only_inheritance_and_readiness(self):
        with self.app.app_context():
            db.execute("UPDATE users SET overrides=? WHERE id=1",(db.dumps({"death_link":True}),))
        self.choose()
        self.post(f"/entries/{self.eid}/ready",{"ready":"1"})
        weighted = MultiDict([("_r","goal"),("m.goal","raw"),("y.goal","boss: 30\nall_chests: 70"),("_action","preview")])
        response = self.post(f"/entries/{self.eid}/options",weighted)
        self.assertIn(b"boss: 30",response.data)
        self.assertTrue(self.entry()["ready_valid"])
        self.assertEqual(db.loads(self.entry()["option_overrides"]),{})
        weighted["_action"] = "save"
        self.post(f"/entries/{self.eid}/options",weighted)
        self.assertEqual(self.entry()["ready"],0)
        self.assertEqual(self.entry()["values"]["goal"],{"boss":30,"all_chests":70})
        self.post(f"/entries/{self.eid}/options",MultiDict([("_r","death_link")]))
        self.assertFalse(self.entry()["values"]["death_link"])
        self.post(f"/entries/{self.eid}/options",MultiDict([("_r","death_link"),("_inherit","death_link")]))
        self.assertTrue(self.entry()["values"]["death_link"])

    def test_invalid_unknown_legacy_options_are_not_silently_removed(self):
        self.choose()
        with self.app.app_context():
            db.execute("UPDATE entries SET option_overrides=? WHERE id=?",(db.dumps({"removed_option":17}),self.eid))
        response = self.post(f"/entries/{self.eid}/options",{"_r":"goal","o.goal":"all_chests"})
        self.assertIn(b"removed_option",response.data)
        self.assertEqual(db.loads(self.entry()["option_overrides"]),{"removed_option":17})
        self.post(f"/entries/{self.eid}/ready",{"ready":"1"})
        self.assertEqual(self.entry()["ready"],0)
        with self.app.app_context():
            _,files,issues = mvp.preflight(self.sid)
            self.assertFalse(files)
            self.assertTrue(any("removed_option" in issue for issue in issues))
        self.post(f"/entries/{self.eid}/options",{"_action":"reset"})
        self.assertEqual(db.loads(self.entry()["option_overrides"]),{})

    def test_profile_changes_and_schema_changes_invalidate_readiness(self):
        self.choose()
        self.post(f"/entries/{self.eid}/ready",{"ready":"1"})
        self.assertTrue(self.entry()["ready_valid"])
        self.post("/profile",{"slot_name":"Host","death_link":"on","progression_balancing":"30"})
        self.assertEqual(self.entry()["ready"],0)
        self.post(f"/entries/{self.eid}/ready",{"ready":"1"})
        self.schema["options"][0]["default"] = "all_chests"
        self.assertFalse(self.entry()["ready_valid"])
        with self.app.app_context():
            _,files,issues = mvp.preflight(self.sid)
            self.assertFalse(files)

    def test_late_edit_cannot_change_configuration_after_lobby_closes(self):
        self.choose()
        update = mvp.update_open_entry
        def close_lobby(*args):
            with self.app.app_context():
                db.execute("UPDATE sessions SET locked=1 WHERE id=?",(self.sid,))
            return update(*args)
        before = self.entry()["option_overrides"]
        with patch.object(mvp,"update_open_entry",side_effect=close_lobby):
            response = self.post(f"/entries/{self.eid}/options",{"_r":"goal","o.goal":"all_chests"})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.entry()["option_overrides"],before)

    def test_incompatible_template_requirements_and_missing_worlds_block_generation(self):
        tid = self.preset({}, {"game":{"Test Game":{"min":"9.0.0"}}})
        self.choose(f"t:{tid}")
        response = self.client.get(f"/entries/{self.eid}/options")
        self.assertIn("nicht mit der Vorlage kompatibel".encode(),response.data)
        self.post(f"/entries/{self.eid}/ready",{"ready":"1"})
        self.assertEqual(self.entry()["ready"],0)
        with patch.object(ap_bridge,"schema",return_value=None):
            self.assertEqual(self.client.get(f"/sessions/{self.sid}").status_code,200)
            with self.app.app_context():
                _,files,issues = mvp.preflight(self.sid)
                self.assertFalse(files)
                self.assertTrue(any("nicht installiert" in issue for issue in issues))

    def test_community_yaml_is_a_selectable_preset_and_tampering_is_detected(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive,"w") as z:
            z.writestr("test_game/__init__.py","pass")
            z.writestr("test_game/archipelago.json",json.dumps({"game":"Test Game","world_version":"1.2.0"}))
        self.post("/games/community/add",{"apworld":(io.BytesIO(archive.getvalue()),"test.apworld"),
                  "yaml":(io.BytesIO(b"name: Test\ngame: Test Game\nTest Game:\n  goal: all_chests\n"),"preset.yaml")},
                  content_type="multipart/form-data")
        with self.app.app_context():
            sha = db.query("SELECT sha256 FROM community_games",one=True)["sha256"]
        self.schema.update(custom=True,world_sha256=sha)
        refs = self.client.get("/api/games/test_game/templates").get_json()
        self.assertIn("c:"+sha,[t["ref"] for t in refs])
        self.choose("c:"+sha)
        self.assertEqual(self.entry()["values"]["goal"],"all_chests")
        path = config.DATA/"community"/sha/"options.yaml"
        path.write_text("name: Changed\ngame: Test Game\nTest Game: {}\n",encoding="utf-8")
        self.assertEqual(self.entry()["values"]["goal"],"all_chests")
        self.assertEqual(self.post(f"/sessions/{self.sid}/entries",{"game":"test_game","ref":"c:"+sha}).status_code,400)

    def test_schema_provenance_requires_reextract_after_world_version_switch(self):
        self.choose()
        active = [{"module":"test_game","sha256":"a"*64,"active":True}]
        with patch.object(ap_bridge,"list_apworld_versions",return_value=active):
            response = self.client.get(f"/entries/{self.eid}/options")
            self.assertEqual(response.status_code,409)
            self.assertIn("Optionen neu einlesen".encode(),response.data)
            self.schema["world_sha256"] = "a"*64
            self.assertEqual(self.client.get(f"/entries/{self.eid}/options").status_code,200)
            with self.app.app_context():
                db.execute("UPDATE entries SET selected_apworld_sha=? WHERE id=?",("b"*64,self.eid))
            self.assertIn("gewählte APWorld-Version".encode(),self.client.get(f"/entries/{self.eid}/options").data)

    def test_legacy_values_survive_migration_and_clone_keeps_snapshot(self):
        tid = self.preset({"goal":"all_chests"})
        with self.app.app_context():
            self.eid = db.execute("""INSERT INTO entries(session_id,user_id,game,template_ref,option_overrides)
                VALUES (?,1,'test_game',?,?)""",(self.sid,f"t:{tid}",db.dumps({"death_link":False})))
        mvp.migrate()
        first = self.entry()
        mvp.migrate()
        self.assertEqual(self.entry()["template_snapshot"],first["template_snapshot"])
        self.assertEqual(db.loads(first["option_overrides"]),{"death_link":False})
        self.assertEqual(first["values"]["goal"],"all_chests")
        self.post(f"/sessions/{self.sid}/clone")
        with self.app.app_context():
            cloned = db.query("SELECT * FROM entries WHERE session_id!=?",(self.sid,),one=True)
            self.assertEqual(cloned["template_snapshot"],first["template_snapshot"])


class ValueValidationTests(unittest.TestCase):
    def test_repeated_aliases_cannot_expand_without_limit(self):
        value = ["leaf"]
        for _ in range(18):
            value = [value,value]
        with self.assertRaisesRegex(ValueError,"zu groß"):
            yamlgen.json_value(value)

    def test_slot_names_cannot_escape_output_folder_or_use_windows_reserved_names(self):
        for original in ("../Host",r"..\Host","a/b\\c", "CON", "AUX.txt", "Host. ","a\nHost"):
            name = yamlgen.clean_slot_name(original)
            self.assertNotIn("/",name)
            self.assertNotIn("\\",name)
            self.assertNotIn("\n",name)
            self.assertFalse(name.endswith("."))
        self.assertEqual(yamlgen.clean_slot_name("CON"),"_CON")
    def test_invalid_weights_unknown_options_and_containers_have_errors(self):
        for value in ({"boss":0,"all_chests":0},{"boss":-1},{"boss":.5},{"boss":float("nan")},
                      {"boss":float("inf")},{"boss":True},{"missing":1},[],["missing"],{}):
            self.assertIn("goal",yamlgen.validate_values(SCHEMA,{"goal":value}))
        self.assertIn("removed",yamlgen.validate_values(SCHEMA,{"removed":1}))
        schema = {**SCHEMA,"options":[{"key":"complex","kind":"raw","default":{},"container":"dict"}]}
        self.assertIn("complex",yamlgen.validate_values(schema,{"complex":["wrong"]}))
        self.assertFalse(yamlgen.validate_values(schema,{"complex":{"nested":[{"value":1}]}}))

    def test_weighted_ranges_named_values_and_free_text_choices(self):
        values = {"progression_balancing":{"0":1,"normal":2,"random-range-10-20":1},
                  "goal":["boss","all_chests"]}
        self.assertEqual(yamlgen.validate_values(SCHEMA,values),{})
        self.assertIn("progression_balancing",yamlgen.validate_values(SCHEMA,{"progression_balancing":{1.5:2}}))
        schema = {"options":[{"key":"text","kind":"textchoice","choices":[["default","Default"]]}]}
        self.assertEqual(yamlgen.validate_values(schema,{"text":{"custom value":1,"another value":2}}),{})

    def test_import_does_not_drop_unknown_or_unsupported_options(self):
        for text in ("game: Test Game\nTest Game: {unknown: 1}",
                     "game: Test Game\nTest Game: [wrong]",
                     "game: Test Game\ntriggers: []\nTest Game: {}",
                     "game: Test Game\nTest Game:\n  goal: boss\n  goal: all_chests",
                     "game: Test Game\nTest Game:\n  progression_balancing: .nan",
                     "game: Test Game\nTest Game:\n  goal: &loop [*loop]"):
            results,errors = yamlgen.import_yaml(text,{"test_game":{"game":"Test Game"}},lambda _:SCHEMA)
            self.assertFalse(results,text)
            self.assertTrue(errors,text)

    def test_explicit_empty_values_and_default_overrides_survive_serialization(self):
        baseline = yamlgen.effective_values(SCHEMA,{"start_inventory":{"Sword":2},"exclude_locations":["Boss"]},
                                            {"death_link":True,"progression_balancing":70})
        form = MultiDict([("_r","death_link"),("_r","progression_balancing"),("o.progression_balancing","50"),
                          ("_r","start_inventory"),("o.start_inventory",""),("_r","exclude_locations"),("o.exclude_locations","")])
        overrides,errors = yamlgen.parse_lobby_form(SCHEMA,form,{},baseline)
        self.assertEqual(errors,{})
        self.assertEqual(overrides,{"death_link":False,"progression_balancing":50,"start_inventory":{},"exclude_locations":[]})
        document = yaml.safe_load(yamlgen.player_yaml("Name",SCHEMA,yamlgen.effective_values(SCHEMA,baseline,overrides),"Test","0.6.8"))
        for key,value in overrides.items():
            self.assertEqual(document["Test Game"][key],value)

    def test_inherit_can_remove_a_now_invalid_lobby_value(self):
        baseline = yamlgen.effective_values(SCHEMA)
        form = MultiDict([("_r","goal"),("_inherit","goal"),("o.goal","removed")])
        values,errors = yamlgen.parse_lobby_form(SCHEMA,form,{"goal":"removed"},baseline)
        self.assertFalse(errors)
        self.assertEqual(values,{})

    def test_real_option_classes_validate_every_weighted_alternative_without_changing_rng(self):
        checked = []
        class Option:
            supports_weighting = True
            @staticmethod
            def from_any(value):
                random.random()
                checked.append(value)
                if value == "invalid":
                    raise ValueError("World rejects this option")
                return SimpleNamespace(verify=lambda *a:None)
        world = SimpleNamespace(options_dataclass=SimpleNamespace(type_hints={"goal":Option}))
        modules = {"worlds":SimpleNamespace(AutoWorldRegister=SimpleNamespace(world_types={"Test Game":world})),
                   "BaseClasses":SimpleNamespace(PlandoOptions=SimpleNamespace(bosses="bosses"))}
        with tempfile.TemporaryDirectory() as folder,patch.dict(sys.modules,modules):
            path = Path(folder)/"Player.yaml"
            path.write_text(yaml.safe_dump({"name":"Player","game":"Test Game","Test Game":{"goal":{"valid":1,"invalid":1}}}),encoding="utf-8")
            state = random.getstate()
            with self.assertRaisesRegex(ValueError,"Player.yaml.*goal.*World rejects"):
                ap_runner.validate_player_files(folder)
            self.assertIn("invalid",checked)
            self.assertEqual(random.getstate(),state)

    def test_successful_extraction_binds_schema_to_actual_world_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("schemas","apworlds"):
                (root/name).mkdir()
            (root/"apworlds"/"test_game.apworld").write_bytes(b"archive bytes for provenance test")
            def run(args,timeout):
                target = Path(args[args.index("--out")+1])
                target.mkdir()
                (target/"index.json").write_text(json.dumps({"games":{"test_game":{"game":"Test Game"}}}),encoding="utf-8")
                (target/"test_game.json").write_text(json.dumps(SCHEMA),encoding="utf-8")
                return True,"fake extraction"
            with patch.object(config,"DATA",root),patch.object(config,"SCHEMAS",root/"schemas"), \
                    patch.object(config,"APWORLDS",root/"apworlds"),patch.object(ap_bridge,"_sync_custom_worlds"), \
                    patch.object(ap_bridge,"_run",side_effect=run),patch.object(ap_bridge,"_write_status"):
                self.assertTrue(ap_bridge.extract())
                schema = json.loads((root/"schemas"/"test_game.json").read_text(encoding="utf-8"))
                self.assertEqual(schema["world_sha256"],hashlib.sha256(b"archive bytes for provenance test").hexdigest())

    def test_incomplete_extraction_preserves_previous_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"schemas").mkdir()
            previous = root/"schemas"/"index.json"
            previous.write_text('{"games":{}}',encoding="utf-8")
            with patch.object(config,"DATA",root),patch.object(config,"SCHEMAS",root/"schemas"), \
                    patch.object(ap_bridge,"_sync_custom_worlds"),patch.object(ap_bridge,"_run",return_value=(True,"no output")), \
                    patch.object(ap_bridge,"_write_status") as status:
                self.assertFalse(ap_bridge.extract())
                self.assertEqual(previous.read_text(encoding="utf-8"),'{"games":{}}')
                self.assertEqual(status.call_args.kwargs["status"],"error")
