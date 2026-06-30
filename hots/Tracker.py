from __future__ import annotations

from .Challenges import get_pass_key, get_role, pass_name_for_key, role_display, PASS_KEYS, HERO_CHECKS
from .Locations import location_table


class HoTSTracker:
    def __init__(self, ctx):
        self.ctx = ctx

    def has_hero_unlock(self, hero: str) -> bool:
        return hero in self.ctx.unlocked_heroes

    def has_role_pass(self, hero: str) -> bool:
        if not self.ctx.use_role_passes:
            return True
        return get_pass_key(hero) in self.ctx.unlocked_roles

    def hero_unlocked(self, hero: str) -> bool:
        if hero not in self.ctx.enabled_heroes:
            return False
        return self.has_hero_unlock(hero) and self.has_role_pass(hero)

    def location_accessible(self, loc_name: str) -> bool:
        data = location_table.get(loc_name)
        if not data or not data.hero:
            return True
        return self.hero_unlocked(data.hero)

    def is_checked(self, loc_name: str) -> bool:
        data = location_table.get(loc_name)
        if not data or data.id is None:
            return False
        return data.id in self.ctx.checked_locations

    def _unlock_needs(self, hero: str) -> str:
        needs: list[str] = []
        if not self.has_hero_unlock(hero):
            needs.append(hero)
        if self.ctx.use_role_passes and not self.has_role_pass(hero):
            needs.append(pass_name_for_key(get_pass_key(hero)))
        return " + ".join(needs)

    def _hero_check_count(self, hero: str) -> int:
        sd = getattr(self.ctx, "slot_data", {}) or {}
        hero_checks = sd.get("hero_checks", {})
        if hero in hero_checks:
            return len(hero_checks[hero])
        return len(HERO_CHECKS.get(hero, []))

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
        if self.ctx.starting_heroes:
            if len(self.ctx.starting_heroes) == 1:
                output(f"Starting hero: {self.ctx.starting_heroes[0]}")
            else:
                output(f"Starting heroes: {', '.join(self.ctx.starting_heroes)}")
        output(f"Goal: {sd.get('goal_summary', '?')}")
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
        goal_names = sd.get("goal_location_names", [])
        done = sum(1 for name in goal_names if self.is_checked(name))
        rows = [
            {"text": f"Goal: {sd.get('goal_summary', '?')}"},
            {"text": f"Progress: {done}/{len(goal_names)}"},
            {"text": ""},
        ]
        for hero in sd.get("goal_heroes", []):
            role = get_role(hero)
            hero_ok = self.has_hero_unlock(hero)
            pass_ok = self.has_role_pass(hero)
            needs = self._unlock_needs(hero)
            if self.hero_unlocked(hero):
                rows.append(self._line(f"{hero} — ready", done=True))
            else:
                rows.append({"text": f"{hero} — needs {needs or '?'}"})
            if self.ctx.use_role_passes:
                pass_name = pass_name_for_key(get_pass_key(hero))
                rows.append(
                    self._line(f"  {pass_name}", done=pass_ok)
                    if pass_ok
                    else {"text": f"  {pass_name}"}
                )
            rows.append(
                self._line(f"  {hero}", done=hero_ok)
                if hero_ok
                else {"text": f"  {hero}"}
            )
            rows.append({"text": ""})

        rows.append({"text": "Goal checks:"})
        for name in goal_names:
            if not self.location_accessible(name) and not self.is_checked(name):
                continue
            short = name.split(": ", 1)[-1]
            if self.is_checked(name):
                rows.append(self._line(f"  [done] {short}", done=True))
            else:
                rows.append({"text": f"  [open] {short}"})
        tab.content.data = rows

    def update_tracker_tab(self) -> None:
        tab = getattr(self.ctx, "tab_tracker", None)
        if not tab:
            return
        if not getattr(self.ctx, "tracker_enabled", True):
            tab.content.data = [{"text": "Tracker disabled. Use /hots for status."}]
            return

        rows: list[dict] = []
        by_hero: dict[str, list[str]] = {h: [] for h in self.unlocked_heroes()}

        for loc_id in getattr(self.ctx, "missing_locations", set()):
            if loc_id in self.ctx.checked_locations:
                continue
            loc_name = self.ctx.location_names.lookup_in_game(loc_id, self.ctx.game)
            if not loc_name or not self.location_accessible(loc_name):
                continue
            data = location_table.get(loc_name)
            hero = data.hero if data else None
            if hero and hero in by_hero:
                by_hero[hero].append(loc_name)

        for hero in sorted(by_hero):
            checks = sorted(by_hero[hero])
            if not checks:
                continue
            rows.append({"text": f"--- {hero} ({role_display(get_role(hero))}) ---"})
            for name in checks:
                rows.append({"text": f"  {name.split(': ', 1)[-1]}"})

        if not rows:
            rows = [{"text": "No open checks for unlocked heroes."}]
        tab.content.data = rows

    def update_unlocks_tab(self) -> None:
        tab = getattr(self.ctx, "tab_unlocks", None)
        if not tab:
            return
        rows: list[dict] = []
        if self.ctx.starting_heroes:
            if len(self.ctx.starting_heroes) == 1:
                rows.append({"text": f"Starting hero: {self.ctx.starting_heroes[0]}"})
            else:
                rows.append({"text": f"Starting heroes: {', '.join(self.ctx.starting_heroes)}"})
            rows.append({"text": ""})

        if self.ctx.use_role_passes:
            rows.append({"text": "Role passes:"})
            for pass_key in PASS_KEYS:
                label = pass_name_for_key(pass_key)
                rows.append(
                    self._line(f"  {label}", done=pass_key in self.ctx.unlocked_roles)
                    if pass_key in self.ctx.unlocked_roles
                    else {"text": f"  {label}"}
                )
            rows.append({"text": ""})

        rows.append({"text": "Hero unlocks:"})
        for hero in sorted(self.ctx.enabled_heroes):
            role = get_role(hero)
            unlocked = self.hero_unlocked(hero)
            suffix = f" ({role_display(role)}, {self._hero_check_count(hero)} checks)"
            if unlocked:
                rows.append(self._line(f"  {hero}{suffix}", done=True))
            else:
                needs = self._unlock_needs(hero)
                rows.append({"text": f"  {hero}{suffix} — needs {needs}"})

        if len(rows) <= 2:
            rows = [{"text": "No heroes unlocked yet."}]
        tab.content.data = rows

    def refresh(self) -> None:
        self.update_goal_tab()
        self.update_tracker_tab()
        self.update_unlocks_tab()
