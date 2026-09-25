# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The welcome (core 2.10): the dialog Hariku shows the first time it starts,
before the main window, and again from Help, Welcome Dialog. Eight pages with
Back, Next (Finish on the last) and Cancel; what they ask and say comes from
core.onboarding, which has no window and is unit-tested.

Talking with a screen reader:
  * Each page opens with Hariku's line: the reply to the page before ("Senang
    kenalan, Rafli!", "Di Batam sekarang jam 14:20, cerah berawan, 31
    derajat.") and the page's question. It is the label of the page's first
    field, created right before it, so the screen reader reads it with the
    field when Next or Back puts the focus there (core.ui_overrides reads a
    label's current text, so a question changed with SetLabel is what the
    screen reader says). The rest of the page's text is spoken a moment
    later, without interrupting, and is on the page to review.
  * Focus moves only when the user acts: Next and Back put it on the page's
    first field (the Finish button on the last page); a city search the user
    is waiting on takes them to the results. Selecting in a list never moves
    it. Enter is Next (in the search and "Try it" fields it searches and
    tries, and is Next when they are empty); Escape is Cancel, asking first
    when something was entered.
  * Speech goes to the screen reader (core.speech), never forced into Hariku
    Voice.

Network requests (the city search, the weather, the store's list, and the
downloads after Finish) run on worker threads and come back through
wx.CallAfter. Nothing is downloaded before Finish.
"""
import logging
import threading

import wx

import core.api
import core.commands
import core.extension_manager
import core.hotkeys
import core.i18n
import core.onboarding as onboarding
import core.personal
import core.places
import core.sounds
import core.store
import core.ui_scale
from core.core_panels import _plain_label
from core.i18n import apply_rtl_layout, get_translator
from core.speech import speak

_ = get_translator("core")
logger = logging.getLogger(__name__)

PAGES = onboarding.PAGES
WRAP = 560                   # pixels a line of text may take
SPEAK_DELAY_MS = 400         # the page's text waits for the focused field's announcement
ERROR_DELAY_MS = 100         # a problem is said once the focus has moved to the field
DESCRIBE_DELAY_MS = 700      # an extension's line, once the arrow keys rest
WEATHER_DELAY_MS = 700       # a city's weather is asked for once the arrow keys rest
START_SOUND = "start.wav"    # opened from Help (Hariku has just played it on a first run)
DONE_SOUND = "confirm.wav"


def _key_label(action_id, keycode, ctrl=False, shift=False, alt=False):
    """The key an action has now (or saved for it, before the main window
    registered it), else its default, in words: "Ctrl + Alt + Backspace"."""
    try:
        bindings = core.hotkeys.get_current_bindings(action_id)
        if not bindings:
            saved = core.hotkeys.saved_config.get(action_id)
            bindings = [(b.get("keycode"), bool(b.get("ctrl")), bool(b.get("shift")),
                         bool(b.get("alt")), bool(b.get("win")), bool(b.get("global")))
                        for b in (saved if isinstance(saved, list) else [])
                        if isinstance(b, dict) and isinstance(b.get("keycode"), int)]
        if bindings:
            code, c, s, a, w, _global = sorted(bindings)[0]
            return core.hotkeys.format_key_name(code, c, s, a, w)
    except Exception as e:
        logger.debug(f"Welcome: no key for {action_id}: {e}")
    return core.hotkeys.format_key_name(keycode, ctrl, shift, alt)


def _change(ctrl, value):
    """Put `value` in a read-only field, unless it is there already."""
    if ctrl.GetValue() != value:
        ctrl.ChangeValue(value)


def aruna_key():
    """Aruna's key: ui.command_bar.hotkey_label() once it is registered."""
    try:
        from ui.command_bar import ACTION_ID, hotkey_label
        label = hotkey_label()
        if label:
            return label
    except Exception as e:
        logger.debug(f"Welcome: Aruna's key unknown: {e}")
        ACTION_ID = core.commands.COMMAND_BAR_ACTION
    return _key_label(ACTION_ID, wx.WXK_BACK, ctrl=True, alt=True)


def store_key():
    """The Extension Manager's key (Ctrl + X in the main window)."""
    return _key_label("Hariku Core.manage_extensions", ord("X"), ctrl=True)


class Outcome:
    """How the welcome ended: `finished` (Finish), `cancelled`, the ids of
    the extensions `installed` and `failed`, whether the language changed,
    and what onboarding.save() reported."""

    def __init__(self):
        self.finished = False
        self.cancelled = False
        self.installed = []
        self.failed = []
        self.language_changed = False
        self.saved = None


class OnboardingDialog(wx.Dialog):
    def __init__(self, parent=None, first_run=False):
        super().__init__(parent, title=_("onb_title"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.first_run = first_run
        self.outcome = Outcome()
        self._closed = False
        self.opened_language = core.i18n.get_current_language()
        self.answers = onboarding.prefill(first_run=first_run)
        core.i18n.use_language(self.answers.language)
        self._nick_auto = onboarding.nickname_is_automatic(self.answers)
        self.main = onboarding.main_place()
        self.aruna_key = aruna_key()
        self.store_key = store_key()

        self.city = None              # the city chosen from the results
        self.cities = []
        self._searched = ""           # the last query searched
        self._cities_answered = False
        self._search_id = 0
        self._weather = {}            # rounded point -> weather, or None (none to be had)
        self._weather_pending = set()
        self._reply_place = None      # the place the birthday page's opening line is about
        self._reply_weather = False   # ...and whether that line has the weather
        self.registry = None          # None: the store hasn't answered yet
        self.installed = []
        self.offers = []              # the extensions offered
        self._ext_checked = None      # the ids ticked; None before the list was first filled
        self._ext_default = None      # ...and those ticked at first
        self.installing = False
        self.install_done = False
        self.replies = {}             # page index -> the reply that opens it
        self.index = 0
        self.ready = False            # the first page has been shown and focused
        self._timers = {}
        # [window, text function, kind, the control it labels, the text it has]
        self._texts = []

        root = wx.BoxSizer(wx.VERTICAL)
        self.pages = []
        for page in PAGES:
            panel = wx.Panel(self)
            sizer = wx.BoxSizer(wx.VERTICAL)
            getattr(self, "_build_" + page)(panel, sizer)
            panel.SetSizer(sizer)
            root.Add(panel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
            self.pages.append(panel)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_back = self._button(self, buttons, lambda: _("onb_btn_back"))
        self.btn_next = self._button(self, buttons, lambda: _("onb_btn_next"))
        self.btn_cancel = self._button(self, buttons, lambda: _("onb_btn_cancel"))
        self.btn_next.SetDefault()
        root.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(root)
        self.SetEscapeId(wx.ID_NONE)   # Escape is handled below: it may ask first

        self.btn_back.Bind(wx.EVT_BUTTON, self.on_back)
        self.btn_next.Bind(wx.EVT_BUTTON, self.on_next)
        self.btn_cancel.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self._refresh_texts()          # after the text size is set, so lines wrap right
        # Every page as big as the biggest, so Next and Back don't resize the window.
        sizes = [p.GetBestSize() for p in self.pages]
        biggest = (max(s.width for s in sizes), max(s.height for s in sizes))
        for i, panel in enumerate(self.pages):
            panel.SetMinSize(biggest)
            panel.Show(i == 0)
        self._update_buttons()
        self.Fit()
        self.CentreOnScreen() if parent is None else self.CentreOnParent()
        self._before = self._answers()
        wx.CallAfter(self._opened)

    # ------------------------------------------------------------
    # Building
    # ------------------------------------------------------------

    def _static(self, parent, sizer, text, bold=False):
        """A text on the page; `text()` gives it in the current language."""
        static = wx.StaticText(parent, label=text().replace("&", "&&") or "-")
        if bold:
            font = static.GetFont()
            font.MakeBold()
            font.SetPointSize(font.GetPointSize() + 2)
            static.SetFont(font)
        sizer.Add(static, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._texts.append([static, text, "static", None, None])
        return static

    def _field(self, parent, sizer, text, make, bold=False, proportion=0, button=None):
        """A label, then the control it names (created right after it, so
        screen readers read the label with the control), and optionally a
        button beside the control. Returns the control (and the button)."""
        self._static(parent, sizer, text, bold)
        entry = self._texts[-1]
        ctrl = make()
        entry[3] = ctrl
        ctrl.SetName(_plain_label(text().replace("&", "&&")))
        if button is None:
            sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
            return ctrl
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(ctrl, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        btn = self._button(parent, row, button)
        sizer.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        return ctrl, btn

    def _button(self, parent, sizer, text):
        btn = wx.Button(parent, label=text())
        self._texts.append([btn, text, "label", None, text()])
        sizer.Add(btn, 0, wx.LEFT, 5)
        return btn

    def _check(self, parent, sizer, text, value):
        check = wx.CheckBox(parent, label=text())
        check.SetValue(bool(value))
        self._texts.append([check, text, "label", None, text()])
        sizer.Add(check, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        return check

    def _build_hello(self, panel, sizer):
        self.language_codes = [code for code, _name in onboarding.languages()]
        names = [name for _code, name in onboarding.languages()]
        self.choice_language = self._field(
            panel, sizer, lambda: onboarding.question("hello"),
            lambda: wx.Choice(panel, choices=names), bold=True)
        if self.answers.language in self.language_codes:
            self.choice_language.SetSelection(self.language_codes.index(self.answers.language))
        elif names:
            self.choice_language.SetSelection(0)
        self._static(panel, sizer, lambda: _("onb_hello_intro"))
        self.choice_language.Bind(wx.EVT_CHOICE, self._on_language)

    def _build_name(self, panel, sizer):
        self.txt_name = self._field(
            panel, sizer, lambda: onboarding.question("name", reply=self._reply("name")),
            lambda: wx.TextCtrl(panel, value=self.answers.name), bold=True)
        self.txt_name.SetMaxLength(core.personal.MAX_VALUE_LENGTH)
        self.txt_nickname = self._field(
            panel, sizer, lambda: _("onb_nickname_label"),
            lambda: wx.TextCtrl(panel, value=self.answers.nickname))
        self.txt_nickname.SetMaxLength(core.personal.MAX_VALUE_LENGTH)
        self._static(panel, sizer, lambda: _("onb_name_intro"))
        self.txt_name.Bind(wx.EVT_TEXT, self._on_name_text)
        self.txt_nickname.Bind(wx.EVT_TEXT, self._on_nickname_text)

    def _build_where(self, panel, sizer):
        self.txt_city, self.btn_search = self._field(
            panel, sizer,
            lambda: onboarding.question("where", self._nickname(), self._reply("where")),
            lambda: wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER), bold=True,
            button=lambda: _("onb_where_btn_search"))
        self.list_cities = self._field(panel, sizer, self._cities_label,
                                       lambda: wx.ListBox(panel, size=(-1, 90), style=wx.LB_SINGLE))
        self.txt_chosen = self._field(panel, sizer, lambda: _("onb_where_chosen"),
                                      lambda: wx.TextCtrl(panel, style=wx.TE_READONLY))
        self._static(panel, sizer, self._where_intro)
        self.txt_city.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        self.list_cities.Bind(wx.EVT_LISTBOX, self._on_city_selected)

    def _build_birthday(self, panel, sizer):
        day, month, year = self.answers.birthday or (0, 0, None)
        self.choice_day = self._field(
            panel, sizer,
            lambda: onboarding.question("birthday", self._nickname(), self._reply("birthday")),
            lambda: wx.Choice(panel, choices=[_("profile_not_set")]
                              + [str(d) for d in range(1, 32)]), bold=True)
        self.choice_day.SetSelection(day)
        self.choice_month = self._field(panel, sizer, lambda: _("onb_birthday_month"),
                                        lambda: wx.Choice(panel, choices=self._month_names()))
        self.choice_month.SetSelection(month)
        self.txt_year = self._field(panel, sizer, lambda: _("onb_birthday_year"),
                                    lambda: wx.TextCtrl(panel, value=str(year) if year else ""))
        self.txt_year.SetMaxLength(4)
        self.lbl_birthday_error = wx.StaticText(panel, label="")
        sizer.Add(self.lbl_birthday_error, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._static(panel, sizer, lambda: _("onb_birthday_intro"))

    def _build_aruna(self, panel, sizer):
        self.txt_try, self.btn_try = self._field(
            panel, sizer,
            lambda: onboarding.question("aruna", self._nickname(), self._reply("aruna")),
            lambda: wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER), bold=True,
            button=lambda: _("onb_aruna_btn_try"))
        self.txt_answer = self._field(panel, sizer, lambda: _("onb_aruna_answer"),
                                      lambda: wx.TextCtrl(panel, style=wx.TE_READONLY))
        self._static(panel, sizer, lambda: _("onb_aruna_intro", shortcut=self.aruna_key))
        self.txt_try.Bind(wx.EVT_TEXT_ENTER, self._on_try)
        self.btn_try.Bind(wx.EVT_BUTTON, self._on_try)

    def _build_extensions(self, panel, sizer):
        self.list_ext = self._field(
            panel, sizer,
            lambda: onboarding.question("extensions", self._nickname(), self._reply("extensions")),
            lambda: wx.CheckListBox(panel, size=(-1, 150)), bold=True, proportion=1)
        self.txt_ext_details = self._field(
            panel, sizer, lambda: _("onb_ext_details"),
            lambda: wx.TextCtrl(panel, size=(-1, 60), style=wx.TE_READONLY | wx.TE_MULTILINE))
        self._static(panel, sizer, self._ext_state_text)
        self.list_ext.Bind(wx.EVT_LISTBOX, self._on_ext_selected)
        self.list_ext.Bind(wx.EVT_CHECKLISTBOX, self._on_ext_checked)

    def _build_startup(self, panel, sizer):
        # The question comes right before the first check box, so the screen
        # reader reads it with the box (core.ui_overrides).
        self._static(panel, sizer,
                     lambda: onboarding.question("startup", self._nickname(),
                                                 self._reply("startup")), bold=True)
        self.chk_autostart = self._check(panel, sizer, lambda: _("onb_startup_autostart"),
                                         self.answers.autostart)
        self.chk_greet = self._check(panel, sizer, lambda: _("onb_startup_greet"),
                                     self.answers.greet)
        self._static(panel, sizer, lambda: _("onb_startup_intro",
                                             example=onboarding.startup_example(self._nickname())))

    def _build_done(self, panel, sizer):
        self.txt_summary = self._field(
            panel, sizer, lambda: _("onb_done_label"),
            lambda: wx.TextCtrl(panel, size=(-1, 150), style=wx.TE_READONLY | wx.TE_MULTILINE),
            bold=True, proportion=1)
        self.lbl_status = self._static(panel, sizer, lambda: _("onb_install_status"))
        self.txt_status = wx.TextCtrl(panel, size=(-1, 70), style=wx.TE_READONLY | wx.TE_MULTILINE)
        self._texts[-1][3] = self.txt_status
        self.txt_status.SetName(_plain_label(_("onb_install_status")))
        sizer.Add(self.txt_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        self.lbl_status.Hide()
        self.txt_status.Hide()

    # ------------------------------------------------------------
    # Texts
    # ------------------------------------------------------------

    def _month_names(self):
        return [_("profile_not_set")] + [_(f"month_{m}") for m in range(1, 13)]

    def _reply(self, page):
        return self.replies.get(PAGES.index(page), "")

    def _nickname(self):
        return onboarding.nickname_for(self.txt_name.GetValue(), self.txt_nickname.GetValue())

    def _language(self):
        sel = self.choice_language.GetSelection()
        return self.language_codes[sel] if 0 <= sel < len(self.language_codes) else None

    def _refresh_texts(self):
        """Every text in the current language, with the nickname in it. Only
        what changed is set again, so a focused control isn't re-announced."""
        for entry in self._texts:
            window, text, kind, ctrl, shown = entry
            value = text()
            if value == shown:
                continue
            entry[4] = value
            if kind == "static":
                label = value.replace("&", "&&")
                window.SetLabel(label or "-")
                window.Wrap(WRAP)
                if ctrl is not None:
                    ctrl.SetName(_plain_label(label))
            else:
                window.SetLabel(value)
        not_set = _("profile_not_set")
        if self.choice_day.GetString(0) != not_set:
            self.choice_day.SetString(0, not_set)
        for i, month in enumerate(self._month_names()):
            if self.choice_month.GetString(i) != month:
                self.choice_month.SetString(i, month)
        _change(self.txt_chosen, self._chosen_text())
        self._show_ext_details()
        self._update_buttons()

    def _update_buttons(self):
        last = self.index == len(PAGES) - 1
        label = _("onb_btn_finish") if last else _("onb_btn_next")
        if self.btn_next.GetLabel() != label:
            self.btn_next.SetLabel(label)
        self.btn_back.Enable(self.index > 0 and not self.installing and not self.install_done)
        self.btn_cancel.Enable(not self.installing and not self.install_done)
        title = _("onb_title_step", number=self.index + 1, count=len(PAGES))
        if self.GetTitle() != title:
            self.SetTitle(title)

    def _relayout(self):
        self.pages[self.index].Layout()
        self.Layout()
        best, size = self.GetBestSize(), self.GetSize()
        if best.width > size.width or best.height > size.height:
            self.SetSize((max(best.width, size.width), max(best.height, size.height)))
            self.Layout()

    def _page_speech(self, index):
        """What is said once a page shows: its text besides the question the
        screen reader reads with the focused field."""
        page = PAGES[index]
        if page == "hello":
            return _("onb_hello_intro")
        if page == "name":
            return _("onb_name_intro")
        if page == "where":
            return self._where_intro()
        if page == "birthday":
            return _("onb_birthday_intro")
        if page == "aruna":
            return _("onb_aruna_intro", shortcut=self.aruna_key)
        if page == "extensions":
            return self._ext_state_text()
        if page == "startup":
            return _("onb_startup_intro", example=onboarding.startup_example(self._nickname()))
        return " ".join(self._summary_lines())

    # ------------------------------------------------------------
    # Speech, sounds and timers
    # ------------------------------------------------------------

    def _say(self, text, interrupt=False):
        if text and not self._closed:
            speak(text, interrupt=interrupt)

    def _later(self, name, delay, fn, *args):
        """Run fn(*args) after `delay` ms; a newer call with the same name replaces it."""
        self._stop(name)
        self._timers[name] = wx.CallLater(delay, self._timer_fired, name, fn, *args)

    def _timer_fired(self, name, fn, *args):
        self._timers.pop(name, None)
        if self and not self._closed:
            fn(*args)

    def _stop(self, name):
        timer = self._timers.pop(name, None)
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass

    def _play(self, sound):
        try:
            core.sounds.play_internal_sound(sound)
        except Exception as e:
            logger.debug(f"Welcome: {sound} didn't play: {e}")

    # ------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------

    def _opened(self):
        if not self or self._closed:
            return
        threading.Thread(target=self._store_worker, daemon=True, name="hariku-welcome-store").start()
        if not self.first_run:
            self._play(START_SOUND)
        self.Raise()
        self.show_page(0)
        self.ready = True

    def show_page(self, index, reply=""):
        """Show page `index`, opening with `reply`; focus goes to its first field."""
        for name in ("speech", "describe"):
            self._stop(name)
        self.replies = {index: reply} if reply else {}
        self.index = index
        self.pages[index].Show()
        on_show = getattr(self, "_on_show_" + PAGES[index], None)
        if on_show is not None:
            on_show()
        self._refresh_texts()
        # The focus moves before the page it was on is hidden, so it never
        # falls to the window in between.
        target = self.focus_target(index)
        target.SetFocus()
        if isinstance(target, wx.TextCtrl):
            target.SelectAll()
        for i, panel in enumerate(self.pages):
            if i != index and panel.IsShown():
                panel.Hide()
        self._relayout()
        self._later("speech", SPEAK_DELAY_MS, self._say, self._page_speech(index))

    def focus_target(self, index=None):
        page = PAGES[self.index if index is None else index]
        return {"hello": self.choice_language, "name": self.txt_name, "where": self.txt_city,
                "birthday": self.choice_day, "aruna": self.txt_try, "extensions": self.list_ext,
                "startup": self.chk_autostart, "done": self.btn_next}[page]

    def on_next(self, event=None):
        if self.installing:
            self._say(_("onb_install_wait"), True)
            return
        if self.install_done:
            self._close(wx.ID_OK)
            return
        page = PAGES[self.index]
        if page == "done":
            self.finish()
            return
        if not self._leave(page):
            return
        self.show_page(self.index + 1, self._reply_after(page))

    def on_back(self, event=None):
        if self.index > 0 and not self.installing and not self.install_done:
            self.show_page(self.index - 1)

    def _leave(self, page):
        """Whether the page can be left with Next; if not, it says why."""
        if page == "where":
            query = " ".join(self.txt_city.GetValue().split())
            if len(query) >= onboarding.CITY_MIN_LENGTH and query != self._searched:
                self._on_search()   # typed but not searched yet: search first
                return False
        if page == "birthday":
            try:
                onboarding.check_birthday(*self._birthday_fields())
            except core.personal.ProfileError as e:
                self._birthday_error(e)
                return False
            self.lbl_birthday_error.SetLabel("")
        return True

    def _reply_after(self, page):
        """What Hariku answers to the page being left, said at the top of the next."""
        if page == "name":
            return onboarding.name_reply(self._nickname())
        if page == "where":
            place = self.city or self.main
            self._reply_place = place
            if not place:
                return ""
            weather = self._weather.get(onboarding.weather_key(place))
            self._reply_weather = bool(weather)
            return onboarding.place_sentence(place, weather=weather)
        if page == "birthday":
            return onboarding.birthday_reply(self._birthday())
        return ""

    # --- hello --------------------------------------------------------------

    def _on_language(self, event):
        code = self._language()
        if code and core.i18n.use_language(code):
            self._refresh_texts()
            self._relayout()
            # The screen reader only read the new choice: say the page again, in it.
            self._later("speech", SPEAK_DELAY_MS, self._say,
                        f"{onboarding.question('hello')} {_('onb_hello_intro')}")
        event.Skip()

    # --- name ---------------------------------------------------------------

    def _on_name_text(self, event):
        if self._nick_auto:
            self.txt_nickname.ChangeValue(onboarding.first_word(self.txt_name.GetValue()))
        event.Skip()

    def _on_nickname_text(self, event):
        # Typed by the user: it no longer follows the name (unless emptied).
        self._nick_auto = not self.txt_nickname.GetValue().strip()
        event.Skip()

    # --- where --------------------------------------------------------------

    def _cities_label(self):
        if not self._cities_answered:
            return _("onb_where_results")
        if self.cities:
            return _("onb_where_results_count", count=len(self.cities))
        return _("onb_where_results_none")

    def _place_words(self, place):
        label = place.get("label") or core.places.point_text(place["lat"], place["lon"])
        return f"{place['name']}: {label}"

    def _chosen_text(self):
        if self.city:
            return self.city.get("label") or self.city.get("name") or ""
        if self.main:
            return _("onb_where_chosen_keep", place=self._place_words(self.main))
        return _("onb_where_chosen_none")

    def _where_intro(self):
        text = _("onb_where_intro")
        if self.main:
            text = f"{_('onb_where_intro_keep', place=self._place_words(self.main))} {text}"
        return text

    def _on_show_where(self):
        if self.main and not self.city:
            self._want_weather(self.main)

    def _on_search(self, event=None):
        query = " ".join(self.txt_city.GetValue().split())
        if len(query) < onboarding.CITY_MIN_LENGTH:
            self._say(_("places_city_too_short", count=onboarding.CITY_MIN_LENGTH), True)
            return
        self._search_id += 1
        self._searched = query
        self._say(_("onb_where_searching", query=query), True)
        language = "id" if core.i18n.get_current_language() == "id" else "en"
        threading.Thread(target=self._search_worker, args=(self._search_id, query, language),
                         daemon=True, name="hariku-welcome-city").start()

    def _search_worker(self, search_id, query, language):
        found, error = onboarding.search_cities(query, language)
        wx.CallAfter(self._on_cities, search_id, query, found, error)

    def _on_cities(self, search_id, query, found, error):
        if not self or self._closed or search_id != self._search_id:
            return   # closed, or a newer search is running
        if error:
            self._say(_("onb_where_failed"), True)
            return
        self.cities = list(found)
        self._cities_answered = True
        self.list_cities.Set([f.get("label") or f.get("name") for f in self.cities])
        self._refresh_texts()
        self._relayout()
        if not self.cities:
            self._say(_("onb_where_none", query=query), True)
            return
        self.list_cities.SetSelection(0)
        self._choose_city(self.cities[0])
        self._want_weather(self.cities[0])
        # The user pressed Search and is waiting there: take them to the results.
        if wx.Window.FindFocus() in (self.txt_city, self.btn_search):
            self.list_cities.SetFocus()
        else:
            self._say(_("onb_where_found", count=len(self.cities)))

    def _on_city_selected(self, event):
        sel = self.list_cities.GetSelection()
        if 0 <= sel < len(self.cities):
            self._choose_city(self.cities[sel])   # state only: focus stays in the list
            self._later("weather", WEATHER_DELAY_MS, self._want_weather, dict(self.cities[sel]))
        event.Skip()

    def _choose_city(self, found):
        self.city = dict(found)
        self.txt_chosen.ChangeValue(self._chosen_text())

    def _want_weather(self, place):
        key = onboarding.weather_key(place)
        if key in self._weather or key in self._weather_pending:
            return
        self._weather_pending.add(key)
        threading.Thread(target=self._weather_worker, args=(dict(place), key), daemon=True,
                         name="hariku-welcome-weather").start()

    def _weather_worker(self, place, key):
        weather = onboarding.fetch_weather(place)
        wx.CallAfter(self._on_weather, place, key, weather)

    def _on_weather(self, place, key, weather):
        if not self or self._closed:
            return
        self._weather_pending.discard(key)
        self._weather[key] = weather
        # It came after the time was said: the birthday page's opening line gets it.
        if (weather and PAGES[self.index] == "birthday" and self._reply_place
                and not self._reply_weather
                and onboarding.weather_key(self._reply_place) == key):
            self._reply_weather = True
            self.replies[self.index] = onboarding.place_sentence(self._reply_place,
                                                                 weather=weather)
            self._refresh_texts()
            self._relayout()
            self._say(onboarding.weather_sentence(self._reply_place, weather))

    # --- birthday -----------------------------------------------------------

    def _birthday_fields(self):
        year = self.txt_year.GetValue().strip()
        return self.choice_day.GetSelection(), self.choice_month.GetSelection(), year or None

    def _birthday(self):
        try:
            return onboarding.check_birthday(*self._birthday_fields())
        except core.personal.ProfileError:
            return None

    def _birthday_error(self, error):
        message = str(error)
        self.lbl_birthday_error.SetLabel(message.replace("&", "&&"))
        self.lbl_birthday_error.Wrap(WRAP)
        self._relayout()
        ctrl = {"birthday_month": self.choice_month,
                "birthday_year": self.txt_year}.get(error.field, self.choice_day)
        ctrl.SetFocus()
        if isinstance(ctrl, wx.TextCtrl):
            ctrl.SelectAll()
        self._later("speech", ERROR_DELAY_MS, self._say, message, True)

    # --- Aruna --------------------------------------------------------------

    def _on_try(self, event=None):
        kind, answer = onboarding.try_answer(self.txt_try.GetValue())
        self.txt_answer.ChangeValue(answer)
        if kind in ("time", "date"):
            try:
                if core.commands.bar_settings()["sounds"]:
                    self._play(core.commands.REPLY_SOUND)
            except Exception:
                pass
        self._say(answer, True)
        self.txt_try.SelectAll()

    # --- extensions ---------------------------------------------------------

    def _store_worker(self):
        try:
            registry = core.store.fetch_registry() or []
        except Exception:
            logger.exception("Welcome: the store's list failed")
            registry = []
        try:
            installed = core.extension_manager.get_installed_extensions_info()
        except Exception:
            logger.exception("Welcome: reading the installed extensions failed")
            installed = []
        wx.CallAfter(self._on_store, registry, installed)

    def _on_store(self, registry, installed):
        if not self or self._closed:
            return
        self.registry, self.installed = list(registry), list(installed)
        if PAGES[self.index] == "extensions":
            self._fill_extensions()
            self._refresh_texts()
            self._relayout()
            self._say(_("onb_ext_ready", count=len(self.offers)) if self.offers
                      else self._ext_state_text())

    def _ext_state_text(self):
        if self.registry is None:
            return _("onb_ext_loading")
        if not self.registry:
            return _("onb_ext_offline", shortcut=self.store_key)
        if not self.offers:
            return _("onb_ext_all_installed", shortcut=self.store_key)
        return _("onb_ext_intro", shortcut=self.store_key)

    def _on_show_extensions(self):
        if self.registry is not None:
            self._fill_extensions()

    def _fill_extensions(self):
        self.offers = onboarding.recommendations(self.installed, self.registry,
                                                 has_place=bool(self.city or self.main))
        if self._ext_checked is None:
            self._ext_checked = {o["id"] for o in self.offers if o["checked"]}
            self._ext_default = set(self._ext_checked)
        sel = max(0, self.list_ext.GetSelection())
        self.list_ext.Set([o["name"] for o in self.offers])
        for i, offer in enumerate(self.offers):
            self.list_ext.Check(i, offer["id"] in self._ext_checked)
        if self.offers:
            self.list_ext.SetSelection(min(sel, len(self.offers) - 1))
        self._show_ext_details()

    def _show_ext_details(self):
        sel = self.list_ext.GetSelection()
        if 0 <= sel < len(self.offers):
            offer = self.offers[sel]
            _change(self.txt_ext_details, f"{offer['name']} {offer['version']}\n"
                    f"{onboarding.description(offer['id'], offer['description'])}")
        else:
            _change(self.txt_ext_details, "")

    def _on_ext_selected(self, event):
        self._show_ext_details()
        sel = self.list_ext.GetSelection()
        if 0 <= sel < len(self.offers):
            # Once the arrow keys rest, and only while the user is still there.
            self._later("describe", DESCRIBE_DELAY_MS, self._describe, sel)
        event.Skip()

    def _describe(self, sel):
        if (sel < len(self.offers) and wx.Window.FindFocus() is self.list_ext
                and self.list_ext.GetSelection() == sel):
            self._say(onboarding.description(self.offers[sel]["id"],
                                             self.offers[sel]["description"]))

    def _on_ext_checked(self, event):
        index = event.GetInt()
        if 0 <= index < len(self.offers) and self._ext_checked is not None:
            ext_id = self.offers[index]["id"]
            if self.list_ext.IsChecked(index):
                self._ext_checked.add(ext_id)
            else:
                self._ext_checked.discard(ext_id)
        event.Skip()

    def chosen_extensions(self):
        checked = self._ext_checked or set()
        return [o for o in self.offers if o["id"] in checked]

    # --- done ---------------------------------------------------------------

    def _summary_lines(self):
        return onboarding.summary(self._answers(), place=self.city or self.main,
                                  aruna_key=self.aruna_key,
                                  extensions=self.chosen_extensions())

    def _on_show_done(self):
        self.txt_summary.ChangeValue("\n".join(self._summary_lines()))
        self._play(DONE_SOUND)

    # ------------------------------------------------------------
    # Finish, Cancel
    # ------------------------------------------------------------

    def _answers(self):
        return onboarding.Answers(
            language=self._language() or self.answers.language,
            name=self.txt_name.GetValue(), nickname=self.txt_nickname.GetValue(),
            place=self.city, birthday=self._birthday(),
            autostart=self.chk_autostart.GetValue(), greet=self.chk_greet.GetValue(),
            extensions=[o["id"] for o in self.chosen_extensions()])

    def changed(self):
        """Whether the user entered anything: the language alone doesn't
        count, nor the extensions ticked for them."""
        now, before = self._answers(), self._before.copy()
        before.language, before.extensions = now.language, now.extensions
        return now != before or self._ext_checked != self._ext_default

    def finish(self):
        answers = self._answers()
        self.outcome.saved = onboarding.save(answers, first_run=self.first_run)
        self.outcome.finished = True
        self.outcome.language_changed = answers.language != self.opened_language
        extensions = self.chosen_extensions()
        if not extensions:
            self._close(wx.ID_OK)
            return
        # Settings are saved; the downloads may take a while, with Finish
        # (focused) closing the window once they are done.
        self.installing = True
        self._update_buttons()
        self.lbl_status.Show()
        self.txt_status.Show()
        text = onboarding.install_start_text(extensions)
        self.txt_status.ChangeValue(text)
        self._relayout()
        self._say(text, True)
        threading.Thread(target=self._install_worker, args=(extensions,), daemon=True,
                         name="hariku-welcome-install").start()

    def _install_worker(self, extensions):
        count = len(extensions)
        good, bad = onboarding.install(
            extensions, progress=lambda i, ext, ok: wx.CallAfter(self._on_installed, i, count,
                                                                 ext, ok))
        wx.CallAfter(self._on_install_done, good, bad)

    def _on_installed(self, index, count, ext, ok):
        if not self or self._closed:
            return
        text = onboarding.install_progress_text(index, count, ext, ok)
        self.txt_status.AppendText("\n" + text)
        self._say(text)

    def _on_install_done(self, good, bad):
        if not self or self._closed:
            return
        self.installing = False
        self.install_done = True
        self.outcome.installed = [e["id"] for e in good]
        self.outcome.failed = [e["id"] for e in bad]
        text = onboarding.install_summary(good, bad, self.store_key)
        self.txt_status.AppendText("\n" + text)
        self._update_buttons()
        self._say(text)

    def _confirm(self, message):
        dlg = wx.MessageDialog(self, message, _("onb_cancel_title"),
                               wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        try:
            return dlg.ShowModal() == wx.ID_YES
        finally:
            dlg.Destroy()

    def on_cancel(self, event=None):
        if self.installing:
            self._say(_("onb_install_wait"), True)
            return
        if self.outcome.finished:
            self._close(wx.ID_OK)
            return
        if self.changed() and not self._confirm(_("onb_cancel_message")):
            return
        language = onboarding.cancel(self.first_run, shown_language=self._language(),
                                     opened_language=self.opened_language)
        if language:
            core.i18n.use_language(language)
        self.outcome.cancelled = True
        self._close(wx.ID_CANCEL)

    def _close(self, code):
        self._closed = True
        for name in list(self._timers):
            self._stop(name)
        if self.IsModal():
            self.EndModal(code)
        else:
            self.Hide()

    def _on_close(self, event):
        if self._closed or not event.CanVeto():
            event.Skip()
            return
        event.Veto()
        self.on_cancel()

    def _on_char_hook(self, event):
        code = event.GetKeyCode()
        if event.HasAnyModifiers():
            event.Skip()
            return
        if code == wx.WXK_ESCAPE:
            self.on_cancel()
            return
        if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            focus = wx.Window.FindFocus()
            if isinstance(focus, wx.Button):
                event.Skip()   # the button itself
                return
            if focus in (self.txt_city, self.txt_try) and focus.GetValue().strip():
                event.Skip()   # searches, or tries
                return
            self.on_next()
            return
        event.Skip()


def run_onboarding(parent=None, first_run=False):
    """Show the welcome. On a first run Hariku goes on starting however it
    ends (see core.onboarding.cancel). From Help, when extensions were
    installed or the language changed, offer to restart. Returns whether it
    was finished."""
    dlg = OnboardingDialog(parent, first_run=first_run)
    try:
        dlg.ShowModal()
        outcome = dlg.outcome
    finally:
        dlg.Destroy()
    if not first_run and outcome.finished and (outcome.installed or outcome.language_changed):
        if outcome.installed:
            message, title = _("restart_required_msg"), _("restart_required_title")
        else:
            names = dict(onboarding.languages())
            language = names.get(core.i18n.get_current_language(), "")
            message = _("restart_language_msg", language=language)
            title = _("restart_language_title")
        if wx.MessageBox(message, title, wx.YES_NO | wx.ICON_INFORMATION, parent) == wx.YES:
            core.api.restart_app()
    return outcome.finished
