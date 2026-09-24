# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Preferences, Hariku Voice: which announcements a voice speaks (the greeting,
the Briefing, reminders, and answers to commands, which is on by default), the
source and voice, rate, volume, a Test button, the fallback and "Stop when I
press a key".

A voice is picked with three choices, each narrowing the next: Language (one
entry per locale, the user's languages first), Gender (All voices, Female,
Male, as that language has them) and Voice (the names). Voice lists are loaded
on worker threads (a provider may use the network). Changing a choice refills
the ones after it and never moves focus. Everything is saved on OK or Apply,
through core.voice.save_settings().

languages_for(), genders_for(), voices_for() and preselect() hold the
grouping, without wx, so tests can check it.
"""
import logging
import threading

import wx

import core.personal
import core.ui_scale
import core.voice
from core.core_panels import _labeled, _plain_label
from core.i18n import get_translator

_ = get_translator("core")

logger = logging.getLogger(__name__)

_KIND_LABELS = (("greeting", "voice_chk_greeting"), ("briefing", "voice_chk_briefing"),
                ("reminder", "voice_chk_reminder"), ("command", "voice_chk_command"))


# ------------------------------------------------------------
# Grouping the voices: Language, then Gender, then Voice
# ------------------------------------------------------------

def language_label(tag):
    """What the Language choice shows for a BCP-47 tag: Windows' name for it
    ("Indonesian (Indonesia)"), the tag itself when Windows doesn't know it,
    or "Unknown language" for voices without one."""
    if not tag:
        return _("voice_language_unknown")
    return core.voice.language_name(tag) or tag


def gender_label(gender):
    if gender == "female":
        return _("voice_gender_female")
    if gender == "male":
        return _("voice_gender_male")
    return _("voice_gender_all")


def _language_of(voice):
    return voice.get("language") or ""


def _gender_of(voice):
    gender = voice.get("gender")
    return gender if gender in core.voice.GENDERS else ""


def languages_for(voices, languages=None, name=language_label):
    """The Language choice: [(tag, label)], one entry per full locale tag
    ("en-US" and "en-GB" apart). The user's languages come first, in the order
    core.voice.order_voices() gives them (Hariku's language, then Windows'),
    then the rest alphabetically by label; voices without a language last.
    `languages` defaults to core.voice.user_languages(); `name(tag)` makes the
    label."""
    if languages is None:
        languages = core.voice.user_languages()
    preferred = [p for p in (core.voice._primary(tag) for tag in languages) if p]
    mine, rest, seen = [], [], set()
    for voice in core.voice.order_voices(voices, preferred):
        tag = _language_of(voice)
        if tag in seen:
            continue
        seen.add(tag)
        entry = (tag, name(tag))
        (mine if tag and core.voice._primary(tag) in preferred else rest).append(entry)
    rest.sort(key=lambda entry: (not entry[0], entry[1].casefold(), entry[0]))
    return mine + rest


def genders_for(voices, language):
    """The Gender choice for a language: [(gender, label)], "All voices" ("")
    first, then Female and Male if that language has such voices. Only "All
    voices" when none of its voices has a gender."""
    present = {_gender_of(v) for v in voices if _language_of(v) == language}
    return [("", gender_label(""))] + [(gender, gender_label(gender))
                                       for gender in core.voice.GENDERS if gender in present]


def voices_for(voices, language, gender=""):
    """The Voice choice: the voices of that language and gender ("" for all of
    them), sorted by name."""
    return sorted((v for v in voices if _language_of(v) == language
                   and (not gender or _gender_of(v) == gender)),
                  key=lambda v: (str(v.get("name") or "").casefold(), str(v.get("id"))))


def preselect(voices, voice_id, languages=None, name=language_label):
    """Where the three choices start, as (language, gender, voice id): the
    language of the voice `voice_id`, its gender ("" = All voices when it has
    none) and the voice itself. When it isn't listed, the first language
    (the first of the user's), All voices and that language's first voice.
    None when there are no voices."""
    for voice in voices:
        if voice_id and voice.get("id") == voice_id:
            return _language_of(voice), _gender_of(voice), voice_id
    listed = languages_for(voices, languages, name)
    if not listed:
        return None
    language = listed[0][0]
    return language, "", voices_for(voices, language)[0]["id"]


# ------------------------------------------------------------
# The page
# ------------------------------------------------------------

def _labeled_row(parent, sizer, label, make):
    """A label, then the control make() creates beside it, with the same
    accessible name. The label must exist first (see _labeled)."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    ctrl = make()
    ctrl.SetName(_plain_label(label))
    sizer.Add(ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 15)
    return ctrl


def _speak(message, interrupt=False):
    from core.speech import speak
    speak(message, interrupt=interrupt)


def _call_after(fn, *args):
    """wx.CallAfter from a worker thread, unless Hariku is already closing."""
    try:
        if wx.GetApp() is not None:
            wx.CallAfter(fn, *args)
    except Exception:
        pass


def _set_choice(choice, labels, index=0, enabled=True):
    choice.Set(labels)
    if labels:
        choice.SetSelection(max(0, min(index, len(labels) - 1)))
    choice.Enable(enabled)


class VoiceSettingsPanel(wx.ScrolledWindow):
    def __init__(self, parent):
        super().__init__(parent, style=wx.TAB_TRAVERSAL | wx.VSCROLL)
        self.SetScrollRate(0, 20)
        self._settings = core.voice.get_settings()
        self._alive = True
        self._voices = {}          # provider id -> ordered voices, once loaded
        self._errors = {}          # provider id -> why its voices couldn't be listed
        self._loading = set()
        self._chosen = {}          # provider id -> voice id picked on this page
        self._picked = {}          # (provider id, language) -> (gender, voice id) last picked there
        self._language_tags = []   # what the Language, Gender and Voice choices hold,
        self._genders = []         # item by item (empty while they show a message)
        self._rows = []
        self._filling = False
        self._shown = None         # provider whose voices the choices show
        self._language_names = {}
        self._fallback_ids = [""]

        providers = core.voice.get_providers()
        self._provider_ids = [p["id"] for p in providers]
        self._provider_notes = {p["id"]: p["privacy_note"] for p in providers}
        names = [p["name"] for p in providers]
        saved = self._settings["provider"]
        if saved not in self._provider_ids:
            # Its extension is off or gone; keep it until the user picks another.
            self._provider_ids.append(saved)
            names.append(_("voice_source_missing", source=saved))

        vbox = wx.BoxSizer(wx.VERTICAL)
        # Right before the first checkbox, so screen readers say it with it.
        lbl_help = wx.StaticText(self, label=_("voice_help"))
        lbl_help.Wrap(520)
        vbox.Add(lbl_help, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.chk_kinds = {}
        for kind, key in _KIND_LABELS:
            chk = wx.CheckBox(self, label=_(key))
            chk.SetName(_plain_label(_(key)))
            chk.SetValue(self._settings["kinds"][kind])
            vbox.Add(chk, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
            self.chk_kinds[kind] = chk

        # Each label is created right before its control (the factories run
        # after it): screen readers name a control after the static text just
        # before it in window order; SetName alone doesn't.
        self.choice_source = _labeled(self, vbox, _("voice_lbl_source"),
                                      lambda: wx.Choice(self, choices=names))
        self.choice_source.SetSelection(self._provider_ids.index(saved))

        # Language, then gender, then the voice: each one narrows the next.
        self.choice_language = _labeled(self, vbox, _("voice_lbl_language"),
                                        lambda: wx.Choice(self, choices=[]))
        self.choice_gender = _labeled(self, vbox, _("voice_lbl_gender"),
                                      lambda: wx.Choice(self, choices=[]))
        self.choice_voice = _labeled(self, vbox, _("voice_lbl_voice"),
                                     lambda: wx.Choice(self, choices=[]))

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.spin_rate = _labeled_row(
            self, row, _("voice_lbl_rate"),
            lambda: wx.SpinCtrl(self, min=core.voice.RATE_MIN, max=core.voice.RATE_MAX,
                                initial=self._settings["rate"], size=(80, -1)))
        self.spin_volume = _labeled_row(
            self, row, _("voice_lbl_volume"),
            lambda: wx.SpinCtrl(self, min=core.voice.VOLUME_MIN, max=core.voice.VOLUME_MAX,
                                initial=self._settings["volume"], size=(80, -1)))
        self.btn_test = wx.Button(self, label=_("voice_btn_test"))
        row.Add(self.btn_test, 0, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(row, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.choice_fallback = _labeled(self, vbox, _("voice_lbl_fallback"),
                                        lambda: wx.Choice(self, choices=[]))
        self._fill_fallback()

        label = _("voice_chk_stop_on_key")
        self.chk_stop_on_key = wx.CheckBox(self, label=label)
        self.chk_stop_on_key.SetName(_plain_label(label))
        self.chk_stop_on_key.SetValue(self._settings["stop_on_key"])
        vbox.Add(self.chk_stop_on_key, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # Read-only but in the Tab order, so screen reader users can reach it.
        self.txt_privacy = _labeled(
            self, vbox, _("voice_lbl_privacy"),
            lambda: wx.TextCtrl(self, style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 70)))
        vbox.AddSpacer(10)
        self.SetSizer(vbox)

        self.choice_source.Bind(wx.EVT_CHOICE, self.on_source)
        self.choice_language.Bind(wx.EVT_CHOICE, self.on_language)
        self.choice_gender.Bind(wx.EVT_CHOICE, self.on_gender)
        self.choice_voice.Bind(wx.EVT_CHOICE, self.on_voice)
        self.btn_test.Bind(wx.EVT_BUTTON, self.on_test)
        for spin in (self.spin_rate, self.spin_volume):
            spin.Bind(wx.EVT_SPINCTRL, lambda event: (self._mark_dirty(), event.Skip()))
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        # The fallback lists Windows voices whichever source is chosen.
        self._request(core.voice.WINDOWS)
        self._show(self._selected_provider())
        core.ui_scale.apply_appearance(self)

    # --- helpers -----------------------------------------------------------------

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._alive = False
        event.Skip()

    def _mark_dirty(self):
        top = wx.GetTopLevelParent(self)
        if top is not None and hasattr(top, "is_dirty"):
            top.is_dirty = True

    # --- voices ----------------------------------------------------------------

    def _selected_provider(self):
        index = self.choice_source.GetSelection()
        return self._provider_ids[index] if 0 <= index < len(self._provider_ids) else \
            core.voice.WINDOWS

    def _request(self, provider_id):
        """List the provider's voices on a worker thread, once."""
        if provider_id in self._loading or provider_id in self._voices:
            return
        self._loading.add(provider_id)

        def work():
            try:
                voices, error = core.voice.order_voices(core.voice.list_voices(provider_id)), None
            except Exception as e:
                voices, error = None, e
            _call_after(self._loaded, provider_id, voices, error)

        threading.Thread(target=work, daemon=True, name="hariku-voice-list").start()

    def _loaded(self, provider_id, voices, error):
        try:
            if not self._alive or not self:
                return   # Preferences closed meanwhile
        except RuntimeError:
            return
        self._loading.discard(provider_id)
        if error is not None:
            logger.warning(f"Hariku Voice: could not list the voices of {provider_id}: {error}")
            self._errors[provider_id] = str(error) or type(error).__name__
        else:
            self._voices[provider_id] = voices
            self._errors.pop(provider_id, None)
        if provider_id == core.voice.WINDOWS:
            self._fill_fallback()
        if provider_id == self._shown:
            self._fill_choices()

    def _show(self, provider_id):
        self._shown = provider_id
        self.txt_privacy.SetValue(self._provider_notes.get(provider_id, ""))
        if provider_id in self._voices or provider_id in self._errors:
            self._fill_choices()
        else:
            self._message(_("voice_loading"), loading=True)
            if provider_id in self._provider_notes:
                self._request(provider_id)
            else:
                self._errors[provider_id] = _("voice_source_missing", source=provider_id)
                self._fill_choices()

    def _language(self, tag):
        if tag not in self._language_names:
            self._language_names[tag] = language_label(tag)
        return self._language_names[tag]

    def _message(self, text, loading=False):
        """One item instead of the voices: "Loading voices…" in all three
        choices, or why there are none in Language, with Gender and Voice
        empty and disabled."""
        self._filling = True
        try:
            self._language_tags, self._genders, self._rows = [], [], []
            _set_choice(self.choice_language, [text])
            for choice in (self.choice_gender, self.choice_voice):
                _set_choice(choice, [text] if loading else [], enabled=loading)
        finally:
            self._filling = False

    def _wanted_voice(self, provider_id):
        if provider_id in self._chosen:
            return self._chosen[provider_id]
        return self._settings["voice"] if provider_id == self._settings["provider"] else ""

    def _shown_voices(self):
        return self._voices.get(self._shown) or []

    def _selected_language(self):
        index = self.choice_language.GetSelection()
        return self._language_tags[index] if 0 <= index < len(self._language_tags) else None

    def _selected_gender(self):
        index = self.choice_gender.GetSelection()
        return self._genders[index] if 0 <= index < len(self._genders) else ""

    def _fill_gender(self, language, gender):
        genders = genders_for(self._shown_voices(), language)
        self._genders = [key for key, _label in genders]
        _set_choice(self.choice_gender, [label for _key, label in genders],
                    self._genders.index(gender) if gender in self._genders else 0)

    def _fill_voice(self, language, gender, voice_id=None):
        """The voices of that language and gender, with voice_id selected when
        it is one of them, else the first."""
        self._rows = voices_for(self._shown_voices(), language, gender)
        ids = [voice["id"] for voice in self._rows]
        _set_choice(self.choice_voice, [voice["name"] for voice in self._rows],
                    ids.index(voice_id) if voice_id in ids else 0)

    def _fill_choices(self):
        """The source changed or its voices arrived: fill Language, Gender and
        Voice at the saved (or already picked) voice."""
        provider_id = self._shown
        if provider_id in self._errors:
            self._message(_("voice_load_failed", error=self._errors[provider_id]))
            return
        voices = self._shown_voices()
        if not voices:
            self._message(_("voice_none"))
            return
        listed = languages_for(voices, name=self._language)
        language, gender, voice_id = preselect(voices, self._wanted_voice(provider_id),
                                               name=self._language)
        remembered = self._picked.get((provider_id, language))
        if remembered and remembered[1] == voice_id:
            gender = remembered[0]          # as the user left it
        self._filling = True
        try:
            self._language_tags = [tag for tag, _label in listed]
            _set_choice(self.choice_language, [label for _tag, label in listed],
                        self._language_tags.index(language))
            self._fill_gender(language, gender)
            self._fill_voice(language, self._selected_gender(), voice_id)
        finally:
            self._filling = False
        self._chosen.setdefault(provider_id, self.selected_voice())
        self._picked.setdefault((provider_id, language),
                                (self._selected_gender(), self.selected_voice()))

    def selected_voice(self):
        """The voice selected in the Voice choice, or None (nothing loaded, or a message)."""
        index = self.choice_voice.GetSelection()
        return self._rows[index]["id"] if 0 <= index < len(self._rows) else None

    def _voice_to_save(self, provider_id):
        if provider_id in self._voices:
            if provider_id == self._shown:
                selected = self.selected_voice()
                if selected is not None:
                    return selected
            return self._chosen.get(provider_id, "")
        # Not listed (still loading, or it failed): keep what was saved.
        return self._wanted_voice(provider_id)

    def _fill_fallback(self):
        chosen = self._fallback_ids[self.choice_fallback.GetSelection()] \
            if 0 <= self.choice_fallback.GetSelection() < len(self._fallback_ids) \
            else self._settings["fallback"]
        ids, labels = [""], [_("voice_fallback_reader")]
        voices = self._voices.get(core.voice.WINDOWS)
        if voices is None and chosen:
            ids.append(chosen)                 # until the list arrives, or if it can't
            labels.append(chosen.rsplit("\\", 1)[-1] if core.voice.WINDOWS in self._errors
                          else _("voice_loading"))
        for voice in voices or ():
            ids.append(voice["id"])
            labels.append(_("voice_row", name=voice["name"],
                            language=self._language(voice["language"])))
        self._fallback_ids = ids
        self.choice_fallback.Set(labels)
        self.choice_fallback.SetSelection(ids.index(chosen) if chosen in ids else 0)

    # --- events ----------------------------------------------------------------
    # Changing a choice refills only the ones after it; focus stays where it is.

    def on_source(self, event):
        self._show(self._selected_provider())
        event.Skip()

    def on_language(self, event):
        language = self._selected_language()
        if not self._filling and language is not None:
            # The voice last picked in this language on this page, else the first.
            gender, voice_id = self._picked.get((self._shown, language), ("", None))
            self._filling = True
            try:
                self._fill_gender(language, gender)
                self._fill_voice(language, self._selected_gender(), voice_id)
            finally:
                self._filling = False
            self._voice_changed(remember=False)
        event.Skip()

    def on_gender(self, event):
        language = self._selected_language()
        if not self._filling and language is not None:
            current = self.selected_voice()     # kept when it has this gender
            self._filling = True
            try:
                self._fill_voice(language, self._selected_gender(), current)
            finally:
                self._filling = False
            self._voice_changed()
        event.Skip()

    def on_voice(self, event):
        if not self._filling:
            self._voice_changed()
        event.Skip()

    def _voice_changed(self, remember=True):
        voice = self.selected_voice()
        if voice is None:
            return
        self._chosen[self._shown] = voice
        if remember:
            self._picked[(self._shown, self._selected_language())] = \
                (self._selected_gender(), voice)
        self._mark_dirty()

    def test_text(self):
        nickname = core.personal.get_nickname()
        return (_("voice_test_text", name=nickname) if nickname
                else _("voice_test_text_noname"))

    def on_test(self, event=None):
        provider_id = self._selected_provider()
        started = core.voice.preview(self.test_text(), provider_id,
                                     self._voice_to_save(provider_id),
                                     self.spin_rate.GetValue(), self.spin_volume.GetValue(),
                                     self.chk_stop_on_key.GetValue(), on_done=self._test_done)
        if not started:
            _speak(_("voice_test_unavailable"), True)

    def _test_done(self, error):
        if error is not None:
            _call_after(_speak, _("voice_test_failed", error=str(error) or type(error).__name__),
                        True)

    # --- saving ------------------------------------------------------------------

    def get_settings(self):
        provider_id = self._selected_provider()
        index = self.choice_fallback.GetSelection()
        return {
            "kinds": {kind: chk.GetValue() for kind, chk in self.chk_kinds.items()},
            "provider": provider_id,
            "voice": self._voice_to_save(provider_id),
            "rate": self.spin_rate.GetValue(),
            "volume": self.spin_volume.GetValue(),
            "fallback": self._fallback_ids[index] if 0 <= index < len(self._fallback_ids) else "",
            "stop_on_key": self.chk_stop_on_key.GetValue(),
        }

    def ValidateChanges(self):
        """None, or (message, control) for input Preferences must not save."""
        if not any(chk.GetValue() for chk in self.chk_kinds.values()):
            return None
        provider_id = self._selected_provider()
        if provider_id in self._voices and not self._voices[provider_id]:
            return _("voice_err_no_voices"), self.choice_source
        return None

    def ApplyChanges(self):
        self._settings = core.voice.normalize_settings(self.get_settings())
        core.voice.save_settings(self._settings)


_panel_instance = None


def create_voice_panel(parent):
    global _panel_instance
    _panel_instance = VoiceSettingsPanel(parent)
    return _panel_instance


def apply_voice_settings():
    if _panel_instance:
        try:
            _panel_instance.ApplyChanges()
        except RuntimeError:
            pass  # panel already destroyed
