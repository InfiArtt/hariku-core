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
        assert pet_kind["reactions"]["en"] and set(pet_kind["reactions"]) == {"en"}
        assert all(set(trick["names"]) == {"en"} for trick in pet_kind["tricks"].values())
    names = {tid: world.things[tid]["effects"]["pet"]["name"] for tid in kinds}
    assert names == {"robot_pet": "Bip", "cat_pet": "Marmalade", "robocat_pet": "Tinker", "fox_pet": "Dusk",
                     "jelly_pet": "Lumi", "minidrone_pet": "Zip"}
    ani = join(game, "Ani")
    ani.session.char["credits"] = 5000
    walk(game, ani, "pet_shop")
    bought = cmd(game, ani, "buy", item="space fox")
    assert bought["text"].startswith("You adopt your new friend, space fox, for")
    assert pet(game, ani)["kind"] == "fox_pet" and pet(game, ani)["name"] == "Dusk"
    assert cmd(game, ani, "pet", op="status")["text"] == \
        "Dusk, your little space fox: well fed, playful and rested. Dusk is happy."


def test_needs_fall_gently_and_never_below_nothing(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    adopt(game, ani)
    clock.advance(10 * HOUR)
    assert needs(game, ani) == {"food": 50, "fun": 40, "rest": 60}
    assert cmd(game, ani, "pet", op="status")["text"] == \
        "Dusk, your little space fox: a little peckish, a bit bored and a little tired. Dusk is content."
    clock.advance(4 * 24 * HOUR)
    assert needs(game, ani) == {"food": 0, "fun": 0, "rest": 0}
    assert game.pets_of(ani.session.char)                          # still there, always
    assert cmd(game, ani, "pet", op="status")["text"].endswith(
        "hungry, bored and lonely and sleepy. Dusk is sad and quiet, and would love some care.")
    budi = join(game, "Budi")
    assert "Dusk seems sad and quiet." in cmd(game, budi, "look", a="Ani")["text"]
    budi.clear()
    game.pet_reacts(ani.session, chance=1.0)
    assert not budi.events("emote")                                # sad pets are quiet
    played = cmd(game, ani, "pet", op="play")
    assert played["text"] == "Dusk is too tired to run about, so you just cuddle, and Dusk cheers up a little."
    assert needs(game, ani) == {"food": 0, "fun": 15, "rest": 0}
    clock.advance(301)
    cmd(game, ani, "pet", op="rest")
    assert cmd(game, ani, "pet", op="play")["text"] == "You play with Dusk. Slowly at first, then with " \
                                                       "everything it has: Dusk is cheered right up."


def test_feeding_with_pet_food_and_treats(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", lang="id")                  # an older client asking for Indonesian: English
    adopt(game, ani)
    char = ani.session.char
    clock.advance(20 * HOUR)
    assert cmd(game, ani, "pet", op="feed")["text"].startswith("You have no pet food for Dusk.")
    char["inventory"].update({"pet_food": 2, "pet_treat": 1})
    fed = cmd(game, ani, "pet", op="feed")
    assert fed["text"].startswith("You feed Dusk: bag of pet food. Dusk gulps its food")
    assert fed["sound"] == "pet_fox" and needs(game, ani)["food"] == 55 and char["inventory"]["pet_food"] == 1
    clock.advance(2)
    game.receive(ani, {"t": "cmd", "c": "give", "to": "food", "n": 1, "item": "Dusk"})   # "give food Dusk"
    assert needs(game, ani)["food"] == 90 and "pet_food" not in char["inventory"]
    clock.advance(2)
    assert cmd(game, ani, "pet", op="feed", a="treat")["text"].startswith("You feed Dusk: pet treat")
    assert needs(game, ani)["food"] == 100 and needs(game, ani)["fun"] == 20
    clock.advance(2)
    char["inventory"]["pet_treat"] = 1
    assert cmd(game, ani, "pet", op="feed")["text"] == "Dusk is full, and turns its nose up at more food."
    assert char["inventory"]["pet_treat"] == 1
    clock.advance(2)
    game.receive(ani, {"t": "cmd", "c": "use", "item": "pet treat"})             # "use pet treat"
    assert ani.sent[-1]["text"] == "Dusk is full, and turns its nose up at more food."


def test_play_and_rest(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    adopt(game, ani)
    budi = join(game, "Budi")
    played = cmd(game, ani, "pet", op="play")
    assert played["text"].startswith("You play with Dusk") and budi.texts("emote")[-1] == "Ani plays with Dusk."
    assert needs(game, ani) == {"food": 80, "fun": 100, "rest": 72}
    assert cmd(game, ani, "pet", op="play")["text"].startswith("Dusk needs a breather before playing again")
    assert cmd(game, ani, "pet", op="rest")["text"] == "Dusk curls up for a nap, and wakes up refreshed."
    assert needs(game, ani)["rest"] == 100
    assert cmd(game, ani, "pet", op="rest")["text"] == "Dusk isn't sleepy right now."
    clock.advance(45 * HOUR)
    assert cmd(game, ani, "pet", op="play")["text"].startswith("Dusk is too tired to run about")


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
    assert grew == [(2, "Dusk has grown: Dusk is young now!"), (8, "Dusk has grown: Dusk is grown now!")]
    assert game.pet_stage(comp) == 2 and comp["stats"]["care"] >= 25
    assert cmd(game, ani, "pet", op="status")["text"].startswith("Dusk, your grown space fox:")


def test_tricks_are_taught_in_lessons_and_shown_off(make_game, clock, monkeypatch):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    budi = join(game, "Budi")
    comp = adopt(game, ani)
    assert text(game, ani, "teach trick sit")["text"] == "Dusk is too young to learn sit: wait until it's young."
    comp["stats"]["stage"] = 1
    game.store.save_companion(comp)
    monkeypatch.setattr(game.rng, "random", lambda: 0.1)
    assert text(game, ani, "teach trick sit")["text"] == "A good lesson: Dusk is getting the hang of sit (1 of 3)."
    assert text(game, ani, "teach trick sit")["text"].startswith("Dusk is still thinking about the last lesson.")
    clock.advance(301)
    text(game, ani, "teach Dusk sit")
    clock.advance(301)
    learned = text(game, ani, "teach Dusk sit")
    assert learned["text"] == "Dusk has learned sit! Say trick sit to show everyone."
    assert learned["sound"] == "pet_trick"
    budi.clear()
    shown = text(game, ani, "trick sit")
    assert shown["text"].startswith("Dusk sits, tail swept neatly") and shown["sound"] == "pet_trick"
    assert budi.texts("emote")[-1].startswith("Dusk sits, tail swept neatly")
    assert text(game, ani, "trick howl")["text"] == "Dusk doesn't know that trick."
    assert text(game, ani, "teach trick howl")["text"] == "Dusk is too young to learn howl: wait until it's grown."
    assert "Tricks: sit." in text(game, ani, "pet status")["text"]
    assert text(game, ani, "ajari trik duduk")["text"].startswith("I don't understand")      # English only
    clock.advance(5 * 24 * HOUR)
    assert text(game, ani, "trick sit")["text"] == "Dusk is too sad for tricks right now. Some care first?"
    assert text(game, ani, "teach trick jump")["text"].startswith("Dusk isn't in the mood for lessons.")


def test_names_and_several_pets(make_game):
    game = make_game()
    ani = join(game, "Ani")
    adopt(game, ani)
    adopt(game, ani, "jelly_pet")
    assert cmd(game, ani, "pet", op="name", a="Dusk to Ember")["text"] == "Your pet's name is Ember now."
    assert cmd(game, ani, "pet", op="name", a="Lumi Nebula")["text"] == "Your pet's name is Nebula now."
    assert sorted(p["name"] for p in game.pets_of(ani.session.char)) == ["Ember", "Nebula"]
    status = cmd(game, ani, "pet", op="status")["text"]
    assert status.startswith("Ember, your little space fox:") and "Nebula, your little glow jellyfish:" in status
    assert cmd(game, ani, "pet", op="name", a="Ember to f*ck!")["text"] == "A pet's name needs 1 to 16 letters or digits."
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
    assert budi.texts("emote")[-1] == "Marmalade dances along with Ani."
    assert budi.sent[-1]["sound"] == "pet_cat"
    budi.clear()
    cmd(game, ani, "emote", e="hug", to="Marmalade")
    assert budi.texts("emote")[0] == "Ani hugs Marmalade." and "Marmalade" in budi.texts("emote")[-1]
    budi.clear()
    cmd(game, budi, "emote", e="wave", to="Marmalade")                   # another player's pet
    assert budi.texts("emote")[0] == "You wave at Marmalade."
    assert "With them: Marmalade the orange space cat." in cmd(game, budi, "look", a="Ani")["text"]


def test_a_pet_in_need_nudges_its_owner_once_an_hour(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    adopt(game, ani)
    clock.advance(22 * HOUR)
    ani.clear()
    game.tick()
    nudges = [m for m in ani.sent if m.get("sound") == "pet_fox"]
    assert [m["text"] for m in nudges] == ["Dusk looks at you hopefully: it's bored. Play with it?"]
    clock.advance(600)
    game.tick()
    assert len([m for m in ani.sent if m.get("sound") == "pet_fox"]) == 1
    clock.advance(HOUR)
    game.tick()
    assert len([m for m in ani.sent if m.get("sound") == "pet_fox"]) == 2
    cmd(game, ani, "bye")
    back = join(game, "Ani")
    assert "Dusk missed you, and would love some care." in back.sent[1]["text"]


def test_a_pet_may_choose_you_out_on_the_worlds(make_game, clock, monkeypatch):
    game = make_game()
    ani = join(game, "Ani")
    ani.session.char["location"] = "grove_wood"
    monkeypatch.setattr(game.rng, "randint", lambda a, b: 18)
    monkeypatch.setattr(game.rng, "random", lambda: 0.001)
    won = cmd(game, ani, "face", a="moss sprite")
    assert won["text"].endswith("And something small comes along with you: a space fox has chosen you! "
                                "Its name is Dusk; change it with name pet.")
    assert [p["kind"] for p in game.pets_of(ani.session.char)] == ["fox_pet"]
    clock.advance(21)
    again = cmd(game, ani, "face", a="moss sprite")
    assert "chosen you" not in again["text"] and len(game.pets_of(ani.session.char)) == 1
