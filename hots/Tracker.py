from .Challenges import (
    get_pass_key, get_role, pass_name_for_key, role_display, pass_contributor_hint,
    HERO_CHECKS, XP_PASS_18K, XP_PASS_40K, PASS_XP_THRESHOLDS,
    CHECK_SCORE_THRESHOLDS, pass_location_name,
    DAILY_QUESTS_COMPLETE, DAILY_QUEST_UNLOCK_MIN, capable_heroes_in_pool,
    daily_quest_location_name,
)
from .Locations import location_table
from .Talents import TALENT_LEVELS, parse_talent_check_key, talent_req_is_any
from .Items import PROGRESSIVE_HERO_WAVE_NAME, progressive_waves_needed


class HoTSTracker:
    def __init__(self, ctx):
        self.ctx = ctx

    def has_hero_unlock(self, hero: str) -> bool:
        if hero in self.ctx.unlocked_heroes:
            return True
        need = int(getattr(self.ctx, "shards_to_unlock", 5) or 0)
        return need > 0 and getattr(self.ctx, "hero_shards", {}).get(hero, 0) >= need

    def shard_progress(self, hero: str) -> tuple[int, int]:
        need = int(getattr(self.ctx, "shards_to_unlock", 5) or 0)
        have = getattr(self.ctx, "hero_shards", {}).get(hero, 0)
        if hero in getattr(self.ctx, "full_unlock_heroes", []) or hero in self.ctx.starting_heroes:
            return (need if hero in self.ctx.unlocked_heroes else 0, need)
        return min(have, need), need

    def has_role_pass(self, hero: str) -> bool:
        if not self.ctx.use_role_passes:
            return True
        return get_pass_key(hero) in self.ctx.unlocked_roles

    def hero_unlocked(self, hero: str) -> bool:
        if hero not in self.ctx.enabled_heroes:
            return False
        return self.has_hero_unlock(hero) and self.has_role_pass(hero)

    def has_pass_unlock(self, pass_key: str) -> bool:
        if not self.ctx.use_role_passes:
            return True
        return pass_key in self.ctx.unlocked_roles

    def has_hero_for_pass(self, pass_key: str) -> bool:
        """True when at least one unlocked hero belongs to this pass bucket."""
        if not self.ctx.use_role_passes:
            return True
        return any(
            get_pass_key(hero) == pass_key and self.hero_unlocked(hero)
            for hero in self.ctx.enabled_heroes
        )

    def can_do_pass_checks(self, pass_key: str) -> bool:
        return self.has_pass_unlock(pass_key) and self.has_hero_for_pass(pass_key)

    def location_accessible(self, loc_name: str) -> bool:
        data = location_table.get(loc_name)
        if not data:
            return True
        if data.chest_index:
            cost = int(getattr(self.ctx, "chest_cost_xp", 1000) or 1000)
            need = data.chest_index * cost
            from .Items import open_capacity_value
            total = 0
            for item in getattr(self.ctx, "items_received", []):
                name = self.ctx.item_names.lookup_in_game(item.item)
                total += open_capacity_value(name)
            return total >= need
        if data.pass_key:
            return self.can_do_pass_checks(data.pass_key)
        if data.hero:
            return self.hero_unlocked(data.hero)
        if data.daily_quest_key:
            keys = list(getattr(self.ctx, "daily_quest_keys", None) or [])
            if data.daily_quest_key == DAILY_QUESTS_COMPLETE:
                return bool(keys) and all(self.daily_quest_in_logic(k) for k in keys)
            return self.daily_quest_in_logic(data.daily_quest_key)
        return True

    def daily_quest_in_logic(self, quest_key: str) -> bool:
        """Match world rules: Daily Quest Unlock N plus 3 playable capable heroes."""
        has_slip_fn = getattr(self.ctx, "_has_daily_quest_slip", None)
        if not (has_slip_fn and has_slip_fn(quest_key)):
            return False
        defs = getattr(self.ctx, "daily_quest_defs", {}) or {}
        cap = (defs.get(quest_key) or {}).get("capability")
        if not cap:
            return False
        enabled = list(getattr(self.ctx, "enabled_heroes", []) or [])
        heroes = capable_heroes_in_pool(cap, enabled)
        return sum(1 for hero in heroes if self.hero_unlocked(hero)) >= DAILY_QUEST_UNLOCK_MIN

    def is_checked(self, loc_name: str) -> bool:
        data = location_table.get(loc_name)
        if not data or data.id is None:
            return False
        return data.id in self.ctx.checked_locations

    def _progressive_wave_count(self) -> int:
        return int(getattr(self.ctx, "progressive_hero_waves", 0) or 0)

    def _unlock_needs(self, hero: str) -> str:
        needs: list[str] = []
        wave_need = (getattr(self.ctx, "hero_wave_need", None) or {}).get(hero) or 0
        if wave_need and not self.has_hero_unlock(hero):
            have = self._progressive_wave_count()
            needs.append(f"{PROGRESSIVE_HERO_WAVE_NAME} {min(have, wave_need)}/{wave_need}")
        elif not self.has_hero_unlock(hero):
            have, need = self.shard_progress(hero)
            if hero in getattr(self.ctx, "shard_heroes", []):
                needs.append(f"shards {have}/{need}")
            else:
                needs.append(hero)
        if self.ctx.use_role_passes and not self.has_role_pass(hero):
            needs.append(pass_name_for_key(get_pass_key(hero)))
        return " + ".join(needs)

    def _hero_check_count(self, hero: str) -> int:
        sd = getattr(self.ctx, "slot_data", {}) or {}
        hero_checks = sd.get("hero_checks", {})
        if hero in hero_checks:
            base = len(hero_checks[hero])
        else:
            base = len(HERO_CHECKS.get(hero, []))
        reqs_by_hero = getattr(self.ctx, "hero_talent_requirements", None) or sd.get(
            "hero_talent_requirements", {}
        )
        talent_n = len(reqs_by_hero.get(hero) or [])
        return base + talent_n

    def _pass_xp_progress(self, pass_key: str) -> tuple[int, int, bool, bool]:
        thresholds = getattr(self.ctx, "pass_xp_thresholds", PASS_XP_THRESHOLDS)
        total = getattr(self.ctx, "pass_xp_totals", {}).get(pass_key, 0)
        tier1 = thresholds.get(XP_PASS_18K, 18_000)
        tier2 = thresholds.get(XP_PASS_40K, 40_000)
        tier1_done = self.is_checked(pass_location_name(pass_key, XP_PASS_18K))
        tier2_done = self.is_checked(pass_location_name(pass_key, XP_PASS_40K))
        goal = tier2 if not tier2_done else tier2
        return total, goal, tier1_done, tier2_done

    def _talent_label(self, hero: str, level: int, loc_name: str | None = None) -> str:
        reqs = getattr(self.ctx, "hero_talent_requirements", {}).get(hero) or []
        req = next((r for r in reqs if int(r["level"]) == level), None)
        base = loc_name or f"Level {level} Talent"
        if req and talent_req_is_any(req):
            return f"{base} (any)" if loc_name else f"Level {level} Talent (any)"
        rank = int(req["rank"]) if req else None
        if rank:
            return f"{base} #{rank}" if loc_name else f"Level {level} Talent #{rank}"
        return base if loc_name else f"Level {level} Talent"

    def unlocked_heroes(self) -> list[str]:
        return sorted(h for h in self.ctx.enabled_heroes if self.hero_unlocked(h))

    @staticmethod
    def _line(text: str, *, done: bool = False) -> dict:
        if done:
            return {"text": f"[color=44cc44]{text}[/color]"}
        return {"text": text}

    def print_status(self, output) -> None:
        sd = getattr(self.ctx, "slot_data", {}) or {}
        output("Heroes of the Storm — Status")
        if self.ctx.starting_heroes and not getattr(self.ctx, "party_mode", False):
            if len(self.ctx.starting_heroes) == 1:
                output(f"Starting hero: {self.ctx.starting_heroes[0]}")
            else:
                output(f"Starting heroes: {', '.join(self.ctx.starting_heroes)}")
        output(f"Goal: {sd.get('goal_summary', '?')}")
        if getattr(self.ctx, "_print_credit_status", None):
            self.ctx._print_credit_status(output)
        output(f"Unlocked heroes: {', '.join(self.unlocked_heroes()) or '(none)'}")
        output(f"Open checks: {len(self.accessible_missing())}")
        output(f"Checked: {len(self.ctx.checked_locations)}")

    def accessible_missing(self) -> list[str]:
        names: list[str] = []
        for loc_id in getattr(self.ctx, "missing_locations", set()):
            if loc_id in self.ctx.checked_locations:
                continue
            loc_name = self.ctx.location_names.lookup_in_game(loc_id, self.ctx.game)
            if loc_name and self.location_accessible(loc_name):
                names.append(loc_name)
        return sorted(names)

    def update_goal_tab(self) -> None:
        tab = getattr(self.ctx, "tab_goal", None)
        if not tab:
            return
        sd = getattr(self.ctx, "slot_data", {}) or {}
        goal_names = list(sd.get("goal_location_names", []) or [])
        goal_heroes = list(sd.get("goal_heroes", []) or [])
        goal_mode = sd.get("goal_mode", "")
        done = sum(1 for name in goal_names if self.is_checked(name))
        rows = [
            {"text": f"Goal: {sd.get('goal_summary', '?')}"},
            {"text": f"Progress: {done}/{len(goal_names)}"},
            {"text": ""},
        ]

        win_only = goal_mode == "distinct_wins" or (
            goal_heroes
            and goal_names
            and all(name.endswith(": Win a match") for name in goal_names)
        )
        if win_only and goal_heroes:
            rows.append({"text": "Heroes (win one match each):"})
            for hero in goal_heroes:
                win_name = f"{hero}: Win a match"
                if self.is_checked(win_name):
                    rows.append(self._line(f"  {hero} - done", done=True))
                elif self.hero_unlocked(hero):
                    rows.append({"text": f"  {hero} - ready (play and win)"})
                else:
                    needs = self._unlock_needs(hero)
                    rows.append({"text": f"  {hero} - locked ({needs or '?'})"})
            tab.content.data = rows
            return

        if goal_heroes:
            rows.append({"text": "Goal heroes:"})
            for hero in goal_heroes:
                if self.hero_unlocked(hero):
                    rows.append(self._line(f"  {hero} - unlocked", done=True))
                else:
                    needs = self._unlock_needs(hero)
                    rows.append({"text": f"  {hero} - locked ({needs or '?'})"})
            rows.append({"text": ""})

        rows.append({"text": "Goal checks:"})
        for name in goal_names:
            if not self.location_accessible(name) and not self.is_checked(name):
                continue
            display = name
            data = location_table.get(name)
            parsed = parse_talent_check_key(data.check_key) if data and data.check_key else None
            if parsed and data.hero:
                level, _ = parsed
                display = self._talent_label(data.hero, level, name)
            if self.is_checked(name):
                rows.append(self._line(f"  {display}", done=True))
            else:
                rows.append({"text": f"  {display}"})
        tab.content.data = rows

    def _collect_open_checks(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        by_pass: dict[str, list[str]] = {}
        by_hero: dict[str, list[str]] = {h: [] for h in self.unlocked_heroes()}

        for loc_id in getattr(self.ctx, "missing_locations", set()):
            if loc_id in self.ctx.checked_locations:
                continue
            loc_name = self.ctx.location_names.lookup_in_game(loc_id, self.ctx.game)
            if not loc_name or not self.location_accessible(loc_name):
                continue
            data = location_table.get(loc_name)
            if data and data.pass_key:
                by_pass.setdefault(data.pass_key, []).append(loc_name)
                continue
            hero = data.hero if data else None
            if hero and hero in by_hero:
                by_hero[hero].append(loc_name)

        return by_pass, by_hero

    def _pass_check_rows(self, pass_key: str, pass_check_keys: list[str]) -> list[dict]:
        rows: list[dict] = []
        has_xp = XP_PASS_18K in pass_check_keys

        if has_xp:
            total, goal, tier1_done, tier2_done = self._pass_xp_progress(pass_key)
            if not (tier1_done and tier2_done):
                rows.append({"text": f"  {total:,} / {goal:,} XP"})

        for check_key in pass_check_keys:
            loc_name = pass_location_name(pass_key, check_key)
            short = loc_name.split(": ", 1)[-1]
            if self.is_checked(loc_name):
                rows.append(self._line(f"  {short}", done=True))
            elif self.location_accessible(loc_name):
                rows.append({"text": f"  {short}"})

        return rows

    def _pass_has_open_checks(self, pass_key: str, pass_check_keys: list[str]) -> bool:
        for check_key in pass_check_keys:
            loc_name = pass_location_name(pass_key, check_key)
            if self.location_accessible(loc_name) and not self.is_checked(loc_name):
                return True
        return False

    def _daily_quest_rows(self) -> list[dict]:
        """Daily Quest 1 is always listed. Later dailies wait for their unlock."""
        """Even though Daily Quest 1 is always listed, it is not truly considered in-logic until 
        3 associated heroes are unlocked."""
        """This allows for some starting progress on Daily 1, but does not cause a bottleneck on the location."""
        keys = list(getattr(self.ctx, "daily_quest_keys", None) or [])
        if not keys:
            return []
        totals = getattr(self.ctx, "daily_quest_totals", {}) or {}
        defs = getattr(self.ctx, "daily_quest_defs", {}) or {}
        rows: list[dict] = []
        for index, quest_key in enumerate(keys):
            info = defs.get(quest_key) or {}
            loc_name = daily_quest_location_name(quest_key)
            done = self.is_checked(loc_name)
            in_logic = self.daily_quest_in_logic(quest_key)
            if index > 0 and not in_logic and not done:
                continue
            title = (info.get("name") or loc_name).replace("Daily Quest: ", "")
            if done:
                rows.append(self._line(f"  {title}", done=True))
                continue
            threshold = int(info.get("threshold", 0) or 0)
            current = int(totals.get(quest_key, 0) or 0)
            progress = f"  {current:,}/{threshold:,}" if threshold else ""
            rows.append({"text": f"  {title}{progress}"})
        if not rows:
            return []
        complete_name = daily_quest_location_name(DAILY_QUESTS_COMPLETE)
        if self.is_checked(complete_name):
            rows.append(self._line("  Complete all daily quests", done=True))
        return [{"text": "--- Daily Quests ---"}, *rows, {"text": ""}]

    def update_tracker_tab(self) -> None:
        panel = getattr(self.ctx, "tracker_panel", None)
        if panel is not None:
            panel.refresh()
            return
        tab = getattr(self.ctx, "tab_tracker", None)
        if not tab:
            return
        if not getattr(self.ctx, "tracker_enabled", True):
            tab.content.data = [{"text": "Tracker disabled. Use /hots for status."}]
            return

        rows: list[dict] = []
        sd = getattr(self.ctx, "slot_data", {}) or {}
        cons = getattr(self.ctx, "consumables", None)
        if cons is not None and cons.stim_remaining > 0:
            queued = cons.stim_remaining
            matches = "match" if queued == 1 else "matches"
            rows.append({
                "text": f"[color=ffd24a]Stimpack active: {queued} boosted {matches} queued[/color]"
            })
            rows.append({"text": ""})
        rows.extend(self._daily_quest_rows())
        pass_check_keys = sd.get("pass_check_keys", [])
        enabled_pass_keys = sd.get("enabled_pass_keys", [])

        _, by_hero = self._collect_open_checks()

        if pass_check_keys:
            for pass_key in enabled_pass_keys:
                if not self.can_do_pass_checks(pass_key):
                    continue
                if not self._pass_has_open_checks(pass_key, pass_check_keys):
                    continue
                label = pass_name_for_key(pass_key)
                rows.append({"text": f"--- {label} ---"})
                hint = pass_contributor_hint(pass_key)
                if hint:
                    rows.append({"text": f"  {hint}"})
                rows.extend(self._pass_check_rows(pass_key, pass_check_keys))
                rows.append({"text": ""})

        cumulative = bool(getattr(self.ctx, "cumulative_checks", False))
        for hero in sorted(by_hero):
            checks = by_hero[hero]
            if not checks:
                continue
            rows.append({"text": f"--- {hero} ({role_display(get_role(hero))}) ---"})
            totals = getattr(self.ctx, "hero_stat_totals", {}).get(hero, {}) if cumulative else {}
            for name in self._sorted_hero_check_names(checks):
                short = name.split(": ", 1)[-1]
                progress = ""
                data = location_table.get(name)
                check_key = data.check_key if data else None
                parsed = parse_talent_check_key(check_key) if check_key else None
                if parsed:
                    level, _ = parsed
                    short = self._talent_label(hero, level)
                if cumulative:
                    if check_key and check_key in CHECK_SCORE_THRESHOLDS:
                        field, threshold = CHECK_SCORE_THRESHOLDS[check_key]
                        cur = int(totals.get(field, 0) or 0)
                        progress = f" ({cur:,}/{threshold:,})"
                rows.append({"text": f"  {short}{progress}"})

        while rows and rows[-1] == {"text": ""}:
            rows.pop()

        if not rows:
            rows = [{"text": "No open checks for unlocked heroes."}]
        tab.content.data = rows

    def _sorted_hero_check_names(self, names: list[str]) -> list[str]:
        def sort_key(name: str):
            data = location_table.get(name)
            if data and data.check_key:
                parsed = parse_talent_check_key(data.check_key)
                if parsed:
                    level, rank = parsed
                    return (1, TALENT_LEVELS.index(level) if level in TALENT_LEVELS else level, rank)
            return (0, name.lower(), 0)

        return sorted(names, key=sort_key)

    def update_unlocks_tab(self) -> None:
        tab = getattr(self.ctx, "tab_unlocks", None)
        if not tab:
            return
        rows: list[dict] = []
        if self.ctx.starting_heroes:
            if getattr(self.ctx, "hero_waves", None) and getattr(self.ctx, "party_mode", False):
                start_n = max(1, int(getattr(self.ctx, "starting_waves", 1) or 1))
                total = max(0, len(self.ctx.hero_waves) - start_n)
                have = self._progressive_wave_count()
                for index, wave in enumerate(self.ctx.hero_waves):
                    labels = ", ".join(
                        f"{hero} ({role_display(get_role(hero))})" for hero in wave
                    )
                    need = progressive_waves_needed(index, start_n)
                    if need <= 0:
                        rows.append({"text": f"Starting wave {index + 1}: {labels}"})
                    elif have >= need:
                        rows.append(self._line(
                            f"After {need}/{total} {PROGRESSIVE_HERO_WAVE_NAME}: {labels}",
                            done=True,
                        ))
                    else:
                        rows.append({"text": (
                            f"After {need}/{total} {PROGRESSIVE_HERO_WAVE_NAME}: {labels}"
                            f" — {have}/{need} collected"
                        )})
            elif len(self.ctx.starting_heroes) == 1:
                rows.append({"text": f"Starting hero: {self.ctx.starting_heroes[0]}"})
            else:
                rows.append({"text": f"Starting heroes: {', '.join(self.ctx.starting_heroes)}"})
            rows.append({"text": ""})

        if self.ctx.use_role_passes:
            sd = getattr(self.ctx, "slot_data", {}) or {}
            enabled_pass_keys = sd.get("enabled_pass_keys", [])
            rows.append({"text": "Role passes in seed:"})
            for pass_key in enabled_pass_keys:
                label = pass_name_for_key(pass_key)
                if pass_key in self.ctx.unlocked_roles:
                    rows.append(self._line(f"  {label}", done=True))
                else:
                    rows.append({"text": f"  {label}"})
            rows.append({"text": ""})

        rows.append({"text": "Hero unlocks:"})
        for hero in sorted(self.ctx.enabled_heroes):
            role = get_role(hero)
            unlocked = self.hero_unlocked(hero)
            have, need = self.shard_progress(hero)
            if hero in getattr(self.ctx, "shard_heroes", []):
                shard_txt = f", shards {have}/{need}"
            elif hero in self.ctx.starting_heroes:
                shard_txt = ", starting"
            elif hero in getattr(self.ctx, "full_unlock_heroes", []):
                shard_txt = ", full unlock"
            elif (getattr(self.ctx, "hero_wave_need", None) or {}).get(hero):
                need_n = int(self.ctx.hero_wave_need[hero])
                have_n = self._progressive_wave_count()
                shard_txt = f", {PROGRESSIVE_HERO_WAVE_NAME} {min(have_n, need_n)}/{need_n}"
            else:
                shard_txt = ""
            suffix = f" ({role_display(role)}, {self._hero_check_count(hero)} checks{shard_txt})"
            if unlocked:
                rows.append(self._line(f"  {hero}{suffix}", done=True))
            else:
                needs = self._unlock_needs(hero)
                rows.append({"text": f"  {hero}{suffix} — needs {needs}"})

        if len(rows) <= 2:
            rows = [{"text": "No heroes unlocked yet."}]
        tab.content.data = rows

    def update_talents_tab(self) -> None:
        panel = getattr(self.ctx, "talents_panel", None)
        if panel is not None:
            panel.refresh()

    def refresh(self) -> None:
        self.update_goal_tab()
        self.update_tracker_tab()
        self.update_talents_tab()
        self.update_unlocks_tab()
