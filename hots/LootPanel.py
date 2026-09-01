"""Loot tab"""

from typing import Callable

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Line, PushMatrix, PopMatrix, Translate, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

from .Items import CHEST_COST_XP, CHEST_SLOTS, is_loot_legendary_item

_SLOT_SIZE = dp(126)
_SLOT_GAP = dp(14)
_OWNER_H = dp(22)
_COL_H = _SLOT_SIZE + _OWNER_H + dp(4)
_SLOT_TOP_PAD = dp(52)
_LAND_FROM_Y = dp(44)
_LAND_STAGGER = 0.18
_LAND_START_DELAY = 0.12

_COLOR_LOCKED = (0.22, 0.22, 0.26, 1)
_COLOR_REVEALED_BG = (0.06, 0.07, 0.09, 1)

_HOTS_COMMON = (0.95, 0.95, 0.97, 1)       # white
_HOTS_USEFUL = (0.28, 0.58, 0.98, 1)       # blue
_HOTS_EPIC = (0.72, 0.42, 0.95, 1)         # purple (normal progression)
_HOTS_LEGENDARY = (1.0, 0.82, 0.12, 1)     # gold (full hero / role pass) - local only
_HOTS_TRAP = (0.90, 0.20, 0.20, 1)

_AP_TEXT = {
    "trap": "FF4040",
    "legendary": "FFD24A",
    "progression": "AF99EF",
    "useful": "6D8BE8",
    "filler": "00EEEE",
}

_TEXT_BRIGHT = (1.0, 1.0, 1.0, 1.0)


def _tier_for(name: str | None, flags: int) -> str:
    if name and is_loot_legendary_item(name):
        return "legendary"
    if flags & 0b1000:
        return "trap"
    if flags & 0b001:
        return "epic"
    if flags & 0b010:
        return "useful"
    if flags:
        return "common"
    return "locked"


def _slot_color(tier: str) -> tuple:
    return {
        "legendary": _HOTS_LEGENDARY,
        "epic": _HOTS_EPIC,
        "useful": _HOTS_USEFUL,
        "common": _HOTS_COMMON,
        "trap": _HOTS_TRAP,
        "locked": _COLOR_LOCKED,
    }.get(tier, _COLOR_LOCKED)


def _feed_hex(name: str, flags: int) -> str:
    tier = _tier_for(name, flags)
    if tier == "legendary":
        return _AP_TEXT["legendary"]
    if tier == "trap":
        return _AP_TEXT["trap"]
    if tier == "epic":
        return _AP_TEXT["progression"]
    if tier == "useful":
        return _AP_TEXT["useful"]
    return _AP_TEXT["filler"]


class _GlowSlot(ButtonBehavior, Widget):
    offset_x = NumericProperty(0)
    offset_y = NumericProperty(0)

    def __init__(self, slot_index: int, on_click: Callable[[int], None], **kwargs):
        super().__init__(**kwargs)
        self.slot_index = slot_index
        self._on_click = on_click
        self.size_hint = (None, None)
        self.size = (_SLOT_SIZE, _SLOT_SIZE)
        self._base_size = (_SLOT_SIZE, _SLOT_SIZE)
        self._rgba = _COLOR_LOCKED
        self._clickable = False
        self._face_key = None
        self._label = Label(
            text="·",
            font_size=dp(20),
            bold=True,
            color=_TEXT_BRIGHT,
            halign="center",
            valign="middle",
            text_size=(self.size[0] - dp(8), self.size[1] - dp(8)),
            size_hint=(None, None),
            size=self.size,
            disabled_color=_TEXT_BRIGHT,
        )
        self.add_widget(self._label)
        with self.canvas.before:
            PushMatrix()
            self._translate = Translate(0, 0)
            self._color = Color(*self._rgba)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
            self._line_color = Color(1, 1, 1, 0.35)
            self._border = Line(rounded_rectangle=(0, 0, 10, 10, dp(12)), width=1.6)
            PopMatrix()
        self.bind(pos=self._sync, size=self._sync, offset_x=self._sync, offset_y=self._sync)

    def _sync(self, *_args) -> None:
        self._translate.x = self.offset_x
        self._translate.y = self.offset_y
        self._rect.pos = self.pos
        self._rect.size = self.size
        pad = dp(10)
        lw, lh = self._base_size
        self._label.size = (lw, lh)
        self._label.pos = (
            self.pos[0] + self.offset_x + (self.size[0] - lw) / 2,
            self.pos[1] + self.offset_y + (self.size[1] - lh) / 2,
        )
        self._label.text_size = (max(1, lw - pad * 2), max(1, lh - pad * 2))
        self._border.rounded_rectangle = (*self.pos, *self.size, dp(12))

    def set_face(
        self,
        *,
        revealed: bool,
        name: str | None,
        flags: int,
        clickable: bool,
    ) -> None:
        face_key = (revealed, name, flags, clickable)
        if face_key == self._face_key:
            return
        self._face_key = face_key
        tier = _tier_for(name, flags) if (name or flags) else "locked"
        if not name and flags and not revealed:
            tier = _tier_for(None, flags)
        glow = _slot_color(tier)
        if revealed and name:
            self._rgba = _COLOR_REVEALED_BG
            safe = (
                str(name)
                .replace("&", "&amp;")
                .replace("[", "&bl;")
                .replace("]", "&br;")
            )
            self._label.markup = True
            self._label.text = f"[color=FFFFFFFF]{safe}[/color]"
            self._label.font_size = dp(17)
            self._label.bold = True
            self._label.color = _TEXT_BRIGHT
            self._label.disabled_color = _TEXT_BRIGHT
            self._line_color.rgba = (*glow[:3], 1.0)
            self._fit_label_text()
        else:
            self._rgba = glow if tier != "locked" else _COLOR_LOCKED
            self._label.markup = False
            self._label.text = "?" if (clickable or flags or name) else "·"
            self._label.font_size = dp(28)
            self._label.bold = True
            if tier == "common":
                self._label.color = (0.12, 0.12, 0.14, 1)
            else:
                self._label.color = _TEXT_BRIGHT
            self._line_color.rgba = (1, 1, 1, 0.55 if clickable else 0.25)
        self._color.rgba = self._rgba
        self._clickable = clickable
        self.disabled = False

    def _fit_label_text(self) -> None:
        pad = dp(10)
        max_w = max(1, self._base_size[0] - pad * 2)
        max_h = max(1, self._base_size[1] - pad * 2)
        self._label.text_size = (max_w, None)
        self._label.texture_update()
        size = dp(17)
        min_size = dp(11)
        while size > min_size and self._label.texture_size[1] > max_h:
            size -= dp(1)
            self._label.font_size = size
            self._label.texture_update()
        self._label.text_size = (max_w, max_h)
        self._label.font_size = size
        self._label.color = _TEXT_BRIGHT
        self._label.disabled_color = _TEXT_BRIGHT

    def pulse(self) -> None:
        w, h = self._base_size
        self.size = (w * 0.78, h * 0.78)
        anim = Animation(size=(w * 1.12, h * 1.12), d=0.14, t="out_quad")
        anim += Animation(size=(w, h), d=0.22, t="out_back")
        anim.start(self)

    def land_in(self, delay: float, *, from_center_x: float) -> None:
        w, h = self._base_size
        self.opacity = 0
        self.size = (w * 0.25, h * 0.25)
        self.offset_x = from_center_x
        self.offset_y = _LAND_FROM_Y
        anim = Animation(
            opacity=1,
            size=(w * 1.08, h * 1.08),
            offset_x=0,
            offset_y=0,
            d=0.38,
            t="out_bounce",
        )
        anim += Animation(size=(w, h), d=0.12, t="out_quad")
        Clock.schedule_once(lambda *_: anim.start(self), delay)

    def on_press(self) -> None:
        if self._clickable:
            self._on_click(self.slot_index)


class LootPanel(FloatLayout):
    def __init__(self, ctx, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx

        self._status = Label(text="Connect to a HotS slot to use Loot.", size_hint_y=None, height=dp(26))
        self._counts = Label(text="", size_hint_y=None, height=dp(24))
        self._stim_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=0, spacing=dp(8), opacity=0)
        self._stim_label = Label(text="", size_hint_x=0.7, halign="left", valign="middle")
        self._stim_label.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width, inst.height)))
        self._stim_btn = Button(text="Use Stimpack", size_hint_x=0.3, disabled=True)
        self._stim_btn.bind(on_press=lambda *_: self._drink_stim())
        self._stim_row.add_widget(self._stim_label)
        self._stim_row.add_widget(self._stim_btn)
        self._buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
        self._buy_btn = Button(text="Buy Chest (1000 XP)", size_hint_x=0.5)
        self._open_btn = Button(text="Open Owned Chest", size_hint_x=0.5)
        self._buy_btn.bind(on_press=lambda *_: self._buy())
        self._open_btn.bind(on_press=lambda *_: self._open())
        self._buttons.add_widget(self._buy_btn)
        self._buttons.add_widget(self._open_btn)

        row_w = CHEST_SLOTS * _SLOT_SIZE + (CHEST_SLOTS - 1) * _SLOT_GAP
        self._slots_anchor = AnchorLayout(
            anchor_x="center",
            anchor_y="bottom",
            size_hint_y=None,
            height=0,
            opacity=0,
            disabled=True,
        )
        self._slots_row = BoxLayout(
            orientation="horizontal",
            size_hint=(None, None),
            size=(row_w, _COL_H),
            spacing=_SLOT_GAP,
        )
        self._slots: list[_GlowSlot] = []
        self._slot_cols: list[BoxLayout] = []
        self._owner_labels: list[Label] = []
        for i in range(CHEST_SLOTS):
            col = BoxLayout(
                orientation="vertical",
                size_hint=(None, None),
                size=(_SLOT_SIZE, _COL_H),
                spacing=dp(2),
            )
            slot = _GlowSlot(i, self._reveal_slot)
            owner = Label(
                text="",
                size_hint=(1, None),
                height=_OWNER_H,
                font_size=dp(12),
                bold=True,
                halign="center",
                valign="middle",
                color=(0.85, 0.88, 0.95, 1),
                shorten=True,
                shorten_from="right",
            )
            owner.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width, inst.height)))
            col.add_widget(slot)
            col.add_widget(owner)
            self._slots.append(slot)
            self._slot_cols.append(col)
            self._owner_labels.append(owner)
            self._slots_row.add_widget(col)
        self._slots_anchor.add_widget(self._slots_row)
        self._slot_clip = ScrollView(
            size_hint=(1, None),
            height=0,
            do_scroll_x=False,
            do_scroll_y=False,
            bar_width=0,
            scroll_timeout=0,
            scroll_type=["bars"],
        )
        self._slot_clip.bind(width=lambda _i, w: setattr(self._slots_anchor, "width", w))
        self._slot_clip.add_widget(self._slots_anchor)

        self._feed_title = Label(
            text="Recent rewards",
            size_hint_y=None,
            height=dp(22),
            color=(0.75, 0.78, 0.85, 1),
        )
        self._feed = Label(
            text="",
            markup=True,
            size_hint_y=None,
            font_size=dp(22),
            halign="left",
            valign="top",
            color=(0.92, 0.93, 0.96, 1),
        )
        self._feed.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None)),
            texture_size=lambda inst, ts: setattr(inst, "height", max(ts[1], 1)),
        )
        self._feed_scroll = ScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            bar_width=dp(10),
            scroll_timeout=0,
            scroll_type=["bars", "content"],
        )
        self._feed_scroll.bind(width=lambda _i, w: setattr(self._feed, "width", w))
        self._feed_scroll.add_widget(self._feed)

        self._header = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=(0, 0, 0, dp(10)),
            size_hint_y=None,
        )
        self._header.bind(minimum_height=self._header.setter("height"))
        self._header.add_widget(self._status)
        self._header.add_widget(self._counts)
        self._header.add_widget(self._stim_row)
        self._header.add_widget(self._buttons)

        self._chrome = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=dp(16),
        )
        self._chrome.add_widget(self._header)
        self._chrome.add_widget(self._slot_clip)
        self._chrome.add_widget(self._feed_title)
        self._chrome.add_widget(self._feed_scroll)
        self.add_widget(self._chrome)

        muted = bool(getattr(ctx, "cfg", {}).get("loot_sounds_muted", False))
        self._mute_btn = ToggleButton(
            text="Muted" if muted else "Sound on",
            state="down" if muted else "normal",
            size_hint=(None, None),
            size=(dp(78), dp(28)),
            pos_hint={"right": 0.98, "top": 0.98},
            font_size=dp(11),
        )
        self._mute_btn.bind(on_press=self._toggle_mute)
        self.add_widget(self._mute_btn)

        self._land_chest: int | None = None
        self._sting_played = False
        Clock.schedule_interval(lambda *_: self.refresh(), 0.5)

    def _toggle_mute(self, *_args) -> None:
        muted = self._mute_btn.state == "down"
        self._mute_btn.text = "Muted" if muted else "Sound on"
        if hasattr(self.ctx, "set_loot_sounds_muted"):
            self.ctx.set_loot_sounds_muted(muted)

    def _set_slots_visible(self, visible: bool) -> None:
        height = _COL_H + _SLOT_TOP_PAD if visible else 0
        self._slot_clip.height = height
        self._slots_anchor.height = height
        self._slots_anchor.opacity = 1 if visible else 0
        self._slots_anchor.disabled = not visible
        for slot in self._slots:
            if not visible:
                slot._clickable = False

    def refresh(self) -> None:
        ctx = self.ctx
        if not getattr(ctx, "_connected", False):
            self._status.text = "Connect to a HotS slot to use Loot."
            self._stim_row.height = 0
            self._stim_row.opacity = 0
            return
        loot = getattr(ctx, "loot", None)
        if loot is None:
            self._status.text = "Loot system not ready."
            self._stim_row.height = 0
            self._stim_row.opacity = 0
            return

        total = int(getattr(ctx, "loot_chest_count", 0) or 0)
        cost = int(getattr(ctx, "chest_cost_xp", CHEST_COST_XP) or CHEST_COST_XP)
        bank = loot.bank_xp
        owned = loot.owned_chests
        acquired = loot.purchased_chests + loot.free_loot_chests
        spent = loot.purchased_chests * cost
        active = loot.active_chest
        fully = loot.chest_fully_revealed(active)

        if spent > 0:
            self._status.text = f"Banked XP: {bank:,}   (received {loot.received_xp:,} − spent {spent:,})"
        else:
            self._status.text = f"Banked XP: {bank:,}"
        self._counts.text = f"Owned: {owned}   |   Chests: {acquired}/{total}   |   Buy: {cost:,} XP"

        cons = getattr(ctx, "consumables", None)
        sd = getattr(ctx, "slot_data", {}) or {}
        show_stim = bool(
            (cons and (cons.received_stim or cons.stim_remaining))
            or sd.get("stimpack_count")
        )
        if cons is not None and show_stim:
            self._stim_row.height = dp(42)
            self._stim_row.opacity = 1
            bag = cons.stim_in_bag
            queued = cons.stim_remaining
            self._stim_label.text = (
                f"Stimpack  |  Bag: {bag}  |  Boosted matches queued: {queued}"
            )
            self._stim_label.color = (1.0, 0.82, 0.12, 1) if queued else (0.92, 0.93, 0.96, 1)
            self._stim_btn.disabled = bag < 1
        else:
            self._stim_row.height = 0
            self._stim_row.opacity = 0
            self._stim_btn.disabled = True

        in_pipeline = loot._pipeline_count()
        self._buy_btn.disabled = not (bank >= cost and in_pipeline < total)
        self._open_btn.disabled = not loot.can_begin_open()

        recent = loot.recent_rewards[: CHEST_SLOTS * 2]
        if recent:
            lines = []
            for entry in recent:
                name = entry.get("name", "?")
                flags = int(entry.get("flags", 0) or 0)
                hex_color = _feed_hex(name, flags)
                safe = (
                    str(name)
                    .replace("&", "&amp;")
                    .replace("[", "&bl;")
                    .replace("]", "&br;")
                )
                lines.append(f"• [color={hex_color}]{safe}[/color]")
            self._feed.text = "\n".join(lines)
        else:
            self._feed.text = ""

        if active is None:
            self._set_slots_visible(False)
            return

        self._set_slots_visible(True)
        self._maybe_legendary_sting(active)
        revealed = loot.revealed_for(active)
        for i, slot in enumerate(self._slots):
            key = f"{active}:{i}"
            name = loot.pending_names.get(key) or loot.revealed_names.get(key)
            flags = loot.pending_flags.get(key, 0)
            owner = loot.pending_owners.get(key, "")
            owner_lbl = self._owner_labels[i]
            if owner:
                if owner == "You":
                    owner_lbl.color = (0.75, 0.78, 0.85, 1)
                    owner_lbl.text = "You"
                else:
                    owner_lbl.color = (1.0, 0.78, 0.35, 1)
                    owner_lbl.text = owner
            else:
                owner_lbl.text = ""
            if i in revealed:
                shown = loot.revealed_names.get(key)
                if shown in ("(claimed)", "(already claimed)"):
                    shown = None
                slot.set_face(
                    revealed=True,
                    name=shown or "…",
                    flags=flags,
                    clickable=False,
                )
            else:
                slot.set_face(
                    revealed=False,
                    name=name,
                    flags=flags,
                    clickable=not fully,
                )

    def _buy(self) -> None:
        loot = getattr(self.ctx, "loot", None)
        if loot and loot.buy_chest():
            if hasattr(self.ctx, "play_loot_sound"):
                self.ctx.play_loot_sound("buy")
            self.refresh()

    def _drink_stim(self) -> None:
        cons = getattr(self.ctx, "consumables", None)
        if cons and cons.drink_stimpack():
            self.refresh()

    def _open(self) -> None:
        loot = getattr(self.ctx, "loot", None)
        if not loot or not loot.begin_open():
            return
        self._set_slots_visible(True)
        for col, slot in zip(self._slot_cols, self._slots):
            col.opacity = 0
            slot.opacity = 0
            slot.offset_x = 0
            slot.offset_y = 0
            slot._face_key = None
        self._land_chest = loot.active_chest
        self._sting_played = False
        self._start_land_animation(loot.active_chest)
        if hasattr(self.ctx, "play_loot_sound"):
            self.ctx.play_loot_sound("open")

    def _maybe_legendary_sting(self, chest: int | None) -> None:
        if self._sting_played or chest is None or chest != self._land_chest:
            return
        loot = getattr(self.ctx, "loot", None)
        if not loot or not hasattr(self.ctx, "play_loot_sound"):
            return
        if not any(
            is_loot_legendary_item(loot.pending_names.get(f"{chest}:{i}", ""))
            for i in range(CHEST_SLOTS)
        ):
            return
        self._sting_played = True
        last_land = _LAND_START_DELAY + (CHEST_SLOTS - 1) * _LAND_STAGGER
        Clock.schedule_once(
            lambda *_: self.ctx.play_loot_sound("legendary_sting"),
            last_land + 0.22,
        )

    def _start_land_animation(self, chest: int) -> None:
        self.refresh()
        mid = (CHEST_SLOTS - 1) / 2.0
        for i, slot in enumerate(self._slots):
            delay = _LAND_START_DELAY + i * _LAND_STAGGER
            from_x = (mid - i) * (_SLOT_SIZE + _SLOT_GAP) * 0.55
            col = self._slot_cols[i]
            col.opacity = 0
            Clock.schedule_once(
                lambda _dt, c=col: Animation(opacity=1, d=0.35, t="out_quad").start(c),
                delay,
            )
            slot.land_in(delay, from_center_x=from_x)

            def _land_sfx(_dt, idx=i):
                if hasattr(self.ctx, "play_loot_sound"):
                    self.ctx.play_loot_sound("land", index=idx)

            Clock.schedule_once(_land_sfx, delay)

        self._maybe_legendary_sting(chest)
        last_land = _LAND_START_DELAY + (CHEST_SLOTS - 1) * _LAND_STAGGER
        Clock.schedule_once(lambda *_: self.refresh(), last_land + 0.5)

    def _reveal_slot(self, slot_index: int) -> None:
        loot = getattr(self.ctx, "loot", None)
        if not loot:
            return
        result = loot.reveal_slot(slot_index)
        if not result:
            return
        name, flags = result
        if hasattr(self.ctx, "play_loot_sound"):
            self.ctx.play_loot_sound("reveal", flags, item_name=name)
        self.refresh()
        self._slots[slot_index].pulse()
