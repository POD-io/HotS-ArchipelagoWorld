from typing import Any, ClassVar, TextIO
from Options import OptionError
from worlds.AutoWorld import World, WebWorld
from BaseClasses import Region, Item, ItemClassification
from .Challenges import (
    ALL_HEROES, HERO_CHECKS, WIN, checks_for_hero, get_pass_key, get_role,
    location_name, CHECK_DESCRIPTIONS, pass_key_from_item_name, pass_name_for_key,
)
from .Items import item_table, FILLER_ITEM_NAME, hero_unlock_items, role_pass_items
from .Locations import location_table, HoTSLocation, locations_by_hero
from .Options import HoTSOptions, hots_option_groups, resolve_goal_hero_name
from .Rules import set_rules


def launch_client(*args):
    from .Client import launch
    from worlds.LauncherComponents import launch as launch_component
    launch_component(launch, name="HotS Client", args=args)


from worlds.LauncherComponents import Component, components, Type
components.append(Component(
    "Heroes of the Storm Client",
    game_name="Heroes of the Storm",
    func=launch_client,
    component_type=Type.CLIENT,
    supports_uri=True,
))


class HoTSWebWorld(WebWorld):
    theme = "ice"
    option_groups = hots_option_groups
    location_descriptions = {
        location_name(hero, check_key): CHECK_DESCRIPTIONS[check_key]
        for hero, checks in HERO_CHECKS.items()
        for check_key in checks
    }


class HoTSWorld(World):
    game = "Heroes of the Storm"
    web = HoTSWebWorld()
    topology_present = False

    options_dataclass = HoTSOptions
    options: HoTSOptions

    item_name_to_id = {name: data.id for name, data in item_table.items()}
    location_name_to_id = {name: data.id for name, data in location_table.items()}
    location_name_groups = {hero: set(locations_by_hero[hero]) for hero in ALL_HEROES}
    item_name_groups: ClassVar[dict[str, set[str]]] = {
        "Pass": set(role_pass_items),
        "Hero": set(hero_unlock_items),
    }

    hero_rank: dict[str, int]
    hero_checks: dict[str, list[str]]
    starting_heroes: list[str]

    MAX_STARTING_HEROES = 5

    def generate_early(self) -> None:
        hero_pool = self.options.enabled_heroes.enabled_display_names()
        pool_size = self.options.hero_pool_size.value
        goal_mode = self.options.goal.current_key
        goal_hero: str | None = None

        if goal_mode == "specific_hero":
            goal_hero = resolve_goal_hero_name(self.options.goal_hero)
            if goal_hero not in ALL_HEROES:
                raise OptionError(f"Unknown goal hero: {goal_hero!r}")
            if goal_hero not in hero_pool:
                raise OptionError(
                    f"Goal Hero ({goal_hero}) must be set to 1 in Enabled Heroes."
                )

        inventory_heroes = {
            k for k, v in self.options.start_inventory.value.items()
            if v > 0 and k in ALL_HEROES
        }
        for hero in inventory_heroes:
            if hero not in hero_pool:
                raise OptionError(
                    f"start_inventory hero {hero} must be set to 1 in Enabled Heroes."
                )

        must_include = set(inventory_heroes)
        if goal_mode == "specific_hero":
            must_include.add(goal_hero)

        if pool_size > 0:
            if pool_size > len(hero_pool):
                raise OptionError(
                    f"Hero Pool Size ({pool_size}) exceeds enabled heroes ({len(hero_pool)})."
                )
            if len(must_include) > pool_size:
                raise OptionError(
                    f"Hero Pool Size ({pool_size}) is too small for "
                    f"start_inventory and goal heroes ({len(must_include)} required)."
                )
            others = [h for h in hero_pool if h not in must_include]
            self.enabled_heroes = sorted(
                list(must_include) + self.random.sample(others, pool_size - len(must_include))
            )
        else:
            self.enabled_heroes = hero_pool

        remove_hardest = bool(self.options.remove_hardest_checks.value)
        self.hero_checks = {
            hero: checks_for_hero(hero, remove_hardest)
            for hero in self.enabled_heroes
        }

        goal_count = min(self.options.goal_hero_count.value, len(self.enabled_heroes))

        if goal_mode == "random_heroes":
            picked = self.random.sample(self.enabled_heroes, goal_count)
            self.goal_heroes = sorted(picked)
            self.goal_check_keys: list[str] | None = None

        elif goal_mode == "specific_hero":
            self.goal_heroes = [goal_hero]
            self.goal_check_keys = None

        elif goal_mode == "distinct_wins":
            picked = self.random.sample(self.enabled_heroes, goal_count)
            self.goal_heroes = sorted(picked)
            self.goal_check_keys = [WIN]

        else:
            raise Exception(f"Unknown goal mode: {goal_mode}")

        self.goal_mode = goal_mode
        self.use_role_passes = bool(self.options.role_passes.value)
        self._pick_starting_heroes()
        self._build_hero_ranks()
        self.goal_location_names = self._goal_location_names()

    def _pick_starting_heroes(self) -> None:
        inv = {k: v for k, v in self.options.start_inventory.value.items() if v > 0}
        hero_inv = next((k for k in inv if k in ALL_HEROES), None)
        pass_inv = next(
            (key for k, v in inv.items() if v > 0 and (key := pass_key_from_item_name(k))),
            None,
        )

        extra_wanted = min(
            self.options.extra_starting_heroes.value,
            self.MAX_STARTING_HEROES - 1,
        )
        requested_total = min(
            1 + extra_wanted,
            self.MAX_STARTING_HEROES,
            len(self.enabled_heroes),
        )

        if not self.use_role_passes:
            pool = list(self.enabled_heroes)
            actual_total = min(requested_total, len(pool))
            if hero_inv and hero_inv in pool:
                starters = [hero_inv]
                others = [hero for hero in pool if hero != hero_inv]
                if actual_total > 1:
                    starters.extend(self.random.sample(others, actual_total - 1))
            else:
                starters = self.random.sample(pool, actual_total)
            self.starting_role_pass = None
            self.starting_heroes = starters
            self.starting_hero = hero_inv if hero_inv in starters else starters[0]
            return

        by_pass: dict[str, list[str]] = {}
        for hero in self.enabled_heroes:
            by_pass.setdefault(get_pass_key(hero), []).append(hero)

        if hero_inv and hero_inv in self.enabled_heroes:
            pass_key = get_pass_key(hero_inv)
        elif pass_inv and pass_inv in by_pass:
            pass_key = pass_inv
        else:
            viable = [key for key, heroes in by_pass.items() if len(heroes) >= requested_total]
            if viable:
                pass_key = self.random.choice(viable)
            else:
                best_count = max(len(heroes) for heroes in by_pass.values())
                pass_key = self.random.choice(
                    [key for key, heroes in by_pass.items() if len(heroes) == best_count]
                )

        pool = by_pass[pass_key]
        actual_total = min(requested_total, len(pool))

        if hero_inv and hero_inv in pool:
            starters = [hero_inv]
            others = [hero for hero in pool if hero != hero_inv]
            if actual_total > 1:
                starters.extend(self.random.sample(others, actual_total - 1))
        else:
            starters = self.random.sample(pool, actual_total)

        self.starting_role_pass = pass_key
        self.starting_heroes = starters
        self.starting_hero = hero_inv if hero_inv in starters else starters[0]

    def _build_hero_ranks(self) -> None:
        """Random shuffle used only to forbid unlock cycles in item rules — not a fixed unlock chain."""
        starters = list(self.starting_heroes)
        self.random.shuffle(starters)
        other_heroes = [hero for hero in self.enabled_heroes if hero not in self.starting_heroes]
        self.random.shuffle(other_heroes)
        hero_order = [*starters, *other_heroes]
        self.hero_rank = {hero: index for index, hero in enumerate(hero_order)}

    def _goal_location_names(self) -> list[str]:
        names: list[str] = []
        for hero in self.goal_heroes:
            check_keys = self.goal_check_keys or self.hero_checks.get(hero, [])
            for check_key in check_keys:
                names.append(location_name(hero, check_key))
        return names

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        nexus = Region("The Nexus", self.player, self.multiworld)

        conn = menu.create_exit("Enter the Nexus")
        conn.connect(nexus)
        self.multiworld.regions += [menu, nexus]

        for hero in self.enabled_heroes:
            for check_key in self.hero_checks[hero]:
                loc_name = location_name(hero, check_key)
                data = location_table[loc_name]
                loc = HoTSLocation(self.player, loc_name, data.id, nexus)
                nexus.locations.append(loc)

        victory_loc = HoTSLocation(self.player, "Nexus Mastery", None, nexus)
        nexus.locations.append(victory_loc)

    def set_rules(self) -> None:
        set_rules(
            self.multiworld,
            self.player,
            self.enabled_heroes,
            self.use_role_passes,
            self.hero_rank,
            self.hero_checks,
        )

        goal_locs = tuple(self.goal_location_names)
        player = self.player
        victory = self.multiworld.get_location("Nexus Mastery", player)
        victory.access_rule = lambda state, locs=goal_locs, pid=player: all(
            state.multiworld.get_location(loc_name, pid) in state.locations_checked
            for loc_name in locs
        )

    def post_fill(self) -> None:
        for loc_name in self.goal_location_names:
            loc = self.multiworld.get_location(loc_name, self.player)
            if loc.item and not loc.item.advancement:
                loc.item.classification = ItemClassification.progression

    def create_items(self) -> None:
        """One unlock item per locked hero and one pass per missing role — AP fill randomizes placement."""
        total_locations = sum(len(self.hero_checks[h]) for h in self.enabled_heroes)
        item_pool: list[Item] = []
        starting = set(self.starting_heroes)

        for hero in self.enabled_heroes:
            if hero not in starting:
                item_pool.append(self.create_item(hero))

        if self.use_role_passes:
            pass_keys_needed = sorted({get_pass_key(h) for h in self.enabled_heroes})
            for pass_key in pass_keys_needed:
                if pass_key != self.starting_role_pass:
                    item_pool.append(self.create_item(pass_name_for_key(pass_key)))

        filler_needed = total_locations - len(item_pool)
        if filler_needed < 0:
            raise Exception("More progression items than locations.")

        for _ in range(filler_needed):
            item_pool.append(self.create_item(FILLER_ITEM_NAME))

        self.multiworld.itempool += item_pool

    def create_item(self, name: str) -> Item:
        data = item_table[name]
        return Item(name, data.classification, data.id, self.player)

    def generate_basic(self) -> None:
        start_inv = self.options.start_inventory.value
        for hero in self.starting_heroes:
            if start_inv.get(hero, 0) <= 0:
                self.multiworld.push_precollected(self.create_item(hero))
        if self.use_role_passes and self.starting_role_pass:
            pass_name = pass_name_for_key(self.starting_role_pass)
            if start_inv.get(pass_name, 0) <= 0:
                self.multiworld.push_precollected(self.create_item(pass_name))

        victory = self.multiworld.get_location("Nexus Mastery", self.player)
        victory.place_locked_item(Item("Victory", ItemClassification.progression, None, self.player))
        self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", self.player)

    def fill_slot_data(self) -> dict[str, Any]:
        goal_location_ids = [
            self.location_name_to_id[name]
            for name in self.goal_location_names
            if name in self.location_name_to_id
        ]
        goal_summary = self._goal_summary_text()
        return {
            "enabled_heroes": self.enabled_heroes,
            "hero_checks": self.hero_checks,
            "remove_hardest_checks": bool(self.options.remove_hardest_checks.value),
            "goal_mode": self.goal_mode,
            "goal_heroes": self.goal_heroes,
            "goal_location_names": self.goal_location_names,
            "goal_location_ids": goal_location_ids,
            "goal_summary": goal_summary,
            "role_passes": self.use_role_passes,
            "starting_hero": self.starting_hero,
            "starting_heroes": self.starting_heroes,
            "starting_role_pass": self.starting_role_pass,
            "locations": self.location_name_to_id,
            "items": self.item_name_to_id,
        }

    def _goal_summary_text(self) -> str:
        if self.goal_mode == "distinct_wins":
            hero_list = ", ".join(self.goal_heroes)
            return f"Win a match with each of: {hero_list}"
        hero_list = ", ".join(self.goal_heroes)
        return f"Complete all checks for: {hero_list}"

    def write_spoiler_header(self, spoiler_handle: TextIO) -> None:
        pool_size = self.options.hero_pool_size.value
        if pool_size > 0:
            spoiler_handle.write(f"Hero Pool Size:                  {pool_size}\n")
        spoiler_handle.write(f"Selected Heroes:                 {', '.join(self.enabled_heroes)}\n")
        if bool(self.options.remove_hardest_checks.value):
            spoiler_handle.write("Remove Hardest Checks:           yes\n")
        if len(self.starting_heroes) > 1:
            spoiler_handle.write(
                f"Starting Heroes:                 {', '.join(self.starting_heroes)}\n"
            )
        spoiler_handle.write(f"Goal Summary:                    {self._goal_summary_text()}\n")
        spoiler_handle.write(f"Goal Heroes:                     {', '.join(self.goal_heroes)}\n")
        if self.use_role_passes:
            goal_passes = sorted({get_pass_key(hero) for hero in self.goal_heroes})
            spoiler_handle.write(
                "Goal Role Passes Needed:         "
                + ", ".join(pass_name_for_key(pass_key) for pass_key in goal_passes)
                + "\n"
            )
