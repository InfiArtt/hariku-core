# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Native voices: which of Hariku Voice's voices speaks a place's own language.
The Edge Voices extension's online voices come first (they cover nearly every
language here), then Piper's (installed on this computer), then the Windows
voices. Voices are listed through core.voice on a worker thread and kept for
ten minutes. No wx.
"""

import threading
import time

import world_trip_phrases as phrases

PROVIDER_ORDER = ("edge", "piper", "windows")
MAX_AGE_SECONDS = 600.0


def norm_tag(tag):
    return str(tag or "").replace("_", "-").strip().lower()


def pick(voices_by_provider, tags, primary=None, any_region=True, order=PROVIDER_ORDER):
    """The best voice for the language: the first provider in `order` with a
    voice whose tag is one of `tags` (in that order), or, with `any_region`,
    any voice of the `primary` language. {"provider", "id", "name",
    "language", "gender"} or None."""
    wanted = [norm_tag(t) for t in tags if t]
    primary = norm_tag(primary)
    for provider in order:
        voices = sorted(voices_by_provider.get(provider) or [],
                        key=lambda v: (str(v.get("name") or "").lower(), str(v.get("id"))))
        for tag in wanted:
            for voice in voices:
                if norm_tag(voice.get("language")) == tag:
                    return dict(voice, provider=provider)
        if any_region and primary:
            for voice in voices:
                if norm_tag(voice.get("language")).split("-")[0] == primary:
                    return dict(voice, provider=provider)
    return None


def pick_for(voices_by_provider, code, country_code=""):
    """The native voice for a World Trip language code ("ja", "pt-PT")."""
    if code not in phrases.LANGUAGES:
        return None
    return pick(voices_by_provider, phrases.voice_tags(code, country_code),
                primary=code.split("-")[0], any_region=phrases.any_region(code))


class VoiceBook:
    """The voices of the registered providers, listed on demand and kept for
    a while. `providers()` gives the registered provider ids, `available(id)`
    whether one can speak now, `list_voices(id)` its voices (slow)."""

    def __init__(self, providers, available, list_voices, clock=time.monotonic,
                 max_age=MAX_AGE_SECONDS):
        self._providers = providers
        self._available = available
        self._list_voices = list_voices
        self._clock = clock
        self._max_age = max_age
        self._lock = threading.Lock()
        self._voices = None
        self._listed_at = None

    def forget(self):
        with self._lock:
            self._voices = None

    def cached(self):
        with self._lock:
            if self._voices is None or self._clock() - self._listed_at > self._max_age:
                return None
            return dict(self._voices)

    def voices(self):
        """{provider id: [voices]} of the providers that can speak now. Blocks:
        a worker thread only. A provider that fails to list is left out."""
        found = self.cached()
        if found is not None:
            return found
        found = {}
        try:
            registered = list(self._providers())
        except Exception:
            registered = []
        for provider in PROVIDER_ORDER:
            if provider not in registered:
                continue
            try:
                if not self._available(provider):
                    continue
                found[provider] = list(self._list_voices(provider) or [])
            except Exception:
                continue
        with self._lock:
            self._voices = found
            self._listed_at = self._clock()
        return dict(found)

    def for_language(self, code, country_code=""):
        return pick_for(self.voices(), code, country_code)
