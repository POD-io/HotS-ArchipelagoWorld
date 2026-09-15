"""Replay parsing for .StormReplay files."""
import os
import re
import sys
from dataclasses import dataclass, field
from collections import defaultdict

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import mpyq
from heroprotocol.versions import protocol96477

GAMELOOP_PER_SECOND = 16


HUMAN_CONTROL = 2
AI_CONTROL = 3


@dataclass
class ReplayResult:
    map_name: str
    duration_seconds: int
    player_name: str
    hero: str
    hero_id: str
    toon_handle: str
    result: str
    score: dict = field(default_factory=dict)
    level_history: list = field(default_factory=list)
    talent_picks: list = field(default_factory=list)
    pid: int = 0
    team_id: int = 0
    control: int = HUMAN_CONTROL
    is_ai: bool = False
    is_host: bool = False


def normalize_toon_handle(handle: str | None) -> str | None:
    if not handle:
        return handle
    handle = handle.strip()
    m = re.match(r"^(\d+-Hero-\d+-\d+)(?:-\d+)?$", handle, re.I)
    if m:
        return m.group(1)
    return handle


def battle_tags_match(configured: str | None, replay_name: str | None) -> bool:
    if not configured or not replay_name:
        return False
    return configured.strip().lower() == replay_name.strip().lower()


def battle_tags_match_any(configured: list[str] | None, replay_name: str | None) -> bool:
    return any(battle_tags_match(tag, replay_name) for tag in (configured or []))


def _b(v) -> str:
    return v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v) if v is not None else ""


def _kv_int(entries, key: str):
    for e in (entries or []):
        if _b(e.get("m_key")) == key:
            return e.get("m_value")
    return None


def _kv_str(entries, key: str) -> str | None:
    for e in (entries or []):
        if _b(e.get("m_key")) == key:
            return _b(e.get("m_value"))
    return None


def _extract_players(tracker_events: list) -> dict:
    players: dict = {}
    for event in tracker_events:
        if event.get("_event") != "NNet.Replay.Tracker.SStatGameEvent":
            continue
        ev = _b(event.get("m_eventName"))
        if ev == "PlayerInit":
            pid = _kv_int(event.get("m_intData"), "PlayerID")
            if pid is not None:
                players.setdefault(pid, {})
                players[pid]["toon_handle"] = _kv_str(event.get("m_stringData"), "ToonHandle")
        elif ev == "PlayerSpawned":
            pid = _kv_int(event.get("m_intData"), "PlayerID")
            if pid is not None:
                players.setdefault(pid, {})
                players[pid]["hero_id"] = _kv_str(event.get("m_stringData"), "Hero") or ""
        elif ev == "EndOfGameTalentChoices":
            pid = _kv_int(event.get("m_intData"), "PlayerID")
            if pid is not None:
                players.setdefault(pid, {})
                players[pid]["result"] = _kv_str(event.get("m_stringData"), "Win/Loss")
    return players


def _extract_details_by_slot(archive) -> tuple[dict[int, str], dict[int, str], dict[int, dict]]:
    try:
        details = protocol96477.decode_replay_details(archive.read_file("replay.details"))
    except Exception:
        return {}, {}, {}
    names: dict[int, str] = {}
    heroes: dict[int, str] = {}
    meta: dict[int, dict] = {}
    for slot in details.get("m_playerList", []):
        slot_id = slot.get("m_workingSetSlotId")
        if slot_id is None:
            continue
        if int(slot.get("m_observe") or 0):
            continue
        pid = slot_id + 1
        names[pid] = _b(slot.get("m_name", b""))
        heroes[pid] = _b(slot.get("m_hero", b""))
        control = int(slot.get("m_control") or 0)
        meta[pid] = {
            "control": control,
            "team_id": int(slot.get("m_teamId") or 0),
            "is_ai": control == AI_CONTROL,
        }
    return names, heroes, meta


def _extract_map_name(tracker_events: list) -> str:
    for event in tracker_events:
        if event.get("_event") != "NNet.Replay.Tracker.SStatGameEvent":
            continue
        if _b(event.get("m_eventName")) != "EndOfGameTalentChoices":
            continue
        name = _kv_str(event.get("m_stringData"), "Map")
        if name:
            return name
    return "Unknown"


def _extract_score(tracker_events: list) -> dict:
    scores: dict = defaultdict(dict)
    for event in tracker_events:
        if event.get("_event") != "NNet.Replay.Tracker.SScoreResultEvent":
            continue
        for instance in event.get("m_instanceList", []):
            stat_name = _b(instance.get("m_name"))
            for slot_idx, timeseries in enumerate(instance.get("m_values", [])):
                if timeseries:
                    scores[slot_idx + 1][stat_name] = timeseries[-1].get("m_value", 0)
    return dict(scores)


def _extract_level_history(tracker_events: list) -> dict:
    levels: dict = defaultdict(list)
    for event in tracker_events:
        if event.get("_event") != "NNet.Replay.Tracker.SStatGameEvent":
            continue
        if _b(event.get("m_eventName")) != "LevelUp":
            continue
        pid = _kv_int(event.get("m_intData"), "PlayerID")
        lvl = _kv_int(event.get("m_intData"), "Level")
        if pid is not None and lvl is not None:
            levels[pid].append(lvl)
    return dict(levels)


def _userid_by_toon(archive) -> dict[str, int]:
    try:
        init = protocol96477.decode_replay_initdata(archive.read_file("replay.initData"))
    except Exception:
        return {}
    lobby = (init.get("m_syncLobbyState") or {}).get("m_lobbyState") or {}
    mapping: dict[str, int] = {}
    for slot in lobby.get("m_slots") or []:
        user_id = slot.get("m_userId")
        toon = normalize_toon_handle(_b(slot.get("m_toonHandle")))
        if user_id is None or not toon:
            continue
        mapping[toon.lower()] = user_id
    return mapping


def _extract_talent_indices(game_events: list, user_id: int | None) -> list[int]:
    if user_id is None:
        return []
    indices: list[int] = []
    for event in game_events:
        if event.get("_event") != "NNet.Game.SHeroTalentTreeSelectedEvent":
            continue
        if event.get("_userid", {}).get("m_userId") != user_id:
            continue
        index = event.get("m_index")
        if isinstance(index, int):
            indices.append(index)
    return indices


def find_player(
    players: dict,
    names: dict,
    *,
    toon_handle: str | None = None,
    player_name: str | None = None,
    hero_name: str | None = None,
    heroes: dict | None = None,
) -> int | None:
    if toon_handle:
        needle = normalize_toon_handle(toon_handle) or ""
        for pid, p in players.items():
            stored = normalize_toon_handle(p.get("toon_handle")) or ""
            if stored.lower() == needle.lower():
                return pid

    if player_name:
        needle = player_name.strip().lower()
        if needle:
            for pid in sorted(players):
                if names.get(pid, "").lower() == needle:
                    return pid

    if hero_name and heroes:
        from .Challenges import hero_from_replay_name

        target = hero_from_replay_name(hero_name) or hero_name
        matches = [
            pid for pid, replay_hero in heroes.items()
            if hero_from_replay_name(replay_hero) == target
        ]
        if len(matches) == 1:
            return matches[0]

    return None


def pick_host_result(
    roster: list[ReplayResult],
    *,
    toon_handle: str | None = None,
    player_name: str | None = None,
    player_names: list[str] | None = None,
    hero_name: str | None = None,
) -> ReplayResult | None:
    if not roster:
        return None
    target_toon = normalize_toon_handle(toon_handle)
    if target_toon:
        needle = target_toon.lower()
        for row in roster:
            stored = (normalize_toon_handle(row.toon_handle) or "").lower()
            if stored == needle:
                row.is_host = True
                return row
    names = [player_name, *(player_names or [])]
    seen: set[str] = set()
    for tag in names:
        key = (tag or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        for row in roster:
            if battle_tags_match(tag, row.player_name):
                row.is_host = True
                return row
    if hero_name:
        from .Challenges import hero_from_replay_name

        target = hero_from_replay_name(hero_name) or hero_name
        matches = [
            row for row in roster
            if (hero_from_replay_name(row.hero) or row.hero) == target
        ]
        if len(matches) == 1:
            matches[0].is_host = True
            return matches[0]
    return None


CREDIT_MODES = ("me", "team", "match")


def normalize_credit_mode(mode: str | None) -> str:
    value = (mode or "me").strip().lower()
    return value if value in CREDIT_MODES else "me"


def select_credited_results(
    roster: list[ReplayResult],
    host: ReplayResult | None,
    *,
    credit_mode: str = "me",
    include_ai: bool = False,
    credit_names: list[str] | None = None,
) -> list[ReplayResult]:
    mode = normalize_credit_mode(credit_mode)
    names = [n.strip() for n in (credit_names or []) if str(n).strip()]

    if mode == "me":
        return [host] if host is not None else []
    if mode == "team" and host is None:
        return []

    pool: list[ReplayResult] = []
    for row in roster:
        if mode == "team" and host is not None and row.team_id != host.team_id:
            continue
        if row.is_ai:
            if include_ai:
                pool.append(row)
            continue
        if names and not battle_tags_match_any(names, row.player_name):
            continue
        pool.append(row)

    credited: list[ReplayResult] = []
    seen_heroes: set[str] = set()
    seen_pids: set[int] = set()
    for row in pool:
        if row.pid in seen_pids:
            continue
        hero_key = (row.hero or "").strip().lower()
        if hero_key and hero_key in seen_heroes:
            continue
        seen_pids.add(row.pid)
        if hero_key:
            seen_heroes.add(hero_key)
        credited.append(row)
    return credited


def parse_replay_roster(path: str) -> list[ReplayResult]:
    try:
        archive = mpyq.MPQArchive(path)
        raw_header = archive.header["user_data_header"]["content"]
        header = protocol96477.decode_replay_header(raw_header)
        tracker_events = list(protocol96477.decode_replay_tracker_events(
            archive.read_file("replay.tracker.events")
        ))
    except Exception:
        return []

    if not tracker_events:
        return []

    duration_seconds = header.get("m_elapsedGameLoops", 0) // GAMELOOP_PER_SECOND
    players = _extract_players(tracker_events)
    names, heroes_by_pid, meta_by_pid = _extract_details_by_slot(archive)
    map_name = _extract_map_name(tracker_events)
    score_by_pid = _extract_score(tracker_events)
    level_by_pid = _extract_level_history(tracker_events)

    talent_by_pid: dict[int, list] = {}
    try:
        game_events = list(protocol96477.decode_replay_game_events(
            archive.read_file("replay.game.events")
        ))
        user_map = _userid_by_toon(archive)
        from .Challenges import hero_from_replay_name
        from .Talents import picks_from_indices

        for pid, p in players.items():
            toon = normalize_toon_handle(p.get("toon_handle")) or ""
            if not toon:
                continue
            user_id = user_map.get(toon.lower())
            talent_indices = _extract_talent_indices(game_events, user_id)
            hero_display = heroes_by_pid.get(pid, "")
            hero_key = hero_from_replay_name(hero_display) or hero_display
            if hero_key and talent_indices:
                talent_by_pid[pid] = picks_from_indices(hero_key, talent_indices)
    except Exception:
        talent_by_pid = {}

    roster: list[ReplayResult] = []
    pids = sorted(set(players) | set(names) | set(heroes_by_pid))
    for pid in pids:
        p = players.get(pid, {})
        meta = meta_by_pid.get(pid, {})
        hero_display = heroes_by_pid.get(pid, "")
        if not hero_display and not names.get(pid):
            continue
        roster.append(ReplayResult(
            map_name=map_name,
            duration_seconds=duration_seconds,
            player_name=names.get(pid, f"Player {pid}"),
            hero=hero_display,
            hero_id=p.get("hero_id", ""),
            toon_handle=normalize_toon_handle(p.get("toon_handle")) or "",
            result=p.get("result") or "Unknown",
            score=score_by_pid.get(pid, {}),
            level_history=level_by_pid.get(pid, []),
            talent_picks=talent_by_pid.get(pid, []),
            pid=pid,
            team_id=int(meta.get("team_id") or 0),
            control=int(meta.get("control") or 0),
            is_ai=bool(meta.get("is_ai")),
        ))
    return roster


def parse_replay(
    path: str,
    toon_handle: str | None = None,
    player_name: str | None = None,
    player_names: list[str] | None = None,
    hero_name: str | None = None,
) -> ReplayResult | None:
    roster = parse_replay_roster(path)
    return pick_host_result(
        roster,
        toon_handle=toon_handle,
        player_name=player_name,
        player_names=player_names,
        hero_name=hero_name,
    )
