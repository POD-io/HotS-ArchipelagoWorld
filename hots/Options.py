from dataclasses import dataclass
import random
from Options import (
    OptionCounter, Choice, Range, TextChoice, DefaultOnToggle,
    PerGameCommonOptions, OptionGroup, OptionError,
)
from .Challenges import ALL_HEROES, YAML_KEY_TO_HERO, normalize_hero_yaml_key, yaml_key_to_hero


def resolve_goal_hero_name(goal_hero: "GoalHero") -> str:
    hero = goal_hero.value
    if isinstance(hero, int):
        hero = goal_hero.current_key
    if isinstance(hero, str):
        hero = yaml_key_to_hero(hero) or hero
    return hero


class EnabledHeroes(OptionCounter):
    """Set each hero to 1 to enable them for use in this seed, or 0 to exclude them."""
    display_name = "Enabled Heroes"
    valid_keys = sorted(YAML_KEY_TO_HERO.keys())
    min = 0
    max = 1
    cull_zeroes = False
    default = {key: 1 for key in YAML_KEY_TO_HERO}

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
            YAML_KEY_TO_HERO[key]
            for key, enabled in self.value.items()
            if enabled and key in YAML_KEY_TO_HERO
        )


class GoalMode(Choice):
    """
    random_heroes: Complete all checks for N random enabled heroes.
    specific_hero: Complete all checks for one chosen hero.
    distinct_wins: Win one match each with N random enabled heroes.
    """
    display_name = "Goal"
    option_random_heroes = 0
    option_specific_hero = 1
    option_distinct_wins = 2
    default = 0


class GoalHeroCount(Range):
    """Number of heroes used when Goal is random_heroes or distinct_wins."""
    display_name = "Goal Hero Count"
    range_start = 1
    range_end = 20
    default = 3


class GoalHero(TextChoice):
    """Hero to complete when Goal is specific_hero."""
    display_name = "Goal Hero"
    default = "Alarak"

    vars().update({
        f"option_{yaml_key}": yaml_key
        for yaml_key in sorted(YAML_KEY_TO_HERO.keys())
    })

    @classmethod
    def from_text(cls, text: str):
        if text.lower() == "random":
            return cls(random.choice(list(cls.name_lookup)))
        for option_name, value in cls.options.items():
            if option_name.lower() == text.lower():
                return cls(value)
        resolved = yaml_key_to_hero(text) or text
        return cls(resolved)

    def verify(self, world, player_name, plando_options):
        super().verify(world, player_name, plando_options)
        hero = resolve_goal_hero_name(self)
        if hero not in ALL_HEROES:
            raise OptionError(f"{player_name}: Unknown goal hero: {hero!r}")
        # Enabled-hero cross-check runs in HoTSWorld.generate_early when goal is specific_hero.


class RolePasses(DefaultOnToggle):
    """When on, each hero needs its unlock item and a role pass (Tank, Bruiser, Support, Melee Assassin, or Ranged Assassin). Healers and utility supports use Support Pass."""
    display_name = "Role Passes"


class HeroPoolSize(Range):
    """
    Randomly include this many heroes from those set to 1 in Enabled Heroes.
    When Goal is specific_hero, the goal hero is always kept in the pool.
    """
    display_name = "Hero Pool Size"
    range_start = 0
    range_end = len(ALL_HEROES)
    default = 0


class RemoveHardestChecks(DefaultOnToggle):
    """
    When off, every role keeps all checks. When on, each role drops its hardest checks:
    highest takedown count, highest hero/heal/siege/damage tier, 8 assists (healers),
    3 solo kills (melee assassins), level 20, and 12k XP.
    """
    display_name = "Remove Hardest Checks"
    default = 0


@dataclass
class HoTSOptions(PerGameCommonOptions):
    enabled_heroes: EnabledHeroes
    hero_pool_size: HeroPoolSize
    remove_hardest_checks: RemoveHardestChecks
    goal:             GoalMode
    goal_hero_count:  GoalHeroCount
    goal_hero:        GoalHero
    role_passes:      RolePasses


hots_option_groups = [
    OptionGroup("Heroes", [EnabledHeroes, HeroPoolSize, RemoveHardestChecks]),
    OptionGroup("Victory", [GoalMode, GoalHeroCount, GoalHero]),
    OptionGroup("Unlock System", [RolePasses]),
]
