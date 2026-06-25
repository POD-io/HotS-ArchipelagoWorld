from BaseClasses import MultiWorld
from worlds.generic.Rules import add_item_rule
from .Challenges import ALL_HEROES, get_role, location_name


def set_rules(
    multiworld: MultiWorld,
    player: int,
    enabled_heroes: list[str],
    use_role_passes: bool,
    hero_rank: dict[str, int],
    hero_checks: dict[str, list[str]],
) -> None:
    for hero in enabled_heroes:
        unlock_item = hero
        role = get_role(hero)
        pass_needed = f"{role.capitalize()} Pass"
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
                    pass_role = item.name[: -len(" Pass")].lower()
                    return get_role(host) != pass_role

                add_item_rule(loc, pass_item_rule)
