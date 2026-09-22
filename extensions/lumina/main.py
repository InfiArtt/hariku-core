# extensions/lumina/main.py
# ============================================================
# Lumina — Pengingat Ulang Tahun untuk Hariku V2
# ============================================================
# Fitur:
#   - Simpan ulang tahun teman & keluarga (nama, DD-MM, tahun opsional)
#   - Ulang tahun DIRI SENDIRI dengan ucapan spesial — nama diambil
#     otomatis dari profil onboarding Hariku
#   - Pengingat otomatis H-7, H-3, H-1, dan tepat hari H
#   - Ucapan custom per orang
#   - Dialog daftar dengan Tambah / Edit / Hapus
#   - Hotkey: Ctrl+Shift+B
# ============================================================

import logging
import datetime
import os
import wx

import core.api
import core.hotkeys
import core.preferences
from core.events import bus
from core.speech import speak
from core.i18n import get_translator

logger  = logging.getLogger(__name__)
EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_       = get_translator("lumina", os.path.join(EXT_DIR, "locales"))

DATA_KEY = "Lumina"


# ============================================================
# 1. HELPERS
# ============================================================

def _load() -> dict:
    return core.api.load_data(DATA_KEY)

def _save(data: dict):
    core.api.save_data(DATA_KEY, data)

def _get_birthdays() -> list:
    data = _load()
    return sorted(data.get("birthdays", []),
                  key=lambda e: e.get("name", "").lower())

def _save_birthdays(entries: list):
    data = _load()
    data["birthdays"] = entries
    _save(data)

def _get_settings() -> dict:
    return _load().get("settings", {
        "notify_on_startup": True,
        "remind_7": True,
        "remind_3": True,
        "remind_1": True,
        "remind_today": True,
        "nav_action": "speak",
    })

def _save_settings(s: dict):
    data = _load()
    data["settings"] = s
    _save(data)

def _get_self_birthday() -> dict:
    """
    Kembalikan data ulang tahun pengguna sendiri.
    Nama diambil dari profil Core (onboarding), bukan disimpan di Lumina.
    """
    return _load().get("self_birthday", {})

def _save_self_birthday(sb: dict):
    data = _load()
    data["self_birthday"] = sb
    _save(data)

def _get_user_name() -> str:
    """Ambil nama pengguna dari data onboarding Core."""
    core_data = core.api.load_data("Core")
    return core_data.get("user_name", "").strip() or "Kamu"


# ============================================================
# 2. BIRTHDAY LOGIC
# ============================================================

def _parse_birthday(dd_mm: str):
    """Parse 'DD-MM' → (day, month), atau None jika invalid."""
    try:
        parts = dd_mm.strip().split("-")
        if len(parts) != 2:
            return None
        day, month = int(parts[0]), int(parts[1])
        datetime.date(2000, month, day)  # validasi
        return day, month
    except (ValueError, IndexError):
        return None

def _days_until(day: int, month: int) -> int:
    """Hitung hari ke ulang tahun berikutnya (0 = hari ini)."""
    today = datetime.date.today()
    try:
        bday = datetime.date(today.year, month, day)
    except ValueError:
        bday = datetime.date(today.year, 3, 1)  # fallback 29 Feb

    delta = (bday - today).days
    if delta < 0:
        try:
            bday = datetime.date(today.year + 1, month, day)
        except ValueError:
            bday = datetime.date(today.year + 1, 3, 1)
        delta = (bday - today).days
    return delta

def _calc_age(birth_year, day, month):
    if not birth_year:
        return None
    return datetime.date.today().year - int(birth_year)


def _announce_one(entry: dict, is_self: bool = False):
    """
    Ucapkan pengingat untuk satu entry berdasarkan hari tersisa.
    is_self=True menggunakan ucapan spesial untuk diri sendiri.
    """
    parsed = _parse_birthday(entry.get("date", ""))
    if not parsed:
        return
    day, month = parsed
    days_left   = _days_until(day, month)
    name        = entry.get("name") or _get_user_name()
    greeting    = entry.get("greeting", "")
    year        = entry.get("year")
    settings    = _get_settings()

    if days_left == 0 and settings.get("remind_today", True):
        if greeting:
            msg = greeting
        elif is_self:
            msg = _("today_self").format(name=name)
        else:
            msg = _("today_msg").format(name=name)

        age = _calc_age(year, day, month)
        if age:
            suffix = _("age_suffix_self" if is_self else "age_suffix")
            msg += " " + suffix.format(name=name, age=age)
        speak(msg)

    elif days_left == 1 and settings.get("remind_1", True):
        key = "in_1_day_self" if is_self else "in_1_day"
        speak(_(key).format(name=name))

    elif days_left == 3 and settings.get("remind_3", True):
        key = "in_3_days_self" if is_self else "in_3_days"
        speak(_(key).format(name=name))

    elif days_left == 7 and settings.get("remind_7", True):
        key = "in_7_days_self" if is_self else "in_7_days"
        speak(_(key).format(name=name))


def _check_all_and_announce():
    """Cek seluruh daftar + self birthday dan umumkan yang relevan."""
    delay_ms = 2500

    # Cek ulang tahun sendiri
    sb = _get_self_birthday()
    if sb.get("date"):
        parsed = _parse_birthday(sb["date"])
        if parsed:
            days = _days_until(*parsed)
            if days in (0, 1, 3, 7):
                wx.CallLater(delay_ms, _announce_one, sb, True)
                delay_ms += 3000

    # Cek daftar teman/keluarga
    for entry in _get_birthdays():
        parsed = _parse_birthday(entry.get("date", ""))
        if not parsed:
            continue
        days = _days_until(*parsed)
        if days in (0, 1, 3, 7):
            wx.CallLater(delay_ms, _announce_one, entry, False)
            delay_ms += 2500


def get_upcoming(days_ahead: int = 30) -> list:
    """Kembalikan semua ulang tahun (termasuk self) dalam X hari ke depan."""
    result = []

    sb = _get_self_birthday()
    if sb.get("date"):
        parsed = _parse_birthday(sb["date"])
        if parsed:
            days = _days_until(*parsed)
            if days <= days_ahead:
                result.append({
                    "name":      _get_user_name(),
                    "date":      sb["date"],
                    "year":      sb.get("year"),
                    "days_left": days,
                    "is_self":   True,
                })

    for entry in _get_birthdays():
        parsed = _parse_birthday(entry.get("date", ""))
        if not parsed:
            continue
        days = _days_until(*parsed)
        if days <= days_ahead:
            result.append({
                "name":      entry.get("name", "?"),
                "date":      entry.get("date", ""),
                "year":      entry.get("year"),
                "days_left": days,
                "is_self":   False,
            })

    return sorted(result, key=lambda x: x["days_left"])


# ============================================================
# 3. ADD / EDIT DIALOG
# ============================================================

class BirthdayEditDialog(wx.Dialog):
    def __init__(self, parent, entry: dict | None = None):
        title = _("edit_birthday") if entry else _("add_birthday")
        super().__init__(parent, title=title, size=(420, 340),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._entry = entry or {}

        panel = wx.Panel(self)
        vbox  = wx.BoxSizer(wx.VERTICAL)

        def _lbl(text):
            vbox.Add(wx.StaticText(panel, label=text), 0, wx.LEFT | wx.TOP, 12)

        _lbl(_("name_label"))
        self.txt_name = wx.TextCtrl(panel, value=self._entry.get("name", ""))
        vbox.Add(self.txt_name, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        _lbl(_("date_label"))
        self.txt_date = wx.TextCtrl(panel, value=self._entry.get("date", ""))
        vbox.Add(self.txt_date, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        _lbl(_("year_label"))
        year_val = str(self._entry.get("year", "")) if self._entry.get("year") else ""
        self.txt_year = wx.TextCtrl(panel, value=year_val)
        vbox.Add(self.txt_year, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        _lbl(_("greeting_label"))
        self.txt_greeting = wx.TextCtrl(panel, value=self._entry.get("greeting", ""))
        vbox.Add(self.txt_greeting, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        btn_sizer = wx.StdDialogButtonSizer()
        self.btn_ok  = wx.Button(panel, wx.ID_OK, _("save"))
        btn_cancel   = wx.Button(panel, wx.ID_CANCEL, _("cancel"))
        btn_sizer.AddButton(self.btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 12)

        panel.SetSizer(vbox)
        self.btn_ok.Bind(wx.EVT_BUTTON, self._on_ok)
        self.txt_name.SetFocus()

    def _on_ok(self, event):
        name = self.txt_name.GetValue().strip()
        date = self.txt_date.GetValue().strip()
        if not name or not date or not _parse_birthday(date):
            speak(_("invalid_date"))
            core.api.show_message("Lumina", _("invalid_date"))
            return

        year = None
        try:
            year = int(self.txt_year.GetValue().strip())
        except ValueError:
            pass

        self._result = {
            "name":     name,
            "date":     date,
            "year":     year,
            "greeting": self.txt_greeting.GetValue().strip(),
        }
        self.EndModal(wx.ID_OK)

    def get_result(self) -> dict:
        return getattr(self, "_result", {})


# ============================================================
# 4. MAIN LIST DIALOG
# ============================================================

class LuminaListDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("list_title"),
                         size=(540, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._entries = _get_birthdays()

        panel = wx.Panel(self)
        vbox  = wx.BoxSizer(wx.VERTICAL)

        self.listbox = wx.ListBox(panel, style=wx.LB_SINGLE)
        vbox.Add(self.listbox, 1, wx.EXPAND | wx.ALL, 10)
        self._refresh_list()

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        btn_add   = wx.Button(panel, label=_("add_birthday"))
        btn_edit  = wx.Button(panel, label=_("edit_birthday"))
        btn_del   = wx.Button(panel, label=_("delete_birthday"))
        btn_close = wx.Button(panel, wx.ID_CLOSE, _("cancel"))
        for btn in (btn_add, btn_edit, btn_del):
            hbox.Add(btn, 0, wx.RIGHT, 6)
        hbox.AddStretchSpacer()
        hbox.Add(btn_close)
        vbox.Add(hbox, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(vbox)
        btn_add.Bind(wx.EVT_BUTTON, self._on_add)
        btn_edit.Bind(wx.EVT_BUTTON, self._on_edit)
        btn_del.Bind(wx.EVT_BUTTON, self._on_delete)
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        self.listbox.SetFocus()

    def _refresh_list(self):
        self.listbox.Clear()

        # Tampilkan self birthday di posisi pertama jika ada
        sb = _get_self_birthday()
        if sb.get("date"):
            name  = _get_user_name()
            days  = _days_until(*_parse_birthday(sb["date"])) if _parse_birthday(sb["date"]) else None
            label = f"★ {name}{_('self_badge')} — {sb['date']}"
            if sb.get("year"):
                label += f" ({sb['year']})"
            if days == 0:
                label += _("today_badge")
            elif days is not None:
                label += _("days_left_badge").format(days=days)
            self.listbox.Append(label)

        if not self._entries and not sb.get("date"):
            self.listbox.Append(_("no_birthdays"))
            return

        for e in self._entries:
            name  = e.get("name", "?")
            date  = e.get("date", "")
            year  = e.get("year")
            parsed = _parse_birthday(date)
            days  = _days_until(*parsed) if parsed else None
            label = f"{name} — {date}"
            if year:
                label += f" ({year})"
            if days == 0:
                label += _("today_badge")
            elif days is not None:
                label += _("days_left_badge").format(days=days)
            self.listbox.Append(label)

    def _selected_friend_index(self) -> int | None:
        idx = self.listbox.GetSelection()
        if idx == wx.NOT_FOUND:
            return None
        # Offset jika self birthday ada di baris 0
        sb = _get_self_birthday()
        offset = 1 if sb.get("date") else 0
        friend_idx = idx - offset
        if friend_idx < 0 or friend_idx >= len(self._entries):
            return None
        return friend_idx

    def _on_add(self, event):
        dlg = BirthdayEditDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            r = dlg.get_result()
            self._entries.append(r)
            self._entries = sorted(self._entries, key=lambda e: e.get("name", "").lower())
            _save_birthdays(self._entries)
            self._refresh_list()
            speak(_("saved").format(name=r["name"]))
        dlg.Destroy()

    def _on_edit(self, event):
        idx = self._selected_friend_index()
        if idx is None:
            return
        dlg = BirthdayEditDialog(self, entry=self._entries[idx])
        if dlg.ShowModal() == wx.ID_OK:
            r = dlg.get_result()
            self._entries[idx] = r
            self._entries = sorted(self._entries, key=lambda e: e.get("name", "").lower())
            _save_birthdays(self._entries)
            self._refresh_list()
            speak(_("saved").format(name=r["name"]))
        dlg.Destroy()

    def _on_delete(self, event):
        idx = self._selected_friend_index()
        if idx is None:
            return
        name = self._entries[idx].get("name", "?")
        if core.api.prompt_yes_no("Lumina", _("delete_confirm").format(name=name)):
            self._entries.pop(idx)
            _save_birthdays(self._entries)
            self._refresh_list()
            speak(_("deleted").format(name=name))


# ============================================================
# 5. HOTKEY ACTIONS
# ============================================================

def open_birthday_list():
    parent = wx.GetTopLevelWindows()[0] if wx.GetTopLevelWindows() else None
    dlg = LuminaListDialog(parent)
    dlg.ShowModal()
    dlg.Destroy()

def announce_upcoming():
    upcoming = get_upcoming(30)
    if not upcoming:
        speak(_("no_upcoming"))
        return
    speak(_("upcoming_title"))
    for item in upcoming:
        name = item["name"]
        days = item["days_left"]
        is_self = item["is_self"]
        if days == 0:
            key = "today_self" if is_self else "today_msg"
        elif days == 1:
            key = "in_1_day_self" if is_self else "in_1_day"
        elif days == 3:
            key = "in_3_days_self" if is_self else "in_3_days"
        elif days == 7:
            key = "in_7_days_self" if is_self else "in_7_days"
        else:
            speak(f"{name}: {days} hari lagi")
            continue
        speak(_(key).format(name=name))


# ============================================================
# 6. SETTINGS PANEL
# ============================================================

class LuminaSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        settings = _get_settings()
        sb       = _get_self_birthday()
        vbox     = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(self, label=_("settings_title")),
                 0, wx.ALL, 12)

        # --- Ulang tahun sendiri ---
        box     = wx.StaticBox(self, label=_("self_birthday_section"))
        box_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        hint = wx.StaticText(box, label=_("self_birthday_hint"))
        hint.SetForegroundColour(wx.Colour(120, 120, 120))
        box_sizer.Add(hint, 0, wx.ALL, 6)

        box_sizer.Add(wx.StaticText(box, label=_("self_birthday_date")),
                      0, wx.LEFT, 6)
        self.txt_self_date = wx.TextCtrl(box, value=sb.get("date", ""))
        box_sizer.Add(self.txt_self_date, 0, wx.EXPAND | wx.ALL, 6)

        box_sizer.Add(wx.StaticText(box, label=_("self_birthday_year")),
                      0, wx.LEFT, 6)
        yr_val = str(sb.get("year", "")) if sb.get("year") else ""
        self.txt_self_year = wx.TextCtrl(box, value=yr_val)
        box_sizer.Add(self.txt_self_year, 0, wx.EXPAND | wx.ALL, 6)

        vbox.Add(box_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # --- Pengingat ---
        self.chk_startup = wx.CheckBox(self, label=_('notify_on_startup'))
        self.chk_startup.SetValue(settings.get('notify_on_startup', True))
        vbox.Add(self.chk_startup, 0, wx.LEFT | wx.BOTTOM, 12)

        # (attr_name, locale_key, settings_key, default)
        remind_opts = [
            ('chk_7',     'remind_7_days', 'remind_7',    True),
            ('chk_3',     'remind_3_days', 'remind_3',    True),
            ('chk_1',     'remind_1_day',  'remind_1',    True),
            ('chk_today', 'remind_today',  'remind_today', True),
        ]
        for attr, locale_key, settings_key, default in remind_opts:
            chk = wx.CheckBox(self, label=_(locale_key))
            chk.SetValue(settings.get(settings_key, default))
            vbox.Add(chk, 0, wx.LEFT | wx.BOTTOM, 8)
            setattr(self, attr, chk)

        # Navigasi kalender
        vbox.Add(wx.StaticText(self, label=_("nav_action_label")), 0, wx.LEFT | wx.TOP, 12)
        choices = [_("nav_action_none"), _("nav_action_speak"), _("nav_action_agenda")]
        self.choice_nav = wx.Choice(self, choices=choices)
        val = settings.get("nav_action", "speak")
        idx = {"none": 0, "speak": 1, "agenda": 2}.get(val, 1)
        self.choice_nav.SetSelection(idx)
        vbox.Add(self.choice_nav, 0, wx.LEFT | wx.BOTTOM, 12)

        self.SetSizer(vbox)

    def ApplyChanges(self):
        # Simpan self birthday
        date_val = self.txt_self_date.GetValue().strip()
        year_val = None
        try:
            year_val = int(self.txt_self_year.GetValue().strip())
        except ValueError:
            pass

        if date_val and _parse_birthday(date_val):
            _save_self_birthday({"date": date_val, "year": year_val})
        elif not date_val:
            _save_self_birthday({})

        nav_val = ["none", "speak", "agenda"][self.choice_nav.GetSelection()]
        _save_settings({
            "notify_on_startup": self.chk_startup.GetValue(),
            "remind_7":   self.chk_7.GetValue(),
            "remind_3":   self.chk_3.GetValue(),
            "remind_1":   self.chk_1.GetValue(),
            "remind_today": self.chk_today.GetValue(),
            "nav_action": nav_val,
        })


_panel_instance = None

def _create_panel(parent):
    global _panel_instance
    _panel_instance = LuminaSettingsPanel(parent)
    return _panel_instance

def _apply_panel():
    if _panel_instance:
        _panel_instance.ApplyChanges()


# ============================================================
# 7. EVENT HANDLERS
# ============================================================

def on_app_startup():
    if not _get_settings().get("notify_on_startup", True):
        return
    wx.CallLater(2500, _check_all_and_announce)


def on_date_changed(date_str):
    settings = _get_settings()
    nav_action = settings.get("nav_action", "speak")
    if nav_action == "none":
        return

    try:
        parts = date_str.split('-')
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    except:
        return
        
    birthdays_today = []
    
    # Cek ulang tahun sendiri
    sb = _get_self_birthday()
    if sb.get("date"):
        parsed = _parse_birthday(sb["date"])
        if parsed and parsed[0] == day and parsed[1] == month:
            birthdays_today.append(_get_user_name() + _("self_badge"))
            
    # Cek daftar teman/keluarga
    for e in _get_birthdays():
        parsed = _parse_birthday(e.get("date", ""))
        if parsed and parsed[0] == day and parsed[1] == month:
            birthdays_today.append(e.get("name", "?"))
            
    if birthdays_today:
        names = ", ".join(birthdays_today)
        msg = _("navigate_birthday").format(names=names)
        if nav_action == "speak":
            speak(msg)

def on_fetch_agenda(payload):
    settings = _get_settings()
    if settings.get("nav_action", "speak") != "agenda":
        return

    date_str = payload.get("date")
    if not date_str:
        return

    try:
        parts = date_str.split('-')
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    except:
        return
        
    birthdays_today = []
    
    # Cek ulang tahun sendiri
    sb = _get_self_birthday()
    if sb.get("date"):
        parsed = _parse_birthday(sb["date"])
        if parsed and parsed[0] == day and parsed[1] == month:
            birthdays_today.append(_get_user_name() + _("self_badge"))
            
    # Cek daftar teman/keluarga
    for e in _get_birthdays():
        parsed = _parse_birthday(e.get("date", ""))
        if parsed and parsed[0] == day and parsed[1] == month:
            birthdays_today.append(e.get("name", "?"))
            
    if birthdays_today:
        names = ", ".join(birthdays_today)
        title = _("agenda_birthday_title").format(names=names)
        
        # Inject fake reminder ke list agenda
        payload["reminders"].insert(0, {
            "id": f"lumina_bday_{date_str}",
            "title": title,
            "date": date_str,
            "time": "00:00",
            "is_done": False,
            "readonly": True
        })


# ============================================================
# 8. REGISTER
# ============================================================

def register(bus):
    logger.info("Lumina — Birthday Reminder loaded.")

    bus.subscribe("on_app_startup", on_app_startup)
    bus.subscribe("on_date_changed", on_date_changed)
    bus.subscribe("on_fetch_agenda", on_fetch_agenda)

    core.hotkeys.register_action(
        "Lumina",
        "open_list",
        _("open_list"),
        ord("B"),
        True,        # Ctrl
        open_birthday_list,
        default_shift=True,
        default_alt=False,
    )

    core.hotkeys.register_action(
        "Lumina",
        "check_upcoming",
        _("check_upcoming"),
        None,
        False,
        announce_upcoming,
    )

    core.preferences.register_panel(
        "Lumina",
        "",
        _create_panel,
        _apply_panel,
    )
