"""Loot chest economy — purchases synced via Archipelago data storage."""

import asyncio
from typing import TYPE_CHECKING

from .Items import (
    CHEST_COST_XP, CHEST_SLOTS, XP_BANK_ITEMS, LOOT_CHEST_NAME, open_capacity_value,
)
from .Locations import chest_location_name, location_name_to_id

if TYPE_CHECKING:
    from .Client import HoTSClient


class LootState:
    """Buy/open UI for sequential loot chests.

    XP-bought chest count is stored on the Archipelago server, so two
    clients on the same slot share one bank. Open/reveal progress comes from
    checked_locations.
    """

    def __init__(self, ctx: "HoTSClient"):
        self.ctx = ctx
        self.received_xp = 0
        self.bought_chests = 0
        self.free_loot_chests = 0
        self.owned_chests = 0
        self.chests_completed = 0
        self.active_chest: int | None = None
        self.revealed: dict[int, set[int]] = {}
        self.revealed_names: dict[str, str] = {}
        self.pending_flags: dict[str, int] = {}
        self.pending_names: dict[str, str] = {}
        self.pending_owners: dict[str, str] = {}
        self.recent_rewards: list[dict] = []
        self._awaiting_receive_slots: list[tuple[int, int]] = []
        self._click_feed_keys: set[str] = set()
        self._announced_buyable: int = 0
        self._storage_ready = False

    @property
    def purchased_chests(self) -> int:
        """Chests paid with XP, clamped so bank cannot go negative across clients."""
        cost = int(getattr(self.ctx, "chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        if cost <= 0:
            return 0
        return min(max(0, self.bought_chests), self.received_xp // cost)

    @property
    def bank_xp(self) -> int:
        cost = int(getattr(self.ctx, "chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        return max(0, self.received_xp - self.purchased_chests * cost)

    def revealed_for(self, chest_index: int) -> set[int]:
        return self.revealed.setdefault(chest_index, set())

    def chest_fully_revealed(self, chest_index: int | None) -> bool:
        if chest_index is None:
            return True
        return len(self.revealed_for(chest_index)) >= CHEST_SLOTS

    def reset(self) -> None:
        self.received_xp = 0
        self.bought_chests = 0
        self.free_loot_chests = 0
        self.owned_chests = 0
        self.chests_completed = 0
        self.active_chest = None
        self.revealed = {}
        self.revealed_names = {}
        self.pending_flags = {}
        self.pending_names = {}
        self.pending_owners = {}
        self.recent_rewards = []
        self._awaiting_receive_slots = []
        self._click_feed_keys = set()
        self._announced_buyable = 0
        self._storage_ready = False

    def _owner_label(self, player: int) -> str:
        if player == getattr(self.ctx, "slot", None):
            return "You"
        names = getattr(self.ctx, "player_names", None) or {}
        name = names.get(player)
        if name:
            return str(name)
        return f"Player {player}"

    def bind_to_room(self, cfg: dict) -> None:
        """Reconnect: rebuild from items + checked locations; wire server purchase counter."""
        self.reset()
        self._load_click_feed()
        self.recompute_from_items(announce=False)
        self.rebuild_from_server_checks()
        self.ctx._setup_loot_storage()
        self.resolve_bought_chests(cfg, announce=False, push_if_raised=True)
        self._refresh_announced_buyable(silent=True)
        if self.active_chest is not None:
            asyncio.create_task(self._scout_chest(self.active_chest))
        panel = getattr(self.ctx, "loot_panel", None)
        if panel is not None:
            panel.refresh()

    def _economy_local_key(self) -> str:
        seed = (getattr(self.ctx, "seed_name", None) or "").strip()
        return f"{seed}|{self.ctx.team}|{self.ctx.slot}"

    def _read_local_bought(self, cfg: dict | None = None) -> int:
        cfg = cfg if cfg is not None else getattr(self.ctx, "cfg", {}) or {}
        key = self._economy_local_key()
        if not key.startswith("|") and key:
            blob = (cfg.get("loot_economy") or {}).get(key) or {}
        else:
            blob = {}
        if blob.get("bought_chests") is not None:
            return max(0, int(blob.get("bought_chests") or 0))
        spent = max(0, int(blob.get("spent_xp", 0) or 0))
        cost = int(getattr(self.ctx, "chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        if cost > 0 and spent > 0:
            return spent // cost
        return 0

    def _write_local_bought(self, bought: int) -> None:
        """Mirror purchases locally so reconnect works even if data storage is empty."""
        persist = getattr(self.ctx, "persist_loot_bought", None)
        if callable(persist):
            persist(max(0, int(bought)))

    def _load_click_feed(self) -> None:
        key = self._economy_local_key()
        raw = (getattr(self.ctx, "cfg", {}) or {}).get("loot_click_feed") or {}
        entries = raw.get(key) if key and not key.startswith("|") else []
        loaded: list[dict] = []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "").strip()
                if not name or name in ("…", "(claimed)", "(already claimed)"):
                    continue
                loaded.append({"name": name, "flags": int(entry.get("flags", 0) or 0)})
        self.recent_rewards = loaded[: CHEST_SLOTS * 2]

    def _inferred_purchased_from_progress(self) -> int:
        """Chests already opened/touched must have been acquired somehow."""
        touched = self.chests_completed
        if self.active_chest is not None:
            touched = max(touched, self.active_chest)
        for chest, slots in self.revealed.items():
            if slots:
                touched = max(touched, int(chest))
        return max(0, touched - self.free_loot_chests)

    def resolve_bought_chests(
        self,
        cfg: dict | None = None,
        *,
        announce: bool = True,
        push_if_raised: bool = False,
    ) -> None:
        key = self.ctx._loot_bought_storage_key()
        stored = getattr(self.ctx, "stored_data", {}) or {}
        server_val: int | None = None
        for candidate in getattr(self.ctx, "_loot_bought_storage_keys", lambda: [key])():
            if candidate not in stored:
                continue
            raw = stored.get(candidate)
            try:
                val = max(0, int(raw or 0))
            except (TypeError, ValueError):
                val = 0
            server_val = val if server_val is None else max(server_val, val)
            self._storage_ready = True

        local_val = self._read_local_bought(cfg)
        inferred = self._inferred_purchased_from_progress()
        resolved = max(self.bought_chests, local_val, inferred)
        if server_val is not None:
            resolved = max(resolved, server_val)

        prev = self.bought_chests
        self.bought_chests = resolved
        self._recompute_owned()
        if resolved != prev or resolved > 0:
            self._write_local_bought(resolved)
        if push_if_raised and (server_val is None or resolved > server_val):
            asyncio.create_task(self._push_bought_replace(resolved))

        if announce:
            self._maybe_announce_buyable()
        else:
            self._refresh_announced_buyable(silent=True)
        panel = getattr(self.ctx, "loot_panel", None)
        if panel is not None:
            panel.refresh()

    def apply_bought_from_storage(self, *, announce: bool = True) -> None:
        self.resolve_bought_chests(announce=announce, push_if_raised=True)

    def recompute_from_items(self, *, announce: bool = True) -> None:
        received_xp = 0
        free = 0
        for item in self.ctx.items_received:
            name = self.ctx.item_names.lookup_in_game(item.item)
            if name == LOOT_CHEST_NAME:
                free += 1
            elif name in XP_BANK_ITEMS:
                received_xp += open_capacity_value(name)
        self.received_xp = received_xp
        self.free_loot_chests = free
        self._recompute_owned()
        if announce:
            self._maybe_announce_buyable()

    def _opened_from_inventory(self) -> int:
        n = self.chests_completed
        if self.active_chest is not None and not self.chest_fully_revealed(self.active_chest):
            if self.active_chest == self.chests_completed + 1:
                n += 1
        return n

    def _recompute_owned(self) -> None:
        self.owned_chests = max(
            0,
            self.purchased_chests + self.free_loot_chests - self._opened_from_inventory(),
        )

    def rebuild_from_server_checks(self) -> None:
        """Derive chest open progress solely from this room's checked_locations."""
        total = int(getattr(self.ctx, "loot_chest_count", 0) or 0)
        prev_active = self.active_chest
        keep_names = dict(self.revealed_names)
        keep_flags = dict(self.pending_flags)
        keep_pending = dict(self.pending_names)
        keep_owners = dict(self.pending_owners)
        self.revealed = {}
        self.revealed_names = keep_names
        self.pending_flags = keep_flags
        self.pending_names = keep_pending
        self.pending_owners = keep_owners
        self.chests_completed = 0
        self.active_chest = None
        in_progress: int | None = None

        for chest in range(1, total + 1):
            checked_slots: set[int] = set()
            for slot in range(CHEST_SLOTS):
                loc_id = location_name_to_id.get(chest_location_name(chest, slot + 1))
                if loc_id is not None and loc_id in self.ctx.checked_locations:
                    checked_slots.add(slot)
                    key = f"{chest}:{slot}"
                    if key not in self.revealed_names or self.revealed_names[key] in (
                        "(claimed)", "(already claimed)", "…",
                    ):
                        if self.pending_names.get(key):
                            self.revealed_names[key] = self.pending_names[key]
            if checked_slots:
                self.revealed[chest] = checked_slots
            if len(checked_slots) >= CHEST_SLOTS:
                self.chests_completed = chest
            elif checked_slots:
                in_progress = chest
                break

        if in_progress is not None:
            self.active_chest = in_progress
        elif prev_active and prev_active == self.chests_completed and self.chests_completed > 0:
            self.active_chest = prev_active
        elif in_progress is None and self.chests_completed > 0 and prev_active:
            self.active_chest = prev_active if prev_active <= self.chests_completed else None
        self._recompute_owned()

    def note_server_checks(self) -> None:
        """Fold newly checked chest locations into revealed sets without wiping scout data."""
        total = int(getattr(self.ctx, "loot_chest_count", 0) or 0)
        for chest in range(1, total + 1):
            for slot in range(CHEST_SLOTS):
                loc_id = location_name_to_id.get(chest_location_name(chest, slot + 1))
                if loc_id is None or loc_id not in self.ctx.checked_locations:
                    continue
                self.revealed.setdefault(chest, set()).add(slot)
                key = f"{chest}:{slot}"
                if self.pending_names.get(key) and (
                    key not in self.revealed_names
                    or self.revealed_names[key] in ("…", "(claimed)", "(already claimed)")
                ):
                    self.revealed_names[key] = self.pending_names[key]
            if len(self.revealed_for(chest)) >= CHEST_SLOTS and chest > self.chests_completed:
                self.chests_completed = chest
        self._recompute_owned()

    def _pipeline_count(self) -> int:
        if self.active_chest and not self.chest_fully_revealed(self.active_chest):
            return self.chests_completed + 1 + self.owned_chests
        return self.chests_completed + self.owned_chests

    def _refresh_announced_buyable(self, *, silent: bool) -> None:
        cost = int(getattr(self.ctx, "chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        total = int(getattr(self.ctx, "loot_chest_count", 0) or 0)
        room = max(0, total - self._pipeline_count())
        if cost > 0 and room > 0:
            affordable = min(self.bank_xp // cost, room)
        else:
            affordable = 0
        if silent:
            self._announced_buyable = affordable
        elif affordable > self._announced_buyable:
            self._maybe_announce_buyable()

    def _maybe_announce_buyable(self) -> None:
        from CommonClient import logger
        cost = int(getattr(self.ctx, "chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        total = int(getattr(self.ctx, "loot_chest_count", 0) or 0)
        room = max(0, total - self._pipeline_count())
        if room <= 0 or cost <= 0:
            return
        affordable = min(self.bank_xp // cost, room)
        if affordable > self._announced_buyable:
            newly = affordable - self._announced_buyable
            if newly == 1:
                logger.info(
                    "[HotS] Loot chests available - (1) (buy in the Loot tab)."
                )
            else:
                logger.info(
                    f"[HotS] Loot chests available - ({newly}) (buy in the Loot tab)."
                )
            self._announced_buyable = affordable

    def buy_chest(self) -> bool:
        cost = int(getattr(self.ctx, "chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        total = int(getattr(self.ctx, "loot_chest_count", 0) or 0)
        in_pipeline = self._pipeline_count()
        if self.bank_xp < cost or in_pipeline >= total:
            return False
        self.bought_chests += 1
        self._recompute_owned()
        self._announced_buyable = max(0, self._announced_buyable - 1)
        self._write_local_bought(self.bought_chests)
        asyncio.create_task(self._push_bought_delta(1))
        return True

    async def _push_bought_delta(self, delta: int) -> None:
        await self.ctx.send_msgs([{
            "cmd": "Set",
            "key": self.ctx._loot_bought_storage_key(),
            "default": 0,
            "want_reply": True,
            "operations": [{"operation": "add", "value": int(delta)}],
        }])

    async def _push_bought_replace(self, value: int) -> None:
        await self.ctx.send_msgs([{
            "cmd": "Set",
            "key": self.ctx._loot_bought_storage_key(),
            "default": 0,
            "want_reply": True,
            "operations": [{"operation": "max", "value": int(value)}],
        }])

    def can_begin_open(self) -> bool:
        total = int(getattr(self.ctx, "loot_chest_count", 0) or 0)
        if self.owned_chests < 1 or self.chests_completed >= total:
            return False
        if self.active_chest is not None and not self.chest_fully_revealed(self.active_chest):
            return False
        return True

    def begin_open(self) -> bool:
        cost = int(getattr(self.ctx, "chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        if not self.can_begin_open():
            return False
        next_index = self.chests_completed + 1
        if self._open_capacity_received() < next_index * cost:
            return False
        self.owned_chests -= 1
        self.active_chest = next_index
        self.revealed.setdefault(next_index, set())
        for slot in range(CHEST_SLOTS):
            key = f"{next_index}:{slot}"
            self.pending_flags.setdefault(key, 0)
        asyncio.create_task(self._scout_chest(next_index))
        return True

    async def _scout_chest(self, chest_index: int) -> None:
        ids: list[int] = []
        for slot in range(CHEST_SLOTS):
            loc_id = location_name_to_id.get(chest_location_name(chest_index, slot + 1))
            if loc_id is not None:
                ids.append(loc_id)
        if not ids:
            return
        await self.ctx.send_msgs([{
            "cmd": "LocationScouts",
            "locations": ids,
            "create_as_hint": 0,
        }])

    def apply_location_info(self, network_items: list) -> None:
        for net_item in network_items:
            if isinstance(net_item, dict):
                loc_id = int(net_item.get("location", 0) or 0)
                item_id = int(net_item.get("item", 0) or 0)
                flags = int(net_item.get("flags", 0) or 0)
                player = int(net_item.get("player", 0) or 0)
            else:
                loc_id = int(getattr(net_item, "location", 0) or 0)
                item_id = int(getattr(net_item, "item", 0) or 0)
                flags = int(getattr(net_item, "flags", 0) or 0)
                player = int(getattr(net_item, "player", 0) or 0)
            for chest in range(1, int(getattr(self.ctx, "loot_chest_count", 0) or 0) + 1):
                for slot in range(CHEST_SLOTS):
                    if location_name_to_id.get(chest_location_name(chest, slot + 1)) != loc_id:
                        continue
                    key = f"{chest}:{slot}"
                    name = None
                    try:
                        name = self.ctx.item_names.lookup_in_slot(item_id, player)
                    except Exception:
                        pass
                    if not name:
                        try:
                            name = self.ctx.item_names.lookup_in_game(item_id)
                        except Exception:
                            name = f"Item {item_id}"
                    self.pending_names[key] = name
                    self.pending_flags[key] = flags
                    if player:
                        self.pending_owners[key] = self._owner_label(player)
                    if slot in self.revealed_for(chest):
                        cur = self.revealed_names.get(key, "")
                        if not cur or cur in ("…", "(claimed)", "(already claimed)") or cur.startswith("Reward "):
                            self.revealed_names[key] = name
                        self._clear_awaiting(chest, slot)
                        self._feed_if_click(key, self.revealed_names.get(key) or name, flags)
                    break

    def _open_capacity_received(self) -> int:
        total = 0
        for item in self.ctx.items_received:
            name = self.ctx.item_names.lookup_in_game(item.item)
            total += open_capacity_value(name)
        return total

    def reveal_slot(self, slot_index: int) -> tuple[str, int] | None:
        if self.active_chest is None:
            return None
        chest = self.active_chest
        if self.chest_fully_revealed(chest):
            return None
        if slot_index in self.revealed_for(chest):
            return None
        loc_name = chest_location_name(chest, slot_index + 1)
        loc_id = location_name_to_id.get(loc_name)
        if loc_id is None:
            return None

        key = f"{chest}:{slot_index}"
        flags = self.pending_flags.get(key, 0)
        scout_name = self.pending_names.get(key)
        self._click_feed_keys.add(key)

        if loc_id in self.ctx.checked_locations:
            name = self.revealed_names.get(key) or scout_name or "…"
            self.revealed_for(chest).add(slot_index)
            if name and name not in ("(claimed)", "(already claimed)"):
                self.revealed_names[key] = name
            self._feed_if_click(key, self.revealed_names.get(key) or "", flags)
            self._mark_completed_if_done(chest)
            return self.revealed_names.get(key) or "…", flags

        self.revealed_for(chest).add(slot_index)
        name = scout_name or "…"
        self.revealed_names[key] = name
        self._awaiting_receive_slots.append((chest, slot_index))
        self._feed_if_click(key, name, flags)
        self._mark_completed_if_done(chest)
        asyncio.create_task(self._send_check(loc_id))
        return name, flags

    async def _send_check(self, loc_id: int) -> None:
        send = getattr(self.ctx, "_send_new_location_checks", None)
        if send is not None:
            await send([loc_id])
            return
        if loc_id in self.ctx.checked_locations:
            return
        self.ctx.checked_locations.add(loc_id)
        getattr(self.ctx, "locations_checked", set()).add(loc_id)
        await self.ctx.send_msgs([{"cmd": "LocationChecks", "locations": [loc_id]}])

    def remember_received_name(self, item_name: str, flags: int = 0) -> None:
        if not item_name:
            return
        still: list[tuple[int, int]] = []
        for chest, slot in self._awaiting_receive_slots:
            key = f"{chest}:{slot}"
            scout = self.pending_names.get(key) or ""
            cur = self.revealed_names.get(key, "")
            mine = self._slot_is_mine(key)
            if cur and cur not in ("…",) and not cur.startswith("Reward "):
                self._feed_if_click(key, cur, self.pending_flags.get(key, flags))
                continue
            if scout and scout != item_name:
                still.append((chest, slot))
                continue
            if mine is False:
                still.append((chest, slot))
                continue
            shown = scout or item_name
            self.revealed_names[key] = shown
            if flags:
                self.pending_flags[key] = flags
            self._feed_if_click(key, shown, self.pending_flags.get(key, flags))
        self._awaiting_receive_slots = still

    def _slot_is_mine(self, key: str) -> bool | None:
        owner = self.pending_owners.get(key)
        if owner == "You":
            return True
        if owner:
            return False
        return None

    def _clear_awaiting(self, chest: int, slot: int) -> None:
        pair = (chest, slot)
        if pair in self._awaiting_receive_slots:
            self._awaiting_receive_slots = [p for p in self._awaiting_receive_slots if p != pair]

    def _feed_if_click(self, key: str, name: str, flags: int = 0) -> None:
        if key not in self._click_feed_keys:
            return
        mine = self._slot_is_mine(key)
        if mine is False:
            self._click_feed_keys.discard(key)
            return
        if mine is not True:
            return
        if not name or name in ("…", "(already claimed)", "(claimed)"):
            return
        self._click_feed_keys.discard(key)
        self._push_recent(name, flags)

    def _push_recent(self, name: str, flags: int = 0) -> None:
        if not name or name in ("…", "(already claimed)", "(claimed)"):
            return
        self.recent_rewards = [{"name": name, "flags": flags}, *self.recent_rewards][: CHEST_SLOTS * 2]
        persist = getattr(self.ctx, "persist_loot_click_feed", None)
        if callable(persist):
            persist(self.recent_rewards)

    def _mark_completed_if_done(self, chest: int) -> None:
        if len(self.revealed_for(chest)) >= CHEST_SLOTS:
            if chest > self.chests_completed:
                self.chests_completed = chest
            self._recompute_owned()
