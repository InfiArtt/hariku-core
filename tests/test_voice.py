# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for Hariku Voice (core/voice.py and the Windows voices in
# core/voice_sapi.py): the provider registry, announce() per kind, the fallback
# chain, braille, the queue, stopping on a key press, the MCI file player and
# the SAPI worker. Nothing here speaks or plays: providers, SAPI, MCI and the
# screen reader are all fakes, and every test uses a temporary data folder.

import ctypes
import ctypes.wintypes as wt
import logging
import os
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wait_until(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


class FakeProvider:
    """A provider whose speech ends by itself ("ok"), fails ("error"), raises
    ("raise") or lasts until stop() ("hang")."""

    def __init__(self, provider_id, behaviour="ok", voices=None, available=True):
        self.id = provider_id
        self.behaviour = behaviour
        self.voices = voices or []
        self.available = available
        self.calls = []
        self.stops = 0
        self.pending = None
        self.lock = threading.Lock()

    def speak(self, text, voice_id, rate, volume, on_done):
        with self.lock:
            self.calls.append((text, voice_id, rate, volume))
        if self.behaviour == "ok":
            threading.Timer(0.01, on_done, args=(None,)).start()
        elif self.behaviour == "error":
            threading.Timer(0.01, on_done, args=(RuntimeError("no voice here"),)).start()
        elif self.behaviour == "raise":
            raise RuntimeError("broken at once")
        elif self.behaviour == "hang":
            self.pending = on_done

    def stop(self):
        self.stops += 1
        pending, self.pending = self.pending, None
        if pending is not None:
            pending(None)

    def finish(self):
        pending, self.pending = self.pending, None
        if pending is not None:
            pending(None)

    def is_available(self):
        return self.available

    def list_voices(self):
        return self.voices

    def register(self, voice):
        voice.register_provider(self.id, self.id.title(), self.list_voices, self.speak,
                                self.stop, self.is_available, privacy_note=f"{self.id} note")
        return self

    def texts(self):
        with self.lock:
            return [c[0] for c in self.calls]


@pytest.fixture
def voice(tmp_data_dir, tmp_path, monkeypatch):
    import core.api
    import core.speech
    import core.voice as voice
    monkeypatch.setattr(core.api, "USER_DATA_DIR", str(tmp_path / "userdata"))
    saved = dict(voice._providers)
    monkeypatch.setattr(voice, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(voice, "STOP_GRACE_SECONDS", 0.5)
    # No input unless a test says so.
    inputs = {"tick": 1000, "held": False, "cursor": (10, 10)}
    monkeypatch.setattr(voice, "_last_input_tick", lambda: inputs["tick"])
    monkeypatch.setattr(voice, "_any_key_down", lambda: inputs["held"])
    monkeypatch.setattr(voice, "_cursor_pos", lambda: inputs["cursor"])
    voice.inputs = inputs
    # The screen reader, recorded.
    said = {"speak": [], "braille": [], "announced": []}
    monkeypatch.setattr(core.speech, "speak",
                        lambda text, interrupt=False: said["speak"].append((text, interrupt)))
    monkeypatch.setattr(core.speech, "braille",
                        lambda text, interrupt=False: said["braille"].append((text, interrupt)))
    monkeypatch.setattr(core.speech, "speak_announced",
                        lambda text, interrupt=False, braille=True:
                        said["announced"].append((text, interrupt, braille)))
    voice.said = said
    voice._logged.clear()
    # The built-in Windows provider is replaced by a fake for every test.
    voice.windows = FakeProvider("windows").register(voice)
    yield voice
    voice.stop()
    assert wait_until(lambda: not voice.is_speaking()), "the announcer did not stop"
    with voice._providers_lock:
        voice._providers.clear()
        voice._providers.update(saved)
    voice._logged.clear()


def enable(module, *kinds, **settings):
    values = {"kinds": {k: True for k in kinds}}
    values.update(settings)
    module.save_settings(values)


# ------------------------------------------------------------
# Registry
# ------------------------------------------------------------

class TestRegistry:
    def test_windows_is_built_in_and_first(self, voice):
        FakeProvider("edge").register(voice)
        ids = [p["id"] for p in voice.get_providers()]
        assert ids == ["windows", "edge"]
        edge = voice.get_providers()[1]
        assert edge["name"] == "Edge" and edge["privacy_note"] == "edge note"

    def test_real_windows_provider_is_registered(self):
        import core.voice
        import core.voice_sapi
        provider = core.voice._providers["windows"]
        assert provider.speak is core.voice_sapi.speak
        assert provider.list_voices is core.voice_sapi.list_voices
        assert provider.name in ("Windows voices", "voice_provider_windows")

    @pytest.mark.parametrize("bad_id", ["", "Edge", "edge voices", "x" * 33, None, "a/b"])
    def test_bad_ids_are_refused(self, voice, bad_id):
        with pytest.raises(ValueError):
            voice.register_provider(bad_id, "X", list, lambda *a: None, lambda: None)

    def test_callables_are_required(self, voice):
        with pytest.raises(TypeError):
            voice.register_provider("x", "X", None, lambda *a: None, lambda: None)
        with pytest.raises(TypeError):
            voice.register_provider("x", "X", list, lambda *a: None, lambda: None,
                                    is_available=True)

    def test_replace_and_unregister(self, voice):
        first = FakeProvider("piper").register(voice)
        second = FakeProvider("piper").register(voice)
        assert [p["id"] for p in voice.get_providers()].count("piper") == 1
        assert voice._get_provider("piper").speak == second.speak
        assert voice.unregister_provider("piper") is True
        assert voice.unregister_provider("piper") is False
        assert second.stops == 1 and first.stops == 0
        assert "piper" not in [p["id"] for p in voice.get_providers()]

    def test_windows_cannot_be_unregistered(self, voice):
        assert voice.unregister_provider("windows") is False
        assert voice._get_provider("windows") is not None

    def test_unregistering_stops_its_speech(self, voice):
        edge = FakeProvider("edge", "hang").register(voice)
        enable(voice, "briefing", provider="edge")
        assert voice.announce("Long briefing", "briefing")
        assert wait_until(lambda: edge.pending is not None)
        voice.unregister_provider("edge")
        assert wait_until(lambda: not voice.is_speaking())
        assert edge.stops >= 1

    def test_availability(self, voice):
        edge = FakeProvider("edge", available=False).register(voice)
        assert voice.is_provider_available("windows")
        assert not voice.is_provider_available("edge")
        assert not voice.is_provider_available("nothing")
        edge.available = True
        assert voice.is_provider_available("edge")
        voice.register_provider("none", "None", list, edge.speak, edge.stop)   # no check given
        assert voice.is_provider_available("none")

        def broken():
            raise RuntimeError("oops")

        voice.register_provider("broken", "Broken", list, edge.speak, edge.stop, broken)
        assert not voice.is_provider_available("broken")

    def test_list_voices_is_checked(self, voice):
        FakeProvider("edge", voices=[
            {"id": "a", "name": "Ardi", "language": "id-ID", "gender": "male"},
            {"id": "a", "name": "Duplicate"}, "junk", {"name": "no id"}, {"id": ""},
            {"id": "b"}, {"id": "c", "name": None, "language": 5},
        ]).register(voice)
        voices = voice.list_voices("edge")
        assert [v["id"] for v in voices] == ["a", "b", "c"]
        assert voices[0] == {"id": "a", "name": "Ardi", "language": "id-ID", "gender": "male"}
        assert voices[1] == {"id": "b", "name": "b", "language": ""}
        assert voices[2]["name"] == "c" and voices[2]["language"] == ""
        with pytest.raises(ValueError):
            voice.list_voices("nothing")

    def test_users_language_comes_first(self, voice):
        voices = [{"id": "1", "name": "Zira", "language": "en-US"},
                  {"id": "2", "name": "Gadis", "language": "id-ID"},
                  {"id": "3", "name": "Aria", "language": "en-US"},
                  {"id": "4", "name": "Ardi", "language": "id-ID"},
                  {"id": "5", "name": "Denise", "language": "fr-FR"},
                  {"id": "6", "name": "Unknown", "language": ""}]
        assert [v["name"] for v in voice.order_voices(voices, ["id"])] == [
            "Ardi", "Gadis", "Unknown", "Aria", "Zira", "Denise"]
        assert [v["name"] for v in voice.order_voices(voices, ["en", "id"])][:4] == [
            "Aria", "Zira", "Ardi", "Gadis"]

    def test_user_languages_start_with_harikus(self, voice, monkeypatch):
        from core import i18n
        monkeypatch.setattr(i18n, "_current_language", "id")
        monkeypatch.setattr(voice, "_windows_locale", lambda: "en-US")
        assert voice.user_languages() == ["id", "en"]
        monkeypatch.setattr(voice, "_windows_locale", lambda: "id-ID")
        assert voice.user_languages() == ["id"]

    def test_language_names(self, voice):
        assert voice.language_name("") == ""
        assert voice.language_name("id-ID")          # whatever Windows calls it
        assert voice.language_name("xx-not-a-tag") == "xx-not-a-tag"

    def test_cache_dir(self, voice, tmp_path):
        path = voice.cache_dir("edge")
        assert path == str(tmp_path / "userdata" / "voice_cache" / "edge")
        assert os.path.isdir(path)
        with pytest.raises(ValueError):
            voice.cache_dir("../evil")


# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------

class TestSettings:
    def test_defaults_change_nothing(self, voice):
        settings = voice.get_settings()
        assert settings == {"kinds": {"greeting": False, "briefing": False, "reminder": False},
                            "provider": "windows", "voice": "", "rate": 0, "volume": 100,
                            "fallback": "", "stop_on_key": True}
        assert not any(voice.is_enabled(kind) for kind in voice.KINDS)

    def test_round_trip_keeps_other_settings(self, voice):
        import core.api
        core.api.save_data("Core", {"user_nickname": "Bro", "volume": 40})
        assert voice.save_settings({"kinds": {"reminder": True}, "provider": "edge",
                                    "voice": "id-ID-GadisNeural", "rate": 3, "volume": 70,
                                    "fallback": "HKLM\\voice", "stop_on_key": False})
        stored = core.api.load_data("Core")
        assert stored["user_nickname"] == "Bro" and stored["volume"] == 40
        assert stored["hariku_voice"] == {
            "kinds": {"greeting": False, "briefing": False, "reminder": True},
            "provider": "edge", "voice": "id-ID-GadisNeural", "rate": 3, "volume": 70,
            "fallback": "HKLM\\voice", "stop_on_key": False}
        assert voice.is_enabled("reminder") and not voice.is_enabled("greeting")

    @pytest.mark.parametrize("raw, key, expected", [
        ({"rate": 99}, "rate", 10), ({"rate": -99}, "rate", -10), ({"rate": "x"}, "rate", 0),
        ({"volume": 150}, "volume", 100), ({"volume": -1}, "volume", 0),
        ({"provider": "Bad Id"}, "provider", "windows"), ({"voice": 5}, "voice", ""),
        ({"fallback": ["x"]}, "fallback", ""), ({"kinds": "all"}, "kinds",
                                                {"greeting": False, "briefing": False,
                                                 "reminder": False}),
    ])
    def test_hand_edited_values(self, voice, raw, key, expected):
        assert voice.normalize_settings(raw)[key] == expected

    def test_not_a_dict(self, voice):
        assert voice.normalize_settings("broken") == voice.normalize_settings(None)


# ------------------------------------------------------------
# announce()
# ------------------------------------------------------------

class TestAnnounce:
    def test_everything_off_by_default_goes_to_the_screen_reader(self, voice):
        edge = FakeProvider("edge").register(voice)
        events = []
        from core.events import bus
        handler = lambda payload: events.append(payload)   # noqa: E731
        bus.subscribe("on_before_speak", handler)
        try:
            for kind in voice.KINDS:
                assert voice.announce(f"{kind} text", kind, interrupt=kind != "greeting") is False
        finally:
            bus.unsubscribe("on_before_speak", handler)
        assert voice.said["speak"] == [("greeting text", False), ("briefing text", True),
                                       ("reminder text", True)]
        assert voice.said["braille"] == [] and voice.said["announced"] == []
        assert voice.windows.calls == [] and edge.calls == []
        assert events == []   # speech.speak (faked here) emits it itself
        assert not voice.is_speaking()

    def test_each_kind_has_its_own_switch(self, voice):
        enable(voice, "reminder")
        assert voice.announce("Good morning.", "greeting") is False
        assert voice.announce("Today is Monday.", "briefing") is False
        assert voice.announce("Reminder: Medicine", "reminder") is True
        assert wait_until(lambda: voice.windows.texts() == ["Reminder: Medicine"])
        assert [t for t, _i in voice.said["speak"]] == ["Good morning.", "Today is Monday."]

    def test_the_chosen_voice_speaks_and_braille_gets_the_text(self, voice):
        edge = FakeProvider("edge").register(voice)
        enable(voice, "briefing", provider="edge", voice="id-ID-GadisNeural", rate=4, volume=60)
        assert voice.announce("  Today is Monday.  ", "briefing") is True
        assert wait_until(lambda: edge.calls)
        assert edge.calls == [("Today is Monday.", "id-ID-GadisNeural", 4, 60)]
        assert voice.said["braille"] == [("Today is Monday.", True)]
        assert voice.said["speak"] == [] and voice.said["announced"] == []

    def test_on_before_speak_sees_it_once_and_can_change_or_cancel_it(self, voice):
        from core.events import bus
        enable(voice, "reminder")
        seen = []

        def handler(payload):
            seen.append(dict(payload))
            if payload["text"] == "secret":
                payload["cancel"] = True
            else:
                payload["text"] = payload["text"].upper()

        bus.subscribe("on_before_speak", handler)
        try:
            assert voice.announce("medicine", "reminder") is True
            assert voice.announce("secret", "reminder") is True
        finally:
            bus.unsubscribe("on_before_speak", handler)
        assert wait_until(lambda: voice.windows.texts() == ["MEDICINE"])
        assert [(s["text"], s["kind"], s["voice"]) for s in seen] == [
            ("medicine", "reminder", "windows"), ("secret", "reminder", "windows")]
        assert voice.said["braille"] == [("MEDICINE", True)]

    def test_bad_kind_and_empty_text(self, voice):
        with pytest.raises(ValueError):
            voice.announce("hi", "weather")
        enable(voice, "greeting")
        assert voice.announce("   ", "greeting") is False
        assert voice.announce(None, "greeting") is False
        assert voice.said == {"speak": [], "braille": [], "announced": []}

    def test_quiet_hours_do_not_apply(self, voice, monkeypatch):
        import core.personal
        monkeypatch.setattr(core.personal, "is_quiet_time", lambda now=None: True)
        enable(voice, "reminder")
        assert voice.announce("Reminder: Medicine", "reminder")
        assert wait_until(lambda: voice.windows.texts() == ["Reminder: Medicine"])


# ------------------------------------------------------------
# Fallbacks
# ------------------------------------------------------------

class TestFallback:
    def test_fallback_windows_voice(self, voice):
        edge = FakeProvider("edge", "error").register(voice)
        enable(voice, "reminder", provider="edge", voice="id-ID-ArdiNeural", fallback="ZIRA")
        assert voice.announce("Reminder: Medicine", "reminder")
        assert wait_until(lambda: voice.windows.calls)
        assert edge.texts() == ["Reminder: Medicine"]
        assert voice.windows.calls == [("Reminder: Medicine", "ZIRA", 0, 100)]
        assert wait_until(lambda: not voice.is_speaking())
        assert voice.said["announced"] == []
        assert voice.said["braille"] == [("Reminder: Medicine", True)]   # once

    def test_then_the_screen_reader(self, voice):
        FakeProvider("edge", "error").register(voice)
        voice.windows.behaviour = "error"
        enable(voice, "reminder", provider="edge", fallback="ZIRA")
        assert voice.announce("Reminder: Medicine", "reminder", interrupt=True)
        assert wait_until(lambda: voice.said["announced"])
        # Braille already has it, so the screen reader only speaks it.
        assert voice.said["announced"] == [("Reminder: Medicine", True, False)]
        assert voice.said["speak"] == []

    def test_screen_reader_as_the_fallback(self, voice):
        FakeProvider("edge", "raise").register(voice)
        enable(voice, "briefing", provider="edge", fallback="")
        assert voice.announce("Briefing", "briefing")
        assert wait_until(lambda: voice.said["announced"])
        assert voice.windows.calls == []

    def test_unavailable_source_uses_the_fallback_at_once(self, voice):
        edge = FakeProvider("edge", available=False).register(voice)
        enable(voice, "greeting", provider="edge", fallback="DAVID")
        assert voice.announce("Good morning.", "greeting", interrupt=False)
        assert wait_until(lambda: voice.windows.calls)
        assert edge.calls == [] and voice.windows.calls[0][1] == "DAVID"

    def test_nothing_available_goes_straight_to_the_screen_reader(self, voice):
        FakeProvider("edge", available=False).register(voice)
        enable(voice, "greeting", provider="edge")
        assert voice.announce("Good morning.", "greeting", interrupt=False) is False
        assert voice.said["speak"] == [("Good morning.", False)]
        assert voice.said["braille"] == []

    def test_missing_extension_falls_back(self, voice):
        enable(voice, "reminder", provider="edge", fallback="ZIRA")   # edge not registered
        assert voice.announce("Reminder: Medicine", "reminder")
        assert wait_until(lambda: voice.windows.calls)

    def test_same_voice_is_not_tried_twice(self, voice):
        voice.windows.behaviour = "error"
        enable(voice, "reminder", provider="windows", voice="ZIRA", fallback="ZIRA")
        voice.announce("Reminder: Medicine", "reminder")
        assert wait_until(lambda: voice.said["announced"])
        assert len(voice.windows.calls) == 1

    def test_a_stuck_voice_times_out(self, voice, monkeypatch):
        monkeypatch.setattr(voice, "_time_limit", lambda text, rate: 0.05)
        edge = FakeProvider("edge", "hang").register(voice)
        enable(voice, "reminder", provider="edge", fallback="ZIRA")
        voice.announce("Reminder: Medicine", "reminder")
        assert wait_until(lambda: voice.windows.calls)
        assert edge.stops >= 1

    def test_failures_are_logged_once(self, voice, caplog):
        edge = FakeProvider("edge", "error").register(voice)
        enable(voice, "reminder", provider="edge", fallback="ZIRA")
        caplog.set_level(logging.DEBUG, logger="core.voice")
        for _ in range(3):
            voice.announce("Reminder", "reminder", interrupt=False)
        assert wait_until(lambda: len(voice.windows.calls) == 3)
        assert wait_until(lambda: not voice.is_speaking())
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert sum("edge could not speak" in m for m in warnings) == 1, warnings
        assert sum("falling back from edge to windows" in m for m in warnings) == 1, warnings
        # Once it works again, a new failure is reported again.
        edge.behaviour = "ok"
        voice.announce("Reminder", "reminder", interrupt=False)
        assert wait_until(lambda: len(edge.calls) == 4 and not voice.is_speaking())
        edge.behaviour = "error"
        caplog.clear()
        voice.announce("Reminder", "reminder", interrupt=False)
        assert wait_until(lambda: len(voice.windows.calls) == 4)
        assert any("edge could not speak" in r.getMessage()
                   for r in caplog.records if r.levelno == logging.WARNING)


# ------------------------------------------------------------
# The queue
# ------------------------------------------------------------

class TestQueue:
    def test_without_interrupt_announcements_wait_their_turn(self, voice):
        voice.windows.behaviour = "hang"
        enable(voice, "greeting", "briefing")
        voice.announce("Good morning.", "greeting", interrupt=False)
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.announce("Today is Monday.", "briefing", interrupt=False)
        time.sleep(0.05)
        assert voice.windows.texts() == ["Good morning."]
        voice.windows.finish()
        assert wait_until(lambda: voice.windows.texts() == ["Good morning.", "Today is Monday."])
        voice.windows.finish()
        assert wait_until(lambda: not voice.is_speaking())
        assert voice.windows.stops == 0

    def test_interrupt_stops_the_current_one(self, voice):
        voice.windows.behaviour = "hang"
        enable(voice, "greeting", "reminder")
        voice.announce("Good morning, this is long.", "greeting", interrupt=False)
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.announce("Reminder: Medicine", "reminder", interrupt=True)
        assert wait_until(lambda: voice.windows.texts() == ["Good morning, this is long.",
                                                            "Reminder: Medicine"])
        assert voice.windows.stops == 1

    def test_interrupt_drops_what_was_waiting(self, voice):
        voice.windows.behaviour = "hang"
        enable(voice, "greeting", "briefing", "reminder")
        voice.announce("one", "greeting", interrupt=False)
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.announce("two", "briefing", interrupt=False)
        voice.announce("three", "reminder", interrupt=True)
        assert wait_until(lambda: voice.windows.texts() == ["one", "three"])
        voice.windows.finish()
        time.sleep(0.05)
        assert voice.windows.texts() == ["one", "three"]

    def test_interrupt_speech_setting_off_queues(self, voice):
        import core.api
        voice.windows.behaviour = "hang"
        enable(voice, "reminder")
        config = core.api.load_data("Core")
        config["interrupt_speech"] = False
        core.api.save_data("Core", config)
        voice.announce("one", "reminder")
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.announce("two", "reminder")
        time.sleep(0.05)
        assert voice.windows.texts() == ["one"] and voice.windows.stops == 0
        voice.windows.finish()
        assert wait_until(lambda: voice.windows.texts() == ["one", "two"])

    def test_stop_silences_everything(self, voice):
        voice.windows.behaviour = "hang"
        enable(voice, "greeting", "briefing")
        voice.announce("one", "greeting", interrupt=False)
        voice.announce("two", "briefing", interrupt=False)
        assert wait_until(lambda: voice.windows.pending is not None)
        assert voice.is_speaking()
        voice.stop()
        assert wait_until(lambda: not voice.is_speaking())
        assert voice.windows.texts() == ["one"] and voice.windows.stops == 1
        assert voice.said["announced"] == []   # stopping is not a failure

    def test_stop_also_stops_file_playback(self, voice, monkeypatch):
        stopped = []
        monkeypatch.setattr(voice, "stop_playback", lambda: stopped.append(True))
        voice.windows.behaviour = "hang"
        enable(voice, "briefing")
        voice.announce("one", "briefing")
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.stop()
        assert wait_until(lambda: stopped)

    def test_preview_speaks_with_unsaved_choices_and_reports(self, voice):
        edge = FakeProvider("edge", "error").register(voice)
        results = []
        assert voice.preview("Good morning. This is your Hariku voice.", "edge", "id-ID-Gadis",
                             -3, 55, on_done=results.append)
        assert wait_until(lambda: results)
        assert edge.calls == [("Good morning. This is your Hariku voice.", "id-ID-Gadis", -3, 55)]
        assert isinstance(results[0], RuntimeError)
        assert voice.windows.calls == [] and voice.said["announced"] == []   # no fallback
        assert voice.said["braille"] == [("Good morning. This is your Hariku voice.", True)]
        assert voice.preview("x", "nothing") is False


# ------------------------------------------------------------
# Stop when I press a key
# ------------------------------------------------------------

class TestKeyPress:
    def test_a_key_press_stops_the_voice_and_the_queue(self, voice, monkeypatch, caplog):
        monkeypatch.setattr(voice, "KEY_GRACE_SECONDS", 0.0)
        voice.windows.behaviour = "hang"
        enable(voice, "greeting", "briefing")
        caplog.set_level(logging.INFO, logger="core.voice")
        voice.announce("one", "greeting", interrupt=False)
        voice.announce("two", "briefing", interrupt=False)
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.inputs["tick"] += 50          # the user pressed a key
        assert wait_until(lambda: not voice.is_speaking())
        assert voice.windows.stops == 1 and voice.windows.texts() == ["one"]
        assert any("key press" in r.getMessage() for r in caplog.records)

    def test_input_right_after_the_start_does_not_count(self, voice, monkeypatch):
        monkeypatch.setattr(voice, "KEY_GRACE_SECONDS", 0.3)
        voice.windows.behaviour = "hang"
        enable(voice, "briefing")
        voice.announce("Briefing", "briefing")
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.inputs["tick"] += 1           # releasing the B that started it
        time.sleep(0.4)
        assert voice.is_speaking() and voice.windows.stops == 0
        voice.inputs["tick"] += 1           # a real key press afterwards
        assert wait_until(lambda: not voice.is_speaking())

    def test_a_key_still_held_extends_the_grace(self, voice, monkeypatch):
        monkeypatch.setattr(voice, "KEY_GRACE_SECONDS", 0.0)
        monkeypatch.setattr(voice, "KEY_HELD_GRACE_SECONDS", 10.0)
        voice.windows.behaviour = "hang"
        enable(voice, "briefing")
        voice.inputs["held"] = True
        voice.announce("Briefing", "briefing")
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.inputs["tick"] += 1
        time.sleep(0.1)
        assert voice.is_speaking()
        voice.inputs["held"] = False
        voice.inputs["tick"] += 1
        assert wait_until(lambda: not voice.is_speaking())

    def test_moving_the_mouse_does_not_count(self, voice, monkeypatch):
        monkeypatch.setattr(voice, "KEY_GRACE_SECONDS", 0.0)
        voice.windows.behaviour = "hang"
        enable(voice, "briefing")
        voice.announce("Briefing", "briefing")
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.inputs["cursor"] = (400, 300)     # the pointer moves, then the input time
        voice.inputs["tick"] += 1
        time.sleep(0.1)
        assert voice.is_speaking() and voice.windows.stops == 0
        time.sleep(voice.MOUSE_MOVE_SECONDS)
        voice.inputs["tick"] += 1               # a key, with the mouse still
        assert wait_until(lambda: not voice.is_speaking())

    def test_turned_off(self, voice, monkeypatch):
        monkeypatch.setattr(voice, "KEY_GRACE_SECONDS", 0.0)
        voice.windows.behaviour = "hang"
        enable(voice, "briefing", stop_on_key=False)
        voice.announce("Briefing", "briefing")
        assert wait_until(lambda: voice.windows.pending is not None)
        voice.inputs["tick"] += 100
        time.sleep(0.1)
        assert voice.is_speaking() and voice.windows.stops == 0

    def test_uses_getlastinputinfo_never_a_hook(self):
        with open(os.path.join(ROOT, "core", "voice.py"), encoding="utf-8") as f:
            source = f.read()
        assert "GetLastInputInfo" in source
        assert "SetWindowsHookEx" not in source and "import winsound" not in source

    def test_real_last_input_tick_is_a_number(self):
        import core.voice
        tick = core.voice._last_input_tick()
        assert tick is None or isinstance(tick, int)


# ------------------------------------------------------------
# play_file() through a fake MCI
# ------------------------------------------------------------

class FakeMci:
    def __init__(self, playing_polls=3, length="4000", fail_on=None):
        self.commands = []
        self.playing_polls = playing_polls
        self.length = length
        self.fail_on = fail_on
        self.lock = threading.Lock()
        self.threads = set()

    def __call__(self, command):
        import core.voice
        with self.lock:
            self.commands.append(command)
            self.threads.add(threading.get_ident())
        verb = command.split()[0]
        if self.fail_on and command.startswith(self.fail_on):
            raise core.voice.MciError(263, "The specified device is not open")
        if command.startswith("status") and command.endswith("length"):
            return self.length
        if command.startswith("status") and command.endswith("mode"):
            if self.playing_polls > 0:
                self.playing_polls -= 1
                return "playing"
            return "stopped"
        if command.startswith("status") and command.endswith("position"):
            return "100"
        return "1" if verb == "open" else ""


@pytest.fixture
def mci(voice, monkeypatch, tmp_path):
    fake = FakeMci()
    monkeypatch.setattr(voice, "_mci_send", fake)
    monkeypatch.setattr(voice, "PLAYER_POLL_SECONDS", 0.005)
    path = tmp_path / "speech.mp3"
    path.write_bytes(b"\xff\xf3" + b"\0" * 100)
    fake.path = str(path)
    yield fake
    playback = voice._current_playback
    voice.stop_playback()
    if playback is not None:
        playback._thread.join(2)


class TestPlayFile:
    def test_plays_to_the_end(self, voice, mci):
        done = []
        voice.play_file(mci.path, 80, done.append)
        assert wait_until(lambda: done)
        assert done == [None]
        alias = mci.commands[0].split()[-1]
        assert alias.startswith("hariku_voice_")
        assert mci.commands[:5] == [
            f'open "{mci.path}" type mpegvideo alias {alias}',
            f"set {alias} time format milliseconds",
            f"status {alias} length",
            f"setaudio {alias} volume to 800",
            f"play {alias}"]
        assert mci.commands[-1] == f"close {alias}"
        assert len(mci.threads) == 1 and threading.get_ident() not in mci.threads

    def test_stop_playback(self, voice, mci):
        mci.playing_polls = 10 ** 6
        done = []
        voice.play_file(mci.path, 100, done.append)
        assert wait_until(lambda: any(c.startswith("play") for c in mci.commands))
        voice.stop_playback()
        assert wait_until(lambda: done)
        assert done == [None]
        assert mci.commands[-2].startswith("stop ") and mci.commands[-1].startswith("close ")

    def test_a_new_file_stops_the_previous(self, voice, mci):
        mci.playing_polls = 10 ** 6
        first, second = [], []
        voice.play_file(mci.path, 100, first.append)
        assert wait_until(lambda: any(c.startswith("play") for c in mci.commands))
        voice.play_file(mci.path, 100, second.append)
        assert wait_until(lambda: first)
        assert wait_until(lambda: len([c for c in mci.commands if c.startswith("open")]) == 2)
        aliases = {c.split()[-1] for c in mci.commands if c.startswith("open")}
        assert len(aliases) == 2          # each playback has its own alias
        voice.stop_playback()
        assert wait_until(lambda: second)

    def test_errors_are_reported(self, voice, mci):
        mci.fail_on = "open"
        done = []
        voice.play_file(mci.path, 100, done.append)
        assert wait_until(lambda: done)
        assert isinstance(done[0], voice.MciError)
        assert not any(c.startswith("close") for c in mci.commands)
        missing = []
        voice.play_file(mci.path + ".gone", 100, missing.append)
        assert wait_until(lambda: missing)
        assert isinstance(missing[0], FileNotFoundError)

    def test_a_volume_mci_cannot_set_is_not_fatal(self, voice, mci):
        mci.fail_on = "setaudio"
        done = []
        voice.play_file(mci.path, 50, done.append)
        assert wait_until(lambda: done)
        assert done == [None]

    def test_voice_and_ui_sounds_use_separate_mci_devices(self, voice):
        # core/sounds.py names its waveaudio devices after the file; the voice
        # uses its own mpegvideo device and its own winmm handle, and never
        # winsound's single PlaySound slot.
        import ctypes
        import core.sounds
        assert core.sounds._sound_alias("C:\\x\\start.wav") == "startwav"
        assert voice._winmm() is not ctypes.windll.winmm
        with open(os.path.join(ROOT, "core", "voice.py"), encoding="utf-8") as f:
            source = f.read()
        assert "PlaySound(" not in source and "type waveaudio" not in source


# ------------------------------------------------------------
# The Windows voices (SAPI through ctypes COM, all mocked)
# ------------------------------------------------------------

class FakeEngine:
    instances = []
    default_done_after = 3      # polls of is_done() before the speech ends

    def __init__(self):
        self.log = []
        self.threads = set()
        self.done_after = FakeEngine.default_done_after
        self.polls = 0
        FakeEngine.instances.append(self)

    def _note(self, *entry):
        self.threads.add(threading.get_ident())
        self.log.append(entry)

    def list_voices(self):
        self._note("list")
        return [{"id": "ZIRA", "name": "Microsoft Zira", "language": "en-US"}]

    def set_voice(self, voice_id):
        self._note("set_voice", voice_id)

    def speak(self, text, rate, volume):
        self.polls = 0
        self._note("speak", text, rate, volume)

    def purge(self):
        self._note("purge")

    def is_done(self):
        self.polls += 1
        return self.polls > self.done_after

    def close(self):
        self._note("close")


@pytest.fixture
def sapi(monkeypatch):
    from core import voice_sapi
    monkeypatch.setattr(voice_sapi, "POLL_SECONDS", 0.005)
    FakeEngine.instances = []
    monkeypatch.setattr(FakeEngine, "default_done_after", 3)
    worker = voice_sapi.Worker(engine_factory=FakeEngine)
    yield voice_sapi, worker
    worker.shutdown()


class TestWindowsWorker:
    def test_speaks_on_one_worker_thread(self, sapi):
        voice_sapi, worker = sapi
        done = []
        worker.speak("Hello", "ZIRA", -2, 70, done.append)
        assert wait_until(lambda: done)
        assert done == [None]
        engine = FakeEngine.instances[0]
        assert engine.log[:2] == [("set_voice", "ZIRA"), ("speak", "Hello", -2, 70)]
        assert worker.call(lambda e: e.list_voices())[0]["id"] == "ZIRA"
        assert len(engine.threads) == 1 and threading.get_ident() not in engine.threads

    def test_default_voice(self, sapi):
        _voice_sapi, worker = sapi
        done = []
        worker.speak("Hello", "", 0, 100, done.append)
        assert wait_until(lambda: done)
        assert FakeEngine.instances[0].log[0] == ("set_voice", "")

    def test_stop_purges(self, sapi):
        _voice_sapi, worker = sapi
        FakeEngine.default_done_after = 10 ** 9
        done = []
        worker.speak("A long text", "ZIRA", 0, 100, done.append)
        assert wait_until(lambda: FakeEngine.instances and FakeEngine.instances[0].log)
        worker.stop()
        assert wait_until(lambda: done)
        assert done == [None] and ("purge",) in FakeEngine.instances[0].log

    def test_new_speech_replaces_the_old(self, sapi):
        _voice_sapi, worker = sapi
        first, second = [], []
        FakeEngine.default_done_after = 10 ** 9
        worker.speak("one", "ZIRA", 0, 100, first.append)
        assert wait_until(lambda: FakeEngine.instances and FakeEngine.instances[0].log)
        worker.speak("two", "ZIRA", 0, 100, second.append)
        assert wait_until(lambda: first)
        engine = FakeEngine.instances[0]
        assert first == [None] and ("purge",) in engine.log
        engine.done_after = 0
        assert wait_until(lambda: second)

    def test_errors_reach_on_done(self, sapi, monkeypatch):
        _voice_sapi, worker = sapi

        def broken(self, text, rate, volume):
            raise OSError("ISpVoice::Speak failed")

        monkeypatch.setattr(FakeEngine, "speak", broken)
        done = []
        worker.speak("Hello", "ZIRA", 0, 100, done.append)
        assert wait_until(lambda: done)
        assert isinstance(done[0], OSError)

    def test_sapi_that_cannot_start(self, sapi, monkeypatch):
        voice_sapi, _worker = sapi

        def no_sapi():
            raise OSError("CoCreateInstance failed")

        worker = voice_sapi.Worker(engine_factory=no_sapi)
        try:
            done = []
            worker.speak("Hello", "", 0, 100, done.append)
            assert wait_until(lambda: done)
            assert isinstance(done[0], OSError)
            assert not worker.available()
            with pytest.raises(OSError):
                worker.call(lambda e: e.list_voices())
            worker._failed_at -= voice_sapi.RETRY_SECONDS + 1
            assert worker.available()   # tried again after a minute
        finally:
            worker.shutdown()

    def test_stop_without_a_worker_starts_nothing(self, sapi):
        voice_sapi, _worker = sapi
        idle = voice_sapi.Worker(engine_factory=FakeEngine)
        idle.stop()
        assert idle._thread is None


class FakeInterface:
    """Stands in for a COM interface: records vtable calls and fills out-params."""

    def __init__(self, name, handler=None):
        self.name = name
        self.handler = handler
        self.calls = []
        self.released = False
        self.ptr = ctypes.c_void_p(id(self))

    def call(self, index, argtypes, *args, what=""):
        self.calls.append((index, args))
        if self.handler:
            return self.handler(self, index, args)
        return 0

    def release(self):
        self.released = True


_keep_alive = []


def put_string(out_arg, text):
    buf = ctypes.create_unicode_buffer(text)
    _keep_alive.append(buf)
    out_arg._obj.value = ctypes.addressof(buf)


def put_pointer(out_arg, obj):
    _keep_alive.append(obj)
    out_arg._obj.value = id(obj)


class TestSapiCom:
    @pytest.fixture
    def com(self, monkeypatch):
        from core import voice_sapi as vs

        class Ole32:
            def __init__(self):
                self.initialized = 0
                self.uninitialized = 0

            def CoInitializeEx(self, reserved, flags):
                assert flags == vs.COINIT_APARTMENTTHREADED
                self.initialized += 1
                return 0

            def CoUninitialize(self):
                self.uninitialized += 1

            def CoTaskMemFree(self, ptr):
                pass

        ole32 = Ole32()
        monkeypatch.setattr(vs, "_ole32", lambda: ole32)
        tokens = {}   # id(FakeInterface) -> FakeInterface
        categories = {
            vs.VOICE_CATEGORIES[0]: [("HKLM\\Speech\\Tokens\\ZIRA", "Microsoft Zira Desktop",
                                      "409"),
                                     ("HKLM\\Speech\\Tokens\\GADIS", "Microsoft Gadis", "421")],
            vs.VOICE_CATEGORIES[1]: [("HKLM\\OneCore\\Tokens\\ZIRA2", "Microsoft Zira Desktop",
                                      "409;9"),
                                     ("HKLM\\OneCore\\Tokens\\ANDIKA", "", "421")],
        }

        def token_handler(token_id, name, lcid):
            def handler(self, index, args):
                if index == vs.TOKEN_GET_ID:
                    put_string(args[0], token_id)
                elif index == vs.DATAKEY_GET_STRING_VALUE and args[0] is None:
                    put_string(args[1], f"{name or 'Microsoft Andika'} - Some Language")
                elif index == vs.DATAKEY_OPEN_KEY:
                    attrs = FakeInterface("attributes", attribute_handler(name, lcid))
                    put_pointer(args[1], attrs)
                    tokens[id(attrs)] = attrs
                return 0
            return handler

        def attribute_handler(name, lcid):
            def handler(self, index, args):
                if index == vs.DATAKEY_GET_STRING_VALUE:
                    value = {"Name": name, "Language": lcid}.get(args[0])
                    if not value:
                        raise vs.ComError(-2147201990, "GetStringValue")   # SPERR_NOT_FOUND
                    put_string(args[1], value)
                return 0
            return handler

        def enum_handler(entries):
            def handler(self, index, args):
                if index == vs.ENUM_GET_COUNT:
                    args[0]._obj.value = len(entries)
                elif index == vs.ENUM_ITEM:
                    token = FakeInterface("token", token_handler(*entries[args[0]]))
                    put_pointer(args[1], token)
                    tokens[id(token)] = token
                return 0
            return handler

        def category_handler(self, index, args):
            if index == vs.CATEGORY_SET_ID:
                self.category = args[0]
            elif index == vs.CATEGORY_ENUM_TOKENS:
                enum = FakeInterface("enum", enum_handler(categories[self.category]))
                put_pointer(args[2], enum)
                tokens[id(enum)] = enum
            return 0

        created = []

        def create(clsid, iid, what=""):
            if clsid == vs.CLSID_SpVoice:
                obj = FakeInterface("voice", lambda self, index, args:
                                    0 if index != vs.VOICE_WAIT_UNTIL_DONE else 1)
            elif clsid == vs.CLSID_SpObjectTokenCategory:
                obj = FakeInterface("category", category_handler)
            else:
                obj = FakeInterface("token")
            created.append(obj)
            return obj

        monkeypatch.setattr(vs, "create", create)

        # Interface(ptr) wraps what an out-param received: map it back to the fake.
        real_interface = vs.Interface

        def interface(ptr):
            value = ptr.value if isinstance(ptr, ctypes.c_void_p) else ptr
            return tokens.get(value) or real_interface(ptr)

        monkeypatch.setattr(vs, "Interface", interface)
        return vs, ole32, created

    def test_lists_classic_and_onecore_voices_once(self, com):
        vs, ole32, created = com
        engine = vs.Sapi()
        voices = engine.list_voices()
        assert ole32.initialized == 1
        assert [(v["name"], v["language"]) for v in voices] == [
            ("Microsoft Zira Desktop", "en-US"), ("Microsoft Gadis", "id-ID"),
            ("Microsoft Andika", "id-ID")]
        assert voices[0]["id"] == "HKLM\\Speech\\Tokens\\ZIRA"
        categories = [o for o in created if o.name == "category"]
        assert [c.category for c in categories] == list(vs.VOICE_CATEGORIES)
        assert all(c.released for c in categories)
        engine.close()
        assert ole32.uninitialized == 1

    def test_speak_rate_volume_and_stop(self, com):
        vs, _ole32, created = com
        engine = vs.Sapi()
        voice = created[0]
        engine.set_voice("HKLM\\Speech\\Tokens\\ZIRA")
        engine.set_voice("HKLM\\Speech\\Tokens\\ZIRA")      # already set: no call
        token = created[-1]
        assert token.calls[0] == (vs.TOKEN_SET_ID, (None, "HKLM\\Speech\\Tokens\\ZIRA", False))
        engine.speak("Reminder: <Rapat> & makan", -4, 65)
        assert not engine.is_done()
        engine.purge()
        engine.set_voice("")
        flags = vs.SPF_ASYNC | vs.SPF_PURGEBEFORESPEAK | vs.SPF_IS_NOT_XML
        assert voice.calls == [
            (vs.VOICE_SET_VOICE, (token.ptr,)),
            (vs.VOICE_SET_RATE, (-4,)),
            (vs.VOICE_SET_VOLUME, (65,)),
            (vs.VOICE_SPEAK, ("Reminder: <Rapat> & makan", flags, None)),
            (vs.VOICE_WAIT_UNTIL_DONE, (0,)),
            (vs.VOICE_SPEAK, (None, vs.SPF_ASYNC | vs.SPF_PURGEBEFORESPEAK, None)),
            (vs.VOICE_SET_VOICE, (None,)),
        ]
        engine.close()
        assert token.released and voice.released

    def test_vtable_calls_go_through_ctypes(self):
        # A real (fake) COM object: a pointer to a table of function pointers.
        from core import voice_sapi as vs
        seen = []
        prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_long)
        callbacks = [prototype(lambda this, value, i=i: seen.append((i, value)) or
                               (-2147467259 if value < 0 else 0)) for i in range(4)]
        table = (ctypes.c_void_p * 4)(*[ctypes.cast(c, ctypes.c_void_p) for c in callbacks])
        obj = ctypes.c_void_p(ctypes.addressof(table))
        pointer = ctypes.c_void_p(ctypes.addressof(obj))
        assert vs.vcall(pointer, 3, (ctypes.c_long,), 7) == 0
        assert seen == [(3, 7)]
        with pytest.raises(vs.ComError) as error:
            vs.vcall(pointer, 1, (ctypes.c_long,), -1)
        assert error.value.hresult == 0x80004005
        assert seen[-1] == (1, -1)

    def test_guids_and_languages(self):
        from core import voice_sapi as vs
        g = vs.guid(vs.CLSID_SpVoice)
        assert (g.Data1, g.Data2, g.Data3) == (0x96749377, 0x3391, 0x11D2)
        assert bytes(g.Data4) == bytes.fromhex("9EE300C04F797396")
        assert vs.lcid_to_tag("409;9") == "en-US"
        assert vs.lcid_to_tag("421") == "id-ID"
        assert vs.lcid_to_tag("") == "" and vs.lcid_to_tag("zz") == ""

    def test_the_provider_functions_use_the_worker(self, monkeypatch):
        from core import voice_sapi as vs
        worker = vs.Worker(engine_factory=FakeEngine)
        monkeypatch.setattr(vs, "_worker", worker)
        monkeypatch.setattr(vs, "POLL_SECONDS", 0.005)
        try:
            assert vs.list_voices()[0]["name"] == "Microsoft Zira"
            done = []
            vs.speak("Hi", "ZIRA", 0, 100, done.append)
            assert wait_until(lambda: done)
            assert vs.is_available()
        finally:
            vs.shutdown()


# ------------------------------------------------------------
# The screen reader side (core/speech.py, Tolk mocked by conftest)
# ------------------------------------------------------------

class TestSpeechHelpers:
    @pytest.fixture
    def tolk(self, tmp_data_dir, monkeypatch):
        import core.speech
        from cytolk import tolk
        time.sleep(0.05)          # speech threads of earlier tests
        tolk.reset_mock()
        monkeypatch.setattr(core.speech, "TOLK_LOADED", True)
        return tolk

    def test_braille_only(self, tolk):
        import core.speech
        core.speech.braille("Reminder: Medicine", interrupt=True)
        assert wait_until(lambda: tolk.braille.called)
        tolk.braille.assert_called_once_with("Reminder: Medicine")
        tolk.silence.assert_called_once_with()
        assert not tolk.output.called and not tolk.speak.called

    def test_braille_follows_the_setting(self, tolk):
        import core.api
        import core.speech
        core.api.save_data("Core", {"braille_output": False})
        core.speech.braille("hidden")
        time.sleep(0.05)
        assert not tolk.braille.called

    def test_fallback_speech_without_a_second_braille_or_event(self, tolk):
        import core.speech
        from core.events import bus
        events = []
        handler = lambda payload: events.append(payload)   # noqa: E731
        bus.subscribe("on_before_speak", handler)
        try:
            core.speech.speak_announced("Reminder: Medicine", True, braille=False)
            assert wait_until(lambda: tolk.speak.called)
        finally:
            bus.unsubscribe("on_before_speak", handler)
        tolk.speak.assert_called_once_with("Reminder: Medicine", True)
        assert not tolk.output.called and events == []

    def test_speak_is_unchanged(self, tolk):
        import core.speech
        core.speech.speak("Hello", interrupt=True)
        assert wait_until(lambda: tolk.output.called)
        tolk.output.assert_called_once_with("Hello", True)


# ------------------------------------------------------------
# The call sites
# ------------------------------------------------------------

@pytest.fixture
def english(monkeypatch):
    from core import i18n
    had_core, old_core = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    monkeypatch.setattr(i18n, "_current_language", "en")
    yield
    if had_core:
        i18n._language_cache["core"] = old_core
    else:
        i18n._language_cache.pop("core", None)


class TestCallSites:
    def test_startup_greeting(self, voice, english):
        import core.api
        import core.personal
        core.api.save_data("Core", {"user_nickname": "Bro"})
        core.personal.speak_startup_greeting("Welcome to Hariku version 2.7.0")
        assert voice.said["speak"] and voice.windows.calls == []      # off: screen reader
        enable(voice, "greeting")
        core.personal.speak_startup_greeting("Welcome to Hariku version 2.7.0")
        assert wait_until(lambda: voice.windows.calls)
        text = voice.windows.calls[0][0]
        assert ", Bro. " in text and text.endswith("Welcome to Hariku version 2.7.0.")
        assert len(voice.said["speak"]) == 1

    def _fire_reminder(self, voice, monkeypatch):
        import core.reminders
        import core.sounds
        shown = []

        class FakeDialog:
            def __init__(self, parent, data, voiced=False):
                shown.append((dict(data), voiced))

            def Raise(self):
                pass

            def ShowModal(self):
                return 0

            def Destroy(self):
                pass

        monkeypatch.setattr(core.sounds, "play_sound", lambda path: True)
        monkeypatch.setattr(core.reminders, "ReminderDialog", FakeDialog)
        core.reminders.show_notification({"id": "1", "title": "Take <medicine> & water",
                                          "date": "2026-09-24", "time": "08:00"})
        return shown

    def test_reminder_with_the_voice_is_not_sent_to_the_screen_reader(self, voice, monkeypatch):
        enable(voice, "reminder")
        shown = self._fire_reminder(voice, monkeypatch)
        assert wait_until(lambda: voice.windows.calls)
        assert voice.windows.calls[0][0] == "Reminder: Take <medicine> & water"
        assert voice.said["speak"] == []
        assert voice.said["braille"] == [("Reminder: Take <medicine> & water", True)]
        assert shown[0][1] is True        # the dialog keeps the text out of its announcement

    def test_reminder_without_the_voice_is_as_before(self, voice, monkeypatch):
        shown = self._fire_reminder(voice, monkeypatch)
        assert voice.said["speak"] == [("Reminder: Take <medicine> & water", True)]
        assert shown[0][1] is False and voice.windows.calls == []

    def test_briefing_announces_as_a_briefing(self):
        with open(os.path.join(ROOT, "extensions", "briefing", "main.py"), encoding="utf-8") as f:
            source = f.read()
        assert "from core.speech import speak" not in source
        assert source.count('"briefing", interrupt=') == 2
        assert source.count('"briefing",\n             interrupt=False)') == 1

    def test_stop_hotkey(self):
        with open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8") as f:
            source = f.read()
        assert ('register_action("Hariku Core", "stop_voice", _("nav_stop_voice"), ord(\'S\'), '
                'False, core.voice.stop)') in source

    def test_no_bundled_extension_takes_plain_s(self):
        import re
        found = []
        ext_root = os.path.join(ROOT, "extensions")
        for ext in os.listdir(ext_root):
            main = os.path.join(ext_root, ext, "main.py")
            if not os.path.isfile(main):
                continue
            with open(main, encoding="utf-8") as f:
                source = f.read()
            for match in re.finditer(r"register_action\((.*?)\)\n", source, re.S):
                call = match.group(1)
                if re.search(r"ord\(['\"]S['\"]\)", call) and "default_shift=True" not in call \
                        and not re.search(r"ord\(['\"]S['\"]\),\s*True", call):
                    found.append(ext)
        assert found == []

    def test_voice_page_creates_each_label_before_its_control(self):
        # Screen readers name a control after the static text created right
        # before it; SetName alone doesn't do it. So every labeled control on
        # the page is made by a factory the helper calls after the label.
        import ast
        with open(os.path.join(ROOT, "core", "voice_panel.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id in ("_labeled", "_labeled_row")]
        assert len(calls) == 6
        for call in calls:
            assert isinstance(call.args[3], ast.Lambda), f"line {call.lineno}: pass a factory"
        controls = {"Choice", "ComboBox", "ListCtrl", "ListBox", "SpinCtrl", "Slider", "TextCtrl"}
        made = [node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in controls]
        inside = {id(n) for call in calls for n in ast.walk(call.args[3])}
        assert made and all(id(node) in inside for node in made), \
            "a control is created outside a label helper"

    def test_voice_messages_exist_in_both_languages(self):
        import ast
        import json
        used = set()
        for name in ("voice.py", "voice_panel.py", "core_panels.py"):
            with open(os.path.join(ROOT, "core", name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "_" and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and str(node.args[0].value).startswith(("voice_", "prefs_tab_voice"))):
                    used.add(node.args[0].value)
        used.add("nav_stop_voice")
        assert "voice_test_text" in used and "voice_windows_privacy" in used
        for code in ("en", "id"):
            with open(os.path.join(ROOT, "locales", f"{code}.json"), encoding="utf-8") as f:
                messages = json.load(f)["messages"]
            assert not sorted(used - set(messages)), f"locales/{code}.json lacks some keys"
        with open(os.path.join(ROOT, "locales", "id.json"), encoding="utf-8") as f:
            messages = json.load(f)["messages"]
        assert "Anda" in messages["voice_test_text"]
