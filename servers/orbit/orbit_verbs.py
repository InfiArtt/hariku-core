# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Plain text a player typed or said, in Indonesian or English, read as one of
the server's commands.

The client reads the commands it knows itself (say, whisper, buy...) and
sends anything else as {"c": "text", "a": ...}; Orbit 1.0's client knows
none of the commands that came later, so the server reads them here, and
every client can use them:

    parse("s")                    -> {"c": "move", "d": "s"}
    parse("u", "id")              -> {"c": "move", "d": "n"}      ("u" is utara)
    parse("u", "en")              -> {"c": "move", "d": "u"}      ("u" is up)
    parse("arah ke kantin")       -> {"c": "way", "a": "kantin"}
    parse("tanam 2 tomat")        -> {"c": "plant", "item": "tomat", "n": 2}
    parse("naik kancil")          -> {"c": "board"}
    parse("dadu 50 tinggi")       -> {"c": "dice", "a": "tinggi", "n": 50}
    parse("tawarkan Budi 3 besi untuk 200 kredit")
                                  -> {"c": "offer", "to": "Budi", "a": "3 besi untuk 200 kredit"}
    parse("beri kredit Budi 50")  -> {"c": "admin", "op": "grant", "to": "Budi", "n": 50}

`find_direction(word, lang)` comes from the world (its direction words), so
the words for directions live in world.json. No I/O.
"""

import re

_TOKEN_RE = re.compile(r"\S+")
_EDGE = ".,!?;:\"'()[]“”‘’"

# (words, meaning), longest first when matched.
VERBS = [
    # moving and finding the way
    (("arah", "ke"), "way"), (("arah", "menuju"), "way"), (("rute", "ke"), "way"), (("rute",), "way"),
    (("jalan", "menuju"), "way"), (("bagaimana", "ke"), "way"), (("gimana", "ke"), "way"),
    (("way", "to"), "way"), (("route", "to"), "way"), (("directions", "to"), "way"),
    (("path", "to"), "way"), (("how", "do", "i", "get", "to"), "way"), (("way",), "way"),
    (("arah",), "way"), (("route",), "way"),
    (("peta",), "map"), (("map",), "map"), (("denah",), "map"), (("peta", "dek"), "map"),
    (("di", "mana", "aku"), "where"), (("dimana", "aku"), "where"), (("di", "mana", "saya"), "where"),
    (("dimana", "saya"), "where"), (("aku", "di", "mana"), "where"), (("saya", "di", "mana"), "where"),
    (("where", "am", "i"), "where"), (("whereami",), "where"), (("location",), "where"),
    (("lokasi",), "where"), (("posisi",), "where"), (("posisiku",), "where"), (("lokasiku",), "where"),
    (("kompas",), "compass"), (("compass",), "compass"), (("heading",), "compass"),
    (("pindai",), "scan"), (("scan",), "scan"), (("memindai",), "scan"),
    (("lacak",), "locate"), (("locate",), "locate"), (("find",), "locate"), (("cari",), "locate"),
    (("di", "mana"), "locate"), (("dimana",), "locate"), (("where", "is"), "locate"),
    (("naik", "kancil"), "board"), (("naik", "shuttle"), "board"), (("naik", "pesawat"), "board"),
    (("naik", "ulang-alik"), "board"), (("board",), "board"), (("board", "the", "kancil"), "board"),
    (("board", "kancil"), "board"), (("board", "shuttle"), "board"), (("board", "the", "shuttle"), "board"),
    (("berangkat",), "board"), (("depart",), "board"), (("ride",), "board"),
    (("ride", "the", "kancil"), "board"), (("ride", "kancil"), "board"), (("ride", "the", "shuttle"), "board"),
    (("ride", "shuttle"), "board"), (("naik", "lift"), "up"),
    (("naik", "tangga"), "up"), (("turun", "tangga"), "down"), (("turun", "lift"), "down"),
    # the temple of the Way of Starlight
    (("bunyikan", "lonceng"), "ring"), (("ring", "bell"), "ring"), (("ring", "the", "bell"), "ring"),
    (("pukul", "lonceng"), "ring"), (("ring", "the", "star", "bell"), "ring"),
    (("bunyikan", "lonceng", "bintang"), "ring"),
    (("nyalakan", "lentera"), "lantern"), (("light", "lantern"), "lantern"),
    (("light", "a", "lantern"), "lantern"), (("light", "the", "lantern"), "lantern"),
    (("nyalakan", "lentera", "bintang"), "lantern"), (("light", "a", "star", "lantern"), "lantern"),
    (("baca",), "read"), (("read",), "read"), (("membaca",), "read"),
    # things
    (("buka",), "open"), (("open",), "open"),
    (("pakai",), "use"), (("use",), "use"), (("gunakan",), "use"), (("minum",), "use"),
    (("drink",), "use"), (("makan",), "use"), (("eat",), "use"), (("nyalakan",), "use"),
    (("pasang",), "equip"), (("equip",), "equip"), (("wear",), "equip"), (("kenakan",), "equip"),
    (("put", "on"), "equip"), (("place",), "equip"), (("set", "beacon"), "equip"),
    (("lepas",), "unequip"), (("lepaskan",), "unequip"), (("copot",), "unequip"),
    (("unequip",), "unequip"), (("take", "off"), "unequip"), (("remove",), "unequip"),
    (("daftar",), "list"), (("list",), "list"), (("stok",), "list"), (("stock",), "list"),
    (("katalog",), "list"), (("catalog",), "list"), (("menu",), "list"),
    (("toko",), "shop"), (("shop",), "shop"), (("belanja",), "shop"),
    # friends and visitors
    (("teman",), "friends"), (("friends",), "friends"), (("daftar", "teman"), "friends"),
    (("tambah", "teman"), "friend_add"), (("add", "friend"), "friend_add"),
    (("hapus", "teman"), "friend_remove"), (("remove", "friend"), "friend_remove"),
    (("unfriend",), "friend_remove"),
    (("undang",), "invite"), (("invite",), "invite"), (("ajak",), "invite"),
    (("usir",), "uninvite"), (("uninvite",), "uninvite"), (("batal", "undang"), "uninvite"),
    (("kunjungi",), "visit"), (("visit",), "visit"), (("mampir", "ke"), "visit"), (("mampir",), "visit"),
    (("bertamu", "ke"), "visit"),
    (("elus",), "pat"), (("pat",), "pat"), (("usap",), "pat"), (("pet",), "pat"),
    (("namai",), "name_pet"), (("name", "pet"), "name_pet"), (("name", "my", "pet"), "name_pet"),
    (("rename", "pet"), "name_pet"),
    # you, your progress
    (("harian",), "daily"), (("daily",), "daily"), (("bonus", "harian"), "daily"),
    (("daily", "bonus"), "daily"), (("klaim", "harian"), "daily"), (("klaim",), "daily"),
    (("claim",), "daily"), (("claim", "daily"), "daily"), (("hadiah", "harian"), "daily"),
    (("profil",), "profile"), (("profile",), "profile"), (("profilku",), "profile"),
    (("peringkat",), "rank"), (("rank",), "rank"), (("pangkat",), "rank"), (("level",), "rank"),
    (("xp",), "rank"), (("levelku",), "rank"),
    (("suaraku",), "voice"), (("my", "voice"), "voice"), (("suara", "saya"), "voice"),
    (("suara", "ku"), "voice"), (("voice",), "voice"),
    (("kode", "pindah"), "transfer"), (("transfer", "code"), "transfer"),
    (("pindah", "komputer"), "transfer"), (("move", "character"), "transfer"),
    (("move", "my", "character"), "transfer"), (("pindahkan", "karakter"), "transfer"),
    # the farm, mining, salvage
    (("tanam",), "plant"), (("plant",), "plant"), (("menanam",), "plant"), (("sow",), "plant"),
    (("panen",), "harvest"), (("harvest",), "harvest"), (("memanen",), "harvest"), (("petik",), "harvest"),
    (("siram",), "water"), (("water",), "water"), (("sirami",), "water"), (("menyiram",), "water"),
    (("siram", "tanaman"), "water"), (("water", "plants"), "water"),
    (("lahan",), "farm"), (("petak",), "farm"), (("plots",), "farm"), (("my", "plots"), "farm"),
    (("farm",), "farm"), (("my", "farm"), "farm"), (("lahanku",), "farm"), (("kebunku",), "farm"),
    (("tambang",), "mine"), (("mine",), "mine"), (("menambang",), "mine"), (("gali",), "mine"),
    (("dig",), "mine"),
    (("kumpulkan",), "collect"), (("collect",), "collect"), (("salvage",), "collect"),
    (("pulung",), "collect"), (("memulung",), "collect"), (("kais",), "collect"),
    # the casino
    (("kasino",), "casino"), (("casino",), "casino"), (("menu", "kasino"), "casino"),
    (("casino", "menu"), "casino"),
    (("dadu",), "dice"), (("lempar", "dadu"), "dice"), (("main", "dadu"), "dice"), (("kocok", "dadu"), "dice"),
    (("dice",), "dice"), (("roll",), "dice"), (("roll", "dice"), "dice"), (("roll", "the", "dice"), "dice"),
    (("play", "dice"), "dice"),
    (("slot",), "slots"), (("slots",), "slots"), (("main", "slot"), "slots"), (("mesin", "slot"), "slots"),
    (("putar", "slot"), "slots"), (("play", "slots"), "slots"), (("play", "the", "slots"), "slots"),
    (("spin",), "slots"), (("slot", "machine"), "slots"),
    (("blackjack",), "blackjack"), (("main", "blackjack"), "blackjack"), (("play", "blackjack"), "blackjack"),
    (("bj",), "blackjack"), (("main", "kartu"), "blackjack"),
    (("hit",), "hit"), (("hit", "me"), "hit"), (("tambah", "kartu"), "hit"), (("kartu", "lagi"), "hit"),
    (("minta", "kartu"), "hit"), (("another", "card"), "hit"), (("one", "more", "card"), "hit"),
    (("stand",), "stand"), (("cukup",), "stand"), (("sudah", "cukup"), "stand"),
    (("i", "stand"), "stand"),
    (("tantang",), "challenge"), (("challenge",), "challenge"), (("lempar", "koin"), "challenge"),
    (("coinflip",), "challenge"), (("coin", "flip"), "challenge"), (("flip", "a", "coin"), "challenge"),
    (("adu", "koin"), "challenge"),
    (("lotre",), "lottery"), (("lottery",), "lottery"), (("undian",), "lottery"), (("lotere",), "lottery"),
    (("lotre", "mingguan"), "lottery"), (("weekly", "lottery"), "lottery"),
    # trading (and anything waiting for a yes)
    (("terima",), "accept"), (("accept",), "accept"), (("terima", "tawaran"), "accept"),
    (("accept", "offer"), "accept"), (("terima", "tantangan"), "accept"), (("accept", "challenge"), "accept"),
    (("tawarkan",), "offer"), (("tawari",), "offer"), (("offer",), "offer"), (("tukar",), "offer"),
    (("trade",), "offer"), (("barter",), "offer"),
    (("tolak",), "decline"), (("decline",), "decline"), (("refuse",), "decline"), (("reject",), "decline"),
    (("menolak",), "decline"), (("tolak", "tawaran"), "decline"), (("decline", "offer"), "decline"),
    (("tolak", "tantangan"), "decline"),
    (("batalkan", "tawaran"), "cancel_offer"), (("batal", "tawaran"), "cancel_offer"),
    (("tarik", "tawaran"), "cancel_offer"), (("cancel", "offer"), "cancel_offer"),
    (("withdraw", "offer"), "cancel_offer"), (("cancel", "challenge"), "cancel_offer"),
    (("batalkan", "tantangan"), "cancel_offer"), (("batal", "tantangan"), "cancel_offer"),
    # achievements, leaderboards
    (("prestasi",), "achievements"), (("prestasiku",), "achievements"), (("pencapaian",), "achievements"),
    (("achievements",), "achievements"), (("achievement",), "achievements"),
    (("my", "achievements"), "achievements"), (("badges",), "achievements"), (("lencana",), "achievements"),
    (("papan", "skor"), "leaderboard"), (("papan", "peringkat"), "leaderboard"),
    (("peringkat", "teratas"), "leaderboard"), (("klasemen",), "leaderboard"),
    (("leaderboard",), "leaderboard"), (("leaderboards",), "leaderboard"), (("scoreboard",), "leaderboard"),
    (("high", "scores"), "leaderboard"), (("top", "players"), "leaderboard"), (("top",), "leaderboard"),
    (("lihat", "papan", "skor"), "leaderboard"), (("skor",), "leaderboard"),
    # help, the status
    (("bantuan",), "help"), (("help",), "help"),
    (("status",), "status"), (("status", "orbit"), "status"), (("orbit", "status"), "status"),
    # admin (the game checks who may)
    (("grant",), "grant"), (("beri", "kredit"), "grant"), (("hibah",), "grant"),
    (("grant", "credits"), "grant"),
    (("ambil", "kredit"), "take_credits"), (("take", "credits"), "take_credits"),
    (("beri", "item"), "give_item"), (("give", "item"), "give_item"), (("spawn",), "give_item"),
    (("ekonomi",), "economy"), (("economy",), "economy"),
    (("atur", "harga"), "set_price"), (("set", "price"), "set_price"),
    (("reset", "harian"), "reset_streak"), (("reset", "streak"), "reset_streak"),
    (("reset", "beruntun"), "reset_streak"),
    (("goto",), "goto"), (("teleport",), "goto"), (("tp",), "goto"),
    (("tak", "terlihat"), "invisible"), (("invisible",), "invisible"), (("siluman",), "invisible"),
    (("pindahan",), "transfers"), (("transfers",), "transfers"),
    (("cabut", "akses"), "revoke"), (("revoke",), "revoke"),
    (("kode", "pindah", "untuk"), "transfer_for"), (("transfer", "code", "for"), "transfer_for"),
    (("log", "admin"), "admin_log"), (("admin", "log"), "admin_log"),
]
VERBS.sort(key=lambda entry: -len(entry[0]))

ADMIN_OPS = {"grant", "take_credits", "give_item", "economy", "set_price", "reset_streak", "goto",
             "invisible", "transfers", "revoke", "transfer_for", "admin_log"}
BOARD_WORDS = {"kancil", "shuttle", "pesawat", "ulang-alik"}
_ALL_WORDS = {"all", "semua", "semuanya", "everything"}


def _tokens(text):
    """[(start, end, word)]: each word lower-cased, without punctuation around it."""
    found = []
    for m in _TOKEN_RE.finditer(text):
        word = m.group().lower().strip(_EDGE)
        if word:
            found.append((m.start(), m.end(), word))
    return found


def _number(word):
    try:
        return int(word)
    except (TypeError, ValueError):
        return None


def _word(text, token):
    return text[token[0]:token[1]].strip(_EDGE)


def _rest(text, tokens, index):
    return text[tokens[index][0]:].strip() if index < len(tokens) else ""


def _thing_and_count(tokens, index, allow_all=False):
    """ "2 tomat", "tomat 2", "semua tomat" -> (item words, n or None or "all")."""
    n = None
    words = []
    for _s, _e, word in tokens[index:]:
        if n is None and _number(word) is not None:
            n = _number(word)
        elif n is None and allow_all and word in _ALL_WORDS:
            n = "all"
        else:
            words.append(word)
    return " ".join(words), n


def _name_and_rest(text, tokens, index):
    """The first word (a player's name, in its own case) and what follows."""
    if index >= len(tokens):
        return "", ""
    return _word(text, tokens[index]), _rest(text, tokens, index + 1)


def parse(text, lang="en", find_direction=None):
    """The command in `text`, or None when there is none here."""
    text = " ".join(str(text or "").split())
    tokens = _tokens(text)
    if not tokens:
        return None
    if find_direction is not None:
        d = find_direction(" ".join(t[2] for t in tokens), lang)
        if d:
            return {"c": "move", "d": d}
        if len(tokens) >= 2 and tokens[0][2] in ("go", "walk", "pergi", "jalan", "ke", "head"):
            d = find_direction(" ".join(t[2] for t in tokens[1:]), lang)
            if d:
                return {"c": "move", "d": d}
    words = [t[2] for t in tokens]
    meaning, used = None, 0
    for phrase, what in VERBS:
        if tuple(words[:len(phrase)]) == phrase:
            meaning, used = what, len(phrase)
            break
    if meaning is None:
        return None
    rest = _rest(text, tokens, used)
    if meaning == "up":
        return {"c": "move", "d": "u"}
    if meaning == "down":
        return {"c": "move", "d": "d"}
    if meaning == "way":
        if not rest and words[0] == "arah":
            return {"c": "compass"}
        return {"c": "way", "a": rest}
    if meaning in ("map", "where", "compass", "scan", "board", "daily", "rank", "harvest", "water",
                   "farm", "mine", "collect", "transfer", "friends", "status", "casino", "hit", "stand",
                   "lottery", "decline", "cancel_offer"):
        if meaning == "board" and used == 1 and words[0] == "naik" and rest:
            return None
        return {"c": meaning}
    if meaning == "locate":
        if not rest:
            return {"c": "where"}
        return {"c": "locate", "to": _word(text, tokens[used])}
    if meaning in ("friend_add", "friend_remove"):
        name, _more = _name_and_rest(text, tokens, used)
        return {"c": "friends", "op": "add" if meaning == "friend_add" else "remove", "to": name}
    if meaning in ("invite", "uninvite", "visit"):
        name, _more = _name_and_rest(text, tokens, used)
        if meaning == "visit":
            return {"c": "visit", "to": name}
        return {"c": "invite", "op": "remove" if meaning == "uninvite" else "add", "to": name}
    if meaning == "pat":
        return {"c": "pet", "op": "pat"}
    if meaning == "name_pet":
        return {"c": "pet", "op": "name", "a": rest}
    if meaning == "open":
        return {"c": "open", "a": rest}
    if meaning == "ring":
        return {"c": "ring"}
    if meaning == "lantern":
        return {"c": "lantern"}
    if meaning == "read":
        return {"c": "look", "a": rest} if rest else None
    if meaning in ("use", "equip", "unequip"):
        message = {"c": "unequip" if meaning == "unequip" else "use", "item": rest}
        if meaning == "equip":
            message["equip"] = True
        return message
    if meaning in ("list", "shop"):
        return {"c": "list", "a": rest}
    if meaning == "profile":
        return {"c": "profile", "to": _word(text, tokens[used]) if used < len(tokens) else ""}
    if meaning == "voice":
        return {"c": "voice", "a": rest}
    if meaning == "plant":
        item, n = _thing_and_count(tokens, used)
        message = {"c": "plant", "item": item}
        if n is not None:
            message["n"] = n
        return message
    if meaning == "help":
        return {"c": "help", "a": rest}
    if meaning in ("dice", "slots", "blackjack"):
        choice, n = _thing_and_count(tokens, used)
        message = {"c": meaning}
        if choice and meaning == "dice":
            message["a"] = choice
        if n is not None:
            message["n"] = n
        return message
    if meaning == "challenge":
        name, _more = _name_and_rest(text, tokens, used)
        message = {"c": "challenge", "to": name}
        numbers = [_number(t[2]) for t in tokens[used + 1:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
        return message
    if meaning == "accept":
        numbers = [_number(t[2]) for t in tokens[used:] if _number(t[2]) is not None]
        return {"c": "accept", "n": numbers[0]} if numbers else {"c": "accept"}
    if meaning == "offer":
        name, more = _name_and_rest(text, tokens, used)
        return {"c": "offer", "to": name, "a": more}
    if meaning == "achievements":
        return {"c": "achievements", "to": _word(text, tokens[used]) if used < len(tokens) else ""}
    if meaning == "leaderboard":
        return {"c": "leaderboard", "a": rest}
    if meaning in ADMIN_OPS:
        return _admin(meaning, text, tokens, used)
    return None


def _admin(op, text, tokens, used):
    message = {"c": "admin", "op": op}
    if op in ("economy", "transfers", "admin_log", "invisible"):
        return message
    if op == "goto":
        message["a"] = _rest(text, tokens, used)
        return message
    if op == "set_price":
        item, n = _thing_and_count(tokens, used)
        message["item"] = item
        if n is not None:
            message["n"] = n
        return message
    name, _more = _name_and_rest(text, tokens, used)
    message["to"] = name
    if op in ("grant", "take_credits"):
        numbers = [_number(t[2]) for t in tokens[used + 1:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
    elif op == "give_item":
        item, n = _thing_and_count(tokens, used + 1)
        message["item"] = item
        if n is not None:
            message["n"] = n
    return message
