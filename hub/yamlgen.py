"""Option values: form parsing, layering, YAML export and import. No Flask, no database."""
import re
import math
from copy import deepcopy

import yaml

from .config import SLOT_NAME_MAX

SCALAR_KINDS = {"toggle", "choice", "textchoice", "range", "text"}
TRUE_WORDS = {"on", "1", "true", "yes", "enabled"}
FALSE_WORDS = {"off", "0", "false", "none", "null", "no", "disabled"}
# Options a player may pin for every game they play (profile page).
GLOBAL_OVERRIDE_KEYS = {"death_link": "toggle", "progression_balancing": "range"}


class _Loader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in seen:
                    raise ValueError(f"Doppelter YAML-Schlüssel: {key}")
                seen.add(key)
            except TypeError as exc:
                raise ValueError("YAML-Schlüssel müssen einfache Werte sein.") from exc
        return super().construct_mapping(node, deep=deep)


def json_value(value, ancestors=None, budget=None):
    """Preserve supported YAML values across JSON storage, rejecting lossy conversions."""
    ancestors = set() if ancestors is None else ancestors
    budget = [0] if budget is None else budget
    budget[0] += 1
    if budget[0] > 100000 or len(ancestors) > 100:
        raise ValueError("Die YAML-Struktur ist zu groß oder zu tief verschachtelt.")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise ValueError("NaN und unendliche Zahlen sind nicht erlaubt.")
    if not isinstance(value, (list, dict)):
        raise ValueError("Nicht unterstützter YAML-Wert. Listen, Zuordnungen und einfache Werte verwenden.")
    if id(value) in ancestors:
        raise ValueError("Rekursive YAML-Verweise sind nicht erlaubt.")
    parents = ancestors | {id(value)}
    if isinstance(value, list):
        return [json_value(v, parents,budget) for v in value]
    result = {}
    for key, item in value.items():
        if not isinstance(key, (str, int, bool)):
            raise ValueError("YAML-Schlüssel müssen Text, ganze Zahlen oder An/Aus-Werte sein.")
        name = str(key).lower() if isinstance(key, bool) else str(key)
        if name in result:
            raise ValueError(f"Mehrdeutiger YAML-Schlüssel: {name}")
        result[name] = json_value(item, parents,budget)
    return result


def options_by_key(schema: dict) -> dict:
    return {opt["key"]: opt for opt in schema["options"]}


def _same(opt: dict, a, b) -> bool:
    if opt["kind"] == "set" and isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def is_weighted(opt: dict, value) -> bool:
    """A dict for a single-value option is AP's weight syntax ({easy: 30, hard: 70})."""
    return opt["kind"] in SCALAR_KINDS and isinstance(value, (dict,list)) and opt.get("supports_weighting",True)


def raw_mode(opt,value):
    return (opt["kind"] == "raw" or is_weighted(opt,value)
            or (opt["kind"] == "range" and isinstance(value,str))
            or (opt["kind"] == "toggle" and not isinstance(value,bool))
            or (opt["kind"] == "choice" and (not isinstance(value,str) or value not in dict(opt.get("choices") or [])))
            or (opt["kind"] == "list" and isinstance(value,list) and any(isinstance(v,(list,dict)) for v in value)))


# --- Layering ----------------------------------------------------------------------------------

def layer(schema: dict, *layers: dict) -> dict:
    """Resolve layers in order, preserving explicit defaults and unknown keys for validation."""
    return effective_values(schema,*layers)


def effective_values(schema, *layers):
    """AP defaults < template < profile < lobby; never silently discard unknown keys."""
    result = {opt["key"]: deepcopy(opt.get("default")) for opt in schema["options"]}
    for values in layers:
        result.update(deepcopy(values or {}))
    return result


def global_overrides_for(schema: dict, overrides: dict) -> dict:
    opts = options_by_key(schema)
    return {k: v for k, v in (overrides or {}).items()
            if k in opts and opts[k]["kind"] == GLOBAL_OVERRIDE_KEYS.get(k)
            }


# --- Slot names --------------------------------------------------------------------------------

def clean_slot_name(name: str) -> str:
    name = re.sub(r"[{}\[\]:,#&*!|<>'\"%@`/\\?\x00-\x1f\x7f]", "", name).strip().rstrip(". ")
    if re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",name):
        name = "_" + name
    return name[:SLOT_NAME_MAX].rstrip(". ") or "Player"


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


def player_yaml(slot: str, schema: dict, values: dict, description: str, ap_version: str, requirements=None) -> str:
    values = effective_values(schema, values)
    errors = validate_values(schema, values)
    if errors:
        raise ValueError("; ".join(f"{key}: {error}" for key, error in errors.items()))
    errors.update(validate_requirements(schema,requirements or {},ap_version))
    if errors:
        raise ValueError("; ".join(f"{key}: {error}" for key,error in errors.items()))
    requires = deepcopy(requirements or {})
    requires["version"] = ap_version
    if schema.get("version") and schema["version"] != "0.0.0":
        requires.setdefault("game",{})[schema["game"]] = {"min":schema["version"],"max":schema["version"]}
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
        return "gewichtet: " + (", ".join(f"{k} {w}" for k, w in value.items()) if isinstance(value,dict) else ", ".join(map(str,value)))
    kind = opt["kind"]
    if kind == "toggle":
        return "an" if value is True else "aus" if value is False else str(value)
    if kind in ("choice", "textchoice"):
        return dict(opt["choices"]).get(value, str(value)) if isinstance(value, (str,int,bool)) else dump(value).strip()
    if kind == "range":
        names = {v: k for k, v in (opt.get("special") or {}).items()}
        return f"{value} ({names[value]})" if isinstance(value,(str,int)) and value in names else str(value)
    if kind in ("set", "list"):
        return ", ".join(map(str, value)) if value else "–"
    if kind == "counter" and isinstance(value, dict):
        return ", ".join(f"{k} ×{v}" for k, v in value.items()) if value else "–"
    return dump(value).strip()


def summarize(schema: dict, values: dict) -> list[tuple[str, str]]:
    opts = options_by_key(schema)
    return [(opts[k]["name"], display_value(opts[k], v)) for k, v in values.items()
            if k in opts and not _same(opts[k],v,opts[k].get("default"))]


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
        text = form.get(f"y.{key}", form.get(field, "")).strip()
        if not text:
            return opt.get("default"), None
        try:
            value = json_value(yaml.load(text, Loader=_Loader))
        except (yaml.YAMLError, ValueError, RecursionError) as e:
            return None, f"Ungültiges YAML: {e}"
        if kind in SCALAR_KINDS and isinstance(value, dict):
            errors = validate_values({"options": [opt], "items": [], "locations": []}, {key: value})
            if key in errors:
                return None, errors[key]
        return value, None

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


def parse_form(schema: dict, form, previous: dict, *, keep_defaults=False) -> tuple[dict, dict]:
    """Only fields listed in _r (rendered) are read; hidden ones keep their previous value."""
    opts = options_by_key(schema)
    rendered = set(form.getlist("_r"))
    values = {k: v for k, v in (previous or {}).items() if k not in rendered}
    errors = {}
    for key in rendered:
        if key not in opts:
            errors[key] = "Diese Option existiert in der aktuellen APWorld nicht."
            continue
        value, error = parse_field(opts[key], form, schema)
        if error:
            errors[key] = error
            values[key] = previous.get(key) if previous else None
        elif keep_defaults or not _same(opts[key], value, opts[key].get("default")):
            values[key] = value
    errors.update(validate_values(schema, values))
    return values, errors


def parse_lobby_form(schema, form, previous, baseline):
    inherited = set(form.getlist("_inherit")) & set(form.getlist("_r"))
    submitted = form.copy()
    submitted.setlist("_r",[key for key in form.getlist("_r") if key not in inherited])
    before = effective_values(schema,baseline,previous)
    for key in inherited:
        if key in baseline:
            before[key] = deepcopy(baseline[key])
    desired, errors = parse_form(schema, submitted, before, keep_defaults=True)
    values = deepcopy(previous)
    opts = options_by_key(schema)
    for key in set(form.getlist("_r")):
        if key in errors or key not in opts:
            continue
        if key in inherited or _same(opts[key], desired[key], baseline.get(key)):
            values.pop(key, None)
        else:
            values[key] = desired[key]
    errors.update(validate_values(schema, effective_values(schema, baseline, values)))
    return values, errors


# --- Independent pre-flight validation -------------------------------------------------------

def validate_values(schema: dict, values: dict) -> dict[str, str]:
    """Validate all supplied options, including weighted scalar values.

    Deep game-specific validation still belongs to Archipelago's own generator.
    This check catches obvious input errors before starting that process.
    """
    opts = options_by_key(schema)
    errors = {}
    for key, value in (values or {}).items():
        opt = opts.get(key)
        if opt is None:
            errors[key] = "Diese Option existiert in der aktuellen APWorld nicht."
            continue
        kind = opt["kind"]
        try:
            json_value(value)
        except (ValueError,RecursionError) as exc:
            errors[key] = str(exc)
            continue
        if is_weighted(opt, value):
            if not value:
                errors[key] = "Mindestens ein Gewicht größer als 0 erforderlich."
                continue
            if isinstance(value,list):
                for candidate in value:
                    error = scalar_error(opt,candidate)
                    if error:
                        errors[key] = error
                continue
            if any(type(w) is not int or w < 0 for w in value.values()):
                errors[key] = "Gewichte müssen nichtnegative ganze Zahlen sein."
                continue
            if not any(w > 0 for w in value.values()):
                errors[key] = "Alle Gewichte sind 0. Mindestens ein Wert muss positiv sein."
                continue
            for candidate in value:
                error = scalar_error(opt,candidate)
                if error:
                    errors[key] = error
            continue
        if kind in SCALAR_KINDS:
            error = scalar_error(opt,value)
            if error:
                errors[key] = error
        elif kind in ("set", "list") and not isinstance(value, list):
            errors[key] = "Liste erwartet."
        elif kind in ("set", "list") and isinstance(value, list):
            unknown = _check_names(opt, value, schema)
            if unknown:
                errors[key] = unknown[0]
        elif kind == "counter" and not isinstance(value, dict):
            errors[key] = "Wörterbuch mit Anzahlen erwartet."
        elif kind == "counter" and isinstance(value, dict):
            unknown = _check_names(opt, value, schema)
            if unknown:
                errors[key] = unknown[0]
            elif any(not isinstance(v, int) or isinstance(v, bool) or v < (opt.get("min") or 0)
                     or (opt.get("max") is not None and v > opt["max"]) for v in value.values()):
                errors[key] = "Ungültige Anzahl."
        elif kind == "raw":
            container = opt.get("container") or ("dict" if isinstance(opt.get("default"),dict)
                                                  else "list" if isinstance(opt.get("default"),list) else "")
            if container == "dict" and not isinstance(value,dict):
                errors[key] = "Eine YAML-Zuordnung (Schlüssel: Wert) wird erwartet."
            elif container == "list" and not isinstance(value,list):
                errors[key] = "Eine YAML-Liste wird erwartet."
    return errors


def scalar_error(opt,value):
    kind = opt["kind"]
    if isinstance(value,(dict,list)) or value is None:
        return "Ein einzelner gültiger Wert wird erwartet."
    text = str(value).lower()
    if kind == "toggle":
        return "Bitte An oder Aus auswählen." if text not in TRUE_WORDS | FALSE_WORDS | {"random"} else ""
    if kind == "choice":
        choices = dict(opt.get("choices") or [])
        aliases = opt.get("aliases",{})
        numeric = type(value) is int and text in opt.get("choice_values",{})
        if text not in choices and text not in aliases and text != "random" and not numeric:
            return "Unbekannter Auswahlwert."
    elif kind in ("text","textchoice"):
        if not isinstance(value,str):
            return "Text wird erwartet."
    elif kind == "range":
        special = opt.get("special") or {}
        if text in special or text in ("random","random-low","random-high","random-middle","default","high","low"):
            return ""
        if text.startswith("random-range-"):
            match = re.fullmatch(r"random-range-(?:(?:low|middle|high)-)?(-?\d+)-(-?\d+)",text)
            if match and all(opt["min"] <= int(v) <= opt["max"] for v in match.groups()):
                return ""
            return "Ungültiger Zufallsbereich."
        if isinstance(value,bool) or not re.fullmatch(r"-?\d+",str(value)):
            return "Ganze Zahl erforderlich."
        number = int(value)
        if not opt["min"] <= number <= opt["max"] and number not in special.values():
            return "Zahl außerhalb des erlaubten Bereichs."
    return ""


# --- YAML import -------------------------------------------------------------------------------

def import_yaml(text: str, games: dict, load_schema) -> tuple[list[dict], list[str]]:
    """games: {slug: {game: name}}. Returns ([{slug, game, name, values, warnings}], errors)."""
    by_name = {info["game"]: slug for slug, info in games.items()}
    results, errors = [], []
    try:
        docs = [json_value(d) for d in yaml.load_all(text,Loader=_Loader) if d is not None]
    except (yaml.YAMLError,ValueError,RecursionError) as e:
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
        unsupported = set(doc) - {"name","description","game","requires",*game_names}
        if unsupported:
            errors.append("Nicht unterstützte YAML-Bereiche: " + ", ".join(sorted(unsupported)) + ". Es wurde nichts daraus übernommen.")
            continue

        for game in game_names:
            slug = by_name.get(game)
            if not slug:
                errors.append(f"„{game}“ ist auf dem Server nicht installiert – erst die APWorld hochladen.")
                continue
            schema = load_schema(slug)
            if not schema:
                errors.append(f"{game}: Das APWorld-Schema fehlt.")
                continue
            opts = options_by_key(schema)
            section = doc.get(game,{})
            if not isinstance(section,dict):
                errors.append(f"{game}: Die Spieloptionen müssen eine YAML-Zuordnung sein.")
                continue
            values = deepcopy(section)
            issues = validate_values(schema,values)
            if not isinstance(doc.get("requires",{}),dict):
                issues["requires"] = "Die Versionsanforderungen müssen eine Zuordnung sein."
            if issues:
                errors.extend(f"{game} – {key}: {message}" for key,message in issues.items())
                continue
            warnings = [f"„{opts[key]['name']}“ bleibt unverändert gewichtet." for key,value in values.items()
                        if is_weighted(opts[key],value)]
            description = doc.get("description")
            results.append({
                "slug": slug,
                "game": game,
                "name": description if isinstance(description, str) and description.strip() else f"Import ({doc.get('name', '?')})",
                "values": values,
                "warnings": warnings,
                "requires": doc.get("requires",{}),
            })
    return results, errors


def validate_requirements(schema, requirements, ap_version):
    errors = {}
    def version(value):
        if not isinstance(value,str) or not re.fullmatch(r"\d+\.\d+\.\d+",value):
            raise ValueError("Version muss als Text im Format 0.0.0 angegeben werden.")
        return tuple(map(int,value.split(".")))
    try:
        if set(requirements) - {"version","game"}:
            raise ValueError("Nicht unterstützte Versions-/Plando-Anforderungen.")
        if "version" in requirements and version(requirements["version"]) > version(ap_version):
            raise ValueError("Die Vorlage benötigt eine neuere Archipelago-Version.")
        games = requirements.get("game",{})
        if not isinstance(games,dict):
            raise ValueError("requires.game muss eine Zuordnung sein.")
        for game,limits in games.items():
            bounds = {"min":limits} if isinstance(limits,str) else limits
            if not isinstance(bounds,dict) or not bounds or set(bounds) - {"min","max"}:
                raise ValueError("World-Version benötigt min und/oder max.")
            for bound,value in bounds.items():
                parsed = version(value)
                if game == schema["game"]:
                    actual = version(schema.get("version") or "0.0.0")
                    if (bound == "min" and actual < parsed) or (bound == "max" and actual > parsed):
                        raise ValueError(f"{game}: aktive APWorld {schema.get('version')} ist nicht mit der Vorlage kompatibel.")
    except (ValueError,TypeError) as exc:
        errors["requires"] = str(exc)
    return errors
