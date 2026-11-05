"""Option values: form parsing, layering, YAML export and import. No Flask, no database."""
import re

import yaml

from .config import SLOT_NAME_MAX

SCALAR_KINDS = {"toggle", "choice", "textchoice", "range", "text"}
TRUE_WORDS = {"on", "1", "true", "yes", "enabled"}
FALSE_WORDS = {"off", "0", "false", "none", "null", "no", "disabled"}
# Options a player may pin for every game they play (profile page).
GLOBAL_OVERRIDE_KEYS = {"death_link": "toggle", "progression_balancing": "range"}


def options_by_key(schema: dict) -> dict:
    return {opt["key"]: opt for opt in schema["options"]}


def _same(opt: dict, a, b) -> bool:
    if opt["kind"] == "set" and isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def is_weighted(opt: dict, value) -> bool:
    """A dict for a single-value option is AP's weight syntax ({easy: 30, hard: 70})."""
    return opt["kind"] in SCALAR_KINDS and isinstance(value, dict)


# --- Layering ----------------------------------------------------------------------------------

def layer(schema: dict, *layers: dict) -> dict:
    """APWorld default < template < personal overrides. Returns only values that differ from default."""
    opts = options_by_key(schema)
    result = {}
    for values in layers:
        for key, value in (values or {}).items():
            if key in opts:
                result[key] = value
    return {k: v for k, v in result.items() if not _same(opts[k], v, opts[k].get("default"))}


def global_overrides_for(schema: dict, overrides: dict) -> dict:
    opts = options_by_key(schema)
    return {k: v for k, v in (overrides or {}).items()
            if k in opts and opts[k]["kind"] == GLOBAL_OVERRIDE_KEYS.get(k)
            and (opts[k]["kind"] != "range" or opts[k]["min"] <= v <= opts[k]["max"])}


# --- Slot names --------------------------------------------------------------------------------

def clean_slot_name(name: str) -> str:
    name = re.sub(r"[{}\[\]:,#&*!|>'\"%@`]", "", name).strip()
    return name[:SLOT_NAME_MAX] or "Player"


def assign_slot_names(entries: list[dict]) -> dict[int, str]:
    """entries: [{id, slot_name}] in join order. Duplicates get 2, 3, ... appended within 16 chars."""
    taken: set[str] = set()
    result = {}
    for entry in entries:
        base = clean_slot_name(entry["slot_name"])
        name, n = base, 1
        while name.casefold() in taken:
            n += 1
            suffix = str(n)
            name = base[:SLOT_NAME_MAX - len(suffix)] + suffix
        taken.add(name.casefold())
        result[entry["id"]] = name
    return result


# --- YAML export -------------------------------------------------------------------------------

class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_presenter)


def dump(data) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False)


def player_yaml(slot: str, schema: dict, values: dict, description: str, ap_version: str) -> str:
    requires = {"version": ap_version}
    if schema.get("version") and schema["version"] != "0.0.0":
        requires["game"] = {schema["game"]: schema["version"]}
    doc = {
        "name": slot,
        "description": description,
        "game": schema["game"],
        "requires": requires,
        schema["game"]: values,
    }
    return "# Erstellt mit AP YAML Hub\n" + dump(doc)


# --- Display -----------------------------------------------------------------------------------

def display_value(opt: dict, value) -> str:
    if is_weighted(opt, value):
        return "gewichtet: " + ", ".join(f"{k} {w}" for k, w in value.items())
    kind = opt["kind"]
    if kind == "toggle":
        return "an" if value is True else "aus" if value is False else str(value)
    if kind in ("choice", "textchoice"):
        return dict(opt["choices"]).get(value, str(value))
    if kind == "range":
        names = {v: k for k, v in (opt.get("special") or {}).items()}
        return f"{value} ({names[value]})" if value in names else str(value)
    if kind in ("set", "list"):
        return ", ".join(map(str, value)) if value else "–"
    if kind == "counter" and isinstance(value, dict):
        return ", ".join(f"{k} ×{v}" for k, v in value.items()) if value else "–"
    return dump(value).strip()


def summarize(schema: dict, values: dict) -> list[tuple[str, str]]:
    opts = options_by_key(schema)
    return [(opts[k]["name"], display_value(opts[k], v)) for k, v in values.items() if k in opts]


# --- Form parsing ------------------------------------------------------------------------------

def checkbox_mode(opt: dict) -> bool:
    return opt["kind"] in ("set", "list") and 0 < len(opt.get("valid_keys") or []) <= 200


def form_text(opt: dict, value) -> str:
    """Text shown in a textarea for list/counter/raw options."""
    if value is None:
        return ""
    if opt["kind"] in ("set", "list") and isinstance(value, list):
        return "\n".join(map(str, value))
    if opt["kind"] == "counter" and isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    return dump(value).strip() if not isinstance(value, str) else value


def _check_names(opt: dict, names, schema: dict) -> list[str]:
    allowed = set()
    if opt.get("valid_keys"):
        allowed |= set(opt["valid_keys"])
    if opt.get("items"):
        allowed |= set(schema["items"])
    if opt.get("locations"):
        allowed |= set(schema["locations"])
    if not allowed:
        return []
    unknown = [n for n in names if str(n) not in allowed and str(n).casefold() not in {a.casefold() for a in allowed}]
    return [f"Unbekannt: {', '.join(map(str, unknown[:10]))}"] if unknown else []


def parse_field(opt: dict, form, schema: dict):
    """Returns (value, error). Field names: o.<key>, raw-mode flag m.<key>=raw."""
    key, kind = opt["key"], opt["kind"]
    field = f"o.{key}"

    if form.get(f"m.{key}") == "raw" or kind == "raw":
        text = form.get(field, "").strip()
        if not text:
            return opt.get("default"), None
        try:
            return yaml.safe_load(text), None
        except yaml.YAMLError as e:
            return None, f"Ungültiges YAML: {e}"

    if kind == "toggle":
        return form.get(field) == "1", None

    if kind == "choice":
        value = form.get(field, "")
        if value not in dict(opt["choices"]):
            return None, f"Ungültige Auswahl: {value}"
        return value, None

    if kind == "textchoice":
        value = form.get(field, "").strip()
        lowered = value.lower()
        if lowered in dict(opt["choices"]):
            return lowered, None
        return (value, None) if value else (None, "Darf nicht leer sein.")

    if kind == "range":
        raw = form.get(field, "").strip()
        special = opt.get("special") or {}
        if raw.lower() in special:
            return special[raw.lower()], None
        try:
            value = int(raw)
        except ValueError:
            return None, f"Keine Zahl: {raw}"
        if not (opt["min"] <= value <= opt["max"]) and value not in special.values():
            return None, f"Muss zwischen {opt['min']} und {opt['max']} liegen."
        return value, None

    if kind == "text":
        return form.get(field, ""), None

    if kind in ("set", "list"):
        if checkbox_mode(opt):
            values = form.getlist(field)
        else:
            values = [line.strip() for line in form.get(field, "").splitlines() if line.strip()]
        if kind == "set":
            values = sorted(set(values), key=values.index)
        errors = _check_names(opt, values, schema)
        return values, (errors[0] if errors else None)

    if kind == "counter":
        result = {}
        for line in form.get(field, "").splitlines():
            if not line.strip():
                continue
            name, sep, count = line.rpartition(":")
            if not sep:
                name, count = line, "1"
            try:
                result[name.strip()] = int(count.strip())
            except ValueError:
                return None, f"„{line.strip()}“: Anzahl muss eine Zahl sein (Format: Name: Anzahl)."
        for name, count in result.items():
            if opt.get("min") is not None and count < opt["min"] or opt.get("max") is not None and count > opt["max"]:
                return None, f"„{name}“: Anzahl außerhalb des erlaubten Bereichs."
        errors = _check_names(opt, result, schema)
        return result, (errors[0] if errors else None)

    return None, f"Unbekannter Optionstyp {kind}"


def parse_form(schema: dict, form, previous: dict) -> tuple[dict, dict]:
    """Only fields listed in _r (rendered) are read; hidden ones keep their previous value."""
    opts = options_by_key(schema)
    rendered = set(form.getlist("_r"))
    values = {k: v for k, v in (previous or {}).items() if k in opts and k not in rendered}
    errors = {}
    for key in rendered:
        if key not in opts:
            continue
        value, error = parse_field(opts[key], form, schema)
        if error:
            errors[key] = error
            values[key] = previous.get(key) if previous else None
        elif not _same(opts[key], value, opts[key].get("default")):
            values[key] = value
    return {k: v for k, v in values.items() if v is not None}, errors


# --- YAML import -------------------------------------------------------------------------------

def _collapse_weights(opt: dict, value):
    """{hard: 50, easy: 0} -> hard. Real weighting (several >0) is kept as-is."""
    if not is_weighted(opt, value):
        return value
    active = [k for k, w in value.items() if isinstance(w, (int, float)) and w > 0]
    if len(active) != 1:
        return value
    choice = active[0]
    kind = opt["kind"]
    if kind == "toggle":
        if choice is True or str(choice).lower() in TRUE_WORDS:
            return True
        if choice is False or str(choice).lower() in FALSE_WORDS:
            return False
    if kind == "range":
        if isinstance(choice, int):
            return choice
        special = opt.get("special") or {}
        if str(choice).lower() in special:
            return special[str(choice).lower()]
        if str(choice).lower() == "default":
            return opt.get("default")
        return value
    if kind in ("choice", "textchoice"):
        return str(choice).lower() if str(choice).lower() in dict(opt["choices"]) else str(choice)
    return choice


def _normalize_plain(opt: dict, value):
    kind = opt["kind"]
    if kind == "toggle" and isinstance(value, str):
        if value.lower() in TRUE_WORDS:
            return True
        if value.lower() in FALSE_WORDS:
            return False
    if kind in ("choice", "textchoice") and isinstance(value, str) and value.lower() in dict(opt["choices"]):
        return value.lower()
    if kind == "set" and isinstance(value, dict):  # some YAMLs write sets as {name: weight}
        return [k for k, w in value.items() if w]
    return value


def import_yaml(text: str, games: dict, load_schema) -> tuple[list[dict], list[str]]:
    """games: {slug: {game: name}}. Returns ([{slug, game, name, values, warnings}], errors)."""
    by_name = {info["game"]: slug for slug, info in games.items()}
    results, errors = [], []
    try:
        docs = [d for d in yaml.safe_load_all(text) if d]
    except yaml.YAMLError as e:
        return [], [f"Die Datei ist kein gültiges YAML: {e}"]

    for doc in docs:
        if not isinstance(doc, dict):
            errors.append("Ein Dokument in der Datei ist keine YAML-Zuordnung und wurde übersprungen.")
            continue
        game_field = doc.get("game")
        if isinstance(game_field, dict):
            game_names = [g for g, w in game_field.items() if w]
        elif isinstance(game_field, str):
            game_names = [game_field]
        else:
            game_names = [k for k in doc if k in by_name]
        if not game_names:
            errors.append("Kein Spiel gefunden („game:“ fehlt).")
            continue

        for game in game_names:
            slug = by_name.get(game)
            if not slug:
                errors.append(f"„{game}“ ist auf dem Server nicht installiert – erst die APWorld hochladen.")
                continue
            schema = load_schema(slug)
            opts = options_by_key(schema)
            section = doc.get(game) or {}
            values, warnings = {}, []
            for key, value in section.items():
                if key not in opts:
                    warnings.append(f"Unbekannte Option „{key}“ ignoriert.")
                    continue
                value = _normalize_plain(opts[key], _collapse_weights(opts[key], value))
                if is_weighted(opts[key], value):
                    warnings.append(f"„{opts[key]['name']}“ ist gewichtet und wird so übernommen.")
                if not _same(opts[key], value, opts[key].get("default")):
                    values[key] = value
            description = doc.get("description")
            results.append({
                "slug": slug,
                "game": game,
                "name": description if isinstance(description, str) and description.strip() else f"Import ({doc.get('name', '?')})",
                "values": values,
                "warnings": warnings,
            })
    return results, errors
