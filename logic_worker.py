"""One bounded UT evaluation in Archipelago's Python, never in Flask.

Uses the separately installed, hash-pinned Universal Tracker. Reads one JSON
request on stdin and writes one JSON result; all engine output goes to stderr.
"""
import contextlib
import json
import logging
import os
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
    missing = set(request["missing"])
    checked = set(request["checked"])
    known = {loc.address for loc in core.multiworld.get_locations(core.player_id) if type(loc.address) is int}
    if known != missing | checked:
        raise LogicError("Die rekonstruierten Checks stimmen nicht mit dem Server überein. Die Logik wird nicht als verlässlich angezeigt.")
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
                 for loc in core.multiworld.get_locations(core.player_id) if type(loc.address) is int]
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
