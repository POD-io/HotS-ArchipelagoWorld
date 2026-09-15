from BaseClasses import CollectionState, MultiWorld
from worlds.generic.Rules import add_item_rule
from .Challenges import (
    ALL_HEROES, DAILY_QUESTS_COMPLETE, DAILY_QUEST_DEFS, DAILY_QUEST_UNLOCK_MIN,
    capable_heroes_in_pool, daily_quest_item_name, daily_quest_location_name,
    get_pass_key, heroes_in_pass, pass_key_from_item_name, pass_name_for_key,
    location_name, pass_location_name,
)
from .Items import (
    CHEST_COST_XP, SHARDS_TO_UNLOCK, XP_VALUES, daily_quest_items,
    is_hero_wave_item, is_open_currency_item, shard_item_name,
    PROGRESSIVE_HERO_WAVE_NAME,
)
from .Locations import chest_location_name, location_table


def hero_unlocked_in_state(
    state: CollectionState,
    hero: str,
    player: int,
    shards_needed: int = SHARDS_TO_UNLOCK,
    wave_need: int = 0,
) -> bool:
    if wave_need > 0:
        return state.count(PROGRESSIVE_HERO_WAVE_NAME, player) >= wave_need
    if state.has(hero, player):
        return True
    if shards_needed <= 0:
        return False
    return state.count(shard_item_name(hero), player) >= shards_needed


def hero_playable_in_state(
    state: CollectionState,
    hero: str,
    player: int,
    shards_needed: int = SHARDS_TO_UNLOCK,
    use_role_passes: bool = False,
    wave_need: int = 0,
) -> bool:
    if not hero_unlocked_in_state(state, hero, player, shards_needed, wave_need=wave_need):
        return False
    if use_role_passes and not state.has(pass_name_for_key(get_pass_key(hero)), player):
        return False
    return True


def daily_quest_capable_playable_count(
    state: CollectionState,
    heroes: list[str],
    player: int,
    shards_needed: int,
    use_role_passes: bool,
    hero_wave_need: dict[str, int] | None = None,
) -> int:
    mapping = hero_wave_need or {}
    return sum(
        1 for h in heroes
        if hero_playable_in_state(
            state, h, player, shards_needed, use_role_passes, wave_need=mapping.get(h, 0),
        )
    )


def open_capacity_in_state(state: CollectionState, player: int) -> int:
    total = 0
    for name, value in XP_VALUES.items():
        total += state.count(name, player) * value
    return total


def set_rules(
    multiworld: MultiWorld,
    player: int,
    enabled_heroes: list[str],
    use_role_passes: bool,
    hero_rank: dict[str, int],
    hero_checks: dict[str, list[str]],
    enabled_pass_keys: list[str] | None = None,
    pass_check_keys: list[str] | None = None,
    talent_location_names: list[str] | None = None,
    loot_chest_count: int = 0,
    shards_to_unlock: int = SHARDS_TO_UNLOCK,
    daily_quest_keys: list[str] | None = None,
    starting_heroes: list[str] | None = None,
    hero_wave_need: dict[str, int] | None = None,
) -> None:
    wave_need = hero_wave_need or {}
    for hero in enabled_heroes:
        pass_needed = pass_name_for_key(get_pass_key(hero))
        need_waves = wave_need.get(hero, 0)
        for check_key in hero_checks.get(hero, []):
            loc_name = location_name(hero, check_key)
            try:
                loc = multiworld.get_location(loc_name, player)
            except KeyError:
                continue

            if use_role_passes:
                loc.access_rule = lambda state, h=hero, pass_item=pass_needed, pid=player, need=shards_to_unlock, wn=need_waves: (
                    hero_unlocked_in_state(state, h, pid, need, wave_need=wn) and state.has(pass_item, pid)
                )
            else:
                loc.access_rule = lambda state, h=hero, pid=player, need=shards_to_unlock, wn=need_waves: (
                    hero_unlocked_in_state(state, h, pid, need, wave_need=wn)
                )

            _add_hero_host_item_rules(loc, hero, hero_rank, use_role_passes)
            if starting_heroes and hero in starting_heroes:
                _forbid_daily_quest_items_on_loc(loc)

    if use_role_passes and enabled_pass_keys and pass_check_keys:
        set_pass_rules(
            multiworld, player, enabled_heroes, enabled_pass_keys, pass_check_keys, shards_to_unlock,
        )

    if talent_location_names:
        set_talent_rules(
            multiworld, player, use_role_passes, hero_rank, talent_location_names,
            shards_to_unlock, starting_heroes=starting_heroes, hero_wave_need=wave_need,
        )

    if loot_chest_count > 0:
        set_chest_rules(multiworld, player, loot_chest_count)

    if daily_quest_keys:
        set_daily_quest_rules(
            multiworld, player, enabled_heroes, daily_quest_keys, shards_to_unlock,
            use_role_passes=use_role_passes, hero_wave_need=wave_need,
        )


def _add_hero_host_item_rules(loc, host: str, hero_rank: dict[str, int], use_role_passes: bool) -> None:
    def unlock_item_rule(item, host_hero=host, ranks=hero_rank) -> bool:
        name = item.name
        if is_hero_wave_item(name):
            host_wave = ranks.get(host_hero)
            if host_wave is None:
                return False
            return True
        if name in ALL_HEROES:
            if host_hero not in ranks or name not in ranks:
                return False
            if name == host_hero:
                return False
            return ranks[host_hero] < ranks[name]
        if name == shard_item_name(host_hero):
            return False
        if name.endswith(" Shard"):
            parent = name[: -len(" Shard")]
            if parent in ALL_HEROES and host_hero in ranks and parent in ranks:
                if parent == host_hero:
                    return False
                return ranks[host_hero] < ranks[parent]
        return True

    add_item_rule(loc, unlock_item_rule)

    if use_role_passes:

        def pass_item_rule(item, host_hero=host) -> bool:
            if not item.name.endswith(" Pass"):
                return True
            item_pass_key = pass_key_from_item_name(item.name)
            if item_pass_key is None:
                return True
            return get_pass_key(host_hero) != item_pass_key

        add_item_rule(loc, pass_item_rule)


def set_talent_rules(
    multiworld: MultiWorld,
    player: int,
    use_role_passes: bool,
    hero_rank: dict[str, int],
    talent_location_names: list[str],
    shards_to_unlock: int = SHARDS_TO_UNLOCK,
    starting_heroes: list[str] | None = None,
    hero_wave_need: dict[str, int] | None = None,
) -> None:
    starters = set(starting_heroes or [])
    wave_need = hero_wave_need or {}
    for loc_name in talent_location_names:
        data = location_table.get(loc_name)
        if not data or not data.hero:
            continue
        hero = data.hero
        try:
            loc = multiworld.get_location(loc_name, player)
        except KeyError:
            continue

        pass_needed = pass_name_for_key(get_pass_key(hero))
        need_waves = wave_need.get(hero, 0)
        if use_role_passes:
            loc.access_rule = lambda state, h=hero, pass_item=pass_needed, pid=player, need=shards_to_unlock, wn=need_waves: (
                hero_unlocked_in_state(state, h, pid, need, wave_need=wn) and state.has(pass_item, pid)
            )
        else:
            loc.access_rule = lambda state, h=hero, pid=player, need=shards_to_unlock, wn=need_waves: (
                hero_unlocked_in_state(state, h, pid, need, wave_need=wn)
            )

        _add_hero_host_item_rules(loc, hero, hero_rank, use_role_passes)
        if hero in starters:
            _forbid_daily_quest_items_on_loc(loc)


def set_pass_rules(
    multiworld: MultiWorld,
    player: int,
    enabled_heroes: list[str],
    enabled_pass_keys: list[str],
    pass_check_keys: list[str],
    shards_to_unlock: int = SHARDS_TO_UNLOCK,
) -> None:
    for pass_key in enabled_pass_keys:
        pass_item = pass_name_for_key(pass_key)
        pass_heroes = heroes_in_pass(pass_key, enabled_heroes)
        for check_key in pass_check_keys:
            loc_name = pass_location_name(pass_key, check_key)
            try:
                loc = multiworld.get_location(loc_name, player)
            except KeyError:
                continue

            loc.access_rule = lambda state, needed=pass_item, heroes=pass_heroes, pid=player, need=shards_to_unlock: (
                state.has(needed, pid)
                and any(hero_unlocked_in_state(state, hero, pid, need) for hero in heroes)
            )

            host_pass = pass_key

            def pass_item_rule(item, host=host_pass) -> bool:
                if not item.name.endswith(" Pass"):
                    return True
                item_pass_key = pass_key_from_item_name(item.name)
                if item_pass_key is None:
                    return True
                return item_pass_key != host

            add_item_rule(loc, pass_item_rule)

            def pass_hero_item_rule(item, host=host_pass) -> bool:
                name = item.name
                if name in ALL_HEROES:
                    return get_pass_key(name) != host
                if name.endswith(" Shard"):
                    parent = name[: -len(" Shard")]
                    if parent in ALL_HEROES:
                        return get_pass_key(parent) != host
                return True

            add_item_rule(loc, pass_hero_item_rule)


def _forbid_daily_quest_items_on_loc(loc) -> None:
    """Keep Daily Quest Unlocks off sphere-0 / starting-hero hosts."""

    def rule(item) -> bool:
        return item.name not in daily_quest_items

    add_item_rule(loc, rule)


def set_daily_quest_rules(
    multiworld: MultiWorld,
    player: int,
    enabled_heroes: list[str],
    daily_quest_keys: list[str],
    shards_to_unlock: int = SHARDS_TO_UNLOCK,
    use_role_passes: bool = False,
    hero_wave_need: dict[str, int] | None = None,
) -> None:
    """Quest location needs Daily Quest Unlock N and DAILY_QUEST_UNLOCK_MIN playable capable heroes."""
    quest_loc_names: list[str] = []
    wave_need = hero_wave_need or {}
    for slot, quest_key in enumerate(daily_quest_keys, start=1):
        cap, _field, _thr, _title = DAILY_QUEST_DEFS[quest_key]
        heroes = capable_heroes_in_pool(cap, enabled_heroes)
        loc_name = daily_quest_location_name(quest_key)
        quest_loc_names.append(loc_name)
        unlock_item = daily_quest_item_name(slot)
        try:
            loc = multiworld.get_location(loc_name, player)
        except KeyError:
            continue
        loc.access_rule = lambda state, hs=heroes, pid=player, need=shards_to_unlock, item=unlock_item, passes=use_role_passes, waves=wave_need: (
            state.has(item, pid)
            and daily_quest_capable_playable_count(state, hs, pid, need, passes, waves)
            >= DAILY_QUEST_UNLOCK_MIN
        )
        _forbid_daily_quest_items_on_loc(loc)

    try:
        complete_loc = multiworld.get_location(daily_quest_location_name(DAILY_QUESTS_COMPLETE), player)
    except KeyError:
        return
    _forbid_daily_quest_items_on_loc(complete_loc)
    complete_loc.access_rule = lambda state, names=tuple(quest_loc_names), pid=player: all(
        state.can_reach_location(name, pid) for name in names
    )


def set_chest_rules(multiworld: MultiWorld, player: int, loot_chest_count: int) -> None:
    """Chest N requires N * 1000 open-capacity. Open currency cannot sit inside chests."""
    for chest_index in range(1, loot_chest_count + 1):
        required = chest_index * CHEST_COST_XP
        for slot in range(1, 5):
            loc_name = chest_location_name(chest_index, slot)
            try:
                loc = multiworld.get_location(loc_name, player)
            except KeyError:
                continue

            loc.access_rule = lambda state, need=required, pid=player: (
                open_capacity_in_state(state, pid) >= need
            )

            def no_currency_in_chests(item) -> bool:
                return not is_open_currency_item(item.name)

            add_item_rule(loc, no_currency_in_chests)

            def no_own_hero_waves(item, pid=player) -> bool:
                if item.player != pid:
                    return True
                return not is_hero_wave_item(item.name)

            add_item_rule(loc, no_own_hero_waves)
