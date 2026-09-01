from typing import Any, ClassVar, TextIO
from Options import OptionError
from worlds.AutoWorld import World, WebWorld
from BaseClasses import Region, Item, ItemClassification
from .Challenges import (
    ALL_HEROES, HERO_CHECKS, WIN, roll_checks_for_hero, get_pass_key, hero_sort_key,
    location_name, CHECK_DESCRIPTIONS, pass_key_from_item_name, pass_name_for_key,
    pass_location_name, pass_check_keys_for_seed, pass_location_names_for_seed,
    PASS_KEYS, PASS_XP_CHECKS, PASS_TIMED_WIN_CHECKS,
    PASS_XP_THRESHOLDS, TIMED_WIN_MAX_SECONDS,
    DAILY_QUESTS_COMPLETE, DAILY_QUEST_DEFS, daily_quest_item_name,
    daily_quest_location_name, roll_daily_quests,
)
from .Items import (
    item_table, FILLER_ITEM_NAME, hero_unlock_items, role_pass_items, hero_shard_items,
    daily_quest_items, consumable_items,
    SHARDS_TO_UNLOCK, HEROES_PER_LOOT_CHEST, CHEST_COST_XP, CHEST_SLOTS, CHEST_NON_FILLER_SLOTS,
    MAX_LOOT_CHESTS, EXTRA_XP_PERCENT,
    XP_100_NAME, XP_200_NAME, XP_500_NAME, LOOT_CHEST_NAME, STIMPACK_NAME, TALENT_TOME_NAME,
    shard_item_name, is_open_currency_item,
    stimpack_count_for_seed, talent_tome_count_for_seed,
)
from .Locations import location_table, HoTSLocation, locations_by_hero, chest_location_name
from .Options import HoTSOptions, hots_option_groups
from .Rules import set_rules
from .Talents import (
    TALENT_LEVELS, choose_talent_rank, talent_counts_for_hero,
    talent_location_name, talent_slot_description,
)


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
        **{
            location_name(hero, check_key): CHECK_DESCRIPTIONS[check_key]
            for hero, checks in HERO_CHECKS.items()
            for check_key in checks
        },
        **{
            pass_location_name(pass_key, check_key): CHECK_DESCRIPTIONS[check_key]
            for pass_key in PASS_KEYS
            for check_key in PASS_XP_CHECKS + PASS_TIMED_WIN_CHECKS
        },
        **{
            talent_location_name(hero, level): (
                f"Win a match while taking the assigned {talent_slot_description(level).lower()} "
                "(see the Talents tab; a Talent Tome can make that tier accept any pick)"
            )
            for hero in ALL_HEROES
            for level in TALENT_LEVELS
        },
        **{
            daily_quest_location_name(key): DAILY_QUEST_DEFS[key][3]
            for key in DAILY_QUEST_DEFS
        },
        daily_quest_location_name(DAILY_QUESTS_COMPLETE): "Complete every daily quest in this seed",
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
        "Shard": set(hero_shard_items),
        "XP": {XP_100_NAME, XP_200_NAME, XP_500_NAME},
        "Loot": {LOOT_CHEST_NAME},
        "Daily Quest Unlock": set(daily_quest_items),
        "Consumable": set(consumable_items),
    }

    hero_rank: dict[str, int]
    hero_checks: dict[str, list[str]]
    starting_heroes: list[str]
    hero_talent_requirements: dict[str, list[dict[str, int]]]
    talent_location_names: list[str]
    talent_assigned_heroes: list[str]

    MAX_STARTING_HEROES = 5

    def generate_early(self) -> None:
        hero_pool = self.options.enabled_heroes.enabled_display_names()
        pool_size = self.options.hero_pool_size.value

        pinned_goal = self.options.goal_heroes.pinned_display_names()
        for hero in pinned_goal:
            if hero not in hero_pool:
                raise OptionError(
                    f"Goal hero ({hero}) must be set to 1 in Enabled Heroes."
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
        must_include.update(pinned_goal)

        if pool_size > 0:
            pool_size = min(pool_size, len(hero_pool))
            if len(must_include) > pool_size:
                raise OptionError(
                    f"Hero Pool Size ({pool_size}) is too small for "
                    f"start_inventory and pinned goal heroes ({len(must_include)} required)."
                )
            others = [h for h in hero_pool if h not in must_include]
            self.enabled_heroes = sorted(
                list(must_include) + self.random.sample(others, pool_size - len(must_include)),
                key=hero_sort_key,
            )
        else:
            self.enabled_heroes = sorted(hero_pool, key=hero_sort_key)

        remove_level_20 = bool(self.options.remove_level_20_check.value)
        self.hero_checks = {
            hero: roll_checks_for_hero(hero, self.random, remove_level_20)
            for hero in self.enabled_heroes
        }

        count = int(self.options.goal_hero_count.value)
        if pinned_goal:
            extra_needed = max(0, count - len(pinned_goal)) if count > 0 else 0
            others = [h for h in self.enabled_heroes if h not in pinned_goal]
            extra = self.random.sample(others, min(extra_needed, len(others))) if extra_needed else []
            self.goal_heroes = sorted([*pinned_goal, *extra], key=hero_sort_key)
        elif count <= 0 or count >= len(self.enabled_heroes):
            self.goal_heroes = list(self.enabled_heroes)
        else:
            self.goal_heroes = sorted(
                self.random.sample(self.enabled_heroes, count),
                key=hero_sort_key,
            )

        goal_mode = self.options.goal.current_key
        if goal_mode == "mastery":
            self.goal_check_keys: list[str] | None = None
        elif goal_mode == "distinct_wins":
            self.goal_check_keys = [WIN]
        else:
            raise Exception(f"Unknown goal mode: {goal_mode}")
        self.goal_mode = goal_mode
        self.use_role_passes = bool(self.options.role_passes.value)
        self.include_timed_win_check = (
            self.use_role_passes and bool(self.options.include_timed_win_check.value)
        )
        self.enabled_pass_keys = sorted({get_pass_key(h) for h in self.enabled_heroes})
        self.pass_check_keys = pass_check_keys_for_seed(
            self.use_role_passes, self.include_timed_win_check,
        )
        self.pass_location_names = pass_location_names_for_seed(
            self.enabled_pass_keys, self.use_role_passes, self.include_timed_win_check,
        )
        self.random_talents_per_hero = int(self.options.random_talents_per_hero.value)
        self.random_talent_hero_count = int(self.options.random_talent_hero_count.value)
        self.placed_stimpacks = 0
        self.placed_talent_tomes = 0
        self.shards_to_unlock = SHARDS_TO_UNLOCK
        self.hero_talent_requirements = {}
        self.talent_location_names = []
        self.talent_assigned_heroes: list[str] = []
        if self.random_talents_per_hero > 0 and self.random_talent_hero_count > 0:
            self._roll_talent_requirements()
        self._pick_starting_heroes()
        self._roll_full_unlock_heroes()
        self._roll_loot_chest_count()
        self._build_hero_ranks()
        self.daily_quest_keys: list[str] = []
        self.daily_quest_location_names: list[str] = []
        if bool(self.options.daily_quests.value):
            self.daily_quest_keys = roll_daily_quests(
                self.enabled_heroes, self.random, self.starting_heroes,
            )
            self.daily_quest_location_names = [
                daily_quest_location_name(key) for key in self.daily_quest_keys
            ]
            if self.daily_quest_keys:
                self.daily_quest_location_names.append(
                    daily_quest_location_name(DAILY_QUESTS_COMPLETE)
                )
        self.goal_location_names = self._goal_location_names()

    def _roll_talent_requirements(self) -> None:
        """Assign random talent slots to a random subset of seed heroes."""
        per_hero = self.random_talents_per_hero
        hero_count = min(self.random_talent_hero_count, len(self.enabled_heroes))
        if per_hero <= 0 or hero_count <= 0:
            return
        assigned = sorted(self.random.sample(self.enabled_heroes, hero_count))
        self.talent_assigned_heroes = assigned
        skip_level_20 = bool(self.options.remove_level_20_check.value)
        for hero in assigned:
            counts = talent_counts_for_hero(hero)
            available_levels = [
                lvl for lvl in TALENT_LEVELS
                if counts.get(lvl, 0) > 0 and not (skip_level_20 and lvl == 20)
            ]
            n = min(per_hero, len(available_levels))
            if n <= 0:
                continue
            levels = self.random.sample(available_levels, n)
            levels.sort(key=TALENT_LEVELS.index)
            reqs: list[dict[str, int]] = []
            for level in levels:
                total = counts[level]
                rank = choose_talent_rank(hero, level, total, reqs, self.random)
                reqs.append({"level": level, "rank": rank})
            self.hero_talent_requirements[hero] = reqs
            for req in reqs:
                self.talent_location_names.append(
                    talent_location_name(hero, req["level"])
                )

    def _starters_excluded_heroes(self) -> set[str]:
        """Keep goal heroes off the starting roster when the pool has other options."""
        if len(self.enabled_heroes) <= 1:
            return set()
        return set(self.goal_heroes)

    def _eligible_starters(self, heroes: list[str]) -> list[str]:
        excluded = self._starters_excluded_heroes()
        eligible = [hero for hero in heroes if hero not in excluded]
        return eligible if eligible else list(heroes)

    def _pick_starting_heroes(self) -> None:
        inv = {k: v for k, v in self.options.start_inventory.value.items() if v > 0}
        hero_inv = next((k for k in inv if k in ALL_HEROES), None)
        excluded = self._starters_excluded_heroes()
        if hero_inv in excluded:
            hero_inv = None
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
            pool = self._eligible_starters(list(self.enabled_heroes))
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
            viable = [
                key for key, heroes in by_pass.items()
                if len(self._eligible_starters(heroes)) >= requested_total
            ]
            if viable:
                pass_key = self.random.choice(viable)
            else:
                fallback = [
                    (key, self._eligible_starters(heroes))
                    for key, heroes in by_pass.items()
                    if self._eligible_starters(heroes)
                ]
                if not fallback:
                    pass_key = self.random.choice(list(by_pass))
                else:
                    pass_key = max(fallback, key=lambda item: len(item[1]))[0]

        pool = self._eligible_starters(by_pass[pass_key])
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

    def _roll_full_unlock_heroes(self) -> None:
        """10–25% of seed heroes (min 1) use a full unlock item; others use shards."""
        locked = [h for h in self.enabled_heroes if h not in self.starting_heroes]
        if not locked:
            self.full_unlock_heroes: list[str] = []
            self.shard_heroes: list[str] = []
            return
        pct = self.random.uniform(0.10, 0.25)
        count = max(1, round(len(self.enabled_heroes) * pct))
        count = min(count, len(locked))
        self.full_unlock_heroes = sorted(self.random.sample(locked, count), key=hero_sort_key)
        full_set = set(self.full_unlock_heroes)
        self.shard_heroes = sorted((h for h in locked if h not in full_set), key=hero_sort_key)

    def _roll_loot_chest_count(self) -> None:
        import math
        n = max(1, math.ceil(len(self.enabled_heroes) / HEROES_PER_LOOT_CHEST))
        self.loot_chest_count = min(n, MAX_LOOT_CHESTS)

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
        include_talents = self.goal_check_keys is None
        for hero in self.goal_heroes:
            check_keys = self.goal_check_keys or self.hero_checks.get(hero, [])
            for check_key in check_keys:
                names.append(location_name(hero, check_key))
            if include_talents:
                for req in self.hero_talent_requirements.get(hero) or []:
                    names.append(
                        talent_location_name(hero, int(req["level"]))
                    )
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

        for loc_name in self.pass_location_names:
            data = location_table[loc_name]
            loc = HoTSLocation(self.player, loc_name, data.id, nexus)
            nexus.locations.append(loc)

        for loc_name in self.talent_location_names:
            data = location_table[loc_name]
            loc = HoTSLocation(self.player, loc_name, data.id, nexus)
            nexus.locations.append(loc)

        for chest_index in range(1, self.loot_chest_count + 1):
            for slot in range(1, CHEST_SLOTS + 1):
                loc_name = chest_location_name(chest_index, slot)
                data = location_table[loc_name]
                loc = HoTSLocation(self.player, loc_name, data.id, nexus)
                nexus.locations.append(loc)

        for loc_name in self.daily_quest_location_names:
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
            self.enabled_pass_keys if self.use_role_passes else None,
            self.pass_check_keys if self.use_role_passes else None,
            self.talent_location_names or None,
            loot_chest_count=self.loot_chest_count,
            shards_to_unlock=self.shards_to_unlock,
            daily_quest_keys=self.daily_quest_keys or None,
            starting_heroes=self.starting_heroes,
        )

        goal_locs = tuple(self.goal_location_names)
        player = self.player
        victory = self.multiworld.get_location("Nexus Mastery", player)
        victory.access_rule = lambda state, locs=goal_locs, pid=player: all(
            state.can_reach_location(loc_name, pid) for loc_name in locs
        )

    def create_items(self) -> None:
        """Shards / full unlocks / passes / reserved XP / consumables / Void Scrap."""
        total_locations = sum(len(self.hero_checks[h]) for h in self.enabled_heroes)
        total_locations += len(self.pass_location_names)
        total_locations += len(self.talent_location_names)
        total_locations += self.loot_chest_count * CHEST_SLOTS
        total_locations += len(self.daily_quest_location_names)
        item_pool: list[Item] = []

        for hero in self.full_unlock_heroes:
            item_pool.append(self.create_item(hero))
        for hero in self.shard_heroes:
            for _ in range(self.shards_to_unlock):
                item_pool.append(self.create_item(shard_item_name(hero)))

        for slot, _quest_key in enumerate(self.daily_quest_keys, start=1):
            if slot == 1:
                continue
            item_pool.append(self.create_item(daily_quest_item_name(slot)))

        if self.use_role_passes:
            pass_keys_needed = sorted({get_pass_key(h) for h in self.enabled_heroes})
            for pass_key in pass_keys_needed:
                if pass_key != self.starting_role_pass:
                    item_pool.append(self.create_item(pass_name_for_key(pass_key)))

        reserved_opens = self.loot_chest_count
        free_chests = 0
        if reserved_opens >= 4:
            free_chests = self.random.randint(0, max(1, reserved_opens // 5))
        reserved_xp_value = (reserved_opens - free_chests) * CHEST_COST_XP
        xp500_count = reserved_xp_value // 500
        for _ in range(xp500_count):
            item_pool.append(self.create_item(XP_500_NAME))
        for _ in range(free_chests):
            item_pool.append(self.create_item(LOOT_CHEST_NAME))

        bonus_value = int(reserved_opens * CHEST_COST_XP * EXTRA_XP_PERCENT / 100)
        useful_200 = (bonus_value // 2) // 200
        rem = bonus_value - useful_200 * 200
        filler_100 = rem // 100
        if useful_200 == 0 and bonus_value >= 100:
            filler_100 = bonus_value // 100
        for _ in range(useful_200):
            item_pool.append(self.create_item(XP_200_NAME))
        for _ in range(filler_100):
            item_pool.append(self.create_item(XP_100_NAME))

        room = total_locations - len(item_pool)
        wanted_tomes = talent_tome_count_for_seed(len(self.talent_location_names))
        wanted_stims = stimpack_count_for_seed(len(self.enabled_heroes))
        tome_n = min(wanted_tomes, room) if self.hero_talent_requirements else 0
        room -= tome_n
        stim_n = min(wanted_stims, room)
        room -= stim_n
        self.placed_talent_tomes = tome_n
        self.placed_stimpacks = stim_n
        for _ in range(tome_n):
            item_pool.append(self.create_item(TALENT_TOME_NAME))
        for _ in range(stim_n):
            item_pool.append(self.create_item(STIMPACK_NAME))

        filler_needed = total_locations - len(item_pool)
        if filler_needed < 0:
            raise Exception(
                f"More progression/XP items ({len(item_pool)}) than locations ({total_locations})."
            )
        for _ in range(filler_needed):
            item_pool.append(self.create_item(FILLER_ITEM_NAME))

        self.multiworld.itempool += item_pool

    def create_item(self, name: str) -> Item:
        data = item_table[name]
        return Item(name, data.classification, data.id, self.player)

    def pre_fill(self) -> None:
        """Fill most chest slots from the shared pool via fill_restrictive (same hook as
        OoT shops / SMZ3 dungeons). Not YAML-local and not priority: any world's
        useful/progression can land here. Slot 4 is left for main fill.
        """
        from Fill import fill_restrictive

        if self.loot_chest_count <= 0:
            return
        prize_slots = max(0, min(CHEST_SLOTS - 1, CHEST_NON_FILLER_SLOTS))
        if prize_slots <= 0:
            return

        locations: list = []
        for chest_index in range(1, self.loot_chest_count + 1):
            for slot in range(1, prize_slots + 1):
                try:
                    loc = self.multiworld.get_location(
                        chest_location_name(chest_index, slot), self.player,
                    )
                except KeyError:
                    continue
                if loc.item is None:
                    locations.append(loc)
        if not locations:
            return

        def is_prize(item: Item) -> bool:
            if item.classification in (ItemClassification.filler, ItemClassification.trap):
                return False
            if item.player == self.player and is_open_currency_item(item.name):
                return False
            return True

        prizes = [item for item in self.multiworld.itempool if is_prize(item)]
        if not prizes:
            return
        self.random.shuffle(prizes)
        self.random.shuffle(locations)
        chest_locs = list(locations)

        fill_restrictive(
            self.multiworld,
            self.multiworld.get_all_state(False),
            locations,
            prizes,
            single_player_placement=False,
            lock=True,
            allow_partial=True,
            one_item_per_player=False,
            name="HotS loot chests",
        )

        placed_ids = {id(loc.item) for loc in chest_locs if loc.item is not None}
        if placed_ids:
            self.multiworld.itempool[:] = [
                item for item in self.multiworld.itempool if id(item) not in placed_ids
            ]

    def generate_basic(self) -> None:
        start_inv = self.options.start_inventory.value
        for hero in self.starting_heroes:
            if start_inv.get(hero, 0) <= 0:
                self.multiworld.push_precollected(self.create_item(hero))
        if self.use_role_passes and self.starting_role_pass:
            pass_name = pass_name_for_key(self.starting_role_pass)
            if start_inv.get(pass_name, 0) <= 0:
                self.multiworld.push_precollected(self.create_item(pass_name))
        if self.daily_quest_keys:
            unlock1 = daily_quest_item_name(1)
            if start_inv.get(unlock1, 0) <= 0:
                self.multiworld.push_precollected(self.create_item(unlock1))

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
            "cumulative_checks": bool(self.options.cumulative_checks.value),
            "remove_level_20_check": bool(self.options.remove_level_20_check.value),
            "goal_mode": self.goal_mode,
            "goal_heroes": self.goal_heroes,
            "goal_location_names": self.goal_location_names,
            "goal_location_ids": goal_location_ids,
            "goal_summary": goal_summary,
            "role_passes": self.use_role_passes,
            "starting_hero": self.starting_hero,
            "starting_heroes": self.starting_heroes,
            "starting_role_pass": self.starting_role_pass,
            "enabled_pass_keys": self.enabled_pass_keys,
            "pass_check_keys": self.pass_check_keys,
            "pass_location_names": self.pass_location_names,
            "pass_xp_thresholds": PASS_XP_THRESHOLDS,
            "timed_win_max_seconds": TIMED_WIN_MAX_SECONDS,
            "include_timed_win_check": self.include_timed_win_check,
            "random_talents_per_hero": self.random_talents_per_hero,
            "random_talent_hero_count": self.random_talent_hero_count,
            "talent_assigned_heroes": self.talent_assigned_heroes,
            "hero_talent_requirements": self.hero_talent_requirements,
            "talent_location_names": self.talent_location_names,
            "loot_chest_count": self.loot_chest_count,
            "chest_cost_xp": CHEST_COST_XP,
            "shards_to_unlock": self.shards_to_unlock,
            "full_unlock_heroes": self.full_unlock_heroes,
            "shard_heroes": self.shard_heroes,
            "stimpack_count": getattr(self, "placed_stimpacks", 0),
            "talent_tome_count": getattr(self, "placed_talent_tomes", 0),
            "daily_quest_keys": self.daily_quest_keys,
            "daily_quest_defs": {
                key: {
                    "capability": DAILY_QUEST_DEFS[key][0],
                    "field": DAILY_QUEST_DEFS[key][1],
                    "threshold": DAILY_QUEST_DEFS[key][2],
                    "name": DAILY_QUEST_DEFS[key][3],
                    "item": daily_quest_item_name(slot),
                    "slot": slot,
                }
                for slot, key in enumerate(self.daily_quest_keys, start=1)
            },
            "locations": self.location_name_to_id,
            "items": self.item_name_to_id,
        }

    def _goal_summary_text(self) -> str:
        all_seed = set(self.goal_heroes) == set(self.enabled_heroes)
        if self.goal_mode == "distinct_wins":
            if all_seed:
                return f"Win a match with every hero in the seed ({len(self.goal_heroes)})"
            return f"Win a match with each of: {', '.join(self.goal_heroes)}"
        if all_seed:
            return f"Complete all checks for every hero in the seed ({len(self.goal_heroes)})"
        return f"Complete all checks for: {', '.join(self.goal_heroes)}"

    def write_spoiler_header(self, spoiler_handle: TextIO) -> None:
        pool_size = self.options.hero_pool_size.value
        if pool_size > 0:
            spoiler_handle.write(f"Hero Pool Size:                  {pool_size}\n")
        spoiler_handle.write(f"Selected Heroes:                 {', '.join(self.enabled_heroes)}\n")
        if bool(self.options.cumulative_checks.value):
            spoiler_handle.write("Cumulative Checks:               yes\n")
        if bool(self.options.remove_level_20_check.value):
            spoiler_handle.write("Remove Level 20 Check:             yes\n")
        if self.hero_talent_requirements:
            spoiler_handle.write(
                f"Random Talent Checks:            {self.random_talents_per_hero}/hero, "
                f"{len(self.talent_assigned_heroes)} heroes\n"
            )
            for hero in self.talent_assigned_heroes:
                reqs = self.hero_talent_requirements.get(hero) or []
                if not reqs:
                    continue
                labels = ", ".join(f"L{r['level']}#{r['rank']}" for r in reqs)
                spoiler_handle.write(f"  {hero}: {labels}\n")
        if len(self.starting_heroes) > 1:
            spoiler_handle.write(
                f"Starting Heroes:                 {', '.join(self.starting_heroes)}\n"
            )
        spoiler_handle.write(f"Goal Summary:                    {self._goal_summary_text()}\n")
        spoiler_handle.write(f"Goal Heroes:                     {', '.join(self.goal_heroes)}\n")
        spoiler_handle.write(f"Loot Chests:                     {self.loot_chest_count}\n")
        stim_n = getattr(self, "placed_stimpacks", 0)
        tome_n = getattr(self, "placed_talent_tomes", 0)
        if stim_n or tome_n:
            parts = []
            if stim_n:
                parts.append(f"{stim_n} Stimpack")
            if tome_n:
                parts.append(f"{tome_n} Talent Tome")
            spoiler_handle.write(f"Consumables:                     {', '.join(parts)}\n")
        if self.daily_quest_keys:
            spoiler_handle.write(
                "Daily Quests:                    "
                + ", ".join(daily_quest_location_name(k) for k in self.daily_quest_keys)
                + "\n"
            )
        if self.full_unlock_heroes:
            spoiler_handle.write(
                f"Full Unlock Heroes:              {', '.join(self.full_unlock_heroes)}\n"
            )
        if self.shard_heroes:
            spoiler_handle.write(
                f"Shard Heroes ({self.shards_to_unlock} each):      "
                f"{len(self.shard_heroes)} heroes\n"
            )
        if self.use_role_passes:
            goal_passes = sorted({get_pass_key(hero) for hero in self.goal_heroes})
            spoiler_handle.write(
                "Goal Role Passes Needed:         "
                + ", ".join(pass_name_for_key(pass_key) for pass_key in goal_passes)
                + "\n"
            )
