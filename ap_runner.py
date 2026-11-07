"""Runs inside the Archipelago source tree (cwd = AP source, AP's Python env).

The hub never imports Archipelago itself; it calls this script as a subprocess:

    python ap_runner.py extract  --out <dir> [--hide mod1,mod2]
    python ap_runner.py generate --players <dir> --out <dir> [--hide ...] [--spoiler N] [--race]

--hide lists built-in world folders to skip, so an uploaded .apworld with the same
module name replaces the built-in version instead of being ignored.
"""
import argparse
import json
import logging
import os
import sys
from inspect import cleandoc


def hide_builtin_worlds(names: set[str]) -> None:
    """Filter os.scandir() on AP's worlds/ folder while the world loader indexes it."""
    if not names:
        return
    worlds_dir = os.path.normcase(os.path.abspath("worlds"))
    real_scandir = os.scandir

    class _Listing(list):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def close(self):
            pass

    def scandir(path="."):
        it = real_scandir(path)
        if os.path.normcase(os.path.abspath(os.fspath(path))) != worlds_dir:
            return it
        with it:
            return _Listing(e for e in it if os.path.splitext(e.name)[0] not in names)

    os.scandir = scandir


def jsonable(value):
    if isinstance(value, (set, frozenset)):
        return sorted(jsonable(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def describe_option(key, option, group, Options):
    doc = cleandoc(option.__doc__) if option.__doc__ else ""
    info = {
        "key": key,
        "name": getattr(option, "display_name", key.replace("_", " ").title()),
        "doc": doc,
        "group": group,
        "simple": bool(Options.Visibility.simple_ui & option.visibility),
    }
    default = getattr(option, "default", None)

    if issubclass(option, Options.Toggle):
        info.update(kind="toggle", default=bool(default) if not isinstance(default, str) else default)
    elif issubclass(option, Options.Choice):
        choices = [[name, option.get_option_name(value)] for value, name in option.name_lookup.items()]
        if isinstance(default, int) and default in option.name_lookup:
            default = option.name_lookup[default]
        info.update(kind="textchoice" if issubclass(option, Options.TextChoice) else "choice",
                    choices=choices, default=default)
    elif issubclass(option, Options.Range):
        info.update(kind="range", min=option.range_start, max=option.range_end, default=default)
        if issubclass(option, Options.NamedRange) and option.special_range_names:
            info["special"] = dict(option.special_range_names)
    elif issubclass(option, Options.FreeText):
        info.update(kind="text", default=default)
    elif issubclass(option, Options.OptionCounter):
        info.update(kind="counter", default=jsonable(default), min=option.min, max=option.max)
    elif issubclass(option, Options.OptionDict):
        info.update(kind="raw", default=jsonable(default))
    elif issubclass(option, Options.ItemLinks):
        info.update(kind="raw", default=jsonable(default))
    elif issubclass(option, (Options.OptionSet, Options.OptionList)):
        info.update(kind="set" if issubclass(option, Options.OptionSet) else "list", default=jsonable(default))
    else:
        info.update(kind="raw", default=jsonable(default))

    if info["kind"] in ("set", "list", "counter"):
        info["valid_keys"] = sorted(map(str, option.valid_keys)) if option.valid_keys else []
        info["items"] = bool(option.verify_item_name)
        info["locations"] = bool(option.verify_location_name)
    return info


def normalize_preset_value(option, value, Options):
    if value == "random":
        return value
    try:
        parsed = option.from_any(value)
    except Exception:
        return jsonable(value)
    if isinstance(parsed, Options.Toggle):
        return bool(parsed.value)
    if isinstance(parsed, Options.Choice):
        return parsed.current_key
    return jsonable(parsed.value)


def extract(out_dir: str) -> None:
    import Options
    import Utils
    from worlds import AutoWorldRegister, failed_world_loads

    os.makedirs(out_dir, exist_ok=True)
    index = {"ap_version": Utils.__version__, "games": {}, "failed": failed_world_loads}

    for game, world in sorted(AutoWorldRegister.world_types.items()):
        if world.hidden:
            continue
        module = world.__module__.split(".")[1]
        try:
            options = []
            groups = Options.get_option_groups(world, visibility_level=Options.Visibility.template)
            for group, group_options in groups.items():
                for key, option in group_options.items():
                    options.append(describe_option(key, option, group, Options))

            hints = world.options_dataclass.type_hints
            presets = {
                preset_name: {k: normalize_preset_value(hints[k], v, Options) for k, v in preset.items() if k in hints}
                for preset_name, preset in world.web.options_presets.items()
            }
            version = world.world_version.as_simple_string() if world.world_version else "0.0.0"
            source_file = os.path.abspath(sys.modules[world.__module__].__file__)
            schema = {
                "game": game,
                "slug": module,
                "version": version,
                "custom": not source_file.startswith(os.path.abspath("worlds") + os.sep)
                          or ".apworld" in source_file,
                "options": options,
                "presets": presets,
                "items": sorted(world.item_names) + sorted(world.item_name_groups),
                "locations": sorted(world.location_names) + sorted(world.location_name_groups),
            }
        except Exception as e:  # one broken world must not break the whole index
            index["failed"][game] = f"Optionen konnten nicht gelesen werden: {e!r}"
            continue

        with open(os.path.join(out_dir, f"{module}.json"), "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False)
        index["games"][module] = {"game": game, "version": version, "custom": schema["custom"]}

    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"Extracted {len(index['games'])} games, {len(index['failed'])} failed.")


def generate(players: str, out: str, spoiler: int, race: bool) -> None:
    sys.argv = ["Generate.py", "--player_files_path", players, "--outputpath", out,
                "--spoiler", str(spoiler)] + (["--race"] if race else [])
    import Utils
    Utils.init_logging("Generate_hub", loglevel="info")  # AP's own setup, also logs to stdout for the hub

    import Generate
    from Main import main as ERmain

    args, seed = Generate.main()
    multiworld = ERmain(args, seed)
    if race:
        # Item placement information must not reveal race spoilers.
        print("Race mode: item distribution analytics disabled.")
        return
    try:
        from hub.stats import aggregate_placements
        from BaseClasses import ItemClassification
        player_ids = sorted(multiworld.player_ids)
        players = [{"id": p, "name": multiworld.get_player_name(p),
                    "game": multiworld.game[p]} for p in player_ids]
        placements = []
        details = []
        player_set = set(player_ids)
        for loc in multiworld.get_filled_locations():
            if type(loc.address) is not int or not loc.item or type(loc.item.code) is not int:
                continue
            item = loc.item
            classification = item.classification
            if classification & ItemClassification.progression:
                kind = "progression"
            elif classification & ItemClassification.trap:
                kind = "trap"
            elif classification & ItemClassification.useful:
                kind = "useful"
            else:
                kind = "filler"
            placements.append((loc.player, item.player, kind))
            if loc.player in player_set and item.player in player_set:
                details.append({
                    "finder": loc.player, "recipient": item.player, "category": kind,
                    "location_id": loc.address, "item_id": item.code,
                    "location": loc.name, "item": item.name,
                })
        result = aggregate_placements(players, placements)
        with open(os.path.join(out, "item_distribution.json"), "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, indent=2)
        print("Real item distribution statistics written.")
        with open(os.path.join(out, "item_placements.json"), "w", encoding="utf-8") as fp:
            json.dump({"source": result["source"], "placements": details}, fp, ensure_ascii=False)
    except Exception:
        # Successful seed generation must not be discarded for analytics errors.
        logging.exception("Item distribution analytics unavailable for this seed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["extract", "generate"])
    parser.add_argument("--out", required=True)
    parser.add_argument("--players")
    parser.add_argument("--hide", default="")
    parser.add_argument("--spoiler", type=int, default=1)
    parser.add_argument("--race", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, os.getcwd())
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    hide_builtin_worlds({n for n in args.hide.split(",") if n})

    if args.command == "extract":
        extract(args.out)
    else:
        generate(args.players, args.out, args.spoiler, args.race)


if __name__ == "__main__":
    main()
