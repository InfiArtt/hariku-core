# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Families (Orbit 1.2): partnerships with the consent of both (asked,
# accepted, declined, run out), ended only with a confirmation and told
# kindly, admins ending one; adopting a baby alone or as partners (the other
# asked); a child's care, growing over real days from baby to toddler to
# child, its lines, its help and its voice; the naming rite at the temple;
# and how a family looks to others. The clock is fixed and the dice seeded.

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from tests.test_orbit_server import clock, cmd, join, make_game, world  # noqa: E402,F401

HOUR, DAY = 3600, 86400


def text(game, conn, words):
    game.receive(conn, {"t": "cmd", "c": "text", "a": words})
    return [m for m in conn.sent if m.get("sound") != "achievement"][-1]


def place(conn, room):
    conn.session.char["location"] = room


def ready(game, conn, credits=2000, level=3):
    char = conn.session.char
    char["credits"] = credits
    char["xp"] = game.xp_for_level(level)
    return char


def partners(game, clock, a, b):
    text(game, a, f"partner with {b.session.name}")
    assert cmd(game, b, "accept")["text"] == f"You and {a.session.name} are partners now."
    clock.advance(2)


def child_of(game, conn):
    return game.children_of(conn.session.char)[0]


# ------------------------------------------------------------
# Partnerships
# ------------------------------------------------------------

def test_both_must_say_yes(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi", lang="id")
    asked = text(game, ani, "partner with Budi")
    assert asked["text"] == "You ask Budi to be partners. Now it's up to them."
    offer = budi.sent[-1]
    assert offer["k"] == "offer" and offer["ask"] == "partner" and offer["actor"] == "Ani"
    assert offer["text"] == "Ani mengajakmu berpasangan. Ucapkan terima atau tolak, dalam 2 menit."
    assert text(game, budi, "tolak")["text"] == "Kamu dengan baik hati menolak Ani."
    assert ani.sent[-1]["text"] == "Budi kindly says no to being partners."
    assert game.partner_of(ani.session.char)[0] is None
    assert text(game, ani, "partner with Budi")["text"].startswith("Budi said no a little while ago.")
    clock.advance(601)
    text(game, ani, "partner with Budi")
    assert text(game, budi, "terima")["text"] == "Kamu dan Ani sekarang berpasangan."
    assert ani.sent[-1]["text"] == "You and Budi are partners now."
    p, other = game.partner_of(ani.session.char)
    assert p["status"] == "partners" and other == budi.session.char["id"]
    ceri = join(game, "Ceri")
    assert text(game, ceri, "partner with Ani")["text"] == "Ani already has a partner."
    assert "Partners with Budi." in cmd(game, ceri, "look", a="Ani")["text"]
    assert text(game, ani, "pasangan")["text"].startswith("Your partner is Budi, since 25-09-2026.")


def test_a_proposal_runs_out(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    text(game, ani, "ajak berpasangan Budi")
    clock.advance(121)
    game.tick()
    assert budi.sent[-1]["text"] == "You didn't answer Ani in time, so nothing changes."
    assert ani.sent[-1]["text"] == "Budi didn't answer in time."
    assert cmd(game, budi, "accept")["k"] == "error"


def test_ending_needs_a_confirmation_and_the_other_is_told_kindly(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    partners(game, clock, ani, budi)
    assert text(game, ani, "confirm end")["text"] == "Type end partnership first, then confirm end within a minute."
    sure = text(game, ani, "end partnership")
    assert sure["text"].startswith("Do you want to end your partnership with Budi? Budi will be told.")
    clock.advance(61)
    assert text(game, ani, "confirm end")["k"] == "error"                   # too late: nothing ends
    assert game.partner_of(ani.session.char)[0] is not None
    text(game, ani, "end partnership")
    cmd(game, budi, "bye")                                                  # Budi is away when it ends
    assert text(game, ani, "confirm end")["text"].startswith("Your partnership with Budi has ended.")
    assert game.partner_of(ani.session.char)[0] is None
    budi = join(game, "Budi")
    assert "Ani has ended your partnership." in budi.sent[1]["text"]
    assert text(game, ani, "partner with Budi")["text"].startswith("A partnership of Ani's ended not long ago.")
    clock.advance(DAY + 1)
    text(game, ani, "partner with Budi")
    assert cmd(game, budi, "accept")["text"] == "You and Ani are partners now."


def test_admins_can_end_a_partnership(make_game, clock):
    game = make_game()
    ani, budi, rafli = join(game, "Ani"), join(game, "Budi"), join(game, "Rafli")
    partners(game, clock, ani, budi)
    assert text(game, rafli, "akhiri kemitraan Ani")["text"] == "The partnership of Ani and Budi has ended."
    assert ani.sent[-1]["text"] == "The station's admins have ended your partnership with Budi."
    assert budi.sent[-1]["text"] == "The station's admins have ended your partnership with Ani."
    assert "end partnership" in {row["action"] for row in game.store.admin_log(5)}
    assert text(game, ani, "akhiri kemitraan Budi")["text"] == "You don't have a partner."   # players: only their own


# ------------------------------------------------------------
# Adopting
# ------------------------------------------------------------

def test_adopting_alone_at_the_family_desk(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    assert text(game, ani, "adopt")["text"] == "Adopting is done at the family desk, in the Medbay."
    place(ani, "medbay")
    assert text(game, ani, "adopt")["text"].startswith("The family desk asks 300 credits")
    ready(game, ani, level=2)
    assert text(game, ani, "adopt")["text"] == "The family desk asks that parents be level 3 or more."
    char = ready(game, ani)
    adopted = text(game, ani, "adopsi")
    assert adopted["text"].startswith("The nurse brings a baby wrapped in a star-patterned blanket") and \
        adopted["sound"] == "baby"
    assert char["credits"] == 1700
    child = child_of(game, ani)
    assert child["name"] == "" and 1 <= child["stats"]["voice"] <= 10 and game.child_stage(child) == 0
    assert text(game, ani, "adopt")["text"].startswith("Ani adopted not long ago.")
    assert "With them: their child your baby, a baby." not in cmd(game, join(game, "Budi"), "look", a="Ani")["text"]


def test_partners_adopt_together(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    partners(game, clock, ani, budi)
    ready(game, ani)
    place(ani, "medbay")
    cmd(game, budi, "bye")
    assert text(game, ani, "adopt")["text"].startswith("Adopting is something you and Budi decide together.")
    budi = join(game, "Budi")
    assert text(game, ani, "adopt")["text"] == "You ask Budi if the two of you should adopt a baby."
    assert budi.sent[-1]["ask"] == "adopt" and "300 credits, paid by Ani" in budi.sent[-1]["text"]
    cmd(game, budi, "decline")
    assert ani.sent[-1]["text"] == "Budi isn't ready to adopt right now."
    clock.advance(601)
    text(game, ani, "adopt")
    cmd(game, budi, "accept")
    assert ani.sent[-1]["text"].startswith("The nurse brings a baby") and "you and Budi are parents now" in \
        ani.sent[-1]["text"]
    child = child_of(game, ani)
    assert game.children_of(budi.session.char)[0]["id"] == child["id"]
    assert {role for _c, role in game.store.companion_owners(child["id"])} == {"owner", "parent"}


# ------------------------------------------------------------
# Children
# ------------------------------------------------------------

def adopted(game, clock, name="Ani"):
    conn = join(game, name)
    ready(game, conn)
    place(conn, "medbay")
    text(game, conn, "adopt")
    clock.advance(2)
    return conn


def test_a_baby_needs_care_and_is_never_harmed(make_game, clock):
    game = make_game()
    ani = adopted(game, clock)
    char = ani.session.char
    assert text(game, ani, "beri makan bayi")["text"] == \
        "You have no baby porridge for your baby. The Food Court has some."
    char["inventory"]["baby_porridge"] = 3
    clock.advance(20 * HOUR)
    fed = text(game, ani, "feed the baby")
    assert fed["text"].startswith("You feed your baby spoonful by spoonful: pot of baby porridge.")
    assert fed["sound"] == "baby"
    assert text(game, ani, "main dengan bayi")["text"] == "You play peekaboo with your baby, who laughs every single time."
    assert text(game, ani, "tidurkan bayi")["text"].startswith("You hum a lullaby")
    assert text(game, ani, "read a story to the baby")["text"].startswith("You tell your baby a story")
    clock.advance(10 * DAY)
    child = child_of(game, ani)
    assert game.child_needs(child) == {"food": 0.0, "fun": 0.0, "rest": 0.0}
    assert child_of(game, ani)["id"] == child["id"]                         # always still there
    assert text(game, ani, "family")["text"].endswith("your baby is quiet and a little sad, and asks for you.")


def test_growing_over_real_days_from_baby_to_child(make_game, clock):
    game = make_game()
    ani = adopted(game, clock)
    char = ani.session.char
    char["inventory"].update({"baby_porridge": 30, "kerupuk": 30})
    grew = []
    for day in range(6):
        clock.advance(DAY)
        for words in ("feed the baby", "play with the baby", "rest the baby", "read a story to the baby"):
            ani.clear()
            text(game, ani, words)
            grew += [(day, m["text"]) for m in ani.sent if m.get("sound") == "levelup"]
    assert [day for day, _t in grew] == [1, 4]
    assert grew[0][1].startswith("your baby is a toddler now, and has learned to say:")
    assert grew[1][1].startswith("your baby is a child now, full of questions.")
    assert game.child_stage(child_of(game, ani)) == 2


def test_the_naming_rite_at_the_temple(make_game, clock):
    game = make_game()
    ani = adopted(game, clock)
    budi = join(game, "Budi")
    assert text(game, ani, "upacara nama Mira")["text"].startswith(
        "A name is given in the naming rite at the temple of the Way of Starlight")
    place(ani, "star_hall")
    place(budi, "star_hall")
    assert text(game, ani, "naming rite X")["text"] == "A name needs 2 to 16 letters."
    budi.clear()
    text(game, ani, "naming rite mira")
    assert "Ibu Sekar smiles and beckons you under the dome. The naming rite for Mira begins." in ani.texts()
    assert child_of(game, ani)["name"] == "Mira"
    for _ in range(4):
        clock.advance(4)
        game.tick()
    lines = [m["text"] for m in budi.sent]
    assert lines[0] == "Ibu Sekar says: Welcome, little one. Tonight the dome learns a new name."
    assert any("lights a small lantern for the child" in line for line in lines)
    assert "Ibu Sekar says: Under these stars, you are Mira. Keep your word, stay curious, and look after one " \
           "another, Mira." in lines
    sounds = [m.get("sound") for m in budi.sent]
    assert sounds.count("lantern") == 1 and sounds.count("bell") == 1
    assert lines[-1] == "Mira has a name now, spoken under the stars."
    assert text(game, ani, "naming rite Bima")["text"] == "Your children all have their names already."
    assert "With them: their child Mira, a baby." in cmd(game, budi, "look", a="Ani")["text"]
    look = cmd(game, budi, "look", a="Mira")["text"]
    assert look.startswith("Mira, Ani's baby (a companion, not a player).")


def test_a_child_speaks_follows_and_helps(make_game, clock, monkeypatch):
    game = make_game()
    ani = adopted(game, clock)
    child = child_of(game, ani)
    child["name"] = "Mira"
    child["stats"].update(stage=2, needs={"food": 100, "fun": 100, "rest": 100, "at": clock()})
    game.store.save_companion(child)
    budi = join(game, "Budi")
    place(budi, "medbay")
    for _ in range(80):                                 # forty minutes
        clock.advance(30)
        game.tick()
    said = [m for m in budi.sent if m.get("actor") == "Mira" and m["k"] == "say"]
    assert said and said[0]["voice"] == child["stats"]["voice"]
    assert said[0]["text"].startswith("Mira says:")
    xp = ani.session.char["xp"]
    game.award_xp(ani.session, 100)
    assert ani.session.char["xp"] == xp + 105                                   # a happy child lends a hand
    monkeypatch.setattr(game, "_pick", lambda table: "pet_treat")
    helped = text(game, ani, "minta tolong Mira")
    assert helped["text"] == "Mira runs off to help, and comes back with 1 pet treat. You have a very useful child."
    assert ani.session.char["inventory"]["pet_treat"] == 1
    assert text(game, ani, "ask Mira for help")["text"] == "Mira has already helped today. Tomorrow!"
    talk = text(game, ani, "talk to Mira")
    assert talk["actor"] == "Mira" and talk["k"] == "say"
    ceri = join(game, "Ceri")
    place(ceri, "medbay")
    partners(game, clock, ani, ceri)
    game.store.add_companion_owner(child["id"], ceri.session.char["id"], "parent")
    assert text(game, ceri, "bawa Mira")["text"] == "Mira comes along with you now."
    assert "their child Mira" in cmd(game, budi, "look", a="Ceri")["text"]
    assert "their child Mira" not in cmd(game, budi, "look", a="Ani")["text"]
