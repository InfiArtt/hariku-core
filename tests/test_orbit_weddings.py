# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Weddings (Orbit 1.2): rings, proposals with both players' yes, booking a
# hall with a tier, a ceremony and a time (parsed in both languages), clashes
# and limits, invitations and answers (online and while away), cancelling
# with refunds, the admins' cancel, the Starlight rite and the neutral
# ceremony step by step on a fixed clock (lanterns, the joined light, the
# silence, vows, the bell; vows, yes or no, signatures), a missed wedding,
# what comes after (news, titles, keepsakes, the memory, the reception's
# look and ambience) and the cooldown before marrying again.

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from tests.test_orbit_server import FakeConn, clock, cmd, join, make_game, secret_of, world  # noqa: E402,F401

UTC = datetime.timezone.utc
HOUR, DAY = 3600, 86400


def text(game, conn, words):
    game.receive(conn, {"t": "cmd", "c": "text", "a": words})
    return [m for m in conn.sent if m.get("sound") != "achievement"][-1]


def place(conn, room):
    conn.session.char["location"] = room


def join12(game, name, lang="en"):
    """A player on the 1.2 client."""
    conn = FakeConn(lang)
    game.hello(conn, {"t": "hello", "v": 1, "lang": lang, "name": name, "job": "pilot", "secret": secret_of(name),
                      "client": "Hariku Orbit 1.2"})
    return conn


def rich(conn, credits=20000):
    conn.session.char["credits"] = credits
    return conn.session.char


def engaged(game, clock, a, b, ring="ring_gold"):
    a.session.char["inventory"][ring] = 1
    place(a, b.session.char["location"])
    text(game, a, f"propose to {b.session.name}")
    assert cmd(game, b, "accept")["text"].startswith("You say yes")
    clock.advance(2)


def booked(game, clock, a, words="pavilion simple neutral 14:00"):
    rich(a)
    place(a, "jeweller")
    reply = text(game, a, f"book wedding {words}")
    assert reply["text"].startswith("Booked!"), reply
    clock.advance(2)
    return game.upcoming_wedding(a.session.char)


def tick_until(game, clock, until, step=2):
    while clock() < until:
        clock.advance(step)
        game.tick()


# ------------------------------------------------------------
# Rings and proposals
# ------------------------------------------------------------

def test_rings_at_the_jeweller(make_game):
    game = make_game()
    ani = join(game, "Ani")
    rich(ani)
    place(ani, "jeweller")
    budi = join(game, "Budi")
    place(budi, "jeweller")
    listing = cmd(game, ani, "list")["text"]
    assert "silver band" in listing and "gold band" in listing and "star-crystal ring" in listing
    bought = cmd(game, ani, "buy", item="gold band")
    assert bought["text"].startswith("You buy 1 gold band") and game.worn(ani.session.char)["hand"] == "ring_gold"
    assert "a gold band" in cmd(game, budi, "look", a="Ani")["text"]


def test_a_proposal_needs_a_ring_a_room_and_a_yes(make_game, clock):
    game = make_game()
    ani, budi, ceri = join(game, "Ani"), join(game, "Budi", lang="id"), join(game, "Ceri")
    assert text(game, ani, "propose to Budi")["text"] == "You'll want a ring first. Starglint Jewellers on the " \
                                                        "Mall Ring has some."
    ani.session.char["inventory"]["ring_silver"] = 1
    place(budi, "cantina")
    assert text(game, ani, "propose to Budi")["text"] == "Budi isn't here. A proposal is made face to face."
    place(budi, "dock")
    sent = text(game, ani, "propose to Budi")
    assert sent["text"] == "You offer Budi a silver band, and wait for the answer."
    assert budi.sent[-1]["ask"] == "ring" and budi.sent[-1]["sound"] == "ring"
    assert budi.sent[-1]["text"] == "Ani offers you a silver band and asks you to marry them. Say accept or decline."
    assert ceri.sent[-1]["text"] == "Ani offers Budi a ring. The room holds its breath."
    text(game, budi, "decline")
    assert ani.sent[-1]["text"] == "Budi gently says no, and gives the ring back."
    assert ani.session.char["inventory"]["ring_silver"] == 1
    assert text(game, ani, "propose to Budi")["text"].startswith("Budi said no a little while ago.")
    clock.advance(601)
    assert text(game, ani, "lamar Budi")["text"].startswith("I don't understand")      # English only
    text(game, ani, "propose to Budi")
    yes = text(game, budi, "accept")
    assert yes["text"].startswith("You say yes, and Ani slips the silver band on your finger.")
    assert ceri.sent[-1]["text"] == "Budi says yes to Ani, and the room bursts into cheers!"
    assert "ring_silver" not in ani.session.char["inventory"]
    assert game.worn(budi.session.char)["hand"] == "ring_silver"
    p, _o = game.partner_of(ani.session.char)
    assert p["status"] == "engaged"
    assert "Engaged to Ani." in cmd(game, ceri, "look", a="Budi")["text"]


def test_partners_become_engaged_and_others_are_refused(make_game, clock):
    game = make_game()
    ani, budi, ceri = join(game, "Ani"), join(game, "Budi"), join(game, "Ceri")
    text(game, ani, "partner with Budi")
    cmd(game, budi, "accept")
    ceri.session.char["inventory"]["ring_star"] = 1
    assert text(game, ceri, "propose to Ani")["text"] == "Ani already has a partner."
    engaged(game, clock, ani, budi, "ring_star")
    assert game.partner_of(ani.session.char)[0]["status"] == "engaged"
    ani.session.char["inventory"]["ring_silver"] = 1
    assert text(game, ani, "propose to Budi")["text"] == \
        "You and Budi are already engaged. Book your wedding at Starglint Jewellers."


# ------------------------------------------------------------
# Booking
# ------------------------------------------------------------

@pytest.mark.parametrize("words, venue, tier, style, when", [
    ("pavilion grand neutral 14:00", "pavilion", "grand", "neutral", (2026, 9, 25, 14, 0)),
    ("the jasmine pavilion big civil 14:00", "pavilion", "grand", "neutral", (2026, 9, 25, 14, 0)),
    ("star dome hall deluxe way of starlight tomorrow 09:30", "star_hall", "luxurious", "starlight",
     (2026, 9, 26, 9, 30)),
    ("the great hall simple starlight 2026-10-03 14:00", "grove_hall", "simple", "starlight", (2026, 10, 3, 14, 0)),
    ("star dome luxury starlight 11:00", "star_hall", "luxurious", "starlight", (2026, 9, 26, 11, 0)),
    ("castle hall basic registrar", "grove_hall", "simple", "neutral", None),
    ("pavilion 14:00", "pavilion", None, None, (2026, 9, 25, 14, 0)),
    # Indonesian isn't read any more
    ("paviliun megah netral 14:00", None, None, None, (2026, 9, 25, 14, 0)),
])
def test_bookings_are_read(make_game, words, venue, tier, style, when):
    game = make_game()                                        # 12:30 station time
    found, problem = game.parse_booking(words, game.now())
    assert problem is None
    expected = datetime.datetime(*when, tzinfo=UTC).timestamp() if when else None
    assert found == {"venue": venue, "tier": tier, "style": style, "starts": expected}


def test_booking_a_hall(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    rich(ani)
    assert text(game, ani, "book wedding pavilion simple neutral 14:00")["text"].startswith(
        "Weddings are booked at the wedding desk, at Starglint Jewellers.")
    place(ani, "jeweller")
    assert text(game, ani, "book wedding pavilion simple neutral 14:00")["text"].startswith(
        "Weddings are for engaged couples.")
    engaged(game, clock, ani, budi)
    place(ani, "jeweller")
    assert text(game, ani, "book wedding pavilion 14:00")["text"].startswith("Say book wedding, then the hall")
    assert text(game, ani, "book wedding pavilion simple neutral 12:35")["text"] == \
        "A wedding is booked at least 10 minutes and at most 14 days ahead."
    assert text(game, ani, "book wedding pavilion simple neutral 25:00")["text"].startswith(
        "That time doesn't look right.")
    before = ani.session.char["credits"]
    assert text(game, ani, "pesan pernikahan paviliun megah netral 14:00")["text"].startswith("I don't understand")
    booked_reply = text(game, ani, "book wedding the jasmine pavilion grand neutral 14:00")
    assert booked_reply["text"] == ("Booked! Your wedding is at the Jasmine Pavilion, Friday 25-09-2026 at 14:00 "
                                    "station time: grand, with a neutral ceremony. You paid 4000 credits and have "
                                    f"{before - 4000}. Invite your guests: invite, a name, to the wedding.")
    assert budi.sent[-1]["text"].startswith("Ani has booked your wedding: the Jasmine Pavilion")
    assert text(game, ani, "book wedding star dome simple starlight 16:00")["text"].startswith(
        "Your wedding is already booked.")
    assert text(game, budi, "wedding")["text"].startswith(
        "Your wedding with Ani: the Jasmine Pavilion, Friday 25-09-2026 at 14:00 station time (in 90 minutes)")
    ceri, dani = join(game, "Ceri"), join(game, "Dani", lang="id")
    engaged(game, clock, ceri, dani)
    rich(ceri)
    place(ceri, "jeweller")
    assert text(game, ceri, "book wedding pavilion simple neutral 14:30")["text"] == \
        "There's already a wedding at the Jasmine Pavilion then, Friday 25-09-2026 at 14:00 station time. " \
        "Choose another time or hall."
    assert text(game, ceri, "book wedding pavilion simple neutral 15:00")["text"].startswith("Booked!")
    assert text(game, dani, "wedding schedule")["text"] == \
        "Weddings to come: Ani and Budi, the Jasmine Pavilion, Friday 25-09-2026 at 14:00 station time; " \
        "Ceri and Dani, the Jasmine Pavilion, Friday 25-09-2026 at 15:00 station time."


def test_invitations_and_answers(make_game, clock):
    game = make_game()
    ani, budi, ceri = join(game, "Ani"), join(game, "Budi"), join(game, "Ceri", lang="id")
    engaged(game, clock, ani, budi)
    booked(game, clock, ani)
    invited = text(game, ani, "invite Ceri to the wedding")
    assert invited["text"] == "You invite Ceri to your wedding."
    assert ceri.sent[-1]["k"] == "offer" and ceri.sent[-1]["event"] == "wedding"
    assert ceri.sent[-1]["text"].startswith("You're invited to the wedding of Ani and Budi: the Jasmine Pavilion")
    assert text(game, ani, "invite Ceri to the wedding")["text"] == "Ceri is invited already."
    assert text(game, ani, "invite Budi to the wedding")["text"] == "The couple doesn't need an invitation."
    dani = join(game, "Dani")
    cmd(game, dani, "bye")
    text(game, budi, "invite Dani to our wedding")
    dani = join(game, "Dani")
    assert "You're invited to the wedding of Ani and Budi" in dani.sent[1]["text"]
    assert text(game, ceri, "rsvp yes")["text"].startswith("You'll be at the wedding of Ani and Budi")
    assert ani.sent[-1]["text"] == "Ceri is coming to your wedding!"
    text(game, dani, "rsvp no")
    assert budi.sent[-1]["text"] == "Dani can't come to your wedding, and sends their best wishes."
    assert text(game, ceri, "invitations")["text"].startswith(
        "Your invitations: Ani and Budi, the Jasmine Pavilion")
    assert "coming: Ceri" in text(game, ani, "wedding")["text"]
    for n in range(9):
        game.store.create(f"Guest{n}", f"guest{n}", f"hash{n}", "pilot", 100, "dock")
        clock.advance(2)
        text(game, ani, f"invite Guest{n} to the wedding")
    assert ani.sent[-1]["text"] == "Your tier has room for 10 guests, and they're all invited."


def test_cancelling_gives_money_back_when_early_enough(make_game, clock):
    game = make_game()
    ani, budi, ceri = join(game, "Ani"), join(game, "Budi"), join(game, "Ceri")
    engaged(game, clock, ani, budi)
    booked(game, clock, ani, "pavilion grand neutral 2026-09-27 14:00")
    text(game, ani, "invite Ceri to the wedding")
    credits = ani.session.char["credits"]
    assert text(game, budi, "cancel wedding")["text"] == "Your wedding is cancelled. 4000 credits come back."
    assert ani.session.char["credits"] == credits + 4000
    assert ceri.sent[-1]["text"] == "The wedding of Ani and Budi is cancelled."
    booked(game, clock, ani, "pavilion grand neutral 15:00")               # two and a half hours ahead
    credits = ani.session.char["credits"]
    text(game, ani, "cancel wedding")
    assert ani.session.char["credits"] == credits + 2000
    booked(game, clock, ani, "pavilion grand neutral 13:00")               # half an hour ahead
    credits = ani.session.char["credits"]
    assert text(game, ani, "cancel wedding")["text"] == "Your wedding is cancelled. 0 credits come back."
    assert ani.session.char["credits"] == credits
    booked(game, clock, ani, "star dome simple starlight 16:00")
    rafli = join(game, "Rafli")
    credits = ani.session.char["credits"]
    assert text(game, rafli, "cancel wedding Budi")["text"] == \
        "The wedding of Budi is cancelled; 1000 credits went back."
    assert ani.session.char["credits"] == credits + 1000
    assert "cancel wedding" in {row["action"] for row in game.store.admin_log(5)}


def test_ending_an_engagement_cancels_the_wedding(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    engaged(game, clock, ani, budi)
    booked(game, clock, ani, "pavilion simple neutral 2026-09-28 14:00")
    text(game, budi, "end partnership")
    assert "a wedding you booked is cancelled" in budi.sent[-1]["text"]
    credits = ani.session.char["credits"]
    text(game, budi, "confirm end")
    assert game.upcoming_wedding(ani.session.char) is None
    assert ani.session.char["credits"] == credits + 1000


# ------------------------------------------------------------
# The ceremonies
# ------------------------------------------------------------

def at(clock, hour, minute=0):
    clock.now = datetime.datetime(2026, 9, 25, hour, minute, tzinfo=UTC).timestamp()


def test_the_starlight_rite_step_by_step(make_game, clock):
    game = make_game()
    ani, budi = join12(game, "Ani"), join(game, "Budi")
    ceri, dani = join(game, "Ceri"), join(game, "Dani")
    engaged(game, clock, ani, budi)
    wedding = booked(game, clock, ani, "star dome luxurious starlight 14:00")
    text(game, ani, "invite Ceri to the wedding")
    text(game, ceri, "rsvp yes")
    tick_until(game, clock, datetime.datetime(2026, 9, 25, 13, 50, 1, tzinfo=UTC).timestamp(), step=60)
    assert "Your wedding begins in about ten minutes, at the Star Dome Hall. Make your way there!" in ani.texts()
    assert "The wedding of Ani and Budi begins in about ten minutes, at the Star Dome Hall." in ceri.texts()
    for conn in (ani, budi, ceri):
        place(conn, "star_hall")
    tick_until(game, clock, datetime.datetime(2026, 9, 25, 14, 0, 2, tzinfo=UTC).timestamp())
    wedding = game.store.wedding_by_id(wedding["id"])
    assert wedding["status"] == "ceremony"
    decor = [m for m in ceri.sent
             if m.get("text", "").startswith("The wedding of Ani and Budi begins. The hall is transformed")]
    assert decor and decor[0]["sound"] == "wedding_music"
    assert [m for m in ani.sent if m.get("amb") == "wedding"]                   # the 1.2 client's ambience
    assert not [m for m in ceri.sent if m.get("amb") == "wedding"]              # older clients keep theirs
    tick_until(game, clock, clock() + 14)
    assert "Amara says: Ani, Budi: each of you, light a lantern for your promise. Say light lantern." in ceri.texts()
    text(game, ani, "light lantern")
    assert ceri.texts()[-1] == "Ani lights a lantern, and a small warm light rises in the hall."
    text(game, budi, "light a lantern")
    tick_until(game, clock, clock() + 5)
    assert "Amara says: Now bring your two lights together, into one. Say join the lights." in ceri.texts()
    text(game, budi, "join the lights")
    assert ceri.sent[-1]["text"] == "Ani and Budi bring their lanterns together, and the two flames lean into one " \
                                    "bright light." and ceri.sent[-1]["sound"] == "lanterns_join"
    tick_until(game, clock, clock() + 6)
    assert "The hall falls silent. For a moment there is only the light, and the stars." in ceri.texts()
    tick_until(game, clock, clock() + 12)
    assert any("Speak your promises now" in t for t in ceri.texts())
    text(game, ani, "vow I will keep watch in turns, and never leave you behind.")
    assert ceri.sent[-1]["text"] == "Ani vows: I will keep watch in turns, and never leave you behind."
    assert ceri.sent[-1]["words"] == "I will keep watch in turns, and never leave you behind."
    text(game, ceri, "throw flowers")
    cmd(game, ceri, "emote", e="cheer")
    text(game, budi, "vow Aku akan selalu penasaran bersamamu.")         # the words are the player's own
    tick_until(game, clock, clock() + 20)
    bells = [m for m in ceri.sent if m.get("sound") == "bell"]
    assert [m["text"] for m in bells] == ["The star bell rings once.", "It rings a second time.",
                                          "And a third, its three tones drifting across the hall."]
    tick_until(game, clock, clock() + 6)
    assert "Amara says: Two lights, one path. Ani, Budi: you walk the Way together now. Congratulations!" in \
        ceri.texts()
    assert dani.sent[-1]["text"] == "Ani and Budi are married! The wedding was held at the Star Dome Hall. " \
                                    "Congratulations to them both!" and dani.sent[-1]["sound"] == "fireworks"
    assert "Beyond the windows, fireworks bloom in every colour for Ani and Budi." in ceri.texts()
    p, _o = game.partner_of(ani.session.char)
    assert p["status"] == "married"
    for conn in (ani, budi):
        inventory = conn.session.char["inventory"]
        assert inventory.get("title_starlit") == 1 and inventory.get("keepsake_lantern") == 1
    assert "Married to Budi." in cmd(game, ceri, "look", a="Ani")["text"]
    assert "decorated for the wedding of Ani and Budi" in cmd(game, ceri, "look")["text"]
    memory = text(game, ceri, "read memory")["text"]
    assert memory.startswith("The wedding of Ani and Budi, 25-09-2026 at 14:00 station time, at the Star Dome Hall: "
                             "luxurious, with the Starlight rite. Guests: Ceri.")
    assert "Ani vowed: I will keep watch in turns, and never leave you behind." in memory
    assert "Budi vowed: Aku akan selalu penasaran bersamamu." in memory
    assert memory.endswith("Petals were thrown 1 times, and the hall cheered 1 times.")
    assert text(game, dani, "read memory")["text"] == "You have no wedding to remember yet: yours, or one you went to."
    tick_until(game, clock, clock() + 46 * 60, step=60)
    assert ani.texts()[-1] == "The celebration winds down, and the hall grows quiet again."
    assert ani.sent[-1]["amb"] == "venue"


def test_the_neutral_ceremony_asks_each_for_a_yes(make_game, clock):
    game = make_game()
    ani, budi, ceri = join(game, "Ani"), join(game, "Budi"), join(game, "Ceri")
    engaged(game, clock, ani, budi)
    booked(game, clock, ani, "pavilion simple neutral 14:00")
    for conn in (ani, budi, ceri):
        place(conn, "pavilion")
    tick_until(game, clock, datetime.datetime(2026, 9, 25, 13, 55, tzinfo=UTC).timestamp(), step=30)
    assert game.npcs["safira"]["room"] == "pavilion"                      # the registrar walks over
    tick_until(game, clock, datetime.datetime(2026, 9, 25, 14, 0, 8, tzinfo=UTC).timestamp())
    assert "Celeste says: Welcome, everyone, to the wedding of Ani and Budi. Thank you for being here." in \
        ceri.texts()
    tick_until(game, clock, clock() + 8)
    text(game, ani, "vow Always.")
    text(game, budi, "vow Always, too.")
    tick_until(game, clock, clock() + 5)
    assert "Celeste says: Ani, do you choose to share your life with Budi? Say yes, or no." in ceri.texts()
    assert text(game, budi, "yes")["text"] == "That's for the couple, at the right moment of their ceremony."
    text(game, ani, "i do")
    assert "Ani says yes." in ceri.texts()
    assert "Celeste says: Budi, do you choose to share your life with Ani? Say yes, or no." in ceri.texts()
    text(game, budi, "yes")
    tick_until(game, clock, clock() + 5)
    assert "Celeste says: Then please sign the station's register, both of you. Say sign." in ceri.texts()
    text(game, ani, "sign")
    text(game, budi, "sign the register")
    tick_until(game, clock, clock() + 5)
    assert "Celeste says: With your own words and your own names, Ani and Budi, you are married. Congratulations!" \
        in ceri.texts()
    assert game.partner_of(ani.session.char)[0]["status"] == "married"
    assert ani.session.char["inventory"].get("title_wedded") == 1
    assert ani.session.char["inventory"].get("keepsake_star") == 1


def test_a_no_stops_the_ceremony_kindly(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    engaged(game, clock, ani, budi)
    booked(game, clock, ani, "pavilion grand neutral 14:00")
    for conn in (ani, budi):
        place(conn, "pavilion")
    credits = ani.session.char["credits"]
    tick_until(game, clock, datetime.datetime(2026, 9, 25, 14, 0, 20, tzinfo=UTC).timestamp())
    tick_until(game, clock, clock() + 200)                                  # no vows: they're kept quietly
    text(game, ani, "no")
    assert "The ceremony stops here, kindly, for today." in budi.texts()
    assert ani.session.char["credits"] == credits + 4000
    assert game.partner_of(ani.session.char)[0]["status"] == "engaged"


def test_a_wedding_nobody_comes_to_is_missed(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    engaged(game, clock, ani, budi)
    wedding = booked(game, clock, ani, "pavilion grand neutral 14:00")
    credits = ani.session.char["credits"]
    tick_until(game, clock, datetime.datetime(2026, 9, 25, 14, 21, tzinfo=UTC).timestamp(), step=30)
    assert game.store.wedding_by_id(wedding["id"])["status"] == "missed"
    assert ani.session.char["credits"] == credits + 2000
    assert ani.texts()[-1].startswith("The wedding waited, but you weren't both there.")


def test_marrying_again_waits_a_while(make_game, clock):
    game = make_game()
    ani, budi, ceri = join(game, "Ani"), join(game, "Budi"), join(game, "Ceri")
    engaged(game, clock, ani, budi)
    wedding = booked(game, clock, ani, "pavilion simple neutral 14:00")
    wedding["status"] = "done"
    game.store.save_wedding(wedding)
    text(game, ani, "end partnership")
    text(game, ani, "confirm end")
    clock.advance(DAY + 2)
    ceri.session.char["inventory"]["ring_gold"] = 1
    place(ceri, ani.session.char["location"])
    assert text(game, ceri, "propose to Ani")["text"].startswith("Ani was married not long ago.")
    clock.advance(7 * DAY)
    assert text(game, ceri, "propose to Ani")["text"].startswith("You offer Ani a gold band")
