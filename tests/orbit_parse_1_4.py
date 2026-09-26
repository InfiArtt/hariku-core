# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
A frozen copy of Orbit 1.4's command reader (extensions/orbit/orbit_parse.py
as published in the Extension Store, before Orbit became English-only), kept
only so tests/test_orbit_compat.py can check that players who haven't updated
keep playing. Don't change it.

What a player typed or said, in Indonesian or English, as an Orbit command.

    parse("pergi ke kantin")          -> {"c": "go", "a": "kantin"}
    parse("say hi everyone")          -> {"c": "say", "a": "hi everyone"}
    parse("bisik Sari ketemu di dek") -> {"c": "whisper", "to": "Sari", "a": "ketemu di dek"}
    parse("senyum ke Sari")           -> {"c": "emote", "e": "smile", "to": "Sari"}
    parse("beri Sari 50 kredit")      -> {"c": "give", "to": "Sari", "n": 50, "item": "kredit"}
    parse("3 1 4 2")                  -> {"c": "answer", "a": "3 1 4 2"}
    parse("bantuan")                  -> {"local": "help"}
    parse("bantuan kasino")           -> {"local": "help", "topic": "kasino"}
    parse("suara pemain mati")        -> {"local": "set", "key": "voices", "value": False}
    parse("abaikan Budi")             -> {"local": "ignore", "name": "Budi"}
    parse("keluar")                   -> {"local": "disconnect"}
    parse("kantin")                   -> {"c": "text", "a": "kantin"}   (the server guesses)
    parse("s")                        -> {"c": "text", "a": "s"}        (a direction: the server
                                         knows them, and that "u" is utara in Indonesian)

Only the command word is read here; the server finds the place, the player
or the thing (it knows the station), and reads the commands this reader
doesn't know itself (directions, the farm, the shops...), so a new place or
command needs no new client. Settings, the ignore list, the help and
leaving are the client's own ("local").
Words are compared in lower case without the punctuation around them; what
is said keeps its capitals and punctuation. "orbit" (and "tolong",
"please"...) in front is skipped, so Aruna's "orbit pergi ke kantin" works
the same. No wx.
"""

import re

_TOKEN_RE = re.compile(r"\S+")
_EDGE = ".,!?;:\"'()[]“”‘’"
_DIGITS_ONLY = re.compile(r"^[\d\s,.\-]+$")
_LAUGH = re.compile(r"^(ha){2,}h?$|^(he){2,}$|^(wk){2,}w?$|^l+o+l+$")

PREFIXES = {"orbit", "aruna", "tolong", "please", "coba", "ayo", "yuk", "dong", "hariku"}
PREPOSITIONS = {"to", "at", "with", "ke", "pada", "kepada", "sama", "bareng", "untuk", "for"}

EMOTES = {
    "smile": ("smile", "grin", "senyum", "tersenyum", "mesem", "senyum-senyum"),
    "wave": ("wave", "lambai", "melambai", "dadah", "lambaikan tangan", "melambaikan tangan",
             "melambaikan"),
    "laugh": ("laugh", "lol", "tertawa", "ketawa", "ngakak", "tawa"),
    "nod": ("nod", "angguk", "mengangguk"),
    "shrug": ("shrug", "angkat bahu", "mengangkat bahu"),
    "clap": ("clap", "applaud", "tepuk tangan", "bertepuk tangan", "keplok"),
    "cheer": ("cheer", "hooray", "yay", "sorak", "bersorak", "hore", "horee"),
    "sigh": ("sigh", "hela napas", "menghela napas", "hela nafas", "menghela nafas", "huft"),
    "bow": ("bow", "membungkuk", "bungkuk", "hormat", "beri hormat"),
    "dance": ("dance", "joget", "berjoget", "menari", "nari", "goyang"),
    "hug": ("hug", "peluk", "memeluk", "pelukan"),
}

# (words, what they mean), longest first when matched.
_VERBS = [
    # asking the client itself
    (("help",), "help"), (("commands",), "help"), (("bantuan",), "help"), (("?",), "help"),
    (("daftar", "perintah"), "help"), (("perintah",), "help"),
    (("connect",), "connect"), (("reconnect",), "connect"), (("sambungkan",), "connect"),
    (("sambung",), "connect"), (("hubungkan",), "connect"),
    (("disconnect",), "disconnect"), (("quit",), "disconnect"), (("logout",), "disconnect"),
    (("putuskan",), "disconnect"), (("putus",), "disconnect"), (("keluar",), "disconnect"),
    (("keluar", "dari", "orbit"), "disconnect"), (("log", "out"), "disconnect"),
    (("leave", "orbit"), "disconnect"), (("exit",), "disconnect"),
    (("status",), "status"), (("status", "orbit"), "status"), (("connection", "status"), "status"),
    (("pengaturan",), "settings"), (("settings",), "settings"), (("preferences",), "settings"),
    (("setelan",), "settings"), (("options",), "settings"),
    (("abaikan",), "ignore"), (("ignore",), "ignore"), (("daftar", "abaikan"), "ignored"),
    (("ignored",), "ignored"), (("ignore", "list"), "ignored"),
    (("ingatkan", "aku"), "remind"), (("ingatkan", "saya"), "remind"), (("remind", "me"), "remind"),
    (("remind", "me", "of"), "remind"), (("remind", "me", "about"), "remind"), (("ingatkan", "aku", "soal"), "remind"),
    (("pengingat", "acara"), "remind"), (("event", "reminder"), "remind"),
    (("dengar", "lagi"), "unignore"), (("unignore",), "unignore"), (("jangan", "abaikan"), "unignore"),
    (("berhenti", "abaikan"), "unignore"), (("stop", "ignoring"), "unignore"),
    # the server reads these itself: words this reader would take for something else
    (("beri", "kredit"), "raw"), (("ambil", "kredit"), "raw"), (("beri", "item"), "raw"),
    (("take", "off"), "raw"), (("take", "credits"), "raw"), (("board", "the", "kancil"), "raw"),
    (("board", "kancil"), "raw"), (("board", "the", "shuttle"), "raw"), (("board", "shuttle"), "raw"),
    (("transfer", "code"), "raw"), (("lihat", "papan", "skor"), "raw"), (("give", "item"), "raw"),
    (("lihat", "peta"), "raw"), (("cek", "lahan"), "raw"),
    (("terbang", "ke"), "raw"), (("fly", "to"), "raw"), (("board", "ship"), "raw"), (("board", "my", "ship"), "raw"),
    (("get", "off"), "raw"), (("take", "the", "ferry"), "raw"), (("take", "a", "gig"), "raw"),
    (("ambil", "gig"), "raw"), (("cek", "kapal"), "raw"), (("lihat", "dunia"), "raw"),
    (("bicara", "dengan"), "raw"), (("bicara", "sama"), "raw"), (("beri", "makan"), "raw"),
    (("kasih", "makan"), "raw"), (("beri", "pakan"), "raw"), (("say", "hi", "to"), "raw"),
    (("say", "hello", "to"), "raw"),
    (("repeat",), "repeat"), (("again",), "repeat"), (("ulangi",), "repeat"), (("ulang",), "repeat"),
    (("apa", "tadi"), "repeat"),
    # missions, before "look" and "take"
    (("missions",), "missions"), (("mission", "board"), "missions"), (("board",), "missions"),
    (("check", "missions"), "missions"), (("list", "missions"), "missions"),
    (("misi",), "missions"), (("papan", "misi"), "missions"), (("lihat", "misi"), "missions"),
    (("cek", "misi"), "missions"), (("daftar", "misi"), "missions"), (("lihat", "papan"), "missions"),
    (("accept", "mission"), "accept"), (("accept",), "accept"), (("take", "mission"), "accept"),
    (("ambil", "misi"), "accept"), (("terima", "misi"), "accept"), (("terima",), "accept"),
    (("pilih", "misi"), "accept"),
    (("complete", "mission"), "complete"), (("complete",), "complete"), (("deliver",), "complete"),
    (("turn", "in"), "complete"), (("hand", "in"), "complete"), (("finish", "mission"), "complete"),
    (("selesaikan", "misi"), "complete"), (("selesaikan",), "complete"), (("selesai",), "complete"),
    (("serahkan",), "complete"), (("setor",), "complete"), (("lapor", "misi"), "complete"),
    (("abandon", "mission"), "abandon"), (("abandon",), "abandon"), (("drop", "mission"), "abandon"),
    (("cancel", "mission"), "abandon"), (("batalkan", "misi"), "abandon"),
    (("batal", "misi"), "abandon"), (("tinggalkan", "misi"), "abandon"),
    # the market
    (("prices",), "prices"), (("price",), "prices"), (("market",), "prices"),
    (("check", "prices"), "prices"), (("price", "list"), "prices"),
    (("harga",), "prices"), (("cek", "harga"), "prices"), (("lihat", "harga"), "prices"),
    (("pasar",), "prices"), (("daftar", "harga"), "prices"),
    (("buy",), "buy"), (("beli",), "buy"), (("membeli",), "buy"),
    (("sell",), "sell"), (("jual",), "sell"), (("menjual",), "sell"),
    # you and your things
    (("inventory",), "inventory"), (("inv",), "inventory"), (("i",), "inventory"),
    (("credits",), "inventory"), (("check", "credits"), "inventory"), (("balance",), "inventory"),
    (("money",), "inventory"), (("bag",), "inventory"), (("my", "bag"), "inventory"),
    (("tas",), "inventory"), (("inventaris",), "inventory"), (("kredit",), "inventory"),
    (("cek", "kredit"), "inventory"), (("lihat", "kredit"), "inventory"), (("saldo",), "inventory"),
    (("cek", "saldo"), "inventory"), (("uang",), "inventory"), (("barang",), "inventory"),
    (("barangku",), "inventory"), (("isi", "tas"), "inventory"), (("cek", "tas"), "inventory"),
    (("lihat", "tas"), "inventory"), (("kreditku",), "inventory"),
    (("give",), "give"), (("pay",), "give"), (("send",), "give"), (("beri",), "give"),
    (("berikan",), "give"), (("kasih",), "give"), (("kasi",), "give"), (("bayar",), "give"),
    (("transfer",), "give"), (("kirim",), "give"),
    (("describe", "me"), "describe"), (("describe", "myself"), "describe"),
    (("describe",), "describe"), (("set", "description"), "describe"),
    (("description",), "describe"), (("deskripsi", "aku"), "describe"),
    (("deskripsi", "diriku"), "describe"), (("deskripsiku",), "describe"),
    (("deskripsi",), "describe"), (("gambarkan", "aku"), "describe"),
    (("gambarkan", "diriku"), "describe"),
    # work
    (("work",), "work"), (("start", "work"), "work"), (("shift",), "work"),
    (("start", "shift"), "work"), (("repair", "the", "reactor"), "work"),
    (("repair", "reactor"), "work"), (("fix", "reactor"), "work"), (("repair",), "repair"),
    (("fix",), "repair"), (("fly",), "work"), (("cargo", "run"), "work"),
    (("market", "report"), "work"),
    (("kerja",), "work"), (("bekerja",), "work"), (("mulai", "kerja"), "work"),
    (("perbaiki", "reaktor"), "work"), (("perbaiki",), "repair"), (("terbang",), "work"),
    (("antar", "kargo"), "work"),
    (("laporan", "pasar"), "work"),
    (("answer",), "answer"), (("jawab",), "answer"), (("sequence",), "answer"),
    (("urutan",), "answer"), (("urutannya",), "answer"),
    # talking
    (("say",), "say"), (("bilang",), "say"), (("katakan",), "say"), (("ucap",), "say"),
    (("ucapkan",), "say"), (("ngomong",), "say"), (("bicara",), "say"), (("berkata",), "say"),
    (("whisper", "to"), "whisper"), (("whisper",), "whisper"), (("tell",), "whisper"),
    (("msg",), "whisper"), (("pm",), "whisper"),
    (("bisik", "ke"), "whisper"), (("bisik", "pada"), "whisper"), (("bisik",), "whisper"),
    (("bisikkan", "ke"), "whisper"), (("bisikkan",), "whisper"), (("bisiki",), "whisper"),
    (("berbisik", "ke"), "whisper"), (("berbisik", "pada"), "whisper"),
    (("berbisik", "kepada"), "whisper"), (("berbisik",), "whisper"),
    (("shout",), "shout"), (("yell",), "shout"), (("broadcast",), "shout"),
    (("teriak",), "shout"), (("teriakkan",), "shout"), (("berteriak",), "shout"),
    # who
    (("who",), "who"), (("who", "is", "online"), "who"), (("whos", "online"), "who"),
    (("who's", "online"), "who"), (("online",), "who"), (("players",), "who"),
    (("siapa",), "who"), (("siapa", "online"), "who"), (("siapa", "saja"), "who"),
    (("siapa", "yang", "online"), "who"), (("siapa", "saja", "yang", "online"), "who"),
    (("daftar", "pemain"), "who"),
    # looking
    (("look", "around"), "look_around"), (("look", "at"), "look"), (("look",), "look"),
    (("l",), "look"), (("examine",), "look"), (("inspect",), "look"),
    (("lihat", "sekitar"), "look_around"), (("lihat", "lihat"), "look_around"),
    (("lihat",), "look"), (("liat",), "look"), (("periksa",), "look"), (("amati",), "look"),
    (("cek",), "look"),
    # going
    (("go", "to"), "go"), (("go",), "go"), (("walk", "to"), "go"), (("walk",), "go"),
    (("head", "to"), "go"), (("move", "to"), "go"), (("enter",), "go"), (("travel", "to"), "go"),
    (("run", "to"), "go"),
    (("pergi", "ke"), "go"), (("pergi",), "go"), (("jalan", "ke"), "go"),
    (("berjalan", "ke"), "go"), (("ke",), "go"), (("masuk", "ke"), "go"), (("masuk",), "go"),
    (("menuju",), "go"), (("kembali", "ke"), "go"), (("balik", "ke"), "go"),
    (("pulang", "ke"), "go"), (("pindah", "ke"), "go"), (("pulang",), "go_home"),
    # taking things for missions
    (("pick", "up"), "take"), (("take",), "take"), (("get",), "take"), (("grab",), "take"),
    (("ambil",), "take"), (("angkat",), "take"), (("pungut",), "take"),
    # admin (the server checks who may)
    (("mute",), "mute"), (("bisukan",), "mute"), (("unmute",), "unmute"),
    (("kick",), "kick"), (("tendang",), "kick"), (("ban",), "ban"), (("unban",), "unban"),
    (("announce",), "announce"), (("umumkan",), "announce"),
]
_VERBS.sort(key=lambda entry: -len(entry[0]))

_EMOTE_PHRASES = sorted(((tuple(p.split()), eid) for eid, phrases in EMOTES.items()
                         for p in phrases), key=lambda e: -len(e[0]))

_ALL_WORDS = {"all", "semua", "semuanya", "everything"}
_ON_WORDS = {"on", "nyala", "hidup", "aktif", "nyalakan", "hidupkan", "aktifkan", "enable", "yes", "ya"}
_OFF_WORDS = {"off", "mati", "matikan", "nonaktif", "nonaktifkan", "disable", "no", "tidak"}
# What the quick settings are called: (words, setting).
_SETTINGS = sorted([
    (("suara", "pemain"), "voices"), (("suara", "orang"), "voices"), (("voices",), "voices"),
    (("player", "voices"), "voices"), (("players", "voices"), "voices"),
    (("bacakan", "pesan"), "speak"), (("baca", "pesan"), "speak"), (("speech",), "speak"),
    (("speak", "messages"), "speak"), (("read", "aloud"), "speak"),
    (("ambience",), "ambience"), (("ambiance",), "ambience"), (("suasana",), "ambience"),
    (("suasana", "latar"), "ambience"),
    (("suara", "efek"), "sounds"), (("efek", "suara"), "sounds"), (("bunyi",), "sounds"),
    (("sounds",), "sounds"), (("sound", "effects"), "sounds"), (("effects",), "sounds"),
    (("kata-kataku",), "speak_own"), (("kata", "kataku"), "speak_own"), (("suaraku", "sendiri"), "speak_own"),
    (("my", "lines"), "speak_own"), (("own", "lines"), "speak_own"), (("my", "own", "voice"), "speak_own"),
    (("nama", "pemain"), "speak_names"), (("sebut", "nama"), "speak_names"), (("names",), "speak_names"),
    (("player", "names"), "speak_names"), (("speaker", "names"), "speak_names"),
    (("suara", "orang", "lain"), "other_sounds"), (("other", "sounds"), "other_sounds"),
    (("other", "players", "sounds"), "other_sounds"), (("others", "sounds"), "other_sounds"),
], key=lambda e: -len(e[0]))
# Who reads the game aloud ("reader"): the screen reader, Hariku Voice, or both.
_READERS = {
    ("pembaca", "nvda"): "nvda", ("reader", "nvda"): "nvda", ("baca", "pakai", "nvda"): "nvda",
    ("nvda", "saja"): "nvda", ("nvda", "only"): "nvda", ("pembaca", "layar"): "nvda",
    ("screen", "reader"): "nvda",
    ("pembaca", "campuran"): "mixed", ("reader", "mixed"): "mixed", ("campuran",): "mixed",
    ("pembaca", "suara"): "voices", ("reader", "voices"): "voices", ("pembaca", "hariku"): "voices",
    ("semua", "suara", "hariku"): "voices", ("all", "voices"): "voices",
}
_VOLUMES = sorted([
    (("volume", "efek"), "effects_volume"), (("effects", "volume"), "effects_volume"),
    (("volume", "suara", "efek"), "effects_volume"), (("volume", "bunyi"), "effects_volume"),
    (("volume", "suasana"), "ambience_volume"), (("ambience", "volume"), "ambience_volume"),
    (("volume", "ambience"), "ambience_volume"),
], key=lambda e: -len(e[0]))
_CREDIT_WORDS = {"credit", "credits", "kredit", "cr", "uang", "duit"}


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
    """The text without "orbit", "tolong", "please"... in front."""
    text = str(text or "").strip()
    while True:
        tokens = _tokens(text)
        if len(tokens) > 1 and tokens[0][2] in PREFIXES:
            text = text[tokens[1][0]:].strip()
            continue
        return text


def _target_after(text, tokens, index):
    """A name after an optional "to"/"ke"/"pada" (for emotes)."""
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
        return None, 0     # "senyum itu ibadah": a sentence, not a gesture
    message = {"c": "emote", "e": emote}
    target = _target_after(text, tokens, used)
    if target:
        message["to"] = target
    return message, used


def _give(text, tokens, index):
    """ "Sari 50 kredit", "50 credits to Sari", "Sari kopi", "ke Sari 2 kopi"."""
    words = tokens[index:]
    if not words:
        return {"c": "give"}
    name, what = None, []
    for i, (_s, _e, word) in enumerate(words):
        if word in ("to", "ke", "kepada", "untuk", "pada") and i + 1 < len(words):
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
    """ "2 kopi", "kopi", "semua kopi", "all coffee", "kopi 3"."""
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
    """A quick setting ("suara pemain mati", "matikan ambience", "effects volume 40"), or None."""
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
        return emote                        # "angkat bahu" is a shrug, not "take"

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
        return {"c": "accept", "n": _number(rest)}      # "misi 2"
    if meaning == "prices":
        return {"c": "prices", "a": rest} if rest else {"c": "prices"}
    if meaning == "look_around":
        return {"c": "look"}
    if meaning == "look":
        return {"c": "look", "a": rest} if rest else {"c": "look"}
    if meaning == "go":
        return {"c": "go", "a": rest}
    if meaning == "go_home":
        return {"c": "go", "a": rest or "kabin"}
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
