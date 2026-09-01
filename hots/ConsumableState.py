"""Stimpack and Talent Tome inventory — state synced via data storage."""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING

from CommonClient import logger

from .Items import STIMPACK_NAME, TALENT_TOME_NAME
from .Locations import location_name_to_id
from .Talents import (
    can_unlock_any_talent_slot,
    talent_count,
    talent_location_name,
    talent_req_is_any,
    unlock_any_talent_slot,
)

if TYPE_CHECKING:
    from .Client import HoTSClient


def _as_int(value, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(v) for v in parsed if v]
    return []


def _as_reqs(value) -> dict[str, list[dict[str, int]]] | None:
    raw = value
    if isinstance(value, str) and value.strip():
        try:
            raw = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    out: dict[str, list[dict[str, int]]] = {}
    for hero, reqs in raw.items():
        if not isinstance(reqs, list):
            return None
        parsed: list[dict[str, int]] = []
        for req in reqs:
            if not isinstance(req, dict) or "level" not in req or "rank" not in req:
                return None
            parsed.append({
                "level": int(req["level"]),
                "rank": int(req["rank"]),
                **({"any": True} if req.get("any") else {}),
            })
        out[str(hero)] = parsed
    return out


# Every cumulative scoreboard tally that feeds AP progress. Level / Win / talents stay 1x.
STIMPACK_SCORE_FIELDS = frozenset({
    "ExperienceContribution",
    "HeroDamage",
    "SiegeDamage",
    "Healing",
    "SelfHealing",
    "ProtectionGivenToAllies",
    "Takedowns",
    "Assists",
    "SoloKill",
    "MinionKills",
    "MercCampCaptures",
    "RegenGlobes",
    "TimeStunningEnemyHeroes",
    "TimeSilencingEnemyHeroes",
})


def apply_stimpack_score(score: dict) -> dict:
    """Return a copy with Stimpack tally fields doubled. Level and win are unchanged."""
    out = dict(score)
    for key in STIMPACK_SCORE_FIELDS:
        val = out.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out[key] = int(val) * 2
    return out


def _req_fingerprint(reqs) -> str:
    parsed = _as_reqs(reqs)
    if not parsed:
        return ""
    parts: list[str] = []
    for hero in sorted(parsed):
        packed = ",".join(
            f"{int(row['level'])}:{int(row['rank'])}:{'A' if talent_req_is_any(row) else 'R'}"
            for row in sorted(parsed[hero], key=lambda item: int(item["level"]))
        )
        parts.append(f"{hero}={packed}")
    return "|".join(parts)


class ConsumableState:
    """Bag counts + active Stimpack matches, mirrored locally and on the AP server."""

    def __init__(self, ctx: "HoTSClient"):
        self.ctx = ctx
        self.received_stim = 0
        self.received_tomes = 0
        self.stim_consumed = 0
        self.stim_used = 0
        self.tome_consumed = 0
        self.boosted_replays: list[str] = []
        self._storage_ready = False

    @property
    def stim_in_bag(self) -> int:
        return max(0, self.received_stim - self.stim_consumed)

    @property
    def tomes_in_bag(self) -> int:
        return max(0, self.received_tomes - self.tome_consumed)

    @property
    def stim_remaining(self) -> int:
        return max(0, self.stim_consumed - self.stim_used)

    def reset(self) -> None:
        self.received_stim = 0
        self.received_tomes = 0
        self.stim_consumed = 0
        self.stim_used = 0
        self.tome_consumed = 0
        self.boosted_replays = []
        self._storage_ready = False

    def bind_to_room(self, cfg: dict) -> None:
        self.reset()
        self.recompute_from_items()
        self._read_local(cfg)
        self._apply_stored_talent_reqs(self._local_blob(cfg).get("talent_requirements"))
        self.ctx._setup_consumable_storage()
        self.resolve_from_storage(cfg, announce=False, push_if_raised=True)
        self._refresh_panels()

    def recompute_from_items(self) -> None:
        stim = 0
        tomes = 0
        for item in self.ctx.items_received:
            name = self.ctx.item_names.lookup_in_game(item.item)
            if name == STIMPACK_NAME:
                stim += 1
            elif name == TALENT_TOME_NAME:
                tomes += 1
        self.received_stim = stim
        self.received_tomes = tomes

    def _economy_local_key(self) -> str:
        seed = (getattr(self.ctx, "seed_name", None) or "").strip()
        return f"{seed}|{self.ctx.team}|{self.ctx.slot}"

    def _local_blob(self, cfg: dict | None = None) -> dict:
        cfg = cfg if cfg is not None else getattr(self.ctx, "cfg", {}) or {}
        key = self._economy_local_key()
        if not key.startswith("|") and key:
            blob = (cfg.get("consumables") or {}).get(key) or {}
            return blob if isinstance(blob, dict) else {}
        return {}

    def _read_local(self, cfg: dict | None = None) -> None:
        blob = self._local_blob(cfg)
        self.stim_consumed = max(self.stim_consumed, _as_int(blob.get("stim_consumed")))
        self.stim_used = max(self.stim_used, _as_int(blob.get("stim_used")))
        self.tome_consumed = max(self.tome_consumed, _as_int(blob.get("tome_consumed")))
        for name in _as_str_list(blob.get("boosted_replays")):
            if name not in self.boosted_replays:
                self.boosted_replays.append(name)

    def _write_local(self) -> None:
        persist = getattr(self.ctx, "persist_consumables", None)
        if callable(persist):
            persist({
                "stim_consumed": self.stim_consumed,
                "stim_used": self.stim_used,
                "tome_consumed": self.tome_consumed,
                "boosted_replays": list(self.boosted_replays),
                "talent_requirements": self.ctx.hero_talent_requirements,
            })

    def _reqs_compatible(self, stored: dict[str, list[dict[str, int]]]) -> bool:
        generated = getattr(self.ctx, "slot_data", {}) or {}
        original = generated.get("hero_talent_requirements") or {}
        if set(stored) != set(original):
            return False
        for hero, greqs in original.items():
            sreqs = stored.get(hero) or []
            if {int(r["level"]) for r in sreqs} != {int(r["level"]) for r in greqs}:
                return False
            for req in sreqs:
                total = talent_count(hero, int(req["level"]))
                if int(req["rank"]) < 1 or int(req["rank"]) > total:
                    return False
        return True

    def _apply_stored_talent_reqs(self, raw) -> bool:
        stored = _as_reqs(raw)
        if not stored or not self._reqs_compatible(stored):
            return False
        self.ctx.hero_talent_requirements = stored
        return True

    def resolve_from_storage(
        self,
        cfg: dict | None = None,
        *,
        announce: bool = True,
        push_if_raised: bool = False,
    ) -> None:
        stored = getattr(self.ctx, "stored_data", {}) or {}

        def _read_counter(key: str, current: int) -> int:
            if key not in stored:
                return current
            self._storage_ready = True
            return max(current, _as_int(stored.get(key)))

        self._read_local(cfg)
        self.stim_consumed = _read_counter(self.ctx._stim_consumed_storage_key(), self.stim_consumed)
        self.stim_used = _read_counter(self.ctx._stim_used_storage_key(), self.stim_used)
        self.tome_consumed = _read_counter(self.ctx._tome_consumed_storage_key(), self.tome_consumed)

        replay_key = self.ctx._boosted_replays_storage_key()
        if replay_key in stored:
            for name in _as_str_list(stored.get(replay_key)):
                if name not in self.boosted_replays:
                    self.boosted_replays.append(name)

        req_key = self.ctx._talent_reqs_storage_key()
        if req_key in stored:
            self._apply_stored_talent_reqs(stored.get(req_key))

        self._write_local()
        if push_if_raised:
            def _needs_max(key: str, value: int) -> bool:
                if key not in stored:
                    return value > 0
                return value > _as_int(stored.get(key))

            if _needs_max(self.ctx._stim_consumed_storage_key(), self.stim_consumed):
                asyncio.create_task(self._push_max(self.ctx._stim_consumed_storage_key(), self.stim_consumed))
            if _needs_max(self.ctx._stim_used_storage_key(), self.stim_used):
                asyncio.create_task(self._push_max(self.ctx._stim_used_storage_key(), self.stim_used))
            if _needs_max(self.ctx._tome_consumed_storage_key(), self.tome_consumed):
                asyncio.create_task(self._push_max(self.ctx._tome_consumed_storage_key(), self.tome_consumed))
            server_replays = set(_as_str_list(stored.get(replay_key))) if replay_key in stored else None
            if self.boosted_replays and (
                server_replays is None or set(self.boosted_replays) != server_replays
            ):
                asyncio.create_task(self._push_replace(
                    replay_key, json.dumps(self.boosted_replays),
                ))
            if self.tome_consumed > 0 and self.ctx.hero_talent_requirements:
                server_fp = _req_fingerprint(stored.get(req_key)) if req_key in stored else ""
                local_fp = _req_fingerprint(self.ctx.hero_talent_requirements)
                if local_fp and local_fp != server_fp:
                    asyncio.create_task(self._push_replace(
                        req_key, json.dumps(self.ctx.hero_talent_requirements),
                    ))

        if announce:
            self._refresh_panels()

    def apply_from_storage(self) -> None:
        self.resolve_from_storage(announce=True, push_if_raised=True)

    async def _push_add(self, key: str, delta: int) -> None:
        await self.ctx.send_msgs([{
            "cmd": "Set",
            "key": key,
            "default": 0,
            "want_reply": True,
            "operations": [{"operation": "add", "value": int(delta)}],
        }])

    async def _push_max(self, key: str, value: int) -> None:
        await self.ctx.send_msgs([{
            "cmd": "Set",
            "key": key,
            "default": 0,
            "want_reply": True,
            "operations": [{"operation": "max", "value": int(value)}],
        }])

    async def _push_replace(self, key: str, value: str) -> None:
        await self.ctx.send_msgs([{
            "cmd": "Set",
            "key": key,
            "default": "",
            "want_reply": True,
            "operations": [{"operation": "replace", "value": value}],
        }])

    def _refresh_panels(self) -> None:
        panel = getattr(self.ctx, "loot_panel", None)
        if panel is not None:
            panel.refresh()
        talents = getattr(self.ctx, "talents_panel", None)
        if talents is not None:
            talents.refresh()
        tracker = getattr(self.ctx, "tracker", None)
        if tracker is not None:
            tracker.refresh()

    def drink_stimpack(self) -> bool:
        """Queue one 2x match. A second use adds another match, it does not 4x."""
        if self.stim_in_bag < 1:
            return False
        self.stim_consumed += 1
        self._write_local()
        asyncio.create_task(self._push_add(self.ctx._stim_consumed_storage_key(), 1))
        logger.info(
            f"[HotS] Stimpack used — next {self.stim_remaining} match"
            f"{'' if self.stim_remaining == 1 else 'es'} "
            f"tallies count double "
            f"({self.stim_in_bag} left in bag)."
        )
        self._refresh_panels()
        return True

    def consume_boost_for_replay(self, path: str) -> bool:
        """True if this parse should count double.

        Drink queues a charge (stim_consumed). A credited match spends one (stim_used).
        Both counters are mirrored to AP data storage and hots_config.json, so a restart
        still has N matches queued. /rescan of a replay already in boosted_replays
        reapplies 2x and does not spend another charge.
        """
        fname = os.path.basename(path)
        if fname in self.boosted_replays:
            return True
        if self.stim_remaining <= 0:
            return False
        self.stim_used += 1
        self.boosted_replays.append(fname)
        self._write_local()
        asyncio.create_task(self._push_add(self.ctx._stim_used_storage_key(), 1))
        asyncio.create_task(self._push_replace(
            self.ctx._boosted_replays_storage_key(), json.dumps(self.boosted_replays),
        ))
        return True

    def locked_talent_levels(self, hero: str) -> set[int]:
        locked: set[int] = set()
        for req in self.ctx.hero_talent_requirements.get(hero) or []:
            level = int(req["level"])
            loc_id = location_name_to_id.get(talent_location_name(hero, level))
            if loc_id is not None and loc_id in self.ctx.checked_locations:
                locked.add(level)
        return locked

    def can_unlock_any(self, hero: str, level: int) -> bool:
        if self.tomes_in_bag < 1:
            return False
        reqs = self.ctx.hero_talent_requirements.get(hero) or []
        return can_unlock_any_talent_slot(level, reqs, self.locked_talent_levels(hero))

    def drink_talent_tome(self, hero: str, level: int) -> str | None:
        """Make one uncompleted talent tier accept any pick. Returns a status line, or None."""
        if self.tomes_in_bag < 1:
            return None
        reqs = list(self.ctx.hero_talent_requirements.get(hero) or [])
        locked = self.locked_talent_levels(hero)
        new_reqs = unlock_any_talent_slot(level, reqs, locked)
        if new_reqs is None:
            return None
        self.ctx.hero_talent_requirements[hero] = new_reqs
        self.tome_consumed += 1
        self._write_local()
        asyncio.create_task(self._push_add(self.ctx._tome_consumed_storage_key(), 1))
        asyncio.create_task(self._push_replace(
            self.ctx._talent_reqs_storage_key(),
            json.dumps(self.ctx.hero_talent_requirements),
        ))
        msg = (
            f"[HotS] Talent Tome: {hero} Level {level} now accepts any pick "
            f"({self.tomes_in_bag} tome{'' if self.tomes_in_bag == 1 else 's'} left)."
        )
        logger.info(msg)
        export_fn = getattr(self.ctx, "install_talent_builds", None)
        if callable(export_fn):
            export_fn()
        self._refresh_panels()
        return msg
