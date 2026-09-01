import unicodedata

WIN = "win"

XP_PASS_18K = "xp_pass_18k"
XP_PASS_40K = "xp_pass_40k"
TIMED_WIN_18 = "timed_win_18"

PASS_XP_CHECKS: list[str] = [XP_PASS_18K, XP_PASS_40K]
PASS_TIMED_WIN_CHECKS: list[str] = [TIMED_WIN_18]

PASS_XP_THRESHOLDS: dict[str, int] = {
    XP_PASS_18K: 18_000,
    XP_PASS_40K: 40_000,
}

TIMED_WIN_MAX_SECONDS = 18 * 60

LEVEL_20 = "level_20"

CHECK_DESCRIPTIONS: dict[str, str] = {
    WIN:                 "Win a match",
    LEVEL_20:            "Reach level 20",
    XP_PASS_18K:         "Amass 18,000 XP",
    XP_PASS_40K:         "Amass 40,000 XP",
    TIMED_WIN_18:        "Win in under 18 minutes",
}

HERO_ROLES: dict[str, str] = {
    # Tank
    "Anub'arak": "tank", "Arthas": "tank", "Blaze": "tank", "Cho": "tank",
    "Diablo": "tank", "E.T.C.": "tank", "Garrosh": "tank", "Johanna": "tank",
    "Mal'Ganis": "tank", "Mei": "tank", "Muradin": "tank", "Stitches": "tank",
    "Tyrael": "tank",
    # Bruiser
    "Artanis": "bruiser", "Chen": "bruiser", "D.Va": "bruiser", "Dehaka": "bruiser",
    "Gazlowe": "bruiser",
    "Deathwing": "bruiser", "Imperius": "bruiser", "Leoric": "bruiser",
    "Malthael": "bruiser", "Ragnaros": "bruiser", "Rexxar": "bruiser",
    "Sonya": "bruiser", "Thrall": "bruiser", "Varian": "bruiser", "Xul": "bruiser",
    "Yrel": "bruiser",
    # Healer
    "Alexstrasza": "healer", "Ana": "healer", "Anduin": "healer", "Auriel": "healer",
    "Brightwing": "healer", "Deckard": "healer", "Kharazim": "healer", "Li Li": "healer",
    "Lt. Morales": "healer", "Lúcio": "healer", "Malfurion": "healer", "Rehgar": "healer",
    "Stukov": "healer", "Tyrande": "healer", "Uther": "healer", "Whitemane": "healer",
    # Support (macro / siege bucket — not healer; no healing checks)
    "Abathur": "support", "Medivh": "support", "Murky": "support",
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

def hero_sort_key(hero: str) -> str:
    name = hero
    if name.lower().startswith("the "):
        name = name[4:]
    return name.casefold()

ALL_HEROES: list[str] = sorted(HERO_ROLES.keys(), key=hero_sort_key)

CAP_WIN = "can_win"
CAP_LEVEL_20 = "can_level_20"
CAP_TAKEDOWN = "can_takedown"
CAP_HERO_DAMAGE = "can_hero_damage"
CAP_SIEGE = "can_siege"
CAP_HEAL = "can_heal"
CAP_SELF_HEAL = "can_self_heal"
CAP_PROTECT = "can_protect"
CAP_SOLO_KILL = "can_solo_kill"
CAP_MINION = "can_minion"
CAP_ASSIST = "can_assist"
CAP_MERC = "can_merc"
CAP_REGEN_GLOBE = "can_regen_globe"
CAP_STUN = "can_stun"
CAP_SILENCE = "can_silence"

ALL_CAPABILITIES: tuple[str, ...] = (
    CAP_WIN, CAP_LEVEL_20, CAP_TAKEDOWN, CAP_HERO_DAMAGE, CAP_SIEGE,
    CAP_HEAL, CAP_SELF_HEAL, CAP_PROTECT, CAP_SOLO_KILL, CAP_MINION,
    CAP_ASSIST, CAP_MERC, CAP_REGEN_GLOBE, CAP_STUN, CAP_SILENCE,
)

CAPABILITY_CHECK_KEYS: dict[str, tuple[str, ...]] = {
    CAP_WIN: (WIN,),
    CAP_LEVEL_20: (LEVEL_20,),
}

HERO_CAPABILITY_CHECKS: dict[str, dict[str, str]] = {}

CAPABILITY_HEROES: dict[str, frozenset[str]] = {
    cap: frozenset() for cap in ALL_CAPABILITIES
}

def _apply_hero_tier_tables(
    hero_checks: dict[str, dict[str, str]],
    descriptions: dict[str, str],
    thresholds: dict[str, dict],
) -> None:
    global CAPABILITY_CHECK_KEYS, CAPABILITY_HEROES, HERO_CAPABILITY_CHECKS
    global CHECK_DESCRIPTIONS, CHECK_SCORE_THRESHOLDS

    HERO_CAPABILITY_CHECKS = {
        hero: dict(caps)
        for hero, caps in hero_checks.items()
        if hero in HERO_ROLES
    }
    for hero in ALL_HEROES:
        HERO_CAPABILITY_CHECKS.setdefault(hero, {})[CAP_WIN] = WIN

    pools: dict[str, set[str]] = {cap: set() for cap in ALL_CAPABILITIES}
    for hero, caps in HERO_CAPABILITY_CHECKS.items():
        for cap in caps:
            if cap in pools:
                pools[cap].add(hero)
    CAPABILITY_HEROES = {cap: frozenset(heroes) for cap, heroes in pools.items()}

    keys_by_cap: dict[str, list[str]] = {cap: [] for cap in ALL_CAPABILITIES}
    seen_by_cap: dict[str, set[str]] = {cap: set() for cap in ALL_CAPABILITIES}
    for caps in HERO_CAPABILITY_CHECKS.values():
        for cap, key in caps.items():
            if cap not in seen_by_cap or key in seen_by_cap[cap]:
                continue
            seen_by_cap[cap].add(key)
            keys_by_cap[cap].append(key)
    CAPABILITY_CHECK_KEYS = {cap: tuple(keys_by_cap[cap]) for cap in ALL_CAPABILITIES}

    CHECK_DESCRIPTIONS.update({k: v for k, v in descriptions.items() if isinstance(v, str)})

    for key, meta in thresholds.items():
        if key == WIN:
            continue
        field = meta.get("field")
        threshold = meta.get("threshold")
        if field and isinstance(threshold, int):
            CHECK_SCORE_THRESHOLDS[key] = (field, threshold)

def hero_has_capability(hero: str, capability: str) -> bool:
    return capability in capabilities_for_hero(hero)

def capabilities_for_hero(hero: str) -> frozenset[str]:
    if HERO_CAPABILITY_CHECKS:
        return frozenset(HERO_CAPABILITY_CHECKS.get(hero, {CAP_WIN: WIN}))
    return frozenset(
        cap for cap, heroes in CAPABILITY_HEROES.items() if hero in heroes
    )

def check_key_for_hero_capability(hero: str, capability: str) -> str | None:
    if HERO_CAPABILITY_CHECKS:
        return HERO_CAPABILITY_CHECKS.get(hero, {}).get(capability)
    keys = CAPABILITY_CHECK_KEYS.get(capability) or ()
    return keys[0] if keys else None

def validate_capability_tables() -> None:
    for cap, heroes in CAPABILITY_HEROES.items():
        bad = [h for h in heroes if h not in HERO_ROLES]
        if bad:
            raise ValueError(f"{cap} has unknown heroes: {bad}")

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

def heroes_in_pass(pass_key: str, heroes: list[str] | None = None) -> list[str]:
    """Heroes whose unlock/pass bucket matches pass_key."""
    pool = heroes if heroes is not None else ALL_HEROES
    return [hero for hero in pool if get_pass_key(hero) == pass_key]

def pass_name_for_key(pass_key: str) -> str:
    return PASS_NAMES[pass_key]

def pass_key_from_item_name(item_name: str) -> str | None:
    return ITEM_NAME_TO_PASS_KEY.get(item_name)

def role_display(role: str) -> str:
    return ROLE_DISPLAY.get(role, role.replace("_", " ").title())

def pass_contributor_hint(pass_key: str) -> str | None:
    """Short tracker note when multiple check-roles share one pass bucket."""
    labels: list[str] = []
    for role, mapped_pass in ROLE_TO_PASS.items():
        if mapped_pass != pass_key:
            continue
        label = role_display(role)
        if label not in labels:
            labels.append(label)
    if len(labels) <= 1:
        return None
    pluralized = [f"{label}s" if not label.endswith("s") else label for label in labels]
    return f"{' + '.join(pluralized)} count toward this pass"

FORCED_CAPABILITIES: tuple[str, ...] = (CAP_WIN,)
ROLLED_CAPABILITIES_PER_HERO = 5

def all_check_keys_for_hero(hero: str) -> list[str]:
    caps = capabilities_for_hero(hero)
    keys: list[str] = []
    seen: set[str] = set()
    for cap in ALL_CAPABILITIES:
        if cap not in caps:
            continue
        key = check_key_for_hero_capability(hero, cap)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys

def _order_check_keys(hero: str, keys: list[str] | set[str]) -> list[str]:
    wanted = set(keys)
    return [k for k in all_check_keys_for_hero(hero) if k in wanted]

def roll_checks_for_hero(
    hero: str,
    rng,
    remove_level_20: bool = False,
    rolled_count: int = ROLLED_CAPABILITIES_PER_HERO,
) -> list[str]:
    caps = set(capabilities_for_hero(hero))
    if remove_level_20:
        caps.discard(CAP_LEVEL_20)

    forced_caps = [c for c in FORCED_CAPABILITIES if c in caps]
    rollable_caps = [
        c for c in ALL_CAPABILITIES
        if c in caps and c not in forced_caps and check_key_for_hero_capability(hero, c)
    ]
    n = min(rolled_count, len(rollable_caps))
    picked_caps = list(rng.sample(rollable_caps, n)) if n else []

    keys: list[str] = []
    for cap in (*forced_caps, *picked_caps):
        key = check_key_for_hero_capability(hero, cap)
        if key:
            keys.append(key)
    return _order_check_keys(hero, keys)

HERO_CHECKS: dict[str, list[str]] = {}

def _normalize_hero_name(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name)
    return "".join(c.lower() for c in folded if c.isalnum())

def location_name(hero: str, check_key: str) -> str:
    return f"{hero}: {CHECK_DESCRIPTIONS[check_key]}"

def pass_location_name(pass_key: str, check_key: str) -> str:
    return f"{pass_name_for_key(pass_key)}: {CHECK_DESCRIPTIONS[check_key]}"

def pass_check_keys_for_seed(use_role_passes: bool, include_timed_win: bool) -> list[str]:
    if not use_role_passes:
        return []
    keys = list(PASS_XP_CHECKS)
    if include_timed_win:
        keys.append(TIMED_WIN_18)
    return keys

def pass_location_names_for_seed(
    enabled_pass_keys: list[str],
    use_role_passes: bool,
    include_timed_win: bool,
) -> list[str]:
    return [
        pass_location_name(pass_key, check_key)
        for pass_key in enabled_pass_keys
        for check_key in pass_check_keys_for_seed(use_role_passes, include_timed_win)
    ]

def hero_from_replay_name(replay_hero: str) -> str | None:
    """Resolve replay.details m_hero display name to a world hero."""
    if not replay_hero:
        return None
    replay_norm = _normalize_hero_name(replay_hero)
    for hero in ALL_HEROES:
        if _normalize_hero_name(hero) == replay_norm:
            return hero
    return None

DAILY_QUEST_POOL_MIN = 5       # seed must include this many can_* heroes to roll the daily
DAILY_QUEST_UNLOCK_MIN = 3     # this many capable heroes must be playable before the daily is in logic
DAILY_QUEST_MAX = 3

DAILY_TAKEDOWNS_100 = "daily_takedowns_100"
DAILY_REGEN_150 = "daily_regen_150"
DAILY_HERO_DAMAGE_250K = "daily_hero_damage_250k"
DAILY_SIEGE_300K = "daily_siege_300k"
DAILY_HEALING_200K = "daily_healing_200k"
DAILY_MINION_200 = "daily_minion_200"
DAILY_MERC_10 = "daily_merc_10"
DAILY_ASSISTS_40 = "daily_assists_40"
DAILY_SOLO_15 = "daily_solo_15"
DAILY_SELF_HEAL_80K = "daily_self_heal_80k"
DAILY_PROTECT_20K = "daily_protect_20k"
DAILY_STUN_120 = "daily_stun_120"
DAILY_SILENCE_80 = "daily_silence_80"
DAILY_QUESTS_COMPLETE = "daily_quests_complete"

DAILY_QUEST_DEFS: dict[str, tuple[str, str, int, str]] = {
    DAILY_TAKEDOWNS_100: (CAP_TAKEDOWN, "Takedowns", 100, "Daily Quest: Achieve 100 takedowns"),
    DAILY_REGEN_150: (CAP_REGEN_GLOBE, "RegenGlobes", 150, "Daily Quest: Collect 150 regen globes"),
    DAILY_HERO_DAMAGE_250K: (CAP_HERO_DAMAGE, "HeroDamage", 250_000, "Daily Quest: Deal 250,000 hero damage"),
    DAILY_SIEGE_300K: (CAP_SIEGE, "SiegeDamage", 300_000, "Daily Quest: Deal 300,000 siege damage"),
    DAILY_HEALING_200K: (CAP_HEAL, "Healing", 200_000, "Daily Quest: Restore 200,000 health"),
    DAILY_MINION_200: (CAP_MINION, "MinionKills", 200, "Daily Quest: Kill 200 minions"),
    DAILY_MERC_10: (CAP_MERC, "MercCampCaptures", 10, "Daily Quest: Capture 10 mercenary camps"),
    DAILY_ASSISTS_40: (CAP_ASSIST, "Assists", 40, "Daily Quest: Get 40 assists"),
    DAILY_SOLO_15: (CAP_SOLO_KILL, "SoloKill", 15, "Daily Quest: Get 15 solo kills"),
    DAILY_SELF_HEAL_80K: (CAP_SELF_HEAL, "SelfHealing", 80_000, "Daily Quest: Self-heal 80,000"),
    DAILY_PROTECT_20K: (CAP_PROTECT, "ProtectionGivenToAllies", 20_000, "Daily Quest: Shield allies for 20,000"),
    DAILY_STUN_120: (CAP_STUN, "TimeStunningEnemyHeroes", 120, "Daily Quest: Stun enemies for 120 seconds"),
    DAILY_SILENCE_80: (CAP_SILENCE, "TimeSilencingEnemyHeroes", 80, "Daily Quest: Silence enemies for 80 seconds"),
}

DAILY_QUESTS_COMPLETE_NAME = "Daily Quest: Complete all daily quests"

ALL_DAILY_QUEST_KEYS: tuple[str, ...] = tuple(DAILY_QUEST_DEFS.keys())

DAILY_QUEST_UNLOCK_ITEMS: tuple[str, ...] = tuple(
    f"Daily Quest Unlock {i}" for i in range(1, DAILY_QUEST_MAX + 1)
)

def daily_quest_location_name(quest_key: str) -> str:
    if quest_key == DAILY_QUESTS_COMPLETE:
        return DAILY_QUESTS_COMPLETE_NAME
    return DAILY_QUEST_DEFS[quest_key][3]

def daily_quest_item_name(slot: int) -> str:
    """1-based unlock slot → item name (Daily Quest Unlock 1..3)."""
    if slot < 1 or slot > DAILY_QUEST_MAX:
        raise ValueError(f"Daily quest unlock slot out of range: {slot}")
    return DAILY_QUEST_UNLOCK_ITEMS[slot - 1]

def daily_quest_slot_from_item_name(name: str) -> int | None:
    try:
        idx = DAILY_QUEST_UNLOCK_ITEMS.index(name)
    except ValueError:
        return None
    return idx + 1

def capable_heroes_in_pool(capability: str, enabled_heroes: list[str] | set[str]) -> list[str]:
    members = CAPABILITY_HEROES.get(capability, frozenset())
    return sorted((h for h in enabled_heroes if h in members), key=hero_sort_key)

def eligible_daily_quest_keys(enabled_heroes: list[str]) -> list[str]:
    """Quest keys whose capability has enough heroes in the seed pool."""
    out: list[str] = []
    for key, (cap, _field, _thr, _title) in DAILY_QUEST_DEFS.items():
        if len(capable_heroes_in_pool(cap, enabled_heroes)) >= DAILY_QUEST_POOL_MIN:
            out.append(key)
    return out

def roll_daily_quests(
    enabled_heroes: list[str],
    rng,
    starting_heroes: list[str] | None = None,
) -> list[str]:
    """Pick up to 3 dailies. Slot 1 prefers a quest at least one starter can earn."""
    eligible = eligible_daily_quest_keys(enabled_heroes)
    if not eligible:
        return []
    n = min(DAILY_QUEST_MAX, len(eligible))
    starters = [h for h in (starting_heroes or []) if h in enabled_heroes]
    starter_keys = [
        key for key in eligible
        if any(hero_has_capability(h, DAILY_QUEST_DEFS[key][0]) for h in starters)
    ]
    if starter_keys:
        first = rng.choice(starter_keys)
        remaining = [key for key in eligible if key != first]
        extra = n - 1
        rest = rng.sample(remaining, min(extra, len(remaining))) if extra and remaining else []
        return [first, *rest]
    return rng.sample(eligible, n)

def _level_check_keys() -> frozenset[str]:
    return frozenset(
        key for key, (field, _thr) in CHECK_SCORE_THRESHOLDS.items()
        if field == "Level"
    )

SINGLE_GAME_CHECKS = frozenset({WIN, LEVEL_20})  # refreshed after tier load

CHECK_SCORE_THRESHOLDS: dict[str, tuple[str, int]] = {
    LEVEL_20: ("Level", 20),
}

def score_fields_for_check_keys(check_keys: list[str]) -> set[str]:
    return {
        CHECK_SCORE_THRESHOLDS[key][0]
        for key in check_keys
        if key in CHECK_SCORE_THRESHOLDS
    }

def detect_instant_checks(score: dict, result: str, level_history: list | None = None) -> set[str]:
    return detect_checks(score, result, level_history) & SINGLE_GAME_CHECKS

def detect_cumulative_checks(stat_totals: dict[str, int], check_keys: list[str]) -> set[str]:
    fired: set[str] = set()
    for key in check_keys:
        if key not in CHECK_SCORE_THRESHOLDS:
            continue
        field, threshold = CHECK_SCORE_THRESHOLDS[key]
        if stat_totals.get(field, 0) >= threshold:
            fired.add(key)
    return fired

def detect_checks(score: dict, result: str, level_history: list | None = None) -> set[str]:
    fired: set[str] = set()
    if result == "Win":
        fired.add(WIN)

    max_level = max(level_history or [0], default=0)
    score_level = int(score.get("Level", 0) or 0)
    best_level = max(max_level, score_level)

    for check_key, (field, threshold) in CHECK_SCORE_THRESHOLDS.items():
        if field == "Level":
            if best_level >= threshold:
                fired.add(check_key)
            continue
        if score.get(field, 0) >= threshold:
            fired.add(check_key)

    return fired

def _load_hero_tiers() -> None:
    global HERO_CHECKS, SINGLE_GAME_CHECKS
    try:
        from . import HeroTiers as _tiers
    except ImportError:
        _tiers = None

    if _tiers is not None:
        _apply_hero_tier_tables(
            getattr(_tiers, "HERO_CAPABILITY_CHECKS", {}),
            getattr(_tiers, "CHECK_DESCRIPTIONS", {}),
            getattr(_tiers, "CHECK_THRESHOLDS", {}),
        )
    else:
        for hero in ALL_HEROES:
            HERO_CAPABILITY_CHECKS[hero] = {
                CAP_WIN: WIN,
                CAP_LEVEL_20: LEVEL_20,
            }
    validate_capability_tables()
    HERO_CHECKS = {hero: all_check_keys_for_hero(hero) for hero in ALL_HEROES}
    SINGLE_GAME_CHECKS = frozenset({WIN}) | _level_check_keys()

_load_hero_tiers()
