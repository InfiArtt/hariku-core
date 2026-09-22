# extensions/world_clock/main.py
# ============================================================
# Hariku V2 Extension — World Clock
# ============================================================
# Hear the current time in cities around the world, screen-reader first:
#   - a hotkey speaks every configured zone,
#   - a window lists them (arrow through with NVDA),
#   - Preferences lets you add/remove cities.
# Uses the standard-library zoneinfo + the tzdata package (IANA database),
# so no network is needed.
# ============================================================

import logging
from datetime import datetime

import wx

import core.api
import core.hotkeys
import core.preferences
from core.speech import speak

logger = logging.getLogger(__name__)

DATA_KEY = "WorldClock"

# Sensible starting set (dev is in Jakarta; spread across the globe).
DEFAULT_ZONES = [
    {"label": "Jakarta", "tz": "Asia/Jakarta"},
    {"label": "London", "tz": "Europe/London"},
    {"label": "New York", "tz": "America/New_York"},
    {"label": "Tokyo", "tz": "Asia/Tokyo"},
]


# ------------------------------------------------------------
# Time-zone helpers
# ------------------------------------------------------------

def _available_timezones():
    """Sorted list of IANA zone names, or [] if the tz database is missing."""
    try:
        from zoneinfo import available_timezones
        return sorted(available_timezones())
    except Exception as e:
        logger.error(f"[WorldClock] Time zone database unavailable: {e}")
        return []


def _get_config():
    return core.api.load_data(DATA_KEY)


def _get_zones():
    """Return the configured zones (falls back to defaults only if never set)."""
    cfg = _get_config()
    zones = cfg.get("zones")
    return DEFAULT_ZONES if zones is None else zones


def _use_24h():
    return _get_config().get("use_24h", False)


def _format_zone(zone, use_24h=False):
    """Return e.g. 'Tokyo: Tuesday 10:44 PM (tomorrow)' or an error note."""
    from zoneinfo import ZoneInfo
    label = zone.get("label", zone.get("tz", "?"))
    tz = zone.get("tz", "")
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception:
        return f"{label}: time zone not found"

    if use_24h:
        clock = now.strftime("%H:%M")
    else:
        # Strip the leading zero on the hour: '08:44 PM' -> '8:44 PM'.
        clock = now.strftime("%I:%M %p").lstrip("0")

    weekday = now.strftime("%A")

    # Relative-day hint vs. the local machine date (handy across the date line).
    local_date = datetime.now().date()
    zone_date = now.date()
    if zone_date > local_date:
        rel = " (tomorrow)"
    elif zone_date < local_date:
        rel = " (yesterday)"
    else:
        rel = ""

    return f"{label}: {weekday} {clock}{rel}"


def _all_lines():
    use_24h = _use_24h()
    return [_format_zone(z, use_24h) for z in _get_zones()]


# ------------------------------------------------------------
# Actions
# ------------------------------------------------------------

def speak_world_clock():
    zones = _get_zones()
    if not zones:
        speak("No world clock cities configured. Add some in Preferences, World Clock.", interrupt=True)
        return
    speak("World clock. " + ". ".join(_all_lines()), interrupt=True)


def show_world_clock_window():
    parent = getattr(core.api, "main_window_instance", None)
    dlg = WorldClockDialog(parent)
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------------
# Live view window (opened by hotkey/menu)
# ------------------------------------------------------------

class WorldClockDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="World Clock",
                         size=(460, 380),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        vbox = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(self, label="Current times")
        vbox.Add(lbl, 0, wx.ALL, 8)

        # ListBox: NVDA reads each city as you arrow through it.
        self.listbox = wx.ListBox(self, style=wx.LB_SINGLE)
        vbox.Add(self.listbox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        btn_speak = wx.Button(self, label="&Speak All")
        btn_refresh = wx.Button(self, label="&Refresh")
        btn_close = wx.Button(self, wx.ID_CANCEL, label="&Close")
        hbox.Add(btn_speak, 0, wx.RIGHT, 6)
        hbox.Add(btn_refresh, 0, wx.RIGHT, 6)
        hbox.Add(btn_close, 0)
        vbox.Add(hbox, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(vbox)
        self.CentreOnParent()

        btn_speak.Bind(wx.EVT_BUTTON, lambda e: speak_world_clock())
        btn_refresh.Bind(wx.EVT_BUTTON, lambda e: self._refresh())

        # Live tick so the minutes stay current while the window is open.
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda e: self._refresh(), self._timer)
        self._timer.Start(1000)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self._refresh()
        self.listbox.SetFocus()
        if self.listbox.GetCount():
            self.listbox.SetSelection(0)

    def _refresh(self):
        # Preserve the caret position across refreshes.
        sel = self.listbox.GetSelection()
        self.listbox.Set(_all_lines() or ["(no cities configured)"])
        if 0 <= sel < self.listbox.GetCount():
            self.listbox.SetSelection(sel)

    def _on_close(self, event):
        if self._timer.IsRunning():
            self._timer.Stop()
        event.Skip()


# ------------------------------------------------------------
# Add-city dialog
# ------------------------------------------------------------

class AddZoneDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Add City")
        self._zones = _available_timezones()
        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(self, label="City label (what you'll hear):"),
                 0, wx.LEFT | wx.TOP, 10)
        self.txt_label = wx.TextCtrl(self)
        vbox.Add(self.txt_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        vbox.Add(wx.StaticText(self, label="Time zone (type to search):"),
                 0, wx.LEFT | wx.TOP, 10)
        # Type-ahead combo over the full IANA list; NVDA-navigable.
        self.cmb_tz = wx.ComboBox(self, choices=self._zones, style=wx.CB_DROPDOWN)
        vbox.Add(self.cmb_tz, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add(btns, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        self.SetSizerAndFit(vbox)
        self.txt_label.SetFocus()

    def get_zone(self):
        """Return {'label','tz'} if valid, else None."""
        tz = self.cmb_tz.GetValue().strip()
        label = self.txt_label.GetValue().strip()
        if tz not in self._zones:
            return None
        if not label:
            # Default the label to the city part of the tz (e.g. Asia/Tokyo -> Tokyo).
            label = tz.split("/")[-1].replace("_", " ")
        return {"label": label, "tz": tz}


# ------------------------------------------------------------
# Preferences panel (manage cities)
# ------------------------------------------------------------

class WorldClockPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self._zones = list(_get_zones())

        vbox = wx.BoxSizer(wx.VERTICAL)

        self.chk_24h = wx.CheckBox(self, label="Use 24-hour time")
        self.chk_24h.SetValue(_use_24h())
        vbox.Add(self.chk_24h, 0, wx.ALL, 10)

        vbox.Add(wx.StaticText(self, label="Cities:"), 0, wx.LEFT, 10)
        self.listbox = wx.ListBox(self, style=wx.LB_SINGLE)
        vbox.Add(self.listbox, 1, wx.EXPAND | wx.ALL, 10)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        btn_add = wx.Button(self, label="&Add City...")
        btn_remove = wx.Button(self, label="&Remove Selected")
        hbox.Add(btn_add, 0, wx.RIGHT, 6)
        hbox.Add(btn_remove, 0)
        vbox.Add(hbox, 0, wx.LEFT | wx.BOTTOM, 10)

        self.SetSizer(vbox)

        btn_add.Bind(wx.EVT_BUTTON, self._on_add)
        btn_remove.Bind(wx.EVT_BUTTON, self._on_remove)

        self._reload_list()

    def _reload_list(self):
        self.listbox.Set([f"{z.get('label','?')} ({z.get('tz','?')})" for z in self._zones])

    def _on_add(self, event):
        dlg = AddZoneDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            zone = dlg.get_zone()
            if zone:
                self._zones.append(zone)
                self._reload_list()
            else:
                core.api.show_message("Add City",
                                      "Please pick a valid time zone from the list.")
        dlg.Destroy()

    def _on_remove(self, event):
        sel = self.listbox.GetSelection()
        if sel != wx.NOT_FOUND:
            del self._zones[sel]
            self._reload_list()

    def ApplyChanges(self):
        cfg = _get_config()
        cfg["zones"] = self._zones
        cfg["use_24h"] = self.chk_24h.GetValue()
        core.api.save_data(DATA_KEY, cfg)


_panel_instance = None


def _create_panel(parent):
    global _panel_instance
    _panel_instance = WorldClockPanel(parent)
    return _panel_instance


def _apply_panel():
    if _panel_instance:
        _panel_instance.ApplyChanges()


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register(bus):
    logger.info("World Clock extension loaded.")

    core.hotkeys.register_action(
        "World Clock", "speak_world_clock", "Speak world clock times",
        ord("W"), False, speak_world_clock
    )
    core.hotkeys.register_action(
        "World Clock", "open_world_clock", "Open the world clock window",
        None, False, show_world_clock_window
    )

    core.preferences.register_panel("World Clock", "", _create_panel, _apply_panel)


def teardown():
    # Called by the engine on shutdown (via on_unload). No persistent resources
    # here (the window's timer is stopped when the window closes), so nothing to
    # clean up — kept as the canonical lifecycle hook / example.
    logger.info("World Clock extension unloaded.")
