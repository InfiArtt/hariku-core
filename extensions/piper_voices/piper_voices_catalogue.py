# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The Piper voice catalogue (no network, no wx).

The index is rhasspy/piper-voices' voices.json on Hugging Face: an object
keyed by voice ("id_ID-news_tts-medium"), each with

    {"key", "name", "quality": "x_low" | "low" | "medium" | "high",
     "language": {"code": "id_ID", "family": "id", "region": "ID",
                  "name_native", "name_english", "country_english"},
     "num_speakers", "speaker_id_map", "aliases",
     "files": {"<family>/<code>/<name>/<quality>/<key>.onnx":
                   {"size_bytes": 62950044, "md5_digest": "17de..."},
               ".../<key>.onnx.json": {...}, ".../MODEL_CARD": {...}}}

parse_catalogue() keeps the voices whose entries are complete and safe (file
paths inside the repository, the three expected files, sizes and md5 digests
that make sense). Each voice's MODEL_CARD names the dataset and its license;
parse_model_card() pulls those lines out.
"""
import re
import urllib.parse

INDEX_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"
FILES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

QUALITIES = ("x_low", "low", "medium", "high")
MAX_FILE_BYTES = 1024 * 1024 * 1024     # no voice file is anywhere near 1 GB
MAX_CARD_BYTES = 64 * 1024
MAX_CARD_LINES = 12
MAX_CARD_LINE_LENGTH = 300

# Names are letters, digits and "_" (Unicode letters too: "pt_PT-tugão-medium").
_KEY_RE = re.compile(r"[a-z]{2,3}_[A-Z]{2}-\w{1,64}-(?:x_low|low|medium|high)\Z")
_CODE_RE = re.compile(r"[a-z]{2,3}_[A-Z]{2}\Z")
_SEGMENT_RE = re.compile(r"\w[\w.\-]{0,127}\Z")
_MD5_RE = re.compile(r"[0-9a-f]{32}\Z")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Licence texts that don't actually name a licence.
_UNCLEAR_LICENSES = ("", "see url", "see link", "see the url", "see website", "unknown",
                     "n/a", "na", "none", "?", "-", "tbd", "todo")


class CatalogueError(ValueError):
    """The voice index is not what Hariku expects."""


def valid_key(key):
    return isinstance(key, str) and bool(_KEY_RE.match(key))


def bcp47(code):
    """"id_ID" -> "id-ID"."""
    return str(code or "").replace("_", "-")


def primary(tag):
    """The language family of a tag: "id-ID", "id_ID" or "id" -> "id"."""
    return str(tag or "").replace("_", "-").split("-")[0].strip().lower()


def file_url(path):
    """The download URL of a file listed in the index."""
    if not safe_path(path):
        raise CatalogueError(f"unsafe file path: {path!r}")
    return FILES_URL + urllib.parse.quote(path, safe="/")


def safe_path(path):
    """A relative path of plain segments: no "..", no drive, no backslash."""
    if not isinstance(path, str) or not path or len(path) > 512:
        return False
    segments = path.split("/")
    return all(_SEGMENT_RE.match(s) and s not in (".", "..") for s in segments)


def _text(value, limit=100):
    if not isinstance(value, str):
        return ""
    return " ".join(_CONTROL_RE.sub(" ", value).split())[:limit]


def _size(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_FILE_BYTES


def _file(path, info):
    if not isinstance(info, dict) or not safe_path(path):
        return None
    size, md5 = info.get("size_bytes"), info.get("md5_digest")
    if not _size(size) or not isinstance(md5, str) or not _MD5_RE.match(md5.lower()):
        return None
    return {"path": path, "size": size, "md5": md5.lower()}


def parse_voice(key, entry):
    """One index entry as Hariku uses it, or None when it isn't usable."""
    if not valid_key(key) or not isinstance(entry, dict):
        return None
    if entry.get("key", key) != key:
        return None
    quality = entry.get("quality")
    if quality not in QUALITIES or not key.endswith("-" + quality):
        return None
    language = entry.get("language")
    if not isinstance(language, dict):
        return None
    code = language.get("code")
    if not isinstance(code, str) or not _CODE_RE.match(code) or not key.startswith(code + "-"):
        return None
    files = entry.get("files")
    if not isinstance(files, dict):
        return None
    found = {}
    for path, info in files.items():
        if not isinstance(path, str):
            continue
        name = path.rsplit("/", 1)[-1]
        role = {key + ".onnx": "model", key + ".onnx.json": "config", "MODEL_CARD": "card"}.get(name)
        if role is None or role in found:
            continue
        item = _file(path, info)
        if item is None:
            return None
        found[role] = item
    if set(found) != {"model", "config", "card"}:
        return None
    speakers = entry.get("num_speakers")
    name = _text(entry.get("name")) or key.split("-")[1]
    return {
        "key": key,
        "name": name,
        "language": bcp47(code),
        "family": primary(code),
        "language_english": _text(language.get("name_english")),
        "country_english": _text(language.get("country_english")),
        "language_native": _text(language.get("name_native")),
        "quality": quality,
        "speakers": speakers if _size(speakers) else 1,
        "files": found,
        # What Download fetches (the model card comes first, on its own).
        "size": found["model"]["size"] + found["config"]["size"],
    }


def parse_catalogue(data):
    """The usable voices of a voices.json index, sorted by key. Raises
    CatalogueError when the index isn't an object or has no usable voice."""
    if not isinstance(data, dict):
        raise CatalogueError("the voice index is not an object")
    voices = []
    for key in sorted(k for k in data if isinstance(k, str)):
        voice = parse_voice(key, data[key])
        if voice is not None:
            voices.append(voice)
    if not voices:
        raise CatalogueError("the voice index lists no usable voice")
    return voices


# ------------------------------------------------------------
# Languages
# ------------------------------------------------------------

def filter_voices(voices, family=None):
    """The voices of one language family ("id"); all of them for None."""
    if not family:
        return list(voices)
    family = primary(family)
    return [v for v in voices if v.get("family") == family]


def order_voices(voices, languages=()):
    """The user's languages first (in their order), then the rest by language
    code; within a language by name, then quality from low to high."""
    preferred = [p for p in (primary(l) for l in languages or ()) if p]

    def key(voice):
        family = voice.get("family") or primary(voice.get("language"))
        rank = preferred.index(family) if family in preferred else len(preferred)
        quality = voice.get("quality")
        return (rank, str(voice.get("language") or "").lower(),
                str(voice.get("name") or "").lower(),
                QUALITIES.index(quality) if quality in QUALITIES else len(QUALITIES),
                str(voice.get("key") or ""))

    return sorted(voices, key=key)


def language_choices(voices, languages=(), english_name=None):
    """The entries of the Language choice: the user's languages that have
    voices, then None ("All languages"), then every other language family
    by name. `english_name(family)` sorts them (the family code by default)."""
    families = []
    for voice in voices:
        family = voice.get("family")
        if family and family not in families:
            families.append(family)
    preferred = []
    for language in languages or ():
        family = primary(language)
        if family in families and family not in preferred:
            preferred.append(family)
    others = sorted((f for f in families if f not in preferred),
                    key=lambda f: ((english_name(f) if english_name else f) or f).lower())
    return preferred + [None] + others


# ------------------------------------------------------------
# Model cards
# ------------------------------------------------------------

def parse_model_card(text):
    """The dataset lines of a MODEL_CARD:

        {"lines": ["URL: https://...", "License: See URL"],
         "dataset_url": "https://...", "license": "See URL",
         "license_clear": False}

    The lines are the card's own (English) words, cleaned of control
    characters. license_clear is False when no licence is named."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = text if isinstance(text, str) else ""
    section = ""
    lines, dataset_url, license_text = [], "", None
    fallback_license, fallback_line = None, ""
    for raw in text[:MAX_CARD_BYTES].splitlines():
        line = raw.strip()
        if line.startswith("#"):
            section = line.lstrip("#").strip().lower()
            continue
        if not line.startswith(("*", "-")):
            continue
        item = " ".join(_CONTROL_RE.sub(" ", line[1:]).split())[:MAX_CARD_LINE_LENGTH]
        if not item:
            continue
        label, _sep, value = item.partition(":")
        label = label.strip().lower()
        value = value.strip()
        if section.startswith("dataset"):
            if len(lines) < MAX_CARD_LINES:
                lines.append(item)
            if label == "url" and not dataset_url:
                dataset_url = value
            elif label in ("license", "licence") and license_text is None:
                license_text = value
        elif label in ("license", "licence") and fallback_license is None:
            fallback_license = value
            fallback_line = item
    if license_text is None and fallback_license is not None:
        license_text = fallback_license
        lines.append(fallback_line)
    license_text = license_text or ""
    return {"lines": lines, "dataset_url": dataset_url, "license": license_text,
            "license_clear": license_is_clear(license_text)}


def license_is_clear(license_text):
    """Whether a licence line actually names a licence ("CC BY 4.0"), rather
    than pointing elsewhere ("See URL") or being empty."""
    value = " ".join(str(license_text or "").split()).strip().rstrip(".").lower()
    return value not in _UNCLEAR_LICENSES
