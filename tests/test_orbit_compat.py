# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Players who haven't updated Orbit keep playing: every command that came
# after Orbit 1.0 must reach the server's right handler from what the 1.0
# client sends for it, from what the 1.4 client sends (both command readers
# are frozen here: orbit_parse_1_0.py and orbit_parse_1_4.py; anything they
# don't know goes as plain text), and from what the current client sends.
# Orbit is played in English (server 1.4, client 1.5): the older clients still
# read some Indonesian themselves, and what they send for it is answered in
# English (an Indonesian word the server can't read gets its help hint). The
# new event fields (dir, sound, voice...) are optional, so the old clients
# only miss the new sounds.

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

import orbit_parse  # noqa: E402
from tests import orbit_parse_1_0, orbit_parse_1_4  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, join, make_game, orbit_lang, world  # noqa: E402,F401

UNKNOWN_COMMAND = "The station's computer doesn't know that command."

# (what a player types, the handler that must end up running)
PHRASEBOOK = [
    ("n", "move"), ("s", "move"), ("u", "move"), ("d", "move"), ("ne", "move"),
    ("north", "move"), ("southwest", "move"), ("northeast", "move"), ("north east", "move"),
    ("up", "move"), ("down", "move"), ("upstairs", "move"),
    ("go north", "go"), ("go east", "go"), ("go to the cantina", "go"),
    ("way to the cantina", "way"), ("route to the cantina", "way"),
    ("map", "map"), ("where am i", "where"),
    ("compass", "compass"), ("scan", "scan"),
    ("locate Sari", "locate"), ("where is Sari", "locate"),
    ("ride the Wombat", "board"), ("ride the shuttle", "board"),
    ("look north", "look"),
    ("daily", "daily"), ("daily bonus", "daily"), ("profile", "profile"), ("profile Sari", "profile"),
    ("rank", "rank"),
    ("plant tomato", "plant"), ("harvest", "harvest"), ("water", "water"),
    ("plots", "farm"), ("my farm", "farm"), ("mine", "mine"), ("collect", "collect"),
    ("list", "list"), ("list tools", "list"),
    ("buy headlamp", "buy"), ("sell all ore", "sell"),
    ("use headlamp", "use"), ("wear headlamp", "use"), ("place beacon", "use"),
    ("drink iced coffee", "use"), ("eat stuffed pancake", "use"),
    ("remove headlamp", "unequip"),
    ("examine headlamp", "look"), ("open capsule", "open"),
    ("ring bell", "ring"), ("light lantern", "lantern"), ("read plaque", "look"),
    ("invite Budi", "invite"), ("visit Budi", "visit"),
    ("add friend Budi", "friends"), ("friends", "friends"),
    ("my voice 3", "voice"),
    ("move my character", "transfer"),
    ("pat", "pet"), ("name pet Kiki", "pet"),
    ("economy", "admin"), ("grant Budi 5", "admin"), ("set price coffee 20", "admin"),
    ("revoke Budi", "admin"),
    # the mall, the casino, trading, achievements (stage 2)
    ("casino", "casino"), ("dice 50 high", "dice"), ("roll 20 low", "dice"), ("roll the dice 20 seven", "dice"),
    ("slots 20", "slots"), ("play slots 20", "slots"),
    ("blackjack 50", "blackjack"), ("play blackjack 50", "blackjack"),
    ("hit", "hit"), ("another card", "hit"), ("stand", "stand"), ("take a card", "take"),
    ("challenge Budi 50", "challenge"),
    ("lottery", "lottery"), ("buy 5 tickets", "buy"),
    ("offer Budi 3 iron for 200 credits", "offer"), ("trade Budi headlamp for 2 platinum", "offer"),
    ("accept", "accept"), ("accept offer", "accept"),
    ("decline", "decline"), ("cancel offer", "cancel_offer"),
    ("achievements", "achievements"), ("achievements Budi", "achievements"),
    ("leaderboard", "leaderboard"), ("leaderboard miners", "leaderboard"),
    ("sell headlamp", "sell"),
    # ships and the other worlds (stage 3)
    ("worlds", "worlds"),
    ("gate to Karmina", "gate"), ("enter the gate to the Moon", "gate"),
    ("ferry to Glasir", "ferry"), ("take the ferry to Glasir", "ferry"), ("ride the ferry to Glasir", "ferry"),
    ("embark", "embark"), ("go to my ship", "embark"), ("enter my ship", "embark"),
    ("disembark", "disembark"), ("leave the ship", "disembark"),
    ("set course for Karmina", "fly"),
    ("refuel", "refuel"), ("load 20 ice", "load"), ("unload all", "unload"),
    ("cargo", "cargo"), ("my ship", "cargo"), ("name ship Starfinch", "name_ship"),
    ("face moss sprite", "face"),
    ("gig", "gig"),
    # events (stage 4)
    ("events", "events"), ("join", "join"), ("open gift", "join"),
    ("listen", "listen"), ("catch the robot", "catch"), ("search", "search"),
    ("watch the comet", "watch"), ("host a party", "party"), ("fix drone", "work"),
    ("start event meteor shower", "admin"), ("stop event", "admin"), ("schedule event 30 Party", "admin"),
    # the hunt (stage 5)
    ("hunt", "hunt"), ("the lost chord", "hunt"), ("investigate", "investigate"),
    ("look for clues", "look"), ("solve 1234", "solve"), ("solve orbit", "solve"), ("my answer is 42", "solve"),
    ("hunt board", "hunt_board"), ("hunters", "hunt_board"),
    ("hunt status", "admin"), ("new season", "admin"), ("release hint 2", "admin"), ("hunt test", "admin"),
    # the arcade
    ("arcade", "arcade"), ("play echo", "play"), ("play quick draw", "play"),
    ("play meteor dodge", "play"), ("play star beat", "play"),
    ("stop game", "stop_game"), ("arcade scores", "high_scores"), ("high scores meteor", "leaderboard"),
    ("buy 10 tokens", "buy"),
    # crews
    ("crew", "crew"), ("crew create Starfinch", "crew_create"), ("create crew Starfinch", "crew_create"),
    ("crew invite Budi", "crew_invite"), ("invite Budi to the crew", "crew_invite"),
    ("crew say hi all", "crew_say"), ("tell crew hello", "whisper"),
    ("leave crew", "crew_leave"), ("crew kick Budi", "crew_kick"),
    ("make captain Budi", "crew_captain"), ("crew motto to the stars", "crew_motto"),
    ("crews", "crews"), ("disband crew Starfinch", "admin"),
    # duels
    ("duel Budi 50", "duel"), ("duel with Budi", "duel"),
    ("duels", "duels"), ("duels off", "duels"), ("duels on", "duels"), ("no duels", "duels"),
    ("stop duel Budi", "admin"),
    # the residents (1.2; Captain Mateo keeps the Dock, where these start)
    ("talk to Mateo", "talk"), ("talk with captain mateo", "talk"), ("chat with Mateo", "talk"),
    ("speak to Mateo", "talk"),
    ("ask Mateo about the ferry", "ask"), ("ask Captain Mateo about customs", "ask"),
    ("ask Mateo about recipes", "ask"),
    ("greet Mateo", "greet"), ("hello Mateo", "greet"), ("say hi to Mateo", "greet"),
    ("wave to Mateo", "emote"), ("hug Mateo", "emote"),
    ("look at Mateo", "look"), ("give Mateo a cracker", "give"),
    ("residents", "residents"),
    # pets (1.2)
    ("pet status", "pet"), ("my pets", "pet"), ("my pet", "pet"),
    ("feed pet", "pet"), ("feed Kiki a treat", "pet"), ("play with pet", "pet"),
    ("rest pet", "pet"), ("teach trick sit", "pet"), ("trick sit", "pet"),
    ("do trick sit", "pet"), ("rename pet Kiki", "pet"), ("rename Kiki to Momo", "pet"),
    # families (1.2)
    ("partner with Budi", "partner"), ("partner", "partner"),
    ("end partnership", "partner"), ("confirm end", "partner"),
    ("adopt", "adopt"), ("adopt a baby", "adopt"),
    ("family", "family"), ("my family", "family"), ("children", "family"),
    ("read a story to Lily", "child"), ("read a story", "child"), ("bring Lily", "child"),
    ("naming rite Lily", "naming"), ("naming ceremony Lily", "naming"),
    # weddings (1.2)
    ("propose to Budi", "wedding"), ("wedding", "wedding"), ("my wedding", "wedding"),
    ("book wedding pavilion grand neutral 14:00", "wedding"),
    ("book wedding pavilion simple starlight tomorrow 14:00", "wedding"),
    ("cancel wedding", "wedding"), ("wedding schedule", "wedding"), ("weddings", "wedding"),
    ("invite Budi to the wedding", "wedding"),
    ("rsvp yes", "wedding"), ("i'll come", "wedding"), ("rsvp no", "wedding"), ("can't come", "wedding"),
    ("invitations", "wedding"), ("throw flowers", "wedding"), ("vow I promise", "wedding"),
    ("join the lights", "wedding"), ("yes", "wedding"), ("i do", "wedding"), ("no", "wedding"),
    ("sign", "wedding"), ("read memory", "wedding"),
    # the duels' board, the tournament (1.2)
    ("leaderboard duels", "leaderboard"), ("start event tournament", "admin"),
    # the markets where you stand (server 1.3)
    ("prices", "prices"), ("prices coffee", "prices"), ("market", "prices"), ("check prices", "prices"),
    ("price list", "prices"),
    ("look at the signpost", "look"),
    ("way to the market", "way"), ("go to the market", "go"),
    ("buy 2 coffee", "buy"), ("sell 3 ice", "sell"),
    # the guide (server 1.3)
    ("guide me to the cantina", "guide"), ("guide me to the dock", "guide"), ("guide", "guide"),
    ("stop guide", "guide"), ("stop guiding", "guide"), ("cancel guidance", "guide"), ("guide off", "guide"),
]
# Only the newer clients: Orbit 1.0 read these as work, take or the mission board.
PHRASEBOOK_NOW = [
    ("fly to Karmina", "fly"), ("launch to Glasir", "fly"), ("board my ship", "embark"),
    ("take a gig", "gig"), ("transfer code", "transfer"), ("get off the ship", "disembark"),
]
# Only the current client (1.4 read "board" as the mission board, as 1.0 did).
PHRASEBOOK_15 = [("board the wombat", "board"), ("board the shuttle", "board")]

# What the older clients still read themselves in Indonesian, and send as plain
# text: the server doesn't read Indonesian any more, and answers with its hint.
INDONESIAN_TEXT = [
    "harian", "arah ke kantin", "pandu ke kantin", "berhenti pandu", "peta", "utara", "barat daya",
    "prestasi", "papan skor", "tanya Mateo tentang feri", "sapa Mateo", "panen",
]
# ...and what they turn into one of the server's commands: it's answered, in English.
# (what they type, the handler, the English key of the answer and its values)
INDONESIAN_STRUCTURED = [
    ("beli 2 kopi", "buy", None, {}),
    ("lihat utara", "look", "look_what", {"what": "utara"}),
    ("jual semua bijih", "sell", None, {}),
    ("siapa online", "who", None, {}),
    ("tas", "inventory", None, {}),
]
# Words that would mean an Indonesian line got through.
INDONESIAN_WORDS = {"kamu", "tidak", "ketik", "bantuan", "aku", "kredit", "sudah", "yang", "dengan", "untuk"}

READERS = {"1.0": orbit_parse_1_0.parse, "1.4": orbit_parse_1_4.parse, "now": orbit_parse.parse}


def _english(text):
    return orbit_lang.Texts().render("en", *text) if isinstance(text, tuple) else text


def _no_indonesian(text):
    words = {w.strip(".,!?:;\"'()").lower() for w in text.split()}
    return not (words & INDONESIAN_WORDS)


@pytest.fixture
def spy(make_game):
    game = make_game()
    calls = []

    def wrap(name, fn):
        def run(self, session, message):
            calls.append(name)
            return fn(self, session, message)
        return run

    game.COMMANDS = {name: wrap(name, fn) for name, fn in type(game).COMMANDS.items()}
    return game, calls


def test_the_phrasebook_is_english_and_reaches_every_handler_it_did():
    handlers = {handler for _text, handler in PHRASEBOOK}
    assert handlers >= {
        "move", "go", "way", "map", "where", "compass", "scan", "locate", "board", "look", "daily", "profile",
        "rank", "plant", "harvest", "water", "farm", "mine", "collect", "list", "buy", "sell", "use", "unequip",
        "open", "ring", "lantern", "invite", "visit", "friends", "voice", "transfer", "pet", "admin", "casino",
        "dice", "slots", "blackjack", "hit", "stand", "take", "challenge", "lottery", "offer", "accept",
        "decline", "cancel_offer", "achievements", "leaderboard", "worlds", "gate", "ferry", "embark",
        "disembark", "fly", "refuel", "load", "unload", "cargo", "name_ship", "face", "gig", "events", "join",
        "listen", "catch", "search", "watch", "party", "work", "hunt", "investigate", "solve", "hunt_board",
        "arcade", "play", "stop_game", "high_scores", "crew", "crew_create", "crew_invite", "crew_say",
        "whisper", "crew_leave", "crew_kick", "crew_captain", "crew_motto", "crews", "duel", "duels", "talk",
        "ask", "greet", "emote", "give", "residents", "partner", "adopt", "family", "child", "naming",
        "wedding", "prices", "guide"}
    assert len({text for text, _handler in PHRASEBOOK}) == len(PHRASEBOOK)       # no case twice


@pytest.mark.parametrize("client", ["1.0", "1.4", "now"])
@pytest.mark.parametrize("text, handler", PHRASEBOOK)
def test_every_new_command_reaches_the_server(spy, client, text, handler):
    game, calls = spy
    conn = join(game, "Tono", "engineer")
    parsed = READERS[client](text)
    assert parsed is not None and "local" not in parsed, parsed
    calls.clear()
    game.receive(conn, dict(parsed, t="cmd"))
    assert calls and calls[-1] == handler, (text, parsed, calls)
    assert conn.sent[-1]["t"] == "ev" and conn.sent[-1]["text"]
    assert "oops" not in conn.sent[-1]["text"] and conn.sent[-1]["text"] != UNKNOWN_COMMAND


@pytest.mark.parametrize("client", ["1.4", "now"])
@pytest.mark.parametrize("text, handler", PHRASEBOOK_NOW)
def test_the_newer_clients_reach_the_rest(spy, client, text, handler):
    game, calls = spy
    conn = join(game, "Tono", "engineer")
    parsed = READERS[client](text)
    calls.clear()
    game.receive(conn, dict(parsed, t="cmd"))
    assert calls and calls[-1] == handler, (text, parsed, calls)


@pytest.mark.parametrize("text, handler", PHRASEBOOK_15)
def test_the_current_client_reaches_the_shuttle(spy, text, handler):
    game, calls = spy
    conn = join(game, "Tono", "engineer")
    parsed = orbit_parse.parse(text)
    calls.clear()
    game.receive(conn, dict(parsed, t="cmd"))
    assert calls and calls[-1] == handler, (text, parsed, calls)


@pytest.mark.parametrize("client", ["1.0", "1.4"])
@pytest.mark.parametrize("text", INDONESIAN_TEXT)
def test_indonesian_from_an_old_client_gets_the_english_hint(spy, client, text):
    game, calls = spy
    conn = join(game, "Tono", "engineer")
    parsed = READERS[client](text)
    assert parsed == {"c": "text", "a": text}, parsed          # the old client sends it as it is
    calls.clear()
    game.receive(conn, dict(parsed, t="cmd"))
    assert calls == ["text"], calls
    hint = orbit_lang.Texts().render("en", "unknown_text", what=text)
    assert conn.last() == {"t": "ev", "k": "error", "text": hint}
    assert hint == f'I don\'t understand "{text}". Type help for the commands.'


@pytest.mark.parametrize("client", ["1.0", "1.4"])
@pytest.mark.parametrize("text, handler, key, values", INDONESIAN_STRUCTURED)
def test_what_an_old_client_builds_from_indonesian_is_answered_in_english(spy, client, text, handler, key,
                                                                          values):
    game, calls = spy
    conn = join(game, "Tono", "engineer")
    parsed = READERS[client](text)
    assert parsed.get("c") not in (None, "text"), parsed
    calls.clear()
    game.receive(conn, dict(parsed, t="cmd"))
    assert calls and calls[-1] == handler, (text, parsed, calls)
    answer = conn.last()
    assert answer["t"] == "ev" and answer["text"], answer
    assert answer["k"] != "error" or "oops" not in answer["text"]
    assert answer["text"] != UNKNOWN_COMMAND and "Type help for the commands" not in answer["text"]
    if key:
        assert answer["text"] == orbit_lang.Texts().render("en", key, **values)
    assert _no_indonesian(answer["text"]), answer["text"]


def test_an_old_clients_indonesian_hello_is_answered_in_english(make_game):
    """Orbit 1.0 to 1.4 say "lang": "id" when Hariku is in Indonesian: it's ignored."""
    game = make_game()
    conn = join(game, "Tono", "engineer", "id")
    assert conn.sent[0]["t"] == "welcome" and conn.sent[0]["name"] == "Tono"
    job = game.world.job_name("engineer")
    welcome = orbit_lang.Texts().render("en", "welcome_new", name="Tono", job=job)
    assert conn.sent[1]["text"].startswith(welcome)
    assert "Welcome to Orbit, Tono!" in conn.sent[1]["text"] and _no_indonesian(conn.sent[1]["text"])
    game.receive(conn, {"t": "cmd", "c": "look"})
    assert conn.last()["text"].startswith("Dock.")


def test_the_old_client_ignores_what_it_doesnt_know(make_game):
    """Everything the server sends is JSON with a kind and a text; the new
    fields are extra keys, which Orbit 1.0 simply doesn't read."""
    game = make_game()
    conn = join(game, "Tono", "engineer")
    for command in ({"c": "move", "d": "e"}, {"c": "look", "a": "north"}, {"c": "text", "a": "daily"},
                    {"c": "voice", "a": "2"}, {"c": "text", "a": "map"}, {"c": "say", "a": "hello"},
                    {"c": "text", "a": "leaderboard"}, {"c": "text", "a": "achievements"},
                    {"c": "text", "a": "harian"}):
        game.receive(conn, dict(command, t="cmd"))
    for message in conn.sent[1:]:
        assert message["t"] == "ev" and isinstance(message["k"], str) and isinstance(message["text"], str)
        assert set(message) <= {"t", "k", "text", "brief", "actor", "room", "amb", "codes", "sound", "floor", "acoustics", "via",
                                "dir", "voice", "preview", "ask", "transfer_code", "expires", "emote", "words",
                                "to", "reels", "outcome"}
    assert conn.last()["k"] == "error" and conn.last()["text"] == \
        'I don\'t understand "harian". Type help for the commands.'
