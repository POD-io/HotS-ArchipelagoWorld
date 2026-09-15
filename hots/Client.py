"""Heroes of the Storm Archipelago client."""
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
from MultiServer import mark_raw
from Utils import user_path
from .Talents import (
    export_ap_talent_builds,
    find_talent_builds_paths,
    talent_location_name,
    talent_req_is_any,
)
from .Challenges import (
    HERO_CHECKS, ALL_HEROES, detect_checks, detect_instant_checks, detect_cumulative_checks,
    hero_from_replay_name, location_name, score_fields_for_check_keys, HERO_TO_YAML_KEY,
    get_pass_key, pass_key_from_item_name, pass_location_name, pass_name_for_key,
    XP_PASS_18K, XP_PASS_40K, TIMED_WIN_18, PASS_XP_THRESHOLDS, CHECK_SCORE_THRESHOLDS,
    CAPABILITY_HEROES, DAILY_QUESTS_COMPLETE, DAILY_QUEST_UNLOCK_MIN,
    capable_heroes_in_pool,
    daily_quest_item_name, daily_quest_slot_from_item_name,
    daily_quest_location_name,
)
from .Items import (
    CHEST_COST_XP, CHEST_SLOTS, SHARDS_TO_UNLOCK, hero_from_shard_name,
    is_hero_wave_item, PROGRESSIVE_HERO_WAVE_NAME, progressive_waves_needed,
)
from .Locations import location_name_to_id
from .LootState import LootState
from .ConsumableState import ConsumableState, apply_stimpack_score
from .ReplayParser import (
    battle_tags_match, battle_tags_match_any, parse_replay,
    parse_replay_roster, pick_host_result, select_credited_results,
    normalize_credit_mode, CREDIT_MODES,
)
from .Tracker import HoTSTracker

POLL_INTERVAL = 10
SETTLE_DELAY = 4
CONFIG_FILE = user_path("hots_config.json")
ACCOUNTS_ROOT = os.path.join(
    os.path.expanduser("~"), "Documents", "Heroes of the Storm", "Accounts"
)
_TOON_PART = re.compile(r"^\d+-Hero-\d+-\d+$", re.I)
_LOOT_SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loot_sounds")
_LOOT_SOUNDS_CACHE = user_path("hots_loot_sounds")
_LOOT_SOUND_VOLUME = 0.15
_LOOT_SOUND_WARNED: set[str] = set()
_LOOT_SOUND_PATHS: dict[str, str | None] = {}


def _resolve_loot_sound(filename: str) -> str | None:
    """Resolve a loot SFX."""
    if filename in _LOOT_SOUND_PATHS:
        return _LOOT_SOUND_PATHS[filename]

    path: str | None = None
    loose = os.path.join(_LOOT_SOUNDS_DIR, filename)
    if os.path.isfile(loose):
        path = loose
    else:
        module_file = os.path.abspath(__file__).replace("/", os.sep)
        lower = module_file.lower()
        if ".apworld" in lower:
            try:
                import zipfile
                idx = lower.index(".apworld")
                zip_path = module_file[: idx + len(".apworld")]
                if os.path.isfile(zip_path):
                    suffix = f"loot_sounds/{filename}".replace("\\", "/")
                    with zipfile.ZipFile(zip_path) as zf:
                        member = next(
                            (n for n in zf.namelist() if n.replace("\\", "/").endswith(suffix)),
                            None,
                        )
                        if member:
                            os.makedirs(_LOOT_SOUNDS_CACHE, exist_ok=True)
                            dest = os.path.join(_LOOT_SOUNDS_CACHE, filename)
                            needs = (
                                not os.path.isfile(dest)
                                or os.path.getmtime(dest) < os.path.getmtime(zip_path)
                            )
                            if needs:
                                with zf.open(member) as src, open(dest, "wb") as out:
                                    out.write(src.read())
                            if os.path.isfile(dest):
                                path = dest
            except Exception:
                path = None

    _LOOT_SOUND_PATHS[filename] = path
    return path



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

    @mark_raw
    def _cmd_name(self, text: str = "") -> bool:
        """Set who YOU are. Examples: /name MyPlayer | /name remove MyPlayer | /name clear"""
        if not isinstance(self.ctx, HoTSClient):
            self.output("Not connected.")
            return True
        raw = (text or "").strip()
        if not raw or raw.lower() in ("help", "?"):
            tags = self.ctx.battle_tags or []
            self.output("You: " + (", ".join(tags) if tags else "(not set)"))
            detected = self.ctx._battle_tag_from_replay(_latest_replay_path(self.ctx.replay_dirs))
            if detected and not battle_tags_match_any(tags, detected):
                self.output(f"Latest replay: {detected}  —  /name {detected}")
            self._print_name_help()
            return True
        low = raw.lower()
        if low in ("clear", "reset"):
            self.ctx.set_battle_tags([])
            self.output("Cleared /name.")
            return True
        action = "add"
        name = raw
        if low.startswith("add "):
            name = raw[4:].strip()
        elif low.startswith("remove "):
            action = "remove"
            name = raw[7:].strip()
        if not name:
            self._print_name_help()
            return True
        if action == "remove":
            if name.lower() in ("all", "*"):
                self.ctx.set_battle_tags([])
                self.output("Cleared /name.")
                return True
            if self.ctx.remove_battle_tag(name):
                self.output(f"Removed {name}. You: {', '.join(self.ctx.battle_tags) or '(none)'}")
            else:
                self.output(f"{name} was not in /name.")
            return True
        if self.ctx.add_battle_tag(name):
            self.output(f"You: {', '.join(self.ctx.battle_tags)}")
        else:
            self.output(f"{name} is already in /name.")
        return True

    def _print_name_help(self) -> None:
        self.output("Who you are on the scoreboard:")
        self.output("  /name MyPlayer")
        self.output("  /name remove MyPlayer")
        self.output("  /name clear")

    @mark_raw
    def _cmd_credit(self, text: str = "") -> bool:
        """Who else this client scores. Examples: /credit team | /credit ai on | /credit add ZergZergling"""
        if not isinstance(self.ctx, HoTSClient):
            self.output("Not connected.")
            return True
        raw = (text or "").strip()
        if not raw or raw.lower() in ("help", "?"):
            self.ctx._print_credit_status(self.output)
            self._print_credit_help()
            return True
        low = raw.lower()
        if low == "ai":
            self.ctx.set_include_ai(not self.ctx.include_ai)
            self.ctx._print_credit_status(self.output)
            return True
        if low.startswith("ai "):
            flag = raw[3:].strip().lower()
            if flag in ("on", "true", "1"):
                self.ctx.set_include_ai(True)
            elif flag in ("off", "false", "0"):
                self.ctx.set_include_ai(False)
            else:
                self.output("Use: /credit ai on   or   /credit ai off")
                return True
            self.ctx._print_credit_status(self.output)
            return True
        if low in CREDIT_MODES:
            self.ctx.set_credit_mode(low)
            self.ctx._print_credit_status(self.output)
            return True
        if low == "reset":
            self.ctx.reset_credit_to_seed()
            self.output("Credit settings restored to seed YAML defaults.")
            self.ctx._print_credit_status(self.output)
            return True
        if low in ("clear", "remove all", "clear all"):
            self.ctx.set_credit_names([])
            self.output("Credit name filter cleared (everyone allowed by mode).")
            self.ctx._print_credit_status(self.output)
            return True
        action = "add"
        name = raw
        if low.startswith("add "):
            name = raw[4:].strip()
        elif low.startswith("remove "):
            action = "remove"
            name = raw[7:].strip()
        if not name:
            self._print_credit_help()
            return True
        if action == "remove":
            if name.lower() in ("all", "*"):
                self.ctx.set_credit_names([])
                self.output("Credit name filter cleared (everyone allowed by mode).")
                self.ctx._print_credit_status(self.output)
                return True
            if self.ctx.remove_credit_name(name):
                self.output(f"Removed {name}.")
            else:
                self.output(f"{name} was not in the list.")
            self.ctx._print_credit_status(self.output)
            return True
        added = self.ctx.add_credit_name(name)
        if added:
            self.output(f"Added {name}.")
        else:
            self.output(f"{name} is already listed.")
        self.ctx._print_credit_status(self.output)
        return True

    def _print_credit_help(self) -> None:
        self.output("Scoring mode (pick one):")
        self.output("  /credit me      only your (/name)")
        self.output("  /credit team    your team")
        self.output("  /credit match   whole lobby")
        self.output("Optional name filter (team/match only):")
        self.output("  /credit add ZergZergling")
        self.output("  /credit remove ZergZergling")
        self.output("  /credit clear              clear filter (everyone allowed)")
        self.output("AI players:")
        self.output("  /credit ai on     /credit ai off     /credit ai  (toggle)")
        self.output("Other:")
        self.output("  /credit reset     restore seed YAML defaults")

    def _cmd_goal(self, text: str = "") -> bool:
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

    def _cmd_builds(self) -> bool:
        """Install this seed's talent checks into HotS TalentBuilds.txt (timestamped backup first)."""
        if not isinstance(self.ctx, HoTSClient):
            self.output("Not connected.")
            return True
        for line in self.ctx.install_talent_builds():
            self.output(line)
        return True

    def _cmd_stim(self) -> bool:
        """Use a Stimpack: next credited match's tallies count double (queues if already active)."""
        if not isinstance(self.ctx, HoTSClient):
            self.output("Not connected.")
            return True
        cons = getattr(self.ctx, "consumables", None)
        if cons is None:
            self.output("Not connected to a HotS slot.")
            return True
        if cons.drink_stimpack():
            self.output(
                f"Stimpack used. {cons.stim_remaining} boosted match"
                f"{'' if cons.stim_remaining == 1 else 'es'} queued, "
                f"{cons.stim_in_bag} left in bag."
            )
        elif cons.received_stim <= 0:
            self.output("No Stimpacks in this seed (yet).")
        else:
            self.output(f"No Stimpacks left in bag ({cons.stim_remaining} match boosts still queued).")
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


def _battle_tags_from_cfg(cfg: dict) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    raw = cfg.get("battle_tags")
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str) and raw.strip():
        values = [raw]
    else:
        values = []
    single = cfg.get("battle_tag")
    if single:
        values = [single, *values]
    for item in values:
        tag = str(item).strip()
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            tags.append(tag)
    return tags

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


def _warn_empty_replay_dirs(dirs: list[str]) -> None:
    for d in dirs:
        try:
            names = [n for n in os.listdir(d) if n.lower().endswith(".stormreplay")]
        except Exception:
            names = []
        if not names:
            logger.warning(
                f"Replay folder has 0 .StormReplay files: {d}\n"
                "  You may have selected the wrong folder (need the Multiplayer replays dir)."
            )

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
        self.battle_tags: list[str] = []
        self.replay_dirs: list[str] = []
        self.known_replays: dict[str, float] = {}
        self.pending_replays: dict[str, float] = {}
        self.unlocked_heroes: set[str] = set()
        self.hero_shards: dict[str, int] = {}
        self.unlocked_roles: set[str] = set()
        self.use_role_passes: bool = True
        self.starting_role_pass: str | None = None
        self.starting_hero: str | None = None
        self.starting_heroes: list[str] = []
        self.enabled_heroes: list[str] = []
        self.hero_checks: dict[str, list[str]] = {}
        self.goal_location_ids: set[int] = set()
        self.enabled_pass_keys: list[str] = []
        self.pass_check_keys: list[str] = []
        self.pass_location_names: list[str] = []
        self.pass_xp_thresholds: dict[str, int] = dict(PASS_XP_THRESHOLDS)
        self.timed_win_max_seconds: int = 18 * 60
        self.include_timed_win_check: bool = False
        self.cumulative_checks: bool = False
        self.hero_talent_requirements: dict[str, list[dict[str, int]]] = {}
        self.pass_xp_totals: dict[str, int] = {}
        self.hero_stat_totals: dict[str, dict[str, int]] = {}
        self.loot_chest_count: int = 0
        self.chest_cost_xp: int = CHEST_COST_XP
        self.shards_to_unlock: int = SHARDS_TO_UNLOCK
        self.full_unlock_heroes: list[str] = []
        self.shard_heroes: list[str] = []
        self.daily_quest_keys: list[str] = []
        self.daily_quest_defs: dict[str, dict] = {}
        self.daily_quest_totals: dict[str, int] = {}
        self.daily_quest_slips: set[str] = set()
        self.party_mode: bool = False
        self.credit_mode: str = "me"
        self.credit_names: list[str] = []
        self.seed_credit_mode: str = "me"
        self.seed_credit_names: list[str] = []
        self.include_ai: bool = False
        self.seed_include_ai: bool = False
        self.party_size: int = 1
        self.starting_waves: int = 1
        self.hero_waves: list[list[str]] = []
        self.hero_wave_need: dict[str, int] = {}
        self.progressive_hero_waves = 0
        self._known_heroes: set[str] = set()
        self._known_roles: set[str] = set()
        self._known_slips: set[str] = set()
        self._had_unlock_baseline = False
        self.loot: LootState | None = None
        self.consumables: ConsumableState | None = None
        self.tracker: HoTSTracker | None = None
        self.tracker_enabled = True
        self.slot_data: dict = {}
        self._connected = False
        self._sound_cache: dict = {}
    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            already = set(args.get("checked_locations", []))
            self.locations_checked -= already
        super().on_package(cmd, args)
        if cmd == "Connected":
            self._on_connected(args)
        elif cmd == "ReceivedItems":
            self._on_items(args.get("items", []), index=int(args.get("index", 0) or 0))
        elif cmd == "LocationInfo":
            if self.loot:
                self.loot.apply_location_info(args.get("locations", []))
                panel = getattr(self, "loot_panel", None)
                if panel is not None:
                    panel.refresh()
        elif cmd == "RoomUpdate":
            if "checked_locations" in args:
                confirmed = set(args["checked_locations"])
                self.checked_locations.update(confirmed)
                self.locations_checked -= confirmed
                if self.loot:
                    self.loot.note_server_checks()
                    panel = getattr(self, "loot_panel", None)
                    if panel is not None:
                        panel.refresh()
                asyncio.create_task(self._check_goal())
            if self.tracker:
                self.tracker.refresh()
        elif cmd in ("Retrieved", "SetReply"):
            self._sync_pass_xp_from_storage()
            self._sync_hero_stats_from_storage()
            self._sync_daily_quests_from_storage()
            if self.loot:
                self.loot.apply_bought_from_storage(announce=True)
            cons = getattr(self, "consumables", None)
            if cons is not None:
                cons.apply_from_storage()
            if self.tracker:
                self.tracker.refresh()

    def _on_connected(self, args: dict):
        sd = args.get("slot_data", {})
        self.slot_data = sd
        self.use_role_passes = bool(sd.get("role_passes", True))
        self.starting_role_pass = sd.get("starting_role_pass")
        self.starting_hero = sd.get("starting_hero")
        raw_starting_heroes = sd.get("starting_heroes")
        if raw_starting_heroes:
            self.starting_heroes = list(raw_starting_heroes)
        elif self.starting_hero:
            self.starting_heroes = [self.starting_hero]
        else:
            self.starting_heroes = []
        self.enabled_heroes = sd.get("enabled_heroes", sd.get("available_heroes", []))
        self.hero_checks = sd.get("hero_checks", {})
        self.goal_location_ids = set(sd.get("goal_location_ids", []))
        self.enabled_pass_keys = list(sd.get("enabled_pass_keys", []))
        self.pass_check_keys = list(sd.get("pass_check_keys", []))
        self.pass_location_names = list(sd.get("pass_location_names", []))
        self.pass_xp_thresholds = dict(sd.get("pass_xp_thresholds", PASS_XP_THRESHOLDS))
        self.timed_win_max_seconds = int(sd.get("timed_win_max_seconds", 18 * 60))
        self.include_timed_win_check = bool(sd.get("include_timed_win_check", False))
        self.cumulative_checks = bool(sd.get("cumulative_checks", False))
        self.hero_talent_requirements = dict(sd.get("hero_talent_requirements") or {})
        self.loot_chest_count = int(sd.get("loot_chest_count", 0) or 0)
        self.chest_cost_xp = int(sd.get("chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        raw_shards = sd.get("shards_to_unlock", SHARDS_TO_UNLOCK)
        try:
            self.shards_to_unlock = int(raw_shards)
        except (TypeError, ValueError):
            self.shards_to_unlock = SHARDS_TO_UNLOCK
        self.full_unlock_heroes = list(sd.get("full_unlock_heroes") or [])
        self.shard_heroes = list(sd.get("shard_heroes") or [])
        self.daily_quest_keys = list(sd.get("daily_quest_keys") or [])
        self.daily_quest_defs = dict(sd.get("daily_quest_defs") or {})
        self.daily_quest_totals = {key: 0 for key in self.daily_quest_keys}
        self.daily_quest_slips = set()
        if args.get("seed_name"):
            self.seed_name = args["seed_name"]
        elif args.get("seed"):
            self.seed_name = args["seed"]
        self.party_mode = bool(sd.get("party_mode", False))
        self.seed_credit_mode = normalize_credit_mode(sd.get("credit_mode"))
        self.seed_credit_names = [
            str(n).strip() for n in (sd.get("credit_names") or []) if str(n).strip()
        ]
        if self.seed_credit_names and self.seed_credit_mode == "me":
            self.seed_credit_mode = "team"
        self.seed_include_ai = bool(sd.get("include_ai", False))
        self._apply_credit_override()
        self.party_size = int(sd.get("party_size") or 1)
        self.starting_waves = int(sd.get("starting_waves") or 1)
        self.hero_waves = [list(wave) for wave in (sd.get("hero_waves") or [])]
        raw_need = sd.get("hero_wave_need") or {}
        self.hero_wave_need = {
            str(key): int(value) for key, value in raw_need.items()
        }
        self.progressive_hero_waves = 0
        self.pass_xp_totals = {pass_key: 0 for pass_key in self.enabled_pass_keys}
        self.hero_stat_totals = {hero: {} for hero in self.enabled_heroes}
        self.checked_locations = set(args.get("checked_locations", []))
        self.unlocked_heroes.clear()
        self.hero_shards.clear()
        self.unlocked_roles.clear()
        for hero in self.starting_heroes:
            self.unlocked_heroes.add(hero)
        if self.use_role_passes and self.starting_role_pass:
            self.unlocked_roles.add(self.starting_role_pass)
        self._load_known_unlocks()
        self.loot = LootState(self)
        self.loot.bind_to_room(self.cfg)
        self.consumables = ConsumableState(self)
        self.consumables.bind_to_room(self.cfg)
        self.tracker = HoTSTracker(self)
        self._connected = True
        goal_summary = sd.get("goal_summary", "")
        if self.party_mode:
            logger.info(
                f"Party Mode: {self.party_size} players, "
                f"{self.starting_waves} starting wave"
                f"{'' if self.starting_waves == 1 else 's'}"
            )
        elif self.starting_heroes:
            if len(self.starting_heroes) == 1:
                logger.info(f"Starting hero: {self.starting_heroes[0]}")
            else:
                logger.info(f"Starting heroes: {', '.join(self.starting_heroes)}")
        self._print_credit_status(logger.info)
        logger.info(f"Goal: {goal_summary}")
        if self.replay_dirs:
            logger.info(
                f"Replay watcher active - {len(self.replay_dirs)} folder(s)"
            )
        else:
            logger.warning("No replay folders configured - checks will not be detected.")
        if self.tracker:
            self.tracker.refresh()
        self._setup_pass_data_storage()
        if self.cumulative_checks:
            self._setup_hero_stat_storage()
        self._setup_daily_quest_storage()
        if self.enabled_pass_keys and XP_PASS_18K in self.pass_check_keys:
            asyncio.create_task(self._reconcile_all_pass_xp_checks())
        if self.cumulative_checks:
            asyncio.create_task(self._reconcile_all_hero_checks())
        if self.daily_quest_keys:
            asyncio.create_task(self._reconcile_daily_quests())
        asyncio.create_task(self._check_goal())

    def _loot_bought_storage_key(self) -> str:
        seed = (getattr(self, "seed_name", None) or "seed").replace(" ", "_")
        return f"hots_loot_bought_{seed}_{self.team}_{self.slot}"

    def _loot_bought_storage_keys(self) -> list[str]:
        keyed = self._loot_bought_storage_key()
        legacy = f"hots_loot_bought_{self.team}_{self.slot}"
        return [keyed] if keyed == legacy else [keyed, legacy]

    def persist_loot_bought(self, bought: int) -> None:
        seed = (getattr(self, "seed_name", None) or "").strip()
        if not seed:
            return
        key = f"{seed}|{self.team}|{self.slot}"
        economy = self.cfg.setdefault("loot_economy", {})
        blob = economy.get(key) if isinstance(economy.get(key), dict) else {}
        blob["bought_chests"] = max(0, int(bought))
        economy[key] = blob
        _save_config(self.cfg)

    def persist_loot_click_feed(self, entries: list) -> None:
        seed = (getattr(self, "seed_name", None) or "").strip()
        if not seed:
            return
        key = f"{seed}|{self.team}|{self.slot}"
        store = self.cfg.setdefault("loot_click_feed", {})
        cleaned = []
        for entry in entries[: CHEST_SLOTS * 2]:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            cleaned.append({"name": name, "flags": int(entry.get("flags", 0) or 0)})
        store[key] = cleaned
        _save_config(self.cfg)

    def _unlock_persist_key(self) -> str:
        seed = (getattr(self, "seed_name", None) or "").strip()
        return f"{seed}|{self.team}|{self.slot}"

    def _load_known_unlocks(self) -> None:
        key = self._unlock_persist_key()
        blob = {}
        if key and not key.startswith("|"):
            raw = (self.cfg.get("known_unlocks") or {}).get(key) or {}
            blob = raw if isinstance(raw, dict) else {}
        self._had_unlock_baseline = bool(blob)
        self._known_heroes = set(blob.get("heroes") or [])
        self._known_roles = set(blob.get("roles") or [])
        self._known_slips = set(blob.get("slips") or [])

    def _save_known_unlocks(self) -> None:
        key = self._unlock_persist_key()
        if not key or key.startswith("|"):
            return
        store = self.cfg.setdefault("known_unlocks", {})
        store[key] = {
            "heroes": sorted(self.unlocked_heroes),
            "roles": sorted(self.unlocked_roles),
            "slips": sorted(self.daily_quest_slips),
        }
        self._known_heroes = set(self.unlocked_heroes)
        self._known_roles = set(self.unlocked_roles)
        self._known_slips = set(self.daily_quest_slips)
        self._had_unlock_baseline = True
        _save_config(self.cfg)

    async def _send_new_location_checks(self, loc_ids: list[int]) -> list[int]:
        """Send only locations the server still lists as missing."""
        new = []
        seen: set[int] = set()
        already = self.checked_locations | getattr(self, "locations_checked", set())
        missing = getattr(self, "missing_locations", None)
        for loc_id in loc_ids:
            if loc_id is None or loc_id in already or loc_id in seen:
                continue
            if missing is not None and loc_id not in missing:
                continue
            seen.add(loc_id)
            new.append(loc_id)
        if not new:
            return []
        self.checked_locations.update(new)
        self.locations_checked.update(new)
        await self.send_msgs([{"cmd": "LocationChecks", "locations": new}])
        return new

    def persist_consumables(self, blob: dict) -> None:
        seed = (getattr(self, "seed_name", None) or "").strip()
        if not seed:
            return
        key = f"{seed}|{self.team}|{self.slot}"
        store = self.cfg.setdefault("consumables", {})
        store[key] = blob
        _save_config(self.cfg)

    def _consumable_storage_key(self, suffix: str) -> str:
        seed = (getattr(self, "seed_name", None) or "seed").replace(" ", "_")
        return f"hots_{suffix}_{seed}_{self.team}_{self.slot}"

    def _stim_consumed_storage_key(self) -> str:
        return self._consumable_storage_key("stim_consumed")

    def _stim_used_storage_key(self) -> str:
        return self._consumable_storage_key("stim_used")

    def _tome_consumed_storage_key(self) -> str:
        return self._consumable_storage_key("tome_consumed")

    def _talent_reqs_storage_key(self) -> str:
        return self._consumable_storage_key("talent_reqs")

    def _boosted_replays_storage_key(self) -> str:
        return self._consumable_storage_key("stim_replays")

    def _setup_consumable_storage(self) -> None:
        keys = [
            self._stim_consumed_storage_key(),
            self._stim_used_storage_key(),
            self._tome_consumed_storage_key(),
            self._talent_reqs_storage_key(),
            self._boosted_replays_storage_key(),
        ]
        self.set_notify(*keys)
        asyncio.create_task(self.send_msgs([{"cmd": "Get", "keys": keys}]))
        if self.consumables:
            self.consumables.resolve_from_storage(self.cfg, announce=False, push_if_raised=True)

    def _setup_loot_storage(self) -> None:
        keys = self._loot_bought_storage_keys()
        self.set_notify(*keys)
        asyncio.create_task(self.send_msgs([{"cmd": "Get", "keys": keys}]))
        if self.loot:
            self.loot.resolve_bought_chests(self.cfg, announce=False, push_if_raised=True)

    def _xp_storage_key(self, pass_key: str) -> str:
        return f"hots_xp_{self.team}_{self.slot}_{pass_key}"

    def _setup_pass_data_storage(self) -> None:
        if not self.use_role_passes or XP_PASS_18K not in self.pass_check_keys:
            return
        keys = [self._xp_storage_key(pass_key) for pass_key in self.enabled_pass_keys]
        if keys:
            self.set_notify(*keys)
        self._sync_pass_xp_from_storage()

    def _sync_pass_xp_from_storage(self) -> None:
        if not self.enabled_pass_keys:
            return
        for pass_key in self.enabled_pass_keys:
            key = self._xp_storage_key(pass_key)
            value = self.stored_data.get(key, 0)
            if isinstance(value, (int, float)):
                self.pass_xp_totals[pass_key] = int(value)

    async def _reconcile_pass_xp_checks(self, pass_key: str, total: int | None = None) -> list[int]:
        if XP_PASS_18K not in self.pass_check_keys:
            return []
        if not self._has_unlocked_hero_for_pass(pass_key):
            return []
        total = self.pass_xp_totals.get(pass_key, 0) if total is None else total
        new_ids: list[int] = []
        for check_key, threshold in self.pass_xp_thresholds.items():
            if check_key not in self.pass_check_keys:
                continue
            if total < threshold:
                continue
            loc_name = pass_location_name(pass_key, check_key)
            loc_id = location_name_to_id.get(loc_name)
            if loc_id is None or loc_id in self.checked_locations:
                continue
            new_ids.append(loc_id)
        return await self._send_new_location_checks(new_ids)

    async def _credit_pass_xp(self, pass_key: str, amount: int) -> None:
        if amount <= 0 or XP_PASS_18K not in self.pass_check_keys:
            return
        current = self.pass_xp_totals.get(pass_key, 0)
        new_total = current + amount
        self.pass_xp_totals[pass_key] = new_total
        await self.send_msgs([{
            "cmd": "Set",
            "key": self._xp_storage_key(pass_key),
            "default": 0,
            "want_reply": False,
            "operations": [{"operation": "add", "value": amount}],
        }])
        await self._reconcile_pass_xp_checks(pass_key, new_total)

    async def _reconcile_all_pass_xp_checks(self) -> None:
        for pass_key in self.enabled_pass_keys:
            await self._reconcile_pass_xp_checks(pass_key)

    def _hero_stat_storage_key(self, hero: str, field: str) -> str:
        safe_hero = HERO_TO_YAML_KEY.get(hero, hero).replace(" ", "_")
        return f"hots_stat_{self.team}_{self.slot}_{safe_hero}_{field}"

    def _setup_hero_stat_storage(self) -> None:
        keys: list[str] = []
        for hero in self.enabled_heroes:
            check_keys = self.hero_checks.get(hero, HERO_CHECKS.get(hero, []))
            for field in score_fields_for_check_keys(check_keys):
                keys.append(self._hero_stat_storage_key(hero, field))
        if keys:
            self.set_notify(*keys)
        self._sync_hero_stats_from_storage()

    def _sync_hero_stats_from_storage(self) -> None:
        if not self.cumulative_checks:
            return
        for hero in self.enabled_heroes:
            check_keys = self.hero_checks.get(hero, HERO_CHECKS.get(hero, []))
            totals = self.hero_stat_totals.setdefault(hero, {})
            for field in score_fields_for_check_keys(check_keys):
                key = self._hero_stat_storage_key(hero, field)
                value = self.stored_data.get(key, 0)
                if isinstance(value, (int, float)):
                    totals[field] = int(value)

    async def _credit_hero_stats(self, hero: str, score: dict) -> None:
        if not self.cumulative_checks:
            return
        check_keys = self.hero_checks.get(hero, HERO_CHECKS.get(hero, []))
        totals = self.hero_stat_totals.setdefault(hero, {})
        credited: list[str] = []
        for field in score_fields_for_check_keys(check_keys):
            amount = int(score.get(field, 0) or 0)
            if amount <= 0:
                continue
            old_total = totals.get(field, 0)
            new_total = old_total + amount
            totals[field] = new_total
            await self.send_msgs([{
                "cmd": "Set",
                "key": self._hero_stat_storage_key(hero, field),
                "default": 0,
                "want_reply": False,
                "operations": [{"operation": "add", "value": amount}],
            }])
            pending_thresholds: list[int] = []
            completed_here = False
            for check_key in check_keys:
                meta = CHECK_SCORE_THRESHOLDS.get(check_key)
                if not meta or meta[0] != field:
                    continue
                threshold = int(meta[1])
                loc_id = location_name_to_id.get(location_name(hero, check_key))
                already = loc_id is not None and loc_id in self.checked_locations
                if already:
                    continue
                if old_total < threshold <= new_total:
                    completed_here = True
                elif new_total < threshold:
                    pending_thresholds.append(threshold)
            if pending_thresholds:
                need = min(pending_thresholds)
                credited.append(f"{field} +{amount:,} (total {new_total:,}/{need:,})")
            elif not completed_here:
                credited.append(f"{field} +{amount:,} (total {new_total:,})")
        if credited:
            logger.info(f"Cumulative {hero}: " + "; ".join(credited))
        elif "RegenGlobes" in score_fields_for_check_keys(check_keys):
            regen = int(score.get("RegenGlobes", 0) or 0)
            if regen <= 0:
                logger.info(
                    f"Cumulative {hero}: RegenGlobes=0 in replay "
                    "(quit/incomplete matches often omit globe score - finish the match to credit)."
                )

    def _daily_quest_storage_key(self, quest_key: str) -> str:
        return f"hots_daily_{self.team}_{self.slot}_{quest_key}"

    def _setup_daily_quest_storage(self) -> None:
        if not self.daily_quest_keys:
            return
        keys = [self._daily_quest_storage_key(k) for k in self.daily_quest_keys]
        self.set_notify(*keys)
        self._sync_daily_quests_from_storage()

    def _sync_daily_quests_from_storage(self) -> None:
        for quest_key in self.daily_quest_keys:
            value = self.stored_data.get(self._daily_quest_storage_key(quest_key), 0)
            if isinstance(value, (int, float)):
                self.daily_quest_totals[quest_key] = int(value)

    def _has_daily_quest_slip(self, quest_key: str) -> bool:
        info = self.daily_quest_defs.get(quest_key) or {}
        item_name = info.get("item") or daily_quest_item_name(quest_key)
        return item_name in self.daily_quest_slips

    def _daily_quest_in_logic(self, quest_key: str) -> bool:
        if not self._has_daily_quest_slip(quest_key):
            return False
        info = self.daily_quest_defs.get(quest_key) or {}
        cap = info.get("capability")
        if not cap:
            return False
        heroes = capable_heroes_in_pool(cap, self.enabled_heroes)
        return sum(1 for h in heroes if self._hero_unlocked(h)) >= DAILY_QUEST_UNLOCK_MIN

    def _log_daily_unlock(self, item_name: str) -> None:
        qname = item_name
        for defn in (self.daily_quest_defs or {}).values():
            if defn.get("item") == item_name:
                qname = defn.get("name") or item_name
                break
        logger.info(f"Daily quest unlocked: {qname}")

    async def _credit_daily_quests(self, hero: str, score: dict) -> list[int]:
        if not self.daily_quest_keys:
            return []
        for quest_key in self.daily_quest_keys:
            info = self.daily_quest_defs.get(quest_key) or {}
            cap = info.get("capability")
            field = info.get("field")
            if not cap or not field:
                continue
            if not self._has_daily_quest_slip(quest_key):
                continue
            if hero not in CAPABILITY_HEROES.get(cap, frozenset()):
                continue
            amount = int(score.get(field, 0) or 0)
            if amount <= 0:
                continue
            self.daily_quest_totals[quest_key] = self.daily_quest_totals.get(quest_key, 0) + amount
            await self.send_msgs([{
                "cmd": "Set",
                "key": self._daily_quest_storage_key(quest_key),
                "default": 0,
                "want_reply": False,
                "operations": [{"operation": "add", "value": amount}],
            }])
            threshold = int(info.get("threshold", 0) or 0)
            new_total = self.daily_quest_totals[quest_key]
            if threshold and new_total < threshold:
                logger.info(
                    f"Daily {info.get('name', quest_key)}: +{amount:,} "
                    f"(total {new_total:,}/{threshold:,})"
                )
        return await self._reconcile_daily_quests()

    async def _reconcile_daily_quests(self) -> list[int]:
        if not self.daily_quest_keys:
            return []
        new_ids: list[int] = []
        for quest_key in self.daily_quest_keys:
            info = self.daily_quest_defs.get(quest_key) or {}
            threshold = int(info.get("threshold", 0) or 0)
            if self.daily_quest_totals.get(quest_key, 0) < threshold:
                continue
            if not self._daily_quest_in_logic(quest_key):
                continue
            loc_id = location_name_to_id.get(daily_quest_location_name(quest_key))
            if loc_id is not None and loc_id not in self.checked_locations:
                new_ids.append(loc_id)
        pending = self.checked_locations | set(new_ids)
        quest_ids = [
            location_name_to_id.get(daily_quest_location_name(k))
            for k in self.daily_quest_keys
        ]
        if (
            quest_ids
            and all(i is not None and i in pending for i in quest_ids)
            and all(self._daily_quest_in_logic(k) for k in self.daily_quest_keys)
        ):
            complete_id = location_name_to_id.get(
                daily_quest_location_name(DAILY_QUESTS_COMPLETE)
            )
            if complete_id is not None and complete_id not in pending:
                new_ids.append(complete_id)
        return await self._send_new_location_checks(new_ids)

    async def _reconcile_hero_checks(self, hero: str) -> list[int]:
        if not self.cumulative_checks:
            return []
        check_keys = self.hero_checks.get(hero, HERO_CHECKS.get(hero, []))
        totals = self.hero_stat_totals.get(hero, {})
        fired = detect_cumulative_checks(totals, check_keys)
        new_ids = [
            loc_id
            for check_key in check_keys
            if check_key in fired
            for loc_id in [location_name_to_id.get(location_name(hero, check_key))]
            if loc_id is not None and loc_id not in self.checked_locations and loc_id not in self.locations_checked
        ]
        return await self._send_new_location_checks(new_ids)

    async def _reconcile_all_hero_checks(self) -> None:
        for hero in self.enabled_heroes:
            await self._reconcile_hero_checks(hero)

    def _on_items(self, items, *, index: int = 0):
        sync = index == 0
        if sync:
            self.progressive_hero_waves = 0
        need = self.shards_to_unlock
        before_heroes = set(self.unlocked_heroes)
        before_roles = set(self.unlocked_roles)
        before_slips = set(self.daily_quest_slips)
        live_shard_hero: str | None = None
        for item in items:
            name = self.item_names.lookup_in_game(item.item)
            flags = int(getattr(item, "flags", 0) or 0)
            if name in ALL_HEROES:
                if name not in self.unlocked_heroes:
                    self.unlocked_heroes.add(name)
            elif is_hero_wave_item(name):
                self.progressive_hero_waves += 1
                have = self.progressive_hero_waves
                start_n = max(1, int(self.starting_waves or 1))
                for idx, wave in enumerate(self.hero_waves):
                    if progressive_waves_needed(idx, start_n) == have:
                        for hero in wave:
                            if hero not in self.unlocked_heroes:
                                self.unlocked_heroes.add(hero)
                        if not sync:
                            total = max(0, len(self.hero_waves) - start_n)
                            logger.info(
                                f"Unlocked {PROGRESSIVE_HERO_WAVE_NAME} ({have}/{total}): "
                                f"{', '.join(wave)}"
                            )
                        break
            elif daily_quest_slot_from_item_name(name):
                if name not in self.daily_quest_slips:
                    self.daily_quest_slips.add(name)
            else:
                shard_hero = hero_from_shard_name(name)
                if shard_hero:
                    self.hero_shards[shard_hero] = self.hero_shards.get(shard_hero, 0) + 1
                    have = self.hero_shards[shard_hero]
                    if need > 0 and have >= need:
                        if shard_hero not in self.unlocked_heroes:
                            self.unlocked_heroes.add(shard_hero)
                    elif not sync:
                        live_shard_hero = shard_hero
                elif name.endswith(" Pass"):
                    pass_key = pass_key_from_item_name(name)
                    if pass_key and pass_key not in self.unlocked_roles:
                        self.unlocked_roles.add(pass_key)
            if self.loot and not sync:
                self.loot.remember_received_name(name, flags)

        new_heroes = self.unlocked_heroes - before_heroes
        new_roles = self.unlocked_roles - before_roles
        new_slips = self.daily_quest_slips - before_slips
        starting = set(self.starting_heroes)
        if sync:
            if self._had_unlock_baseline:
                for hero in sorted((new_heroes - self._known_heroes) - starting):
                    if self.hero_shards.get(hero, 0) >= need:
                        logger.info(f"Unlocked hero (shards): {hero}")
                    else:
                        logger.info(f"Unlocked hero: {hero}")
                for pass_key in sorted(new_roles - self._known_roles):
                    logger.info(f"Unlocked: {pass_name_for_key(pass_key)}")
                for slip in sorted(new_slips - self._known_slips):
                    self._log_daily_unlock(slip)
            self._save_known_unlocks()
        else:
            for hero in sorted(new_heroes - starting):
                if (getattr(self, "hero_wave_need", None) or {}).get(hero):
                    continue
                if self.hero_shards.get(hero, 0) >= need:
                    logger.info(f"Unlocked hero (shards): {hero}")
                else:
                    logger.info(f"Unlocked hero: {hero}")
            if live_shard_hero is not None:
                have = self.hero_shards.get(live_shard_hero, 0)
                if have < need:
                    logger.info(f"{live_shard_hero} shard {have}/{need}")
            for slip in sorted(new_slips):
                self._log_daily_unlock(slip)
            if new_heroes or new_roles or new_slips:
                self._save_known_unlocks()

        if self.loot:
            self.loot.recompute_from_items()
        cons = getattr(self, "consumables", None)
        if cons is not None:
            cons.recompute_from_items()
            panel = getattr(self, "talents_panel", None)
            if panel is not None:
                panel.refresh()
        if self.daily_quest_keys:
            asyncio.create_task(self._reconcile_daily_quests())
        if self.tracker:
            self.tracker.refresh()
        panel = getattr(self, "loot_panel", None)
        if panel is not None:
            panel.refresh()

    def _hero_unlocked(self, hero: str) -> bool:
        if hero not in self.enabled_heroes:
            return False
        has_unlock = hero in self.unlocked_heroes
        has_shards = (
            self.shards_to_unlock > 0
            and self.hero_shards.get(hero, 0) >= self.shards_to_unlock
        )
        if not (has_unlock or has_shards):
            return False
        if self.use_role_passes and get_pass_key(hero) not in self.unlocked_roles:
            return False
        return True

    def play_loot_sound(
        self,
        kind: str,
        flags: int = 0,
        index: int = 0,
        item_name: str = "",
    ) -> None:
        """Play loot UI SFX through Kivy so volume applies to wav and ogg."""
        if self.cfg.get("loot_sounds_muted", False):
            return
        from .Items import is_loot_legendary_item
        legendary = is_loot_legendary_item(item_name)

        if kind == "buy":
            candidates = ["UI_BNet_Loot_Box_Center_Start_Short_02.wav"]
        elif kind == "open":
            candidates = [
                "UI_Bnet_Loot_Chest_Base_Open_PT2_01.ogg",
                "UI_BNet_Loot_Chest_Base_Center_Start_01.wav",
            ]
        elif kind == "land":
            n = (index % 4) + 1
            candidates = [f"UI_Bnet_Loot_Coin_Common_Launch_0{n}.ogg"]
        elif kind == "legendary_sting":
            candidates = [
                "UI_Bnet_Loot_Chest_Base_Open_Crowd_Cheer_Legendary_01.ogg",
                "UI_Bnet_Loot_Coin_Legendary_Land1_01.ogg",
                "UI_BNet_Loot_Coin_Open_Legendary_Airhorn_01.wav",
            ]
        elif kind == "reveal":
            if legendary:
                candidates = ["UI_BNet_Loot_Rarity_Legendary_01.wav"]
            elif flags & 0b001:
                candidates = ["UI_BNet_Loot_Rarity_Epic_01.wav"]
            elif flags & 0b010:
                candidates = ["UI_BNet_Loot_Rarity_Rare_01.wav"]
            else:
                candidates = ["UI_BNet_Loot_Rarity_Common_01.wav"]
        else:
            return

        path = None
        for name in candidates:
            path = _resolve_loot_sound(name)
            if path:
                break
        if not path:
            logger.warning(
                "Loot sound missing "
                f"(tried {', '.join(candidates)}). Re-pack hots.apworld including hots/loot_sounds/."
            )
            return
        self._play_loot_path(path)

    def _play_loot_path(self, path: str) -> None:
        try:
            sound = self._sound_cache.get(path)
            if sound is None:
                from kivy.clock import Clock
                Clock.schedule_once(lambda *_: self._load_and_play_loot(path), 0)
                return
            self._start_loot_sound(sound)
        except Exception:
            key = os.path.basename(path)
            if key not in _LOOT_SOUND_WARNED:
                _LOOT_SOUND_WARNED.add(key)
                logger.warning(f"Could not play loot sound: {key}")

    def _load_and_play_loot(self, path: str) -> None:
        try:
            from kivy.core.audio import SoundLoader
            sound = self._sound_cache.get(path)
            if sound is None:
                sound = SoundLoader.load(path)
                if sound:
                    self._sound_cache[path] = sound
            if sound:
                self._start_loot_sound(sound)
                return
        except Exception:
            pass
        key = os.path.basename(path)
        if key not in _LOOT_SOUND_WARNED:
            _LOOT_SOUND_WARNED.add(key)
            logger.warning(f"Could not play loot sound: {key}")

    def set_loot_sounds_muted(self, muted: bool) -> None:
        self.cfg["loot_sounds_muted"] = bool(muted)
        _save_config(self.cfg)

    def _start_loot_sound(self, sound) -> None:
        if not getattr(sound, "_hots_vol_bound", False):
            sound._hots_vol_bound = True
            sound.bind(on_play=lambda *_: self._apply_loot_volume(sound))
        self._apply_loot_volume(sound)
        sound.stop()
        sound.play()
        self._apply_loot_volume(sound)

    def _apply_loot_volume(self, sound) -> None:
        try:
            sound.volume = _LOOT_SOUND_VOLUME
        except Exception:
            pass
        channel = getattr(sound, "_channel", None)
        if channel is None or channel < 0:
            return
        try:
            from kivy.lib.sdl2 import MIX_MAX_VOLUME, Mix_Volume
            Mix_Volume(int(channel), int(_LOOT_SOUND_VOLUME * MIX_MAX_VOLUME))
        except Exception:
            pass

    def install_talent_builds(self) -> list[str]:
        """Write an AP-only TalentBuilds.txt for this seed; return status lines."""
        reqs = {
            hero: list(slots)
            for hero, slots in (self.hero_talent_requirements or {}).items()
            if slots
        }
        if not reqs:
            return ["No random talent checks in this seed."]

        paths = find_talent_builds_paths(ACCOUNTS_ROOT, self.replay_dirs)
        if not paths:
            return [
                f"No HotS account folder found under: {ACCOUNTS_ROOT}",
                "Play a match once (or set replay folders) so the client can locate TalentBuilds.txt.",
            ]

        lines: list[str] = []
        for path in paths:
            try:
                result = export_ap_talent_builds(path, reqs)
            except OSError as exc:
                lines.append(f"Failed writing {path}: {exc}")
                continue
            if result.skipped_unchanged:
                lines.append(f"TalentBuilds already up to date ({result.heroes_written} heroes).")
                continue
            lines.append(f"Wrote TalentBuilds ({result.heroes_written} heroes).")
            if result.backup_path:
                lines.append(f"Backup: {os.path.basename(result.backup_path)}")
        lines.append(
            "Restart HotS to see the talent favorites, or use Copy on the Talents tab."
        )
        return lines

    def _has_unlocked_hero_for_pass(self, pass_key: str) -> bool:
        if not self.use_role_passes:
            return True
        return any(
            get_pass_key(hero) == pass_key and self._hero_unlocked(hero)
            for hero in self.enabled_heroes
        )

    def _credit_override_key(self) -> str:
        return str(getattr(self, "seed_name", None) or "")

    def _apply_credit_override(self) -> None:
        if not self.cfg:
            self.cfg = _load_config()
        key = self._credit_override_key()
        store = self.cfg.get("credit_overrides") or {}
        ov = store.get(key) if key else None
        mode = normalize_credit_mode((ov or {}).get("mode") if isinstance(ov, dict) else None)
        if isinstance(ov, dict) and ov.get("mode"):
            self.credit_mode = mode
        else:
            self.credit_mode = normalize_credit_mode(self.seed_credit_mode)
        if isinstance(ov, dict) and "names" in ov:
            self.credit_names = [
                str(n).strip() for n in (ov.get("names") or []) if str(n).strip()
            ]
        else:
            self.credit_names = list(self.seed_credit_names)
        if self.credit_names and self.credit_mode == "me":
            self.credit_mode = "team"
        if isinstance(ov, dict) and "include_ai" in ov:
            self.include_ai = bool(ov["include_ai"])
        else:
            self.include_ai = bool(self.seed_include_ai)

    def _persist_credit_override(self) -> None:
        key = self._credit_override_key()
        if not key:
            return
        store = self.cfg.setdefault("credit_overrides", {})
        store[key] = {
            "mode": self.credit_mode,
            "names": list(self.credit_names),
            "include_ai": bool(self.include_ai),
        }
        _save_config(self.cfg)

    def set_credit_mode(self, mode: str) -> None:
        self.credit_mode = normalize_credit_mode(mode)
        self._persist_credit_override()

    def set_credit_names(self, names: list[str]) -> None:
        seen: set[str] = set()
        cleaned: list[str] = []
        for tag in names:
            name = str(tag).strip()
            key = name.lower()
            if name and key not in seen:
                seen.add(key)
                cleaned.append(name)
        self.credit_names = cleaned
        self._persist_credit_override()

    def add_credit_name(self, tag: str) -> bool:
        name = (tag or "").strip()
        if not name:
            return False
        if any(battle_tags_match(existing, name) for existing in self.credit_names):
            return False
        self.credit_names.append(name)
        if self.credit_mode == "me":
            self.credit_mode = "team"
        self._persist_credit_override()
        return True

    def remove_credit_name(self, tag: str) -> bool:
        name = (tag or "").strip().lower()
        before = list(self.credit_names)
        self.credit_names = [t for t in self.credit_names if t.strip().lower() != name]
        if self.credit_names == before:
            return False
        self._persist_credit_override()
        return True

    def reset_credit_to_seed(self) -> None:
        key = self._credit_override_key()
        store = self.cfg.get("credit_overrides") or {}
        if key and key in store:
            del store[key]
            self.cfg["credit_overrides"] = store
            _save_config(self.cfg)
        self._apply_credit_override()

    def set_include_ai(self, enabled: bool) -> None:
        self.include_ai = bool(enabled)
        self._persist_credit_override()

    def _print_credit_status(self, output) -> None:
        you = ", ".join(self.battle_tags) or "(set with /name)"
        output(f"You: {you}")
        if self.credit_mode == "me":
            output("Scoring: only you")
        elif self.credit_names:
            output(
                f"Scoring: {self.credit_mode}, only these players: "
                + ", ".join(self.credit_names)
            )
        elif self.credit_mode == "team":
            output("Scoring: everyone on your team (no name filter)")
        else:
            output("Scoring: everyone in the match (no name filter)")
        output(f"AI: {'on' if self.include_ai else 'off'}")

    def _persist_battle_tags(self) -> None:
        self.battle_tags = list(self.battle_tags)
        self.battle_tag = self.battle_tags[0] if self.battle_tags else None
        self.cfg["battle_tags"] = self.battle_tags
        if self.battle_tag:
            self.cfg["battle_tag"] = self.battle_tag
        else:
            self.cfg.pop("battle_tag", None)
        _save_config(self.cfg)

    def set_battle_tags(self, tags: list[str]) -> None:
        seen: set[str] = set()
        cleaned: list[str] = []
        for tag in tags:
            name = str(tag).strip()
            key = name.lower()
            if name and key not in seen:
                seen.add(key)
                cleaned.append(name)
        self.battle_tags = cleaned
        self._persist_battle_tags()

    def add_battle_tag(self, tag: str) -> bool:
        name = (tag or "").strip()
        if not name:
            return False
        if any(battle_tags_match(existing, name) for existing in self.battle_tags):
            return False
        self.battle_tags.append(name)
        self._persist_battle_tags()
        return True

    def remove_battle_tag(self, tag: str) -> bool:
        name = (tag or "").strip().lower()
        before = list(self.battle_tags)
        self.battle_tags = [t for t in self.battle_tags if t.strip().lower() != name]
        if self.battle_tags == before:
            return False
        self._persist_battle_tags()
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
        self.battle_tags = _battle_tags_from_cfg(self.cfg)
        self.battle_tag = self.battle_tags[0] if self.battle_tags else None
        latest = _latest_replay_path(self.replay_dirs)
        detected = self._battle_tag_from_replay(latest)
        if self.battle_tags:
            if detected and not battle_tags_match_any(self.battle_tags, detected):
                logger.warning(
                    f"Latest replay's account is named {detected!r}, which is not in your "
                    f"player names ({', '.join(self.battle_tags)}). Add it with /name {detected}"
                )
            else:
                logger.info(f"Player names: {', '.join(self.battle_tags)}")
        elif detected:
            self.add_battle_tag(detected)
            logger.info(
                f"Player name: {detected} (from latest replay). "
                f"Use /name to add or remove names."
            )
        else:
            logger.warning(
                "Could not read a player name from your replays yet. "
                "Play a match or set a name with /name <player name>"
            )

    async def _process_replay(self, path: str):
        filename = os.path.basename(path)
        logger.info(f"Processing replay: {filename}")
        roster = parse_replay_roster(path)
        if not roster:
            logger.warning(
                f"Replay skipped, could not parse {filename}. "
                "Try restarting the client after updating hots.apworld."
            )
            return
        toon = _toon_handle_from_replay_path(path)
        host = pick_host_result(roster, toon_handle=toon, player_names=self.battle_tags)
        if host and host.player_name and self.credit_mode == "me":
            if self.add_battle_tag(host.player_name):
                logger.info(f"Added player name from replay: {host.player_name}")
        credited = select_credited_results(
            roster,
            host,
            credit_mode=self.credit_mode,
            include_ai=self.include_ai,
            credit_names=self.credit_names if self.credit_mode in ("team", "match") else None,
        )
        if not credited:
            if self.credit_mode == "team" and host is None:
                logger.warning(
                    f"Replay skipped, team scoring needs your /name in {filename}."
                )
            else:
                logger.info(f"Replay skipped, nobody to credit in {filename}")
            return
        stim_used = False
        for row in credited:
            is_host_row = host is not None and row.pid == host.pid
            await self._credit_replay_result(path, row, apply_stim=is_host_row and not stim_used)
            if is_host_row:
                stim_used = True
        if self.tracker:
            self.tracker.refresh()
        await self._check_goal()

    async def _credit_replay_result(self, path: str, result, *, apply_stim: bool) -> None:
        filename = os.path.basename(path)
        hero = hero_from_replay_name(result.hero)
        if hero is None:
            logger.info(f"{result.hero!r} skipped, unknown hero in {filename}")
            return
        if hero not in self.enabled_heroes:
            logger.info(f"{hero} skipped, not in your enabled hero pool")
            return
        if not self._hero_unlocked(hero):
            logger.info(
                f"{hero} skipped, locked "
                f"(match result: {result.result}, map: {result.map_name})"
            )
            return
        who = result.player_name or "unknown"
        if getattr(result, "is_ai", False):
            logger.info(f"From {who} [AI] — {hero}")
        else:
            logger.info(f"From {who} — {hero}")
        score = dict(result.score or {})
        cons = getattr(self, "consumables", None)
        if apply_stim and cons is not None and cons.consume_boost_for_replay(path):
            score = apply_stimpack_score(score)
            left = cons.stim_remaining
            extra = (
                f" ({left} Stimpack match{'' if left == 1 else 'es'} remaining)"
                if left else " (Stimpack expired)"
            )
            logger.info(f"Stimpack: match tallies count double{extra}.")
        fired = detect_checks(score, result.result, result.level_history)
        if self.cumulative_checks:
            await self._credit_hero_stats(hero, score)
            instant = detect_instant_checks(score, result.result, result.level_history)
            cumulative = detect_cumulative_checks(
                self.hero_stat_totals.get(hero, {}),
                self.hero_checks.get(hero, HERO_CHECKS.get(hero, [])),
            )
            fired = instant | cumulative
        new_ids = [
            i for i in _checks_to_loc_ids(hero, fired, self.hero_checks or None)
            if i not in self.checked_locations
        ]
        pass_key = get_pass_key(hero)
        if (
            self.include_timed_win_check
            and TIMED_WIN_18 in self.pass_check_keys
            and result.result == "Win"
            and result.duration_seconds <= self.timed_win_max_seconds
            and self._has_unlocked_hero_for_pass(pass_key)
        ):
            timed_loc = pass_location_name(pass_key, TIMED_WIN_18)
            timed_id = location_name_to_id.get(timed_loc)
            if timed_id is not None and timed_id not in self.checked_locations:
                new_ids.append(timed_id)
        for loc_id in self._talent_check_ids(hero, result):
            if loc_id not in self.checked_locations and loc_id not in new_ids:
                new_ids.append(loc_id)
        await self._credit_daily_quests(hero, score)
        if new_ids:
            await self._send_new_location_checks(new_ids)
        xp_amount = int(score.get("ExperienceContribution", 0) or 0)
        if xp_amount > 0 and pass_key in self.enabled_pass_keys:
            await self._credit_pass_xp(pass_key, xp_amount)

    def _talent_check_ids(self, hero: str, result) -> list[int]:
        reqs_raw = self.hero_talent_requirements.get(hero) or []
        if not reqs_raw:
            return []
        required = list(reqs_raw)
        picked = list(getattr(result, "talent_picks", None) or [])
        if not picked:
            logger.warning(
                f"Talent checks skipped for {hero}: no talent pick indices in replay "
                "(AI games / observers may lack them)."
            )
            return []
        picked_set = set(picked)
        ids: list[int] = []
        for req in required:
            level = int(req["level"])
            if talent_req_is_any(req):
                if not any(lv == level for lv, _rk in picked_set):
                    continue
            elif (level, int(req["rank"])) not in picked_set:
                continue
            loc_id = location_name_to_id.get(talent_location_name(hero, level))
            if loc_id is not None:
                ids.append(loc_id)
        return ids

    async def _rescan_latest(self, path: str) -> None:
        self.known_replays.pop(path, None)
        self.pending_replays.pop(path, None)
        try:
            await self._process_replay(path)
        except Exception as exc:
            logger.warning(f"Error reprocessing {os.path.basename(path)}: {exc}")
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
    async def _scan_replays(self):
        current = _scan_replay_mtimes(self.replay_dirs)
        now = time.time()
        for path, mtime in current.items():
            if path not in self.known_replays:
                self.known_replays[path] = mtime
                self.pending_replays[path] = now
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
                logger.warning(f"Error processing {os.path.basename(path)}: {exc}")
    async def _replay_loop(self):
        """Watch replay folders."""
        wake = asyncio.Event()
        loop = asyncio.get_running_loop()
        observer = None

        def _nudge(*_args) -> None:
            loop.call_soon_threadsafe(wake.set)

        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            class _ReplayHandler(FileSystemEventHandler):
                def on_created(self, event):
                    if not event.is_directory and str(event.src_path).lower().endswith(".stormreplay"):
                        _nudge()

                def on_modified(self, event):
                    if not event.is_directory and str(event.src_path).lower().endswith(".stormreplay"):
                        _nudge()

            if self.replay_dirs:
                observer = Observer()
                handler = _ReplayHandler()
                for d in self.replay_dirs:
                    observer.schedule(handler, d, recursive=False)
                observer.daemon = True
                observer.start()
                logger.info("Replay watcher started (filesystem events).")
        except Exception:
            observer = None
            logger.info("Replay watcher started.")

        try:
            while not self.exit_event.is_set():
                if self._connected and self.replay_dirs:
                    try:
                        await self._scan_replays()
                    except Exception as exc:
                        logger.warning(f"Replay scan error: {exc}")
                wake.clear()
                try:
                    await asyncio.wait_for(wake.wait(), timeout=POLL_INTERVAL)
                except asyncio.TimeoutError:
                    pass
        finally:
            if observer is not None:
                try:
                    observer.stop()
                    observer.join(timeout=2)
                except Exception:
                    pass

    def _load_replay_dirs(self) -> None:
        self.cfg = _load_config()
        self.cfg.pop("toon_handle", None)
        dirs_from_cfg = [d for d in self.cfg.get("replay_dirs", []) if os.path.isdir(d)]
        if dirs_from_cfg:
            self.replay_dirs = dirs_from_cfg
        else:
            self.replay_dirs = _find_multiplayer_dirs(ACCOUNTS_ROOT)
            if self.replay_dirs:
                self.cfg["replay_dirs"] = self.replay_dirs
        if self.replay_dirs:
            _save_config(self.cfg)
            _warn_empty_replay_dirs(self.replay_dirs)
        self.battle_tags = _battle_tags_from_cfg(self.cfg)
        self.battle_tag = self.battle_tags[0] if self.battle_tags else None

    async def _setup(self):
        self._load_replay_dirs()
        if self.replay_dirs:
            await self._resolve_battle_tag()
            self.known_replays = _scan_replay_mtimes(self.replay_dirs)
            logger.info(
                f"Ignoring {len(self.known_replays)} existing replays "
                f"(use /rescan to reprocess your latest match)."
            )

    async def _prompt_missing(self):
        msg = f"No replay folders found under: {ACCOUNTS_ROOT}"
        if gui_enabled:
            while not self.ui:
                await asyncio.sleep(0.05)
            logger.warning(f"{msg}")
            logger.info(
                "Paste your Multiplayer replay folder path in the console "
                "input below and press Enter (or Enter alone to skip)."
            )
            custom = (await self.console_input()).strip()
        else:
            print(f"\n=== Heroes of the Storm - First Run Setup ===\n{msg}")
            custom = input("Enter your replay folder path (or Enter to skip): ").strip()
        if custom and os.path.isdir(custom):
            self.replay_dirs = [custom]
            self.cfg["replay_dirs"] = self.replay_dirs
            _save_config(self.cfg)
            _warn_empty_replay_dirs(self.replay_dirs)
            await self._resolve_battle_tag()
            self.known_replays = _scan_replay_mtimes(self.replay_dirs)
            logger.info(
                f"Replay folder configured, ignoring {len(self.known_replays)} "
                f"existing replays (use /rescan to reprocess your latest match)."
            )
        elif not self.replay_dirs:
            logger.warning(
                "No replay folder - checks will not be detected until one is configured. "
                f"Edit {CONFIG_FILE} or paste a path in the console when prompted."
            )
            _save_config(self.cfg)

    def run_gui(self):
        from kvui import GameManager, UILog
        from .TalentsPanel import TalentsPanel
        from .LootPanel import LootPanel
        class HoTSManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago Heroes of the Storm Client"
            def build(self):
                ret = super().build()
                from .TrackerPanel import TrackerPanel
                self.ctx.tab_goal = self.add_client_tab("Goal", UILog())
                self.ctx.tracker_panel = TrackerPanel(self.ctx)
                self.ctx.tab_tracker = self.add_client_tab("Tracker", self.ctx.tracker_panel)
                self.ctx.loot_panel = LootPanel(self.ctx)
                self.ctx.tab_loot = self.add_client_tab("Loot", self.ctx.loot_panel)
                self.ctx.talents_panel = TalentsPanel(self.ctx)
                self.ctx.tab_talents = self.add_client_tab("Talents", self.ctx.talents_panel)
                self.ctx.tab_unlocks = self.add_client_tab("Unlocks", UILog())
                self._hook_loot_tab_resize()
                if getattr(self.ctx, "tracker", None):
                    self.ctx.tracker.refresh()
                return ret

            def _hook_loot_tab_resize(self) -> None:
                original = self.screens.switch_screens

                def switch_screens(new_tab):
                    original(new_tab)
                    if getattr(new_tab, "text", "") == "Loot":
                        self._grow_loot_window()

                self.screens.switch_screens = switch_screens

            def _grow_loot_window(self) -> None:
                if getattr(self.ctx, "_loot_window_grown", False):
                    return
                try:
                    from kivy.core.window import Window
                    from kivy.metrics import dp
                    Window.size = (Window.width, Window.height + dp(88))
                    self.ctx._loot_window_grown = True
                except Exception:
                    pass
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
        if not ctx.replay_dirs:
            asyncio.create_task(ctx._prompt_missing(), name="ReplayFolderSetup")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()
    colorama.just_fix_windows_console()
    asyncio.run(main())
    colorama.deinit()
if __name__ == "__main__":
    launch()

