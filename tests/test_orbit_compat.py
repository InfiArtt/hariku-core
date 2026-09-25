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
# client sends for it (its command reader is frozen in orbit_parse_1_0.py;
# anything it doesn't know goes as plain text), and from what the current
# client sends. The new event fields (dir, sound, voice...) are optional, so
# the old client only misses the new sounds.

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

import orbit_parse  # noqa: E402
from tests import orbit_parse_1_0  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, join, make_game, world  # noqa: E402,F401

# (what a player types, their language, the handler that must end up running)
PHRASEBOOK = [
    ("s", "id", "move"), ("u", "id", "move"), ("utara", "id", "move"), ("barat daya", "id", "move"),
    ("naik", "id", "move"), ("turun", "id", "move"), ("tl", "id", "move"),
    ("n", "en", "move"), ("north", "en", "move"), ("southwest", "en", "move"), ("up", "en", "move"),
    ("pergi ke utara", "id", "go"), ("go north", "en", "go"), ("ke timur", "id", "go"),
    ("pergi ke kantin", "id", "go"), ("go to the cantina", "en", "go"),
    ("arah ke kantin", "id", "way"), ("way to the cantina", "en", "way"),
    ("peta", "id", "map"), ("map", "en", "map"), ("di mana aku", "id", "where"), ("where am i", "en", "where"),
    ("kompas", "id", "compass"), ("compass", "en", "compass"), ("pindai", "id", "scan"), ("scan", "en", "scan"),
    ("lacak Sari", "id", "locate"), ("locate Sari", "en", "locate"), ("where is Sari", "en", "locate"),
    ("naik kancil", "id", "board"), ("ride the Kancil", "en", "board"),
    ("lihat utara", "id", "look"), ("look north", "en", "look"),
    ("harian", "id", "daily"), ("daily", "en", "daily"), ("profil", "id", "profile"),
    ("profile Sari", "en", "profile"), ("peringkat", "id", "rank"), ("rank", "en", "rank"),
    ("tanam tomat", "id", "plant"), ("plant tomato", "en", "plant"), ("panen", "id", "harvest"),
    ("harvest", "en", "harvest"), ("siram", "id", "water"), ("water", "en", "water"),
    ("lahan", "id", "farm"), ("plots", "en", "farm"), ("tambang", "id", "mine"), ("mine", "en", "mine"),
    ("kumpulkan", "id", "collect"), ("collect", "en", "collect"),
    ("daftar", "id", "list"), ("list", "en", "list"), ("daftar alat", "id", "list"),
    ("beli senter", "id", "buy"), ("buy headlamp", "en", "buy"), ("jual semua bijih", "id", "sell"),
    ("sell all ore", "en", "sell"),
    ("pakai senter", "id", "use"), ("use headlamp", "en", "use"), ("wear headlamp", "en", "use"),
    ("pasang suar", "id", "use"), ("place beacon", "en", "use"), ("minum es kopi", "id", "use"),
    ("eat martabak", "en", "use"), ("lepas senter", "id", "unequip"), ("remove headlamp", "en", "unequip"),
    ("periksa senter", "id", "look"), ("examine headlamp", "en", "look"),
    ("buka kapsul", "id", "open"), ("open capsule", "en", "open"),
    ("bunyikan lonceng", "id", "ring"), ("ring bell", "en", "ring"),
    ("nyalakan lentera", "id", "lantern"), ("light lantern", "en", "lantern"),
    ("baca prasasti", "id", "look"), ("read plaque", "en", "look"),
    ("undang Budi", "id", "invite"), ("invite Budi", "en", "invite"),
    ("kunjungi Budi", "id", "visit"), ("visit Budi", "en", "visit"),
    ("tambah teman Budi", "id", "friends"), ("add friend Budi", "en", "friends"), ("teman", "id", "friends"),
    ("suaraku 3", "id", "voice"), ("my voice 3", "en", "voice"),
    ("kode pindah", "id", "transfer"), ("move my character", "en", "transfer"),
    ("elus", "id", "pet"), ("pat", "en", "pet"), ("namai Kiki", "id", "pet"),
    ("ekonomi", "id", "admin"), ("economy", "en", "admin"), ("grant Budi 5", "en", "admin"),
    ("atur harga kopi 20", "id", "admin"), ("cabut akses Budi", "id", "admin"),
    # the mall, the casino, trading, achievements (stage 2)
    ("kasino", "id", "casino"), ("casino", "en", "casino"), ("dadu 50 tinggi", "id", "dice"),
    ("dice 50 high", "en", "dice"), ("lempar dadu 20 tujuh", "id", "dice"), ("roll 20 low", "en", "dice"),
    ("slot 20", "id", "slots"), ("main slot 20", "id", "slots"), ("slots 20", "en", "slots"),
    ("blackjack 50", "id", "blackjack"), ("play blackjack 50", "en", "blackjack"),
    ("tambah kartu", "id", "hit"), ("kartu lagi", "id", "hit"), ("hit", "en", "hit"), ("cukup", "id", "stand"),
    ("stand", "en", "stand"), ("ambil kartu", "id", "take"),
    ("tantang Budi 50", "id", "challenge"), ("challenge Budi 50", "en", "challenge"),
    ("lotre", "id", "lottery"), ("lottery", "en", "lottery"), ("beli 5 tiket", "id", "buy"),
    ("buy 5 tickets", "en", "buy"),
    ("tawarkan Budi 3 besi untuk 200 kredit", "id", "offer"), ("offer Budi 3 iron for 200 credits", "en", "offer"),
    ("tukar Budi senter dengan 2 platina", "id", "offer"),
    ("terima", "id", "accept"), ("accept", "en", "accept"), ("terima tawaran", "id", "accept"),
    ("tolak", "id", "decline"), ("decline", "en", "decline"), ("batalkan tawaran", "id", "cancel_offer"),
    ("cancel offer", "en", "cancel_offer"),
    ("prestasi", "id", "achievements"), ("achievements", "en", "achievements"),
    ("prestasi Budi", "id", "achievements"),
    ("papan skor", "id", "leaderboard"), ("papan skor penambang", "id", "leaderboard"),
    ("leaderboard", "en", "leaderboard"), ("leaderboard miners", "en", "leaderboard"),
    ("jual senter", "id", "sell"), ("sell headlamp", "en", "sell"),
    # ships and the other worlds (stage 3)
    ("dunia", "id", "worlds"), ("worlds", "en", "worlds"),
    ("gerbang ke Karmina", "id", "gate"), ("gate to Karmina", "en", "gate"), ("masuk gerbang ke Bulan", "id", "gate"),
    ("feri ke Glasir", "id", "ferry"), ("naik feri ke Glasir", "id", "ferry"), ("ferry to Glasir", "en", "ferry"),
    ("take the ferry to Glasir", "en", "ferry"),
    ("naik kapal", "id", "embark"), ("masuk kapal", "id", "embark"), ("embark", "en", "embark"),
    ("turun kapal", "id", "disembark"), ("keluar dari kapal", "id", "disembark"), ("disembark", "en", "disembark"),
    ("set course for Karmina", "en", "fly"), ("berangkat ke Karmina", "id", "fly"),
    ("isi bahan bakar", "id", "refuel"), ("refuel", "en", "refuel"), ("muat 20 es", "id", "load"),
    ("load 20 ice", "en", "load"), ("bongkar semua", "id", "unload"), ("unload all", "en", "unload"),
    ("kargo", "id", "cargo"), ("my ship", "en", "cargo"), ("namai kapal Bintang", "id", "name_ship"),
    ("hadapi peri lumut", "id", "face"), ("face moss sprite", "en", "face"),
    ("gig", "id", "gig"), ("ambil gig", "id", "gig"),
    # events (stage 4)
    ("acara", "id", "events"), ("events", "en", "events"), ("ikut", "id", "join"), ("join", "en", "join"),
    ("buka hadiah", "id", "join"), ("dengar", "id", "listen"), ("listen", "en", "listen"),
    ("tangkap", "id", "catch"), ("catch the robot", "en", "catch"), ("geledah", "id", "search"),
    ("search", "en", "search"), ("tonton", "id", "watch"), ("watch the comet", "en", "watch"),
    ("adakan pesta", "id", "party"), ("host a party", "en", "party"), ("perbaiki drone", "id", "work"),
    ("fix drone", "en", "work"), ("mulai acara hujan meteor", "id", "admin"), ("stop event", "en", "admin"),
    ("jadwalkan acara 30 Pesta", "id", "admin"),
    # the hunt (stage 5)
    ("perburuan", "id", "hunt"), ("hunt", "en", "hunt"), ("nada yang hilang", "id", "hunt"),
    ("the lost chord", "en", "hunt"), ("selidiki", "id", "investigate"), ("investigate", "en", "investigate"),
    ("cari petunjuk", "id", "investigate"), ("look for clues", "en", "look"), ("pecahkan 1234", "id", "solve"),
    ("solve orbit", "en", "solve"), ("jawaban bintang", "id", "solve"), ("my answer is 42", "en", "solve"),
    ("papan pemburu", "id", "hunt_board"), ("hunt board", "en", "hunt_board"),
    ("status perburuan", "id", "admin"), ("hunt status", "en", "admin"), ("musim baru", "id", "admin"),
    ("umumkan petunjuk 2", "id", "admin"), ("release hint 2", "en", "admin"), ("uji perburuan", "id", "admin"),
    # the arcade
    ("arkade", "id", "arcade"), ("arcade", "en", "arcade"), ("main gema", "id", "play"),
    ("main adu cepat", "id", "play"), ("play meteor dodge", "en", "play"), ("play star beat", "en", "play"),
    ("berhenti main", "id", "stop_game"), ("stop game", "en", "stop_game"), ("skor arkade", "id", "high_scores"),
    ("arcade scores", "en", "high_scores"), ("high scores meteor", "en", "leaderboard"),
    ("beli 10 token", "id", "buy"), ("buy 5 tokens", "en", "buy"),
    # crews
    ("kru", "id", "crew"), ("crew", "en", "crew"), ("buat kru Bintang", "id", "crew_create"),
    ("crew create Bintang", "en", "crew_create"), ("kru undang Budi", "id", "crew_invite"),
    ("undang Budi ke kru", "id", "crew_invite"), ("invite Budi to the crew", "en", "crew_invite"),
    ("kru bilang halo", "id", "crew_say"), ("crew say hi all", "en", "crew_say"), ("tell crew hello", "en", "whisper"),
    ("keluar kru", "id", "crew_leave"), ("leave crew", "en", "crew_leave"), ("kru keluarkan Budi", "id", "crew_kick"),
    ("jadikan kapten Budi", "id", "crew_captain"), ("moto kru ke bintang", "id", "crew_motto"),
    ("papan kru", "id", "crews"), ("crews", "en", "crews"), ("bubarkan kru Bintang", "id", "admin"),
    # duels
    ("duel Budi 50", "en", "duel"), ("tantang duel Budi 50", "id", "duel"), ("duel dengan Budi", "id", "duel"),
    ("duels", "en", "duels"), ("duels off", "en", "duels"), ("matikan duel", "id", "duels"),
    ("nyalakan duel", "id", "duels"), ("hentikan duel Budi", "id", "admin"),
    # the residents (1.2; Kapten Bayu keeps the Dock, where these start)
    ("bicara dengan Bayu", "id", "talk"), ("bicara sama Kapten Bayu", "id", "talk"), ("ngobrol dengan Bayu", "id", "talk"),
    ("talk to Bayu", "en", "talk"), ("talk with captain bayu", "en", "talk"), ("chat with Bayu", "en", "talk"),
    ("tanya Bayu tentang feri", "id", "ask"), ("tanya Kapten Bayu soal pabean", "id", "ask"),
    ("ask Bayu about the ferry", "en", "ask"), ("ask Bayu about recipes", "en", "ask"),
    ("sapa Bayu", "id", "greet"), ("greet Bayu", "en", "greet"), ("halo Bayu", "id", "greet"),
    ("hello Bayu", "en", "greet"), ("say hi to Bayu", "en", "greet"),
    ("lambai ke Bayu", "id", "emote"), ("wave to Bayu", "en", "emote"), ("peluk Bayu", "id", "emote"),
    ("lihat Bayu", "id", "look"), ("look at Bayu", "en", "look"), ("beri Bayu 1 kerupuk", "id", "give"),
    ("give Bayu a cracker", "en", "give"),
    ("penduduk", "id", "residents"), ("residents", "en", "residents"),
    # pets (1.2)
    ("status hewan", "id", "pet"), ("pet status", "en", "pet"), ("hewanku", "id", "pet"), ("my pets", "en", "pet"),
    ("beri makan hewan", "id", "pet"), ("kasih makan Kiki", "id", "pet"), ("feed pet", "en", "pet"),
    ("feed Kiki a treat", "en", "pet"), ("main dengan hewan", "id", "pet"), ("play with pet", "en", "pet"),
    ("istirahatkan hewan", "id", "pet"), ("tidurkan Kiki", "id", "pet"), ("rest pet", "en", "pet"),
    ("ajari trik duduk", "id", "pet"), ("teach trick sit", "en", "pet"), ("trik duduk", "id", "pet"),
    ("do trick sit", "en", "pet"), ("rename pet Kiki", "en", "pet"), ("ganti nama Kiki jadi Momo", "id", "pet"),
    # families (1.2)
    ("ajak berpasangan Budi", "id", "partner"), ("partner with Budi", "en", "partner"), ("pasangan", "id", "partner"),
    ("partner", "en", "partner"), ("akhiri kemitraan", "id", "partner"), ("end partnership", "en", "partner"),
    ("konfirmasi akhiri", "id", "partner"), ("confirm end", "en", "partner"), ("adopsi", "id", "adopt"),
    ("adopt a baby", "en", "adopt"), ("keluarga", "id", "family"), ("my family", "en", "family"),
    ("anak", "id", "family"), ("children", "en", "family"), ("bacakan cerita untuk Mira", "id", "child"),
    ("read a story to Mira", "en", "child"), ("minta tolong Mira", "id", "child"), ("bawa Mira", "id", "child"),
    ("bring Mira", "en", "child"), ("upacara nama Mira", "id", "naming"), ("naming rite Mira", "en", "naming"),
    # weddings (1.2)
    ("lamar Budi", "id", "wedding"), ("propose to Budi", "en", "wedding"), ("pernikahan", "id", "wedding"),
    ("my wedding", "en", "wedding"), ("pesan pernikahan paviliun megah netral 14:00", "id", "wedding"),
    ("book wedding pavilion grand neutral 14:00", "en", "wedding"), ("batalkan pernikahan", "id", "wedding"),
    ("cancel wedding", "en", "wedding"), ("jadwal pernikahan", "id", "wedding"), ("wedding schedule", "en", "wedding"),
    ("undang Budi ke pernikahan", "id", "wedding"), ("invite Budi to the wedding", "en", "wedding"),
    ("hadir", "id", "wedding"), ("rsvp yes", "en", "wedding"), ("tidak hadir", "id", "wedding"),
    ("rsvp no", "en", "wedding"), ("undangan", "id", "wedding"), ("invitations", "en", "wedding"),
    ("lempar bunga", "id", "wedding"), ("throw flowers", "en", "wedding"), ("ikrar aku berjanji", "id", "wedding"),
    ("vow I promise", "en", "wedding"), ("satukan cahaya", "id", "wedding"), ("join the lights", "en", "wedding"),
    ("ya", "id", "wedding"), ("yes", "en", "wedding"), ("tidak", "id", "wedding"), ("tanda tangan", "id", "wedding"),
    ("sign", "en", "wedding"), ("baca kenangan", "id", "wedding"), ("read memory", "en", "wedding"),
    # the duels' board, the tournament (1.2)
    ("papan skor duel", "id", "leaderboard"), ("leaderboard duels", "en", "leaderboard"),
    ("mulai acara turnamen", "id", "admin"), ("start event tournament", "en", "admin"),
]
# Only the current client: Orbit 1.0 read these as work, take or the mission board.
PHRASEBOOK_NOW = [
    ("fly to Karmina", "en", "fly"), ("terbang ke Bulan", "id", "fly"), ("board my ship", "en", "embark"),
    ("take a gig", "en", "gig"),
]


def _reader(name):
    return {"1.0": orbit_parse_1_0.parse, "now": orbit_parse.parse}[name]


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


@pytest.mark.parametrize("client", ["1.0", "now"])
@pytest.mark.parametrize("text, lang, handler", PHRASEBOOK)
def test_every_new_command_reaches_the_server(spy, client, text, lang, handler):
    game, calls = spy
    conn = join(game, "Tono", "engineer", lang)
    parsed = _reader(client)(text)
    assert parsed is not None and "local" not in parsed, parsed
    calls.clear()
    game.receive(conn, dict(parsed, t="cmd"))
    assert calls and calls[-1] == handler, (text, parsed, calls)
    assert conn.sent[-1]["t"] == "ev" and conn.sent[-1]["text"]
    assert "oops" not in conn.sent[-1]["text"] and conn.sent[-1]["text"] != \
        "The station's computer doesn't know that command."


@pytest.mark.parametrize("text, lang, handler", PHRASEBOOK_NOW)
def test_the_current_client_reaches_the_rest(spy, text, lang, handler):
    game, calls = spy
    conn = join(game, "Tono", "engineer", lang)
    parsed = orbit_parse.parse(text)
    calls.clear()
    game.receive(conn, dict(parsed, t="cmd"))
    assert calls and calls[-1] == handler, (text, parsed, calls)


def test_the_old_client_ignores_what_it_doesnt_know(make_game):
    """Everything the server sends is JSON with a kind and a text; the new
    fields are extra keys, which Orbit 1.0 simply doesn't read."""
    game = make_game()
    conn = join(game, "Tono", "engineer")
    for command in ({"c": "move", "d": "e"}, {"c": "look", "a": "north"}, {"c": "text", "a": "harian"},
                    {"c": "voice", "a": "2"}, {"c": "text", "a": "peta"}, {"c": "say", "a": "halo"},
                    {"c": "text", "a": "papan skor"}, {"c": "text", "a": "prestasi"}):
        game.receive(conn, dict(command, t="cmd"))
    for message in conn.sent[1:]:
        assert message["t"] == "ev" and isinstance(message["k"], str) and isinstance(message["text"], str)
        assert set(message) <= {"t", "k", "text", "brief", "actor", "room", "amb", "codes", "sound", "floor", "acoustics", "via",
                                "dir", "voice", "preview", "ask", "transfer_code", "expires", "emote", "words",
                                "to", "reels", "outcome"}
