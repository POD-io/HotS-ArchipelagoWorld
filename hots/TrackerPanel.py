from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner, SpinnerOption

from kvui import UILog

from .Challenges import CHECK_SCORE_THRESHOLDS, pass_contributor_hint, pass_name_for_key
from .Locations import location_table
from .Talents import parse_talent_check_key

ALL_UNLOCKED = "All unlocked heroes"
_BODY_SIZE = dp(20)
_ROW_H = dp(26)
_HEAD_H = dp(30)
_REFRESH_DEBOUNCE = 0.08

# Dropdown tint: complete heroes (no open checks) vs still open.
_COLOR_COMPLETE_BG = (0.20, 0.48, 0.28, 1)
_COLOR_COMPLETE_FG = (0.85, 1.0, 0.88, 1)
_COLOR_OPEN_BG = (0.28, 0.30, 0.34, 1)
_COLOR_OPEN_FG = (0.92, 0.93, 0.96, 1)
_COLOR_ALL_BG = (0.32, 0.34, 0.40, 1)
_COLOR_ALL_FG = (1.0, 1.0, 1.0, 1)


class _HeroSpinnerOption(SpinnerOption):
    """Per-hero dropdown row; greens out when that hero has no open checks."""

    complete_heroes: set[str] = set()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.font_size = _BODY_SIZE
        self._recolor()
        self.bind(text=lambda *_: self._recolor())

    def _recolor(self) -> None:
        name = self.text or ""
        if name == ALL_UNLOCKED:
            self.background_color = _COLOR_ALL_BG
            self.color = _COLOR_ALL_FG
        elif name in _HeroSpinnerOption.complete_heroes:
            self.background_color = _COLOR_COMPLETE_BG
            self.color = _COLOR_COMPLETE_FG
        else:
            self.background_color = _COLOR_OPEN_BG
            self.color = _COLOR_OPEN_FG


class _TrackerLog(UILog):
    """UILog that collapses hero sections on header tap."""

    def __init__(self, panel: "TrackerPanel", **kwargs):
        super().__init__(**kwargs)
        self.panel = panel
        try:
            self.adaptive_height = False
        except Exception:
            pass
        self.do_scroll_x = False
        self.do_scroll_y = True

    def _row_index_at(self, touch) -> int | None:
        if self.children:
            layout = self.children[0]
            try:
                lx, ly = layout.to_widget(*self.to_window(*touch.pos))
                for child in layout.children:
                    if child.collide_point(lx, ly):
                        index = getattr(child, "index", None)
                        if index is not None:
                            return index
            except Exception:
                pass
        try:
            return self.get_view_index_at(self.to_local(*touch.pos))
        except Exception:
            return None

    def on_touch_down(self, touch):
        if (
            self.collide_point(*touch.pos)
            and not getattr(touch, "is_mouse_scrolling", False)
        ):
            index = self._row_index_at(touch)
            data = getattr(self, "data", None) or []
            if index is not None and 0 <= index < len(data):
                hero = data[index].get("hero_toggle")
                if hero:
                    self.panel._toggle(hero)
                    return True
        return super().on_touch_down(touch)


class TrackerPanel(BoxLayout):
    def __init__(self, ctx, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(orientation="vertical", **kwargs)
        self.ctx = ctx
        self._filter = ALL_UNLOCKED
        self._collapsed: set[str] = set()
        self._syncing_spinner = False
        self._refresh_ev = None
        self._refresh_wanted = False
        self._last_sig: list[tuple] | None = None
        self._complete_heroes: set[str] = set()
        self._heroes_with_checks: set[str] = set()

        self._spinner = Spinner(
            text=ALL_UNLOCKED,
            values=(ALL_UNLOCKED,),
            size_hint_y=None,
            height=dp(40),
            font_size=_BODY_SIZE,
            sync_height=True,
            option_cls=_HeroSpinnerOption,
        )
        self._spinner.bind(text=self._on_filter)

        spinner_wrap = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            padding=[dp(10), dp(8), dp(10), dp(4)],
            spacing=dp(4),
        )
        spinner_wrap.add_widget(self._spinner)

        self._chrome = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(28),
            spacing=dp(10),
        )
        self._collapse_btn = Button(
            text="Collapse all",
            size_hint_x=None,
            width=dp(120),
            font_size=dp(15),
            background_normal="",
            background_down="",
            background_color=(0.32, 0.36, 0.44, 1),
            color=(0.92, 0.93, 0.96, 1),
        )
        self._collapse_btn.bind(on_release=lambda *_: self._collapse_or_expand_all())
        self._hint = Label(
            text="Click a hero name to collapse their checks.",
            size_hint_x=1,
            font_size=dp(16),
            color=(0.78, 0.80, 0.86, 1),
            halign="left",
            valign="middle",
        )
        self._hint.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width, inst.height)))
        self._chrome.add_widget(self._collapse_btn)
        self._chrome.add_widget(self._hint)
        spinner_wrap.add_widget(self._chrome)
        self._spinner_wrap = spinner_wrap
        self.add_widget(spinner_wrap)

        self._log = _TrackerLog(self)
        self._log.size_hint = (1, 1)
        self.add_widget(self._log)
        Clock.schedule_once(self._tune_layout, 0)
        Clock.schedule_once(lambda *_: self.refresh(immediate=True), 0)

    def _tune_layout(self, *_args) -> None:
        if not self._log.children:
            Clock.schedule_once(self._tune_layout, 0)
            return
        layout = self._log.children[0]
        layout.default_size = (None, _ROW_H)
        layout.spacing = dp(2)

    def _on_filter(self, _spinner, value: str) -> None:
        if self._syncing_spinner or value == self._filter:
            return
        self._filter = value
        self._update_chrome()
        self._tint_spinner_face()
        self.refresh(immediate=True)

    def _update_chrome(self) -> None:
        show = self._filter == ALL_UNLOCKED
        self._chrome.opacity = 1 if show else 0
        self._chrome.disabled = not show
        self._chrome.height = dp(28) if show else 0
        self._spinner_wrap.height = dp(72) if show else dp(52)
        if show:
            if self._heroes_with_checks and self._heroes_with_checks <= self._collapsed:
                self._collapse_btn.text = "Expand all"
            else:
                self._collapse_btn.text = "Collapse all"

    def _tint_spinner_face(self) -> None:
        name = self._filter
        self._spinner.background_normal = ""
        self._spinner.background_down = ""
        if name == ALL_UNLOCKED:
            self._spinner.background_color = _COLOR_ALL_BG
            self._spinner.color = _COLOR_ALL_FG
        elif name in self._complete_heroes:
            self._spinner.background_color = _COLOR_COMPLETE_BG
            self._spinner.color = _COLOR_COMPLETE_FG
        else:
            self._spinner.background_color = _COLOR_OPEN_BG
            self._spinner.color = _COLOR_OPEN_FG

    def refresh(self, *, immediate: bool = False) -> None:
        """Rebuild list data. Debounced by default; UI actions pass immediate=True."""
        if immediate:
            if self._refresh_ev is not None:
                self._refresh_ev.cancel()
                self._refresh_ev = None
            self._refresh_wanted = False
            self._rebuild()
            return
        self._refresh_wanted = True
        if self._refresh_ev is not None:
            return
        self._refresh_ev = Clock.schedule_once(self._debounced_rebuild, _REFRESH_DEBOUNCE)

    def _debounced_rebuild(self, *_args) -> None:
        self._refresh_ev = None
        if not self._refresh_wanted:
            return
        self._refresh_wanted = False
        self._rebuild()

    def _rebuild(self) -> None:
        tracker = getattr(self.ctx, "tracker", None)
        scroll_y = self._log.scroll_y

        if not tracker:
            self._complete_heroes = set()
            self._heroes_with_checks = set()
            _HeroSpinnerOption.complete_heroes = set()
            self._apply_rows([{"text": "Connect to a HotS slot to use the tracker.", "height": _ROW_H}])
            self._update_chrome()
            self._tint_spinner_face()
            return
        if not getattr(self.ctx, "tracker_enabled", True):
            self._apply_rows([{"text": "Tracker disabled. Use /hots for status.", "height": _ROW_H}])
            self._update_chrome()
            return

        unlocked = tracker.unlocked_heroes()
        _, by_hero = tracker._collect_open_checks()
        self._complete_heroes = {h for h in unlocked if not (by_hero.get(h) or [])}
        self._heroes_with_checks = {h for h, checks in by_hero.items() if checks}
        _HeroSpinnerOption.complete_heroes = set(self._complete_heroes)

        values = [ALL_UNLOCKED, *unlocked]
        self._syncing_spinner = True
        self._spinner.values = values
        if self._filter not in values:
            self._filter = ALL_UNLOCKED
        self._spinner.text = self._filter
        self._syncing_spinner = False
        self._tint_spinner_face()
        self._update_chrome()

        filter_hero = None if self._filter == ALL_UNLOCKED else self._filter
        rows = self._build_rows(tracker, filter_hero, by_hero)
        self._apply_rows(rows)
        Clock.schedule_once(lambda _dt: setattr(self._log, "scroll_y", scroll_y), 0)

    def _apply_rows(self, rows: list[dict]) -> None:
        sig = [(r.get("text"), r.get("hero_toggle"), r.get("height")) for r in rows]
        if sig == self._last_sig:
            return
        self._last_sig = sig
        self._log.data = rows

    def _row(self, text: str, *, height=None, hero_toggle: str | None = None) -> dict:
        item = {"text": text, "height": height if height is not None else _ROW_H}
        if hero_toggle is not None:
            item["hero_toggle"] = hero_toggle
        return item

    def _build_rows(self, tracker, filter_hero: str | None, by_hero: dict) -> list[dict]:
        rows: list[dict] = []
        sd = getattr(self.ctx, "slot_data", {}) or {}
        cons = getattr(self.ctx, "consumables", None)
        if cons is not None and cons.stim_remaining > 0:
            queued = cons.stim_remaining
            matches = "match" if queued == 1 else "matches"
            rows.append(self._row(
                f"[color=ffd24a]Stimpack active: {queued} boosted {matches} queued[/color]"
            ))

        if filter_hero is None:
            for row in tracker._daily_quest_rows():
                text = row.get("text") or ""
                if text:
                    rows.append(self._row(text))
            pass_check_keys = sd.get("pass_check_keys", [])
            enabled_pass_keys = sd.get("enabled_pass_keys", [])
            if pass_check_keys:
                for pass_key in enabled_pass_keys:
                    if not tracker.can_do_pass_checks(pass_key):
                        continue
                    if not tracker._pass_has_open_checks(pass_key, pass_check_keys):
                        continue
                    rows.append(self._row(f"--- {pass_name_for_key(pass_key)} ---"))
                    hint = pass_contributor_hint(pass_key)
                    if hint:
                        rows.append(self._row(f"  {hint}"))
                    for row in tracker._pass_check_rows(pass_key, pass_check_keys):
                        text = row.get("text") or ""
                        if text:
                            rows.append(self._row(text))
                    rows.append(self._row(""))

        heroes = [filter_hero] if filter_hero else sorted(by_hero)
        shown = False
        cumulative = bool(getattr(self.ctx, "cumulative_checks", False))
        for hero in heroes:
            if not hero:
                continue
            checks = by_hero.get(hero) or []
            if not checks:
                if filter_hero:
                    rows.append(self._row(f"No open checks for {hero}."))
                    shown = True
                continue
            shown = True
            rows.extend(self._hero_rows(tracker, hero, checks, cumulative))

        if not shown:
            rows.append(self._row("No open checks for unlocked heroes."))

        while rows and rows[-1].get("text") == "":
            rows.pop()
        return rows

    def _hero_rows(self, tracker, hero: str, checks: list[str], cumulative: bool) -> list[dict]:
        collapsed = hero in self._collapsed
        n = len(checks)
        count = f"{n} check" if n == 1 else f"{n} checks"
        title = f"{hero}  [{count}]"
        rows = [
            self._row(
                f"[b]{title}[/b]" + ("  …" if collapsed else ""),
                height=_HEAD_H,
                hero_toggle=hero,
            )
        ]
        if collapsed:
            return rows

        totals = getattr(self.ctx, "hero_stat_totals", {}).get(hero, {}) if cumulative else {}
        for name in tracker._sorted_hero_check_names(checks):
            short = name.split(": ", 1)[-1]
            progress = ""
            data = location_table.get(name)
            check_key = data.check_key if data else None
            parsed = parse_talent_check_key(check_key) if check_key else None
            if parsed:
                level, _ = parsed
                short = tracker._talent_label(hero, level)
            if cumulative and check_key and check_key in CHECK_SCORE_THRESHOLDS:
                field, threshold = CHECK_SCORE_THRESHOLDS[check_key]
                cur = int(totals.get(field, 0) or 0)
                progress = f" ({cur:,}/{threshold:,})"
            rows.append(self._row(f"  {short}{progress}"))
        return rows

    def _toggle(self, hero: str) -> None:
        if hero in self._collapsed:
            self._collapsed.discard(hero)
        else:
            self._collapsed.add(hero)
        self._update_chrome()
        self.refresh(immediate=True)

    def _collapse_or_expand_all(self) -> None:
        if not self._heroes_with_checks:
            return
        if self._heroes_with_checks <= self._collapsed:
            self._collapsed -= self._heroes_with_checks
        else:
            self._collapsed |= set(self._heroes_with_checks)
        self._update_chrome()
        self.refresh(immediate=True)
