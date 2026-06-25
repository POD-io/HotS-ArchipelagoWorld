from dataclasses import dataclass
from BaseClasses import ItemClassification
from .Challenges import ALL_HEROES

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

ROLES = ["assassin", "warrior", "support", "specialist"]
role_pass_items: dict[str, HoTSItemData] = {
    f"{role.capitalize()} Pass": HoTSItemData(
        id=HOTS_ITEM_BASE + 200 + idx,
        classification=ItemClassification.progression,
    )
    for idx, role in enumerate(ROLES)
}

FILLER_ITEM_NAME = "Void Scrap"
filler_item = HoTSItemData(id=HOTS_ITEM_BASE + 300, classification=ItemClassification.filler)

item_table: dict[str, HoTSItemData] = {
    **hero_unlock_items,
    **role_pass_items,
    FILLER_ITEM_NAME: filler_item,
}
