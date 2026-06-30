import unicodedata

WIN = "win"

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

COMMON_CHECKS = [WIN, LEVEL_20]

CHECK_DESCRIPTIONS: dict[str, str] = {
    WIN:                 "Win a match",
    LEVEL_20:            "Reach level 20",
    TAKEDOWNS_1:         "Get 1 takedown",
    TAKEDOWNS_5:         "Get 5 takedowns",
    TAKEDOWNS_10:        "Get 10 takedowns",
    TAKEDOWNS_15:        "Get 15 takedowns",
    HERO_25K:            "Deal 25,000 hero damage",
    HERO_40K:            "Deal 40,000 hero damage",
    HERO_50K:            "Deal 50,000 hero damage",
    SIEGE_50K:           "Deal 50,000 siege damage",
    SIEGE_75K:           "Deal 75,000 siege damage",
    SIEGE_100K:          "Deal 100,000 siege damage",
    HEALING_40K:         "Restore 40,000 health",
    HEALING_60K:         "Restore 60,000 health",
    SOLO_KILL_1:         "Get 1 solo kill",
    SOLO_KILL_3:         "Get 3 solo kills",
    MINION_15:           "Kill 15 minions",
    MINION_25:           "Kill 25 minions",
    MINION_40:           "Kill 40 minions",
    MINION_50:           "Kill 50 minions",
    ASSISTS_8:           "Get 8 assists",
    MERC_2:              "Capture 2 mercenary camps",
}

ROLE_CHECKS: dict[str, list[str]] = {
    "tank": COMMON_CHECKS + [
        TAKEDOWNS_5, TAKEDOWNS_10, TAKEDOWNS_15,
        HERO_25K,
        ASSISTS_8,
        MERC_2,
    ],
    "bruiser": COMMON_CHECKS + [
        TAKEDOWNS_5, TAKEDOWNS_10, TAKEDOWNS_15,
        HERO_40K, HERO_50K,
        SOLO_KILL_1,
        MERC_2,
    ],
    "healer": COMMON_CHECKS + [
        TAKEDOWNS_1, TAKEDOWNS_5, TAKEDOWNS_10,
        HEALING_40K, HEALING_60K,
        ASSISTS_8,
    ],
    "support": COMMON_CHECKS + [
        TAKEDOWNS_1, TAKEDOWNS_5, TAKEDOWNS_10,
        ASSISTS_8,
        SIEGE_50K,
    ],
    "melee_assassin": COMMON_CHECKS + [
        TAKEDOWNS_5, TAKEDOWNS_10, TAKEDOWNS_15,
        HERO_50K,
        SOLO_KILL_1, SOLO_KILL_3,
    ],
    "ranged_assassin": COMMON_CHECKS + [
        TAKEDOWNS_5, TAKEDOWNS_10, TAKEDOWNS_15,
        HERO_50K,
        SIEGE_50K, SIEGE_75K,
    ],
}

HERO_ROLES: dict[str, str] = {
    # Tank
    "Anub'arak": "tank", "Arthas": "tank", "Blaze": "tank", "Cho": "tank",
    "Diablo": "tank", "E.T.C.": "tank", "Garrosh": "tank", "Johanna": "tank",
    "Mal'Ganis": "tank", "Muradin": "tank", "Stitches": "tank", "Tyrael": "tank",
    # Bruiser
    "Artanis": "bruiser", "Chen": "bruiser", "D.Va": "bruiser", "Dehaka": "bruiser",
    "Deathwing": "bruiser", "Imperius": "bruiser", "Leoric": "bruiser",
    "Malthael": "bruiser", "Mei": "bruiser", "Ragnaros": "bruiser", "Rexxar": "bruiser",
    "Sonya": "bruiser", "Thrall": "bruiser", "Varian": "bruiser", "Xul": "bruiser",
    "Yrel": "bruiser",
    # Healer
    "Alexstrasza": "healer", "Ana": "healer", "Anduin": "healer", "Auriel": "healer",
    "Brightwing": "healer", "Deckard": "healer", "Kharazim": "healer", "Li Li": "healer",
    "Lt. Morales": "healer", "Lúcio": "healer", "Malfurion": "healer", "Rehgar": "healer",
    "Stukov": "healer", "Tyrande": "healer", "Uther": "healer", "Whitemane": "healer",
    # Support (macro / siege bucket — not healer; no healing checks)
    "Abathur": "support", "Gazlowe": "support", "Medivh": "support", "Murky": "support",
    "The Lost Vikings": "support", "Zarya": "support",
    # Melee Assassin
    "Alarak": "melee_assassin", "Hogger": "melee_assassin",
    "Illidan": "melee_assassin", "Kerrigan": "melee_assassin", "Maiev": "melee_assassin",
    "Qhira": "melee_assassin", "Samuro": "melee_assassin",
    "The Butcher": "melee_assassin", "Valeera": "melee_assassin", "Zeratul": "melee_assassin",
    # Ranged Assassin
    "Azmodan": "ranged_assassin", "Cassia": "ranged_assassin", "Chromie": "ranged_assassin",
    "Falstad": "ranged_assassin", "Fenix": "ranged_assassin", "Gall": "ranged_assassin",
    "Genji": "ranged_assassin", "Greymane": "ranged_assassin", "Gul'dan": "ranged_assassin",
    "Hanzo": "ranged_assassin", "Jaina": "ranged_assassin", "Junkrat": "ranged_assassin",
    "Kael'thas": "ranged_assassin", "Kel'Thuzad": "ranged_assassin", "Li-Ming": "ranged_assassin",
    "Lunara": "ranged_assassin", "Mephisto": "ranged_assassin", "Nazeebo": "ranged_assassin",
    "Nova": "ranged_assassin", "Orphea": "ranged_assassin", "Probius": "ranged_assassin",
    "Raynor": "ranged_assassin", "Sgt. Hammer": "ranged_assassin", "Sylvanas": "ranged_assassin",
    "Tassadar": "ranged_assassin",
    "Tracer": "ranged_assassin", "Tychus": "ranged_assassin", "Valla": "ranged_assassin",
    "Zagara": "ranged_assassin", "Zul'jin": "ranged_assassin",
}

ALL_HEROES: list[str] = sorted(HERO_ROLES.keys())

PASS_KEYS: list[str] = ["tank", "bruiser", "support", "melee_assassin", "ranged_assassin"]

PASS_NAMES: dict[str, str] = {
    "tank": "Tank Pass",
    "bruiser": "Bruiser Pass",
    "support": "Support Pass",
    "melee_assassin": "Melee Assassin Pass",
    "ranged_assassin": "Ranged Assassin Pass",
}

ROLE_TO_PASS: dict[str, str] = {
    "tank": "tank",
    "bruiser": "bruiser",
    "healer": "support",
    "support": "support",
    "melee_assassin": "melee_assassin",
    "ranged_assassin": "ranged_assassin",
}

ROLE_DISPLAY: dict[str, str] = {
    "tank": "Tank",
    "bruiser": "Bruiser",
    "healer": "Healer",
    "support": "Specialist",  # macro/siege bucket; healing checks live on healer only
    "melee_assassin": "Melee Assassin",
    "ranged_assassin": "Ranged Assassin",
}

ITEM_NAME_TO_PASS_KEY: dict[str, str] = {name: key for key, name in PASS_NAMES.items()}

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
    """Check-role tag used for location check lists."""
    return HERO_ROLES[hero]


def get_pass_key(hero: str) -> str:
    """Pass bucket used for unlock items."""
    return ROLE_TO_PASS[get_role(hero)]


def pass_name_for_key(pass_key: str) -> str:
    return PASS_NAMES[pass_key]


def pass_key_from_item_name(item_name: str) -> str | None:
    return ITEM_NAME_TO_PASS_KEY.get(item_name)


def role_display(role: str) -> str:
    return ROLE_DISPLAY.get(role, role.replace("_", " ").title())


EASY_MODE_REMOVED: dict[str, frozenset[str]] = {
    "tank": frozenset({LEVEL_20, TAKEDOWNS_15, HERO_25K}),
    "bruiser": frozenset({LEVEL_20, TAKEDOWNS_15, HERO_50K}),
    "healer": frozenset({LEVEL_20, TAKEDOWNS_10, HEALING_60K, ASSISTS_8}),
    "support": frozenset({LEVEL_20, TAKEDOWNS_10, SIEGE_50K}),
    "melee_assassin": frozenset({LEVEL_20, TAKEDOWNS_15, HERO_50K, SOLO_KILL_3}),
    "ranged_assassin": frozenset({LEVEL_20, TAKEDOWNS_15, HERO_50K, SIEGE_75K}),
}


def active_role_checks(role: str, remove_hardest: bool = False) -> list[str]:
    checks = ROLE_CHECKS[role]
    if not remove_hardest:
        return list(checks)
    removed = EASY_MODE_REMOVED[role]
    return [check for check in checks if check not in removed]


# Per-hero check lists when a role bucket is a poor fit.
HERO_CHECK_OVERRIDES: dict[str, list[str]] = {}


def _base_checks_for_hero(hero: str) -> list[str]:
    if hero in HERO_CHECK_OVERRIDES:
        return list(HERO_CHECK_OVERRIDES[hero])
    return list(ROLE_CHECKS[get_role(hero)])


def checks_for_hero(hero: str, remove_hardest: bool = False) -> list[str]:
    if hero in HERO_CHECK_OVERRIDES:
        return list(HERO_CHECK_OVERRIDES[hero])
    return active_role_checks(get_role(hero), remove_hardest)


HERO_CHECKS: dict[str, list[str]] = {
    hero: _base_checks_for_hero(hero)
    for hero in ALL_HEROES
}


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
