"""Narrow native-world adapters for the current group; imported only by UT worker.

Only server-reported check identities/options are used. No seed placements enter
these adapters. Generation hooks are changed in the disposable process only.
"""
import importlib


def server_checks(request):
    names = request.get("location_names", {})
    return {names[str(i)]: i for i in set(request["missing"]) | set(request["checked"]) if str(i) in names}


def prepare(game, cls, request):
    checks = server_checks(request)
    if game == "Hollow Knight":
        original = cls.create_items
        def create_items(world):
            original(world)
            # HK randomly distributes a fixed number of extra vendor slots.
            # Reproduce the actual server's vendor list before native set_rules.
            for base, locations in world.created_multi_locations.items():
                desired = {name for name in checks if name.rpartition('_')[0] == base}
                if not desired and not any(loc.address is not None for loc in locations):
                    continue
                location_type = type(locations[0]) if locations else getattr(importlib.import_module(cls.__module__), "HKLocation")
                for loc in list(locations):
                    if loc.address is not None and loc.name not in desired:
                        loc.parent_region.locations.remove(loc)
                        world.multiworld.regions.location_cache[world.player].pop(loc.name, None)
                        locations.remove(loc)
                existing = {loc.name for loc in locations}
                for name in sorted(desired - existing):
                    if name not in world.location_name_to_id:
                        raise ValueError("Unknown HK vendor check")
                    region = world.multiworld.get_region("Menu", world.player)
                    loc = location_type(world.player, name, checks[name], region, basename=base,
                        costs=request["slot_data"].get("location_costs", {}).get(name))
                    region.locations.append(loc)
                    locations.append(loc)
        cls.create_items = create_items
    elif game == "Bloodstained: Ritual of the Night":
        prefix = cls.__module__.rsplit('.', 1)[0]
        locations = importlib.import_module(prefix + '.locations')
        logic = importlib.import_module(prefix + '.logic')
        def chest_locations(world):
            # The native world randomly allocates multiple checks to physical
            # chests. The server's missing+checked IDs identify the real ones.
            selected = set(checks) & set(locations.CHEST_CANDIDATES)
            if not selected:
                raise ValueError("Missing Bloodstained chest list")
            world.active_chest_locations = selected
            for name in sorted(selected | set(locations.BREAKABLE_WALLS)):
                data = locations.ALL_RITUAL_LOCATIONS[name]
                region = world.get_region(logic.location_check_region(data.native_name, enemy=False))
                region.add_locations(locations.get_location_names_with_ids([name]))
        locations.create_chest_and_wall_locations = chest_locations
    elif game == "Skyward Sword" and request.get('layout'):
        layout = request['layout']
        original_early = cls.generate_early
        def generate_early(world):
            original_early(world)
            all_dungeons = set(world.dungeons.required_dungeons) | set(world.dungeons.banned_dungeons)
            required = layout['Required Dungeons']
            if not isinstance(required, list) or not set(required) <= all_dungeons:
                raise ValueError('Invalid SS dungeon topology')
            world.dungeons.required_dungeons = list(required)
            world.dungeons.banned_dungeons = sorted(all_dungeons - set(required))
            world.entrances.starting_statues = layout['Starting Statues']
            world.entrances.starting_entrance = layout['Starting Entrance']
            world.origin_region_name = layout['Starting Entrance']['apregion']
            world.progress_locations, world.nonprogress_locations = world.determine_progress_and_nonprogress_locations()
            world.batreaux_rewards = layout['Batreaux Rewards']
        cls.generate_early = generate_early
        prefix = cls.__module__
        entrance_module = importlib.import_module(prefix + '.rando.EntranceRando')
        entrance_data = importlib.import_module(prefix + '.Entrances')
        # Obtain the native entrance manager type from the world constructor's
        # module, rather than adding a second set of copied access rules.
        manager_type = next(value for value in vars(entrance_module).values()
            if isinstance(value, type) and value.__module__ == entrance_module.__name__
            and hasattr(value, 'randomize_dungeon_entrances_only'))
        original_trials = manager_type.randomize_trial_gates
        original_dungeons = manager_type.randomize_dungeon_entrances_only
        def without_shuffle(manager, operation):
            old = manager.world.random.shuffle
            manager.world.random.shuffle = lambda values: None
            try:
                return operation(manager)
            finally:
                manager.world.random.shuffle = old
        def trials(manager):
            connections = {trial: gate for gate, trial in layout['Trial Entrances'].items()}
            if set(connections) != set(manager.trials):
                raise ValueError('Invalid SS trial topology')
            manager.trial_gates = [connections[trial] for trial in manager.trials]
            return without_shuffle(manager, original_trials)
        def dungeons(manager):
            actual = dict(layout['Entrances'])
            exits = {dungeon: entrance_data.SSExit(region, 'Dungeon Exit', world=manager.world).ss_name
                     for dungeon, region in entrance_module.DUNGEON_INITIAL_REGIONS.items()}
            destinations = {entrance_data.SSEntrance(region, name, world=manager.world).ss_name: name
                            for name, region in entrance_module.DUNGEON_ENTRANCE_REGIONS.items()}
            manager.dungeon_entrances = [destinations[actual[exits[dungeon]]] for dungeon in manager.dungeons]
            return without_shuffle(manager, original_dungeons)
        manager_type.randomize_trial_gates = trials
        manager_type.randomize_dungeon_entrances_only = dungeons
