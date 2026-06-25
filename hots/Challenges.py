import unicodedata

WIN = "win"

XP_8K = "xp_8k"
XP_12K = "xp_12k"
LEVEL_20 = "level_20"

TAKEDOWNS_1 = "takedowns_1"
TAKEDOWNS_5 = "takedowns_5"
TAKEDOWNS_10 = "takedowns_10"
TAKEDOWNS_15 = "takedowns_15"

HERO_25K = "hero_25k"
HERO_40K = "hero_40k"
HERO_50K = "hero_50k"
SIEGE_50K = "siege_50k"
SIEGE_75K = "siege_75k"
SIEGE_100K = "siege_100k"
HEALING_40K = "healing_40k"
HEALING_60K = "healing_60k"

SOLO_KILL_1 = "solo_kill_1"
SOLO_KILL_3 = "solo_kill_3"
MINION_15 = "minion_15"
MINION_25 = "minion_25"
MINION_40 = "minion_40"
MINION_50 = "minion_50"
ASSISTS_8 = "assists_8"
MERC_2 = "merc_2"

COMMON_CHECKS = [WIN, XP_8K, XP_12K, LEVEL_20]

CHECK_DESCRIPTIONS: dict[str, str] = {
    WIN:           "Win a match",
    XP_8K:         "Collect 8,000 experience",
    XP_12K:        "Collect 12,000 experience",
    LEVEL_20:      "Reach level 20",
    TAKEDOWNS_1:   "Get 1 takedown",
    TAKEDOWNS_5:   "Get 5 takedowns",
    TAKEDOWNS_10:  "Get 10 takedowns",
    TAKEDOWNS_15:  "Get 15 takedowns",
    HERO_25K:      "Deal 25,000 hero damage",
    HERO_40K:      "Deal 40,000 hero damage",
    HERO_50K:      "Deal 50,000 hero damage",
    SIEGE_50K:     "Deal 50,000 siege damage",
    SIEGE_75K:     "Deal 75,000 siege damage",
    SIEGE_100K:    "Deal 100,000 siege damage",
    HEALING_40K:   "Restore 40,000 health",
    HEALING_60K:   "Restore 60,000 health",
    SOLO_KILL_1:   "Get 1 solo kill",
    SOLO_KILL_3:   "Get 3 solo kills",
    MINION_15:     "Kill 15 minions",
    MINION_25:     "Kill 25 minions",
    MINION_40:     "Kill 40 minions",
    MINION_50:     "Kill 50 minions",
    ASSISTS_8:     "Get 8 assists",
    MERC_2:        "Capture 2 mercenary camps",
}

ROLE_CHECKS: dict[str, list[str]] = {
    "assassin": COMMON_CHECKS + [
        TAKEDOWNS_5, TAKEDOWNS_10, TAKEDOWNS_15,
        HERO_50K,
        SOLO_KILL_1, SOLO_KILL_3,
        MINION_40,
    ],
    "warrior": COMMON_CHECKS + [
        TAKEDOWNS_5, TAKEDOWNS_10, TAKEDOWNS_15,
        HERO_25K, HERO_40K,
        SOLO_KILL_1,
        MINION_25,
        MERC_2,
    ],
    "support": COMMON_CHECKS + [
        TAKEDOWNS_1, TAKEDOWNS_5,
        HEALING_40K, HEALING_60K,
        MINION_15,
        ASSISTS_8,
    ],
    "specialist": COMMON_CHECKS + [
        TAKEDOWNS_5, TAKEDOWNS_10,
        SIEGE_50K, SIEGE_75K, SIEGE_100K,
        MINION_50,
        MERC_2,
    ],
}

HERO_ROLES: dict[str, str] = {
    "Alexstrasza": "support", "Ana": "support", "Anduin": "support",
    "Auriel": "support", "Brightwing": "support", "Deckard": "support",
    "Kharazim": "support", "Li Li": "support", "Lt. Morales": "support",
    "Lúcio": "support", "Malfurion": "support", "Rehgar": "support",
    "Stukov": "support", "Tyrande": "support", "Uther": "support",
    "Whitemane": "support",
    "Abathur": "specialist", "Azmodan": "specialist", "Blaze": "specialist",
    "Dehaka": "specialist", "Gazlowe": "specialist", "Hogger": "specialist",
    "Leoric": "specialist", "The Lost Vikings": "specialist", "Malthael": "specialist",
    "Medivh": "specialist", "Murky": "specialist", "Probius": "specialist",
    "Ragnaros": "specialist", "Rexxar": "specialist", "Samuro": "specialist",
    "Sonya": "specialist", "Xul": "specialist", "Zagara": "specialist",
    "Zeratul": "specialist", "Chromie": "specialist", "Nazeebo": "specialist",
    "Falstad": "specialist",
    "Anub'arak": "warrior", "Arthas": "warrior", "Artanis": "warrior",
    "Chen": "warrior", "Cho": "warrior", "Deathwing": "warrior",
    "Diablo": "warrior", "D.Va": "warrior", "E.T.C.": "warrior",
    "Garrosh": "warrior", "Imperius": "warrior", "Johanna": "warrior",
    "Mal'Ganis": "warrior", "Mei": "warrior", "Muradin": "warrior",
    "Stitches": "warrior", "The Butcher": "warrior", "Tyrael": "warrior",
    "Varian": "warrior", "Yrel": "warrior", "Zarya": "warrior",
}

ALL_HEROES: list[str] = sorted({
    *HERO_ROLES.keys(),
    "Alarak", "Cassia", "Chromie", "Falstad", "Fenix", "Gall", "Genji",
    "Greymane", "Gul'dan", "Hanzo", "Illidan", "Jaina", "Junkrat",
    "Kael'thas", "Kel'Thuzad", "Kerrigan", "Li-Ming", "Lunara", "Maiev",
    "Mephisto", "Nazeebo", "Nova", "Orphea", "Qhira", "Raynor", "Sgt. Hammer",
    "Sylvanas", "Tassadar", "Thrall", "Tracer", "Tychus", "Valeera",
    "Valla", "Zul'jin",
})

for _hero in ALL_HEROES:
    HERO_ROLES.setdefault(_hero, "assassin")

_YAML_KEY_OVERRIDES: dict[str, str] = {
    "Anub'arak":          "Anubarak",
    "D.Va":               "DVa",
    "E.T.C.":             "ETC",
    "Gul'dan":            "Guldan",
    "Kael'thas":          "Kaelthas",
    "Kel'Thuzad":         "KelThuzad",
    "Li Li":              "LiLi",
    "Li-Ming":            "LiMing",
    "Lúcio":              "Lucio",
    "Lt. Morales":        "LtMorales",
    "Mal'Ganis":          "MalGanis",
    "Sgt. Hammer":        "SgtHammer",
    "The Butcher":        "TheButcher",
    "The Lost Vikings":   "TheLostVikings",
    "Zul'jin":            "Zuljin",
}

HERO_TO_YAML_KEY: dict[str, str] = {
    hero: _YAML_KEY_OVERRIDES.get(hero, hero) for hero in ALL_HEROES
}
YAML_KEY_TO_HERO: dict[str, str] = {v: k for k, v in HERO_TO_YAML_KEY.items()}


def normalize_hero_yaml_key(key: str) -> str:
    if key in YAML_KEY_TO_HERO:
        return key
    if key in HERO_TO_YAML_KEY:
        return HERO_TO_YAML_KEY[key]
    lowered = key.lower().replace(" ", "").replace("'", "").replace(".", "").replace("-", "")
    if lowered in ("lucio", "lcio"):
        return "Lucio"
    for display, yaml_key in HERO_TO_YAML_KEY.items():
        norm = display.lower().replace(" ", "").replace("'", "").replace(".", "").replace("-", "")
        if norm == lowered:
            return yaml_key
    return key


def yaml_key_to_hero(key: str) -> str | None:
    yaml_key = normalize_hero_yaml_key(key)
    return YAML_KEY_TO_HERO.get(yaml_key)


def get_role(hero: str) -> str:
    return HERO_ROLES.get(hero, "assassin")


HERO_CHECKS: dict[str, list[str]] = {
    hero: list(ROLE_CHECKS[get_role(hero)])
    for hero in ALL_HEROES
}

EASY_MODE_REMOVED: dict[str, frozenset[str]] = {
    "assassin": frozenset({XP_12K, LEVEL_20, TAKEDOWNS_15, HERO_50K}),
    "warrior": frozenset({XP_12K, LEVEL_20, TAKEDOWNS_15, HERO_40K}),
    "support": frozenset({XP_12K, LEVEL_20, TAKEDOWNS_5, HEALING_60K, ASSISTS_8}),
    "specialist": frozenset({XP_12K, LEVEL_20, TAKEDOWNS_10, SIEGE_100K}),
}


def active_role_checks(role: str, remove_hardest: bool = False) -> list[str]:
    checks = ROLE_CHECKS[role]
    if not remove_hardest:
        return list(checks)
    removed = EASY_MODE_REMOVED[role]
    return [check for check in checks if check not in removed]

def _normalize_hero_name(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name)
    return "".join(c.lower() for c in folded if c.isalnum())


def location_name(hero: str, check_key: str) -> str:
    return f"{hero}: {CHECK_DESCRIPTIONS[check_key]}"


def hero_from_replay_name(replay_hero: str) -> str | None:
    """Resolve replay.details m_hero display name to a world hero."""
    if not replay_hero:
        return None
    replay_norm = _normalize_hero_name(replay_hero)
    for hero in ALL_HEROES:
        if _normalize_hero_name(hero) == replay_norm:
            return hero
    return None

def detect_checks(score: dict, result: str, level_history: list | None = None) -> set[str]:
    fired: set[str] = set()
    if result == "Win":
        fired.add(WIN)

    max_level = max(level_history or [0], default=0)
    if max_level >= 20:
        fired.add(LEVEL_20)

    xp = score.get("ExperienceContribution", 0)
    if xp >= 8_000:
        fired.add(XP_8K)
    if xp >= 12_000:
        fired.add(XP_12K)

    takedowns = score.get("Takedowns", 0)
    if takedowns >= 1:
        fired.add(TAKEDOWNS_1)
    if takedowns >= 5:
        fired.add(TAKEDOWNS_5)
    if takedowns >= 10:
        fired.add(TAKEDOWNS_10)
    if takedowns >= 15:
        fired.add(TAKEDOWNS_15)

    hero_damage = score.get("HeroDamage", 0)
    if hero_damage >= 25_000:
        fired.add(HERO_25K)
    if hero_damage >= 40_000:
        fired.add(HERO_40K)
    if hero_damage >= 50_000:
        fired.add(HERO_50K)

    siege = score.get("SiegeDamage", 0)
    if siege >= 50_000:
        fired.add(SIEGE_50K)
    if siege >= 75_000:
        fired.add(SIEGE_75K)
    if siege >= 100_000:
        fired.add(SIEGE_100K)

    healing = score.get("Healing", 0)
    if healing >= 40_000:
        fired.add(HEALING_40K)
    if healing >= 60_000:
        fired.add(HEALING_60K)

    solo = score.get("SoloKill", 0)
    if solo >= 1:
        fired.add(SOLO_KILL_1)
    if solo >= 3:
        fired.add(SOLO_KILL_3)

    minions = score.get("MinionKills", 0)
    if minions >= 15:
        fired.add(MINION_15)
    if minions >= 25:
        fired.add(MINION_25)
    if minions >= 40:
        fired.add(MINION_40)
    if minions >= 50:
        fired.add(MINION_50)

    if score.get("Assists", 0) >= 8:
        fired.add(ASSISTS_8)
    if score.get("MercCampCaptures", 0) >= 2:
        fired.add(MERC_2)

    return fired
