# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Pets (Orbit 1.2): the kinds and the shop, needs that fall gently in real
# time (never below zero, never harm), feeding, playing and resting, growing
# up through care, tricks learned in lessons and shown off, names, pets that
# follow and join in, sad and quiet pets cheered up, nudges, and pets that
# choose a player out on the worlds. The clock is fixed and the dice seeded.

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from tests.test_orbit_server import clock, cmd, join, make_game, walk, world  # noqa: E402,F401

HOUR = 3600


def text(game, conn, words):
    game.receive(conn, {"t": "cmd", "c": "text", "a": words})
    return [m for m in conn.sent if m.get("sound") != "achievement"][-1]


def adopt(game, conn, kind="fox_pet", name=None):
    char = conn.session.char
    thing = game.world.things[kind]
    game.store.add_companion(kind, name or thing["effects"]["pet"]["name"], [char["id"]],
                             stats=game.new_pet_stats())
    return game.pets_of(char)[-1]


def pet(game, conn, index=0):
    return game.pets_of(conn.session.char)[index]


def needs(game, conn, index=0):
    return {k: round(v) for k, v in game.pet_needs(pet(game, conn, index)).items()}


def test_the_pet_shop_has_six_kinds_and_their_food(make_game, world):
    game = make_game()
    kinds = [tid for tid in world.shops["pets"]["stock"] if world.things[tid]["type"] == "pet"]
    assert len(kinds) == 6 and {"pet_food", "pet_treat"} <= set(world.shops["pets"]["stock"])
    for tid in kinds:
        pet_kind = world.things[tid]["effects"]["pet"]
        assert pet_kind["sound"].startswith("pet_") and len(pet_kind["tricks"]) == 3
        assert {t["stage"] for t in pet_kind["tricks"].values()} == {1, 2}
        assert len(pet_kind["reactions"]["en"]) == len(pet_kind["reactions"]["id"])
    ani = join(game, "Ani")
    ani.session.char["credits"] = 5000
    walk(game, ani, "pet_shop")
    bought = cmd(game, ani, "buy", item="space fox")
    assert bought["text"].startswith("You adopt your new friend, space fox, for")
    assert pet(game, ani)["kind"] == "fox_pet" and pet(game, ani)["name"] == "Senja"
    assert cmd(game, ani, "pet", op="status")["text"] == \
        "Senja, your little space fox: well fed, playful and rested. Senja is happy."


def test_needs_fall_gently_and_never_below_nothing(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    adopt(game, ani)
    clock.advance(10 * HOUR)
    assert needs(game, ani) == {"food": 50, "fun": 40, "rest": 60}
    assert cmd(game, ani, "pet", op="status")["text"] == \
        "Senja, your little space fox: a little peckish, a bit bored and a little tired. Senja is content."
    clock.advance(4 * 24 * HOUR)
    assert needs(game, ani) == {"food": 0, "fun": 0, "rest": 0}
    assert game.pets_of(ani.session.char)                          # still there, always
    assert cmd(game, ani, "pet", op="status")["text"].endswith(
        "hungry, bored and lonely and sleepy. Senja is sad and quiet, and would love some care.")
    budi = join(game, "Budi")
    assert "Senja seems sad and quiet." in cmd(game, budi, "look", a="Ani")["text"]
    budi.clear()
    game.pet_reacts(ani.session, chance=1.0)
    assert not budi.events("emote")                                # sad pets are quiet
    played = cmd(game, ani, "pet", op="play")
    assert played["text"] == "Senja is too tired to run about, so you just cuddle, and Senja cheers up a little."
    assert needs(game, ani) == {"food": 0, "fun": 15, "rest": 0}
    clock.advance(301)
    cmd(game, ani, "pet", op="rest")
    assert cmd(game, ani, "pet", op="play")["text"] == "You play with Senja. Slowly at first, then with " \
                                                       "everything it has: Senja is cheered right up."


def test_feeding_with_pet_food_and_treats(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    adopt(game, ani)
    char = ani.session.char
    clock.advance(20 * HOUR)
    assert cmd(game, ani, "pet", op="feed")["text"].startswith("Kamu tidak punya pakan untuk Senja.")
    char["inventory"].update({"pet_food": 2, "pet_treat": 1})
    fed = cmd(game, ani, "pet", op="feed")
    assert fed["text"].startswith("Kamu memberi makan Senja: kantong pakan hewan. Senja melahap makanannya")
    assert fed["sound"] == "pet_fox" and needs(game, ani)["food"] == 55 and char["inventory"]["pet_food"] == 1
    clock.advance(2)
    game.receive(ani, {"t": "cmd", "c": "give", "to": "makan", "n": 1, "item": "Senja"})   # "beri makan Senja"
    assert needs(game, ani)["food"] == 90 and "pet_food" not in char["inventory"]
    clock.advance(2)
    assert cmd(game, ani, "pet", op="feed", a="camilan")["text"].startswith("Kamu memberi makan Senja: camilan")
    assert needs(game, ani)["food"] == 100 and needs(game, ani)["fun"] == 20
    clock.advance(2)
    char["inventory"]["pet_treat"] = 1
    assert cmd(game, ani, "pet", op="feed")["text"] == "Senja sudah kenyang, dan menolak makan lagi."
    assert char["inventory"]["pet_treat"] == 1
    clock.advance(2)
    game.receive(ani, {"t": "cmd", "c": "use", "item": "camilan hewan"})         # "pakai camilan hewan"
    assert ani.sent[-1]["text"] == "Senja sudah kenyang, dan menolak makan lagi."


def test_play_and_rest(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    adopt(game, ani)
    budi = join(game, "Budi")
    played = cmd(game, ani, "pet", op="play")
    assert played["text"].startswith("You play with Senja") and budi.texts("emote")[-1] == "Ani plays with Senja."
    assert needs(game, ani) == {"food": 80, "fun": 100, "rest": 72}
    assert cmd(game, ani, "pet", op="play")["text"].startswith("Senja needs a breather before playing again")
    assert cmd(game, ani, "pet", op="rest")["text"] == "Senja curls up for a nap, and wakes up refreshed."
    assert needs(game, ani)["rest"] == 100
    assert cmd(game, ani, "pet", op="rest")["text"] == "Senja isn't sleepy right now."
    clock.advance(45 * HOUR)
    assert cmd(game, ani, "pet", op="play")["text"].startswith("Senja is too tired to run about")


def test_growing_up_takes_days_and_care(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    comp = adopt(game, ani)
    char = ani.session.char
    char["inventory"]["pet_food"] = 40
    grew = []
    for day in range(9):
        clock.advance(24 * HOUR)
        for op in ("feed", "play", "rest"):
            ani.clear()
            cmd(game, ani, "pet", op=op)
            grew += [(day, m["text"]) for m in ani.sent if m.get("sound") == "levelup"]
    comp = pet(game, ani)
    assert grew == [(2, "Senja has grown: Senja is young now!"), (8, "Senja has grown: Senja is grown now!")]
    assert game.pet_stage(comp) == 2 and comp["stats"]["care"] >= 25
    assert cmd(game, ani, "pet", op="status")["text"].startswith("Senja, your grown space fox:")


def test_tricks_are_taught_in_lessons_and_shown_off(make_game, clock, monkeypatch):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    budi = join(game, "Budi")
    comp = adopt(game, ani)
    assert text(game, ani, "ajari trik duduk")["text"] == \
        "Senja masih terlalu kecil untuk belajar duduk: tunggu sampai remaja."
    comp["stats"]["stage"] = 1
    game.store.save_companion(comp)
    monkeypatch.setattr(game.rng, "random", lambda: 0.1)
    assert text(game, ani, "ajari trik duduk")["text"] == \
        "Pelajaran yang bagus: Senja mulai paham duduk (1 dari 3)."
    assert text(game, ani, "ajari trik duduk")["text"].startswith("Senja masih memikirkan pelajaran tadi.")
    clock.advance(301)
    text(game, ani, "ajari Senja duduk")
    clock.advance(301)
    learned = text(game, ani, "teach Senja sit")
    assert learned["text"] == "Senja sudah bisa duduk! Ucapkan trik duduk untuk menunjukkannya pada semua orang."
    assert learned["sound"] == "pet_trick"
    budi.clear()
    shown = text(game, ani, "trik duduk")
    assert shown["text"].startswith("Senja duduk, ekornya tersapu rapi") and shown["sound"] == "pet_trick"
    assert budi.texts("emote")[-1].startswith("Senja sits, tail swept neatly")
    assert text(game, ani, "trik lolong")["text"] == "Senja belum bisa trik itu."
    assert text(game, ani, "ajari trik lolong")["text"] == \
        "Senja masih terlalu kecil untuk belajar lolong: tunggu sampai sudah dewasa."
    assert "Trik: duduk." in text(game, ani, "status hewan")["text"]
    clock.advance(5 * 24 * HOUR)
    assert text(game, ani, "trik duduk")["text"] == "Senja sedang terlalu sedih untuk bermain trik. Perhatikan dulu?"
    assert text(game, ani, "ajari trik lompat")["text"].startswith("Senja sedang tidak ingin belajar.")


def test_names_and_several_pets(make_game):
    game = make_game()
    ani = join(game, "Ani")
    adopt(game, ani)
    adopt(game, ani, "jelly_pet")
    assert cmd(game, ani, "pet", op="name", a="Senja to Bara")["text"] == "Your pet's name is Bara now."
    assert cmd(game, ani, "pet", op="name", a="Lumi Nebula")["text"] == "Your pet's name is Nebula now."
    assert sorted(p["name"] for p in game.pets_of(ani.session.char)) == ["Bara", "Nebula"]
    status = cmd(game, ani, "pet", op="status")["text"]
    assert status.startswith("Bara, your little space fox:") and "Nebula, your little glow jellyfish:" in status
    assert cmd(game, ani, "pet", op="name", a="Bara to f*ck!")["text"] == "A pet's name needs 1 to 16 letters or digits."
    ani.session.char["inventory"]["pet_food"] = 1
    fed = cmd(game, ani, "pet", op="feed", a="Nebula")
    assert fed["sound"] == "pet_jelly"


def test_pets_follow_and_join_in(make_game, monkeypatch):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    adopt(game, ani, "cat_pet")
    monkeypatch.setattr(game.rng, "random", lambda: 0.0)
    budi.clear()
    cmd(game, ani, "emote", e="dance")
    assert budi.texts("emote")[-1] == "Oyen dances along with Ani."
    assert budi.sent[-1]["sound"] == "pet_cat"
    budi.clear()
    cmd(game, ani, "emote", e="hug", to="Oyen")
    assert budi.texts("emote")[0] == "Ani hugs Oyen." and "Oyen" in budi.texts("emote")[-1]
    budi.clear()
    cmd(game, budi, "emote", e="wave", to="Oyen")                   # another player's pet
    assert budi.texts("emote")[0] == "You wave at Oyen."
    assert "With them: Oyen the orange space cat." in cmd(game, budi, "look", a="Ani")["text"]


def test_a_pet_in_need_nudges_its_owner_once_an_hour(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    adopt(game, ani)
    clock.advance(22 * HOUR)
    ani.clear()
    game.tick()
    nudges = [m for m in ani.sent if m.get("sound") == "pet_fox"]
    assert [m["text"] for m in nudges] == ["Senja looks at you hopefully: it's bored. Play with it?"]
    clock.advance(600)
    game.tick()
    assert len([m for m in ani.sent if m.get("sound") == "pet_fox"]) == 1
    clock.advance(HOUR)
    game.tick()
    assert len([m for m in ani.sent if m.get("sound") == "pet_fox"]) == 2
    cmd(game, ani, "bye")
    back = join(game, "Ani")
    assert "Senja missed you, and would love some care." in back.sent[1]["text"]


def test_a_pet_may_choose_you_out_on_the_worlds(make_game, clock, monkeypatch):
    game = make_game()
    ani = join(game, "Ani")
    ani.session.char["location"] = "grove_wood"
    monkeypatch.setattr(game.rng, "randint", lambda a, b: 18)
    monkeypatch.setattr(game.rng, "random", lambda: 0.001)
    won = cmd(game, ani, "face", a="moss sprite")
    assert won["text"].endswith("And something small comes along with you: a space fox has chosen you! "
                                "Its name is Senja; change it with name pet.")
    assert [p["kind"] for p in game.pets_of(ani.session.char)] == ["fox_pet"]
    clock.advance(21)
    again = cmd(game, ani, "face", a="moss sprite")
    assert "chosen you" not in again["text"] and len(game.pets_of(ani.session.char)) == 1
