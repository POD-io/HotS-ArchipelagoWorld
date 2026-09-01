"""Talent tier counts and slot helpers."""

import os
import random
import re
import zlib
from dataclasses import dataclass
from typing import Sequence

from .Challenges import ALL_HEROES, HERO_TO_YAML_KEY

TALENT_LEVELS: tuple[int, ...] = (1, 4, 7, 10, 13, 16, 20)

DEFAULT_TALENT_COUNTS: dict[int, int] = {
    1: 3,
    4: 3,
    7: 3,
    10: 2,
    13: 3,
    16: 3,
    20: 4,
}

TALENT_COUNT_EXCEPTIONS: dict[str, dict[int, int]] = {
    "Abathur": {1: 4, 4: 4, 16: 4},
    "Anduin": {16: 4},
    "Artanis": {13: 4},
    "Blaze": {1: 4, 20: 3},
    "Chen": {13: 4},
    "Deathwing": {20: 3},
    "E.T.C.": {20: 5},
    "Fenix": {13: 4},
    "Gul'dan": {13: 4, 20: 3},
    "Imperius": {20: 5},
    "Junkrat": {13: 4},
    "Kharazim": {20: 5},
    "Li-Ming": {16: 4},
    "Lunara": {13: 4, 16: 4, 20: 5},
    "Maiev": {20: 3},
    "Malthael": {13: 4},
    "Medivh": {20: 5},
    "Raynor": {20: 5},
    "Rexxar": {4: 4},
    "The Lost Vikings": {1: 4, 4: 4, 16: 4},
    "Thrall": {20: 5},
    "Tracer": {10: 3},
    "Tyrael": {20: 5},
    "Valeera": {1: 4, 4: 4},
    "Varian": {20: 5},
    "Zarya": {1: 4, 4: 4, 13: 4},
}

# --- Talent roll outliers (default: L10 heroic #1/#2 ↔ L20 upgrade #1/#2) ---
#
# Junkrat is intentionally not listed — both heroics have L20 upgrades; standard pairing applies.

# No L10 to L20 pairing when both tiers are rolled.
TALENT_L20_UNRESTRICTED: frozenset[str] = frozenset({
    "Alarak",
    "Deathwing",
    "Maiev",
    "Tracer",
})

# One L10 heroic has an L20 upgrade; the other heroic does not.
# hero -> (ult_level, l10_rank_with_upgrade, l20_upgrade_rank)
TALENT_SINGLE_L20_UPGRADE: dict[str, tuple[int, int, int]] = {
    "Zeratul": (10, 2, 2),  # Void Annihilation; Void Prison (r1) has no L20
    "Fenix": (10, 1, 1),    # Planet Cracker; Purification Salvo (r2) has no L20
}

# Heroic picked at a non-10 tier; L20 ranks [start, end] upgrade those picks (Varian: 3 ults at 4).
# hero -> (ult_level, first_l20_upgrade_rank, last_l20_upgrade_rank)
TALENT_ULT_AT_LEVEL: dict[str, tuple[int, int, int]] = {
    "Varian": (4, 1, 3),
}

# L20 rank requires an earlier forced tier/rank when both are rolled in the same seed.
# hero -> [(l20_rank, required_level, required_rank), ...]
TALENT_L20_PREREQUISITES: dict[str, tuple[tuple[int, int, int], ...]] = {
    "Garrosh": ((3, 1, 1),),  # Deadly Calm needs Warbreaker at L1 — verify UI order after patches
}


def talent_counts_for_hero(hero: str) -> dict[int, int]:
    counts = dict(DEFAULT_TALENT_COUNTS)
    counts.update(TALENT_COUNT_EXCEPTIONS.get(hero, {}))
    return counts


def talent_count(hero: str, level: int) -> int:
    return talent_counts_for_hero(hero).get(level, 0)


def talent_check_key(level: int) -> str:
    """Location key for a talent *tier* — rank lives in slot_data / client state."""
    return f"talent_l{level}"


def parse_talent_check_key(check_key: str) -> tuple[int, int] | None:
    """Return (level, rank) if this is a talent key. Rank is 0 when the location is tier-only."""
    if not check_key.startswith("talent_l"):
        return None
    try:
        body = check_key[len("talent_l"):]
        if "_r" in body:
            level_s, rank_s = body.split("_r", 1)
            return int(level_s), int(rank_s)
        return int(body), 0
    except ValueError:
        return None


_BUILD_CODE_HERO_NAMES: dict[str, str] = {
    "Lúcio": "Lucio",
}

# YAML-ish key → HotS TalentBuilds.txt unit name (Thing's table). Only differs matter.
_YAML_KEY_TO_UNIT_NAME: dict[str, str] = {
    "Blaze": "Firebat",
    "Brightwing": "FaerieDragon",
    "Cassia": "Amazon",
    "ETC": "L90ETC",
    "Gazlowe": "Tinker",
    "Johanna": "Crusader",
    "Kharazim": "Monk",
    "LiMing": "Wizard",
    "LtMorales": "Medic",
    "Lunara": "Dryad",
    "Mei": "MeiOW",
    "Nazeebo": "WitchDoctor",
    "Qhira": "NexusHunter",
    "Sonya": "Barbarian",
    "TheButcher": "Butcher",
    "TheLostVikings": "LostVikings",
    "Valla": "DemonHunter",
    "Xul": "Necromancer",
}

_TALENT_BUILDS_LINE = re.compile(
    r"^(?P<unit>[^=]+)=(?P<active>[^|]+)\|(?P<s1>[^|]*)\|(?P<s2>[^|]*)\|(?P<s3>[^|]*)\|(?P<hash>[0-9A-Fa-f]+)\s*$"
)
_EMPTY_SLOT = '""'
_BACKUP_PREFIX = "TalentBuilds.bak_"

# HotS rejects TalentBuilds lines whose trailing hash is wrong. These are stable
# per-unit IDs (from real client files / community dumps) — never invent new ones.
_KNOWN_UNIT_HASHES: dict[str, str] = {
    "Abathur": "ED22A0C7F0575B",
    "Alarak": "F985B31D7FAB08",
    "Alexstrasza": "C4218A71921173",
    "Amazon": "9060F0E64787D1",
    "Ana": "5550BAD54C623B",
    "Anduin": "E77A91608DC45A",
    "Anubarak": "B81CD68F6E2368",
    "Artanis": "3BB4C09A5C9BC7",
    "Arthas": "8D6C2BF5F13792",
    "Auriel": "A04BEEE3A385CF",
    "Azmodan": "A094E2C9693649",
    "Barbarian": "FB7F0C970D4ACF",
    "Butcher": "DF98C6D64368F0",
    "Chen": "70BC42AD71FA48",
    "Cho": "FE188EF13759A6",
    "Chromie": "5DB6BEAC15AD92",
    "Crusader": "3D102ED8AA4BA6",
    "DVa": "B056CD4F470A77",
    "Deathwing": "52A50F3DC087E6",
    "Deckard": "D7FBF3345949E5",
    "Dehaka": "06C0E298235A7F",
    "DemonHunter": "FA928E199C01F5",
    "Diablo": "3941B97EA2E595",
    "Dryad": "816A87C97D694D",
    "FaerieDragon": "F64470EAB69ECD",
    "Falstad": "94CDE438D6A38D",
    "Fenix": "EF8E692F946CD7",
    "Firebat": "3B5384AE5EAB7D",
    "Gall": "F232B21302004B",
    "Genji": "FB8261B915F803",
    "Greymane": "75D5054268A86F",
    "Guldan": "56E31DB2259923",
    "Hanzo": "1FD40C129CC38A",
    "Hogger": "B277D000A12093",
    "Illidan": "381B814CED9831",
    "Imperius": "22B0D7408A65C1",
    "Jaina": "2E70D0062730D1",
    "Junkrat": "EF123CCC79D7B6",
    "Kaelthas": "86D5ADE0AD03FB",
    "KelThuzad": "C8890FAF580844",
    "Kerrigan": "435B884F2D9DA7",
    "L90ETC": "6C3CE237A080F7",
    "Leoric": "EA433C82F7FAE1",
    "LiLi": "C9BC9E3413AF26",
    "LostVikings": "E8ED96ED1EB6DC",
    "Lucio": "F6500D17E7C2ED",
    "Maiev": "2B7EAA4539C3F7",
    "MalGanis": "42EF14DFF879D6",
    "Malfurion": "7781E303AB0A91",
    "Medic": "A24CDEAAE39884",
    "Medivh": "0DBEFB89992388",
    "MeiOW": "7AE74832BACE98",
    "Mephisto": "B7E55A546498DA",
    "Monk": "8792B53BC067B7",
    "Muradin": "56E389BDE9B9D7",
    "Murky": "4D425DC9FD4704",
    "Necromancer": "B4166E5BDF2286",
    "NexusHunter": "B6987184816E2F",
    "Nova": "B6DCD69BB65CB3",
    "Orphea": "E34F3E36ED9CED",
    "Probius": "66B18B01F8404F",
    "Ragnaros": "5FF5F209412408",
    "Raynor": "008B32EF2A4753",
    "Rehgar": "BB3B03750091EB",
    "Rexxar": "BA923C83C84BDF",
    "Samuro": "217255C2AACF88",
    "SgtHammer": "92F99B7B94806D",
    "Stitches": "38C553327AA23D",
    "Stukov": "62F5F07690FE8E",
    "Sylvanas": "06BC297F581C10",
    "Tassadar": "30575D7BBA845D",
    "Thrall": "555674B4D06C49",
    "Tinker": "F786564B3D0FB2",
    "Tracer": "535AAB74DDF33C",
    "Tychus": "12997027DE48F1",
    "Tyrael": "ADAC2D621B5233",
    "Tyrande": "3ED0CEF0B2CAEC",
    "Uther": "1D6D8C321DCAB9",
    "Valeera": "A65F0404129175",
    "Varian": "AA275A0AF3C560",
    "Whitemane": "43E85D1E92E92B",
    "WitchDoctor": "463F6BF63C89A6",
    "Wizard": "2EF65E909A6D57",
    "Yrel": "C0CA56FA10CAB5",
    "Zagara": "FCCE7E80F03E90",
    "Zarya": "4B7644B01C0D73",
    "Zeratul": "88C16EE24C8E67",
    "Zuljin": "BE6661C5340EF7",
}


def talent_slot_description(level: int) -> str:
    return f"Level {level} Talent"


def talent_location_name(hero: str, level: int) -> str:
    return f"{hero}: {talent_slot_description(level)}"


def _req_rank(reqs: Sequence[dict[str, int]], level: int) -> int | None:
    for req in reqs:
        if int(req["level"]) == level:
            return int(req["rank"])
    return None


def forbidden_l20_ranks(
    hero: str,
    reqs_so_far: Sequence[dict[str, int]],
    total_l20: int,
) -> set[int]:
    """L20 ranks that contradict an ult already forced on this seed."""
    if hero in TALENT_L20_UNRESTRICTED:
        return set()

    if hero in TALENT_ULT_AT_LEVEL:
        ult_level, rank_start, rank_end = TALENT_ULT_AT_LEVEL[hero]
        ult_rank = _req_rank(reqs_so_far, ult_level)
        if ult_rank is not None and rank_start <= ult_rank <= rank_end:
            return {
                rank
                for rank in range(rank_start, min(rank_end, total_l20) + 1)
                if rank != ult_rank
            }
        return set()

    if hero in TALENT_SINGLE_L20_UPGRADE:
        ult_level, upgrade_l10, upgrade_l20 = TALENT_SINGLE_L20_UPGRADE[hero]
        if upgrade_l20 > total_l20:
            return set()
        ult_rank = _req_rank(reqs_so_far, ult_level)
        if ult_rank is not None and ult_rank != upgrade_l10:
            return {upgrade_l20}
        return set()

    # Standard two-heroic heroes at L10: block the opposite ult's L20 upgrade.
    ult_rank = _req_rank(reqs_so_far, 10)
    if ult_rank in (1, 2) and total_l20 >= 2:
        opposite = 3 - ult_rank
        if opposite <= total_l20:
            return {opposite}
    return set()


def legal_talent_ranks(
    hero: str,
    level: int,
    total: int,
    reqs_so_far: Sequence[dict[str, int]],
) -> list[int]:
    """1-based ranks that are legal for this slot given the other forced picks."""
    if total <= 0:
        return []
    if level != 20:
        return list(range(1, total + 1))

    choices = [
        rank
        for rank in range(1, total + 1)
        if rank not in forbidden_l20_ranks(hero, reqs_so_far, total)
    ]
    for l20_rank, req_level, req_rank in TALENT_L20_PREREQUISITES.get(hero, ()):
        if l20_rank > total:
            continue
        forced = _req_rank(reqs_so_far, req_level)
        if forced is not None and forced != req_rank:
            choices = [rank for rank in choices if rank != l20_rank]

    return choices or list(range(1, total + 1))


def choose_talent_rank(
    hero: str,
    level: int,
    total: int,
    reqs_so_far: Sequence[dict[str, int]],
    rng: random.Random,
    exclude_rank: int | None = None,
) -> int:
    """Pick a valid 1-based rank for a forced talent slot during seed generation."""
    choices = legal_talent_ranks(hero, level, total, reqs_so_far)
    if exclude_rank is not None:
        filtered = [rank for rank in choices if rank != exclude_rank]
        if filtered:
            choices = filtered
    if not choices:
        return rng.randint(1, max(1, total))
    return rng.choice(choices)


def talent_req_is_any(req: dict) -> bool:
    return bool(req.get("any"))


def can_unlock_any_talent_slot(
    level: int,
    reqs: Sequence[dict],
    locked_levels: set[int] | None = None,
) -> bool:
    """True when a Talent Tome can make this uncompleted tier accept any pick."""
    if level in (locked_levels or set()):
        return False
    for req in reqs:
        if int(req["level"]) == level:
            return not talent_req_is_any(req)
    return False


def unlock_any_talent_slot(
    level: int,
    reqs: Sequence[dict],
    locked_levels: set[int] | None = None,
) -> list[dict] | None:
    """Mark one uncompleted talent tier as any-pick. Original rank is kept for the location name."""
    if not can_unlock_any_talent_slot(level, reqs, locked_levels):
        return None
    out: list[dict] = []
    for req in reqs:
        row = dict(req)
        if int(row["level"]) == level:
            row["any"] = True
        out.append(row)
    return out


def build_code_hero_name(hero: str) -> str:
    return _BUILD_CODE_HERO_NAMES.get(hero, hero)


def talent_builds_unit_name(hero: str) -> str:
    """Internal unit name used by Documents/.../TalentBuilds.txt."""
    yaml_key = HERO_TO_YAML_KEY.get(hero, hero)
    return _YAML_KEY_TO_UNIT_NAME.get(yaml_key, yaml_key)


def build_talent_builds_hex(
    requirements: list[tuple[int, int]] | list[dict[str, int]],
) -> str:
    """Encode forced ranks as TalentBuilds bitmask hex (00 = unforced)."""
    req_map: dict[int, int] = {}
    for req in requirements:
        if isinstance(req, dict):
            if talent_req_is_any(req):
                continue
            level, rank = int(req["level"]), int(req["rank"])
        else:
            level, rank = int(req[0]), int(req[1])
        req_map[level] = rank

    parts: list[str] = []
    for level in TALENT_LEVELS:
        rank = req_map.get(level)
        if not rank or rank < 1:
            parts.append("00")
        else:
            parts.append(f"{1 << (rank - 1):02X}")
    return "".join(parts)


def _synthetic_build_hash(unit: str) -> str:
    """14-hex stand-in when no prior hash is known for this unit.

    HotS hashes look like opaque per-hero IDs. Community TalentBuilds copies work across
    PCs, so a deterministic filler is enough for heroes without a known hash.
    """
    a = zlib.crc32(unit.encode("utf-8")) & 0xFFFFFFFF
    b = zlib.crc32(unit[::-1].encode("utf-8")) & 0xFFFFFF
    return f"{a:08X}{b:06X}"


def _parse_unit_hashes(text: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for ln in text.splitlines():
        match = _TALENT_BUILDS_LINE.match(ln.strip())
        if match:
            hashes[match.group("unit")] = match.group("hash").upper()
    return hashes


def _collect_unit_hashes(directory: str, existing_text: str) -> dict[str, str]:
    """Resolve per-unit hashes HotS will accept.

    Priority: this account's TalentBuilds.bak_* (oldest first, pre-AP) → bundled
    known IDs → current file (skipping synthetic CRC placeholders).
    """
    hashes: dict[str, str] = {}

    def _absorb(text: str, *, overwrite: bool = False) -> None:
        for unit, build_hash in _parse_unit_hashes(text).items():
            if build_hash == _synthetic_build_hash(unit):
                continue
            if overwrite or unit not in hashes:
                hashes[unit] = build_hash

    try:
        bak_names = sorted(
            n for n in os.listdir(directory)
            if n.startswith(_BACKUP_PREFIX) and n.endswith(".txt")
        )
        for name in bak_names:
            path = os.path.join(directory, name)
            try:
                with open(path, encoding="utf-8") as f:
                    _absorb(f.read())
            except OSError:
                continue
    except OSError:
        pass

    for unit, build_hash in _KNOWN_UNIT_HASHES.items():
        hashes.setdefault(unit, build_hash)

    _absorb(existing_text)
    return hashes


def _hash_for_unit(unit: str, known: dict[str, str]) -> str:
    return known.get(unit) or _KNOWN_UNIT_HASHES.get(unit) or _synthetic_build_hash(unit)


def _normalize_builds_text(text: str) -> str:
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


def _unique_backup_path(directory: str) -> str:
    """TalentBuilds.bak_YYYYMMDD_HHMMSS.txt — never overwrites an existing backup."""
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = os.path.join(directory, f"{_BACKUP_PREFIX}{stamp}.txt")
    if not os.path.exists(candidate):
        return candidate
    n = 2
    while True:
        candidate = os.path.join(directory, f"{_BACKUP_PREFIX}{stamp}_{n}.txt")
        if not os.path.exists(candidate):
            return candidate
        n += 1


@dataclass
class TalentBuildsExportResult:
    path: str
    heroes_written: int
    backup_path: str | None
    skipped_unchanged: bool


def find_talent_builds_paths(accounts_root: str, replay_dirs: list[str] | None = None) -> list[str]:
    """Locate TalentBuilds.txt under Accounts, preferring folders that own configured replays."""
    if not accounts_root or not os.path.isdir(accounts_root):
        return []

    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(accounts_root):
        if "TalentBuilds.txt" in filenames:
            found.append(os.path.join(dirpath, "TalentBuilds.txt"))

    preferred: list[str] = []
    replay_dirs = replay_dirs or []
    for path in found:
        account_dir = os.path.dirname(path)
        norm_account = os.path.normcase(os.path.normpath(account_dir))
        for rd in replay_dirs:
            if os.path.normcase(os.path.normpath(rd)).startswith(norm_account + os.sep) or (
                os.path.normcase(os.path.normpath(rd)) == norm_account
            ):
                preferred.append(path)
                break

    if preferred:
        return preferred
    if found:
        return found

    # No file yet: infer account folders from replay paths and create targets there.
    inferred: list[str] = []
    root_norm = os.path.normcase(os.path.normpath(accounts_root))
    for rd in replay_dirs:
        cur = os.path.normpath(rd)
        while True:
            parent = os.path.dirname(cur)
            if not parent or parent == cur:
                break
            if os.path.normcase(parent) == root_norm:
                candidate = os.path.join(cur, "TalentBuilds.txt")
                if candidate not in inferred:
                    inferred.append(candidate)
                break
            cur = parent
    return inferred


def export_ap_talent_builds(
    path: str,
    hero_requirements: dict[str, list],
) -> TalentBuildsExportResult:
    """Replace TalentBuilds.txt with an AP-only builds file for this seed.

    HotS only reads TalentBuilds.txt, so the active run file must use that name. Before every
    replace, the current file is copied to a unique timestamped backup
    (TalentBuilds.bak_YYYYMMDD_HHMMSS.txt) unless it already matches what we would write.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    existing_text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            existing_text = f.read()

    known_hashes = _collect_unit_hashes(directory, existing_text)

    out_lines: list[str] = []
    for hero, reqs in sorted(hero_requirements.items(), key=lambda kv: kv[0]):
        if not reqs:
            continue
        unit = talent_builds_unit_name(hero)
        ap_hex = build_talent_builds_hex(reqs)
        build_hash = _hash_for_unit(unit, known_hashes)
        out_lines.append(
            f"{unit}=Build1|{ap_hex}|{_EMPTY_SLOT}|{_EMPTY_SLOT}|{build_hash}"
        )

    new_text = "\n".join(out_lines) + ("\n" if out_lines else "")
    if _normalize_builds_text(existing_text) == _normalize_builds_text(new_text):
        return TalentBuildsExportResult(
            path=path,
            heroes_written=len(out_lines),
            backup_path=None,
            skipped_unchanged=True,
        )

    backup_path: str | None = None
    if existing_text.strip():
        backup_path = _unique_backup_path(directory)
        with open(backup_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(existing_text if existing_text.endswith("\n") else existing_text + "\n")

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text)

    return TalentBuildsExportResult(
        path=path,
        heroes_written=len(out_lines),
        backup_path=backup_path,
        skipped_unchanged=False,
    )


def build_share_digits(
    hero: str,
    requirements: list[tuple[int, int]] | list[dict[str, int]],
    *,
    unforced_digit: str = "0",
) -> str:
    req_map: dict[int, int] = {}
    for req in requirements:
        if isinstance(req, dict):
            if talent_req_is_any(req):
                continue
            level, rank = int(req["level"]), int(req["rank"])
        else:
            level, rank = int(req[0]), int(req[1])
        req_map[level] = rank

    digits: list[str] = []
    for level in TALENT_LEVELS:
        if level in req_map:
            rank = int(req_map[level])
            total = talent_count(hero, level)
            if total and rank > total:
                rank = total
            if rank < 1:
                rank = 1
            digits.append(str(rank))
        else:
            digits.append(unforced_digit)
    return "".join(digits)


def build_share_code(
    hero: str,
    requirements: list[tuple[int, int]] | list[dict[str, int]],
    *,
    unforced_digit: str = "0",
) -> str:
    digits = build_share_digits(hero, requirements, unforced_digit=unforced_digit)
    return f"[T{digits},{build_code_hero_name(hero)}]"


def index_to_level_rank(hero: str, index: int) -> tuple[int, int] | None:
    if index < 0:
        return None
    remaining = index
    for level in TALENT_LEVELS:
        count = talent_count(hero, level)
        if remaining < count:
            return level, remaining + 1
        remaining -= count
    return None


def picks_from_indices(hero: str, indices: list[int]) -> list[tuple[int, int]]:
    picks: list[tuple[int, int]] = []
    seen_levels: set[int] = set()
    for index in indices:
        mapped = index_to_level_rank(hero, index)
        if mapped is None:
            continue
        level, rank = mapped
        if level in seen_levels:
            picks = [(lv, rk) for lv, rk in picks if lv != level]
        seen_levels.add(level)
        picks.append((level, rank))
    picks.sort(key=lambda pair: TALENT_LEVELS.index(pair[0]))
    return picks


def validate_exceptions() -> None:
    unknown = sorted(set(TALENT_COUNT_EXCEPTIONS) - set(ALL_HEROES))
    if unknown:
        raise ValueError(f"Talent exceptions for unknown heroes: {unknown}")

    outlier_heroes = (
        set(TALENT_L20_UNRESTRICTED)
        | set(TALENT_SINGLE_L20_UPGRADE)
        | set(TALENT_ULT_AT_LEVEL)
        | set(TALENT_L20_PREREQUISITES)
    )
    unknown_outliers = sorted(outlier_heroes - set(ALL_HEROES))
    if unknown_outliers:
        raise ValueError(f"Talent roll outliers for unknown heroes: {unknown_outliers}")


validate_exceptions()
