from dataclasses import dataclass
from BaseClasses import Location
from .Challenges import (
    ALL_HEROES, HERO_CHECKS, PASS_KEYS, PASS_XP_CHECKS, PASS_TIMED_WIN_CHECKS,
    ALL_DAILY_QUEST_KEYS, DAILY_QUESTS_COMPLETE, daily_quest_location_name,
    location_name, pass_location_name,
)
from .Items import CHEST_SLOTS, MAX_LOOT_CHESTS
from .Talents import TALENT_LEVELS, talent_check_key, talent_location_name

HOTS_LOCATION_BASE = 8888000


@dataclass
class HoTSLocationData:
    id: int
    hero: str | None = None
    check_key: str | None = None
    pass_key: str | None = None
    daily_quest_key: str | None = None
    chest_index: int | None = None
    chest_slot: int | None = None


class HoTSLocation(Location):
    game = "Heroes of the Storm"


def chest_location_name(chest_index: int, slot: int) -> str:
    return f"Loot Chest {chest_index}: Reward {slot}"


location_table: dict[str, HoTSLocationData] = {}
_loc_id = HOTS_LOCATION_BASE

for _hero in ALL_HEROES:
    for _check_key in HERO_CHECKS[_hero]:
        _name = location_name(_hero, _check_key)
        location_table[_name] = HoTSLocationData(id=_loc_id, hero=_hero, check_key=_check_key)
        _loc_id += 1

for _pass_key in PASS_KEYS:
    for _check_key in PASS_XP_CHECKS + PASS_TIMED_WIN_CHECKS:
        _name = pass_location_name(_pass_key, _check_key)
        location_table[_name] = HoTSLocationData(
            id=_loc_id, check_key=_check_key, pass_key=_pass_key,
        )
        _loc_id += 1

for _hero in ALL_HEROES:
    for _level in TALENT_LEVELS:
        _name = talent_location_name(_hero, _level)
        location_table[_name] = HoTSLocationData(
            id=_loc_id, hero=_hero, check_key=talent_check_key(_level),
        )
        _loc_id += 1

for _chest in range(1, MAX_LOOT_CHESTS + 1):
    for _slot in range(1, CHEST_SLOTS + 1):
        _name = chest_location_name(_chest, _slot)
        location_table[_name] = HoTSLocationData(
            id=_loc_id, chest_index=_chest, chest_slot=_slot,
            check_key=f"chest_{_chest}_{_slot}",
        )
        _loc_id += 1

for _dq_key in (*ALL_DAILY_QUEST_KEYS, DAILY_QUESTS_COMPLETE):
    _name = daily_quest_location_name(_dq_key)
    location_table[_name] = HoTSLocationData(
        id=_loc_id, check_key=_dq_key, daily_quest_key=_dq_key,
    )
    _loc_id += 1

location_name_to_id: dict[str, int] = {name: data.id for name, data in location_table.items()}

locations_by_hero: dict[str, list[str]] = {hero: [] for hero in ALL_HEROES}
for _name, _data in location_table.items():
    if _data.hero:
        locations_by_hero[_data.hero].append(_name)
