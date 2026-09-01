from dataclasses import dataclass
from Options import (
    OptionCounter, OptionSet, Choice, Range, DefaultOnToggle,
    PerGameCommonOptions, OptionGroup, OptionError,
)
from .Challenges import (
    ALL_HEROES, YAML_KEY_TO_HERO, HERO_TO_YAML_KEY, hero_sort_key,
    normalize_hero_yaml_key,
)


def _yaml_keys_in_roster_order() -> list[str]:
    return [HERO_TO_YAML_KEY[hero] for hero in sorted(ALL_HEROES, key=hero_sort_key)]


class EnabledHeroes(OptionCounter):
    """
    Set a hero to 1 to include them. Omit this option to include every hero.
    If you list any heroes, only those set to 1 are included.
    """
    display_name = "Enabled Heroes"
    valid_keys = _yaml_keys_in_roster_order()
    min = 0
    max = 1
    cull_zeroes = False
    default = {key: 1 for key in _yaml_keys_in_roster_order()}

    @classmethod
    def from_any(cls, data):
        if isinstance(data, dict):
            data = {normalize_hero_yaml_key(str(k)): v for k, v in data.items()}
        return super().from_any(data)

    def verify(self, world, player_name, plando_options):
        super().verify(world, player_name, plando_options)
        if not any(v for v in self.value.values()):
            raise OptionError(
                f"{player_name}: Enabled Heroes — at least one hero must be set to 1."
            )

    def enabled_display_names(self) -> list[str]:
        return sorted(
            (
                YAML_KEY_TO_HERO[key]
                for key, enabled in self.value.items()
                if enabled and key in YAML_KEY_TO_HERO
            ),
            key=hero_sort_key,
        )


class GoalMode(Choice):
    """
    mastery: Complete every included check on the goal heroes.
    distinct_wins: Win one match with each goal hero.
    Goal Hero Count rolls that many from the seed. Goal Heroes adds chosen names in that set.
    """
    display_name = "Goal"
    option_mastery = 0
    option_distinct_wins = 1
    default = 0


class GoalHeroCount(Range):
    """
    How many seed heroes are rolled for the goal. Chosen Goal Heroes are included
    first; leftover slots fill at random. 0 = entire seed if nobody is chosen,
    or only the chosen heroes if any are listed.
    """
    display_name = "Goal Hero Count"
    range_start = 0
    range_end = len(ALL_HEROES)
    default = 3


class GoalHeroes(OptionSet):
    """
    Optional named heroes forced into the goal. Leave empty to use only Goal Hero Count.
    Listed heroes must be enabled and stay in the pool.
    """
    display_name = "Goal Heroes"
    valid_keys = frozenset(_yaml_keys_in_roster_order())
    default = frozenset()

    @classmethod
    def from_any(cls, data):
        if isinstance(data, dict):
            data = [
                normalize_hero_yaml_key(str(k))
                for k, v in data.items()
                if v and not str(k).startswith("#") and str(k).lower() != "random"
            ]
        elif isinstance(data, (list, set, frozenset)):
            data = [normalize_hero_yaml_key(str(k)) for k in data]
        return super().from_any(data)

    def pinned_display_names(self) -> list[str]:
        return sorted(
            (YAML_KEY_TO_HERO[key] for key in self.value if key in YAML_KEY_TO_HERO),
            key=hero_sort_key,
        )

    def verify(self, world, player_name, plando_options):
        super().verify(world, player_name, plando_options)
        enabled = getattr(plando_options, "enabled_heroes", None)
        enabled_vals = getattr(enabled, "value", None)
        if not isinstance(enabled_vals, dict):
            return
        for key in self.value:
            if not enabled_vals.get(key):
                hero = YAML_KEY_TO_HERO.get(key, key)
                raise OptionError(
                    f"{player_name}: Goal hero {hero} must be set to 1 in Enabled Heroes."
                )


class RolePasses(DefaultOnToggle):
    """When on, each hero needs its unlock item and a role pass (Tank, Bruiser, Support, Melee Assassin, or Ranged Assassin). Healers and utility supports use Support Pass."""
    display_name = "Role Passes"


class ExtraStartingHeroes(Range):
    """
    Random extra heroes unlocked at start with the starting hero. All extras share one role
    pass when Role Passes is on. Up to 4 extras (5 starting heroes total).
    """
    display_name = "Extra Starting Heroes"
    range_start = 0
    range_end = 4
    default = 1


class HeroPoolSize(Range):
    """
    Randomly include this many heroes from those set to 1 in Enabled Heroes.
    Set to 0 to include all your enabled_heroes.
    """
    display_name = "Hero Pool Size"
    range_start = 0
    range_end = len(ALL_HEROES)
    default = 0


class CumulativeChecks(DefaultOnToggle):
    """
    When on, stat-based hero checks (damage, healing, takedowns, etc.) add up across
    games with that hero. Win and reach level 20 still require a single match.
    """
    display_name = "Cumulative Checks"
    default = 1


class RemoveLevel20Check(DefaultOnToggle):
    """
    When on, the reach level 20 check is removed from every hero.
    Also excludes level 20 from random talent checks (if enabled).
    """
    display_name = "Remove Level 20 Check"
    default = 0


class IncludeTimedWinCheck(DefaultOnToggle):
    """
    When Role Passes is on, add one timed win check per role pass bucket (win in under 18 minutes).
    Any currently unlocked hero in that pass can achieve the check.
    """
    display_name = "Include Timed Win Check"
    default = 0


class RandomTalentsPerHero(Range):
    """
    How many random talent slots are forced on each selected hero.
    0 disables random talent checks. Each matching slot on a win is its own check.
    See the Talents tab for which slots to pick.
    """
    display_name = "Random Talents Per Hero"
    range_start = 0
    range_end = 7
    default = 0


class RandomTalentHeroCount(Range):
    """
    How many heroes in the seed receive random talent assignments.
    Capped at the number of heroes in the seed. Heroes are chosen at random.
    0 disables random talent checks (even if Random Talents Per Hero is above 0).
    """
    display_name = "Random Talent Hero Count"
    range_start = 0
    range_end = len(ALL_HEROES)
    default = 0


class DailyQuests(DefaultOnToggle):
    """
    When on, roll up to 3 cumulative daily quests from check families that have
    at least 5 matching heroes in the pool. Examples: Collect 150 regen globes,
    Kill 200 minions, Restore 200,000 health, etc..
    """
    display_name = "Daily Quests"
    default = 1


@dataclass
class HoTSOptions(PerGameCommonOptions):
    enabled_heroes: EnabledHeroes
    hero_pool_size: HeroPoolSize
    cumulative_checks: CumulativeChecks
    remove_level_20_check: RemoveLevel20Check
    goal: GoalMode
    goal_hero_count: GoalHeroCount
    goal_heroes: GoalHeroes
    role_passes: RolePasses
    extra_starting_heroes: ExtraStartingHeroes
    include_timed_win_check: IncludeTimedWinCheck
    random_talents_per_hero: RandomTalentsPerHero
    random_talent_hero_count: RandomTalentHeroCount
    daily_quests: DailyQuests


hots_option_groups = [
    OptionGroup("Heroes", [EnabledHeroes, HeroPoolSize, CumulativeChecks, RemoveLevel20Check]),
    OptionGroup("Victory", [GoalMode, GoalHeroCount, GoalHeroes]),
    OptionGroup("Unlock System", [RolePasses, ExtraStartingHeroes, IncludeTimedWinCheck]),
    OptionGroup("Quests", [DailyQuests]),
    OptionGroup("Talents", [RandomTalentsPerHero, RandomTalentHeroCount]),
]
