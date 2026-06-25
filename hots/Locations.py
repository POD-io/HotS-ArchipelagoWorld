from dataclasses import dataclass
from BaseClasses import Location
from .Challenges import ALL_HEROES, HERO_CHECKS, location_name

HOTS_LOCATION_BASE = 8888000


@dataclass
class HoTSLocationData:
    id: int
    hero: str | None = None
    check_key: str | None = None


class HoTSLocation(Location):
    game = "Heroes of the Storm"


location_table: dict[str, HoTSLocationData] = {}
_loc_id = HOTS_LOCATION_BASE

for _hero in ALL_HEROES:
    for _check_key in HERO_CHECKS[_hero]:
        _name = location_name(_hero, _check_key)
        location_table[_name] = HoTSLocationData(id=_loc_id, hero=_hero, check_key=_check_key)
        _loc_id += 1

location_name_to_id: dict[str, int] = {name: data.id for name, data in location_table.items()}

locations_by_hero: dict[str, list[str]] = {hero: [] for hero in ALL_HEROES}
for _name, _data in location_table.items():
    if _data.hero:
        locations_by_hero[_data.hero].append(_name)
