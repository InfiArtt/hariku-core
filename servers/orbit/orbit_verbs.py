# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Plain text a player typed or said, in English, read as one of the server's
commands.

The client reads the commands it knows itself (say, whisper, buy...) and
sends anything else as {"c": "text", "a": ...}; Orbit 1.0's client knows
none of the commands that came later, so the server reads them here, and
every client can use them:

    parse("s")                    -> {"c": "move", "d": "s"}
    parse("u")                    -> {"c": "move", "d": "u"}      ("u" is up)
    parse("way to the cantina")   -> {"c": "way", "a": "the cantina"}
    parse("guide me to the cantina")
                                  -> {"c": "guide", "a": "the cantina"}
    parse("stop guide")           -> {"c": "guide", "op": "stop"}
    parse("plant 2 tomato")       -> {"c": "plant", "item": "tomato", "n": 2}
    parse("ride the wombat")      -> {"c": "board"}
    parse("fly to Karmina")       -> {"c": "fly", "a": "Karmina"}
    parse("dice 50 high")         -> {"c": "dice", "a": "high", "n": 50}
    parse("x here")               -> {"c": "examine", "a": "here"}   (and "what can I do here")
    parse("x Rocco")              -> {"c": "examine", "a": "Rocco"}
    parse("offer Sam 3 iron for 200 credits")
                                  -> {"c": "offer", "to": "Sam", "a": "3 iron for 200 credits"}
    parse("grant Sam 50")         -> {"c": "admin", "op": "grant", "to": "Sam", "n": 50}

Orbit is played in English (since 1.4): words in other languages aren't read
here, and the server answers them with its help hint. `find_direction(word)`
comes from the world (its direction words), so the words for directions live
in world.json. No I/O.
"""

import re

_TOKEN_RE = re.compile(r"\S+")
_EDGE = ".,!?;:\"'()[]“”‘’"

# (words, meaning), longest first when matched.
VERBS = [
    # moving and finding the way
    (("way", "to"), "way"), (("route", "to"), "way"), (("directions", "to"), "way"),
    (("path", "to"), "way"), (("how", "do", "i", "get", "to"), "way"), (("way",), "way"),
    (("route",), "way"),
    (("guide", "me", "to"), "guide"), (("guide", "to"), "guide"), (("guide", "me"), "guide"),
    (("guide",), "guide"),
    (("stop", "guide"), "guide_stop"), (("stop", "guiding"), "guide_stop"),
    (("stop", "guiding", "me"), "guide_stop"), (("stop", "guidance"), "guide_stop"),
    (("stop", "the", "guide"), "guide_stop"), (("cancel", "guide"), "guide_stop"),
    (("cancel", "guidance"), "guide_stop"), (("end", "guide"), "guide_stop"), (("end", "guidance"), "guide_stop"),
    (("guide", "off"), "guide_stop"),
    (("map",), "map"),
    (("where", "am", "i"), "where"), (("whereami",), "where"), (("location",), "where"),
    (("compass",), "compass"), (("heading",), "compass"),
    (("scan",), "scan"),
    (("locate",), "locate"), (("find",), "locate"), (("where", "is"), "locate"),
    (("board",), "board"), (("board", "the", "wombat"), "board"), (("board", "wombat"), "board"),
    (("board", "shuttle"), "board"), (("board", "the", "shuttle"), "board"),
    (("depart",), "board"), (("ride",), "board"),
    (("ride", "the", "wombat"), "board"), (("ride", "wombat"), "board"), (("ride", "the", "shuttle"), "board"),
    (("ride", "shuttle"), "board"),
    # the temple of the Way of Starlight
    (("ring", "bell"), "ring"), (("ring", "the", "bell"), "ring"), (("ring", "the", "star", "bell"), "ring"),
    (("light", "lantern"), "lantern"),
    (("light", "a", "lantern"), "lantern"), (("light", "the", "lantern"), "lantern"),
    (("light", "a", "star", "lantern"), "lantern"),
    (("read",), "read"),
    # what you can do here, or with someone or something (the Nova Realm's examine)
    (("x",), "examine"), (("examine",), "examine"), (("what", "can", "i", "do", "with"), "examine"),
    (("what", "can", "i", "do", "here"), "examine_here"), (("what", "can", "i", "do"), "examine_here"),
    (("commands", "here"), "examine_here"), (("actions", "here"), "examine_here"),
    # things
    (("open",), "open"),
    (("use",), "use"), (("drink",), "use"), (("eat",), "use"),
    (("equip",), "equip"), (("wear",), "equip"),
    (("put", "on"), "equip"), (("place",), "equip"), (("set", "beacon"), "equip"),
    (("unequip",), "unequip"), (("take", "off"), "unequip"), (("remove",), "unequip"),
    (("list",), "list"), (("stock",), "list"), (("catalog",), "list"), (("menu",), "list"),
    (("shop",), "shop"),
    # friends and visitors
    (("friends",), "friends"),
    (("add", "friend"), "friend_add"),
    (("remove", "friend"), "friend_remove"), (("unfriend",), "friend_remove"),
    (("invite",), "invite"),
    (("uninvite",), "uninvite"),
    (("visit",), "visit"),
    (("pat",), "pat"), (("pet",), "pat"),
    (("name", "pet"), "name_pet"), (("name", "my", "pet"), "name_pet"),
    (("rename", "pet"), "name_pet"), (("rename",), "name_pet"),
    (("pet", "status"), "pet_status"), (("my", "pet"), "pet_status"), (("my", "pets"), "pet_status"),
    (("feed",), "pet_feed"),
    (("play", "with"), "pet_play"),
    (("rest",), "pet_rest"),
    (("teach", "trick"), "pet_teach"), (("teach",), "pet_teach"), (("train",), "pet_teach"),
    (("trick",), "pet_trick"), (("tricks",), "pet_trick"), (("do", "trick"), "pet_trick"),
    (("show", "trick"), "pet_trick"), (("perform",), "pet_trick"),
    # you, your progress
    (("daily",), "daily"), (("daily", "bonus"), "daily"),
    (("claim",), "daily"), (("claim", "daily"), "daily"),
    (("profile",), "profile"),
    (("rank",), "rank"), (("level",), "rank"), (("xp",), "rank"),
    (("my", "voice"), "voice"), (("voice",), "voice"),
    (("transfer", "code"), "transfer"),
    (("move", "character"), "transfer"), (("move", "my", "character"), "transfer"),
    # the farm, mining, salvage
    (("plant",), "plant"), (("sow",), "plant"),
    (("harvest",), "harvest"),
    (("water",), "water"), (("water", "plants"), "water"),
    (("plots",), "farm"), (("my", "plots"), "farm"), (("farm",), "farm"), (("my", "farm"), "farm"),
    (("mine",), "mine"), (("dig",), "mine"),
    (("collect",), "collect"), (("salvage",), "collect"),
    # travel between worlds, ships
    (("worlds",), "worlds"), (("planets",), "worlds"), (("planet",), "worlds"),
    (("list", "worlds"), "worlds"),
    (("gate",), "gate"), (("gate", "to"), "gate"), (("enter", "the", "gate", "to"), "gate"),
    (("step", "through", "the", "gate", "to"), "gate"),
    (("take", "the", "gate", "to"), "gate"), (("use", "the", "gate", "to"), "gate"),
    (("ferry",), "ferry"), (("ferry", "to"), "ferry"), (("take", "the", "ferry", "to"), "ferry"),
    (("ride", "the", "ferry", "to"), "ferry"), (("catch", "the", "ferry", "to"), "ferry"),
    (("take", "the", "ferry"), "ferry"), (("ride", "the", "ferry"), "ferry"),
    (("embark",), "embark"), (("go", "aboard"), "embark"),
    (("board", "ship"), "embark"), (("board", "my", "ship"), "embark"), (("enter", "my", "ship"), "embark"),
    (("get", "in", "the", "ship"), "embark"), (("aboard",), "embark"),
    (("disembark",), "disembark"), (("leave", "the", "ship"), "disembark"),
    (("leave", "ship"), "disembark"), (("get", "off", "the", "ship"), "disembark"),
    (("get", "off", "the", "ferry"), "disembark"),
    (("fly", "to"), "fly"), (("set", "course", "for"), "fly"),
    (("set", "course", "to"), "fly"), (("launch", "to"), "fly"),
    (("refuel",), "refuel"), (("fuel", "up"), "refuel"),
    (("load",), "load"),
    (("unload",), "unload"),
    (("cargo",), "cargo"), (("my", "ship"), "cargo"), (("ship", "status"), "cargo"),
    (("name", "ship"), "name_ship"), (("name", "my", "ship"), "name_ship"), (("rename", "ship"), "name_ship"),
    # the other worlds' work
    (("face",), "face"), (("approach",), "face"),
    (("gig",), "gig"), (("take", "a", "gig"), "gig"), (("courier", "job"), "gig"), (("delivery",), "gig"),
    # the hunt
    (("hunt",), "hunt"), (("the", "hunt"), "hunt"),
    (("lost", "chord"), "hunt"), (("the", "lost", "chord"), "hunt"),
    (("investigate",), "investigate"), (("look", "for", "clues"), "investigate"),
    (("solve",), "solve"), (("my", "answer", "is"), "solve"),
    (("hunt", "board"), "hunt_board"), (("hunters",), "hunt_board"),
    (("hunt", "status"), "hunt_status"),
    (("new", "season"), "new_season"),
    (("release", "hint"), "release_hint"),
    (("hunt", "test"), "hunt_test"),
    # events
    (("events",), "events"), (("event",), "events"), (("agenda",), "events"),
    (("what's", "on"), "events"), (("whats", "on"), "events"),
    (("join",), "join"), (("join", "event"), "join"), (("join", "in"), "join"), (("open", "gift"), "join"),
    (("listen",), "listen"), (("listen", "for"), "listen"),
    (("catch",), "catch"), (("catch", "robot"), "catch"), (("catch", "the", "robot"), "catch"),
    (("search",), "search"), (("search", "room"), "search"), (("search", "the", "room"), "search"),
    (("watch",), "watch"), (("watch", "comet"), "watch"), (("watch", "the", "comet"), "watch"),
    (("watch", "fireworks"), "watch"),
    (("host", "party"), "party"), (("host", "a", "party"), "party"), (("throw", "a", "party"), "party"),
    (("throw", "party"), "party"),
    (("fix", "drone"), "fix"), (("fix", "the", "drone"), "fix"),
    (("repair", "drone"), "fix"), (("repair", "the", "drone"), "fix"),
    (("start", "event"), "event_start"),
    (("stop", "event"), "event_stop"), (("cancel", "event"), "event_stop"),
    (("schedule", "event"), "event_schedule"),
    # the casino
    (("casino",), "casino"), (("casino", "menu"), "casino"),
    (("dice",), "dice"), (("roll",), "dice"), (("roll", "dice"), "dice"), (("roll", "the", "dice"), "dice"),
    (("play", "dice"), "dice"),
    (("slot",), "slots"), (("slots",), "slots"), (("play", "slots"), "slots"), (("play", "the", "slots"), "slots"),
    (("spin",), "slots"), (("slot", "machine"), "slots"),
    (("blackjack",), "blackjack"), (("play", "blackjack"), "blackjack"), (("bj",), "blackjack"),
    (("hit",), "hit"), (("hit", "me"), "hit"), (("another", "card"), "hit"), (("one", "more", "card"), "hit"),
    (("stand",), "stand"), (("i", "stand"), "stand"),
    (("challenge",), "challenge"),
    (("coinflip",), "challenge"), (("coin", "flip"), "challenge"), (("flip", "a", "coin"), "challenge"),
    (("lottery",), "lottery"), (("weekly", "lottery"), "lottery"),
    # the arcade (after the casino's "play dice": longer phrases are matched first)
    (("arcade",), "arcade"), (("the", "arcade"), "arcade"),
    (("play",), "play"),
    (("stop", "game"), "stop_game"), (("stop", "playing"), "stop_game"),
    (("stop", "the", "game"), "stop_game"), (("quit", "game"), "stop_game"),
    (("arcade", "scores"), "high_scores"), (("arcade", "high", "scores"), "high_scores"),
    # crews
    (("crew",), "crew"), (("my", "crew"), "crew"), (("crew", "info"), "crew"),
    (("crew", "create"), "crew_create"), (("create", "crew"), "crew_create"), (("found", "a", "crew"), "crew_create"),
    (("start", "a", "crew"), "crew_create"),
    (("crew", "invite"), "crew_invite"), (("invite", "to", "crew"), "crew_invite"),
    (("crew", "say"), "crew_say"), (("say", "to", "crew"), "crew_say"), (("cs",), "crew_say"),
    (("crew", "leave"), "crew_leave"), (("leave", "crew"), "crew_leave"), (("leave", "the", "crew"), "crew_leave"),
    (("crew", "kick"), "crew_kick"), (("crew", "remove"), "crew_kick"), (("kick", "from", "crew"), "crew_kick"),
    (("crew", "captain"), "crew_captain"), (("make", "captain"), "crew_captain"),
    (("crew", "motto"), "crew_motto"),
    (("crews",), "crews"), (("crew", "board"), "crews"), (("top", "crews"), "crews"),
    (("disband", "crew"), "crew_disband"),
    # duels
    (("duel",), "duel"), (("challenge", "to", "a", "duel"), "duel"), (("duel", "with"), "duel"),
    (("duels", "off"), "duels_off"), (("duel", "off"), "duels_off"), (("no", "duels"), "duels_off"),
    (("duels", "on"), "duels_on"), (("duel", "on"), "duels_on"), (("duels",), "duels"),
    (("stop", "duel"), "duel_stop"), (("stop", "the", "duel"), "duel_stop"),
    # the residents (characters who are not players)
    (("talk", "to"), "talk"), (("talk", "with"), "talk"), (("speak", "to"), "talk"), (("speak", "with"), "talk"),
    (("chat", "with"), "talk"), (("chat", "to"), "talk"), (("talk",), "talk"),
    (("ask",), "ask"),
    (("greet",), "greet"), (("say", "hi", "to"), "greet"), (("say", "hello", "to"), "greet"),
    (("residents",), "residents"), (("npc",), "residents"), (("npcs",), "residents"),
    (("who", "lives", "here"), "residents"),
    # families
    (("partner",), "partner"), (("my", "partner"), "partner"), (("partnership",), "partner"),
    (("partner", "with"), "partner_ask"), (("partner", "up", "with"), "partner_ask"),
    (("be", "partners", "with"), "partner_ask"),
    (("end", "partnership"), "partner_end"), (("end", "the", "partnership"), "partner_end"),
    (("confirm", "end"), "partner_end_confirm"),
    (("adopt",), "adopt"), (("adopt", "a", "baby"), "adopt"), (("adopt", "a", "child"), "adopt"),
    (("family",), "family"), (("my", "family"), "family"), (("child",), "family"),
    (("children",), "family"), (("my", "child"), "family"), (("my", "children"), "family"),
    (("read", "a", "story"), "child_story"), (("tell", "a", "story"), "child_story"),
    (("read", "a", "story", "to"), "child_story"), (("tell", "a", "story", "to"), "child_story"),
    (("bring",), "child_take"),
    (("naming", "rite"), "naming"), (("naming", "ceremony"), "naming"), (("name", "the", "baby"), "naming"),
    (("name", "baby"), "naming"),
    # weddings
    (("propose", "to"), "propose"), (("propose",), "propose"),
    (("wedding",), "wedding"), (("my", "wedding"), "wedding"), (("our", "wedding"), "wedding"),
    (("book", "wedding"), "wedding_book"), (("book", "a", "wedding"), "wedding_book"),
    (("book", "the", "wedding"), "wedding_book"), (("book", "our", "wedding"), "wedding_book"),
    (("book", "venue"), "wedding_book"),
    (("cancel", "wedding"), "wedding_cancel"), (("cancel", "the", "wedding"), "wedding_cancel"),
    (("cancel", "our", "wedding"), "wedding_cancel"),
    (("wedding", "schedule"), "wedding_schedule"), (("weddings",), "wedding_schedule"),
    (("invitations",), "wedding_invitations"), (("my", "invitations"), "wedding_invitations"),
    (("rsvp", "yes"), "wedding_rsvp_yes"), (("i'll", "come"), "wedding_rsvp_yes"),
    (("i", "will", "come"), "wedding_rsvp_yes"),
    (("rsvp", "no"), "wedding_rsvp_no"), (("can't", "come"), "wedding_rsvp_no"),
    (("cannot", "come"), "wedding_rsvp_no"), (("i", "can't", "come"), "wedding_rsvp_no"),
    (("throw", "flowers"), "wedding_flowers"), (("throw", "petals"), "wedding_flowers"),
    (("vow",), "wedding_vow"), (("my", "vow"), "wedding_vow"), (("my", "vow", "is"), "wedding_vow"),
    (("join", "the", "lights"), "wedding_join"), (("join", "lights"), "wedding_join"),
    (("join", "the", "lanterns"), "wedding_join"),
    (("yes",), "wedding_yes"), (("i", "do"), "wedding_yes"),
    (("no",), "wedding_no"),
    (("sign",), "wedding_sign"), (("sign", "the", "register"), "wedding_sign"),
    (("read", "memory"), "wedding_memory"), (("read", "the", "memory"), "wedding_memory"),
    (("read", "memories"), "wedding_memory"), (("memory",), "wedding_memory"), (("memories",), "wedding_memory"),
    (("wedding", "memory"), "wedding_memory"),
    # trading (and anything waiting for a yes)
    (("accept",), "accept"), (("accept", "offer"), "accept"), (("accept", "challenge"), "accept"),
    (("offer",), "offer"), (("trade",), "offer"), (("barter",), "offer"),
    (("decline",), "decline"), (("refuse",), "decline"), (("reject",), "decline"),
    (("decline", "offer"), "decline"),
    (("cancel", "offer"), "cancel_offer"), (("withdraw", "offer"), "cancel_offer"),
    (("cancel", "challenge"), "cancel_offer"),
    # achievements, leaderboards
    (("achievements",), "achievements"), (("achievement",), "achievements"),
    (("my", "achievements"), "achievements"), (("badges",), "achievements"),
    (("leaderboard",), "leaderboard"), (("leaderboards",), "leaderboard"), (("scoreboard",), "leaderboard"),
    (("high", "scores"), "leaderboard"), (("top", "players"), "leaderboard"), (("top",), "leaderboard"),
    # help, the status
    (("help",), "help"),
    (("status",), "status"), (("orbit", "status"), "status"),
    # admin (the game checks who may)
    (("grant",), "grant"), (("grant", "credits"), "grant"),
    (("take", "credits"), "take_credits"),
    (("give", "item"), "give_item"), (("spawn",), "give_item"),
    (("economy",), "economy"),
    (("set", "price"), "set_price"),
    (("reset", "streak"), "reset_streak"),
    (("goto",), "goto"), (("teleport",), "goto"), (("tp",), "goto"),
    (("invisible",), "invisible"),
    (("transfers",), "transfers"),
    (("revoke",), "revoke"),
    (("transfer", "code", "for"), "transfer_for"),
    (("admin", "log"), "admin_log"),
]
VERBS.sort(key=lambda entry: -len(entry[0]))

ADMIN_OPS = {"grant", "take_credits", "give_item", "economy", "set_price", "reset_streak", "goto",
             "invisible", "transfers", "revoke", "transfer_for", "admin_log", "event_start", "event_stop",
             "event_schedule", "hunt_status", "new_season", "release_hint", "hunt_test", "crew_disband",
             "duel_stop"}
_ALL_WORDS = {"all", "everything"}
WALK_WORDS = ("go", "walk", "head")


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
    """ "2 tomato", "tomato 2", "all tomato" -> (item words, n or None or "all")."""
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


def parse(text, _lang=None, find_direction=None):
    """The command in `text`, or None when there is none here."""
    text = " ".join(str(text or "").split())
    tokens = _tokens(text)
    if not tokens:
        return None
    if find_direction is not None:
        d = find_direction(" ".join(t[2] for t in tokens))
        if d:
            return {"c": "move", "d": d}
        if len(tokens) >= 2 and tokens[0][2] in WALK_WORDS:
            d = find_direction(" ".join(t[2] for t in tokens[1:]))
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
    if meaning == "way":
        return {"c": "way", "a": rest}
    if meaning == "guide":
        return {"c": "guide", "a": rest} if rest else {"c": "guide"}
    if meaning == "guide_stop":
        return {"c": "guide", "op": "stop"}
    if meaning in ("map", "where", "compass", "scan", "board", "daily", "rank", "harvest", "water",
                   "farm", "mine", "collect", "transfer", "friends", "status", "casino", "hit", "stand",
                   "lottery", "decline", "cancel_offer", "worlds", "disembark", "cargo", "gig", "events",
                   "join", "listen", "catch", "search", "watch", "party", "hunt", "investigate", "hunt_board"):
        return {"c": meaning}
    if meaning == "locate":
        if not rest:
            return {"c": "where"}
        return {"c": "locate", "to": _word(text, tokens[used])}
    if meaning in ("friend_add", "friend_remove"):
        name, _more = _name_and_rest(text, tokens, used)
        return {"c": "friends", "op": "add" if meaning == "friend_add" else "remove", "to": name}
    if meaning in ("invite", "uninvite", "visit"):
        name, more = _name_and_rest(text, tokens, used)
        if meaning == "visit":
            return {"c": "visit", "to": name}
        more_words = set(more.lower().strip(".,!?").split())
        if meaning == "invite" and "crew" in more_words:
            return {"c": "crew_invite", "to": name}          # "invite Sam to the crew"
        if meaning == "invite" and WEDDING_WORDS & more_words:
            return {"c": "wedding", "op": "invite", "to": name}     # "invite Sam to the wedding"
        return {"c": "invite", "op": "remove" if meaning == "uninvite" else "add", "to": name}
    if meaning == "pat":
        return {"c": "pet", "op": "pat"}
    if meaning == "name_pet":
        return {"c": "pet", "op": "name", "a": rest}
    if meaning.startswith("pet_"):
        return {"c": "pet", "op": meaning[4:], "a": rest}
    if meaning == "open":
        return {"c": "open", "a": rest}
    if meaning == "ring":
        return {"c": "ring"}
    if meaning == "lantern":
        return {"c": "lantern"}
    if meaning == "read":
        return {"c": "look", "a": rest} if rest else None
    if meaning == "examine":
        return {"c": "examine", "a": rest}
    if meaning == "examine_here":
        return {"c": "examine", "a": "here"}
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
    if meaning in ("gate", "ferry", "fly", "face", "name_ship"):
        return {"c": meaning, "a": rest}
    if meaning == "fix":
        return {"c": "work"}
    if meaning == "solve":
        return {"c": "solve", "a": rest}
    if meaning == "play":
        return {"c": "play", "a": rest, "raw": text}       # "play with Kiki" is a pet, not a game
    if meaning == "high_scores":
        return {"c": "high_scores", "a": rest}
    if meaning in ("arcade", "stop_game", "crew", "crew_leave", "crews", "duels"):
        return {"c": meaning}
    if meaning in ("duels_on", "duels_off"):
        return {"c": "duels", "op": meaning[6:]}
    if meaning == "duel":
        name, _more = _name_and_rest(text, tokens, used)
        message = {"c": "duel", "to": name}
        numbers = [_number(t[2]) for t in tokens[used + 1:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
        return message
    if meaning in ("crew_create", "crew_say", "crew_motto"):
        return {"c": meaning, "a": rest}
    if meaning in ("crew_invite", "crew_kick", "crew_captain"):
        name, _more = _name_and_rest(text, tokens, used)
        return {"c": meaning, "to": name}
    if meaning == "embark":
        name, _more = _name_and_rest(text, tokens, used)
        return {"c": "embark", "to": name} if name else {"c": "embark"}
    if meaning == "refuel":
        numbers = [_number(t[2]) for t in tokens[used:] if _number(t[2]) is not None]
        return {"c": "refuel", "n": numbers[0]} if numbers else {"c": "refuel"}
    if meaning in ("load", "unload"):
        item, n = _thing_and_count(tokens, used, allow_all=True)
        message = {"c": meaning, "item": item}
        if n is not None:
            message["n"] = n
        return message
    if meaning in ("talk", "greet"):
        return {"c": meaning, "to": rest}
    if meaning.startswith("partner"):
        op = {"partner": "status", "partner_ask": "ask", "partner_end": "end",
              "partner_end_confirm": "end_confirm"}[meaning]
        name = _word(text, tokens[used]) if op == "ask" and used < len(tokens) else rest
        return {"c": "partner", "op": op, "to": name}
    if meaning in ("adopt", "family"):
        return {"c": meaning}
    if meaning.startswith("child_"):
        words = rest.split()
        while words and words[0].lower() in ("to", "for"):
            words = words[1:]
        while words and words[-1].lower() in ("along", "for", "help"):
            words = words[:-1]
        return {"c": "child", "op": meaning[6:], "a": " ".join(words)}
    if meaning == "naming":
        return {"c": "naming", "a": rest}
    if meaning == "propose":
        return {"c": "wedding", "op": "propose", "to": rest}
    if meaning == "wedding" or meaning.startswith("wedding_"):
        op = "status" if meaning == "wedding" else meaning[8:]
        message = {"c": "wedding", "op": op, "a": rest}
        if op in ("rsvp_yes", "rsvp_no", "cancel"):
            message["to"] = _word(text, tokens[used]).strip(_EDGE) if used < len(tokens) else ""
        return message
    if meaning == "residents":
        return {"c": "residents"}
    if meaning == "ask":
        return _ask(text, tokens, used)
    if meaning == "achievements":
        return {"c": "achievements", "to": _word(text, tokens[used]) if used < len(tokens) else ""}
    if meaning == "leaderboard":
        return {"c": "leaderboard", "a": rest}
    if meaning in ADMIN_OPS:
        return _admin(meaning, text, tokens, used)
    return None


ABOUT_WORDS = ("about", "regarding")
WEDDING_WORDS = {"wedding", "weddings"}
TO_WORDS = ("to",)


def _ask(text, tokens, used):
    """ "ask Rocco about gossip", "ask Oskar about the reactor", "ask Rocco gossip"."""
    start = used
    if start < len(tokens) and tokens[start][2] in TO_WORDS:
        start += 1
    if start >= len(tokens):
        return {"c": "ask", "to": "", "a": ""}
    for i in range(start, len(tokens)):
        if tokens[i][2] in ABOUT_WORDS:
            name = text[tokens[start][0]:tokens[i - 1][1]].strip(_EDGE) if i > start else ""
            return {"c": "ask", "to": name, "a": _rest(text, tokens, i + 1)}
    return {"c": "ask", "to": _word(text, tokens[start]), "a": _rest(text, tokens, start + 1)}


def _admin(op, text, tokens, used):
    message = {"c": "admin", "op": op}
    if op in ("economy", "transfers", "admin_log", "invisible", "hunt_status", "new_season", "hunt_test"):
        return message
    if op == "release_hint":
        numbers = [_number(t[2]) for t in tokens[used:] if _number(t[2]) is not None]
        if numbers:
            message["n"] = numbers[0]
        return message
    if op in ("goto", "event_start", "event_stop", "event_schedule", "crew_disband", "duel_stop"):
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
