# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Aruna's fallbacks (core 2.11, core.commands.add_fallback): what they are
# asked, when, what of their answers is kept, and how the command bar asks
# the user about it before anything runs. The bar runs on fakes (see
# tests/test_command_bar.py); nothing is shown, spoken or sent.

import threading
import time

import pytest

import core.commands as c
from tests.test_command_bar import cb, indonesian, make_bar, type_and_enter  # noqa: F401
from tests.test_commands import real_actions


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(c, "_fallbacks", [])
    monkeypatch.setattr(c, "_fallback", None)
    monkeypatch.setattr(c, "_intents", {})
    yield


def request_for(text="apakah nanti hujan", intents=(), deadline=None):
    return c.FallbackRequest(text, "typed", "id", c.commands(real_actions("id")), list(intents),
                             deadline=deadline)


def timer_intent(replies=None):
    got = []

    def handler(request):
        got.append(request)
        return replies(request) if callable(replies) else replies
    intent = c.add_intent("Timer and Alarm.timer", ["timer {text}"], handler, title="Timer")
    intent.got = got
    return intent


# ------------------------------------------------------------
# The API
# ------------------------------------------------------------

def test_the_flag_and_the_defaults():
    assert c.FALLBACKS is True
    assert 5 <= c.FALLBACK_TIMEOUT <= 8
    assert c.ASK_SCORE < c.FALLBACK_ASK_BELOW < c.RUN_SCORE


def test_adding_and_removing():
    def handler(request):
        return None
    assert c.has_fallback() is False
    assert c.add_fallback(handler, name="AI") is handler
    assert c.has_fallback() is True
    c.add_fallback(handler)                               # again: replaced, not twice
    assert len(c._fallbacks) == 1
    assert c.remove_fallback(handler) is True
    assert c.remove_fallback(handler) is False
    assert c.has_fallback() is False
    with pytest.raises(TypeError):
        c.add_fallback("not callable")
    with pytest.raises(TypeError):
        c.add_fallback(handler, is_enabled="yes")


def test_a_fallback_that_is_off_is_never_asked():
    asked = []
    c.add_fallback(lambda request: asked.append(request), is_enabled=lambda: False)
    assert c.has_fallback() is False
    assert c.ask_fallbacks(request_for()) is None
    assert asked == []


def test_a_broken_switch_counts_as_off():
    def boom():
        raise RuntimeError("settings unreadable")
    c.add_fallback(lambda request: None, is_enabled=boom)
    assert c.has_fallback() is False


@pytest.mark.parametrize("text, wanted", [
    ("apakah nanti hujan", True),              # not understood
    ("bla bla kucing terbang", True),          # a weak "Did you mean …?" (0.60)
    ("matikan suaranya", False),               # a fair "Did you mean …?" (0.70)
    ("gempa terbaru", False),                  # runs
])
def test_which_decisions_ask_the_fallbacks(text, wanted):
    from tests.test_commands import parse_reminder
    decision = c.decide(text, c.commands(real_actions("id")), parse=parse_reminder,
                        intent_candidates=[])
    assert c.wants_fallback(decision) is wanted, decision


def test_a_weak_guess_with_a_reminder_to_offer_keeps_it():
    guess = c.Command("A.a", "a")
    weak = c.Decision("confirm", "x", command=guess, match=c.Match([(0.56, guess)]),
                      alternative=object())
    assert c.wants_fallback(weak) is False


def test_the_request_s_helpers():
    intent = c.Intent("Timer and Alarm.timer", ["timer {text}"], lambda r: None, title="Timer")
    request = request_for(intents=[intent])
    assert request.command("Weather.speak_current_weather").id == "Weather.speak_current_weather"
    assert request.command("Nope.nothing") is None
    assert request.intent("Timer and Alarm.timer") is intent
    proposed = request.propose_command("Weather.speak_current_weather")
    assert proposed.kind == "confirm" and proposed.text == "apakah nanti hujan"
    assert request.propose_command("Nope.nothing") is None
    offered = request.propose_intent("Timer and Alarm.timer", "  teh  5 menit ")
    assert offered.kind == "intent" and offered.intents[0].text == "teh 5 menit"
    assert request.propose_intent("Timer and Alarm.timer", "  ") is None
    assert request.propose_intent("Nope.x", "teh") is None
    assert 0 < request.time_left() <= c.FALLBACK_TIMEOUT


def test_proposals_are_checked():
    intent = c.Intent("Timer and Alarm.timer", ["timer {text}"], lambda r: None, title="Timer")
    request = request_for(intents=[intent])
    stranger = c.Command("Evil.delete_everything", "Delete everything")
    assert c.proposal_of(c.Decision("confirm", "x", command=stranger), request) is None
    assert c.proposal_of(c.Decision("run", "x", command=stranger), request) is None
    # "run" is never run: it becomes a question, with the request's own Command.
    weather = c.Command("Weather.speak_current_weather", "fake name")
    asked = c.proposal_of(c.Decision("run", "x", command=weather), request)
    assert asked.kind == "confirm" and asked.command is request.command(weather.id)
    other = c.Intent("Evil.intent", ["evil {text}"], lambda r: None)
    assert c.proposal_of(c.Decision("intent", "x", intents=[c.IntentMatch(other, "t", 1, 0)]),
                         request) is None
    kept = c.proposal_of(c.Decision("intent", "x", intents=[c.IntentMatch(intent, "teh", 1, 0)]),
                         request)
    assert kept.intents[0].intent is intent and kept.intents[0].text == "teh"
    assert c.proposal_of(c.Decision("reminder", "x", result=None), request) is None
    assert c.proposal_of(c.Decision("unknown", "x"), request) is None
    assert c.proposal_of("Jawaban.", request).say == "Jawaban."
    assert c.proposal_of("  ", request) is None
    reply = c.Reply("Hi")
    assert c.proposal_of(reply, request) is reply
    assert c.proposal_of(42, request) is None
    assert c.proposal_of("Weather.speak_current_weather", request).say   # a string is only said


def test_the_first_proposal_wins_and_a_failing_one_is_skipped():
    order = []

    def boom(request):
        order.append("boom")
        raise RuntimeError("offline")

    def nothing(request):
        order.append("nothing")

    def weather(request):
        order.append("weather")
        return request.propose_command("Weather.speak_current_weather")

    def never(request):
        order.append("never")
    for handler in (boom, nothing, weather, never):
        c.add_fallback(handler)
    proposal = c.ask_fallbacks(request_for())
    assert proposal.kind == "confirm" and proposal.command.id == "Weather.speak_current_weather"
    assert order == ["boom", "nothing", "weather"]


def test_fallbacks_run_on_threads_of_their_own():
    names = []
    c.add_fallback(lambda request: names.append(threading.current_thread().name))
    c.ask_fallbacks(request_for())
    assert names == ["hariku-aruna-fallback"]


def test_a_slow_fallback_is_given_up_on_in_time():
    release = threading.Event()

    def slow(request):
        release.wait(5)
        return request.propose_command("Weather.speak_current_weather")
    c.add_fallback(slow)
    started = time.monotonic()
    assert c.ask_fallbacks(request_for(deadline=time.monotonic() + 0.3)) is None
    assert time.monotonic() - started < 2
    release.set()
    assert c.ask_fallbacks(request_for(deadline=time.monotonic())) is None   # no time at all


def test_the_core_2_7_form_still_works():
    c.set_fallback(lambda text, commands: "Weather.speak_current_weather")
    assert c.has_fallback() is True
    proposal = c.ask_fallbacks(request_for())
    assert proposal.command.id == "Weather.speak_current_weather"
    c.set_fallback(lambda text, commands: "Nope.nothing")
    assert c.ask_fallbacks(request_for()) is None
    c.set_fallback(None)
    assert c.has_fallback() is False


# ------------------------------------------------------------
# The command bar
# ------------------------------------------------------------

@pytest.fixture
def everything(cb, monkeypatch):
    commands = c.commands(real_actions("id"))
    monkeypatch.setattr(c, "commands", lambda actions=None: commands)
    return commands


def wait_until(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        time.sleep(0.01)
    return condition()


def test_a_proposed_command_is_asked_about_then_runs(cb, everything):
    asked = []

    def ai(request):
        asked.append(request)
        return request.propose_command("Weather.show_forecast")
    c.add_fallback(ai)
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    assert wait_until(lambda: bar.said)
    assert bar.said == ["Maksudnya: Buka prakiraan cuaca?"], bar.said
    assert bar.ran == [] and bar._pending.kind == "action"
    request = asked[0]
    assert request.text == "apakah nanti hujan" and request.source == "typed"
    assert request.language == "id" and request.guess is None
    assert any(x.id == "Weather.show_forecast" for x in request.commands)
    bar._on_enter(None)                                   # Enter again: yes
    assert bar.ran == ["Weather.show_forecast"]


def test_no_to_a_proposal(cb, everything):
    c.add_fallback(lambda request: request.propose_command("Weather.show_forecast"))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    assert wait_until(lambda: bar.said)
    bar.submit("tidak", source="voice")
    assert bar.ran == [] and bar.said[-1] == "Oke, batal." and not bar._closed
    bar.close()


def test_a_proposed_command_with_content(cb, everything):
    intent = timer_intent(lambda r: f"Timer {r.text} dimulai.")
    c.add_fallback(lambda request: request.propose_intent("Timer and Alarm.timer", "teh 5 menit"))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "seduh teh dong lima menitan")
    assert wait_until(lambda: bar.said)
    assert bar.said == ['Maksudnya: Timer, "teh 5 menit"?'] and bar._pending.kind == "proposed"
    assert intent.got == []                               # nothing done yet
    bar._on_enter(None)
    request = intent.got[0]
    assert (request.text, request.full_text, request.intent_id) == (
        "teh 5 menit", "seduh teh dong lima menitan", "Timer and Alarm.timer")
    assert bar.said[-1] == "Timer teh 5 menit dimulai."
    bar.close()


def test_a_proposed_intent_that_turns_it_down(cb, everything):
    timer_intent(None)
    c.add_fallback(lambda request: request.propose_intent("Timer and Alarm.timer", "x"))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    assert wait_until(lambda: bar.said)
    bar._on_enter(None)
    assert bar.said[-1] == "Hmm, itu belum masuk kamusku. Coba pakai kata lain?"
    bar.close()


def test_an_id_that_isn_t_registered_is_never_offered(cb, everything):
    stranger = c.Command("Evil.delete_everything", "Hapus semuanya")
    c.add_fallback(lambda request: c.Decision("confirm", request.text, command=stranger))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    assert wait_until(lambda: bar.said)
    assert bar.said == ["Hmm, itu belum masuk kamusku. Coba pakai kata lain?"]
    assert bar._pending is None and bar.ran == []
    bar.close()


def test_nothing_proposed_is_not_understood(cb, everything):
    c.add_fallback(lambda request: None)
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    assert wait_until(lambda: bar.said)
    assert bar.said == ["Hmm, itu belum masuk kamusku. Coba pakai kata lain?"]
    bar.close()


def test_a_weak_guess_is_asked_about_when_nothing_better_comes(cb, everything):
    asked = []
    c.add_fallback(lambda request: asked.append(request.guess))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "bla bla kucing terbang")
    assert wait_until(lambda: bar.said)
    assert asked[0].id == "Flight Radar.track_flight"      # the fallback knew the guess
    assert bar._pending.kind == "action" and bar._pending.command.id == "Flight Radar.track_flight"
    bar.close()


def test_a_better_proposal_replaces_a_weak_guess(cb, everything):
    c.add_fallback(lambda request: request.propose_command("Weather.show_forecast"))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "is it going to rain")
    assert wait_until(lambda: bar.said)
    assert bar._pending.command.id == "Weather.show_forecast"
    bar.close()


def test_clear_commands_never_wait_for_a_fallback(cb, everything):
    asked = []
    c.add_fallback(lambda request: asked.append(request))
    bar = make_bar(cb)
    type_and_enter(bar, "gempa terbaru")
    assert bar.ran == ["Earthquakes.speak_latest"] and asked == []


def test_a_fallback_that_is_off_changes_nothing(cb, everything):
    asked = []
    c.add_fallback(lambda request: asked.append(request), is_enabled=lambda: False)
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    # Answered at once, on this thread: no thread was started.
    assert bar.said == ["Hmm, itu belum masuk kamusku. Coba pakai kata lain?"] and asked == []
    bar.close()


def test_aruna_stays_responsive_while_the_fallback_thinks(cb, everything):
    release = threading.Event()
    finished = threading.Event()

    def slow(request):
        release.wait(5)
        finished.set()
        return request.propose_command("Weather.show_forecast")
    c.add_fallback(slow)
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    # Enter came back while the fallback is still thinking: it doesn't wait for it.
    assert not finished.is_set() and bar.said == []
    assert bar.txt_status.value == "Aruna sedang berpikir..." and bar._thinking is not None
    assert not bar._idle()
    release.set()
    assert wait_until(lambda: bar.said)
    assert bar._thinking is None and bar._pending.command.id == "Weather.show_forecast"
    bar.close()


def test_a_new_message_makes_the_late_answer_too_late(cb, everything):
    release = threading.Event()

    def slow(request):
        release.wait(5)
        return request.propose_command("Weather.show_forecast")
    c.add_fallback(slow)
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    type_and_enter(bar, "jam berapa")                    # something else meanwhile
    assert bar.ran == ["Hariku Core.speak_time"]
    release.set()
    time.sleep(0.3)
    assert bar._pending is None
    assert all("prakiraan" not in s for s in bar.said), bar.said
    bar.close()


def test_the_bar_gives_up_after_the_timeout(cb, everything, monkeypatch):
    monkeypatch.setattr(c, "FALLBACK_TIMEOUT", 0.3)
    release = threading.Event()
    c.add_fallback(lambda request: release.wait(5) and request.propose_command("Weather.show_forecast"))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    assert wait_until(lambda: bar.said, timeout=3)
    assert bar.said == ["Hmm, itu belum masuk kamusku. Coba pakai kata lain?"]
    release.set()
    time.sleep(0.2)
    assert bar._pending is None                          # the late answer changed nothing
    bar.close()


def test_closing_drops_the_answer(cb, everything):
    release = threading.Event()
    c.add_fallback(lambda request: release.wait(5) and request.propose_command("Weather.show_forecast"))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    bar.close()
    release.set()
    time.sleep(0.2)
    assert bar.said == []


def test_a_proposed_reminder_is_read_back(cb, everything):
    from tests.test_commands import parse_reminder
    c.add_fallback(lambda request: c.Decision(
        "reminder", request.text, result=parse_reminder("ingatkan aku jemput adek besok jam 16")))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "apakah nanti hujan")
    assert wait_until(lambda: bar.said)
    assert bar._pending.kind == "reminder" and "adek" in bar.said[0].lower()
    assert cb.saved == []
    bar._on_enter(None)
    assert len(cb.saved) == 1
    bar.close()


def test_a_spoken_sentence_says_so(cb, everything):
    sources = []
    c.add_fallback(lambda request: sources.append(request.source))
    bar = make_bar(cb, keep_open=True)
    bar.submit("apakah nanti hujan", source="voice")
    assert wait_until(lambda: bar.said)
    assert sources == ["voice"]
    bar.close()


def test_the_bar_never_runs_a_proposal_itself():
    import inspect
    import ui.command_bar as bar_module
    source = inspect.getsource(bar_module.CommandBar._fallbacks_answered)
    assert "_run_command" not in source and "run_action" not in source
