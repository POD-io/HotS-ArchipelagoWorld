"""Heroes of the Storm Archipelago client."""
from __future__ import annotations
import asyncio
import json
import os
import re
import time
from typing import Optional
from NetUtils import ClientStatus
from CommonClient import (
    CommonContext, ClientCommandProcessor, server_loop, logger, get_base_parser, gui_enabled,
)
from Utils import user_path
from .Challenges import HERO_CHECKS, ALL_HEROES, detect_checks, hero_from_replay_name, location_name, get_role
from .Locations import location_name_to_id
from .ReplayParser import battle_tags_match, parse_replay
from .Tracker import HoTSTracker

POLL_INTERVAL = 10
SETTLE_DELAY = 4
CONFIG_FILE = user_path("hots_config.json")
ACCOUNTS_ROOT = os.path.join(
    os.path.expanduser("~"), "Documents", "Heroes of the Storm", "Accounts"
)
_TOON_PART = re.compile(r"^\d+-Hero-\d+-\d+$", re.I)

class HoTSClientCommandProcessor(ClientCommandProcessor):

    def _cmd_hots(self) -> bool:
        """Show unlocked heroes and open checks in the tracker."""
        if isinstance(self.ctx, HoTSClient) and self.ctx.tracker:
            self.ctx.tracker.print_status(self.output)
        else:
            self.output("Not connected to a HotS slot.")
        return True

    def _cmd_rescan(self) -> bool:
        """Reprocess your most recent replay file and send any new checks."""
        if not isinstance(self.ctx, HoTSClient):
            self.output("Not connected.")
            return True
        path = _latest_replay_path(self.ctx.replay_dirs)
        if not path:
            self.output("No replays found in configured folders.")
            return True
        asyncio.create_task(self.ctx._rescan_latest(path))
        self.output(f"Reprocessing latest replay: {os.path.basename(path)}")
        return True

    def _cmd_name(self, *parts: str) -> bool:
        """Show or set your HotS battle tag (in-game player name). Usage: /name YourBattleTag"""
        if not isinstance(self.ctx, HoTSClient):
            self.output("Not connected.")
            return True
        if not parts:
            tag = self.ctx.battle_tag or "(not set)"
            self.output(f"HotS player name: {tag}")
            detected = self.ctx._battle_tag_from_replay(_latest_replay_path(self.ctx.replay_dirs))
            if detected and detected != self.ctx.battle_tag:
                self.output(f"Latest replay shows: {detected}")
            self.output("Set with: /name YourBattleTag")
            self.output("Names with spaces work — type the full tag after /name.")
            return True
        new_tag = " ".join(parts).strip()
        if not new_tag:
            self.output("Usage: /name YourBattleTag")
            return True
        self.ctx.battle_tag = new_tag
        self.ctx.cfg["battle_tag"] = new_tag
        _save_config(self.ctx.cfg)
        latest = _latest_replay_path(self.ctx.replay_dirs)
        detected = self.ctx._battle_tag_from_replay(latest)
        if detected and not battle_tags_match(new_tag, detected):
            self.output(
                f"Saved as {new_tag!r}, but your latest replay shows {detected!r}. "
                "If replays are skipped, double-check the name."
            )
        else:
            self.output(f"HotS player name set to {new_tag}")
        return True

    def _cmd_goal(self) -> bool:
        """Show goal mode and progress on goal locations."""
        if not isinstance(self.ctx, HoTSClient) or not self.ctx.slot_data:
            self.output("Not connected.")
            return True
        sd = self.ctx.slot_data
        self.output(f"Goal ({sd.get('goal_mode', '?')}): {sd.get('goal_summary', '?')}")
        for name in sd.get("goal_location_names", []):
            if self.ctx.tracker and self.ctx.tracker.is_checked(name):
                mark = "done"
            elif self.ctx.tracker and self.ctx.tracker.location_accessible(name):
                mark = "open"
            else:
                mark = "locked"
            self.output(f"  [{mark}] {name}")
        return True

    def _cmd_heroes(self) -> bool:
        """List heroes unlocked for this seed."""
        if not isinstance(self.ctx, HoTSClient):
            self.output("Not connected.")
            return True
        unlocked = sorted(h for h in self.ctx.enabled_heroes if self.ctx._hero_unlocked(h))
        locked = sorted(h for h in self.ctx.enabled_heroes if not self.ctx._hero_unlocked(h))
        self.output(f"Unlocked ({len(unlocked)}): {', '.join(unlocked) or '(none)'}")
        if locked:
            self.output(f"Locked ({len(locked)}): {', '.join(locked)}")
        return True


def _load_config() -> dict:
    try:
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def _find_multiplayer_dirs(root: str) -> list[str]:
    dirs = []
    try:
        for dirpath, _, _ in os.walk(root):
            if os.path.basename(dirpath).lower() == "multiplayer":
                dirs.append(dirpath)
    except Exception:
        pass
    return dirs

def _toon_handle_from_replay_path(replay_path: str) -> Optional[str]:
    """Account folder embedded in the replay file path (internal ID, not shown to players)."""
    try:
        for part in reversed(os.path.normpath(replay_path).split(os.sep)):
            if _TOON_PART.match(part):
                return part
    except Exception:
        pass
    return None

def _scan_replay_mtimes(dirs: list[str]) -> dict[str, float]:
    mtimes: dict[str, float] = {}
    for d in dirs:
        try:
            for name in os.listdir(d):
                if name.lower().endswith(".stormreplay"):
                    path = os.path.join(d, name)
                    try:
                        mtimes[path] = os.path.getmtime(path)
                    except OSError:
                        pass
        except Exception:
            pass
    return mtimes

def _latest_replay_path(dirs: list[str]) -> Optional[str]:
    mtimes = _scan_replay_mtimes(dirs)
    if not mtimes:
        return None
    return max(mtimes, key=mtimes.get)

def _checks_to_loc_ids(
    hero: str,
    fired: set[str],
    hero_checks: dict[str, list[str]] | None = None,
) -> list[int]:
    check_keys = (
        hero_checks.get(hero, HERO_CHECKS.get(hero, []))
        if hero_checks
        else HERO_CHECKS.get(hero, [])
    )
    return [
        loc_id
        for check_key in check_keys
        if check_key in fired
        for loc_id in [location_name_to_id.get(location_name(hero, check_key))]
        if loc_id is not None
    ]

class HoTSClient(CommonContext):
    game = "Heroes of the Storm"
    items_handling = 0b111
    command_processor = HoTSClientCommandProcessor

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cfg: dict = {}
        self.battle_tag: Optional[str] = None
        self.replay_dirs: list[str] = []
        self.known_replays: dict[str, float] = {}
        self.pending_replays: dict[str, float] = {}
        self.unlocked_heroes: set[str] = set()
        self.unlocked_roles: set[str] = set()
        self.use_role_passes: bool = True
        self.starting_role_pass: str | None = None
        self.starting_hero: str | None = None
        self.enabled_heroes: list[str] = []
        self.hero_checks: dict[str, list[str]] = {}
        self.goal_location_ids: set[int] = set()
        self.tracker: HoTSTracker | None = None
        self.tracker_enabled = True
        self.slot_data: dict = {}
        self._connected = False
    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)
        if cmd == "Connected":
            self._on_connected(args)
        elif cmd == "ReceivedItems":
            self._on_items(args.get("items", []))
        elif cmd == "RoomUpdate":
            if "checked_locations" in args:
                self.checked_locations.update(args["checked_locations"])
            if self.tracker:
                self.tracker.refresh()

    def _on_connected(self, args: dict):
        sd = args.get("slot_data", {})
        self.slot_data = sd
        self.use_role_passes = bool(sd.get("role_passes", True))
        self.starting_role_pass = sd.get("starting_role_pass")
        self.starting_hero = sd.get("starting_hero")
        self.enabled_heroes = sd.get("enabled_heroes", sd.get("available_heroes", []))
        self.hero_checks = sd.get("hero_checks", {})
        self.goal_location_ids = set(sd.get("goal_location_ids", []))
        self.checked_locations.update(args.get("checked_locations", []))
        self.unlocked_heroes.clear()
        self.unlocked_roles.clear()
        if self.starting_hero:
            self.unlocked_heroes.add(self.starting_hero)
        if self.use_role_passes and self.starting_role_pass:
            self.unlocked_roles.add(self.starting_role_pass)
        self.tracker = HoTSTracker(self)
        self._connected = True
        goal_summary = sd.get("goal_summary", "")
        if self.starting_hero:
            logger.info(f"[HotS] Starting hero: {self.starting_hero}")
        else:
            logger.info("[HotS] Starting hero: (none)")
        logger.info(f"[HotS] Goal: {goal_summary}")
        if self.battle_tag:
            logger.info(f"[HotS] HotS player: {self.battle_tag}")
        else:
            logger.info("[HotS] HotS player: (unknown — play a match or use /name YourBattleTag)")
        if self.replay_dirs:
            logger.info(
                f"[HotS] Replay watcher active — {len(self.replay_dirs)} folder(s), "
                f"poll every {POLL_INTERVAL}s"
            )
        else:
            logger.warning("[HotS] No replay folders configured — checks will not be detected.")
        if self.tracker:
            self.tracker.refresh()
        asyncio.create_task(self._check_goal())

    def _on_items(self, items):
        for item in items:
            name = self.item_names.lookup_in_game(item.item)
            if name in ALL_HEROES:
                if name not in self.unlocked_heroes:
                    self.unlocked_heroes.add(name)
            elif name.endswith(" Pass"):
                role = name[: -len(" Pass")].lower()
                if role not in self.unlocked_roles:
                    self.unlocked_roles.add(role)
        if self.tracker:
            self.tracker.refresh()

    def _hero_unlocked(self, hero: str) -> bool:
        if hero not in self.enabled_heroes:
            return False
        if hero not in self.unlocked_heroes:
            return False
        if self.use_role_passes and get_role(hero) not in self.unlocked_roles:
            return False
        return True

    def _battle_tag_from_replay(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        toon = _toon_handle_from_replay_path(path)
        if not toon:
            return None
        result = parse_replay(path, toon_handle=toon)
        return result.player_name if result else None
    async def _resolve_battle_tag(self) -> None:
        configured = (self.cfg.get("battle_tag") or "").strip() or None
        latest = _latest_replay_path(self.replay_dirs)
        detected = self._battle_tag_from_replay(latest)
        if configured:
            self.battle_tag = configured
            if detected and not battle_tags_match(configured, detected):
                logger.warning(
                    f"[HotS] Saved player name {configured!r} does not match "
                    f"latest replay ({detected!r}). Use /name to update."
                )
            elif detected:
                logger.info(f"[HotS] HotS player: {configured}")
        elif detected:
            self.battle_tag = detected
            self.cfg["battle_tag"] = detected
            _save_config(self.cfg)
            logger.info(
                f"[HotS] HotS player: {detected} (from latest replay). "
                f"Use /name <tag> if this is wrong."
            )
        else:
            self.battle_tag = None
            logger.warning(
                "[HotS] Could not read a player name from your replays yet. "
                "Play a match or set one with /name YourBattleTag"
            )
    async def _process_replay(self, path: str):
        filename = os.path.basename(path)
        logger.info(f"[HotS] Processing replay: {filename}")
        toon = _toon_handle_from_replay_path(path)
        if not toon:
            logger.warning(f"[HotS] Replay skipped — not in a recognized account folder: {filename}")
            return
        result = parse_replay(path, toon_handle=toon)
        if result is None:
            logger.warning(
                f"[HotS] Replay skipped — could not parse {filename}. "
                "Try restarting the client after updating hots.apworld."
            )
            return
        if result.player_name:
            if not self.battle_tag:
                self.battle_tag = result.player_name
                self.cfg["battle_tag"] = result.player_name
                _save_config(self.cfg)
                logger.info(f"[HotS] HotS player: {result.player_name}")
            elif not battle_tags_match(self.battle_tag, result.player_name):
                logger.warning(
                    f"[HotS] Replay lists player {result.player_name!r}; "
                    f"configured name is {self.battle_tag!r}."
                )
        hero = hero_from_replay_name(result.hero)
        if hero is None:
            logger.info(f"[HotS] Replay skipped — unknown hero {result.hero!r} in {filename}")
            return
        if hero not in self.enabled_heroes:
            logger.info(f"[HotS] Replay skipped — {hero} is not in your enabled hero pool")
            return
        if not self._hero_unlocked(hero):
            logger.info(
                f"[HotS] Replay skipped — {hero} is locked "
                f"(match result: {result.result}, map: {result.map_name})"
            )
            return
        fired = detect_checks(result.score, result.result, result.level_history)
        new_ids = [
            i for i in _checks_to_loc_ids(hero, fired, self.hero_checks or None)
            if i not in self.checked_locations
        ]
        if new_ids:
            self.checked_locations.update(new_ids)
            await self.send_msgs([{"cmd": "LocationChecks", "locations": new_ids}])
        else:
            logger.info(
                f"[HotS] No new checks for {hero} "
                f"(result: {result.result}, map: {result.map_name})"
            )
        if self.tracker:
            self.tracker.refresh()
        await self._check_goal()
    async def _rescan_latest(self, path: str) -> None:
        self.known_replays.pop(path, None)
        self.pending_replays.pop(path, None)
        try:
            await self._process_replay(path)
        except Exception as exc:
            logger.warning(f"[HotS] Error reprocessing {os.path.basename(path)}: {exc}")
        else:
            try:
                self.known_replays[path] = os.path.getmtime(path)
            except OSError:
                pass
    async def _check_goal(self):
        if not self._connected or not self.goal_location_ids:
            return
        if self.goal_location_ids.issubset(self.checked_locations):
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            logger.info("[HotS] GOAL complete — goal sent to server.")
    async def _scan_replays(self):
        current = _scan_replay_mtimes(self.replay_dirs)
        now = time.time()
        for path, mtime in current.items():
            if path not in self.known_replays:
                self.known_replays[path] = mtime
                self.pending_replays[path] = now
                logger.info(f"[HotS] New replay detected: {os.path.basename(path)}")
            elif mtime > self.known_replays[path]:
                self.known_replays[path] = mtime
                self.pending_replays[path] = now
        ready = [
            path for path, detected_at in list(self.pending_replays.items())
            if now - detected_at >= SETTLE_DELAY
        ]
        for path in ready:
            del self.pending_replays[path]
            try:
                await self._process_replay(path)
            except Exception as exc:
                logger.warning(f"[HotS] Error processing {os.path.basename(path)}: {exc}")
    async def _replay_loop(self):
        logger.info(f"[HotS] Replay watcher started (poll every {POLL_INTERVAL}s).")
        while not self.exit_event.is_set():
            if self._connected and self.replay_dirs:
                try:
                    await self._scan_replays()
                except Exception as exc:
                    logger.warning(f"[HotS] Replay scan error: {exc}")
            await asyncio.sleep(POLL_INTERVAL)
    async def _setup(self):
        self.cfg = _load_config()
        self.cfg.pop("toon_handle", None)
        dirs_from_cfg = [d for d in self.cfg.get("replay_dirs", []) if os.path.isdir(d)]
        if dirs_from_cfg:
            self.replay_dirs = dirs_from_cfg
        else:
            self.replay_dirs = _find_multiplayer_dirs(ACCOUNTS_ROOT)
            if self.replay_dirs:
                self.cfg["replay_dirs"] = self.replay_dirs
        _save_config(self.cfg)
        if not self.replay_dirs:
            await self._prompt_missing()
        await self._resolve_battle_tag()
        self.known_replays = _scan_replay_mtimes(self.replay_dirs)
        logger.info(
            f"[HotS] Ignoring {len(self.known_replays)} existing replays "
            f"(use /rescan to reprocess your latest match)."
        )
    async def _prompt_missing(self):
        msg = f"No replay folders found under: {ACCOUNTS_ROOT}"
        if gui_enabled:
            logger.warning(f"[HotS] {msg}")
            custom = (await self.console_input()).strip()
        else:
            print(f"\n=== Heroes of the Storm — First Run Setup ===\n{msg}")
            custom = input("Enter your replay folder path (or Enter to skip): ").strip()
        if custom and os.path.isdir(custom):
            self.replay_dirs = [custom]
            self.cfg["replay_dirs"] = self.replay_dirs
            _save_config(self.cfg)
        elif not self.replay_dirs:
            logger.warning("[HotS] No replay folder — checks will not be detected until one is configured.")

    def run_gui(self):
        from kvui import GameManager, UILog
        class HoTSManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago Heroes of the Storm Client"
            def build(self):
                ret = super().build()
                self.ctx.tab_goal = self.add_client_tab("Goal", UILog())
                self.ctx.tab_tracker = self.add_client_tab("Tracker", UILog())
                self.ctx.tab_unlocks = self.add_client_tab("Unlocks", UILog())
                if getattr(self.ctx, "tracker", None):
                    self.ctx.tracker.refresh()
                return ret
        self.ui = HoTSManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

def launch(*launch_args):
    import colorama
    async def main():
        parser = get_base_parser(description="Heroes of the Storm AP Client")
        args = parser.parse_args(launch_args)
        ctx = HoTSClient(args.connect, args.password)
        await ctx._setup()
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        asyncio.create_task(ctx._replay_loop(), name="ReplayWatcher")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()
    colorama.just_fix_windows_console()
    asyncio.run(main())
    colorama.deinit()
if __name__ == "__main__":
    launch()

