# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Orbit's events (stage 4 of Orbit 1.1): the engine's pacing and cooldowns,
# requirements, taking part and rewards, the co-op drone, the weekly and
# seasonal schedule, persistence across a restart, and the admins' controls.

import datetime
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_events  # noqa: E402
import orbit_store  # noqa: E402
from tests.test_orbit_economy import _old_database  # noqa: E402
from tests.test_orbit_map import give, wear  # noqa: E402
from tests.test_orbit_server import UTC, clock, cmd, join, make_game, walk, world  # noqa: E402,F401


WEEKLY = orbit_events.EVENT_DEFAULTS["events_weekly"]


@pytest.fixture
def events_game(make_game):
    """A game with events on: random, seasonal and weekly ones only when a test asks."""
    def make(path=None, **config):
        settings = {"events_enabled": True, "events_random": False, "events_seasonal": False,
                    "events_weekly": []}
        settings.update(config)
        return make_game(path, **settings)
    return make


def char_of(game, name):
    return game.sessions[name.lower()].char


def news(conn):
    return [m for m in conn.sent if m.get("k") == "announce" and m.get("event")]


# ------------------------------------------------------------
# The events themselves
# ------------------------------------------------------------

def test_there_are_plenty_of_events_and_each_is_complete(world):
    events = world.data["events"]
    kinds = [e["kind"] for e in events.values()]
    assert kinds.count("random") >= 10 and kinds.count("weekly") >= 3 and kinds.count("seasonal") >= 3
    assert len([k for k in kinds if k in ("random", "weekly", "seasonal")]) >= 15
    assert events["station_birthday"]["date"] == "09-25" and events["new_year"]["date"] == "01-01"
    assert events["drone_boss"]["action"] == "boss" and events["drone_boss"]["min_online"] >= 2


# ------------------------------------------------------------
# Pacing
# ------------------------------------------------------------

def test_random_events_come_every_half_hour_to_hour_while_someone_is_on(events_game, clock, monkeypatch):
    game = events_game(events_random=True)
    game.tick()
    assert game.events_state["next"] == 0                          # nobody online: nothing
    ani = join(game, "Ani")
    game.tick()
    first = game.events_state["next"]
    assert 1800 <= first - clock.now <= 3600
    clock.now = first - 1
    game.tick()
    assert not game.active
    clock.now = first + 1
    game.tick()
    assert len(game.active) == 1
    row = next(iter(game.active.values()))
    started = news(ani)[-1]
    assert started["event"] == row["event"] and started["sound"]
    assert 1800 <= game.events_state["next"] - clock.now <= 3600
    # busier, sooner (down to half)
    assert game._gap(1) >= 1800 and game._gap(10) <= 3600 * 0.5 + 1


def test_never_two_big_ones_and_each_waits_for_its_cooldown(events_game, clock, monkeypatch):
    game = events_game(events_random=True)
    join(game, "Ani")
    join(game, "Budi")
    game.start_event("solar_storm")
    seen = {}
    monkeypatch.setattr(game, "_pick", lambda choices: seen.update(choices) or "cargo_spill")
    game.events_state["next"] = clock.now - 1
    game.events_state["last"]["comet_flyby"] = clock.now - 60     # just had one
    game.tick()
    assert seen and not any(game.events_def[e].get("big") for e in seen)
    assert "comet_flyby" not in seen and "solar_storm" not in seen
    assert "drone_boss" not in seen                                # big, while the storm is on
    assert game.active_of("cargo_spill")


def test_the_drone_needs_two_players_online(events_game, clock, monkeypatch):
    game = events_game(events_random=True)
    join(game, "Ani")
    seen = {}
    monkeypatch.setattr(game, "_pick", lambda choices: seen.update(choices) or next(iter(choices)))
    game.events_state["next"] = clock.now - 1
    game.tick()
    assert "drone_boss" not in seen
    join(game, "Budi")
    seen.clear()
    for eid in list(game.events_state["last"]):
        game.events_state["last"][eid] = 0
    for row in list(game.active.values()):
        game.end_event(row)
    game.events_state["next"] = clock.now - 1
    game.tick()
    assert "drone_boss" in seen


# ------------------------------------------------------------
# Taking part
# ------------------------------------------------------------

def test_a_meteor_shower_and_a_cargo_spill_are_collected(events_game, clock):
    game = events_game()
    ani = join(game, "Ani")
    game.start_event("meteor_shower")
    walk(game, ani, "cargo")
    assert cmd(game, ani, "collect")["text"] == "There's nothing to collect here."      # not where it falls
    walk(game, ani, "observation")
    for _ in range(5):
        found = cmd(game, ani, "collect")
        assert found["k"] == "paid" and found["text"].startswith("You catch "), found
        clock.advance(9)
    assert cmd(game, ani, "collect")["text"].startswith("You've gathered all you can from the Meteor shower")
    goods = sum(char_of(game, "Ani")["inventory"].get(g, 0) for g in ("meteorite", "iron", "nickel"))
    assert goods == 5 and char_of(game, "Ani")["stats"]["events"] == 1
    game.start_event("cargo_spill")
    walk(game, ani, "cargo")
    before = char_of(game, "Ani")["credits"]
    paid = cmd(game, ani, "collect")
    assert paid["text"].startswith("You haul a crate back") and 8 <= char_of(game, "Ani")["credits"] - before <= 20
    assert cmd(game, ani, "collect")["text"].startswith("Catch your breath")


def test_the_runaway_robot_is_heard_and_caught(events_game, clock):
    game = events_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    row = game.start_event("lost_robot")
    row["state"]["target"] = "cantina"
    walk(game, ani, "promenade")
    heard = cmd(game, ani, "listen")
    assert heard["text"] == "The sound comes from the west." and heard["dir"] == "w" and heard["sound"] == "robot_beep"
    assert cmd(game, ani, "catch")["text"] == "It isn't here. Listen again."
    walk(game, ani, "cantina")
    clock.advance(4)
    before = char_of(game, "Ani")["credits"]
    cmd(game, ani, "catch")
    assert char_of(game, "Ani")["credits"] == before + 120
    assert "Ani caught the runaway robot and wins 120 credits!" in [m["text"] for m in news(budi)]
    assert not game.active and game.store.events_with("won")[0]["state"]["winner"] == "Ani"
    assert cmd(game, ani, "catch")["text"] == "There's nothing to catch right now."


def test_a_stowaway_pays_security_double(events_game, clock):
    game = events_game()
    tono = join(game, "Tono", "security")
    row = game.start_event("stowaway")
    row["state"]["target"] = "cargo"
    walk(game, tono, "dock")
    wrong = cmd(game, tono, "search")
    assert wrong["text"].startswith("Nobody here, but you hear footsteps. The sound comes from the east.")
    walk(game, tono, "cargo")
    clock.advance(4)
    before = char_of(game, "Tono")["credits"]
    cmd(game, tono, "search")
    assert char_of(game, "Tono")["credits"] == before + 200


def test_a_comet_is_watched_once_and_a_storm_shelter_joined(events_game, clock):
    game = events_game()
    ani = join(game, "Ani")
    game.start_event("comet_flyby")
    assert cmd(game, ani, "watch")["text"] == "There's nothing special to watch right now."
    walk(game, ani, "observation")
    seen = cmd(game, ani, "watch")
    assert seen["k"] == "paid" and "20 credits" in seen["text"]
    assert cmd(game, ani, "watch")["text"].startswith("You've already watched it.")
    game.start_event("dust_storm")
    assert cmd(game, ani, "join")["text"].startswith("To join the Dust storm on Karmina, go in the Storm Shelter.")


def test_the_drone_grows_with_the_crowd_and_rewards_who_helped(events_game, clock, monkeypatch):
    game = events_game()
    conns = [join(game, name, "engineer") for name in ("Ani", "Budi", "Cici")]
    row = game.start_event("drone_boss")
    assert row["state"]["hp"] == 10 + 8 * 3
    for conn in conns[:2]:
        walk(game, conn, "dock")
    monkeypatch.setattr(game.rng, "randint", lambda a, b: 20)          # every tug lands, 2 points each
    hits = 0
    while game.active:
        for conn in conns[:2]:
            if not game.active:
                break
            before = len(conn.sent)
            cmd(game, conn, "work")                                     # "fix drone" arrives as work too
            assert conn.sent[before]["k"] == "paid", conn.sent[before:]
            hits += 1
        clock.advance(9)
    assert hits == 17
    points = dict(game.store.event_players(row["id"]))
    ani, budi = char_of(game, "Ani"), char_of(game, "Budi")
    assert points[ani["id"]] + points[budi["id"]] == 34
    won = [m["text"] for m in news(conns[2]) if m["text"].startswith("The drone powers down")]
    assert won and "Ani" in won[0] and "Budi" in won[0]
    assert ani["credits"] >= 100 + min(300, 40 + 15 * points[ani["id"]])
    # one that nobody finishes: a thank-you for each who tried
    monkeypatch.setattr(game.rng, "randint", lambda a, b: 1)
    clock.advance(20000)
    row = game.start_event("drone_boss")
    before = budi["credits"]
    cmd(game, conns[1], "work")
    assert game.store.event_points(row["id"], budi["id"]) == 1          # took part, no damage
    clock.advance(601)
    game.tick()
    assert budi["credits"] == before + 10


# ------------------------------------------------------------
# Effects
# ------------------------------------------------------------

def test_what_events_change_while_they_last(events_game, clock, monkeypatch):
    game = events_game()
    ani = join(game, "Ani", "engineer")
    char = char_of(game, "Ani")
    base_pay = game.pay(char, 100)
    game.start_event("solar_storm")
    assert game.pay(char, 100) == int(round(base_pay * 1.5))
    game.start_event("double_xp")
    before = char["xp"]
    game.award_xp(game.sessions["ani"], 10)
    assert char["xp"] == before + 20
    bar = game.price_of(char, "iced_coffee", "bar")
    game.start_event("happy_hour")
    assert game.price_of(char, "iced_coffee", "bar") == max(1, round(bar * 0.5))
    game.start_event("power_outage")
    assert game.in_the_dark(dict(char, location="promenade")) and not game.in_the_dark(dict(char, location="park"))
    give(game, "ani", "headlamp")
    wear(game, ani, "headlamp")
    assert not game.in_the_dark(dict(char, location="promenade"))
    monkeypatch.setattr(game.rng, "choice", lambda seq: "glasir" if "glasir" in seq else "ore")
    before = game.market.unit_price("ice", "pilot", "sell", world="glasir")
    game.start_event("market_boom")
    assert game.market.unit_price("ice", "pilot", "sell", world="glasir") > before * 1.2
    for row in list(game.active.values()):
        game.end_event(row)
    assert game.pay(char, 100) == base_pay and game.xp_factor() == 1.0


def test_the_lantern_festival_and_jackpot_night(events_game, clock, monkeypatch):
    game = events_game()
    ani = join(game, "Ani")
    char = char_of(game, "Ani")
    walk(game, ani, "star_hall")
    game.start_event("lantern_festival")
    before = char["credits"]
    cmd(game, ani, "lantern")
    assert char["credits"] == before + 25                          # free, and a gift once a day
    clock.advance(31)
    cmd(game, ani, "lantern")
    assert char["credits"] == before + 25
    walk(game, ani, "casino")
    char["credits"] = 1000
    game.start_event("jackpot_night")
    monkeypatch.setattr(game, "_pick", lambda table: "star")
    cmd(game, ani, "slots", n=10)
    assert char["credits"] == 1000 - 10 + 10 * 3 * 2


# ------------------------------------------------------------
# The schedule: weekly and seasonal
# ------------------------------------------------------------

def test_weekly_events_come_at_their_utc_time_and_are_listed(events_game, clock):
    game = events_game(events_weekly=WEEKLY)
    ani = join(game, "Ani")
    fair = datetime.datetime(2026, 9, 26, 14, 0, tzinfo=UTC).timestamp()        # Saturday
    listed = cmd(game, ani, "events")
    assert listed["text"].startswith("Nothing special is on right now. Coming: ")
    assert "Trading fair on the Mall Ring on Saturday 26-09 at 14:00 UTC" in listed["text"]
    assert {"event": "trading_fair", "name": "Trading fair on the Mall Ring", "at": fair} in listed["schedule"]
    char = char_of(game, "Ani")
    price = game.price_of(char, "headlamp", "gear")
    clock.now = fair + 5
    game.tick()
    assert game.active_of("trading_fair") and "The weekly trading fair has opened" in news(ani)[-1]["text"]
    assert game.price_of(char, "headlamp", "gear") == round(price * 0.8) or \
        abs(game.price_of(char, "headlamp", "gear") - price * 0.8) <= 1
    on = cmd(game, ani, "events")["text"]
    assert on.startswith("On now: Trading fair on the Mall Ring: every shop on the Mall Ring is a fifth off (2 hours left)")
    clock.now = fair + 7201
    game.tick()
    assert not game.active_of("trading_fair") and news(ani)[-1]["text"].startswith("The trading fair has closed")
    clock.now = fair + 7300
    game.tick()
    assert not game.active_of("trading_fair")                          # once a week
    assert game.weekly_start({"event": "trading_fair", "weekday": 5, "hour": 14}, clock.now) == fair + 7 * 86400


def test_the_stations_birthday_is_a_day_long_and_gives_a_gift(events_game, clock):
    game = events_game(events_seasonal=True)
    ani = join(game, "Ani")
    game.tick()                                                          # the 25th of September
    row = game.active_of("station_birthday")
    assert row and row["ends"] == datetime.datetime(2026, 9, 26, tzinfo=UTC).timestamp()
    # On now, so not "coming": what's listed as coming all starts later.
    listed = cmd(game, ani, "events")
    assert not any(e["event"] == "station_birthday" for e in listed["schedule"]), listed["schedule"]
    assert all(e["at"] > clock.now for e in listed["schedule"]), listed["schedule"]
    before = char_of(game, "Ani")["credits"]
    gift = cmd(game, ani, "join")
    assert gift["text"] == "You open your birthday gift: 100 credits and an iced coffee!"
    assert char_of(game, "Ani")["credits"] == before + 100 and char_of(game, "Ani")["inventory"]["iced_coffee"] == 1
    assert cmd(game, ani, "join")["text"].startswith("You've already joined")
    clock.now = row["ends"] + 1
    game.tick()
    assert not game.active_of("station_birthday")
    listed = cmd(game, ani, "events")
    assert any(e["event"] == "lantern_festival" for e in listed["schedule"]) is False    # far off (next April)


def test_events_carry_on_after_a_restart(tmp_path, events_game, clock):
    path = str(tmp_path / "orbit.db")
    game = events_game(path, events_seasonal=True, events_random=True)
    join(game, "Ani")
    row = game.start_event("happy_hour")
    game.tick()
    nxt = game.events_state["next"]
    game.shutdown()
    game.store.close()
    game = events_game(path, events_seasonal=True)
    assert game.active_of("happy_hour")["id"] == row["id"] and game.events_state["next"] == nxt
    assert game.active_of("station_birthday")                              # started before the restart
    clock.advance(1801)
    game.tick()
    assert not game.active_of("happy_hour") and game.store.events_with("done")[0]["event"] == "happy_hour"


# ------------------------------------------------------------
# Parties and the admins
# ------------------------------------------------------------

def test_a_party_in_your_cabin_is_open_to_everyone(events_game, clock):
    game = events_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    assert cmd(game, ani, "party")["text"].startswith("Throw a party in your own cabin")
    walk(game, ani, "cabin")
    cmd(game, ani, "text", a="adakan pesta")
    invite = news(budi)[-1]
    assert invite["text"].startswith("Ani is throwing a party in their cabin!") and invite["sound"] == "event_party"
    walk(game, budi, "cabins_hall")
    cmd(game, budi, "visit", to="Ani")                                     # no invitation needed
    assert char_of(game, "Budi")["location"] == "cabin"
    assert cmd(game, ani, "party")["text"].startswith("You threw a party not long ago.")
    assert "Ani's party" in cmd(game, budi, "events")["text"]
    clock.advance(1801)
    game.tick()
    assert news(budi)[-1]["text"] == "Ani's party is over. Thanks for coming!"


def test_admins_start_stop_and_schedule_events(events_game, clock):
    game = events_game()
    rafli = join(game, "Rafli")
    ani = join(game, "Ani")
    assert cmd(game, ani, "admin", op="event_start", a="meteor shower")["text"] == \
        "Only the station's admins can do that."
    assert not game.active_of("meteor_shower")
    started = cmd(game, rafli, "text", a="mulai acara hujan meteor")
    assert started["text"] == "You start the Meteor shower." and game.active_of("meteor_shower")
    assert cmd(game, rafli, "admin", op="event_start", a="meteor")["text"] == "The Meteor shower is already on."
    assert cmd(game, rafli, "admin", op="event_start", a="dragons")["text"].startswith("No such event.")
    stopped = cmd(game, rafli, "text", a="stop event meteor")
    assert stopped["text"] == "You stop the Meteor shower." and not game.active_of("meteor_shower")
    assert news(ani)[-1]["text"] == "The Meteor shower has been called off."
    scheduled = cmd(game, rafli, "text", a="schedule event 30 Race night at the track!")
    when = datetime.datetime.fromtimestamp(clock.now + 1800, UTC).strftime("%Y-%m-%d %H:%M")
    assert scheduled["text"] == f"Scheduled for {when} UTC: Race night at the track!"
    assert "Race night at the track!" in cmd(game, ani, "events")["text"]
    clock.advance(1801)
    game.tick()
    assert news(ani)[-1]["text"] == "Race night at the track!"
    cmd(game, rafli, "admin", op="event_schedule", a="2026-09-27 14:00 Grand meeting")
    assert game.store.events_with("scheduled")[0]["starts"] == datetime.datetime(2026, 9, 27, 14, tzinfo=UTC).timestamp()
    cmd(game, rafli, "admin", op="event_stop", a="grand meeting")
    assert not game.store.events_with("scheduled")
    assert cmd(game, rafli, "admin", op="event_schedule", a="whenever")["text"].startswith("Schedule an event")
    actions = [row["action"] for row in game.store.admin_log(20)]
    assert {"start event", "stop event", "schedule event"} <= set(actions)


def test_a_version_3_database_gets_the_events_tables(tmp_path, clock, monkeypatch):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    with monkeypatch.context() as m:
        m.setattr(orbit_store, "SCHEMA_VERSION", 3)
        m.setattr(orbit_store.Store, "_migrate_4", lambda self: None)
        orbit_store.Store(path, clock=clock, iterations=1000, durable=False).close()
    store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert store.version() == orbit_store.SCHEMA_VERSION and store.migrated_from == 3
    row = store.add_event("meteor_shower", 1.0, 2.0, {"a": 1}, "active")
    store.add_event_points(row["id"], 1, 2, 1.5)
    store.add_event_points(row["id"], 1, 3, 1.6)
    assert store.event_players(row["id"]) == [(1, 5)] and store.events_with("active")[0]["state"] == {"a": 1}
    store.close()
    backup = sqlite3.connect(path + f".before-v{orbit_store.SCHEMA_VERSION}.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 3
    backup.close()
