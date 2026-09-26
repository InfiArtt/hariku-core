# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
A frozen copy of Orbit 1.6's command reader (extensions/orbit/orbit_parse.py
as published in the Extension Store before client 1.7), kept only so
tests/test_orbit_compat.py can check that players who haven't updated keep
playing. Don't change it.

What a player typed or said, in English, as an Orbit command (Orbit is
played in English since 1.5 of this client and 1.4 of the server).

    parse("go to the cantina")        -> {"c": "go", "a": "the cantina"}
    parse("say hi everyone")          -> {"c": "say", "a": "hi everyone"}
    parse("whisper Maya see you soon")-> {"c": "whisper", "to": "Maya", "a": "see you soon"}
    parse("smile at Maya")            -> {"c": "emote", "e": "smile", "to": "Maya"}
    parse("give Maya 50 credits")     -> {"c": "give", "to": "Maya", "n": 50, "item": "credits"}
    parse("3 1 4 2")                  -> {"c": "answer", "a": "3 1 4 2"}
    parse("help")                     -> {"local": "help"}
    parse("help casino")              -> {"local": "help", "topic": "casino"}
    parse("x here")                   -> {"c": "examine", "a": "here"}   (what you can do here;
                                         "examine here", "commands here" too)
    parse("x Rocco")                  -> {"c": "examine", "a": "Rocco"}  (what you can do with him)
    parse("voices off")               -> {"local": "set", "key": "voices", "value": False}
    parse("ignore Sam")               -> {"local": "ignore", "name": "Sam"}
    parse("quit")                     -> {"local": "disconnect"}
    parse("cantina")                  -> {"c": "text", "a": "cantina"}   (the server guesses)
    parse("u")                        -> {"c": "text", "a": "u"}         (a direction: the server
                                         knows them; "u" is up, "d" down)

Only the command word is read here; the server finds the place, the player
or the thing (it knows the station), and reads the commands this reader
doesn't know itself (directions, the farm, the shops...), so a new place or
command needs no new client. Anything else, words in another language too,
goes to the server as plain text, and it answers with its help hint.
Settings, the ignore list, the help and leaving are the client's own
("local"). Words are compared in lower case without the punctuation around
them; what is said keeps its capitals and punctuation. "orbit" (and
"please"...) in front is skipped, so Aruna's "orbit go to the cantina" works
the same. No wx.
"""

import re

_TOKEN_RE = re.compile(r"\S+")
_EDGE = ".,!?;:\"'()[]“”‘’"
_DIGITS_ONLY = re.compile(r"^[\d\s,.\-]+$")
_LAUGH = re.compile(r"^(ha){2,}h?$|^(he){2,}$|^l+o+l+$")

PREFIXES = {"orbit", "aruna", "please", "hariku"}
PREPOSITIONS = {"to", "at", "with", "for"}

EMOTES = {
    "smile": ("smile", "grin"),
    "wave": ("wave",),
    "laugh": ("laugh", "lol"),
    "nod": ("nod",),
    "shrug": ("shrug",),
    "clap": ("clap", "applaud"),
    "cheer": ("cheer", "hooray", "yay"),
    "sigh": ("sigh",),
    "bow": ("bow",),
    "dance": ("dance",),
    "hug": ("hug",),
}

# (words, what they mean), longest first when matched.
_VERBS = [
    # asking the client itself
    (("help",), "help"), (("commands",), "help"), (("?",), "help"),
    (("connect",), "connect"), (("reconnect",), "connect"),
    (("disconnect",), "disconnect"), (("quit",), "disconnect"), (("logout",), "disconnect"),
    (("log", "out"), "disconnect"), (("leave", "orbit"), "disconnect"), (("exit",), "disconnect"),
    (("status",), "status"), (("status", "orbit"), "status"), (("connection", "status"), "status"),
    (("settings",), "settings"), (("preferences",), "settings"), (("options",), "settings"),
    (("ignore",), "ignore"), (("ignored",), "ignored"), (("ignore", "list"), "ignored"),
    (("remind", "me"), "remind"), (("remind", "me", "of"), "remind"), (("remind", "me", "about"), "remind"),
    (("event", "reminder"), "remind"),
    (("unignore",), "unignore"), (("stop", "ignoring"), "unignore"),
    # the server reads these itself: words this reader would take for something else
    (("take", "off"), "raw"), (("take", "credits"), "raw"), (("board", "the", "wombat"), "raw"),
    (("board", "wombat"), "raw"), (("board", "the", "shuttle"), "raw"), (("board", "shuttle"), "raw"),
    (("transfer", "code"), "raw"), (("give", "item"), "raw"),
    (("fly", "to"), "raw"), (("board", "ship"), "raw"), (("board", "my", "ship"), "raw"),
    (("get", "off"), "raw"), (("take", "the", "ferry"), "raw"), (("take", "a", "gig"), "raw"),
    (("say", "hi", "to"), "raw"), (("say", "hello", "to"), "raw"),
    (("repeat",), "repeat"), (("again",), "repeat"),
    # missions, before "look" and "take"
    (("missions",), "missions"), (("mission", "board"), "missions"), (("board",), "missions"),
    (("check", "missions"), "missions"), (("list", "missions"), "missions"),
    (("accept", "mission"), "accept"), (("accept",), "accept"), (("take", "mission"), "accept"),
    (("complete", "mission"), "complete"), (("complete",), "complete"), (("deliver",), "complete"),
    (("turn", "in"), "complete"), (("hand", "in"), "complete"), (("finish", "mission"), "complete"),
    (("abandon", "mission"), "abandon"), (("abandon",), "abandon"), (("drop", "mission"), "abandon"),
    (("cancel", "mission"), "abandon"),
    # the market
    (("prices",), "prices"), (("price",), "prices"), (("market",), "prices"),
    (("check", "prices"), "prices"), (("price", "list"), "prices"),
    (("buy",), "buy"),
    (("sell",), "sell"),
    # you and your things
    (("inventory",), "inventory"), (("inv",), "inventory"), (("i",), "inventory"),
    (("credits",), "inventory"), (("check", "credits"), "inventory"), (("balance",), "inventory"),
    (("money",), "inventory"), (("bag",), "inventory"), (("my", "bag"), "inventory"),
    (("give",), "give"), (("pay",), "give"), (("send",), "give"), (("transfer",), "give"),
    (("describe", "me"), "describe"), (("describe", "myself"), "describe"),
    (("describe",), "describe"), (("set", "description"), "describe"),
    (("description",), "describe"),
    # work
    (("work",), "work"), (("start", "work"), "work"), (("shift",), "work"),
    (("start", "shift"), "work"), (("repair", "the", "reactor"), "work"),
    (("repair", "reactor"), "work"), (("fix", "reactor"), "work"), (("repair",), "repair"),
    (("fix",), "repair"), (("fly",), "work"), (("cargo", "run"), "work"),
    (("market", "report"), "work"),
    (("answer",), "answer"), (("sequence",), "answer"),
    # talking
    (("say",), "say"),
    (("whisper", "to"), "whisper"), (("whisper",), "whisper"), (("tell",), "whisper"),
    (("msg",), "whisper"), (("pm",), "whisper"),
    (("shout",), "shout"), (("yell",), "shout"), (("broadcast",), "shout"),
    # who
    (("who",), "who"), (("who", "is", "online"), "who"), (("whos", "online"), "who"),
    (("who's", "online"), "who"), (("online",), "who"), (("players",), "who"),
    # looking; what you can do here, or with someone or something
    (("look", "around"), "look_around"), (("look", "at"), "look"), (("look",), "look"),
    (("l",), "look"), (("inspect",), "look"),
    (("x",), "examine"), (("examine",), "examine"), (("commands", "here"), "examine_here"),
    # going
    (("go", "to"), "go"), (("go",), "go"), (("walk", "to"), "go"), (("walk",), "go"),
    (("head", "to"), "go"), (("move", "to"), "go"), (("enter",), "go"), (("travel", "to"), "go"),
    (("run", "to"), "go"),
    # taking things for missions
    (("pick", "up"), "take"), (("take",), "take"), (("get",), "take"), (("grab",), "take"),
    # admin (the server checks who may)
    (("mute",), "mute"), (("unmute",), "unmute"),
    (("kick",), "kick"), (("ban",), "ban"), (("unban",), "unban"),
    (("announce",), "announce"),
]
_VERBS.sort(key=lambda entry: -len(entry[0]))

_EMOTE_PHRASES = sorted(((tuple(p.split()), eid) for eid, phrases in EMOTES.items()
                         for p in phrases), key=lambda e: -len(e[0]))

_ALL_WORDS = {"all", "everything"}
_ON_WORDS = {"on", "enable", "yes"}
_OFF_WORDS = {"off", "disable", "no"}
# What the quick settings are called: (words, setting).
_SETTINGS = sorted([
    (("voices",), "voices"), (("player", "voices"), "voices"), (("players", "voices"), "voices"),
    (("speech",), "speak"), (("speak", "messages"), "speak"), (("read", "aloud"), "speak"),
    (("ambience",), "ambience"), (("ambiance",), "ambience"),
    (("sounds",), "sounds"), (("sound", "effects"), "sounds"), (("effects",), "sounds"),
    (("my", "lines"), "speak_own"), (("own", "lines"), "speak_own"), (("my", "own", "voice"), "speak_own"),
    (("names",), "speak_names"), (("player", "names"), "speak_names"), (("speaker", "names"), "speak_names"),
    (("other", "sounds"), "other_sounds"), (("other", "players", "sounds"), "other_sounds"),
    (("others", "sounds"), "other_sounds"),
], key=lambda e: -len(e[0]))
# Who reads the game aloud ("reader"): the screen reader, Hariku Voice, or both.
_READERS = {
    ("reader", "nvda"): "nvda", ("nvda", "only"): "nvda", ("screen", "reader"): "nvda",
    ("reader", "mixed"): "mixed", ("mixed", "reader"): "mixed",
    ("reader", "voices"): "voices", ("all", "voices"): "voices",
}
_VOLUMES = sorted([
    (("effects", "volume"), "effects_volume"), (("sound", "volume"), "effects_volume"),
    (("ambience", "volume"), "ambience_volume"), (("volume", "ambience"), "ambience_volume"),
    (("volume", "effects"), "effects_volume"),
], key=lambda e: -len(e[0]))
_CREDIT_WORDS = {"credit", "credits", "cr"}


def _tokens(text):
    """[(start, end, word)]: each word lower-cased, without punctuation around it."""
    found = []
    for m in _TOKEN_RE.finditer(text):
        word = m.group().lower().strip(_EDGE)
        if word or m.group() == "?":
            found.append((m.start(), m.end(), word or "?"))
    return found


def _rest(text, tokens, index):
    """The original text from token `index` on."""
    return text[tokens[index][0]:].strip() if index < len(tokens) else ""


def _match(tokens, table, start=0):
    """(meaning, how many words) of the longest phrase at `start`, or (None, 0)."""
    words = [t[2] for t in tokens[start:]]
    for phrase, meaning in table:
        if tuple(words[:len(phrase)]) == phrase:
            return meaning, len(phrase)
    return None, 0


def _number(word):
    try:
        return int(word)
    except (TypeError, ValueError):
        return None


def strip_prefix(text):
    """The text without "orbit", "please"... in front."""
    text = str(text or "").strip()
    while True:
        tokens = _tokens(text)
        if len(tokens) > 1 and tokens[0][2] in PREFIXES:
            text = text[tokens[1][0]:].strip()
            continue
        return text


def _target_after(text, tokens, index):
    """A name after an optional "to"/"at"/"with" (for emotes)."""
    if index < len(tokens) and tokens[index][2] in PREPOSITIONS:
        index += 1
    if index >= len(tokens):
        return ""
    return tokens[index][2] and text[tokens[index][0]:tokens[index][1]].strip(_EDGE)


def _emote(text, tokens):
    """(the emote message, how many words named it), or (None, 0)."""
    if len(tokens) == 1 and _LAUGH.match(tokens[0][2]):
        return {"c": "emote", "e": "laugh"}, 1
    emote, used = _match(tokens, _EMOTE_PHRASES)
    if emote is None:
        return None, 0
    rest = tokens[used:]
    if len(rest) > 2 or (len(rest) == 2 and rest[0][2] not in PREPOSITIONS):
        return None, 0     # "smile if you're happy": a sentence, not a gesture
    message = {"c": "emote", "e": emote}
    target = _target_after(text, tokens, used)
    if target:
        message["to"] = target
    return message, used


def _give(text, tokens, index):
    """ "Maya 50 credits", "50 credits to Maya", "Maya coffee", "to Maya 2 coffee"."""
    words = tokens[index:]
    if not words:
        return {"c": "give"}
    name, what = None, []
    for i, (_s, _e, word) in enumerate(words):
        if word == "to" and i + 1 < len(words):
            name_token = words[i + 1]
            name = text[name_token[0]:name_token[1]].strip(_EDGE)
            what = words[:i] + words[i + 2:]
            break
    if name is None:
        first = words[0]
        name = text[first[0]:first[1]].strip(_EDGE)
        what = words[1:]
    message = {"c": "give", "to": name}
    n = None
    item_words = []
    for _s, _e, word in what:
        if n is None and _number(word) is not None:
            n = _number(word)
        else:
            item_words.append(word)
    item = " ".join(w for w in item_words if w)
    message["n"] = n if n is not None else 1
    message["item"] = item or "credits"
    return message


def _goods(text, tokens, index, command):
    """ "2 coffee", "coffee", "all coffee", "coffee 3"."""
    words = tokens[index:]
    n = None
    item = []
    for _s, _e, word in words:
        if n is None and _number(word) is not None:
            n = _number(word)
        elif n is None and word in _ALL_WORDS and command == "sell":
            n = "all"
        else:
            item.append(word)
    message = {"c": command, "item": " ".join(item)}
    if n is not None:
        message["n"] = n
    return message


def _setting(tokens):
    """A quick setting ("voices off", "turn off ambience", "effects volume 40"), or None."""
    words = [t[2] for t in tokens]
    if tuple(words) in _READERS:
        return {"local": "set", "key": "reader", "value": _READERS[tuple(words)]}
    for phrase, key in _VOLUMES:
        n = len(phrase)
        if tuple(words[:n]) == phrase and len(words) == n + 1 and _number(words[n]) is not None:
            return {"local": "set", "key": key, "value": max(0, min(100, _number(words[n])))}
    value = None
    if words and words[0] in _ON_WORDS | _OFF_WORDS | {"turn"}:
        if words[0] == "turn" and len(words) > 1 and words[1] in ("on", "off"):
            value, words = words[1] == "on", words[2:]
        elif words[0] != "turn":
            value, words = words[0] in _ON_WORDS, words[1:]
    elif words and words[-1] in _ON_WORDS | _OFF_WORDS:
        value, words = words[-1] in _ON_WORDS, words[:-1]
    if value is None:
        return None
    for phrase, key in _SETTINGS:
        if tuple(words) == phrase:
            return {"local": "set", "key": key, "value": value}
    return None


def parse(text):
    """The command in `text` (see the module notes), or None for nothing."""
    text = strip_prefix(" ".join(str(text or "").split()))
    if not text:
        return None
    if text[0] in "'\"" and len(text) > 1:
        return {"c": "say", "a": text[1:].strip().strip("\"")}
    if _DIGITS_ONLY.match(text) and re.search(r"\d", text):
        return {"c": "answer", "a": text}
    tokens = _tokens(text)
    if not tokens:
        return None
    setting = _setting(tokens)
    if setting is not None:
        return setting

    meaning, used = _match(tokens, _VERBS)
    rest = _rest(text, tokens, used)
    emote, emote_words = _emote(text, tokens)
    if emote is not None and emote_words >= used:
        return emote

    if meaning == "help":
        return {"local": "help", "topic": rest.lower()} if rest else {"local": "help"}
    if meaning in ("connect", "disconnect", "repeat", "status", "settings", "ignored") and not rest:
        return {"local": meaning}
    if meaning == "raw":
        return {"c": "text", "a": text}
    if meaning == "remind":
        return {"local": "remind", "name": rest}
    if meaning in ("ignore", "unignore"):
        if not rest:
            return {"local": "ignored"}
        return {"local": meaning, "name": text[tokens[used][0]:tokens[used][1]].strip(_EDGE)}
    if meaning is None:
        return {"c": "text", "a": text}
    if meaning == "inventory" and rest and used == 1 and len(tokens[0][2]) == 1:
        return {"c": "text", "a": text}     # "i" alone is the inventory; "i think..." isn't
    if meaning == "missions" and _number(rest) is not None:
        return {"c": "accept", "n": _number(rest)}      # "board 2"
    if meaning == "prices":
        return {"c": "prices", "a": rest} if rest else {"c": "prices"}
    if meaning == "look_around":
        return {"c": "look"}
    if meaning == "look":
        return {"c": "look", "a": rest} if rest else {"c": "look"}
    if meaning == "examine":
        return {"c": "examine", "a": rest}
    if meaning == "examine_here":
        return {"c": "examine", "a": "here"}
    if meaning == "go":
        return {"c": "go", "a": rest}
    if meaning in ("say", "shout", "describe", "announce"):
        if meaning == "announce":
            return {"c": "admin", "op": "announce", "a": rest}
        return {"c": meaning, "a": rest}
    if meaning == "whisper":
        if used >= len(tokens):
            return {"c": "whisper", "to": "", "a": ""}
        index = used
        if tokens[index][2] in PREPOSITIONS and index + 1 < len(tokens):
            index += 1
        name = text[tokens[index][0]:tokens[index][1]].strip(_EDGE)
        return {"c": "whisper", "to": name, "a": _rest(text, tokens, index + 1)}
    if meaning == "give":
        return _give(text, tokens, used)
    if meaning in ("buy", "sell"):
        return _goods(text, tokens, used, meaning)
    if meaning == "take":
        message = _goods(text, tokens, used, "take")
        return message
    if meaning == "accept":
        numbers = [_number(t[2]) for t in tokens[used:] if _number(t[2]) is not None]
        return {"c": "accept", "n": numbers[0]} if numbers else {"c": "accept"}
    if meaning == "repair":
        if re.search(r"\d", rest):
            return {"c": "answer", "a": rest}
        return {"c": "work"}
    if meaning == "answer":
        return {"c": "answer", "a": rest}
    if meaning in ("mute", "unmute", "kick", "ban", "unban"):
        words = tokens[used:]
        message = {"c": "admin", "op": meaning, "to": words[0][2] and
                   text[words[0][0]:words[0][1]].strip(_EDGE) if words else ""}
        numbers = [_number(t[2]) for t in words[1:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
        return message
    if meaning in ("help", "connect", "disconnect", "repeat", "status", "settings", "ignored"):
        return {"c": "text", "a": text}
    return {"c": meaning}
