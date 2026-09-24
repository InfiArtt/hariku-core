# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load Piper Voices through the real loader with real wxPython and open its page
in the real Preferences dialog with a fake voice catalogue. Check each
control's label comes right before it, watch the catalogue load on a worker
thread, arrow through the voice list and change the language (focus must stay
put, and Preferences must not think a setting changed), download a voice with
a fake downloader (the download dialog is answered by a timer, as a user
pressing Download would), decline a download with Cancel, cancel a running
download, remove a voice, refresh the catalogue, and close Preferences while a
download runs. Fails on any logged error.

Nothing is downloaded, started or played: the catalogue, model cards and
installers are fakes, piper.exe is never run (synthesize is refused), the
network and MCI are refused, and screen reader speech is captured through
on_before_speak.

Run by tests/test_piper_voices_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder so the user's real settings are never touched. Prints one
"OK" line per stage.
"""
import json
import logging
import os
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
# One spelling of the data folder, so the paths compared below match.
os.environ["APPDATA"] = os.path.abspath(os.environ["APPDATA"])


def _watchdog():
    print("TIMEOUT: the Piper Voices check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(240, _watchdog)
_timer.daemon = True
_timer.start()

# Nothing here needs the network; any attempt fails and is remembered.
import socket
import urllib.request

network_attempts = []


def _blocked(*args, **kwargs):
    network_attempts.append(args[0] if args else kwargs)
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked
socket.create_connection = _blocked

# Exceptions in wx event handlers are printed, not raised; collect them, and
# every error logged along the way.
problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    def emit(self, record):
        problems.append(f"logged by {record.name}: {record.getMessage()}")


logging.getLogger().addHandler(_ErrorLog(level=logging.ERROR))

import wx

app = wx.App(False)

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()
import core.api
import core.speech
import core.voice
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)
core.speech.braille = lambda text, interrupt=False: None
core.speech.speak_announced = lambda text, interrupt=False, braille=True: spoken.append(text)


def _no_mci(command):
    problems.append(f"MCI was used: {command}")
    raise core.voice.MciError(0, "MCI is disabled in the UI check")


core.voice._mci_send = _no_mci

core.api.save_data("Core", {"user_name": "Rafli", "user_nickname": "Bro",
                            "onboarding_completed": True, "language": "en",
                            "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad")})


def _unexpected_prompt(*args, **kwargs):
    problems.append(f"unexpected Yes/No prompt: {args}")
    return False


core.api.prompt_yes_no = _unexpected_prompt

from ui.main_window import MainWindow
frame = MainWindow(None, title="piper voices check")
print("OK main_window")

import core.extension_manager as em
em.load_unpacked_extension(os.path.join(ROOT, "extensions", "piper_voices"))
assert "piper_voices" in em.LOADED_EXTENSIONS, "Piper Voices did not load"
main = em.LOADED_EXTENSIONS["piper_voices"]["module"]
pui = sys.modules["piper_voices_ui"]
dl = sys.modules["piper_voices_download"]
store = sys.modules["piper_voices_store"]
catalogue = sys.modules["piper_voices_catalogue"]
synth = sys.modules["piper_voices_synth"]
text = sys.modules["piper_voices_text"]
_ = text._
assert "piper" in [p["id"] for p in core.voice.get_providers()]
assert not core.voice.is_provider_available("piper"), "available before anything was installed"
ROOT_DIR = store.root_dir()
assert ROOT_DIR == os.path.join(os.environ["APPDATA"], "Hariku2", "piper"), ROOT_DIR
print("OK load")

# --------------------------------------------------------------------------- #
# The fakes: a catalogue in voices.json's shape, model cards and installers
# --------------------------------------------------------------------------- #
CARD_ID = ("# Model card for news_tts (medium)\n\n"
           "* Language: id_ID (Indonesian, Indonesia)\n* Speakers: 1\n* Quality: medium\n"
           "* Samplerate: 22,050Hz\n\n## Dataset\n\n"
           "* URL: https://www.kaggle.com/code/mpwolke/indic-tts-malayalam-speech-corpus\n"
           "* License:  See URL\n\n## Training\n\n"
           "Finetuned from U.S. English lessac voice (medium quality).\n")
CARD_OTHER = ("# Model card\n\n## Dataset\n\n* URL: https://example.org/dataset\n"
              "* License: CC BY 4.0\n")


def entry(code, name, quality, model_size, config_size, english, country):
    family, region = code.split("_")
    key = f"{code}-{name}-{quality}"
    base = f"{family}/{code}/{name}/{quality}/"
    return key, {
        "key": key, "name": name, "quality": quality, "num_speakers": 1,
        "speaker_id_map": {}, "aliases": [],
        "language": {"code": code, "family": family, "region": region,
                     "name_native": english, "name_english": english,
                     "country_english": country},
        "files": {base + key + ".onnx": {"size_bytes": model_size, "md5_digest": "0" * 32},
                  base + key + ".onnx.json": {"size_bytes": config_size,
                                              "md5_digest": "1" * 32},
                  base + "MODEL_CARD": {"size_bytes": 316, "md5_digest": "2" * 32}},
    }


INDEX = dict([
    entry("id_ID", "news_tts", "medium", 62950044, 5050, "Indonesian", "Indonesia"),
    entry("en_US", "lessac", "medium", 63201294, 4885, "English", "United States"),
    entry("en_US", "lessac", "high", 113895201, 4883, "English", "United States"),
    entry("de_DE", "thorsten", "low", 63104526, 4943, "German", "Germany"),
])
ID_KEY, EN_KEY, SLOW_KEY, DE_KEY = ("id_ID-news_tts-medium", "en_US-lessac-medium",
                                    "en_US-lessac-high", "de_DE-thorsten-low")

fetches = []          # ("index" | key, on a worker thread?)
installs = []         # (what, card given?, on a worker thread?)
synthesized = []


def _worker():
    return threading.current_thread() is not threading.main_thread()


def fake_fetch_catalogue():
    fetches.append(("index", _worker()))
    time.sleep(0.2)                   # long enough to see "Loading..."
    return json.loads(json.dumps(INDEX))


def fake_fetch_model_card(voice):
    fetches.append((voice["key"], _worker()))
    time.sleep(0.05)
    return CARD_ID if voice["key"] == ID_KEY else CARD_OTHER


def fake_install_runtime(root, progress=None, cancelled=None):
    installs.append(("runtime", None, _worker()))
    for step in range(1, 5):
        time.sleep(0.03)
        if cancelled():
            raise dl.Cancelled()
        progress(dl.RUNTIME_SIZE * step // 4)
    exe = store.exe_path(root)
    os.makedirs(os.path.dirname(exe), exist_ok=True)
    with open(exe, "wb") as f:
        f.write(b"MZ")
    store.write_runtime_marker(root, {"version": dl.RUNTIME_VERSION})


def fake_install_voice(voice, root, card_text=None, progress=None, cancelled=None):
    installs.append((voice["key"], card_text is not None, _worker()))
    delay = 0.25 if voice["key"] == SLOW_KEY else 0.03
    for step in range(1, 11):
        time.sleep(delay)
        if cancelled():
            store.discard_partials(store.voice_dir(root, voice["key"]))
            raise dl.Cancelled()
        progress(voice["size"] * step // 10)
    folder = store.voice_dir(root, voice["key"])
    os.makedirs(folder, exist_ok=True)
    for role in ("model", "config"):
        with open(os.path.join(folder, voice["files"][role]["path"].rsplit("/", 1)[-1]),
                  "wb") as f:
            f.write(b"x")
    store.write_voice_marker(root, voice, catalogue.parse_model_card(card_text or ""))


def refuse_network(*args, **kwargs):
    network_attempts.append(("open_url", args))
    raise dl.DownloadError("offline", "network is disabled in the UI check")


def refuse_synthesis(*args, **kwargs):
    synthesized.append(args)
    raise synth.PiperError("piper.exe is not run in the UI check")


dl.fetch_catalogue = fake_fetch_catalogue
dl.fetch_model_card = fake_fetch_model_card
dl.install_runtime = fake_install_runtime
dl.install_voice = fake_install_voice
dl.open_url = refuse_network
synth.synthesize = refuse_synthesis

# The Remove confirmation is a native message box, which can't be driven from
# here: record it and answer Yes.
confirms = []
pui._confirm = lambda parent, message, title: confirms.append((title, message)) or True

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def pump(condition, timeout=5.0):
    """Process events until condition() is true or the timeout passes. Runs an
    event loop of its own: wx.Yield() alone never delivers timer events here."""
    loop = wx.GUIEventLoop()
    previous = wx.EventLoop.GetActive()
    wx.EventLoop.SetActive(loop)
    try:
        end = time.time() + timeout
        while True:
            while loop.Pending():
                loop.Dispatch()
            app.ProcessPendingEvents()
            if condition():
                return True
            if time.time() > end:
                return False
            time.sleep(0.02)
    finally:
        wx.EventLoop.SetActive(previous)


def fire(ctrl, event_type, index=None):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    if index is not None:
        evt.SetInt(index)
    ctrl.GetEventHandler().ProcessEvent(evt)
    wx.Yield()


answered = []


def answer_download_dialog(result, tries=100):
    """Poll for the download dialog and close it with `result` (wx.ID_OK is
    its Download button, wx.ID_CANCEL its Cancel button and Escape), noting
    what it showed. The dialog opens once the model card has arrived."""
    def step(left):
        for window in wx.GetTopLevelWindows():
            if isinstance(window, pui.ConfirmDownloadDialog) and window.IsModal():
                answered.append({
                    "title": window.GetTitle(),
                    "summary": window.summary_text,
                    "static": window.lbl_summary.GetLabel(),
                    "card": window.txt_card.GetValue(),
                    "card_name": window.txt_card.GetName(),
                    "card_editable": window.txt_card.IsEditable(),
                    "escape": window.GetEscapeId(),
                    "affirmative": window.GetAffirmativeId(),
                    "default": window.GetDefaultItem() is window.btn_download,
                    "ids": (window.btn_download.GetId(), window.btn_cancel.GetId()),
                    "focus": wx.Window.FindFocus(),
                    "button": window.btn_download,
                })
                window.EndModal(result)
                return
        if left > 0:
            wx.CallLater(50, step, left - 1)
        else:
            problems.append("the download dialog never opened")

    wx.CallLater(50, step, tries)


def rows(lst):
    return [tuple(lst.GetItemText(i, c) for c in range(lst.GetColumnCount()))
            for i in range(lst.GetItemCount())]


def select_key(panel, key):
    index = [v["key"] for v in panel._rows].index(key)
    state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    panel.list_voices.SetItemState(index, state, state)
    pump(lambda: False, timeout=0.05)
    assert panel.selected_key() == key, (panel.selected_key(), key)
    return index


def row_of(panel, key):
    return rows(panel.list_voices)[[v["key"] for v in panel._rows].index(key)]


def choose_language(panel, label):
    index = panel.choice_language.FindString(label)
    assert index != wx.NOT_FOUND, (label, panel.choice_language.GetStrings())
    panel.choice_language.SetSelection(index)
    fire(panel.choice_language, wx.EVT_CHOICE, index)


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


def said_since(mark):
    return spoken[mark:]


LABELED = (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl, wx.ListBox, wx.SpinCtrl,
           wx.Slider, wx.Gauge)


def plain(label):
    return " ".join(label.replace("&&", "\0").replace("&", "").replace("\0", "&")
                    .strip().rstrip(":").split())


def check_labels(page):
    """Every input control comes right after a StaticText with its label (what
    screen readers read), and no file or folder picker hides an unlabelled
    field. Returns how many were checked."""
    children = list(page.GetChildren())
    checked = 0
    for index, child in enumerate(children):
        assert not isinstance(child, (wx.FilePickerCtrl, wx.DirPickerCtrl)), \
            f"{type(child).__name__} on the page"
        if not isinstance(child, LABELED):
            continue
        before = children[index - 1] if index > 0 else None
        assert isinstance(before, wx.StaticText), \
            f"{type(child).__name__} {child.GetName()!r} has no label right before it"
        assert child.GetName() == plain(before.GetLabel()), (child.GetName(), before.GetLabel())
        checked += 1
    return checked


# --------------------------------------------------------------------------- #
# The page, and the catalogue loading when it shows
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab=_("ext_name"))
prefs.Show()
pages = [prefs.treebook.GetPageText(i) for i in range(prefs.treebook.GetPageCount())]
assert pages[prefs.treebook.GetSelection()] == "Piper Voices", pages
panel = main._panel
assert panel is not None and panel.IsShown(), "the Piper Voices page was not created or shown"
assert panel.choice_language.GetName() == "Language"
assert panel.list_voices.GetName() == "Voices"
assert panel.txt_status.GetName() == "Status"
assert panel.txt_details.GetName() == "Details"
assert panel.gauge.GetName() == "Download progress"
assert check_labels(panel) == 5, "language, voices, status, details and progress"
assert not panel.txt_status.IsEditable() and not panel.txt_details.IsEditable()
assert panel.txt_details.IsMultiLine()
assert [panel.list_voices.GetColumn(c).GetText() for c in range(5)] == \
    ["Name", "Language", "Quality", "Size", "Installed"]
assert [b.GetLabel() for b in (panel.btn_download, panel.btn_remove, panel.btn_refresh,
                               panel.btn_cancel)] == \
    ["&Download...", "&Remove", "Re&fresh catalogue", "&Cancel download"]

# Only the page on show loads the list; it does so on a worker, once.
assert pump(lambda: fetches), "the catalogue was not requested when the page showed"
assert rows(panel.list_voices)[0][0] == _("loading"), rows(panel.list_voices)
assert pump(lambda: panel._voices is not None and not panel._loading), "the catalogue never loaded"
assert fetches == [("index", True)], fetches
assert os.path.isfile(os.path.join(ROOT_DIR, store.CATALOGUE_FILE)), "the catalogue was not saved"
assert panel.txt_status.GetValue() == _("status_ready", count=4, installed=0), \
    panel.txt_status.GetValue()
english_label = text.family_label("en", [])
assert panel.choice_language.GetString(0) == english_label, panel.choice_language.GetStrings()
all_index = panel.choice_language.FindString(_("language_all"))
assert all_index >= 1, panel.choice_language.GetStrings()
# English first (Hariku's language): Lessac medium, then high.
assert [v["key"] for v in panel._rows] == [EN_KEY, SLOW_KEY], [v["key"] for v in panel._rows]
assert [r[2] for r in rows(panel.list_voices)] == ["Medium", "High"]
assert [r[4] for r in rows(panel.list_voices)] == ["Not installed", "Not installed"]
assert rows(panel.list_voices)[0][3] == "60.3 MB", rows(panel.list_voices)
assert panel.selected_key() == EN_KEY
assert "Lessac" in panel.txt_details.GetValue()
assert "shown when you press Download" in panel.txt_details.GetValue()
assert not prefs.is_dirty, "loading the page marked Preferences as changed"
print("OK page")

# --------------------------------------------------------------------------- #
# Browsing: focus stays on the list; the details follow the selection
# --------------------------------------------------------------------------- #
state = {"focus": True}
lst = panel.list_voices
lst.SetFocus()
pump(lambda: wx.Window.FindFocus() is lst, timeout=1.0)
observable = wx.Window.FindFocus() is lst
selected = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
for i in list(range(lst.GetItemCount())) + [0]:
    lst.SetItemState(i, selected, selected)
    pump(lambda: False, timeout=0.05)
    assert lst.GetFirstSelected() == i
    assert panel._rows[i]["name"].split("_")[0].capitalize() in panel.txt_details.GetValue()
    if observable:
        assert wx.Window.FindFocus() is lst, f"focus left the voice list at row {i}"

# All languages: English stays first, then German and Indonesian by language.
choice = panel.choice_language
choice.SetFocus()
pump(lambda: wx.Window.FindFocus() is choice, timeout=1.0)
choice_focus = wx.Window.FindFocus() is choice
prefs.is_dirty = False
choose_language(panel, _("language_all"))
assert [v["key"] for v in panel._rows] == [EN_KEY, SLOW_KEY, DE_KEY, ID_KEY], \
    [v["key"] for v in panel._rows]
assert panel.selected_key() == EN_KEY, "the selected voice was not kept"
if choice_focus:
    assert wx.Window.FindFocus() is choice, "changing the language moved focus"
assert not prefs.is_dirty, "the language filter was taken for an unsaved setting"
choose_language(panel, text.family_label("de", []))
assert [v["key"] for v in panel._rows] == [DE_KEY]
choose_language(panel, _("language_all"))
state["focus"] = observable and choice_focus
print(f"OK browse ({focus_note(state['focus'])})")

# --------------------------------------------------------------------------- #
# Download the Indonesian voice: the Piper program comes along
# --------------------------------------------------------------------------- #
select_key(panel, ID_KEY)
panel.btn_download.SetFocus()
pump(lambda: wx.Window.FindFocus() is panel.btn_download, timeout=1.0)
button_focus = wx.Window.FindFocus() is panel.btn_download
mark = len(spoken)
answer_download_dialog(wx.ID_OK)
fire(panel.btn_download, wx.EVT_BUTTON)
assert pump(lambda: answered, timeout=5), "the download dialog was not shown"
assert pump(lambda: main._downloads.current() is None and
            store.is_installed(ROOT_DIR, ID_KEY), timeout=10), "the download never finished"
pump(lambda: False, timeout=0.2)
dialog = answered[0]
assert dialog["title"] == _("confirm_title")
summary = dialog["summary"]
assert "Download the voice News tts, " in summary and "Medium quality?" in summary, summary
assert "Download size: 60.0 MB for the voice, plus 21.4 MB for the Piper program, which is " \
       "needed once. 81.5 MB in total." in summary, summary
assert "Dataset license: See URL" in summary, summary
assert _("license_unclear") in summary, summary
assert "News tts" in dialog["static"]        # the text screen readers read on opening
assert "URL: https://www.kaggle.com/code/mpwolke/indic-tts-malayalam-speech-corpus" in \
    dialog["card"] and "License: See URL" in dialog["card"], dialog["card"]
assert dialog["card_name"] == "Model card" and not dialog["card_editable"]
assert dialog["escape"] == wx.ID_CANCEL, "Escape must cancel"
assert dialog["affirmative"] == wx.ID_OK and dialog["default"], "Enter must download"
assert dialog["ids"] == (wx.ID_OK, wx.ID_CANCEL)
if dialog["focus"] is not None:
    assert dialog["focus"] is dialog["button"], "the dialog opened without focus on Download"
assert fetches[1:] == [(ID_KEY, True)], fetches
assert installs == [("runtime", None, True), (ID_KEY, True, True)], installs
said = said_since(mark)
expected = [_("status_card", name="News tts"),
            _("download_started", name="News tts", size="81.5 MB"),
            _("progress_spoken", percent=25), _("progress_spoken", percent=50),
            _("progress_spoken", percent=75), _("progress_spoken", percent=100),
            _("download_done", name="News tts")]
assert said == expected, said
assert row_of(panel, ID_KEY)[4] == "Installed"
assert panel.gauge.GetValue() == 100
assert panel.txt_status.GetValue() == _("download_done", name="News tts")
details = panel.txt_details.GetValue()
assert "Installed on this computer." in details and "License: See URL" in details, details
assert core.voice.is_provider_available("piper")
assert core.voice.list_voices("piper") == [
    {"id": ID_KEY, "name": "News tts (Medium)", "language": "id-ID", "quality": "medium",
     "gender": ""}]   # Piper voices carry no gender; core.voice fills in ""
assert os.path.isfile(store.exe_path(ROOT_DIR))
if button_focus:
    assert wx.Window.FindFocus() is panel.btn_download, "focus moved during the download"
assert not prefs.is_dirty
print(f"OK download ({focus_note(button_focus)})")

# Download again: it is installed already; no dialog.
mark = len(spoken)
fire(panel.btn_download, wx.EVT_BUTTON)
pump(lambda: False, timeout=0.3)
assert said_since(mark) == [_("already_installed", name="News tts")], said_since(mark)
assert len(answered) == 1 and len(fetches) == 2
print("OK already_installed")

# --------------------------------------------------------------------------- #
# Decline in the dialog (its Cancel button, like Escape): nothing downloads
# --------------------------------------------------------------------------- #
select_key(panel, EN_KEY)
answer_download_dialog(wx.ID_CANCEL)
fire(panel.btn_download, wx.EVT_BUTTON)
assert pump(lambda: len(answered) == 2, timeout=5), "the download dialog was not shown"
pump(lambda: False, timeout=0.3)
summary = answered[1]["summary"]
assert "Piper program" not in summary and "Download size: 60.3 MB." in summary, summary
assert "Dataset license: CC BY 4.0" in summary and _("license_unclear") not in summary
assert main._downloads.current() is None and len(installs) == 2, installs
assert panel.txt_status.GetValue() == _("download_declined", name="Lessac")
assert "License: CC BY 4.0" in panel.txt_details.GetValue()
assert row_of(panel, EN_KEY)[4] == "Not installed"
print("OK download_declined")

# --------------------------------------------------------------------------- #
# Cancel a running download
# --------------------------------------------------------------------------- #
select_key(panel, SLOW_KEY)
mark = len(spoken)
answer_download_dialog(wx.ID_OK)
fire(panel.btn_download, wx.EVT_BUTTON)
assert pump(lambda: main._downloads.current() is not None and
            main._downloads.current().percent >= 10, timeout=5), "the download didn't start"
assert panel.gauge.GetValue() >= 10
assert panel.txt_status.GetValue().startswith("Downloading Lessac: ")
# A second download waits its turn.
select_key(panel, DE_KEY)
busy_mark = len(spoken)
fire(panel.btn_download, wx.EVT_BUTTON)
assert _("busy") in said_since(busy_mark), said_since(busy_mark)
fire(panel.btn_cancel, wx.EVT_BUTTON)
assert _("status_cancelling") in said_since(mark)
assert pump(lambda: main._downloads.current() is None, timeout=5), "cancel did not stop it"
pump(lambda: False, timeout=0.2)
assert spoken[-1] == _("download_cancelled"), spoken[-5:]
assert not store.is_installed(ROOT_DIR, SLOW_KEY)
assert installs[-1][0] == SLOW_KEY and [i[0] for i in installs].count("runtime") == 1
assert row_of(panel, SLOW_KEY)[4] == "Not installed"
assert panel.gauge.GetValue() == 0
assert panel.txt_status.GetValue() == _("download_cancelled")
mark = len(spoken)
fire(panel.btn_cancel, wx.EVT_BUTTON)
assert said_since(mark) == [_("nothing_downloading")], said_since(mark)
print("OK cancel_download")

# --------------------------------------------------------------------------- #
# Remove (with a confirmation)
# --------------------------------------------------------------------------- #
select_key(panel, EN_KEY)
mark = len(spoken)
fire(panel.btn_remove, wx.EVT_BUTTON)
assert said_since(mark) == [_("not_installed", name="Lessac")] and confirms == []
select_key(panel, ID_KEY)
fire(panel.btn_remove, wx.EVT_BUTTON)
assert confirms == [(_("confirm_remove_title"), _("confirm_remove", name="News tts"))], confirms
assert pump(lambda: _("removed", name="News tts") in spoken, timeout=2), spoken[-3:]
assert not store.is_installed(ROOT_DIR, ID_KEY)
assert not os.path.exists(store.voice_dir(ROOT_DIR, ID_KEY))
assert row_of(panel, ID_KEY)[4] == "Not installed"
assert "Not installed." in panel.txt_details.GetValue()
assert not core.voice.is_provider_available("piper")
assert core.voice.list_voices("piper") == []
assert store.runtime_installed(ROOT_DIR), "removing a voice removed the Piper program"
print("OK remove")

# --------------------------------------------------------------------------- #
# Refresh catalogue: fetched again, even though the saved one is fresh
# --------------------------------------------------------------------------- #
mark = len(spoken)
fire(panel.btn_refresh, wx.EVT_BUTTON)
assert pump(lambda: len(said_since(mark)) >= 2, timeout=5), said_since(mark)
assert said_since(mark) == [
    _("catalogue_refreshing"),
    f"{_('catalogue_refreshed')} {_('status_ready', count=4, installed=0)}"], said_since(mark)
assert [f for f in fetches if f[0] == "index"] == [("index", True), ("index", True)], fetches
assert panel.selected_key() == ID_KEY
assert not prefs.is_dirty
prefs.OnApply(None)          # nothing on this page waits for OK
prefs.Destroy()
wx.Yield()
pump(lambda: False, timeout=0.2)
print("OK refresh")

# --------------------------------------------------------------------------- #
# Reopen: the saved catalogue is used; close it while a download runs
# --------------------------------------------------------------------------- #
prefs = PreferencesDialog(frame, select_tab=_("ext_name"))
prefs.Show()
panel = main._panel
assert pump(lambda: panel._voices is not None and not panel._loading), "no catalogue on reopen"
assert [f for f in fetches if f[0] == "index"] == [("index", True)] * 2, "fetched again"
choose_language(panel, _("language_all"))
select_key(panel, SLOW_KEY)
mark = len(spoken)
answer_download_dialog(wx.ID_OK)
fire(panel.btn_download, wx.EVT_BUTTON)
assert pump(lambda: main._downloads.current() is not None, timeout=5), "the download didn't start"
prefs.Destroy()               # the download goes on without the page
wx.Yield()
pump(lambda: False, timeout=0.1)
assert pump(lambda: main._downloads.current() is None, timeout=10), "the download never finished"
pump(lambda: False, timeout=0.2)
assert spoken[-1] == _("download_done", name="Lessac"), spoken[-5:]
assert store.is_installed(ROOT_DIR, SLOW_KEY)
assert main._downloads._listeners == [], "the closed page still listens"
assert core.voice.is_provider_available("piper")
print("OK close_while_downloading")

# --------------------------------------------------------------------------- #
# Teardown, and nothing went wrong along the way
# --------------------------------------------------------------------------- #
em.unload_all_extensions()
assert "piper" not in [p["id"] for p in core.voice.get_providers()]
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
assert not synthesized, "piper.exe would have been started"
assert all(worker for _what, worker in fetches), fetches
assert all(i[2] for i in installs), installs
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
