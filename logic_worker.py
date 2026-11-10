"""One bounded UT evaluation in Archipelago's Python, never in Flask.

Uses the separately installed, hash-pinned Universal Tracker. Reads one JSON
request on stdin and writes one JSON result; all engine output goes to stderr.
"""
import contextlib
import json
import logging
import os
from pathlib import Path
import sys


class LogicError(Exception):
    """A safe, deliberately written user-facing failure."""


def evaluate(request):
    from ap_runner import hide_builtin_worlds
    hide_builtin_worlds(set(request.get("hide", [])))
    sys.path.insert(0, os.getcwd())
    # AP uses --nogui to prevent optional UI imports in tracker/game packages.
    sys.argv = [sys.argv[0], "--nogui"]
    import settings
    settings.no_gui = True
    settings.skip_autosave = True
    import worlds
    from worlds import WorldSource
    from worlds.AutoWorld import AutoWorldRegister
    from NetUtils import NetworkItem
    from Utils import __version__
    if request.get("ap_version") and request["ap_version"] != __version__:
        raise LogicError("Die Archipelago-Version passt nicht zum Seed-Snapshot.")
    if "worlds.tracker" not in sys.modules:
        from worlds.Files import APWorldContainer
        source = WorldSource(str(request["tracker"]), is_zip=True, relative=False)
        container = APWorldContainer(str(request["tracker"]))
        container.read()
        worlds.add_apworld_spec(source, container)
        if not source.load():
            raise LogicError("Universal Tracker konnte nicht geladen werden.")
    from worlds.tracker.TrackerCore import TrackerCore
    from worlds.tracker import UT_VERSION, TrackerWorld
    if UT_VERSION != "v0.3.3":
        raise LogicError("Eine andere Universal-Tracker-Version ist bereits installiert. Bitte die festgelegte Version verwenden.")
    # UserFolderPath otherwise opens a native folder chooser when UT's default
    # Players directory does not exist. Server workers must never open dialogs.
    TrackerWorld.settings.player_files_path = request["players"]
    cls = AutoWorldRegister.world_types.get(request["game"])
    if cls is None or getattr(cls, "disable_ut", False):
        raise LogicError("Diese APWorld unterstützt den Logik-Tracker nicht.")
    if request["game"] == "Skyward Sword" and not request.get("layout") and not (
            getattr(cls, "ut_can_gen_without_yaml", False) or callable(getattr(cls, "interpret_slot_data", None))):
        raise LogicError("Diese Skyward-Sword-APWorld kann die zufälligen Dungeon-, Start- und Zielregeln des Seeds nicht für UT rekonstruieren. Eine verlässliche In-Logic- oder Go-Mode-Anzeige ist damit nicht verfügbar.")
    if request["game"] in ("Hollow Knight", "Stardew Valley", "Bloodstained: Ritual of the Night", "Skyward Sword"):
        # HK's native client receives the resolved option values; use those
        # instead of rerolling weighted ranges from the original YAML.
        import yaml
        player_file = Path(request["players"]) / "player.yaml"
        original = yaml.safe_load(player_file.read_text(encoding="utf-8"))
        resolved = request["slot_data"].get("options") if request["game"] == "Hollow Knight" else request["slot_data"]
        if not isinstance(resolved, dict):
            raise LogicError("Die aufgelösten Hollow-Knight-Einstellungen fehlen.")
        original[request["game"]].update({key:value for key,value in resolved.items() if key in cls.options_dataclass.type_hints})
        if request.get("layout"):
            original[request["game"]].update({key.replace('-', '_'):value for key,value in request['layout']['Options'].items()
                if key.replace('-', '_') in cls.options_dataclass.type_hints})
        player_file.write_text(yaml.safe_dump(original), encoding="utf-8")
    from logic_adapters import prepare
    prepare(request["game"], cls, request)
    core = TrackerCore(logging.getLogger("HubLogic"), False, False)
    core.set_slot_params(request["game"], request["slot_id"], request["slot"], 0)
    # Older worlds require the immutable YAML from generation, newer worlds
    # reconstruct all randomized settings from their actual server slot data.
    if not getattr(cls, "ut_can_gen_without_yaml", False):
        core.run_generator(super_override_yaml_path=request["players"])
    core.initalize_tracker_core(cls, request["slot_data"])
    if core.tracker_disabled or core.multiworld is None or core.player_id is None or core.gen_error:
        raise LogicError("Universal Tracker kann die Regeln dieser Spielversion oder Einstellung nicht rekonstruieren.")
    world = core.get_current_world()
    if request["game"] == "Skyward Sword" and request.get('layout'):
        actual = {tuple(row) for row in world.entrances.entrance_mapping.output_entrance_mapping()}
        expected = {tuple(row) for row in request['layout']['Entrances']}
        if actual != expected:
            raise LogicError("Das rekonstruierte Skyward-Sword-Dungeonlayout passt nicht zum Slot-Patch.")
        if world.entrances.trial_connections != {trial:gate for gate,trial in request['layout']['Trial Entrances'].items()}:
            raise LogicError("Das rekonstruierte Trial-Layout passt nicht zum Slot-Patch.")
    if request["game"] == "Hollow Knight":
        # Native HK exposes these rolled values but does not interpret them for
        # UT. Its logic mixin reads the world/location attributes dynamically.
        data = request["slot_data"]
        costs = data.get("notch_costs")
        if not isinstance(costs, list) or len(costs) != len(world.charm_costs) or any(type(v) is not int or v < 0 for v in costs):
            raise LogicError("Hollow Knight meldet keine vollständigen tatsächlichen Talisman-Kosten.")
        world.charm_costs = costs
        shop_costs = data.get("location_costs")
        if not isinstance(shop_costs, dict):
            raise LogicError("Hollow Knight meldet keine tatsächlichen Check-Kosten.")
        for name, prices in shop_costs.items():
            if not isinstance(prices, dict) or any(type(v) is not int or v < 0 for v in prices.values()):
                raise LogicError("Die Hollow-Knight-Kosten sind unvollständig.")
            if name in core.multiworld.regions.location_cache[core.player_id]:
                core.multiworld.get_location(name, core.player_id).costs = prices
            elif name in set(request.get("location_names", {}).get(str(i)) for i in request["missing"] + request["checked"]):
                raise LogicError("Ein tatsächlicher Hollow-Knight-Shop fehlt im Modell.")
        if type(data.get("grub_count")) is int:
            world.grub_count = data["grub_count"]
            world.grub_player_count = {core.player_id: data["grub_count"]}
    missing = set(request["missing"])
    checked = set(request["checked"])
    known = {loc.address for loc in core.multiworld.get_locations(core.player_id) if type(loc.address) is int}
    if not (missing | checked) <= known:
        unknown = sorted((missing | checked) - known)
        labels = ", ".join(request.get("location_names", {}).get(str(i), str(i)) for i in unknown[:3])
        raise LogicError(f"{len(unknown)} Server-Checks fehlen im rekonstruierten Modell: {labels}. Die Logik wird nicht als verlässlich angezeigt.")
    if any(world.item_id_to_name.get(int(key)) != name for key, name in request["item_names"].items()):
        raise LogicError("Der Itemkatalog passt nicht zur installierten APWorld-Version.")
    core.set_missing_locations(missing)
    core.set_items_received([NetworkItem(i["item"], i["location"], i["player"], i["flags"]) for i in request["received"]])
    state = core.updateTracker()
    if state.state is None or any(line.group.value == "error" for lines in core.log_lines.values() for line in lines):
        raise LogicError("Die Spielregeln konnten nicht vollständig ausgewertet werden.")
    reachable = set(core.locations_available)
    locations = [dict(id=loc.address, name=loc.name, region=loc.parent_region.name,
                      reachable=loc.address in reachable, checked=loc.address in checked)
                 for loc in core.multiworld.get_locations(core.player_id) if type(loc.address) is int and loc.address in missing | checked]
    goal = core.multiworld.has_beaten_game(state.state, core.player_id)
    return dict(state="ready", engine="Universal Tracker 0.3.3", game=request["game"],
                go_mode=True if goal else None if state.unconnected_entrances else False, reachable=len(reachable), remaining=len(missing),
                locations=sorted(locations, key=lambda loc:(loc["checked"], not loc["reachable"], loc["region"], loc["name"])),
                inventory=[dict(name=name, count=count) for name, count in sorted(state.all_items.items())],
                deferred_entrances=len(state.unconnected_entrances))


def main():
    output = sys.stdout
    try:
        request = json.loads(sys.stdin.read(8 * 1024 * 1024))
        with contextlib.redirect_stdout(sys.stderr):
            result = evaluate(request)
    except Exception as exc:
        # Do not send raw engine exceptions/tracebacks or server slot_data to UI.
        result = dict(state="unsupported", error=str(exc) if isinstance(exc, LogicError) else
                      "Universal Tracker konnte diese Spielversion nicht auswerten. Prüfe Engine und APWorld-Version.")
    output.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
