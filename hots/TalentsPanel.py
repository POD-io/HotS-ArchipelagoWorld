import subprocess

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from .Locations import location_name_to_id
from .Talents import build_share_code, talent_count, talent_location_name, talent_req_is_any

_CELL_W = dp(26)
_CELL_H = dp(14)
_CELL_GAP = dp(3)
_COL_GAP = dp(8)
_COLOR_EMPTY = (0.28, 0.28, 0.32, 1)
_COLOR_PICK = (0.95, 0.72, 0.22, 1)
_COLOR_PICK_DONE = (0.30, 0.78, 0.35, 1)
_COLOR_ANY = (0.40, 0.78, 0.95, 1)
_COLOR_ANY_DONE = (0.30, 0.78, 0.35, 1)
_COLOR_DONE_NAME = (0.35, 0.85, 0.40, 1)
_COPY_FLASH = (0.25, 0.55, 0.35, 1)


def _is_checked(ctx, hero: str, level: int, rank: int) -> bool:
    loc_id = location_name_to_id.get(talent_location_name(hero, level))
    if loc_id is None:
        return False
    return loc_id in ctx.checked_locations


def _copy_clipboard(text: str) -> bool:
    try:
        from kivy.core.clipboard import Clipboard
        Clipboard.copy(text)
        return True
    except Exception:
        pass
    try:
        completed = subprocess.run(
            ["clip"],
            input=text.encode("utf-16"),
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.returncode == 0
    except Exception:
        return False


class _SlotCell(Widget):
    def __init__(self, fill_rgba, width=None, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (width if width is not None else _CELL_W, _CELL_H)
        with self.canvas:
            self._color = Color(*fill_rgba)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(3)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_args) -> None:
        self._rect.pos = self.pos
        self._rect.size = self.size


class _HeroHeader(ButtonBehavior, Label):
    pass


class _TierColumn(ButtonBehavior, BoxLayout):
    def __init__(self, on_tome=None, highlight=False, **kwargs):
        super().__init__(**kwargs)
        self._on_tome = on_tome
        self._glow = None
        self._border = None
        if highlight:
            with self.canvas.before:
                self._glow = Color(1.0, 0.82, 0.28, 0.7)
                self._border = Line(rounded_rectangle=(0, 0, 10, 10, dp(4)), width=1.5)
            self.bind(pos=self._sync_glow, size=self._sync_glow)
            pulse = Animation(a=1.0, d=0.85, t="in_out_sine") + Animation(a=0.35, d=0.85, t="in_out_sine")
            pulse.repeat = True
            pulse.start(self._glow)

    def _sync_glow(self, *_args) -> None:
        if self._border is None:
            return
        pad = dp(1)
        self._border.rounded_rectangle = (
            self.x - pad,
            self.y - pad,
            self.width + pad * 2,
            self.height + pad * 2,
            dp(4),
        )

    def on_release(self):
        if self._on_tome:
            self._on_tome()


class TalentsPanel(ScrollView):
    def __init__(self, ctx, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.do_scroll_x = False
        self.bar_width = dp(10)
        self.scroll_type = ["bars", "content"]
        self.bar_inactive_color = (0.55, 0.55, 0.55, 0.45)
        self.bar_color = (0.75, 0.75, 0.75, 0.75)
        self._collapsed: set[str] = set()
        self._root = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(14),
            padding=[dp(12), dp(12), dp(12), dp(12)],
        )
        self._root.bind(minimum_height=self._root.setter("height"))
        self.add_widget(self._root)
        self.bind(width=self._on_width)
        self.refresh()

    def _on_width(self, _instance, width: float) -> None:
        self._root.width = width

    def refresh(self) -> None:
        scroll_y = self.scroll_y
        self._root.clear_widgets()
        ctx = self.ctx
        sd = getattr(ctx, "slot_data", {}) or {}
        reqs_by_hero = getattr(ctx, "hero_talent_requirements", None) or sd.get(
            "hero_talent_requirements", {}
        )
        if not reqs_by_hero:
            self._root.add_widget(self._hint("No random talent checks in this seed."))
            return

        self._root.add_widget(self._header_block())

        unlocked_fn = getattr(ctx, "_hero_unlocked", None)
        enabled = list(getattr(ctx, "enabled_heroes", []) or [])
        heroes = [
            h for h in enabled
            if reqs_by_hero.get(h) and (unlocked_fn(h) if unlocked_fn else True)
        ]

        def _progress(hero: str) -> tuple[int, int, bool]:
            reqs = reqs_by_hero.get(hero) or []
            total = len(reqs)
            done = sum(
                1 for r in reqs
                if _is_checked(ctx, hero, int(r["level"]), int(r["rank"]))
            )
            complete = total > 0 and done >= total
            return done, total, complete

        heroes.sort(key=lambda h: (_progress(h)[2], h.lower()))
        if not heroes:
            self._root.add_widget(self._hint("No talent-check heroes unlocked yet."))
            Clock.schedule_once(lambda _dt: setattr(self, "scroll_y", scroll_y), 0)
            return

        for hero in heroes:
            self._root.add_widget(self._hero_row(hero, reqs_by_hero[hero]))

        Clock.schedule_once(lambda _dt: setattr(self, "scroll_y", scroll_y), 0)

    def _hint(self, text: str) -> Label:
        label = Label(
            text=text,
            size_hint_y=None,
            height=dp(32),
            halign="left",
            valign="middle",
            color=(0.82, 0.82, 0.86, 1),
            font_size=dp(16),
        )
        label.bind(size=lambda inst, _val: setattr(inst, "text_size", (inst.width, None)))
        return label

    def _header_block(self) -> BoxLayout:
        cons = getattr(self.ctx, "consumables", None)
        tomes = cons.tomes_in_bag if cons is not None else 0
        block = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(8),
        )
        block.bind(minimum_height=block.setter("height"))

        tools = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34))
        tools.add_widget(Widget())
        tools.add_widget(self._export_button())
        block.add_widget(tools)

        legend = Label(
            text="Gold cell = required pick (top to bottom). Click a hero name to collapse.",
            size_hint_y=None,
            height=dp(28),
            halign="left",
            valign="middle",
            color=(0.88, 0.88, 0.92, 1),
            font_size=dp(16),
        )
        legend.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None)),
            texture_size=lambda inst, s: setattr(inst, "height", max(dp(28), s[1])),
        )
        block.add_widget(legend)
        if tomes > 0:
            block.add_widget(self._tome_banner(tomes))
        return block

    def _tome_banner(self, tomes: int) -> BoxLayout:
        wrap = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(64),
            padding=[dp(12), dp(8)],
            spacing=dp(2),
        )
        with wrap.canvas.before:
            Color(0.28, 0.18, 0.04, 1)
            rect = RoundedRectangle(radius=[dp(6)])
            Color(1.0, 0.82, 0.28, 0.9)
            border = Line(rounded_rectangle=(0, 0, 10, 10, dp(6)), width=1.3)

        def _sync(_inst, *_args) -> None:
            rect.pos = wrap.pos
            rect.size = wrap.size
            border.rounded_rectangle = (*wrap.pos, *wrap.size, dp(6))

        wrap.bind(pos=_sync, size=_sync)
        title = Label(
            text=f"{tomes} Talent Tome{'s' if tomes != 1 else ''} ready",
            size_hint_y=None,
            height=dp(26),
            halign="left",
            valign="middle",
            bold=True,
            color=(1.0, 0.86, 0.32, 1),
            font_size=dp(20),
        )
        title.bind(size=lambda inst, _val: setattr(inst, "text_size", (inst.width, inst.height)))
        sub = Label(
            text="Click a glowing gold level number to spend one. That column then accepts any pick.",
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
            color=(1.0, 0.92, 0.72, 1),
            font_size=dp(15),
        )
        sub.bind(size=lambda inst, _val: setattr(inst, "text_size", (inst.width, inst.height)))
        wrap.add_widget(title)
        wrap.add_widget(sub)
        return wrap

    def _export_button(self):
        btn_w, btn_h = dp(148), dp(30)
        label_text = "Write TalentBuilds"
        try:
            from kivymd.uix.button import MDButton, MDButtonText

            label = MDButtonText(text=label_text, font_size=dp(11))
            btn = MDButton(
                label,
                style="filled",
                size_hint=(None, None),
                size=(btn_w, btn_h),
                pos_hint={"center_y": 0.5},
            )
            btn.bind(on_release=lambda *_a, b=btn, t=label: self._confirm_export(b, t))
            return btn
        except Exception:
            from kivy.uix.button import Button

            btn = Button(
                text=label_text,
                size_hint=(None, None),
                size=(btn_w, btn_h),
                pos_hint={"center_y": 0.5},
                font_size=dp(11),
            )
            btn.bind(on_release=lambda *_a, b=btn: self._confirm_export(b, None))
            return btn

    def _confirm_export(self, btn, text_widget) -> None:
        title = "Overwrite TalentBuilds.txt?"
        body = (
            "This will replace your HotS TalentBuilds.txt with this seed's talent requirements.\n\n"
            "Your current TalentBuilds.txt will be copied to a timestamped backup first "
            "(TalentBuilds.bak_YYYYMMDD_HHMMSS.txt).\n\n"
            "Restart HotS to see the talent favorites, or use Copy on the Talents tab "
            "to paste build codes in-game.\n\n"
            "Continue?"
        )

        def on_choice(choice: str) -> None:
            prompt = getattr(self, "_builds_prompt", None)
            if prompt is not None:
                try:
                    prompt.dismiss()
                except Exception:
                    pass
                self._builds_prompt = None
            if choice == "Write TalentBuilds":
                self._do_export(btn, text_widget)

        try:
            from kvui import ButtonsPrompt
            self._builds_prompt = ButtonsPrompt(
                title,
                body,
                on_choice,
                "Cancel",
                "Write TalentBuilds",
            )
            self._builds_prompt.open()
            return
        except Exception:
            pass

        from kivy.uix.boxlayout import BoxLayout as KivyBox
        from kivy.uix.button import Button
        from kivy.uix.label import Label as KivyLabel
        from kivy.uix.popup import Popup

        content = KivyBox(orientation="vertical", spacing=dp(8), padding=dp(10))
        content.add_widget(KivyLabel(text=body, halign="left", valign="top", text_size=(dp(360), None)))
        buttons = KivyBox(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8))

        def close_and(choice: str, *_a) -> None:
            popup.dismiss()
            on_choice(choice)

        buttons.add_widget(Button(text="Cancel", on_release=lambda *_a: close_and("Cancel")))
        buttons.add_widget(
            Button(text="Write TalentBuilds", on_release=lambda *_a: close_and("Write TalentBuilds"))
        )
        content.add_widget(buttons)
        popup = Popup(title=title, content=content, size_hint=(None, None), size=(dp(420), dp(260)))
        self._builds_prompt = popup
        popup.open()

    def _do_export(self, btn, text_widget) -> None:
        export_fn = getattr(self.ctx, "install_talent_builds", None)
        if not callable(export_fn):
            self._flash_export(btn, text_widget, ok=False)
            return
        lines = export_fn()
        ok = bool(lines) and not any(ln.startswith("Failed") for ln in lines)
        if not ok:
            try:
                from CommonClient import logger as ap_logger
                for line in lines:
                    if line.startswith("Failed"):
                        ap_logger.warning(f"[HotS] {line}")
            except Exception:
                pass
        self._flash_export(btn, text_widget, ok=ok)

    def _flash_export(self, btn, text_widget, *, ok: bool) -> None:
        flash = "Done" if ok else "Failed"
        restore = "Write TalentBuilds"
        if text_widget is not None:
            text_widget.text = flash
            Clock.schedule_once(lambda _dt: setattr(text_widget, "text", restore), 1.2)
        else:
            btn.text = flash
            Clock.schedule_once(lambda _dt: setattr(btn, "text", restore), 1.2)

        if not ok:
            return
        color_attr = None
        if hasattr(btn, "md_bg_color"):
            color_attr = "md_bg_color"
        elif hasattr(btn, "background_color"):
            color_attr = "background_color"
        if not color_attr:
            return
        original = list(getattr(btn, color_attr))
        setattr(btn, color_attr, list(_COPY_FLASH))
        anim = Animation(**{color_attr: original}, duration=1.0, t="out_quad")
        anim.start(btn)

    def _toggle_collapse(self, hero: str) -> None:
        if hero in self._collapsed:
            self._collapsed.discard(hero)
        else:
            self._collapsed.add(hero)
        self.refresh()

    def _hero_row(self, hero: str, reqs_raw: list) -> BoxLayout:
        reqs = sorted(reqs_raw or [], key=lambda r: int(r["level"]))
        done_n = sum(
            1 for r in reqs
            if _is_checked(self.ctx, hero, int(r["level"]), int(r["rank"]))
        )
        total_n = len(reqs)
        complete = total_n > 0 and done_n >= total_n

        if complete:
            return self._done_row(hero, done_n, total_n)

        collapsed = hero in self._collapsed
        grid = None if collapsed else self._tier_grid(hero, reqs)
        header_h = dp(32)
        body_h = header_h if collapsed else header_h + dp(6) + (grid.height if grid else 0)

        row = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=body_h,
            spacing=dp(6),
        )
        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=header_h,
            spacing=dp(8),
        )
        name = _HeroHeader(
            text=f"[b]{hero}[/b]  {done_n}/{total_n}",
            markup=True,
            size_hint_x=1,
            size_hint_y=None,
            height=header_h,
            halign="left",
            valign="middle",
            color=(1, 1, 1, 1),
            font_size=dp(18),
        )
        name.bind(size=lambda inst, _val: setattr(inst, "text_size", (inst.width, None)))
        name.bind(on_release=lambda *_a, h=hero: self._toggle_collapse(h))
        header.add_widget(name)
        header.add_widget(self._copy_button(hero, reqs))
        row.add_widget(header)
        if grid is not None:
            row.add_widget(grid)
        return row

    def _done_row(self, hero: str, done_n: int, total_n: int) -> BoxLayout:
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            spacing=dp(8),
        )
        header = Label(
            text=f"[b]{hero}[/b]  done ({done_n}/{total_n})",
            markup=True,
            size_hint_y=None,
            height=dp(36),
            halign="left",
            valign="middle",
            color=_COLOR_DONE_NAME,
            font_size=dp(18),
        )
        header.bind(size=lambda inst, _val: setattr(inst, "text_size", (inst.width, None)))
        row.add_widget(header)
        return row

    def _tier_grid(self, hero: str, reqs: list) -> BoxLayout:
        max_slots = max((talent_count(hero, int(r["level"])) for r in reqs), default=1)
        cons = getattr(self.ctx, "consumables", None)
        cols: list[tuple] = []
        any_tome = False
        for req in reqs:
            level = int(req["level"])
            rank = int(req["rank"])
            total = talent_count(hero, level)
            done = _is_checked(self.ctx, hero, level, rank)
            any_pick = talent_req_is_any(req)
            tome_ok = bool(
                cons is not None
                and not done
                and not any_pick
                and cons.can_unlock_any(hero, level)
            )
            any_tome = any_tome or tome_ok
            cols.append((level, rank, total, done, any_pick, tome_ok))

        label_h = dp(24) if any_tome else dp(18)
        stack_h = max_slots * _CELL_H + max(0, max_slots - 1) * _CELL_GAP
        grid_h = label_h + dp(6) + stack_h

        grid = BoxLayout(
            orientation="horizontal",
            size_hint=(None, None),
            height=grid_h,
            spacing=_COL_GAP,
            padding=[0, 0, 0, 0],
        )
        for level, rank, total, done, any_pick, tome_ok in cols:
            grid.add_widget(self._tier_column(
                hero, level, rank, total, done, any_pick, tome_ok, grid_h, label_h,
            ))
        grid.width = (
            len(cols) * _CELL_W
            + max(0, len(cols) - 1) * _COL_GAP
            + dp(4)
        )
        return grid

    def _tier_column(
        self,
        hero: str,
        level: int,
        rank: int,
        total: int,
        done: bool,
        any_pick: bool,
        tome_ok: bool,
        col_h: float,
        label_h: float,
    ) -> BoxLayout:
        on_tome = (lambda h=hero, lv=level: self._confirm_tome(h, lv)) if tome_ok else None
        col = _TierColumn(
            on_tome=on_tome,
            highlight=tome_ok,
            orientation="vertical",
            size_hint=(None, None),
            width=_CELL_W,
            height=col_h,
            spacing=_CELL_GAP,
        )
        lvl = Label(
            text=str(level),
            size_hint=(None, None),
            size=(_CELL_W, label_h),
            halign="center",
            valign="middle",
            bold=tome_ok,
            color=(1.0, 0.86, 0.28, 1) if tome_ok else (0.70, 0.70, 0.74, 1),
            font_size=dp(16) if tome_ok else dp(13),
        )
        lvl.bind(size=lambda inst, _val: setattr(inst, "text_size", (inst.width, inst.height)))
        col.add_widget(lvl)

        for i in range(1, total + 1):
            if any_pick:
                fill = _COLOR_ANY_DONE if done else _COLOR_ANY
            elif i == rank:
                fill = _COLOR_PICK_DONE if done else _COLOR_PICK
            else:
                fill = _COLOR_EMPTY
            col.add_widget(_SlotCell(fill))

        return col

    def _confirm_tome(self, hero: str, level: int) -> None:
        cons = getattr(self.ctx, "consumables", None)
        if cons is None or not cons.can_unlock_any(hero, level):
            return
        title = "Spend Talent Tome?"
        body = (
            f"Spend 1 Talent Tome so {hero} can take any Level {level} talent?\n\n"
            "Any pick on that tier will count. An already-done tier can't be changed.\n\n"
            f"{cons.tomes_in_bag} tome{'' if cons.tomes_in_bag == 1 else 's'} in bag."
        )

        def on_choice(choice: str) -> None:
            prompt = getattr(self, "_tome_prompt", None)
            if prompt is not None:
                try:
                    prompt.dismiss()
                except Exception:
                    pass
                self._tome_prompt = None
            if choice == "Use Tome":
                cons.drink_talent_tome(hero, level)

        try:
            from kvui import ButtonsPrompt
            self._tome_prompt = ButtonsPrompt(
                title, body, on_choice, "Cancel", "Use Tome",
            )
            self._tome_prompt.open()
            return
        except Exception:
            pass

        from kivy.uix.boxlayout import BoxLayout as KivyBox
        from kivy.uix.button import Button
        from kivy.uix.label import Label as KivyLabel
        from kivy.uix.popup import Popup

        content = KivyBox(orientation="vertical", spacing=dp(8), padding=dp(10))
        content.add_widget(KivyLabel(text=body, halign="left", valign="top", text_size=(dp(360), None)))
        buttons = KivyBox(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8))

        def close_and(choice: str, *_a) -> None:
            popup.dismiss()
            on_choice(choice)

        buttons.add_widget(Button(text="Cancel", on_release=lambda *_a: close_and("Cancel")))
        buttons.add_widget(Button(text="Use Tome", on_release=lambda *_a: close_and("Use Tome")))
        content.add_widget(buttons)
        popup = Popup(title=title, content=content, size_hint=(None, None), size=(dp(420), dp(280)))
        self._tome_prompt = popup
        popup.open()

    def _copy_button(self, hero: str, reqs: list):
        from kivy.uix.button import Button

        btn = Button(
            text="Copy",
            size_hint=(None, None),
            size=(dp(64), dp(28)),
            font_size=dp(12),
            pos_hint={"center_y": 0.5},
        )
        btn.bind(on_release=lambda *_a, h=hero, r=reqs, b=btn: self._on_copy(h, r, b, None))
        return btn

    def _on_copy(self, hero: str, reqs: list, btn, text_widget) -> None:
        code = build_share_code(hero, reqs)
        ok = _copy_clipboard(code)
        self._flash_copy(btn, text_widget, ok=ok)

    def _flash_copy(self, btn, text_widget, *, ok: bool) -> None:
        flash = "Copied" if ok else "Failed"
        if text_widget is not None:
            text_widget.text = flash
            Clock.schedule_once(lambda _dt: setattr(text_widget, "text", "Copy"), 0.9)
        else:
            btn.text = flash
            Clock.schedule_once(lambda _dt: setattr(btn, "text", "Copy"), 0.9)

        if not ok:
            return
        color_attr = None
        if hasattr(btn, "md_bg_color"):
            color_attr = "md_bg_color"
        elif hasattr(btn, "background_color"):
            color_attr = "background_color"
        if not color_attr:
            return
        original = list(getattr(btn, color_attr))
        setattr(btn, color_attr, list(_COPY_FLASH))
        anim = Animation(**{color_attr: original}, duration=0.85, t="out_quad")
        anim.start(btn)
