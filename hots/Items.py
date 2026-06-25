from dataclasses import dataclass
from BaseClasses import ItemClassification
from .Challenges import ALL_HEROES, PASS_KEYS, PASS_NAMES

HOTS_ITEM_BASE = 8889000


@dataclass
class HoTSItemData:
    id: int
    classification: ItemClassification


hero_unlock_items: dict[str, HoTSItemData] = {
    hero: HoTSItemData(
        id=HOTS_ITEM_BASE + idx,
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

FILLER_ITEM_NAME = "Void Scrap"
filler_item = HoTSItemData(id=HOTS_ITEM_BASE + 300, classification=ItemClassification.filler)

item_table: dict[str, HoTSItemData] = {
    **hero_unlock_items,
    **role_pass_items,
    FILLER_ITEM_NAME: filler_item,
}
