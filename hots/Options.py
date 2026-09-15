from dataclasses import dataclass
from Options import (
    OptionCounter, OptionSet, OptionList, Choice, Range, Toggle, DefaultOnToggle,
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


class PartyMode(Toggle):
    """
    When enabled, builds the seed for a group. Heroes unlock in waves (Progressive Hero Wave).
    Role Passes, Extra Starting Heroes, and Shards are ignored.

    Use this option if you have a group of players that want to play the multiworld together.
    """
    display_name = "Party Mode"
    default = 0


class PartySize(Range):
    """
    Party Mode only. How many players the seed is built for (2–5).
    Each wave unlocks this many heroes together.
    """
    display_name = "Party Size"
    range_start = 2
    range_end = 5
    default = 2


class StartingWaves(Range):
    """
    Party Mode only. How many hero waves start already unlocked.
    1 = one hero per party size. 2–3 grants that many unlocked waves.

    Example: Party Size:3 + Starting Waves:2 will give 6 heroes at the start.
    """
    display_name = "Starting Waves"
    range_start = 1
    range_end = 3
    default = 1


class RolePasses(DefaultOnToggle):
    """When on, each hero needs its unlock item and a role pass (Tank, Bruiser, Support, Melee Assassin, or Ranged Assassin). Healers and utility supports use Support Pass. Ignored when Party Mode is on."""
    display_name = "Role Passes"


class ExtraStartingHeroes(Range):
    """
    Random extra heroes unlocked at start with the starting hero. All extras share one role
    pass when Role Passes is on. Up to 4 extras (5 starting heroes total).
    Ignored when Party Mode is on (use Starting Waves).
    """
    display_name = "Extra Starting Heroes"
    range_start = 0
    range_end = 4
    default = 1


class ShardsPerHero(Range):
    """
    How many shards it takes to unlock a hero.
    0 = no shards; every hero is a single unlock item.
    1-5 = total shards spread across the multiworld needed to unlock each hero.
    Ignored when Party Mode is on.
    """
    display_name = "Shards Per Hero"
    range_start = 0
    range_end = 5
    default = 5


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
    0 disables random talent checks. Each matching slot is its own check.
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


class CreditMode(Choice):
    """
    Who gets credit from a replay.

    me: Only your /name.
    team: Unlocked heroes on your team. Empty Credit Names = whole team.
    match: Unlocked heroes in the game. Empty Credit Names = everyone.

    """
    display_name = "Credit Mode"
    option_me = 0
    option_team = 1
    option_match = 2
    default = 0


class CreditNames(OptionList):
    """
    Use this option to filter specific players when Credit Mode is team or match.
    Leave empty to credit everyone that mode allows. Your entire team or match.
    Listing names means ONLY those players get credit (include yourself if you want your row).

    Use the scoreboard / replay name (usually BattleTag without #1234).
    """
    display_name = "Credit Names"
    default = []


class IncludeAI(Toggle):
    """
    Also credit computer players allowed by Credit Mode.
    """
    display_name = "Include AI"
    default = 0


@dataclass
class HoTSOptions(PerGameCommonOptions):
    enabled_heroes: EnabledHeroes
    hero_pool_size: HeroPoolSize
    goal: GoalMode
    goal_hero_count: GoalHeroCount
    goal_heroes: GoalHeroes
    party_mode: PartyMode
    party_size: PartySize
    starting_waves: StartingWaves
    role_passes: RolePasses
    extra_starting_heroes: ExtraStartingHeroes
    shards_per_hero: ShardsPerHero
    include_timed_win_check: IncludeTimedWinCheck
    cumulative_checks: CumulativeChecks
    remove_level_20_check: RemoveLevel20Check
    random_talents_per_hero: RandomTalentsPerHero
    random_talent_hero_count: RandomTalentHeroCount
    daily_quests: DailyQuests
    credit_mode: CreditMode
    credit_names: CreditNames
    include_ai: IncludeAI


hots_option_groups = [
    OptionGroup("Heroes", [EnabledHeroes, HeroPoolSize]),
    OptionGroup("Victory", [GoalMode, GoalHeroCount, GoalHeroes]),
    OptionGroup("Party Mode", [PartyMode, PartySize, StartingWaves]),
    OptionGroup("Unlock System", [RolePasses, ExtraStartingHeroes, ShardsPerHero, IncludeTimedWinCheck]),
    OptionGroup("Checks", [CumulativeChecks, RemoveLevel20Check]),
    OptionGroup("Talents", [RandomTalentsPerHero, RandomTalentHeroCount]),
    OptionGroup("Quests", [DailyQuests]),
    OptionGroup("Replay Scoring", [CreditMode, CreditNames, IncludeAI]),
]
