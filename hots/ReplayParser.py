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


def _extract_details_by_slot(archive) -> tuple[dict[int, str], dict[int, str]]:
    try:
        details = protocol96477.decode_replay_details(archive.read_file("replay.details"))
    except Exception:
        return {}, {}
    names: dict[int, str] = {}
    heroes: dict[int, str] = {}
    for slot in details.get("m_playerList", []):
        slot_id = slot.get("m_workingSetSlotId")
        if slot_id is None:
            continue
        pid = slot_id + 1
        names[pid] = _b(slot.get("m_name", b""))
        heroes[pid] = _b(slot.get("m_hero", b""))
    return names, heroes


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


def parse_replay(
    path: str,
    toon_handle: str | None = None,
    player_name: str | None = None,
    hero_name: str | None = None,
) -> ReplayResult | None:
    try:
        archive = mpyq.MPQArchive(path)
        raw_header = archive.header["user_data_header"]["content"]
        header = protocol96477.decode_replay_header(raw_header)
        tracker_events = list(protocol96477.decode_replay_tracker_events(
            archive.read_file("replay.tracker.events")
        ))
    except Exception:
        return None

    if not tracker_events:
        return None

    duration_seconds = header.get("m_elapsedGameLoops", 0) // GAMELOOP_PER_SECOND
    players = _extract_players(tracker_events)
    names, heroes_by_pid = _extract_details_by_slot(archive)
    map_name = _extract_map_name(tracker_events)
    score_by_pid = _extract_score(tracker_events)
    level_by_pid = _extract_level_history(tracker_events)

    target_toon = normalize_toon_handle(toon_handle)
    target_pid = find_player(
        players,
        names,
        toon_handle=target_toon,
        player_name=player_name,
        hero_name=hero_name,
        heroes=heroes_by_pid,
    )
    if target_pid is None:
        return None

    p = players[target_pid]
    result_toon = normalize_toon_handle(p.get("toon_handle") or target_toon) or ""
    talent_picks: list[tuple[int, int]] = []
    try:
        game_events = list(protocol96477.decode_replay_game_events(
            archive.read_file("replay.game.events")
        ))
        user_map = _userid_by_toon(archive)
        user_id = user_map.get(result_toon.lower()) if result_toon else None
        talent_indices = _extract_talent_indices(game_events, user_id)
        from .Challenges import hero_from_replay_name
        from .Talents import picks_from_indices

        hero_display = heroes_by_pid.get(target_pid, "")
        hero_key = hero_from_replay_name(hero_display) or hero_display
        if hero_key and talent_indices:
            talent_picks = picks_from_indices(hero_key, talent_indices)
    except Exception:
        talent_picks = []

    return ReplayResult(
        map_name=map_name,
        duration_seconds=duration_seconds,
        player_name=names.get(target_pid, f"Player {target_pid}"),
        hero=heroes_by_pid.get(target_pid, ""),
        hero_id=p.get("hero_id", ""),
        toon_handle=result_toon,
        result=p.get("result") or "Unknown",
        score=score_by_pid.get(target_pid, {}),
        level_history=level_by_pid.get(target_pid, []),
        talent_picks=talent_picks,
        pid=target_pid,
    )
