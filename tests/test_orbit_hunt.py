# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Orbit's hunt, the Lost Chord (stage 5 of Orbit 1.1): answers kept only as
# keyed hashes, the season files and their tool, clues by place, thing and
# hour, the wrong-answer wait, prizes by place, admins left out, test mode,
# hints, new seasons, the rival, the board, and the database's migration.
# Only the fake demo season (hunt.example.json) is used here: the real ones
# are never in the repository.

import copy
import datetime
import json
import os
import shutil
import sqlite3
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_hunt  # noqa: E402
import orbit_hunt_tool  # noqa: E402
import orbit_store  # noqa: E402
from tests.test_orbit_economy import _old_database  # noqa: E402
from tests.test_orbit_map import give, wear  # noqa: E402
from tests.test_orbit_server import UTC, clock, cmd, join, make_game, walk, world  # noqa: E402,F401

EXAMPLE = os.path.join(SERVER_DIR, "hunt.example.json")
SALT = "0f" * 32


@pytest.fixture
def hunt_game(make_game):
    """A game running the demo season (answers "orbit", then "1234")."""
    def make(path=None, **config):
        return make_game(path, hunt_path=config.pop("hunt_path", EXAMPLE), **config)
    return make


def example():
    with open(EXAMPLE, encoding="utf-8") as f:
        return json.load(f)


def authoring():
    """A tiny authoring file (plain answers) of a season that doesn't exist."""
    return {
        "season": "t1", "title": {"en": "A test", "id": "Sebuah uji"},
        "intro": {"en": "Test intro.", "id": "Pengantar uji."},
        "prize": {"first": 300, "others": [], "rest": 30},
        "stages": [{"id": "a", "riddle": {"en": "Q?", "id": "T?"}, "found": {"en": "Yes.", "id": "Ya."},
                    "accept": ["Kapsul Waktu", "time capsule"],
                    "clues": [{"room": "archive", "requires": {"worn": "headlamp"},
                               "text": {"en": "A drawer.", "id": "Sebuah laci."}}]}],
    }


def write_season(tmp_path, season, name="season.json"):
    path = tmp_path / name
    path.write_text(json.dumps(season), encoding="utf-8")
    return str(path)


def at_hour(clock, hour, minute=0, day=26):
    clock.now = datetime.datetime(2026, 9, day, hour, minute, tzinfo=UTC).timestamp()


def announced(conn, text):
    return [m for m in conn.sent if m.get("k") == "announce" and text in m.get("text", "")]


def solve(game, conn, answer, clock):
    clock.advance(3)
    return cmd(game, conn, "solve", a=answer)


def finish(game, conn, clock):
    assert solve(game, conn, "orbit", clock)["k"] == "paid"
    return solve(game, conn, "1234", clock)


# ------------------------------------------------------------
# Answers and season files
# ------------------------------------------------------------

def test_answers_are_compared_plainly_and_kept_only_as_keyed_hashes():
    assert orbit_hunt.normalize("Time-Capsule Room!") == "timecapsuleroom"
    assert orbit_hunt.normalize("  Café DÉJÀ vu ") == "cafedejavu"
    assert orbit_hunt.normalize("3 1 4") == orbit_hunt.normalize("314") == "314"
    one = orbit_hunt.answer_hash(SALT, "demo", "d1", "Orbit")
    assert one == orbit_hunt.answer_hash(SALT, "demo", "d1", " o-r-b-i-t ") and len(one) == 64
    assert one != orbit_hunt.answer_hash("1f" * 32, "demo", "d1", "orbit")      # another salt
    assert one != orbit_hunt.answer_hash(SALT, "demo2", "d1", "orbit")          # another season
    assert one != orbit_hunt.answer_hash(SALT, "demo", "d2", "orbit")           # another stage


def test_the_example_season_is_valid_and_has_no_plain_answers(world):
    hunt = orbit_hunt.load(EXAMPLE, world)
    assert hunt["season"] == "demo" and len(hunt["stages"]) == 2
    text = json.dumps(hunt)
    assert '"accept"' not in text
    first, second = hunt["stages"]
    assert orbit_hunt.answer_hash(hunt["salt"], "demo", first["id"], "orbit") in first["answers"]
    assert orbit_hunt.answer_hash(hunt["salt"], "demo", second["id"], "1 2 3 4") in second["answers"]


def test_a_season_with_plain_answers_or_bad_clues_is_refused(world):
    season = example()
    season["stages"][0]["accept"] = ["orbit"]
    assert any("plain answers" in p for p in orbit_hunt.validate(season, world))
    broken = example()
    clue = broken["stages"][1]["clues"][0]
    clue["room"] = "nowhere"
    clue["requires"] = {"thing": "unicorn", "hours": [25, 3]}
    clue["tones"] = [1, 5]
    broken["salt"] = "abc"
    broken["stages"][0]["answers"] = ["short"]
    problems = " | ".join(orbit_hunt.validate(broken, world))
    for part in ("unknown room 'nowhere'", "unknown thing 'unicorn'", "hours are", "tones are", "salt must",
                 "answers' hashes"):
        assert part in problems, problems
    assert orbit_hunt.validate({"season": 1}, world)


def test_building_hashes_the_answers_with_a_new_secret_salt(world):
    first = orbit_hunt.build(authoring(), world)
    second = orbit_hunt.build(authoring(), world)
    assert len(first["salt"]) == 64 and first["salt"] != second["salt"]
    text = json.dumps(first).lower()
    assert "accept" not in text and "kapsul waktu" not in text and "time capsule" not in text
    stage = first["stages"][0]
    assert orbit_hunt.answer_hash(first["salt"], "t1", "a", "KAPSUL waktu!") in stage["answers"]
    assert orbit_hunt.answer_hash(first["salt"], "t1", "a", "timecapsule") in stage["answers"]
    assert not orbit_hunt.validate(first, world)
    bad = authoring()
    bad["stages"][0]["accept"] = ["?!"]                       # nothing left once normalized
    with pytest.raises(orbit_hunt.HuntError):
        orbit_hunt.build(bad, world)


def test_the_tool_builds_checks_tries_and_says_what_went_wrong(tmp_path, capsys):
    source = write_season(tmp_path, authoring(), "t1.authoring.json")
    built = str(tmp_path / "t1.hunt.json")
    assert orbit_hunt_tool.main(["build", source, built]) == 0
    assert "1 stages" in capsys.readouterr().out
    assert orbit_hunt_tool.main(["check", built]) == 0
    assert orbit_hunt_tool.main(["try", built, "1", "Time Capsule"]) == 0
    assert orbit_hunt_tool.main(["try", built, "1", "time machine"]) == 1
    assert orbit_hunt_tool.main(["try", built, "9", "x"]) == 1
    assert orbit_hunt_tool.main(["check", source]) == 1                  # plain answers: not a server file
    assert "plain answers" in capsys.readouterr().err
    assert orbit_hunt_tool.main(["template"]) == 0
    template = json.loads(capsys.readouterr().out)
    assert template["stages"][0]["accept"]
    assert orbit_hunt_tool.main([]) == 2


# ------------------------------------------------------------
# Loading the season
# ------------------------------------------------------------

def test_without_a_season_there_is_no_hunt(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    assert game.hunt is None
    for c in ("hunt", "investigate", "hunt_board"):
        assert cmd(game, ani, c)["text"] == "No hunt is running right now."
    assert "invite a closer look" not in cmd(game, ani, "look")["text"]


def test_config_json_names_the_season_file_next_to_it(tmp_path):
    import orbit_server
    (tmp_path / "private").mkdir()
    shutil.copy(EXAMPLE, tmp_path / "private" / "season9.hunt.json")
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"database": "orbit.db", "hunt": "private/season9.hunt.json",
                                "game": {"events_enabled": False}}), encoding="utf-8")
    config = orbit_server.load_config(str(path))
    assert os.path.normpath(config["hunt"]) == str(tmp_path / "private" / "season9.hunt.json")
    assert orbit_server.load_config(None)["hunt"] == ""
    server = orbit_server.OrbitServer(config)
    try:
        assert server.game.hunt["season"] == "demo"
    finally:
        server.store.close()


def test_a_broken_season_file_is_refused_without_stopping_the_server(hunt_game, tmp_path, clock):
    season = example()
    season["stages"][0]["accept"] = ["orbit"]
    game = hunt_game(hunt_path=write_season(tmp_path, season))
    assert game.hunt is None
    game = hunt_game(hunt_path=str(tmp_path / "missing.json"))
    assert game.hunt is None


# ------------------------------------------------------------
# Playing
# ------------------------------------------------------------

def test_playing_the_demo_season_from_the_first_riddle_to_the_prize(hunt_game, clock):
    game = hunt_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    char = ani.session.char
    first = cmd(game, ani, "hunt")["text"]
    assert first.startswith("The Lost Chord (a demo).") and "two easy riddles" in first
    assert "Riddle 1 of 2: What is this game called?" in first

    # a clue where you are
    assert "Something here seems to invite a closer look." in cmd(game, ani, "look")["text"]
    clue = cmd(game, ani, "investigate")
    assert clue["k"] == "task" and clue["sound"] == "hunt_clue" and "the answer is orbit" in clue["text"]
    assert "codes" not in clue

    # wrong answers: a wait, twice as long each time
    wrong = solve(game, ani, "planet", clock)
    assert wrong["k"] == "failed" and wrong["text"].endswith("in 60 seconds.")
    assert solve(game, ani, "orbit", clock)["text"].startswith("Not yet: you can try again in")
    assert "You can try an answer again in" in cmd(game, ani, "hunt")["text"]
    clock.advance(60)
    assert solve(game, ani, "moon", clock)["text"].endswith("in 2 minutes.")
    clock.advance(120)
    assert solve(game, ani, "star", clock)["text"].endswith("in 4 minutes.")
    progress = game.store.hunt_progress("demo", char["id"])
    assert (progress["wrong"], progress["attempts"], progress["stage"]) == (3, 3, 0)
    assert progress["cooldown"] - clock.now == pytest.approx(240)
    assert not announced(budi, "Ani")

    # right: on to the next riddle, and everyone hears how far you've come
    clock.advance(240)
    right = solve(game, ani, "  ORBIT! ", clock)
    assert right["k"] == "paid" and right["sound"] == "hunt_found"
    assert right["text"].startswith("Right: the first demo note. Riddle 2 of 2: Take a scanner")
    assert announced(budi, "Ani has found note 1 of 2 of the Lost Chord!")
    progress = game.store.hunt_progress("demo", char["id"])
    assert (progress["stage"], progress["wrong"], progress["cooldown"]) == (1, 0, 0)

    # the next clue needs a scanner, in the Science Lab
    assert cmd(game, ani, "investigate")["text"] == "You look closely, but find nothing unusual."
    walk(game, ani, "science_lab")
    assert "invite a closer look" not in cmd(game, ani, "look")["text"]
    clock.advance(3)
    assert "can't quite make it out" in cmd(game, ani, "investigate")["text"]
    give(game, "ani", "scanner")
    assert "invite a closer look" in cmd(game, ani, "look")["text"]
    clock.advance(3)
    tones = cmd(game, ani, "investigate")
    assert tones["codes"] == [1, 2, 3, 4] and tones["text"] == "Your scanner hums four tones."

    # the end: the prize, the title, and the news
    credits = char["credits"]
    done = solve(game, ani, "1 2 3 4", clock)
    assert done["k"] == "paid" and done["sound"] == "jackpot"
    assert "You've found the whole chord! You win 1000 credits!" in done["text"]
    assert "Keeper of the Lost Chord" in done["text"]
    assert char["credits"] == credits + 1000 and game.owns(char, "title_chord_keeper")
    assert char["stats"]["hunts"] == 1
    assert announced(budi, "Ani is the first to find the whole Lost Chord and wins The Lost Chord (a demo)!")
    progress = game.store.hunt_progress("demo", char["id"])
    assert progress["finished"] and progress["place"] == 1 and progress["stage"] == 2
    assert "You've found the whole chord (you finished 1)" in cmd(game, ani, "hunt")["text"]
    assert "you finished 1" in solve(game, ani, "anything", clock)["text"]
    assert cmd(game, ani, "investigate")["text"] == "You look closely, but find nothing unusual."
    assert game.store.by_name("ani")["credits"] == char["credits"]


def test_the_hunt_speaks_indonesian_too(hunt_game, clock):
    game = hunt_game()
    sari = join(game, "Sari", lang="id")
    text = cmd(game, sari, "hunt")["text"]
    assert text.startswith("Nada yang Hilang (demo).") and "Teka-teki 1 dari 2: Apa nama permainan ini?" in text
    assert "jawabannya orbit" in cmd(game, sari, "investigate")["text"]
    wrong = solve(game, sari, "salah", clock)["text"]
    assert wrong.startswith("Bukan itu. Pikirkan lagi:") and wrong.endswith("dalam 60 detik.")


def test_look_for_clues_investigates(hunt_game, clock):
    game = hunt_game()
    ani = join(game, "Ani")
    assert "the answer is orbit" in cmd(game, ani, "look", a="for clues")["text"]


def test_later_finishers_win_less_and_only_the_first_gets_the_title(hunt_game, clock):
    game = hunt_game()
    players = [join(game, name) for name in ("Ani", "Budi", "Cici", "Dedi")]
    won = []
    for conn in players:
        char = conn.session.char
        before = char["credits"]
        finish(game, conn, clock)
        won.append((char["credits"] - before, game.owns(char, "title_chord_keeper")))
    assert won == [(1000, True), (500, False), (100, False), (100, False)]
    assert announced(players[0], "Budi has found the whole Lost Chord too, finishing 2.")
    assert game.hunt_state()["finishers"] == 4


def test_admins_dont_count_unless_the_config_says_so(hunt_game, clock):
    game = hunt_game()
    rafli, ani = join(game, "Rafli"), join(game, "Ani")
    char = rafli.session.char
    before = char["credits"]
    done = finish(game, rafli, clock)
    assert done["k"] == "paid" and "credits" not in done["text"]
    assert char["credits"] == before and not game.owns(char, "title_chord_keeper")
    assert not announced(ani, "Rafli")
    assert game.store.hunt_progress("demo", char["id"])["place"] == 0 and game.hunt_state()["finishers"] == 0
    assert "nobody yet" in cmd(game, ani, "hunt_board")["text"]
    # Ani still wins first place
    finish(game, ani, clock)
    assert game.owns(ani.session.char, "title_chord_keeper")

    competing = hunt_game(hunt_admins_compete=True)
    rafli = join(competing, "Rafli")
    before = rafli.session.char["credits"]
    finish(competing, rafli, clock)
    assert rafli.session.char["credits"] == before + 1000


def test_admins_can_play_the_season_in_test_mode_without_it_counting(hunt_game, clock):
    game = hunt_game(hunt_admins_compete=True)
    rafli, ani = join(game, "Rafli"), join(game, "Ani")
    char = rafli.session.char
    assert cmd(game, ani, "admin", op="hunt_test")["text"] == "Only the station's admins can do that."
    assert cmd(game, rafli, "admin", op="hunt_test")["text"].startswith("Hunt test mode on")
    assert "(Test mode: this doesn't count.)" in cmd(game, rafli, "hunt")["text"]
    before = char["credits"]
    finish(game, rafli, clock)
    assert char["credits"] == before and not announced(ani, "Rafli")
    assert game.store.hunt_progress("test:demo", char["id"])["finished"]
    assert game.store.hunt_progress("demo", char["id"])["stage"] == 0
    assert cmd(game, rafli, "admin", op="hunt_test")["text"] == "Hunt test mode off."
    assert "Riddle 1 of 2" in cmd(game, rafli, "hunt")["text"]
    assert "Rafli" not in cmd(game, ani, "hunt_board")["text"]


def test_hints_are_released_one_at_a_time_to_everyone(hunt_game, clock):
    game = hunt_game()
    rafli, ani = join(game, "Rafli"), join(game, "Ani")
    cmd(game, rafli, "admin", op="release_hint", n=1)
    assert announced(ani, "An official hint for riddle 1 of the hunt: It's the name of the game.")
    assert "Official hint: It's the name of the game." in cmd(game, ani, "hunt")["text"]
    assert cmd(game, rafli, "admin", op="release_hint", n=1)["text"] == "Riddle 1 has no more hints."
    assert cmd(game, rafli, "admin", op="release_hint")["text"].startswith("Which riddle?")
    assert cmd(game, rafli, "admin", op="release_hint", n=7)["text"].startswith("Which riddle?")
    # "umumkan petunjuk 2", as Orbit 1.0 sends it: the hint, not an announcement
    ani.clear()
    game.receive(rafli, {"t": "cmd", "c": "admin", "op": "announce", "a": "petunjuk 2"})
    assert [m["text"] for m in ani.sent] == ["An official hint for riddle 2 of the hunt: Low to high."]
    assert game.hunt_state()["hints"] == {"d1": 1, "d2": 1}
    assert {"hunt hint"} <= {row["action"] for row in game.store.admin_log(20)}


def test_a_new_season_starts_everyone_afresh_and_keeps_the_old_one(hunt_game, tmp_path, clock):
    game = hunt_game()
    rafli, ani = join(game, "Rafli"), join(game, "Ani")
    assert solve(game, ani, "orbit", clock)["k"] == "paid"
    assert cmd(game, rafli, "admin", op="new_season")["text"] == "Season demo reloaded."
    assert game.store.hunt_progress("demo", ani.session.char["id"])["stage"] == 1

    season = orbit_hunt.build(dict(authoring(), season="t2"), game.world)
    game.config["hunt_path"] = write_season(tmp_path, season)
    assert cmd(game, rafli, "admin", op="new_season")["text"] == "Season t2 begins."
    assert announced(ani, "A new season of the hunt has begun: A test! Type hunt to hear the first riddle.")
    assert game.hunt_state()["season"] == "t2" and game.hunt_state()["finishers"] == 0
    assert "Riddle 1 of 1: Q?" in cmd(game, ani, "hunt")["text"]
    assert game.store.hunt_progress("demo", ani.session.char["id"])["stage"] == 1

    # a broken file: said so, and the running season goes on
    game.config["hunt_path"] = str(tmp_path / "missing.json")
    assert cmd(game, rafli, "admin", op="new_season")["text"].startswith("The hunt's season file couldn't be read")
    assert game.hunt["season"] == "t2"


def test_clues_by_thing_worn_and_the_hour_around_midnight(hunt_game, tmp_path, clock):
    season = orbit_hunt.build(authoring(), hunt_game().world)
    season["stages"][0]["clues"].append({"room": "dock", "requires": {"hours": [22, 5]},
                                         "text": {"en": "At night.", "id": "Malam."}})
    game = hunt_game(hunt_path=write_season(tmp_path, season))
    ani = join(game, "Ani")
    for hour, seen in ((21, False), (22, True), (0, True), (4, True), (5, False), (12, False)):
        at_hour(clock, hour, 30, day=27 if hour < 21 else 26)
        assert bool(game.hunt_clues_here(ani.session)) == seen, hour
    walk(game, ani, "archive")
    give(game, "ani", "headlamp")
    assert not game.hunt_clues_here(ani.session) and game.hunt_clues_here(ani.session, visible_only=False)
    wear(game, ani, "headlamp")
    assert game.hunt_clues_here(ani.session)


def test_no_clue_in_the_dark(hunt_game, tmp_path, clock):
    dark = next(lid for lid, loc in hunt_game().world.locations.items()
                if loc.get("dark") and not loc.get("airless"))
    season = orbit_hunt.build(dict(authoring(), stages=[dict(authoring()["stages"][0], clues=[
        {"room": dark, "text": {"en": "In the dark.", "id": "Dalam gelap."}}])]), hunt_game().world)
    game = hunt_game(hunt_path=write_season(tmp_path, season))
    ani = join(game, "Ani")
    game._move_to(ani.session, dark, quiet=True)
    assert game.in_the_dark(ani.session.char)
    assert game.hunt_mark(ani.session) == ""
    assert cmd(game, ani, "investigate")["text"] == "It's too dark to see. A headlamp would help."


# ------------------------------------------------------------
# The rival, the board, the admins' view
# ------------------------------------------------------------

def test_the_rival_moves_on_every_so_often_but_never_finishes(hunt_game, clock):
    game = hunt_game()
    ani = join(game, "Ani")
    game.tick()
    assert game.hunt_state()["rival"] == 0
    clock.advance(24 * 3600 + 1)
    game.tick()
    news = announced(ani, "Word on the network: Meridian Grey has found note 1 of 2 of the Lost Chord. Hurry!")
    assert news and news[0]["sound"] == "hunt_rival"
    for _ in range(3):
        clock.advance(24 * 3600 + 1)
        game.tick()
    assert game.hunt_state()["rival"] == 1                        # one short of the end, always
    assert "The rival, Meridian Grey, has 1 of 2." in cmd(game, ani, "hunt_board")["text"]


def test_the_board_lists_the_finishers_then_the_furthest(hunt_game, clock):
    game = hunt_game()
    ani, budi, cici, rafli = (join(game, n) for n in ("Ani", "Budi", "Cici", "Rafli"))
    finish(game, budi, clock)
    solve(game, ani, "orbit", clock)
    solve(game, rafli, "orbit", clock)
    solve(game, cici, "wrong", clock)
    board = cmd(game, cici, "hunt_board")["text"]
    assert board.startswith("The Lost Chord (a demo): Budi, finished 1; Ani, 1 of 2.")
    assert "Cici" not in board and "Rafli" not in board


def test_admins_see_everyones_progress(hunt_game, clock):
    game = hunt_game()
    rafli, ani = join(game, "Rafli"), join(game, "Ani")
    solve(game, ani, "orbit", clock)
    solve(game, ani, "wrong", clock)
    status = cmd(game, rafli, "admin", op="hunt_status")["text"]
    assert status.startswith("Season demo: 1 players, 0 finished, the rival at 0.")
    assert "Ani at 1, 2 tries, 1 wrong in a row, waiting 60 seconds" in status
    assert cmd(game, ani, "admin", op="hunt_status")["text"] == "Only the station's admins can do that."


# ------------------------------------------------------------
# Keeping it
# ------------------------------------------------------------

def test_progress_and_the_rival_survive_a_restart(hunt_game, tmp_path, clock):
    path = str(tmp_path / "orbit.db")
    game = hunt_game(path)
    ani = join(game, "Ani")
    solve(game, ani, "orbit", clock)
    state = copy.deepcopy(game.hunt_state())
    char_id = ani.session.char["id"]
    game.store.close()
    clock.advance(3600)
    again = hunt_game(path)
    assert again.hunt_state() == state
    assert again.store.hunt_progress("demo", char_id)["stage"] == 1
    ani = join(again, "Ani")
    assert "Riddle 2 of 2" in cmd(again, ani, "hunt")["text"]


def test_a_version_4_database_gets_the_hunt_table(tmp_path, clock, monkeypatch):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    with monkeypatch.context() as m:
        m.setattr(orbit_store, "SCHEMA_VERSION", 4)
        m.setattr(orbit_store.Store, "_migrate_5", lambda self: None)
        orbit_store.Store(path, clock=clock, iterations=1000, durable=False).close()
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 4
    assert not db.execute("SELECT name FROM sqlite_master WHERE name = 'hunt_progress'").fetchall()
    db.close()
    store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert store.version() == orbit_store.SCHEMA_VERSION and store.migrated_from == 4
    quila = store.by_name("quilafly")
    assert quila["credits"] == 1234
    store.save_hunt_progress("1", quila["id"], {"stage": 2, "attempts": 5, "wrong": 1, "cooldown": 9.0,
                                                "finished": 0, "place": 0})
    assert store.hunt_progress("1", quila["id"])["stage"] == 2
    assert store.hunt_board("1") == [("Quilafly", 2, 0.0, 0)] and store.hunt_board("1", exclude={"quilafly"}) == []
    store.close()
    backup = sqlite3.connect(path + f".before-v{orbit_store.SCHEMA_VERSION}.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 4
    backup.close()


def test_the_real_seasons_never_go_into_the_repository():
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
        assert "servers/orbit/private/" in f.read().split()
    if shutil.which("git") is None or not os.path.isdir(os.path.join(ROOT, ".git")) and \
            not os.path.isfile(os.path.join(ROOT, ".git")):
        pytest.skip("not a git checkout")
    tracked = subprocess.run(["git", "ls-files", "servers/orbit"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    assert not [p for p in tracked if p.startswith("servers/orbit/private/") or p.endswith(".authoring.json")
                or p.endswith(".hunt.json")]
    ignored = subprocess.run(["git", "check-ignore", "-q", "servers/orbit/private/season1.hunt.json"], cwd=ROOT)
    assert ignored.returncode == 0
