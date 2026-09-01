from dataclasses import dataclass
from BaseClasses import ItemClassification
from .Challenges import ALL_HEROES, DAILY_QUEST_UNLOCK_ITEMS, PASS_KEYS, PASS_NAMES

HOTS_ITEM_BASE = 8889000

SHARDS_TO_UNLOCK = 5
HEROES_PER_LOOT_CHEST = 4
CHEST_COST_XP = 1000
CHEST_SLOTS = 4
# First N slots of each chest are filled in pre_fill from the shared item pool
# (any world's useful/progression). Remaining slot(s) go to main fill.
CHEST_NON_FILLER_SLOTS = 3
MAX_LOOT_CHESTS = 50
# Bonus XP beyond reserved chest-buy amount, as useful 200 XP + filler 100 XP.
# Scales with chest count. Leftover after the last chest is for overflow later.
EXTRA_XP_PERCENT = 40
# Stimpacks: 3 at 10 heroes, +2 per extra 10, max 8. Below 10 scales down.
STIM_AT_TEN = 3
STIM_PER_TEN = 2
STIM_MAX = 8
# Talent Tomes: 1 per 6 talent locations, max 15. None if talents are off.
TOME_PER_TALENT_LOCS = 6
TOME_MAX = 15


def stimpack_count_for_seed(hero_count: int) -> int:
    if hero_count <= 0:
        return 0
    if hero_count < 10:
        return max(1, round(STIM_AT_TEN * hero_count / 10))
    extra_tens = (hero_count - 10) // 10
    return min(STIM_MAX, STIM_AT_TEN + STIM_PER_TEN * extra_tens)


def talent_tome_count_for_seed(talent_location_count: int) -> int:
    if talent_location_count <= 0:
        return 0
    return min(TOME_MAX, talent_location_count // TOME_PER_TALENT_LOCS)

XP_100_NAME = "100 XP"
XP_200_NAME = "200 XP"
XP_500_NAME = "500 XP"
LOOT_CHEST_NAME = "Loot Chest"
FILLER_ITEM_NAME = "Void Scrap"
STIMPACK_NAME = "Stimpack"
TALENT_TOME_NAME = "Talent Tome"

XP_VALUES: dict[str, int] = {
    XP_100_NAME: 100,
    XP_200_NAME: 200,
    XP_500_NAME: 500,
    LOOT_CHEST_NAME: 1000,
}

XP_BANK_ITEMS = frozenset({XP_100_NAME, XP_200_NAME, XP_500_NAME})


@dataclass
class HoTSItemData:
    id: int
    classification: ItemClassification


def shard_item_name(hero: str) -> str:
    return f"{hero} Shard"


def hero_from_shard_name(name: str) -> str | None:
    if name.endswith(" Shard"):
        return name[: -len(" Shard")]
    return None


hero_unlock_items: dict[str, HoTSItemData] = {
    hero: HoTSItemData(
        id=HOTS_ITEM_BASE + idx,
        classification=ItemClassification.progression,
    )
    for idx, hero in enumerate(ALL_HEROES)
}

hero_shard_items: dict[str, HoTSItemData] = {
    shard_item_name(hero): HoTSItemData(
        id=HOTS_ITEM_BASE + 100 + idx,
        classification=ItemClassification.progression,
    )
    for idx, hero in enumerate(ALL_HEROES)
}

role_pass_items: dict[str, HoTSItemData] = {
    PASS_NAMES[pass_key]: HoTSItemData(
        id=HOTS_ITEM_BASE + 200 + idx,
        classification=ItemClassification.progression,
    )
    for idx, pass_key in enumerate(PASS_KEYS)
}

loot_economy_items: dict[str, HoTSItemData] = {
    XP_500_NAME: HoTSItemData(id=HOTS_ITEM_BASE + 300, classification=ItemClassification.progression),
    LOOT_CHEST_NAME: HoTSItemData(id=HOTS_ITEM_BASE + 301, classification=ItemClassification.progression),
    XP_200_NAME: HoTSItemData(id=HOTS_ITEM_BASE + 302, classification=ItemClassification.useful),
    XP_100_NAME: HoTSItemData(id=HOTS_ITEM_BASE + 303, classification=ItemClassification.filler),
    FILLER_ITEM_NAME: HoTSItemData(id=HOTS_ITEM_BASE + 304, classification=ItemClassification.filler),
}

consumable_items: dict[str, HoTSItemData] = {
    STIMPACK_NAME: HoTSItemData(id=HOTS_ITEM_BASE + 310, classification=ItemClassification.useful),
    TALENT_TOME_NAME: HoTSItemData(id=HOTS_ITEM_BASE + 311, classification=ItemClassification.useful),
}

daily_quest_items: dict[str, HoTSItemData] = {
    name: HoTSItemData(
        id=HOTS_ITEM_BASE + 400 + idx,
        classification=ItemClassification.progression,
    )
    for idx, name in enumerate(DAILY_QUEST_UNLOCK_ITEMS)
}

item_table: dict[str, HoTSItemData] = {
    **hero_unlock_items,
    **hero_shard_items,
    **role_pass_items,
    **loot_economy_items,
    **daily_quest_items,
    **consumable_items,
}


def open_capacity_value(item_name: str) -> int:
    """XP-equivalent toward buying/opening loot chests (logic + client)."""
    return XP_VALUES.get(item_name, 0)


def is_open_currency_item(item_name: str) -> bool:
    return item_name in XP_VALUES


def is_loot_legendary_item(item_name: str) -> bool:
    """Full hero unlocks and role passes — gold/legendary chest faces (not shards)."""
    if not item_name:
        return False
    if item_name in hero_unlock_items:
        return True
    if item_name in role_pass_items:
        return True
    return False
