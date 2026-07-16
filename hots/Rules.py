from BaseClasses import MultiWorld
from worlds.generic.Rules import add_item_rule
from .Challenges import (
    ALL_HEROES, get_pass_key, heroes_in_pass, pass_key_from_item_name, pass_name_for_key,
    location_name, pass_location_name,
)


def set_rules(
    multiworld: MultiWorld,
    player: int,
    enabled_heroes: list[str],
    use_role_passes: bool,
    hero_rank: dict[str, int],
    hero_checks: dict[str, list[str]],
    enabled_pass_keys: list[str] | None = None,
    pass_check_keys: list[str] | None = None,
) -> None:
    for hero in enabled_heroes:
        unlock_item = hero
        pass_needed = pass_name_for_key(get_pass_key(hero))
        for check_key in hero_checks.get(hero, []):
            loc_name = location_name(hero, check_key)
            try:
                loc = multiworld.get_location(loc_name, player)
            except KeyError:
                continue

            if use_role_passes:
                loc.access_rule = lambda state, unlock=unlock_item, pass_item=pass_needed, pid=player: (
                    state.has(unlock, pid) and state.has(pass_item, pid)
                )
            else:
                loc.access_rule = lambda state, unlock=unlock_item, pid=player: state.has(unlock, pid)

            on_hero = hero

            def unlock_item_rule(
                item,
                host=on_hero,
                ranks=hero_rank,
            ) -> bool:
                if item.name not in ALL_HEROES:
                    return True
                if host not in ranks or item.name not in ranks:
                    return False
                if item.name == host:
                    return False
                return ranks[host] < ranks[item.name]

            add_item_rule(loc, unlock_item_rule)

            if use_role_passes:

                def pass_item_rule(item, host=on_hero) -> bool:
                    if not item.name.endswith(" Pass"):
                        return True
                    item_pass_key = pass_key_from_item_name(item.name)
                    if item_pass_key is None:
                        return True
                    return get_pass_key(host) != item_pass_key

                add_item_rule(loc, pass_item_rule)

    if use_role_passes and enabled_pass_keys and pass_check_keys:
        set_pass_rules(multiworld, player, enabled_heroes, enabled_pass_keys, pass_check_keys)


def set_pass_rules(
    multiworld: MultiWorld,
    player: int,
    enabled_heroes: list[str],
    enabled_pass_keys: list[str],
    pass_check_keys: list[str],
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

            loc.access_rule = lambda state, needed=pass_item, heroes=pass_heroes, pid=player: (
                state.has(needed, pid)
                and any(state.has(hero, pid) for hero in heroes)
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
                if item.name not in ALL_HEROES:
                    return True
                return get_pass_key(item.name) != host

            add_item_rule(loc, pass_hero_item_rule)
