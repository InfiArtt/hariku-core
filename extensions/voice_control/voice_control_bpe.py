# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
A wake phrase as the keyword model's tokens, in pure Python (no wx, no
network, standard library only).

The keyword model (sherpa-onnx's English gigaspeech KWS model) hears
subword tokens: "HEY ARUNA" is "▁HE Y ▁A RU N A". They come from its
bpe.model, a sentencepiece ModelProto (a protobuf message). Despite the file
name, icefall trained it as a *unigram* sentencepiece model (its trainer spec
says model_type UNIGRAM, "unigram_500"), so a text is split the way
sentencepiece splits for a unigram model, not by BPE merges:

  * the text becomes "▁" + its words joined by "▁" (sentencepiece's
    add_dummy_prefix, remove_extra_whitespaces and escape_whitespaces);
  * of every way to cut it into pieces of the vocabulary, the one whose
    pieces' scores (log probabilities) add up to the most wins (Viterbi, as
    sentencepiece's optimized unigram encoder does it, with float32 sums and
    its tie-breaking); a character no piece covers is <unk>, scored as the
    lowest piece minus 10, and neighbouring unknown characters make one piece.

read_model() reads the parts needed with a small reader of the protobuf wire
format (no protobuf package). The model's normalizer (NFKC) changes nothing
in the plain upper-case ASCII text Hariku gives it (voice_control_wake.
clean_phrase() makes that), so it isn't repeated here.
tests/test_voice_control_wake.py checks the result against sentencepiece
itself (fixed outputs recorded from it) on hundreds of phrases.
"""
import struct

WHITESPACE = "▁"          # sentencepiece's "▁"

# SentencePiece.Type
NORMAL, UNKNOWN, CONTROL, USER_DEFINED, UNUSED, BYTE = 1, 2, 3, 4, 5, 6
# TrainerSpec.ModelType
UNIGRAM, BPE, WORD, CHAR = 1, 2, 3, 4

UNK_PENALTY = 10.0             # sentencepiece's kUnkPenalty
FLT_MIN = 1.1754943508222875e-38
MAX_MODEL_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 200

_F32 = struct.Struct("<f")


def f32(value):
    """`value` rounded to a float32, as sentencepiece's C++ keeps scores."""
    return _F32.unpack(_F32.pack(value))[0]


class ModelError(ValueError):
    """The file isn't a sentencepiece model this reader understands."""


# ------------------------------------------------------------
# The protobuf wire format (just enough of it)
# ------------------------------------------------------------

def _varint(data, pos):
    result = shift = 0
    while True:
        if pos >= len(data):
            raise ModelError("truncated varint")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ModelError("varint too long")


def fields(data):
    """(field number, wire type, value) for each field of a message: an int
    for a varint, bytes for a length-delimited field, 4 or 8 bytes for the
    fixed ones."""
    pos, end = 0, len(data)
    while pos < end:
        key, pos = _varint(data, pos)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise ModelError("field number 0")
        if wire == 0:
            value, pos = _varint(data, pos)
        elif wire == 1:
            value, pos = data[pos:pos + 8], pos + 8
        elif wire == 2:
            size, pos = _varint(data, pos)
            value, pos = data[pos:pos + size], pos + size
        elif wire == 5:
            value, pos = data[pos:pos + 4], pos + 4
        else:
            raise ModelError(f"unsupported wire type {wire}")
        if pos > end:
            raise ModelError("truncated field")
        yield number, wire, value


def _piece(message):
    piece, score, kind = None, 0.0, NORMAL
    for number, wire, value in fields(message):
        if number == 1 and wire == 2:
            try:
                piece = bytes(value).decode("utf-8")
            except UnicodeDecodeError:
                raise ModelError("a piece that isn't UTF-8") from None
        elif number == 2 and wire == 5:
            score = _F32.unpack(value)[0]
        elif number == 3 and wire == 0:
            kind = value
    if not piece:
        raise ModelError("a piece without text")
    return piece, score, kind


def _flags(message, wanted):
    """{name: int} of the varint fields numbered in `wanted` ({number: name})."""
    found = {}
    for number, wire, value in fields(message):
        if number in wanted and wire == 0:
            found[wanted[number]] = value
    return found


# ModelProto: 1 pieces, 2 trainer_spec, 3 normalizer_spec.
_TRAINER = {3: "model_type", 24: "treat_whitespace_as_suffix", 35: "byte_fallback"}
_NORMALIZER = {3: "add_dummy_prefix", 4: "remove_extra_whitespaces", 5: "escape_whitespaces"}


def read_model(data):
    """([(piece, score, type)], trainer {name: value}, normalizer {name:
    value}) from the bytes of a sentencepiece model."""
    if not isinstance(data, (bytes, bytearray)) or not data or len(data) > MAX_MODEL_BYTES:
        raise ModelError("not a sentencepiece model")
    data = bytes(data)
    pieces, trainer, normalizer = [], {}, {}
    for number, wire, value in fields(data):
        if wire != 2:
            continue
        if number == 1:
            pieces.append(_piece(value))
        elif number == 2:
            trainer = _flags(value, _TRAINER)
        elif number == 3:
            normalizer = _flags(value, _NORMALIZER)
    if not pieces:
        raise ModelError("no pieces")
    return pieces, trainer, normalizer


# ------------------------------------------------------------
# Encoding
# ------------------------------------------------------------

class UnigramModel:
    """A sentencepiece unigram model: encode(text) -> its pieces."""

    def __init__(self, pieces, trainer=None, normalizer=None):
        trainer = trainer or {}
        normalizer = normalizer or {}
        if trainer.get("model_type", UNIGRAM) != UNIGRAM:
            raise ModelError("not a unigram sentencepiece model")
        if trainer.get("treat_whitespace_as_suffix"):
            raise ModelError("whitespace as a suffix is not supported")
        self.add_dummy_prefix = bool(normalizer.get("add_dummy_prefix", 1))
        self.pieces = {}          # piece -> id (NORMAL, USER_DEFINED and UNUSED, as sentencepiece)
        self.scores = []
        self.types = []
        self.unk_id = None
        normal_scores = []
        for index, (piece, score, kind) in enumerate(pieces):
            self.scores.append(f32(score))
            self.types.append(kind)
            if kind in (NORMAL, USER_DEFINED, UNUSED):
                self.pieces.setdefault(piece, index)
            if kind == UNKNOWN and self.unk_id is None:
                self.unk_id = index
            if kind == NORMAL:
                normal_scores.append(f32(score))
        if self.unk_id is None or not normal_scores:
            raise ModelError("no <unk> or no pieces")
        self.min_score = min(normal_scores)
        self.max_score = max([FLT_MIN] + normal_scores)      # sentencepiece starts at FLT_MIN
        self.unk_score = f32(self.min_score - UNK_PENALTY)
        self.max_length = max(len(p) for p in self.pieces)
        self.vocabulary = frozenset(p for p, i in self.pieces.items() if self.types[i] == NORMAL)

    @classmethod
    def from_bytes(cls, data):
        return cls(*read_model(data))

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            data = f.read(MAX_MODEL_BYTES + 1)
        return cls.from_bytes(data)

    def normalized(self, text):
        """The text as sentencepiece sees it: words joined by "▁", with one
        in front."""
        words = str(text or "").split()
        if not words:
            return ""
        joined = WHITESPACE.join(words)
        return WHITESPACE + joined if self.add_dummy_prefix else joined

    def encode(self, text):
        """The pieces of `text` (plain words; see the module notes). A run of
        characters the model doesn't know stays one piece, which known()
        tells apart."""
        text = self.normalized(text)[:MAX_TEXT_CHARS]
        size = len(text)
        if not size:
            return []
        # best[end] = (score of the best path ending there; where its last
        # piece starts; its id). Sums are float32, as in sentencepiece, and a
        # later candidate replaces an earlier one only when it is higher: two
        # equal cuts ("F FF" and "FF F") keep the one whose last piece starts
        # first.
        best = [(0.0, -1, -1)] + [None] * size
        for start in range(size):
            here = best[start]
            if here is None:
                continue
            till_here = here[0]
            single = False
            for end in range(start + 1, min(size, start + self.max_length) + 1):
                piece = text[start:end]
                index = self.pieces.get(piece)
                if index is None or self.types[index] == UNUSED:
                    continue
                if self.types[index] == USER_DEFINED:     # always chosen
                    score = f32(f32(len(piece.encode("utf-8")) * self.max_score) - 0.1)
                else:
                    score = self.scores[index]
                candidate = f32(score + till_here)
                target = best[end]
                if target is None or candidate > target[0]:
                    best[end] = (candidate, start, index)
                if end - start == 1:
                    single = True
            if not single:
                candidate = f32(self.unk_score + till_here)
                target = best[start + 1]
                if target is None or candidate > target[0]:
                    best[start + 1] = (candidate, start, self.unk_id)
        found = []
        end = size
        while end > 0:
            _score, start, index = best[end]
            found.append((text[start:end], index))
            end = start
        found.reverse()
        out = []
        previous_unknown = False
        for piece, index in found:
            unknown = index == self.unk_id
            if unknown and previous_unknown:
                out[-1] += piece          # sentencepiece merges a run of unknown pieces
            else:
                out.append(piece)
            previous_unknown = unknown
        return out

    def known(self, piece):
        """Whether `piece` is a token of the model (not an unknown character)."""
        return piece in self.vocabulary
