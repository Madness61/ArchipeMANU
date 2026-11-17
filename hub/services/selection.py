"""Preset resolution, immutable selections and YAML composition."""
import hashlib
import json
import re
from flask import abort, g
from hub import ap_bridge, db, yamlgen, community, config, i18n

def get_schema(slug: str) -> dict:
    schema = ap_bridge.schema(slug)
    if schema is None:
        abort(404, "Spiel nicht gefunden – ist die APWorld installiert und eingelesen?")
    return schema


def group_default_ref(slug: str) -> str:
    row = db.query("SELECT template_ref FROM game_defaults WHERE game = ?", (slug,), one=True)
    return row["template_ref"] if row else "default"


def resolve_template(schema: dict, ref: str) -> tuple[str, dict, bool]:
    """-> (label, values, found). Missing templates fall back to the APWorld defaults."""
    if ref.startswith("preset:"):
        name = ref[len("preset:"):]
        if name in schema["presets"]:
            return f"APWorld-Preset „{name}“", schema["presets"][name], True
    elif ref.startswith("t:") and ref[2:].isdigit():
        row = db.query("SELECT * FROM templates WHERE id = ? AND game = ?", (int(ref[2:]), schema["slug"]), one=True)
        if row:
            actor = getattr(g,"user",None)
            if not row["shared"] and not (actor and (actor["is_admin"] or actor["id"] == row["created_by"])):
                return "Persönliche Vorlage nicht zugänglich",{},False
            if row["immutable"]:
                if hashlib.sha256(row["source_yaml"].encode("utf-8")).hexdigest() != row["source_sha256"]:
                    return "Originalvorlage verändert",{},False
                originals,issues = yamlgen.import_yaml(row["source_yaml"],{schema["slug"]:{"game":schema["game"]}},lambda _:schema)
                original = next((p for p in originals if p["slug"] == schema["slug"]
                                 and p["values"] == db.loads(row["vals"])
                                 and p["requires"] == db.loads(row["requirements"])),None)
                if not original:
                    return "Originalvorlage verändert oder inkompatibel",{},False
            return f"Vorlage „{row['name']}“", db.loads(row["vals"]), True
    elif ref.startswith("c:"):
        preset = uploaded_preset(schema,ref[2:])
        if preset:
            return preset["name"],preset["values"],True
    elif ref == "default":
        return "Standard (APWorld)", {}, True
    return "Standard (APWorld)", {}, False


def uploaded_preset(schema, sha):
    if not re.fullmatch(r"[0-9a-f]{64}",sha):
        return None
    row = db.query("SELECT * FROM community_games WHERE sha256=? AND module=? AND yaml_file=sha256",
                   (sha,schema["slug"]),one=True)
    if not row:
        return None
    try:
        data = (config.DATA / "community" / sha / "options.yaml").read_bytes()
        if len(data) > community.YAML_LIMIT or hashlib.sha256(data).hexdigest() != row["yaml_sha256"]:
            return None
        results, errors = yamlgen.import_yaml(data.decode("utf-8"),{schema["slug"]:{"game":schema["game"]}},lambda _:schema)
        if errors or len(results) != 1:
            return None
        return {**results[0],"name":f"Upload · {row['display_name']} · {sha[:8]}"}
    except (OSError,UnicodeError,ValueError):
        return None


def capture_template(schema, ref):
    label, values, found = resolve_template(schema,ref)
    if not found:
        raise ValueError("Die gewählte Vorlage fehlt oder ist nicht mit dem APWorld-Schema kompatibel.")
    requirements = {}
    if ref.startswith("t:"):
        requirements = db.loads(db.query("SELECT requirements FROM templates WHERE id=?",(int(ref[2:]),),one=True)["requirements"])
    elif ref.startswith("c:"):
        requirements = uploaded_preset(schema,ref[2:])["requires"]
    return db.dumps({"ref":ref,"game":schema["slug"],"label":label,"values":values,"requires":requirements})


def entry_preset(schema, entry):
    if entry["template_snapshot"]:
        snapshot = db.loads(entry["template_snapshot"])
        if snapshot.get("ref") == entry["template_ref"] and snapshot.get("game") == entry["game"]:
            return snapshot["label"],snapshot["values"],True,snapshot.get("requires",{})
        return "Ungültiger Vorlagen-Snapshot",{},False,{}
    label,values,found = resolve_template(schema,entry["template_ref"])
    requirements = db.loads(capture_template(schema,entry["template_ref"]))["requires"] if found else {}
    return label,values,found,requirements


def can_edit_template(row) -> bool:
    return g.user["is_admin"] or row["created_by"] == g.user["id"]


def template_info(template):
    return {"ref": template["ref"], "name": i18n.t(template["name"]) if template['ref']=='default' else template["name"], "source": template["source"],
            "description": template["description"], "summary": template["summary"],
            "is_default": template["is_default"], "compatible": not bool(template["errors"])}


def templates_for(schema: dict) -> list[dict]:
    slug = schema["slug"]
    default_ref = group_default_ref(slug)
    result = [{"ref": "default", "name": "Spiel-Standard", "source": "APWorld",
               "description": "Die Voreinstellungen dieses Spiels, ohne zusätzliche Vorlage. Gespeicherte Profilwerte werden automatisch berücksichtigt.", "values": {}}]
    for name, values in schema["presets"].items():
        result.append({"ref": f"preset:{name}", "name": name, "source": "APWorld-Preset", "description": "",
                       "values": values})
    rows = db.query(
        "SELECT t.*, u.username FROM templates t LEFT JOIN users u ON u.id = t.created_by "
        "WHERE t.game = ? AND (t.shared = 1 OR t.created_by = ?) ORDER BY t.shared DESC, t.name",
        (slug, g.user["id"]))
    for row in rows:
        result.append({"ref": f"t:{row['id']}", "id": row["id"], "name": row["name"],
                       "source": "Gruppe" if row["shared"] else "Persönlich", "owner": row["username"],
                       "description": row["description"], "values": db.loads(row["vals"]),
                       "editable": can_edit_template(row), "updated_at": row["updated_at"],
                       "has_source":bool(row["source_yaml"]),"source_hash":row["source_sha256"],
                       "requires":db.loads(row["requirements"]),
                       "unavailable":bool(row["immutable"] and not resolve_template(schema,f"t:{row['id']}")[2])})
        result[-1]["editable"] = bool(result[-1]["editable"] and not row["immutable"])
    for row in db.query("SELECT sha256,display_name FROM community_games WHERE module=? AND yaml_file=sha256",(slug,)):
        preset = uploaded_preset(schema,row["sha256"])
        if preset:
            result.append({"ref":"c:"+row["sha256"],"name":preset["name"],"source":"Upload",
                           "description":"Unveränderte hochgeladene YAML-Vorlage", "values":preset["values"],"requires":preset["requires"]})
        else:
            result.append({"ref":"c:"+row["sha256"],"name":"Upload · "+row["display_name"],"source":"Upload",
                           "description":"Original-YAML bleibt in der Spielebibliothek herunterladbar.","values":{},"unavailable":True})
    for t in result:
        generated_description = not t['ref'].startswith('t:')
        t["summary"] = yamlgen.summarize(schema, t["values"])
        if not t["description"]:
            generated_description = True
            t["description"] = (f"{len(t['summary'])} Abweichungen vom Spiel-Standard. Die konkreten Werte stehen unten."
                                if t["summary"] else "Diese Vorlage entspricht dem Spiel-Standard.")
        if generated_description:
            t['description']=i18n.t(t['description'])
        t['source']=i18n.t(t['source'])
        t["is_default"] = t["ref"] == default_ref
        t["errors"] = yamlgen.validate_values(schema,t["values"])
        t["errors"].update(yamlgen.validate_requirements(schema,t.get("requires",{}),ap_bridge.index().get("ap_version","0.0.0")))
        if t.get("unavailable"):
            t["errors"]["_source"] = "Die Originalvorlage fehlt, wurde verändert oder passt nicht zum APWorld-Schema."
    result.sort(key=lambda t: not t["is_default"])
    return result


def open_sessions():
    return db.query("SELECT * FROM sessions WHERE locked=0 ORDER BY id DESC")


def user_values(schema: dict, template_values: dict, user, lobby_values=None) -> dict:
    overrides = yamlgen.global_overrides_for(schema, db.loads(user["overrides"]))
    return yamlgen.effective_values(schema, template_values, overrides, lobby_values)


def session_entries(session_id: int) -> list[dict]:
    rows = db.query(
        "SELECT e.*, u.username, u.slot_name, u.overrides FROM entries e JOIN users u ON u.id = e.user_id "
        "WHERE e.session_id = ? ORDER BY e.id", (session_id,))
    entries = [dict(r) for r in rows]
    slots = yamlgen.assign_slot_names(entries)
    games = ap_bridge.index()["games"]
    active = {v["module"]:v["sha256"] for v in ap_bridge.list_apworld_versions() if v["active"]}
    for e in entries:
        e["slot"] = slots[e["id"]]
        schema = ap_bridge.schema(e["game"])
        e["installed"] = e["game"] in games and schema is not None
        e["_schema"] = schema
        e["game_name"] = games.get(e["game"], {}).get("game", e["game"])
        e["game_version"] = (schema or {}).get("version", "")
        e["active_world_sha"] = active.get(e["game"], "")
        e["requested_world_sha"] = e["selected_apworld_sha"] or e["active_world_sha"]
        e["world_error"] = ap_bridge.world_error(e["game"],e["requested_world_sha"])
        e["schema_fingerprint"] = hashlib.sha256(db.dumps(schema or {}).encode("utf-8")).hexdigest()
        e["requirements"] = {}
        if e["installed"]:
            e["template_label"], tvalues, e["template_found"], e["requirements"] = entry_preset(schema,e)
            e["values"] = user_values(schema,tvalues,e,db.loads(e["option_overrides"]))
        else:
            e["template_label"], e["values"], e["template_found"] = "–", {}, False
        e["ready_valid"] = bool(e["ready"] and e["ready_hash"]
            and e["ready_hash"] == slot_fingerprint(e)
            and not e["world_error"])
    return entries


def session_yamls(entries: list[dict]) -> list[tuple[str, str]]:
    ap_version = ap_bridge.index().get("ap_version", "0.0.0")
    files = []
    for e in entries:
        if not e["installed"]:
            continue
        schema = e.get("_schema") or ap_bridge.schema(e["game"])
        text = entry_yaml(e,schema,ap_version)
        files.append((f"{e['slot']}.yaml", text))
    return files


def entry_yaml(entry,schema,ap_version):
    return yamlgen.player_yaml(entry["slot"],schema,entry["values"],
                              f"{schema['game']} – {entry['template_label']}",ap_version,entry.get("requirements",{}))


def get_session(session_id: int):
    row = db.query("SELECT * FROM sessions WHERE id = ?", (session_id,), one=True)
    if row is None:
        abort(404)
    return row


def can_manage_session(row) -> bool:
    return g.user["is_admin"] or row["created_by"] == g.user["id"]



def slot_fingerprint(entry: dict) -> str:
    record = {
        "slot": entry["slot"], "game": entry["game"],
        "values": entry.get("values", {}),
        "game_version": entry.get("game_version", ""),
        "world_sha256": entry.get("requested_world_sha") or "",
        "template_snapshot":entry.get("template_snapshot", ""),
        "requires":entry.get("requirements",{}),
        "schema":entry.get("schema_fingerprint",""),
    }
    raw = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
