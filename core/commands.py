# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
What the command bar (Ctrl+Alt+Backspace, since core 2.7) makes of a typed or
spoken command. No wx here; the window is ui/command_bar.py.

    decide(text)                  -> Decision: a reminder, an action to run, a
                                     "Did you mean …?", or not understood
    match(text)                   -> Match: every registered action, scored
    answer(text)                  -> "yes", "no" or None ("ya", "simpan", "batal")
    add_aliases(action_id, [...]) -> more ways to say an action (extensions)
    register_listener(...)        -> the speech recogniser (Voice Control)
    set_fallback(handler)         -> reserved for a future AI fallback
    add_answer_actions([...])     -> actions that only say something (core 2.8):
                                     Aruna stays open and shows their answer
    add_intent(id, [...], handler) -> commands with content (core 2.9): "catat
                                     {text}", "timer {text}"; handler(request)
                                     returns a Reply (say, confirm, wait, then)
    bar_settings()                -> Aruna's "keep open" and "sounds" (core 2.8)

How a command is matched
------------------------
Every hotkey action registered through core.hotkeys is a command, named by its
description in the Hariku language, plus its aliases: Hariku's own
(BUILTIN_ALIASES, for the core and the official extensions, in English and
Indonesian) and those extensions add. Speech recognisers get words wrong
("Gampak terbaru" for "Gempa terbaru"), so matching is fuzzy:

1. normalize(): lower case, accents and punctuation gone, hyphens are spaces,
   a letter said twice or more counts once ("saat" = "sat", "iyaa" = "iya").
2. Filler words that name no command ("tolong", "ucapkan", "the", "what") are
   dropped from both sides, unless nothing else is left.
3. Words are compared letter by letter (difflib): "gampak" is 0.73 like
   "gempa". Words of one or two letters and numbers must match exactly, and a
   word under WORD_FLOOR counts as not matching at all.
4. A phrase scores the F1 of how much of the text it explains and how much of
   the phrase the text says, each weighted by word length: "gempa terbaru"
   against "gampak terbaru" is 0.86, against "daftar gempa terbaru" 0.69. The
   whole strings without spaces are compared too (the recogniser splits and
   joins words: "baca kan", "tua-tahari"), at CHAR_WEIGHT.
5. An action scores its best phrase. The best action runs at once when it
   scores RUN_SCORE or more and leads the next action by RUN_MARGIN; from
   ASK_SCORE, Hariku asks "Did you mean …?"; below that it didn't understand.

Commands or reminders
---------------------
Command names can hold date words ("briefing pagi", "cuaca hari ini"), so a
sentence core.when reads a date or time in isn't always a reminder. decide()
settles it in this order: a reminder trigger ("ingatkan aku", "remind me")
makes a reminder; a command with content an extension added ("catat {text}",
core 2.9) goes to that extension, unless its handler turns it down; a clear
command runs; a strong date or time (a clock time,
a date, a weekday, "tomorrow", a repeat) makes a reminder, whose read-back
says what is missing, if anything; a close command is asked about (with the
reminder as the alternative when the sentence also had a weaker date word);
any other date or time makes a reminder; words that look like a date but
weren't understood offer the quick reminder; the rest isn't understood.

Everything happens on this computer; nothing is sent anywhere.
"""
import datetime
import difflib
import logging
import math
import re
import threading
import unicodedata

logger = logging.getLogger(__name__)

RUN_SCORE = 0.80       # a clear winner runs at once...
RUN_MARGIN = 0.10      # ...when it leads the next action by this much
ASK_SCORE = 0.55       # "Did you mean …?" from here; below it, not understood
WORD_FLOOR = 0.60      # letter similarity below this is no match for a word
SHORT_WORD_FLOOR = 0.75  # the same for words of three or four letters
CHAR_WEIGHT = 0.95     # the whole-string comparison counts a little less
MIN_LETTERS = 6        # texts shorter than this are only compared word by word
MAX_ANSWER_WORDS = 4   # a longer text is a new command, not a yes or no

# The command bar's own action, which the bar doesn't offer as a command.
COMMAND_BAR_ACTION = "Hariku Core.command_bar"
HIDDEN_ACTIONS = {COMMAND_BAR_ACTION}

# Aruna's settings in Core.json (core 2.8; Preferences, Aruna).
KEEP_OPEN_KEY = "aruna_keep_open"   # stay open after an answer
SOUNDS_KEY = "aruna_sounds"         # a sound when a message is sent and when Aruna answers
SEND_SOUND = "aruna_send.wav"       # core.sounds names, so a sound theme can replace them
REPLY_SOUND = "aruna_reply.wav"

# Actions that only say something (the time, the weather, the latest
# earthquake): they open no window and don't act on the window that had the
# focus. With "Keep Aruna open after an answer" they run with the bar still
# open, and what they say shows in it; any other action closes the bar first,
# as before. Extensions name theirs with add_answer_actions().
ANSWER_ACTIONS = frozenset([
    "Hariku Core.speak_time", "Hariku Core.speak_date",
    "Hariku Core.volume_up", "Hariku Core.volume_down",
    "Morning Briefing.play_briefing", "Morning Briefing.evening_summary",
    "Weather.speak_current_weather", "Earthquakes.speak_latest",
    "Flight Radar.speak_nearby", "Flight Radar.speak_tracked",
    "Sea Conditions.speak_sea", "Air Quality.speak_air",
    "Space.where_is_iss", "Space.sun_and_moon", "Sleep Pattern.last_night",
    "Clipboard History.speak_last", "World Clock.speak_world_clock",
    "Cockpit.pilot_weather", "Sound Themes.next_theme",
])
_answer_actions = set()

# Sounds a speech recogniser plays when it starts and stops listening; sound
# themes can replace them (core.sounds.play_internal_sound).
LISTEN_SOUND = "listen.wav"
LISTEN_END_SOUND = "listen_end.wav"

# Words that name no command, in any language Hariku speaks. Normalized
# below, like everything compared.
FILLERS = {
    # Indonesian
    "tolong", "coba", "dong", "deh", "sih", "kan", "nih", "ya", "yuk", "ayo", "hai", "halo",
    "hei", "hey", "hariku", "ucapkan", "sebutkan", "katakan", "bacakan", "baca", "putar",
    "putarkan", "beri", "berikan", "kasih", "tahu", "saya", "aku", "gue", "gw", "mau",
    "ingin", "pengen", "minta", "apa", "di", "ke", "dari", "yang", "untuk", "dan", "itu",
    "sekarang", "tentang", "soal", "info", "informasi", "aruna",
    # English
    "please", "hi", "hello", "ok", "okay", "the", "a", "an", "me", "my", "tell", "speak",
    "say", "read", "play", "what", "whats", "is", "are", "it", "its", "of", "to", "from",
    "for", "and", "can", "you", "could", "would", "i", "want", "now", "about", "some",
}

YES_WORDS = {
    "ya", "iya", "iyah", "ia", "yes", "yeah", "yep", "yup", "ok", "oke", "okay", "okey",
    "simpan", "simpen", "save", "benar", "betul", "bener", "boleh", "lanjut", "lanjutkan",
    "sure", "correct", "right", "setuju", "sip", "siap", "confirm", "go", "jalankan",
    "yoi",
}
# A question's own verb ("..., Pasang?", "..., Set it?") answers yes too, but
# only said alone or with a word like "aja" or "it": "pasang alarm jam 6" is a
# new command, not a yes.
CONFIRM_VERBS = {"pasang", "setel", "set"}
CONFIRM_EXTRAS = {"it", "aja", "saja", "dong", "deh", "sekarang", "now", "please", "tolong",
                  "ya"}
NO_WORDS = {
    "tidak", "tak", "nggak", "ngga", "enggak", "engga", "gak", "ga", "kagak", "ndak",
    "no", "nope", "nah", "batal", "batalkan", "cancel", "jangan", "bukan", "salah", "stop",
    "wrong", "abort", "never",
}

# Hariku's own aliases, for core actions and the official extensions' actions
# (only used while that action is registered), in English and Indonesian.
# Extensions add theirs with add_aliases().
BUILTIN_ALIASES = {
    "Hariku Core.speak_time": [
        "jam berapa", "jam berapa sekarang", "sekarang jam berapa", "pukul berapa",
        "what time is it", "the time", "time", "current time", "waktu", "jam"],
    "Hariku Core.speak_date": [
        "tanggal berapa", "tanggal berapa hari ini", "hari ini tanggal berapa", "hari apa",
        "hari ini hari apa", "what is the date", "what day is it", "today's date",
        "date", "tanggal"],
    "Hariku Core.quick_reminder": [
        "pengingat baru", "buat pengingat", "tambah pengingat", "new reminder",
        "add a reminder", "quick reminder"],
    "Hariku Core.input_gestures": [
        "pengaturan", "buka pengaturan", "preferensi", "settings", "open settings",
        "preferences", "open preferences"],
    "Hariku Core.manage_extensions": [
        "kelola ekstensi", "ekstensi", "extensions", "manage extensions"],
    "Hariku Core.show_app": [
        "buka hariku", "tampilkan hariku", "open hariku", "show hariku"],
    "Hariku Core.minimize_tray": [
        "sembunyikan hariku", "hide hariku"],
    "Hariku Core.stop_voice": [
        "diam", "berhenti bicara", "stop talking", "be quiet", "stop the voice"],
    "Hariku Core.volume_up": [
        "keraskan suara", "besarkan volume", "volume naik", "volume up", "louder"],
    "Hariku Core.volume_down": [
        "kecilkan suara", "pelankan suara", "volume turun", "volume down", "quieter"],
    "Hariku Core.show_shortcuts": [
        "pintasan keyboard", "daftar pintasan", "keyboard shortcuts"],
    "Hariku Core.go_to_date": [
        "pergi ke tanggal", "go to date"],
    "Calendar Navigation.today": [
        "kalender hari ini", "go to today"],
    "Morning Briefing.play_briefing": [
        "briefing", "briefing pagi", "morning briefing", "ringkasan pagi"],
    "Morning Briefing.evening_summary": [
        "ringkasan malam", "evening summary", "rangkuman malam"],
    "Weather.speak_current_weather": [
        "cuaca", "cuaca hari ini", "cuaca sekarang", "cuaca saat ini", "weather",
        "the weather", "weather today", "current weather", "suhu", "berapa suhu",
        "temperature"],
    "Weather.show_forecast": [
        "prakiraan cuaca", "ramalan cuaca", "cuaca besok", "weather forecast",
        "forecast", "weather tomorrow"],
    "Earthquakes.speak_latest": [
        "gempa", "gempa terbaru", "gempa terkini", "info gempa", "gempa bumi terbaru",
        "latest earthquake", "earthquake", "last earthquake"],
    "Earthquakes.show_recent": [
        "daftar gempa", "daftar gempa terbaru", "list of earthquakes", "recent earthquakes"],
    "Flight Radar.speak_nearby": [
        "pesawat", "pesawat di dekat sini", "pesawat terdekat", "radar pesawat",
        "what's flying nearby", "nearby planes", "planes nearby", "flights nearby"],
    "Flight Radar.show_list": [
        "daftar pesawat", "daftar radar pesawat", "flight list", "radar list"],
    "Flight Radar.speak_tracked": [
        "penerbangan yang dilacak", "tracked flights", "where are my flights"],
    "Sea Conditions.speak_sea": [
        "kondisi laut", "ombak", "gelombang laut", "sea conditions", "waves"],
    "Air Quality.speak_air": [
        "kualitas udara", "polusi udara", "air quality", "pollution"],
    "Space.where_is_iss": [
        "di mana iss", "iss", "stasiun luar angkasa", "where is the iss", "space station"],
    "Space.sun_and_moon": [
        "matahari dan bulan", "matahari terbit", "sun and moon", "sunrise", "sunset"],
    "Space.show_launches": [
        "peluncuran roket", "rocket launches", "launches"],
    "Sleep Pattern.last_night": [
        "tidur semalam", "tidurku semalam", "last night's sleep", "how did i sleep"],
    "Clipboard History.open_history": [
        "riwayat clipboard", "clipboard history", "clipboard"],
    "Clipboard History.speak_last": [
        "teks terakhir disalin", "last copied text"],
    "Finance.open_finance": [
        "keuangan", "buka keuangan", "saldo", "finance", "balance"],
    "Finance.quick_add_expense": [
        "catat pengeluaran", "tambah pengeluaran", "add an expense", "new expense"],
    "Cockpit.pilot_weather": [
        "cuaca pilot", "metar", "pilot weather"],
    "Cockpit.airport_weather": [
        "cuaca bandara", "airport weather"],
    "World Clock.speak_world_clock": [
        "jam dunia", "waktu dunia", "world clock", "world time"],
    "Sound Themes.next_theme": [
        "ganti tema suara", "tema suara berikutnya", "next sound theme"],
}


# ------------------------------------------------------------
# Text
# ------------------------------------------------------------

_REPEATED_LETTER_RE = re.compile(r"([^\W\d_])\1+")
_NOT_WORD_RE = re.compile(r"[^\w\s]|_")


def normalize(text):
    """Lower case without accents or punctuation; hyphens become spaces and a
    letter repeated counts once: "Tua-tahari ini." -> "tua tahari ini"."""
    text = unicodedata.normalize("NFKD", str(text or "")).casefold()
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("'s ", " ").replace("'", "")
    text = _NOT_WORD_RE.sub(" ", text)
    text = _REPEATED_LETTER_RE.sub(r"\1", text)
    return " ".join(text.split())


_FILLERS = {normalize(w) for w in FILLERS}
_LEADING_FILLERS = _FILLERS     # words an intent's pattern may come after
_YES = {normalize(w) for w in YES_WORDS}
_NO = {normalize(w) for w in NO_WORDS}
_CONFIRM_VERBS = {normalize(w) for w in CONFIRM_VERBS}
_CONFIRM_EXTRAS = {normalize(w) for w in CONFIRM_EXTRAS}


def words(text, keep_all_fillers=False):
    """The words that matter: normalized, fillers dropped. A text of fillers
    only ("halo", "ok") gives [], or its words with keep_all_fillers (for a
    command's own phrases, which are never dropped)."""
    tokens = normalize(text).split()
    kept = [t for t in tokens if t not in _FILLERS]
    return kept or (tokens if keep_all_fillers else [])


def _word_similarity(a, b):
    """0 to 1 for two words: letter by letter, 0 below the floor (higher for
    short words, which look alike more easily: "halo" is not "saldo")."""
    if a == b:
        return 1.0
    shorter = min(len(a), len(b))
    if shorter < 3 or a.isdigit() or b.isdigit():
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    floor = SHORT_WORD_FLOOR if shorter <= 4 else WORD_FLOOR
    return ratio if ratio >= floor else 0.0


def _coverage(these, those, weight):
    """How much of `these` `those` says, each word weighted by weight(word,
    its best match)."""
    total = done = 0.0
    for w in these:
        best, partner = 0.0, None
        for o in those:
            s = _word_similarity(w, o)
            if s > best:
                best, partner = s, o
        share = weight(w, partner)
        total += share
        done += share * best
    return done / total if total else 0.0


def similarity(text_words, phrase_words, rarity=None):
    """0 to 1: how well a phrase matches a text, both lists of words().
    `rarity(word)` (default 1) makes words many commands share count less."""
    if not text_words or not phrase_words:
        return 0.0
    if text_words == phrase_words:
        return 1.0
    rarity = rarity or (lambda word: 1.0)

    def said_weight(word, partner):
        # A text word counts as much as the phrase word it matched is rare:
        # saying "hari ini" explains little, many commands have it.
        return len(word) * rarity(partner if partner is not None else word)

    def meant_weight(word, _partner):
        # Every word of the phrase the text leaves out counts in full: without
        # "daftar" ("list") the text didn't ask for the list.
        return len(word)

    said = _coverage(text_words, phrase_words, said_weight)
    meant = _coverage(phrase_words, text_words, meant_weight)
    by_words = 2 * said * meant / (said + meant) if said + meant else 0.0
    joined_text, joined_phrase = "".join(text_words), "".join(phrase_words)
    if min(len(joined_text), len(joined_phrase)) < MIN_LETTERS:
        return by_words
    by_letters = difflib.SequenceMatcher(None, joined_text, joined_phrase).ratio()
    return max(by_words, CHAR_WEIGHT * by_letters)


def rarity_table(candidates):
    """rarity(word): 1 for a word one command uses, less for words many
    commands share ("hari", "buka", "open"), from the commands' phrases."""
    counts = {}
    for command in candidates:
        for word in {w for phrase in command.phrases for w in phrase}:
            counts[word] = counts.get(word, 0) + 1

    def rarity(word):
        n = counts.get(word, 1)
        return 1.0 / (1.0 + math.log(n)) if n > 1 else 1.0

    return rarity


# ------------------------------------------------------------
# Commands: the registered actions, their names and aliases
# ------------------------------------------------------------

_lock = threading.RLock()
_aliases = {}        # action id -> [phrases] added by extensions
_titles = {}         # action id -> a short name for questions


def add_aliases(action_id, aliases, title=None):
    """More ways to say an action, in any language: add_aliases("Weather.
    speak_current_weather", ["cuaca", "weather"]). `title`, optional, is a
    short name for "Did you mean …?" in the user's language (default: the
    action's description). Adding again adds to what is there; call
    remove_aliases() in teardown()."""
    if not isinstance(action_id, str) or not action_id:
        raise ValueError("action_id must be a non-empty string")
    if isinstance(aliases, str):
        aliases = [aliases]
    cleaned = [a.strip() for a in aliases or () if isinstance(a, str) and a.strip()]
    with _lock:
        existing = _aliases.setdefault(action_id, [])
        existing.extend(a for a in cleaned if a not in existing)
        if isinstance(title, str) and title.strip():
            _titles[action_id] = title.strip()
    return list(cleaned)


def remove_aliases(action_id):
    """Forget the aliases and title an extension added for an action."""
    with _lock:
        _titles.pop(action_id, None)
        return _aliases.pop(action_id, None) is not None


def aliases_for(action_id):
    """Hariku's own aliases for an action, then the ones extensions added."""
    with _lock:
        added = list(_aliases.get(action_id, ()))
    return list(BUILTIN_ALIASES.get(action_id, ())) + added


class Command:
    """One action as the matcher sees it: its id, the name to say, and the
    phrases (each a list of words) it answers to."""

    def __init__(self, action_id, name, aliases=(), title=None):
        self.id = action_id
        self.name = str(name or action_id)
        self.title = title or self.name
        self.phrases = []
        for text in [self.name] + _name_parts(self.name) + list(aliases):
            phrase = words(text, keep_all_fillers=True)
            if phrase and phrase not in self.phrases:
                self.phrases.append(phrase)

    def __repr__(self):
        return f"Command({self.id!r})"


_PART_RE = re.compile(r"[?!.:;()\[\]]")


def _name_parts(name):
    """A description of several sentences also answers to each one: "What's
    flying nearby? Speak the nearest aircraft"."""
    parts = [p.strip() for p in _PART_RE.split(name) if p.strip()]
    return parts if len(parts) > 1 else []


def commands(actions=None):
    """Every registered action as a Command (the command bar's own excepted).
    `actions` defaults to core.hotkeys.actions."""
    if actions is None:
        import core.hotkeys
        actions = core.hotkeys.actions
    with _lock:
        titles = dict(_titles)
    found = []
    for action_id, action in list(actions.items()):
        if action_id in HIDDEN_ACTIONS:
            continue
        name = getattr(action, "description", "") or action_id
        found.append(Command(action_id, name, aliases_for(action_id), titles.get(action_id)))
    return found


def vocabulary(actions=None):
    """Words a speech recogniser should expect: the commands' names and
    aliases, and the words of commands with content ("catat", "timer"). For a
    recogniser's prompt."""
    phrases = []
    for command in commands(actions):
        for text in [command.name] + aliases_for(command.id):
            if text not in phrases:
                phrases.append(text)
    for intent in intents():
        for pattern in intent.patterns:
            text = " ".join(w for w in pattern.pattern.replace(SLOT, " ").split())
            if text and text not in phrases:
                phrases.append(text)
    return phrases


# ------------------------------------------------------------
# Matching
# ------------------------------------------------------------

class Match:
    """The actions scored for a text, best first: `ranked` is [(score,
    Command)], one entry per action. `kind` is "run" (a clear winner), "ask"
    (close: ask "Did you mean …?") or "none"."""

    def __init__(self, ranked):
        self.ranked = ranked

    @property
    def best(self):
        return self.ranked[0][1] if self.ranked else None

    @property
    def score(self):
        return self.ranked[0][0] if self.ranked else 0.0

    @property
    def runner_up(self):
        return self.ranked[1][0] if len(self.ranked) > 1 else 0.0

    @property
    def kind(self):
        if self.score >= RUN_SCORE and self.score - self.runner_up >= RUN_MARGIN:
            return "run"
        if self.score >= ASK_SCORE:
            return "ask"
        return "none"

    def __repr__(self):
        top = ", ".join(f"{c.id}={s:.2f}" for s, c in self.ranked[:3])
        return f"Match({self.kind}: {top})"


def match(text, candidates=None):
    """Score every command for `text`. `candidates` is a list of Command
    (default: commands())."""
    if candidates is None:
        candidates = commands()
    said = words(text)
    ranked = []
    if said:
        rarity = rarity_table(candidates)
        for command in candidates:
            score = max((similarity(said, phrase, rarity) for phrase in command.phrases),
                        default=0.0)
            if score > 0:
                ranked.append((round(score, 4), command))
    ranked.sort(key=lambda item: (-item[0], item[1].id))
    return Match(ranked)


# ------------------------------------------------------------
# Yes or no
# ------------------------------------------------------------

def answer(text):
    """ "yes", "no" or None for an answer to a question: "ya", "iya, simpan",
    "yes" and "save" are yes; "tidak", "batal", "no", "cancel", "bukan" are
    no (no wins when both are there: "tidak jadi"). "pasang" and "set it"
    are yes on their own (core 2.9), not in "pasang alarm jam 6". More than a
    few words is a new command, None."""
    tokens = normalize(text).split()
    if not tokens or len(tokens) > MAX_ANSWER_WORDS:
        return None
    if any(t in _NO for t in tokens):
        return "no"
    if any(t in _YES for t in tokens):
        return "yes"
    if any(t in _CONFIRM_VERBS for t in tokens) and \
            all(t in _CONFIRM_VERBS or t in _CONFIRM_EXTRAS for t in tokens):
        return "yes"
    return None


# ------------------------------------------------------------
# Commands with content: intents (core 2.9)
# ------------------------------------------------------------

INTENT_SCORE = 0.80     # the pattern's own words must match this well on average
SLOT = "{text}"
_TOKEN_RE = re.compile(r"\S+")
_SLOT_EDGE = " \t:;,.-–—\"'“”"

_intents = {}           # intent id -> Intent, in the order they were added


class Reply:
    """What an intent's handler answers (core 2.9). Return None instead when
    the text isn't one for you: Aruna then tries the next intent, then treats
    the text as it always did (a command, a reminder...). A plain string is a
    Reply that only says it.

      say      what Aruna shows in Last result and says (Hariku Voice for
               commands, when the user set it up)
      confirm  a function: `say` is then a question ("..., save it?"). Enter,
               "ya" or "yes" calls confirm(), and what it returns (a string, a
               Reply or None) is the answer. Escape, "tidak" or "no" says "OK,
               cancelled" and calls cancel(), when given.
      cancel   see confirm
      wait     True: you started something slow (a download) whose answer you
               will speak later with core.speech.speak(); Aruna says `say`
               first (if any), shows "Aruna is thinking..." and puts what is
               spoken in Last result, as for a command that only answers
      then     a function to run after Aruna has closed and given the focus
               back to the window the user was in: typing into it, or opening
               a window of yours. `say`, if any, is said before Aruna closes
    """

    def __init__(self, say="", confirm=None, cancel=None, wait=False, then=None):
        for name, value in (("confirm", confirm), ("cancel", cancel), ("then", then)):
            if value is not None and not callable(value):
                raise TypeError(f"{name} must be callable or None")
        self.say = str(say or "")
        self.confirm = confirm
        self.cancel = cancel
        self.wait = bool(wait)
        self.then = then

    @classmethod
    def of(cls, value):
        """A handler's answer as a Reply (a string says it); None stays None."""
        if value is None or isinstance(value, Reply):
            return value
        return cls(say=str(value))

    def __repr__(self):
        return f"Reply({self.say!r}, confirm={self.confirm is not None}, wait={self.wait})"


class Request:
    """What an intent's handler gets: `text` (the words in the pattern's
    {text}, as typed or heard, capitals and punctuation kept), `full_text`
    (the whole sentence), `source` ("typed" or "voice") and `intent_id`."""

    def __init__(self, text, full_text, source="typed", intent_id=""):
        self.text = text
        self.full_text = full_text
        self.source = source
        self.intent_id = intent_id

    def __repr__(self):
        return f"Request({self.text!r}, {self.intent_id!r}, {self.source})"


class _Pattern:
    def __init__(self, pattern):
        pattern = " ".join(str(pattern or "").split())
        if pattern.count(SLOT) != 1:
            raise ValueError(f"an intent pattern needs one {SLOT}: {pattern!r}")
        before, after = pattern.split(SLOT)
        self.pattern = pattern
        self.prefix = normalize(before).split()
        self.suffix = normalize(after).split()
        if not self.prefix and not self.suffix:
            raise ValueError(f"an intent pattern needs words besides {SLOT}: {pattern!r}")

    @property
    def size(self):
        return len(self.prefix) + len(self.suffix)


class Intent:
    """A command with content, from add_intent()."""

    def __init__(self, intent_id, patterns, handler, title=None):
        if not callable(handler):
            raise TypeError("handler must be callable")
        if isinstance(patterns, str):
            patterns = [patterns]
        self.id = str(intent_id)
        self.patterns = [_Pattern(p) for p in patterns]
        if not self.patterns:
            raise ValueError("an intent needs at least one pattern")
        self.handler = handler
        self.title = title or self.id

    def __repr__(self):
        return f"Intent({self.id!r})"


class IntentMatch:
    """An intent a text matched: `text` is what its {text} held."""

    def __init__(self, intent, text, score, size):
        self.intent = intent
        self.text = text
        self.score = score
        self.size = size

    def __repr__(self):
        return f"IntentMatch({self.intent.id!r}, {self.text!r}, {self.score:.2f})"


def add_intent(intent_id, patterns, handler, title=None):
    """Teach Aruna a command with content (core 2.9): `patterns` are phrases
    with one {text} in any language, such as "catat {text}", "note {text}" or
    "tambahkan {text} ke daftar belanja". When a sentence matches one, Aruna
    calls handler(request) (a Request; request.text is what {text} held) on
    the UI thread, and does what its Reply says. Keep it quick: start slow
    work on a thread and return Reply(wait=True). A new call with the same id
    replaces the intent. Call it in register(); remove_intent() in teardown()."""
    intent = Intent(intent_id, patterns, handler, title)
    with _lock:
        _intents.pop(intent.id, None)
        _intents[intent.id] = intent
    return intent


def remove_intent(intent_id):
    with _lock:
        return _intents.pop(str(intent_id), None) is not None


def intents():
    with _lock:
        return list(_intents.values())


def _tokens(text):
    """[(start, end, word)] of the normalized words of `text`, each with the
    span of the original it came from ("Tua-tahari" gives two words, one span)."""
    found = []
    for m in _TOKEN_RE.finditer(text):
        for word in normalize(m.group()).split():
            found.append((m.start(), m.end(), word))
    return found


def _match_words(tokens, expected):
    """The mean similarity of tokens to the expected words, or 0 when any
    word doesn't match at all."""
    if len(tokens) != len(expected):
        return 0.0
    total = 0.0
    for (_start, _end, word), want in zip(tokens, expected):
        s = _word_similarity(word, want)
        # A longer word that starts with this one is another word, not a
        # mishearing: "catatan" (notes) is not "catat" (note down).
        if word != want and abs(len(word) - len(want)) >= 2 and \
                (word.startswith(want) or want.startswith(word)):
            s = 0.0
        if s <= 0:
            return 0.0
        total += s
    return total / len(expected) if expected else 1.0


def _match_pattern(text, tokens, pattern):
    """(score, slot text) of one pattern, or None."""
    best = None
    # Fillers before the pattern ("tolong", "Aruna") may be skipped.
    skips = [0]
    while skips[-1] < len(tokens) and tokens[skips[-1]][2] in _LEADING_FILLERS:
        skips.append(skips[-1] + 1)
    for skip in skips:
        first = skip + len(pattern.prefix)
        last = len(tokens) - len(pattern.suffix)
        if last - first < 1:
            continue
        head = _match_words(tokens[skip:first], pattern.prefix) if pattern.prefix else 1.0
        tail = _match_words(tokens[last:], pattern.suffix) if pattern.suffix else 1.0
        if head <= 0 or tail <= 0:
            continue
        score = (head * len(pattern.prefix) + tail * len(pattern.suffix)) / pattern.size
        if score < INTENT_SCORE:
            continue
        start = max(tokens[first][0], tokens[first - 1][1] if first else 0)
        end = tokens[last - 1][1]
        slot = text[start:end].strip(_SLOT_EDGE)
        if slot and (best is None or score > best[0]):
            best = (score, slot)
    return best


def match_intents(text, candidates=None):
    """The intents `text` matches, most specific first (the pattern with
    more words of its own), then the best matched: [IntentMatch]."""
    text = " ".join(str(text or "").split())
    tokens = _tokens(text)
    if not tokens:
        return []
    found = []
    for intent in (intents() if candidates is None else candidates):
        best = None
        for pattern in intent.patterns:
            m = _match_pattern(text, tokens, pattern)
            if m is not None and (best is None or (pattern.size, m[0]) > (best.size, best.score)):
                best = IntentMatch(intent, m[1], m[0], pattern.size)
        if best is not None:
            found.append(best)
    found.sort(key=lambda m: (-m.size, -m.score))
    return found


# ------------------------------------------------------------
# Deciding: a reminder, a command, a question, or not understood
# ------------------------------------------------------------

# Components core.when fills in only for a definite date, time or repeat.
_STRONG_FIELDS = ("hour", "minutes_from_now", "weekday", "day_of_month", "month", "year",
                  "week_offset", "month_offset", "year_offset")


def has_when(result):
    """Whether core.when found a date, time or repeat in the sentence."""
    return result is not None and bool(getattr(result, "recognised", None))


def strong_when(result):
    """A clock time, a date, a weekday, "tomorrow" or later, or a repeat: not
    just a part of the day or "today", which command names also use."""
    if not has_when(result):
        return False
    c = getattr(result, "components", None) or {}
    if any(c.get(field) is not None for field in _STRONG_FIELDS):
        return True
    if (c.get("day_offset") or 0) >= 1:
        return True
    return (c.get("recurrence") or "none") != "none"


def looks_like_reminder(text, parse=None):
    """Whether a sentence reads like a reminder (a trigger such as "ingatkan
    aku", or a date or time). A speech recogniser can then listen again more
    carefully (Voice Control uses a bigger model)."""
    result = _parse(text, parse)
    return result is not None and (bool(result.trigger) or has_when(result))


class Decision:
    """What the command bar does with a text.

    kind "empty"           nothing was typed or said
         "reminder"        the quick reminder: read `result` back, then "Save?"
         "run"             run `command` now
         "confirm"         ask "Did you mean `command`?"; `alternative` is a
                           reminder result to offer when the answer is no
         "offer_reminder"  not understood, but it looks like a date or time:
                           offer the quick reminder with the text
         "unknown"         not understood
         "intent"          (core 2.9) it matched commands with content:
                           `intents` ([IntentMatch], best first) are asked in
                           turn; if none takes it, `fallback` is the decision
                           without them
    """

    def __init__(self, kind, text="", command=None, result=None, match=None,
                 alternative=None, intents=None, fallback=None):
        self.kind = kind
        self.text = text
        self.command = command
        self.result = result
        self.match = match
        self.alternative = alternative
        self.intents = intents or []
        self.fallback = fallback

    @property
    def action_id(self):
        return self.command.id if self.command is not None else None

    def __repr__(self):
        return f"Decision({self.kind!r}, {self.action_id or ''}, {self.match!r})"


def _parse(text, parse=None):
    try:
        if parse is None:
            import core.quick_reminder
            parse = core.quick_reminder.parse_text
        return parse(text)
    except Exception:
        logger.exception("Command bar: reading a sentence for a reminder failed")
        return None


def decide(text, candidates=None, parse=None, intent_candidates=None):
    """Decide what `text` asks for (see the module notes for the order).
    `parse(text)` reads a reminder (default core.quick_reminder.parse_text);
    `candidates` defaults to commands(), `intent_candidates` to intents()."""
    text = " ".join(str(text or "").split())
    if not normalize(text):
        return Decision("empty", text)
    result = _parse(text, parse)
    if result is not None and result.trigger:
        return Decision("reminder", text, result=result)
    found_intents = match_intents(text, intent_candidates)
    if found_intents:
        # A command with content comes before commands and dates ("timer 10
        # menit" is not a reminder); its handler may still turn it down.
        return Decision("intent", text, intents=found_intents,
                        fallback=_decide_without_intents(text, result, candidates))
    return _decide_without_intents(text, result, candidates)


def _decide_without_intents(text, result, candidates):
    found = match(text, candidates)
    if found.kind == "run":
        return Decision("run", text, command=found.best, match=found)
    if strong_when(result):
        return Decision("reminder", text, result=result, match=found)
    if found.kind == "ask":
        titled = result is not None and bool(result.title)
        alternative = result if has_when(result) and titled else None
        return Decision("confirm", text, command=found.best, match=found,
                        alternative=alternative)
    if has_when(result):
        return Decision("reminder", text, result=result, match=found)
    if result is not None and result.unparsed:
        return Decision("offer_reminder", text, result=result, match=found)
    return Decision("unknown", text, match=found)


# ------------------------------------------------------------
# Running an action
# ------------------------------------------------------------

def run_action(action_id, actions=None):
    """Call an action's callback as its hotkey would (a single tap). Returns
    whether it ran."""
    if actions is None:
        import core.hotkeys
        actions = core.hotkeys.actions
    action = actions.get(action_id)
    if action is None:
        logger.warning(f"Command bar: the action {action_id} is gone.")
        return False
    try:
        if getattr(action, "wants_tap_count", False):
            action.callback(tap_count=1)
        else:
            action.callback()
    except Exception:
        logger.exception(f"Command bar: running {action_id} failed")
        return False
    return True


# ------------------------------------------------------------
# The speech recogniser (Voice Control registers one)
# ------------------------------------------------------------

class Listener:
    def __init__(self, start, stop, is_available=None, listen_on_open=None, name=""):
        self.start = start
        self.stop = stop
        self._is_available = is_available
        self._listen_on_open = listen_on_open
        self.name = name

    @staticmethod
    def _ask(fn, default):
        if fn is None:
            return default
        try:
            return bool(fn())
        except Exception:
            logger.exception("Command bar: asking the speech recogniser failed")
            return False

    def is_available(self):
        return self._ask(self._is_available, True)

    def listen_on_open(self):
        return self._ask(self._listen_on_open, False)


_listener = None


def register_listener(start, stop, is_available=None, listen_on_open=None, name=""):
    """Make a speech recogniser the command bar's (one at a time; registering
    again replaces it).

    start(on_event)   start listening; return at once, True when it started.
                      Call on_event(kind, value) from any thread:
                        ("listening", None)    the microphone is open
                        ("recognising", None)  recording ended, now recognising
                        ("text", "...")        what was said
                        ("error", "...")       a message for the user, said
                                               through Hariku Voice; listening
                                               has ended
                        ("stopped", None)      ended without text (cancelled)
                      When it can't start, send ("error", why) and return False.
    stop(discard)     stop recording now: recognise what was heard, or with
                      discard=True drop it and send only ("stopped", None).
    is_available()    fast: True when it can listen (installed and ready).
    listen_on_open()  fast: whether to start listening when the bar opens.
    """
    global _listener
    if not callable(start) or not callable(stop):
        raise TypeError("start and stop must be callable")
    for fn in (is_available, listen_on_open):
        if fn is not None and not callable(fn):
            raise TypeError("is_available and listen_on_open must be callable or None")
    with _lock:
        _listener = Listener(start, stop, is_available, listen_on_open, name)
    logger.info(f"Command bar: speech recogniser registered ({name or 'unnamed'}).")
    return True


def unregister_listener(start=None):
    """Remove the speech recogniser (in teardown()); with `start`, only when
    it is that one."""
    global _listener
    with _lock:
        if _listener is None or (start is not None and _listener.start != start):
            return False
        _listener = None
    return True


def get_listener():
    """The registered speech recogniser, or None."""
    with _lock:
        return _listener


# ------------------------------------------------------------
# A future AI fallback
# ------------------------------------------------------------

_fallback = None


def set_fallback(handler):
    """Reserved for an AI fallback (phase 2). handler(text, commands) is
    called on a worker thread for a text decide() didn't understand, and
    returns an action id or None. The command bar never runs its answer
    straight away: it asks "Did you mean …?" first. None removes it."""
    global _fallback
    if handler is not None and not callable(handler):
        raise TypeError("handler must be callable or None")
    with _lock:
        _fallback = handler


def get_fallback():
    with _lock:
        return _fallback


def ask_fallback(text, candidates=None):
    """The fallback's Command for `text`, or None (no fallback, no answer, an
    error or an unknown action). Slow: call it on a worker thread."""
    handler = get_fallback()
    if handler is None:
        return None
    candidates = commands() if candidates is None else candidates
    try:
        action_id = handler(text, candidates)
    except Exception:
        logger.exception("Command bar: the fallback failed")
        return None
    return next((c for c in candidates if c.id == action_id), None)


# ------------------------------------------------------------
# Aruna's settings, and the actions that only answer (core 2.8)
# ------------------------------------------------------------

def add_answer_actions(action_ids):
    """Name actions of your extension that only say something (no window, and
    nothing done to the window that had the focus), so Aruna can stay open and
    show what they say. Ids as core.hotkeys makes them: "<extension>.<action>"."""
    if isinstance(action_ids, str):
        action_ids = [action_ids]
    with _lock:
        _answer_actions.update(str(a) for a in action_ids if a)


def is_answer_action(action_id):
    with _lock:
        return action_id in ANSWER_ACTIONS or action_id in _answer_actions


def bar_settings(config=None):
    """{"keep_open": bool, "sounds": bool}: both on unless the user turned them off."""
    if config is None:
        import core.api
        config = core.api.load_data("Core")
    return {"keep_open": bool(config.get(KEEP_OPEN_KEY, True)),
            "sounds": bool(config.get(SOUNDS_KEY, True))}


def save_bar_settings(keep_open, sounds):
    import core.api
    config = core.api.load_data("Core")
    config[KEEP_OPEN_KEY] = bool(keep_open)
    config[SOUNDS_KEY] = bool(sounds)
    core.api.save_data("Core", config)


# ------------------------------------------------------------
# Hariku's own answers: the time and the date
# ------------------------------------------------------------

def time_text(now=None):
    from core.i18n import get_translator
    _ = get_translator("core")
    now = now or datetime.datetime.now()
    return _("cmd_time_now", time=now.strftime("%H:%M"))


def date_text(now=None):
    from core.i18n import format_date, get_translator
    _ = get_translator("core")
    now = now or datetime.datetime.now()
    return _("cmd_date_today", date=format_date(now, "%A, %d %B %Y"))


def say_time():
    """The "Say the time" action."""
    from core.speech import speak
    speak(time_text(), interrupt=True)


def say_date():
    """The "Say today's date" action."""
    from core.speech import speak
    speak(date_text(), interrupt=True)
