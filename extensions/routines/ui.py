# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Routines UI — an iOS-Shortcuts-style builder (Manage list + Routine editor +
# item editor). It approximates the Shortcuts look with a vertical STACK of
# grouped "blocks" (native wx.StaticBox cards) for the "When…" conditions and the
# "Then do…" actions, each block carrying a human summary plus per-block
# Edit / Remove / Move Up / Move Down controls.
#
# Accessibility is the top priority (blind / low-vision users on the NVDA screen
# reader, keyboard only). The whole builder is standard, native wx controls:
#   * Every block is a native group box whose LABEL is the item's summary, so
#     NVDA announces "Action 1: Speak text -> Hello, grouping" when you tab into
#     it — that grouping name gives each Edit/Remove/Move button its context.
#   * Every button/field is Tab-reachable in a logical order, has a readable text
#     label, and activates with Enter/Space. Main buttons carry & accelerators.
#   * Focus is placed on the first meaningful control of each window, and moved
#     sensibly after add/remove/move so the reader never gets lost.
#   * ESC closes every dialog (each has a Cancel/Close button).
#   * core.ui_scale.apply_appearance() is (re-)applied so the user's font-scale /
#     high-contrast settings reach every control, including ones built on the fly.
# The only "visual" flourish is a soft background tint per section, and it is
# applied AFTER apply_appearance and skipped entirely in high-contrast mode, so
# it never fights the low-vision colour scheme.
#
# SPEC-DRIVEN: type pickers and per-type parameter fields are built from
# engine.CONDITION_LABELS / ACTION_LABELS and engine.COND_SPECS / ACTION_SPECS,
# so condition/action types added elsewhere appear here automatically.
# Public entry point: open_manage_dialog().
import uuid

import wx

import core.api
from core.speech import speak

import engine
import runtime

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Soft per-section tints (RGB). Built lazily into wx.Colour so importing this
# module never constructs a wx object. Applied only when high-contrast is OFF.
_TINT_WHEN = (230, 240, 252)   # conditions block — soft blue
_TINT_DO = (231, 247, 236)     # actions block   — soft green
_TINT_SETTINGS = (245, 246, 250)  # item-editor settings — very light grey


# --------------------------------------------------------------------------- #
# Appearance helpers
# --------------------------------------------------------------------------- #
def _is_high_contrast():
    try:
        import core.ui_scale
        return bool(core.ui_scale.is_high_contrast())
    except Exception:
        return False


def _apply_scale(window):
    """Apply the user's font-scale / high-contrast theme to `window` and every
    descendant. Idempotent, so it is safe to call again after building new
    controls on the fly."""
    try:
        import core.ui_scale
        core.ui_scale.apply_appearance(window)
    except Exception:
        pass


def _tint(window, rgb):
    """Give `window` a soft background tint — but only when high-contrast is off,
    so the low-vision colour scheme always wins. No-op on failure."""
    if window is None or _is_high_contrast():
        return
    try:
        window.SetBackgroundColour(wx.Colour(*rgb))
        window.Refresh()
    except Exception:
        pass


def _bold(window):
    try:
        f = window.GetFont()
        if f and f.IsOk():
            window.SetFont(f.Bold())
    except Exception:
        pass


def _finish_appearance(dialog):
    """Call at the end of a dialog's __init__: apply the low-vision appearance,
    then (re)apply any section tints on top of it."""
    _apply_scale(dialog)
    fn = getattr(dialog, "_apply_tints", None)
    if fn:
        try:
            fn()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Human-readable summary of a condition/action (spec-driven)
# --------------------------------------------------------------------------- #
def _summarize(item, kind):
    """Build a short, screen-reader-friendly summary like
    'Speak text -> Good morning' straight from the spec, so new types summarise
    themselves without special-casing."""
    labels = dict(engine.CONDITION_LABELS if kind == "condition" else engine.ACTION_LABELS)
    specs = engine.COND_SPECS if kind == "condition" else engine.ACTION_SPECS
    t = item.get("type", "?")
    p = item.get("params", {}) or {}
    label = labels.get(t, t)

    parts = []
    for key, _flabel, fkind in specs.get(t, []):
        val = p.get(key)
        if fkind == "days":
            val = ", ".join(_WEEKDAYS[d] for d in (val or []) if 0 <= d < 7)
        elif fkind == "bool":
            if val is None:
                continue
            val = "yes" if val else "no"
        if val in (None, "", []):
            continue
        parts.append(str(val))
    detail = ", ".join(parts)
    return label + (" → " + detail if detail else "")


# --------------------------------------------------------------------------- #
# Mon–Sun multi-checkbox picker (a labelled group box for NVDA)
# --------------------------------------------------------------------------- #
class _DaysPicker(wx.Panel):
    def __init__(self, parent, selected, label="Days"):
        super().__init__(parent)
        box = wx.StaticBox(self, label=label)
        inner = wx.StaticBoxSizer(box, wx.HORIZONTAL)
        self.checks = []
        selected = set(selected or [])
        for i, name in enumerate(_WEEKDAYS):
            c = wx.CheckBox(box, label=name)
            c.SetValue(i in selected)
            self.checks.append(c)
            inner.Add(c, 0, wx.ALL, 4)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(inner, 1, wx.EXPAND)
        self.SetSizer(outer)

    def get_days(self):
        return [i for i, c in enumerate(self.checks) if c.GetValue()]


# --------------------------------------------------------------------------- #
# Item editor: pick a type, then fill its parameters (spec-driven)
# --------------------------------------------------------------------------- #
class ItemDialog(wx.Dialog):
    """Pick a condition/action type and fill its parameters. This is the
    Shortcuts-style 'choose an action, then configure it' sheet."""
    def __init__(self, parent, kind, existing=None):
        noun = "Condition" if kind == "condition" else "Action"
        verb = "Edit" if existing else "Add"
        super().__init__(parent, title=f"{verb} {noun}", size=(440, 400),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.kind = kind
        self.labels = engine.CONDITION_LABELS if kind == "condition" else engine.ACTION_LABELS
        self.specs = engine.COND_SPECS if kind == "condition" else engine.ACTION_SPECS
        self._types = [t for t, _ in self.labels]
        self._existing = existing or {}
        self._field_ctrls = {}

        v = wx.BoxSizer(wx.VERTICAL)
        hint = wx.StaticText(self, label="Choose a type, then fill in its settings.")
        v.Add(hint, 0, wx.ALL, 10)

        v.Add(wx.StaticText(self, label="&Type:"), 0, wx.LEFT | wx.TOP, 10)
        self.choice = wx.Choice(self, choices=[lbl for _, lbl in self.labels])
        self.choice.SetName("Type")
        start = self._existing.get("type", self._types[0] if self._types else None)
        self.choice.SetSelection(self._types.index(start) if start in self._types else 0)
        self.choice.Bind(wx.EVT_CHOICE, lambda e: self._rebuild_fields(reapply=True))
        v.Add(self.choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self._settings_box = wx.StaticBox(self, label="Settings")
        _bold(self._settings_box)
        sbs = wx.StaticBoxSizer(self._settings_box, wx.VERTICAL)
        self.field_panel = wx.Panel(self._settings_box)
        self.field_sizer = wx.BoxSizer(wx.VERTICAL)
        self.field_panel.SetSizer(self.field_sizer)
        sbs.Add(self.field_panel, 1, wx.EXPAND | wx.ALL, 4)
        v.Add(sbs, 1, wx.EXPAND | wx.ALL, 10)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        v.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(v)

        self._rebuild_fields()
        _finish_appearance(self)
        self.choice.SetFocus()

    def _apply_tints(self):
        _tint(self.field_panel, _TINT_SETTINGS)

    def _rebuild_fields(self, reapply=False):
        self.field_sizer.Clear(delete_windows=True)
        self._field_ctrls = {}
        if not self._types:
            self.field_panel.Layout()
            return
        cur_type = self._types[self.choice.GetSelection()]
        params = self._existing.get("params", {}) if self._existing.get("type") == cur_type else {}
        spec = self.specs.get(cur_type, [])
        if not spec:
            self.field_sizer.Add(
                wx.StaticText(self.field_panel, label="(no settings for this type)"),
                0, wx.ALL, 6)
        for key, label, fkind in spec:
            if fkind == "bool":
                ctrl = wx.CheckBox(self.field_panel, label=label)
                ctrl.SetValue(bool(params.get(key, True)))
                self.field_sizer.Add(ctrl, 0, wx.TOP, 8)
            elif fkind == "days":
                ctrl = _DaysPicker(self.field_panel, params.get(key, []), label=label)
                self.field_sizer.Add(ctrl, 0, wx.EXPAND | wx.TOP, 8)
            elif fkind == "int":
                self.field_sizer.Add(wx.StaticText(self.field_panel, label=label + ":"),
                                     0, wx.TOP, 8)
                ctrl = wx.SpinCtrl(self.field_panel, min=0, max=100000,
                                   initial=int(params.get(key, 0) or 0))
                ctrl.SetName(label)
                self.field_sizer.Add(ctrl, 0, wx.TOP, 2)
            else:
                self.field_sizer.Add(wx.StaticText(self.field_panel, label=label + ":"),
                                     0, wx.TOP, 8)
                ctrl = wx.TextCtrl(self.field_panel, value=str(params.get(key, "")))
                ctrl.SetName(label)
                self.field_sizer.Add(ctrl, 0, wx.EXPAND | wx.TOP, 2)
            self._field_ctrls[key] = (ctrl, fkind)
        self.field_panel.Layout()
        if reapply:
            # New controls were just built — re-apply scale/theme + tint to them
            # and move focus into the settings so NVDA follows the type change.
            _apply_scale(self.field_panel)
            self._apply_tints()
            for _key, (ctrl, _k) in self._field_ctrls.items():
                try:
                    ctrl.SetFocus()
                except Exception:
                    pass
                break

    def get_item(self):
        cur_type = self._types[self.choice.GetSelection()] if self._types else None
        params = {}
        for key, (ctrl, fkind) in self._field_ctrls.items():
            if fkind == "days":
                params[key] = ctrl.get_days()
            else:
                params[key] = ctrl.GetValue()
        return {"type": cur_type, "params": params}


# --------------------------------------------------------------------------- #
# Routine editor: When-block + Do-block, each a vertical stack of item cards
# --------------------------------------------------------------------------- #
class RoutineEditDialog(wx.Dialog):
    def __init__(self, parent, routine=None):
        super().__init__(parent, title="Edit Routine", size=(600, 640),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.routine = routine or {"id": str(uuid.uuid4()), "name": "", "enabled": True,
                                   "conditions": [], "actions": []}
        self.conditions = list(self.routine.get("conditions", []))
        self.actions = list(self.routine.get("actions", []))
        self._btn_refs = {"condition": [], "action": []}

        root = wx.BoxSizer(wx.VERTICAL)

        # --- Name + Enabled row ---
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(wx.StaticText(self, label="&Name:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.txt_name = wx.TextCtrl(self, value=self.routine.get("name", ""))
        self.txt_name.SetName("Routine name")
        top.Add(self.txt_name, 1, wx.ALIGN_CENTER_VERTICAL)
        self.chk_enabled = wx.CheckBox(self, label="Ena&bled")
        self.chk_enabled.SetValue(bool(self.routine.get("enabled", True)))
        top.Add(self.chk_enabled, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        root.Add(top, 0, wx.EXPAND | wx.ALL, 10)

        # --- When-block (conditions) ---
        root.Add(self._build_section("condition",
                                     "When ALL of these are true",
                                     "&Add condition…"),
                 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # --- Do-block (actions, in order) ---
        root.Add(self._build_section("action",
                                     "Then do (in order)",
                                     "A&dd action…"),
                 1, wx.EXPAND | wx.ALL, 10)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        root.Add(btns, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizer(root)
        self.SetMinSize((460, 440))

        self._rebuild("condition")
        self._rebuild("action")
        _finish_appearance(self)
        self.txt_name.SetFocus()

    # -- section scaffolding ------------------------------------------------- #
    def _build_section(self, kind, header, add_label):
        box = wx.StaticBox(self, label=header)
        _bold(box)
        sbs = wx.StaticBoxSizer(box, wx.VERTICAL)

        scr = wx.ScrolledWindow(box, style=wx.VSCROLL)
        scr.SetScrollRate(0, 14)
        scr.SetSizer(wx.BoxSizer(wx.VERTICAL))
        sbs.Add(scr, 1, wx.EXPAND | wx.ALL, 4)

        add = wx.Button(box, label=add_label)
        add.Bind(wx.EVT_BUTTON, lambda e, k=kind: self._add(k))
        sbs.Add(add, 0, wx.ALIGN_LEFT | wx.ALL, 4)

        if kind == "condition":
            self.cond_box, self.cond_scr, self.cond_add = box, scr, add
        else:
            self.act_box, self.act_scr, self.act_add = box, scr, add
        return sbs

    def _scr_and_data(self, kind):
        return (self.cond_scr, self.conditions) if kind == "condition" \
            else (self.act_scr, self.actions)

    def _add_button(self, kind):
        return self.cond_add if kind == "condition" else self.act_add

    def _apply_tints(self):
        _tint(self.cond_scr, _TINT_WHEN)
        _tint(self.act_scr, _TINT_DO)

    # -- (re)build one section's stack of cards ------------------------------ #
    def _rebuild(self, kind):
        scr, data = self._scr_and_data(kind)
        sizer = scr.GetSizer()
        sizer.Clear(delete_windows=True)
        self._btn_refs[kind] = []

        if not data:
            noun = "condition" if kind == "condition" else "action"
            sizer.Add(wx.StaticText(scr, label="Nothing yet. Use the “Add %s” "
                                               "button below." % noun),
                      0, wx.ALL, 8)
        else:
            total = len(data)
            for i, item in enumerate(data):
                self._btn_refs[kind].append(self._build_card(scr, sizer, kind, i, item, total))

        scr.Layout()
        scr.FitInside()

    def _build_card(self, scr, sizer, kind, i, item, total):
        noun = "Condition" if kind == "condition" else "Action"
        summary = _summarize(item, kind)
        # The group-box LABEL is the item summary — NVDA reads it as the grouping
        # name, giving every button inside its context.
        box = wx.StaticBox(scr, label="%d. %s" % (i + 1, summary))
        row = wx.StaticBoxSizer(box, wx.HORIZONTAL)
        refs = {}

        def mk(name, label, handler, enabled=True):
            b = wx.Button(box, label=label)
            b.Bind(wx.EVT_BUTTON, handler)
            b.Enable(enabled)
            # Belt-and-braces context for readers that use the window name.
            b.SetName("%s %s %d: %s" % (label, noun, i + 1, summary))
            row.Add(b, 0, wx.RIGHT, 4)
            refs[name] = b
            return b

        mk("edit", "Edit", lambda e, k=kind, idx=i: self._edit(k, idx))
        mk("remove", "Remove", lambda e, k=kind, idx=i: self._remove(k, idx))
        mk("up", "Move Up", lambda e, k=kind, idx=i: self._move(k, idx, -1),
           enabled=(i > 0))
        mk("down", "Move Down", lambda e, k=kind, idx=i: self._move(k, idx, +1),
           enabled=(i < total - 1))

        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 4)
        return refs

    def _after_change(self, kind):
        # Scale/theme the freshly built cards, restore the tint, relayout.
        scr, _ = self._scr_and_data(kind)
        _apply_scale(scr)
        self._apply_tints()
        self.Layout()

    def _focus_card(self, kind, i, which):
        refs = self._btn_refs.get(kind, [])
        if not (0 <= i < len(refs)):
            return
        b = refs[i].get(which)
        if b is None or not b.IsEnabled():
            # Chosen button unavailable (e.g. moved to an end) — pick any enabled.
            for alt in ("down", "up", "edit", "remove"):
                cand = refs[i].get(alt)
                if cand is not None and cand.IsEnabled():
                    b = cand
                    break
        try:
            if b is not None:
                b.SetFocus()
        except Exception:
            pass

    # -- item operations ----------------------------------------------------- #
    def _add(self, kind):
        dlg = ItemDialog(self, kind)
        if dlg.ShowModal() == wx.ID_OK:
            _, data = self._scr_and_data(kind)
            data.append(dlg.get_item())
            self._rebuild(kind)
            self._after_change(kind)
            self._focus_card(kind, len(data) - 1, "edit")
        dlg.Destroy()

    def _edit(self, kind, i):
        _, data = self._scr_and_data(kind)
        if not (0 <= i < len(data)):
            return
        dlg = ItemDialog(self, kind, existing=data[i])
        if dlg.ShowModal() == wx.ID_OK:
            data[i] = dlg.get_item()
            self._rebuild(kind)
            self._after_change(kind)
            self._focus_card(kind, i, "edit")
        dlg.Destroy()

    def _remove(self, kind, i):
        _, data = self._scr_and_data(kind)
        if not (0 <= i < len(data)):
            return
        del data[i]
        self._rebuild(kind)
        self._after_change(kind)
        if data:
            self._focus_card(kind, min(i, len(data) - 1), "edit")
        else:
            self._add_button(kind).SetFocus()

    def _move(self, kind, i, delta):
        _, data = self._scr_and_data(kind)
        j = i + delta
        if not (0 <= i < len(data) and 0 <= j < len(data)):
            return
        data[i], data[j] = data[j], data[i]
        self._rebuild(kind)
        self._after_change(kind)
        # Keep focus on the moved item's same button so repeated presses work.
        self._focus_card(kind, j, "up" if delta < 0 else "down")

    def get_routine(self):
        self.routine["name"] = self.txt_name.GetValue().strip() or "Untitled routine"
        self.routine["enabled"] = bool(self.chk_enabled.GetValue())
        self.routine["conditions"] = self.conditions
        self.routine["actions"] = self.actions
        return self.routine


# --------------------------------------------------------------------------- #
# Manage screen: the list of routines (like the Shortcuts gallery)
# --------------------------------------------------------------------------- #
class ManageRoutinesDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Routines", size=(540, 480),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.routines = runtime.load_routines()

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(wx.StaticText(self, label="Your routines — each runs its actions when "
                                           "its conditions are met."),
                 0, wx.ALL, 10)

        box = wx.StaticBox(self, label="Routines")
        _bold(box)
        sbs = wx.StaticBoxSizer(box, wx.VERTICAL)

        self.lst = wx.ListBox(box, style=wx.LB_SINGLE)
        self.lst.SetName("Routines")
        self.lst.Bind(wx.EVT_LISTBOX_DCLICK, self.on_edit)
        self.lst.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        sbs.Add(self.lst, 1, wx.EXPAND | wx.ALL, 4)

        h = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in [("&Add", self.on_add), ("&Edit", self.on_edit),
                               ("&Delete", self.on_delete), ("&Toggle On/Off", self.on_toggle),
                               ("&Run Now", self.on_run)]:
            b = wx.Button(box, label=label)
            b.Bind(wx.EVT_BUTTON, handler)
            h.Add(b, 0, wx.RIGHT, 4)
        sbs.Add(h, 0, wx.ALL, 4)
        root.Add(sbs, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        root.Add(wx.Button(self, wx.ID_CANCEL, label="&Close"),
                 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(root)
        self.SetMinSize((440, 360))

        self._refresh()
        _finish_appearance(self)
        self.lst.SetFocus()
        if self.routines:
            self.lst.SetSelection(0)

    # ListBox rows already read cleanly in NVDA (arrow keys announce each row);
    # no tint here so the native list keeps maximum contrast.
    def _on_list_key(self, e):
        code = e.GetKeyCode()
        if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_edit(e)
        else:
            e.Skip()

    def _refresh(self, keep=None):
        sel = self.lst.GetSelection() if keep is None else keep
        self.lst.Set([
            "%s — %s" % (r.get("name", "Untitled"),
                              "On" if r.get("enabled", True) else "Off")
            for r in self.routines])
        if self.routines:
            if sel is None or sel == wx.NOT_FOUND or sel < 0:
                sel = 0
            sel = min(sel, len(self.routines) - 1)
            self.lst.SetSelection(sel)

    def _sel(self):
        i = self.lst.GetSelection()
        return i if i != wx.NOT_FOUND else None

    def _save(self):
        runtime.save_routines(self.routines)

    def on_add(self, _e):
        dlg = RoutineEditDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.routines.append(dlg.get_routine())
            self._save()
            self._refresh(keep=len(self.routines) - 1)
        dlg.Destroy()

    def on_edit(self, _e):
        i = self._sel()
        if i is None:
            return
        dlg = RoutineEditDialog(self, routine=dict(self.routines[i]))
        if dlg.ShowModal() == wx.ID_OK:
            self.routines[i] = dlg.get_routine()
            self._save()
            self._refresh(keep=i)
        dlg.Destroy()

    def on_delete(self, _e):
        i = self._sel()
        if i is None:
            return
        name = self.routines[i].get("name", "this routine")
        if wx.MessageBox("Delete '%s'?" % name, "Confirm",
                         wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
            del self.routines[i]
            self._save()
            self._refresh(keep=i)
            speak("Deleted %s." % name, interrupt=True)

    def on_toggle(self, _e):
        i = self._sel()
        if i is None:
            return
        new_state = not self.routines[i].get("enabled", True)
        self.routines[i]["enabled"] = new_state
        self._save()
        self._refresh(keep=i)
        speak("%s turned %s." % (self.routines[i].get("name", "Routine"),
                                 "on" if new_state else "off"), interrupt=True)

    def on_run(self, _e):
        i = self._sel()
        if i is None:
            return
        runtime.run_now(self.routines[i])
        speak("Running routine now.", interrupt=True)


def open_manage_dialog():
    parent = getattr(core.api, "main_window_instance", None)
    dlg = ManageRoutinesDialog(parent)
    dlg.ShowModal()
    dlg.Destroy()
