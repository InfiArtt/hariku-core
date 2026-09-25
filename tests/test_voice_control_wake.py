# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Voice Control's wake phrase without sherpa-onnx, a microphone or a network:
# the tokenizer against sentencepiece's own answers (recorded in
# voice_control_bpe_oracle.json, so sentencepiece isn't needed here), the
# keyword lines, the ctypes structures and a fake sherpa-onnx DLL, the
# downloads and the tar.bz2 unpacking with made-up archives, the listener's
# pausing rules with a fake microphone and a fake spotter, the test on the
# Preferences page, and the path from "heard it" to Aruna listening.
# Nothing is recorded, played or spoken; every test uses a temporary folder.

import array
import bz2
import ctypes
import hashlib
import io
import json
import math
import os
import struct
import sys
import tarfile
import threading
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VC_DIR = os.path.join(ROOT, "extensions", "voice_control")
if VC_DIR not in sys.path:
    sys.path.insert(0, VC_DIR)

import voice_control_audio as audio        # noqa: E402
import voice_control_bpe as bpe            # noqa: E402
import voice_control_download as dl        # noqa: E402
import voice_control_kws as kws            # noqa: E402
import voice_control_store as store        # noqa: E402
import voice_control_text as text          # noqa: E402
import voice_control_wake as wake          # noqa: E402

from tests.test_voice_control import (  # noqa: E402,F401
    Server, make_listener, no_network, userdata, vc, wait_until)

RATE = 16000
ORACLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "voice_control_bpe_oracle.json")


# ------------------------------------------------------------
# The tokenizer, against sentencepiece's recorded answers
# ------------------------------------------------------------

def _varint(n):
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(number, wire, payload):
    key = _varint(number << 3 | wire)
    if wire == 0:
        return key + _varint(payload)
    if wire == 2:
        return key + _varint(len(payload)) + payload
    return key + payload          # fixed32 / fixed64 bytes


def model_proto(pieces, model_type=1, add_dummy_prefix=None):
    """A sentencepiece ModelProto as bytes, written the way protobuf does."""
    data = b""
    for piece, score, kind in pieces:
        message = _field(1, 2, piece.encode("utf-8")) + _field(2, 5, struct.pack("<f", score))
        if kind != bpe.NORMAL:                 # NORMAL is the default, left out
            message += _field(3, 0, kind)
        data += _field(1, 2, message)
    trainer = _field(2, 2, b"unigram_500") + _field(3, 0, model_type) + _field(4, 0, len(pieces))
    data += _field(2, 2, trainer)
    normalizer = _field(1, 2, b"nmt_nfkc") + _field(2, 2, b"\x00\x01charsmap")
    if add_dummy_prefix is not None:
        normalizer += _field(3, 0, int(add_dummy_prefix))
    data += _field(3, 2, normalizer)
    return data


@pytest.fixture(scope="module")
def oracle():
    with open(ORACLE_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def tokenizer(oracle):
    return bpe.UnigramModel.from_bytes(model_proto(oracle["pieces"]))


class TestTokenizer:
    def test_the_model_is_read_from_its_protobuf(self, oracle):
        pieces, trainer, normalizer = bpe.read_model(model_proto(oracle["pieces"]))
        assert len(pieces) == len(oracle["pieces"]) == 500
        for (piece, score, kind), (want_piece, want_score, want_kind) in zip(pieces,
                                                                             oracle["pieces"]):
            assert (piece, kind) == (want_piece, want_kind)
            assert score == bpe.f32(want_score)
        assert trainer == {"model_type": bpe.UNIGRAM}
        assert normalizer == {}

    def test_every_recorded_phrase_matches_sentencepiece(self, oracle, tokenizer):
        encodings = oracle["encodings"]
        assert len(encodings) > 400
        wrong = {t: (tokenizer.encode(t), want) for t, want in encodings.items()
                 if tokenizer.encode(t) != want}
        assert not wrong, list(wrong.items())[:5]

    @pytest.mark.parametrize("phrase, pieces", [
        ("HEY ARUNA", "▁HE Y ▁A RU N A"),
        ("HI PRINCESS", "▁HI ▁P RI N CE S S"),
        ("HEY JARVIS", "▁HE Y ▁JA R VI S"),
        ("MERRY CHRISTMAS", "▁ME R RY ▁ CH R IST MA S"),     # the model's own keywords.txt
        ("HAPPY NEW YEAR", "▁HA PP Y ▁NEW ▁YEAR"),
        ("HEI ARUNA", "▁HE I ▁A RU N A"),
        ("  HEY   ARUNA  ", "▁HE Y ▁A RU N A"),
    ])
    def test_known_phrases(self, tokenizer, phrase, pieces):
        assert " ".join(tokenizer.encode(phrase)) == pieces

    def test_names_and_indonesian_words(self, oracle, tokenizer):
        for phrase in ("HARIKU", "SELAMAT PAGI", "RAFLI", "TERIMA KASIH", "TWENTY ONE",
                       "DON'T STOP", "HEY-ARUNA"):
            assert tokenizer.encode(phrase) == oracle["encodings"][phrase]

    def test_characters_the_model_lacks_stay_unknown_pieces(self, tokenizer):
        assert tokenizer.encode("HEY 22 7X") == ["▁HE", "Y", "▁", "22", "▁", "7", "X"]
        assert not tokenizer.known("22") and tokenizer.known("▁HE")
        assert tokenizer.encode("") == [] and tokenizer.encode("   ") == []

    def test_equal_cuts_keep_the_one_sentencepiece_keeps(self, oracle, tokenizer):
        # "FFF" is "F FF" or "FF F" at the same score; sentencepiece keeps the
        # cut whose last piece starts first.
        text_ = "QAOT VIABFFFXZEG IYAFA"
        assert tokenizer.encode(text_) == oracle["encodings"][text_]
        assert "F FF" in " ".join(tokenizer.encode(text_))

    def test_bad_models_are_refused(self, oracle):
        with pytest.raises(bpe.ModelError):
            bpe.read_model(b"")
        with pytest.raises(bpe.ModelError):
            bpe.read_model(b"\x0a\xff")                       # a field longer than the data
        with pytest.raises(bpe.ModelError):
            bpe.read_model(b"\x0b")                           # wire type 3 (a group)
        with pytest.raises(bpe.ModelError):
            bpe.UnigramModel.from_bytes(model_proto(oracle["pieces"], model_type=bpe.BPE))
        with pytest.raises(bpe.ModelError):
            bpe.UnigramModel.from_bytes(model_proto([["A", -1.0, bpe.NORMAL]]))    # no <unk>

    def test_without_the_dummy_prefix(self, oracle):
        model = bpe.UnigramModel.from_bytes(model_proto(oracle["pieces"], add_dummy_prefix=False))
        assert model.encode("HEY ARUNA")[0] != "▁HE"

    def test_the_real_model_when_there_is_one(self, oracle):
        # Set HARIKU_KWS_MODEL_DIR to the unpacked keyword model to check the
        # real bpe.model too (its SHA-256 is pinned in the downloads).
        folder = os.environ.get("HARIKU_KWS_MODEL_DIR")
        if not folder or not os.path.isfile(os.path.join(folder, "bpe.model")):
            pytest.skip("no keyword model here")
        model = bpe.UnigramModel.load(os.path.join(folder, "bpe.model"))
        assert all(model.encode(t) == want for t, want in oracle["encodings"].items())


# ------------------------------------------------------------
# The phrase
# ------------------------------------------------------------

TOKENS = None


@pytest.fixture(scope="module")
def tokens(oracle):
    return {piece for piece, _score, kind in oracle["pieces"] if kind == bpe.NORMAL} | {
        "<blk>", "<sos/eos>", "<unk>"}


class TestPhrase:
    @pytest.mark.parametrize("typed, words, unsupported", [
        ("Hey Aruna", ["HEY", "ARUNA"], []),
        ("  hey,   Aruna!  ", ["HEY", "ARUNA"], []),
        ("Hé Arúna", ["HE", "ARUNA"], []),
        ("don’t stop", ["DON'T", "STOP"], []),
        ("hey-aruna", ["HEY-ARUNA"], []),
        ("'quoted' -dash-", ["QUOTED", "DASH"], []),
        ("Hey Hariku 2", ["HEY", "HARIKU"], ["2"]),
        ("Привет", [], list("ПРИВЕТ")),
        ("", [], []),
    ])
    def test_clean_phrase(self, typed, words, unsupported):
        assert wake.clean_phrase(typed) == (words, unsupported)

    @pytest.mark.parametrize("typed, problem", [
        ("Hey Aruna", None), ("Hi Princess", None), ("Selamat pagi Aruna", None),
        ("", "empty"), ("   ", "empty"), ("Hey Aruna 2", "digits"), ("Hey Ärüna", None),
        ("Hey 你好", "unsupported"), ("Hello", "common"), ("Good morning", "common"),
        ("okay", "common"), ("selamat pagi", "common"), ("Aruna", "one_word"),
        ("Jarvis", "one_word"), ("Hi Bob", "short"), ("Yo Al", "short"),
        ("Hey there my lovely little Aruna", "long"),
        ("Supercalifragilistic expialidocious", "long"),
    ])
    def test_phrase_problem(self, typed, problem):
        assert wake.phrase_problem(typed) == problem

    def test_usable(self):
        assert wake.usable("Hey Aruna") and wake.usable("Aruna") and wake.usable("hello")
        assert not wake.usable("") and not wake.usable("Hey 2") and not wake.usable("!!!")

    def test_tidy(self):
        assert wake.tidy("  Hey    Aruna ") == "Hey Aruna"
        assert len(wake.tidy("x" * 100)) == wake.MAX_PHRASE_CHARS
        assert wake.tidy(None) == ""

    def test_the_keyword_lines(self, tokenizer, tokens):
        threshold, score, _paths = wake.SENSITIVITY["normal"]
        assert wake.keywords_text("Hey Aruna", tokenizer, tokens) == \
            f"▁HE Y ▁A RU N A :{score:g} #{threshold:g} @HEY_ARUNA"
        high = wake.keywords_text("hi princess", tokenizer, tokens, "high")
        threshold, score, _paths = wake.SENSITIVITY["high"]
        assert high == f"▁HI ▁P RI N CE S S :{score:g} #{threshold:g} @HI_PRINCESS"
        assert wake.keywords_text("x", tokenizer, tokens, "nonsense").endswith(
            f"#{wake.SENSITIVITY['normal'][0]:g} @X")

    def test_indonesian_spellings_add_the_english_ones(self, tokenizer, tokens):
        lines = wake.keywords_text("Hei Aruna", tokenizer, tokens).split("\n")
        assert [line.split(" :")[0] for line in lines] == ["▁HE I ▁A RU N A",
                                                          "▁HE Y ▁A RU N A"]
        assert all(line.endswith("@HEI_ARUNA") for line in lines)
        assert wake.spellings(["HAI", "HALO"]) == [["HAI", "HALO"], ["HI", "HALO"],
                                                   ["HAI", "HELLO"], ["HI", "HELLO"]]

    def test_phrases_the_model_cant_hear_are_refused(self, tokenizer, tokens):
        for phrase in ("", "Hey 2", "!!!"):
            with pytest.raises(ValueError):
                wake.keywords_text(phrase, tokenizer, tokens)
        with pytest.raises(ValueError):          # a piece tokens.txt doesn't have
            wake.keywords_text("Hey Aruna", tokenizer, tokens - {"RU"})

    def test_every_line_passes_sherpa_onnxs_own_check(self, tokenizer, tokens, oracle):
        for phrase in list(oracle["encodings"])[:200]:
            if wake.usable(phrase):
                kws.check_keywords(wake.keywords_text(phrase, tokenizer, tokens), tokens)

    def test_sensitivities(self):
        assert wake.SENSITIVITIES == ("low", "normal", "high")
        thresholds = [wake.SENSITIVITY[n][0] for n in wake.SENSITIVITIES]
        scores = [wake.SENSITIVITY[n][1] for n in wake.SENSITIVITIES]
        paths = [wake.SENSITIVITY[n][2] for n in wake.SENSITIVITIES]
        assert thresholds == sorted(thresholds, reverse=True)      # lower hears more
        assert scores == sorted(scores) and paths == sorted(paths)
        assert all(0 < t < 1 for t in thresholds) and all(1 <= p <= 32 for p in paths)
        assert wake.sensitivity_values("unknown") == wake.SENSITIVITY["normal"]


# ------------------------------------------------------------
# sherpa-onnx's C API, with a fake DLL
# ------------------------------------------------------------

class TestStructures:
    """c-api.h of v1.13.8, laid out as a 64-bit Windows compiler does."""

    def test_the_keyword_spotter_config(self):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            pytest.skip("64-bit layout")
        assert ctypes.sizeof(kws.OnlineTransducerModelConfig) == 24
        assert ctypes.sizeof(kws.OnlineModelConfig) == 136
        model = kws.OnlineModelConfig
        assert [(name, getattr(model, name).offset) for name in (
            "transducer", "paraformer", "zipformer2_ctc", "tokens", "num_threads", "provider",
            "debug", "model_type", "modeling_unit", "bpe_vocab", "tokens_buf",
            "tokens_buf_size", "nemo_ctc", "t_one_ctc")] == [
            ("transducer", 0), ("paraformer", 24), ("zipformer2_ctc", 40), ("tokens", 48),
            ("num_threads", 56), ("provider", 64), ("debug", 72), ("model_type", 80),
            ("modeling_unit", 88), ("bpe_vocab", 96), ("tokens_buf", 104),
            ("tokens_buf_size", 112), ("nemo_ctc", 120), ("t_one_ctc", 128)]
        config = kws.KeywordSpotterConfig
        assert [(name, getattr(config, name).offset) for name in (
            "feat_config", "model_config", "max_active_paths", "num_trailing_blanks",
            "keywords_score", "keywords_threshold", "keywords_file", "keywords_buf",
            "keywords_buf_size")] == [
            ("feat_config", 0), ("model_config", 8), ("max_active_paths", 144),
            ("num_trailing_blanks", 148), ("keywords_score", 152),
            ("keywords_threshold", 156), ("keywords_file", 160), ("keywords_buf", 168),
            ("keywords_buf_size", 176)]
        assert ctypes.sizeof(config) == 184

    def test_the_keyword_result(self):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            pytest.skip("64-bit layout")
        result = kws.KeywordResult
        assert [(name, getattr(result, name).offset) for name in (
            "keyword", "tokens", "tokens_arr", "count", "timestamps", "start_time", "json")] == [
            ("keyword", 0), ("tokens", 8), ("tokens_arr", 16), ("count", 24),
            ("timestamps", 32), ("start_time", 40), ("json", 48)]
        assert ctypes.sizeof(result) == 56


class FakeFunction:
    def __init__(self, fn):
        self.fn = fn
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.fn(*args)


class FakeSherpa:
    """The C API: a spotter "hears" the keyword when a chunk's first sample
    is 0.5; `configs` keeps what was passed to the create call."""

    def __init__(self, version=b"1.13.8", fail_create=False):
        self.version = version
        self.fail_create = fail_create
        self.configs = []
        self.calls = []
        self.results = []
        self.streams = {}
        self._next = 100
        names = ("SherpaOnnxGetVersionStr", "SherpaOnnxCreateKeywordSpotter",
                 "SherpaOnnxDestroyKeywordSpotter", "SherpaOnnxCreateKeywordStream",
                 "SherpaOnnxDestroyOnlineStream", "SherpaOnnxOnlineStreamAcceptWaveform",
                 "SherpaOnnxOnlineStreamInputFinished", "SherpaOnnxIsKeywordStreamReady",
                 "SherpaOnnxDecodeKeywordStream", "SherpaOnnxResetKeywordStream",
                 "SherpaOnnxGetKeywordResult", "SherpaOnnxDestroyKeywordResult")
        for name in names:
            setattr(self, name, FakeFunction(getattr(self, "_" + name[len("SherpaOnnx"):])))

    def _GetVersionStr(self):
        return self.version

    def _CreateKeywordSpotter(self, pconfig):
        config = pconfig._obj
        model = config.model_config
        self.configs.append({
            "sample_rate": config.feat_config.sample_rate,
            "feature_dim": config.feat_config.feature_dim,
            "encoder": model.transducer.encoder, "decoder": model.transducer.decoder,
            "joiner": model.transducer.joiner, "tokens": model.tokens,
            "threads": model.num_threads, "provider": model.provider,
            "paths": config.max_active_paths, "blanks": config.num_trailing_blanks,
            "score": config.keywords_score, "threshold": config.keywords_threshold,
            "file": config.keywords_file,
            "keywords": ctypes.string_at(config.keywords_buf, config.keywords_buf_size)})
        self.calls.append("create")
        return None if self.fail_create else 1

    def _DestroyKeywordSpotter(self, spotter):
        self.calls.append("destroy_spotter")

    def _CreateKeywordStream(self, spotter):
        self._next += 1
        self.streams[self._next] = {"pending": [], "ready": 0}
        self.calls.append("stream")
        return self._next

    def _DestroyOnlineStream(self, stream):
        self.calls.append("destroy_stream")
        self.streams.pop(stream, None)

    def _OnlineStreamAcceptWaveform(self, stream, rate, samples, n):
        assert rate == 16000
        first = samples[0] if n else 0.0
        self.streams[stream]["pending"].append(abs(first - 0.5) < 1e-6)
        self.streams[stream]["ready"] += 1

    def _OnlineStreamInputFinished(self, stream):
        self.calls.append("finished")

    def _IsKeywordStreamReady(self, spotter, stream):
        return 1 if self.streams[stream]["ready"] else 0

    def _DecodeKeywordStream(self, spotter, stream):
        self.streams[stream]["ready"] -= 1

    def _GetKeywordResult(self, spotter, stream):
        heard = self.streams[stream]["pending"].pop(0)
        result = kws.KeywordResult()
        result.keyword = b"HEY_ARUNA" if heard else b""
        self.results.append(result)
        return ctypes.pointer(result)

    def _DestroyKeywordResult(self, result):
        self.calls.append("destroy_result")

    def _ResetKeywordStream(self, spotter, stream):
        self.calls.append("reset")


@pytest.fixture
def model_files(tmp_path, tokens):
    files = {}
    for key in ("encoder", "decoder", "joiner"):
        path = tmp_path / f"{key}.int8.onnx"
        path.write_bytes(b"onnx")
        files[key] = str(path)
    path = tmp_path / "tokens.txt"
    path.write_text("".join(f"{t} {i}\n" for i, t in enumerate(sorted(tokens))), encoding="utf-8")
    files["tokens"] = str(path)
    return files


class TestSpotter:
    def test_a_spotter_hears_and_starts_over(self, model_files):
        fake = FakeSherpa()
        spotter = kws.Spotter("runtime", model_files, "▁HE Y ▁A RU N A :1 #0.25 @HEY_ARUNA",
                              threshold=0.25, score=1.0, dll=fake)
        config = fake.configs[0]
        assert config["keywords"] == "▁HE Y ▁A RU N A :1 #0.25 @HEY_ARUNA".encode("utf-8")
        assert (config["sample_rate"], config["feature_dim"], config["threads"],
                config["provider"], config["paths"], config["blanks"]) == (
            16000, 80, 1, b"cpu", 4, 1)
        assert config["threshold"] == pytest.approx(0.25) and config["score"] == 1.0
        assert config["file"] is None
        assert config["encoder"] == model_files["encoder"].encode("ascii")
        assert spotter.accept(array.array("f", [0.1] * 1600)) == []
        assert spotter.accept(array.array("f", [0.5] + [0.0] * 1599)) == ["HEY_ARUNA"]
        assert fake.calls.count("reset") == 1              # it starts over after hearing it
        assert fake.calls.count("destroy_result") == 2     # every result is freed
        spotter.new_stream()
        assert fake.calls.count("destroy_stream") == 1 and fake.calls.count("stream") == 2
        assert spotter.finish() == [] and "finished" in fake.calls
        spotter.close()
        assert fake.calls[-2:] == ["destroy_stream", "destroy_spotter"]
        assert spotter.closed and spotter.accept([0.5]) == []
        spotter.close()                                    # twice is fine

    def test_unknown_tokens_never_reach_sherpa_onnx(self, model_files):
        # sherpa-onnx would end Hariku (exit(-1)) over a token it doesn't have.
        for bad in ("▁HE Y ▁ZZZ @X", "", "\n", ":1 #0.2 @X", "▁HE Y #zero @X",
                    "▁HE Y #0 @X", "▁HE Y :500 @X", "▁HE Y ▁A\n\n▁HE Y @X", "▁HE Y @"):
            fake = FakeSherpa()
            with pytest.raises(kws.KwsError) as error:
                kws.Spotter("runtime", model_files, bad, dll=fake)
            assert error.value.kind == "keywords" and fake.calls == [], bad

    def test_missing_files_and_a_failed_create(self, model_files):
        with pytest.raises(kws.KwsError) as error:
            kws.Spotter("runtime", dict(model_files, joiner="nowhere"), "▁HE Y @X",
                        dll=FakeSherpa())
        assert error.value.kind == "missing"
        with pytest.raises(kws.KwsError) as error:
            kws.Spotter("runtime", model_files, "▁HE Y @X", dll=FakeSherpa(fail_create=True))
        assert error.value.kind == "create"

    def test_loading_checks_the_files_the_order_and_the_version(self, tmp_path, monkeypatch):
        monkeypatch.setattr(kws, "_loaded", {})
        folder = tmp_path / "runtime"
        folder.mkdir()
        with pytest.raises(kws.KwsError) as error:
            kws.load(str(folder), cdll=lambda path: pytest.fail("loaded without the files"))
        assert error.value.kind == "missing"
        for name in kws.RUNTIME_FILES:
            (folder / name).write_bytes(b"MZ")
        loaded = []

        def cdll(path):
            loaded.append(os.path.basename(path))
            return FakeSherpa()

        dll = kws.load(str(folder), cdll=cdll)
        assert loaded == ["onnxruntime.dll", "sherpa-onnx-c-api.dll"]     # ours first
        assert dll.SherpaOnnxGetKeywordResult.restype is not None
        assert kws.load(str(folder), cdll=cdll) is dll and len(loaded) == 2      # once
        monkeypatch.setattr(kws, "_loaded", {})
        with pytest.raises(kws.KwsError) as error:
            kws.load(str(folder), cdll=lambda path: FakeSherpa(version=b"1.12.0"))
        assert error.value.kind == "version" and error.value.detail == "1.12.0"

    def test_dlls_that_dont_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(kws, "_loaded", {})
        for name in kws.RUNTIME_FILES:
            (tmp_path / name).write_bytes(b"MZ")

        def cdll(path):
            raise OSError("[WinError 193] %1 is not a valid Win32 application")

        with pytest.raises(kws.KwsError) as error:
            kws.load(str(tmp_path), cdll=cdll)
        assert error.value.kind == "load" and "193" in error.value.detail
        assert text.wake_engine_error(error.value) == text._("wake_err_damaged")
        assert str(tmp_path) not in kws._loaded

    def test_native_paths(self):
        assert kws.native_path(r"C:\Users\Rafli\x.onnx") == rb"C:\Users\Rafli\x.onnx"
        path = "C:\\Users\\Jos\u00e9\\x.onnx"
        assert kws.native_path(path, short_path=lambda p: r"C:\Users\JOSE~1\x.onnx") == \
            rb"C:\Users\JOSE~1\x.onnx"
        if sys.platform == "win32":
            chinese = "C:\\Users\\\u738b\u5c0f\u660e\\x.onnx"
            try:
                chinese.encode("mbcs", "strict")
            except UnicodeEncodeError:
                with pytest.raises(kws.KwsError) as error:
                    kws.native_path(chinese, short_path=lambda p: None)
                assert error.value.kind == "path"

    def test_float_samples(self):
        pcm = array.array("h", [0, 16384, -32768, 32767]).tobytes() + b"\x01"
        assert list(kws.pcm_to_float(pcm)) == pytest.approx([0.0, 0.5, -1.0, 32767 / 32768])

    def test_reading_tokens(self, tmp_path):
        path = tmp_path / "tokens.txt"
        path.write_text("<blk> 0\n▁HE 1\nY 2\nbroken line here\n\n", encoding="utf-8")
        assert kws.read_tokens(str(path)) == {"<blk>", "▁HE", "Y"}


# ------------------------------------------------------------
# Sound in, detections out: the gate, the speech watch, the ear
# ------------------------------------------------------------

def chunk(level=0.0, ms=100, first=None, seed=0):
    """100 ms of 16-bit samples as bytes: a 220 Hz tone with an RMS of
    `level` (0: silence); `first` replaces the first sample."""
    n = RATE * ms // 1000
    samples = [int(level * math.sqrt(2) * math.sin(2 * math.pi * 220 * i / RATE + seed))
               for i in range(n)]
    if first is not None:
        samples[0] = first
    return array.array("h", samples).tobytes()


QUIET = chunk(10)
LOUD = chunk(3000)
TRIGGER = chunk(3000, first=16384)        # the fake spotter "hears" the phrase in this one


def samples(data):
    out = array.array("h")
    out.frombytes(data)
    return out


class FakeSpotter:
    """Hears the phrase in a chunk whose first sample is 0.5."""

    def __init__(self, name="HEY_ARUNA"):
        self.name = name
        self.streams = 0
        self.chunks = 0
        self.closed = False

    def new_stream(self):
        self.streams += 1

    def accept(self, floats):
        self.chunks += 1
        return [self.name] if len(floats) and abs(floats[0] - 0.5) < 1e-6 else []

    def close(self):
        self.closed = True


class TestGate:
    def test_a_quiet_room_reaches_nothing(self):
        gate = wake.ActivityGate()
        for _ in range(50):
            assert gate.feed(samples(QUIET)) == (False, [])
        assert gate.room == pytest.approx(10, rel=0.1)

    def test_sound_brings_the_moment_before_and_after(self):
        gate = wake.ActivityGate(preroll=3, hangover=2)
        for _ in range(10):
            gate.feed(samples(QUIET))
        started, chunks = gate.feed(samples(LOUD))
        assert started and len(chunks) == 4               # three quiet ones before it
        assert gate.feed(samples(LOUD)) == (False, [samples(LOUD)])
        assert gate.feed(samples(QUIET))[1] and gate.feed(samples(QUIET))[1]   # the hangover
        assert gate.feed(samples(QUIET)) == (False, [])
        assert gate.feed(samples(LOUD))[0]                # a new stretch of sound

    def test_a_steady_noise_becomes_the_room(self):
        # A fan switched on: loud at first, then, after ten seconds without a
        # quieter moment (speech has them), it is the room and costs nothing.
        gate = wake.ActivityGate()
        fan = samples(chunk(60))
        gate.feed(samples(QUIET))
        passed = [len(gate.feed(fan)[1]) for _ in range(300)]
        assert sum(passed[:100]) >= 100
        assert sum(passed[150:]) == 0 and not gate.active
        assert gate.room == pytest.approx(60, rel=0.1)
        assert gate.feed(samples(chunk(3000)))[0]            # a voice over the fan still counts

    def test_speech_with_pauses_doesnt_become_the_room(self):
        gate = wake.ActivityGate()
        gate.feed(samples(QUIET))
        for _ in range(30):                                    # a minute of talking, with pauses
            for _i in range(4):
                gate.feed(samples(chunk(2000)))
            gate.feed(samples(QUIET))
        assert gate.room < 40

    def test_chunk_level(self):
        assert wake.chunk_level(array.array("h")) == 0.0
        assert wake.chunk_level(samples(chunk(1000))) == pytest.approx(1000, rel=0.05)
        clicky = array.array("h", [0] * 1000 + [8000] * 600)
        assert wake.chunk_level(clicky) > 4000            # the loud part counts


class TestSpeechWatch:
    def test_what_hariku_says_is_not_heard(self):
        now = [100.0]
        watch = wake.SpeechWatch(clock=lambda: now[0])
        assert not watch.speaking()
        watch.on_before_speak({"text": "Hey Aruna is listening now.", "interrupt": True})
        assert watch.speaking()
        now[0] += wake.speech_seconds("Hey Aruna is listening now.") + 0.5
        assert watch.speaking()                           # the microphone's buffers
        now[0] += wake.AFTER_SPEECH_SECONDS
        assert not watch.speaking()
        for payload in ({"text": ""}, {"text": None}, "text", None, {}):
            watch.on_before_speak(payload)
        assert not watch.speaking()

    def test_hariku_voice_speaking(self):
        now = [0.0]
        speaking = [True]
        watch = wake.SpeechWatch(voice_speaking=lambda: speaking[0], clock=lambda: now[0])
        assert watch.speaking()
        speaking[0] = False
        assert watch.speaking()                            # just after it stops, still
        now[0] += wake.AFTER_SPEECH_SECONDS + 0.01
        assert not watch.speaking()

    def test_long_texts_are_capped(self):
        assert wake.speech_seconds("x" * 100000) == wake.READER_MAX_SECONDS
        assert wake.speech_seconds("") == wake.READER_SECONDS

    def test_interrupting_text_replaces_what_was_being_said(self):
        # The screen reader stops a long answer for new text said with
        # interrupt, so only that text is left: the wake phrase test's
        # instructions after the microphone test's long result, for one.
        now = [0.0]
        watch = wake.SpeechWatch(clock=lambda: now[0])
        long_text, short_text = "x" * 300, "Say it."
        watch.on_before_speak({"text": long_text, "interrupt": True})
        now[0] += 1.0
        watch.on_before_speak({"text": short_text, "interrupt": True})
        now[0] += wake.speech_seconds(short_text) + wake.AFTER_SPEECH_SECONDS
        assert not watch.speaking()

    def test_text_without_interrupt_waits_its_turn(self):
        now = [0.0]
        watch = wake.SpeechWatch(clock=lambda: now[0])
        first, second = "x" * 100, "y" * 50
        watch.on_before_speak({"text": first, "interrupt": True})
        watch.on_before_speak({"text": second, "interrupt": False})
        now[0] += wake.speech_seconds(first) + wake.speech_seconds(second) - 0.1
        assert watch.speaking()
        now[0] += 0.1 + wake.AFTER_SPEECH_SECONDS
        assert not watch.speaking()

    def test_with_interrupt_speech_off_everything_waits_its_turn(self):
        now = [0.0]
        watch = wake.SpeechWatch(clock=lambda: now[0], interrupts=lambda: False)
        watch.on_before_speak({"text": "x" * 300, "interrupt": True})
        watch.on_before_speak({"text": "Say it.", "interrupt": True})
        now[0] += wake.speech_seconds("x" * 300)
        assert watch.speaking()


class TestEar:
    def test_hearing_the_phrase(self):
        now = [0.0]
        spotter = FakeSpotter()
        ear = wake.Ear(spotter, clock=lambda: now[0])
        for _ in range(10):
            assert ear.hear(QUIET) == []
        assert spotter.chunks == 0                        # the quiet never reached it
        assert ear.hear(TRIGGER) == ["HEY_ARUNA"]
        assert spotter.streams == 2                       # a fresh stream for the sound
        assert ear.hear(TRIGGER) == []                    # one phrase, one detection
        now[0] += wake.COOLDOWN_SECONDS
        assert ear.hear(TRIGGER) == ["HEY_ARUNA"]

    def test_nothing_is_heard_while_hariku_speaks(self):
        speaking = [True]
        spotter = FakeSpotter()
        ear = wake.Ear(spotter, speaking=lambda: speaking[0])
        assert ear.hear(TRIGGER) == [] and spotter.chunks == 0
        speaking[0] = False
        streams = spotter.streams
        assert ear.hear(TRIGGER) == ["HEY_ARUNA"] and spotter.streams == streams + 1


# ------------------------------------------------------------
# The listener's rules
# ------------------------------------------------------------

class FakeMic:
    """A microphone: the scripted chunks, then quiet every few ms until
    on_chunk says stop or `stop` is set. Keeps nothing."""

    def __init__(self, script, log):
        self.script = list(script)
        self.log = log

    def record(self, on_chunk, stop=None, max_seconds=30.0, keep=True):
        assert keep is False, "the wake phrase must not keep audio"
        self.log.opened += 1
        try:
            end = time.monotonic() + max_seconds
            while time.monotonic() < end:
                if stop is not None and stop.is_set():
                    return b""
                piece = self.script.pop(0) if self.script else QUIET
                self.log.chunks += 1
                if on_chunk(piece):
                    return b""
                time.sleep(0.003)
            return b""
        finally:
            self.log.closed += 1


@pytest.fixture
def fast(monkeypatch):
    for name, value in (("IDLE_SECONDS", 0.01), ("RETRY_SECONDS", 0.05),
                        ("BLOCKED_CHECK_SECONDS", 0.02), ("HANDOVER_SECONDS", 0.3),
                        ("AFTER_COMMAND_SECONDS", 0.05), ("QUIET_CHECK_SECONDS", 0.0),
                        ("CAPTURE_SECONDS", 30.0)):
        monkeypatch.setattr(wake, name, value)


@pytest.fixture
def make(fast):
    made = []

    def make_listener(script=(), fail=None, mic_error=None, **options):
        log = types.SimpleNamespace(detected=[], states=[], problems=[], spotters=[],
                                    opened=0, closed=0, chunks=0, scripts=[list(script)])

        def make_spotter(phrase, sensitivity):
            if fail is not None:
                raise fail
            spotter = FakeSpotter()
            spotter.phrase, spotter.sensitivity = phrase, sensitivity
            log.spotters.append(spotter)
            return spotter

        def make_recorder():
            if mic_error is not None:
                log.opened += 1
                raise audio.MicrophoneError(mic_error)
            return FakeMic(log.scripts.pop(0) if log.scripts else [], log)

        listener = wake.WakeListener(make_spotter, make_recorder, log.detected.append,
                                     on_state=log.states.append,
                                     on_problem=lambda kind, value: log.problems.append(
                                         (kind, value)), **options)
        made.append(listener)
        return listener, log

    yield make_listener
    for listener in made:
        listener.stop()


ON = wake.Config(enabled=True)


class TestWakeListener:
    def test_off_by_default_and_no_thread(self, make):
        listener, log = make()
        listener.configure(wake.Config())
        assert listener.state == wake.OFF and listener._thread is None and log.opened == 0

    def test_listening_and_hearing_the_phrase(self, make):
        listener, log = make([QUIET] * 5 + [TRIGGER])
        listener.configure(ON)
        assert wait_until(lambda: log.detected == ["HEY_ARUNA"])
        assert log.spotters[0].phrase == "Hey Aruna"
        assert log.spotters[0].sensitivity == "normal"
        # The bar takes the microphone: the listener lets go of it...
        assert wait_until(lambda: listener.state == wake.BUSY)
        assert log.closed == log.opened == 1
        # ...and listens again after a moment.
        assert wait_until(lambda: listener.state == wake.LISTENING and log.opened == 2)
        assert listener.detections == 1

    def test_not_downloaded(self, make):
        installed = [False]
        listener, log = make(installed=lambda: installed[0])
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.MISSING)
        assert log.opened == 0 and not log.spotters
        installed[0] = True
        listener.refresh()
        assert wait_until(lambda: listener.state == wake.LISTENING)

    def test_paused_by_the_user(self, make):
        listener, log = make()
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.LISTENING)
        listener.set_paused(True)
        assert wait_until(lambda: listener.state == wake.PAUSED)
        assert wait_until(lambda: log.closed == log.opened == 1)       # the microphone is closed
        listener.set_paused(False)
        assert wait_until(lambda: listener.state == wake.LISTENING and log.opened == 2)

    def test_while_voice_control_listens_to_a_command(self, make):
        busy = [False]
        listener, log = make(busy=lambda: busy[0])
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.LISTENING)
        busy[0] = True
        assert wait_until(lambda: listener.state == wake.BUSY and log.closed == 1)
        time.sleep(0.05)
        assert log.opened == 1
        busy[0] = False
        assert wait_until(lambda: listener.state == wake.LISTENING and log.opened == 2)

    def test_quiet_hours_only_when_asked(self, make):
        quiet = [True]
        listener, log = make(quiet_time=lambda: quiet[0])
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.LISTENING)   # not asked: listens
        listener.configure(wake.Config(enabled=True, quiet_hours=True))
        assert wait_until(lambda: listener.state == wake.QUIET)
        quiet[0] = False
        assert wait_until(lambda: listener.state == wake.LISTENING)

    def test_a_blocked_microphone_is_said_once(self, make):
        blocked = ["blocked_desktop"]
        listener, log = make(blocked=lambda: blocked[0])
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.BLOCKED)
        time.sleep(0.1)
        assert log.problems == [("blocked", "blocked_desktop")] and log.opened == 0
        blocked[0] = None
        assert wait_until(lambda: listener.state == wake.LISTENING)
        blocked[0] = "blocked_apps"            # blocked while listening
        assert wait_until(lambda: listener.state == wake.BLOCKED)
        assert log.problems[-1] == ("blocked", "blocked_apps")
        message = text.wake_problem(*log.problems[0])
        assert message.startswith("The wake phrase is paused.")
        assert "Let desktop apps access your microphone" in message

    def test_nothing_is_heard_while_hariku_speaks(self, make):
        speaking = [True]
        listener, log = make([TRIGGER] * 20, speaking=lambda: speaking[0])
        listener.configure(ON)
        assert wait_until(lambda: log.chunks >= 20)
        assert log.detected == [] and log.spotters[0].chunks == 0
        speaking[0] = False
        log.scripts.append([TRIGGER])
        listener.hold(0)                       # a new recording with the phrase in it
        assert wait_until(lambda: log.detected == ["HEY_ARUNA"])

    def test_a_test_on_the_page_suspends_it(self, make):
        listener, log = make()
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.LISTENING)
        listener.suspend("wake-test")
        assert wait_until(lambda: listener.state == wake.BUSY and log.closed == 1)
        listener.release("wake-test")
        assert wait_until(lambda: listener.state == wake.LISTENING and log.opened == 2)

    def test_a_spotter_that_cant_start_is_said_once(self, make):
        error = kws.KwsError("damaged", "a file doesn't match its SHA-256")
        listener, log = make(fail=error)
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.ENGINE_ERROR)
        time.sleep(0.2)                        # it tries again, silently
        assert log.problems == [("engine", error)] and log.opened == 0
        assert text.wake_problem("engine", error) == text._(
            "wake_problem_engine", reason=text._("wake_err_damaged"))

    def test_a_microphone_error(self, make):
        listener, log = make(mic_error="busy")
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.MIC_ERROR)
        time.sleep(0.2)
        assert log.problems == [("mic", "busy")] and log.opened >= 2

    def test_a_new_phrase_makes_a_new_spotter(self, make):
        listener, log = make()
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.LISTENING and len(log.spotters) == 1)
        listener.configure(wake.Config(enabled=True, phrase="Hi Princess", sensitivity="high"))
        assert wait_until(lambda: len(log.spotters) == 2)
        assert log.spotters[0].closed
        assert (log.spotters[1].phrase, log.spotters[1].sensitivity) == ("Hi Princess", "high")

    def test_turning_it_off_and_stopping(self, make):
        listener, log = make()
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.LISTENING)
        listener.configure(wake.Config())
        assert wait_until(lambda: listener.state == wake.OFF and listener._thread is None)
        assert log.spotters[0].closed and log.closed == log.opened
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.LISTENING)
        listener.stop()
        assert listener._thread is None and listener.state == wake.OFF
        listener.configure(ON)                 # stopped for good
        assert listener._thread is None
        listener.restart()
        listener.configure(wake.Config())
        listener.configure(ON)
        assert wait_until(lambda: listener.state == wake.LISTENING)

    def test_config(self):
        assert wake.Config().phrase == "Hey Aruna" and not wake.Config().enabled
        assert wake.Config(True, "  ", "loud", 1) == wake.Config(True, "Hey Aruna", "normal", True)
        assert wake.Config(phrase="Hi  Bob").spotter_key() == ("Hi Bob", "normal")


# ------------------------------------------------------------
# Downloading and unpacking
# ------------------------------------------------------------

def test_the_pinned_wake_downloads():
    # The "shared-MT" build: its DLLs don't need the Visual C++ runtime.
    assert dl.WAKE_RUNTIME_URL == (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/"
        "sherpa-onnx-v1.13.8-win-x64-shared-MT-Release.tar.bz2")
    assert dl.WAKE_MODEL_URL == (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
        "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2")
    assert (dl.WAKE_RUNTIME_SIZE, dl.WAKE_MODEL_SIZE) == (24805859, 17626723)
    assert dl.WAKE_RUNTIME_SHA256 == \
        "6dffdc715a4465b989446a6105265d2cb345e7101591a17d35534b6758f6e8df"
    assert all(name.startswith("sherpa-onnx-v1.13.8-win-x64-shared-MT-Release/lib/")
               for name in dl.WAKE_RUNTIME_MEMBERS)
    assert dl.WAKE_MODEL_SHA256 == \
        "f170013b4716e41b62b9bfd809687c207cef798ef9bc6534d524e17af9b6561a"
    assert all(dl.host_allowed(url) for url in (dl.WAKE_RUNTIME_URL, dl.WAKE_MODEL_URL))
    assert kws.VERSION == dl.WAKE_RUNTIME_VERSION == "1.13.8"
    # Eight files: the three DLLs and the model's five, each pinned.
    assert sorted(dl.WAKE_FILES) == sorted(
        [f"runtime/{name}" for name in kws.RUNTIME_FILES]
        + ["/".join(parts) for parts in store.WAKE_PARTS.values()])
    assert all(len(sha) == 64 for _size, sha in dl.WAKE_FILES.values())
    assert text.size_label(dl.WAKE_SIZE) == "42.4 MB"


class Entry:
    """A tar entry that isn't a regular file (tarfile.DIRTYPE, SYMTYPE, LNKTYPE)."""

    def __init__(self, kind):
        self.kind = kind


def tar_bz2(entries):
    """A .tar.bz2 in memory: entries are (name, bytes) or (name, Entry(type))."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            if isinstance(content, Entry):
                info.type = content.kind
                info.linkname = "elsewhere"
                archive.addfile(info)
            else:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
    return bz2.compress(raw.getvalue())


def members_for(files):
    return {name: (f"out/{os.path.basename(name)}", len(data), hashlib.sha256(data).hexdigest())
            for name, data in files.items()}


WANTED = {"pkg/lib/a.dll": b"MZ a", "pkg/lib/b.dll": b"MZ bb"}


class TestUnpacking:
    def extract(self, tmp_path, entries, members=None, **options):
        archive = tmp_path / "x.tar.bz2"
        archive.write_bytes(tar_bz2(entries))
        dest = tmp_path / "dest"
        dest.mkdir(exist_ok=True)
        dl.extract_members(str(archive), str(dest), members or members_for(WANTED), **options)
        return dest

    def written(self, tmp_path):
        return sorted(os.path.relpath(os.path.join(d, f), tmp_path).replace("\\", "/")
                      for d, _dirs, files in os.walk(tmp_path) for f in files
                      if not f.endswith(".tar.bz2"))

    def test_only_the_wanted_files_under_our_names(self, tmp_path):
        entries = [("pkg", Entry(tarfile.DIRTYPE)), ("pkg/bin/tool.exe", b"MZ tool")] + \
            list(WANTED.items()) + [("pkg/lib/extra.dll", b"MZ extra")]
        dest = self.extract(tmp_path, entries)
        assert self.written(tmp_path) == ["dest/out/a.dll", "dest/out/b.dll"]
        assert (dest / "out" / "b.dll").read_bytes() == b"MZ bb"

    @pytest.mark.parametrize("evil", ["../evil.dll", "pkg/../../evil.dll", "/abs/evil.dll",
                                      "C:/evil.dll", "pkg\\..\\..\\evil.dll"])
    def test_an_entry_pointing_outside_is_refused(self, tmp_path, evil):
        with pytest.raises(dl.DownloadError) as error:
            self.extract(tmp_path, [(evil, b"MZ evil")] + list(WANTED.items()))
        assert error.value.kind == "extract"
        assert self.written(tmp_path) == []

    def test_a_link_in_place_of_a_wanted_file_is_refused(self, tmp_path):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with pytest.raises(dl.DownloadError) as error:
                self.extract(tmp_path, [("pkg/lib/a.dll", Entry(kind)),
                                        ("pkg/lib/b.dll", b"MZ bb")])
            assert error.value.kind == "extract"
        assert not os.path.exists(tmp_path / "elsewhere")

    def test_wrong_contents_twice_or_missing(self, tmp_path):
        with pytest.raises(dl.DownloadError) as error:
            self.extract(tmp_path, [("pkg/lib/a.dll", b"MZ A"), ("pkg/lib/b.dll", b"MZ bb")])
        assert error.value.kind == "verify"
        assert not any(name.endswith(".part") for name in self.written(tmp_path))
        with pytest.raises(dl.DownloadError) as error:
            self.extract(tmp_path, [("pkg/lib/a.dll", b"MZ ab"), ("pkg/lib/b.dll", b"MZ bb")])
        assert error.value.kind == "verify"                 # a different size
        with pytest.raises(dl.DownloadError) as error:
            self.extract(tmp_path, list(WANTED.items()) + [("pkg/lib/a.dll", b"MZ a")])
        assert error.value.kind == "extract"                # twice
        with pytest.raises(dl.DownloadError) as error:
            self.extract(tmp_path, [("pkg/lib/a.dll", b"MZ a")])
        assert error.value.kind == "extract" and "b.dll" in error.value.detail

    def test_too_many_entries_or_too_much_data(self, tmp_path):
        with pytest.raises(dl.DownloadError):
            self.extract(tmp_path, list(WANTED.items()) + [(f"f{i}", b"") for i in range(20)],
                         max_members=10)
        with pytest.raises(dl.DownloadError):
            self.extract(tmp_path, [("big", bytes(5000))] + list(WANTED.items()),
                         max_bytes=4000)

    def test_not_an_archive_and_cancel(self, tmp_path):
        bad = tmp_path / "bad.tar.bz2"
        bad.write_bytes(b"not bzip2 at all")
        with pytest.raises(dl.DownloadError) as error:
            dl.extract_members(str(bad), str(tmp_path / "d"), members_for(WANTED))
        assert error.value.kind == "extract"
        with pytest.raises(dl.Cancelled):
            self.extract(tmp_path, list(WANTED.items()), cancelled=lambda: True)

    def test_without_tarfile(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "tarfile", None)
        with pytest.raises(dl.DownloadError) as error:
            self.extract(tmp_path, list(WANTED.items()))
        assert error.value.kind == "unsupported"
        assert "Update Hariku" in text.download_error(error.value)


def fake_wake_archives(monkeypatch):
    """Two made-up archives with the eight files, pinned like the real ones."""
    runtime = {name: b"MZ " + name.encode() for name in dl.WAKE_RUNTIME_MEMBERS}
    runtime["sherpa-onnx-v1.13.8-win-x64-shared-MT-Release/bin/tool.exe"] = b"MZ not wanted"
    model = {name: b"model " + name.encode() for name in dl.WAKE_MODEL_MEMBERS}
    runtime_members = {name: (dest, len(runtime[name]), hashlib.sha256(runtime[name]).hexdigest())
                       for name, (dest, _s, _h) in dl.WAKE_RUNTIME_MEMBERS.items()}
    model_members = {name: (dest, len(model[name]), hashlib.sha256(model[name]).hexdigest())
                     for name, (dest, _s, _h) in dl.WAKE_MODEL_MEMBERS.items()}
    runtime_tar = tar_bz2(list(runtime.items()))
    model_tar = tar_bz2(list(model.items()))
    monkeypatch.setattr(dl, "WAKE_RUNTIME_MEMBERS", runtime_members)
    monkeypatch.setattr(dl, "WAKE_MODEL_MEMBERS", model_members)
    monkeypatch.setattr(dl, "WAKE_FILES", {dest: (size, sha) for dest, size, sha in
                                           list(runtime_members.values())
                                           + list(model_members.values())})
    for prefix, data in (("WAKE_RUNTIME", runtime_tar), ("WAKE_MODEL", model_tar)):
        monkeypatch.setattr(dl, prefix + "_SIZE", len(data))
        monkeypatch.setattr(dl, prefix + "_SHA256", hashlib.sha256(data).hexdigest())
    server = Server({dl.WAKE_RUNTIME_URL: runtime_tar, dl.WAKE_MODEL_URL: model_tar})
    monkeypatch.setattr(dl, "open_url", server)
    monkeypatch.setattr(dl, "_verified", {})
    return server


class TestInstallWake:
    def test_installed_checked_and_the_archives_deleted(self, userdata, monkeypatch):
        server = fake_wake_archives(monkeypatch)
        root = store.root_dir()
        assert not store.wake_installed(root)
        seen = []
        dl.install_wake(root, progress=seen.append)
        assert [url for url, _headers in server.requests] == [dl.WAKE_RUNTIME_URL,
                                                              dl.WAKE_MODEL_URL]
        assert store.wake_installed(root) and dl.verify_wake(root)
        assert seen[-1] == dl.WAKE_RUNTIME_SIZE + dl.WAKE_MODEL_SIZE
        assert sorted(os.listdir(store.wake_runtime_dir(root))) == sorted(kws.RUNTIME_FILES)
        files = store.wake_files(root)
        assert all(os.path.isfile(path) for path in files.values())
        assert not os.path.exists(os.path.join(store.wake_runtime_dir(root), "tool.exe"))
        assert os.listdir(store.downloads_dir(root)) == []          # the archives are gone
        assert not os.path.exists(store.wake_dir(root) + ".new")
        marker = store.read_json(os.path.join(store.wake_dir(root), store.WAKE_MARKER))
        assert marker["version"] == "1.13.8" and len(marker["files"]) == 8

    def test_a_changed_file_is_noticed(self, userdata, monkeypatch):
        fake_wake_archives(monkeypatch)
        root = store.root_dir()
        dl.install_wake(root)
        path = store.wake_files(root)["encoder"]
        with open(path, "r+b") as f:
            f.write(b"X")                                  # same size, other bytes
        os.utime(path, ns=(time.time_ns(), time.time_ns() + 10 ** 9))
        assert store.wake_installed(root) and not dl.verify_wake(root)
        with open(path, "ab") as f:
            f.write(b"more")
        assert not store.wake_installed(root)

    def test_a_bad_archive_leaves_nothing(self, userdata, monkeypatch):
        fake_wake_archives(monkeypatch)
        bad = dict(dl.WAKE_MODEL_MEMBERS)
        name = next(iter(bad))
        bad[name] = (bad[name][0], bad[name][1], "0" * 64)
        monkeypatch.setattr(dl, "WAKE_MODEL_MEMBERS", bad)
        root = store.root_dir()
        with pytest.raises(dl.DownloadError) as error:
            dl.install_wake(root)
        assert error.value.kind == "verify"
        assert not store.wake_installed(root) and not os.path.exists(store.wake_dir(root))
        assert not os.path.exists(store.wake_dir(root) + ".new")

    def test_removing_and_leftovers(self, userdata, monkeypatch):
        fake_wake_archives(monkeypatch)
        root = store.root_dir()
        assert store.remove_wake(root) == (False, True)
        dl.install_wake(root)
        assert store.remove_wake(root) == (True, True) and not store.wake_installed(root)
        # A DLL Windows keeps (loaded) is left; it goes at the next start.
        leftover = os.path.join(store.wake_runtime_dir(root), "onnxruntime.dll")
        os.makedirs(os.path.dirname(leftover))
        with open(leftover, "wb") as f:
            f.write(b"MZ")
        store.cleanup_partials(root)
        assert not os.path.exists(store.wake_dir(root))

    def test_a_marker_cannot_point_outside(self, userdata):
        root = store.root_dir()
        os.makedirs(store.wake_dir(root))
        store.write_json(os.path.join(store.wake_dir(root), store.WAKE_MARKER),
                         {"files": {"../../evil.dll": {"size": 2}}})
        assert not store.wake_installed(root)

    def test_a_listener_with_other_pins_counts_as_not_installed(self, userdata, monkeypatch):
        # One installed from an earlier build (the "shared-MD" one, say) is
        # downloaded again, never loaded.
        fake_wake_archives(monkeypatch)
        root = store.root_dir()
        dl.install_wake(root)
        assert dl.wake_current(root) and dl.wake_installed(root)
        changed = dict(dl.WAKE_FILES)
        changed["runtime/onnxruntime.dll"] = (changed["runtime/onnxruntime.dll"][0], "1" * 64)
        monkeypatch.setattr(dl, "WAKE_FILES", changed)
        assert store.wake_installed(root)                    # the files are all there...
        assert not dl.wake_current(root) and not dl.wake_installed(root)   # ...but not ours
        os.remove(os.path.join(store.wake_dir(root), store.WAKE_MARKER))
        assert not dl.wake_current(root)

    def test_replacing_a_listener_whose_dll_is_loaded(self, userdata, monkeypatch):
        fake_wake_archives(monkeypatch)
        root = store.root_dir()
        dl.install_wake(root)
        real_rmtree = dl.shutil.rmtree

        def rmtree(path, *args, **kwargs):
            if os.path.normcase(path) == os.path.normcase(store.wake_dir(root)) and \
                    not kwargs.get("ignore_errors"):
                raise PermissionError(5, "Access is denied", "onnxruntime.dll")
            return real_rmtree(path, *args, **kwargs)

        monkeypatch.setattr(dl.shutil, "rmtree", rmtree)
        with pytest.raises(dl.DownloadError) as error:
            dl.install_wake(root)
        assert error.value.kind == "in_use"
        assert "Restart Hariku" in text.download_error(error.value)
        assert not os.path.exists(store.wake_dir(root) + ".new")


# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------

class TestWakeSettings:
    def test_defaults_and_checking(self, userdata):
        settings = store.load_settings()
        assert (settings["wake"], settings["wake_phrase"], settings["wake_sensitivity"],
                settings["wake_quiet_hours"]) == (False, "Hey Aruna", "normal", False)
        clean = store.normalize_settings({"wake": "yes", "wake_phrase": "   ",
                                          "wake_sensitivity": "very_high",
                                          "wake_quiet_hours": 1})
        assert (clean["wake"], clean["wake_phrase"], clean["wake_sensitivity"],
                clean["wake_quiet_hours"]) == (False, "Hey Aruna", "normal", False)
        clean = store.normalize_settings({"wake": True, "wake_phrase": "  Hi   Princess ",
                                          "wake_sensitivity": "high", "wake_quiet_hours": True})
        assert (clean["wake"], clean["wake_phrase"], clean["wake_sensitivity"],
                clean["wake_quiet_hours"]) == (True, "Hi Princess", "high", True)
        assert len(store.normalize_settings({"wake_phrase": "a" * 99})["wake_phrase"]) == 40

    def test_saved_from_the_page_and_given_to_the_listener(self, vc):
        try:
            vc.save_settings("auto", True, 1000, "normal", {
                "enabled": False, "phrase": "Hi Princess", "sensitivity": "high",
                "quiet_hours": True})
            saved = store.load_settings()
            assert (saved["wake"], saved["wake_phrase"], saved["wake_sensitivity"],
                    saved["wake_quiet_hours"]) == (False, "Hi Princess", "high", True)
            assert vc._wake.config == wake.Config(False, "Hi Princess", "high", True)
            vc.save_settings("base", False, 800)            # without it, it stays
            assert store.load_settings()["wake_phrase"] == "Hi Princess"
        finally:
            vc._wake.stop()


# ------------------------------------------------------------
# The extension: "heard it" -> Aruna, the pause action, the page's test
# ------------------------------------------------------------

@pytest.fixture
def fake_bar(monkeypatch):
    """ui.command_bar without a window."""
    calls = []
    bar = types.SimpleNamespace(_listening=False,
                                start_listening=lambda: calls.append("start_listening"))
    module = types.ModuleType("ui.command_bar")
    module.state = {"bar": None}
    module.current_bar = lambda: module.state["bar"]
    module.open_command_bar = lambda listen=None, **kw: calls.append(("open", listen))
    module.bring_to_front = lambda b: calls.append("front")
    monkeypatch.setitem(sys.modules, "ui.command_bar", module)
    import ui
    monkeypatch.setattr(ui, "command_bar", module, raising=False)
    module.calls, module.bar = calls, bar
    return module


class TestExtension:
    def test_hearing_the_phrase_opens_aruna_listening(self, vc, fake_bar):
        vc._on_wake_detected("HEY_ARUNA")
        assert fake_bar.calls == [("open", True)]
        fake_bar.state["bar"] = fake_bar.bar                 # Aruna is open already
        vc._on_wake_detected("HEY_ARUNA")
        assert fake_bar.calls[1:] == ["front", "start_listening"]
        fake_bar.bar._listening = True                       # and listening
        vc._on_wake_detected("HEY_ARUNA")
        assert fake_bar.calls[3:] == ["front"]

    def test_a_listener_detection_reaches_aruna(self, vc, fake_bar, fast):
        vc._wake.stop()
        vc._wake.restart()
        log = types.SimpleNamespace(opened=0, closed=0, chunks=0)
        vc._wake._make_spotter = lambda phrase, sensitivity: FakeSpotter()
        vc._wake._make_recorder = lambda: FakeMic([QUIET] * 3 + [TRIGGER], log)
        vc._wake._installed = lambda: True
        vc._wake._blocked = lambda: None
        try:
            vc._wake.configure(wake.Config(enabled=True))
            assert wait_until(lambda: ("open", True) in fake_bar.calls)
        finally:
            vc._wake.stop()

    def test_pausing_and_resuming(self, vc, monkeypatch):
        try:
            vc.toggle_wake_pause()
            assert vc.spoken[-1] == text._("wake_is_off")
            vc._settings["wake"] = True
            vc.toggle_wake_pause()
            assert vc.spoken[-1] == text._("wake_not_installed")
            monkeypatch.setattr(vc, "wake_available", lambda: True)
            vc.toggle_wake_pause()
            assert vc._wake.paused and vc.spoken[-1] == text._("wake_paused")
            vc.toggle_wake_pause()
            assert not vc._wake.paused
            assert vc.spoken[-1] == 'Listening for "Hey Aruna" again.'
        finally:
            vc._wake.stop()

    def test_the_page_test_counts_what_it_hears(self, vc, monkeypatch):
        monkeypatch.setattr(wake, "COOLDOWN_SECONDS", 0.0)
        listener, log = make_listener(vc, b"")
        mic = types.SimpleNamespace(opened=0, closed=0, chunks=0)
        listener.make_recorder = lambda: types.SimpleNamespace(
            record=lambda on_chunk, stop=None, max_seconds=30.0, keep=True:
            FakeMic([QUIET] * 5 + [TRIGGER] + [QUIET] * 30 + [TRIGGER] + [QUIET] * 3, mic)
            .record(on_chunk, stop=stop, max_seconds=max_seconds, keep=keep))
        heard = []
        spotter = FakeSpotter()
        result = vc.test_wake("Hey Aruna", "normal", heard.append, threading.Event(),
                              listener=listener, seconds=0.6, spotter=spotter)
        assert heard == [1, 2] and result == {"count": 2, "seconds": 0.6, "stopped": False}
        assert log.played == ["listen.wav", "listen_end.wav"] and spotter.closed
        assert text.wake_test_message(result, None) == \
            "Heard the wake phrase 2 times in 0.6 seconds."

    def test_the_page_test_hears_after_a_long_answer_was_cut_off(self, vc, monkeypatch):
        # What CI's window check did: the microphone test's long result was
        # said, then "Test the wake phrase..." said its instructions (which
        # interrupt it) and waited that long. The test was deaf for the rest
        # of the long result, so it heard nothing.
        monkeypatch.setattr(wake, "speech_seconds", lambda t: 30.0 if len(t) > 100 else 0.05)
        monkeypatch.setattr(wake, "AFTER_SPEECH_SECONDS", 0.0)
        monkeypatch.setattr(wake, "COOLDOWN_SECONDS", 0.0)
        result_text = text.calibration_message(audio.Calibration("very_high", "too_quiet",
                                                                  20.0, 60.0))
        assert len(result_text) > 100
        vc._speech.on_before_speak({"text": result_text, "interrupt": True})
        instructions = text._("wake_test_speak", phrase="Hey Aruna", seconds=20)
        vc._speech.on_before_speak({"text": instructions, "interrupt": True})
        time.sleep(wake.speech_seconds(instructions) + 0.01)     # the page waits this long
        listener, log = make_listener(vc, b"")
        mic = types.SimpleNamespace(opened=0, closed=0, chunks=0)
        listener.make_recorder = lambda: types.SimpleNamespace(
            record=lambda on_chunk, stop=None, max_seconds=30.0, keep=True:
            FakeMic([QUIET] * 5 + [TRIGGER] + [QUIET] * 30 + [TRIGGER] + [QUIET] * 3, mic)
            .record(on_chunk, stop=stop, max_seconds=max_seconds, keep=keep))
        heard = []
        result = vc.test_wake("Hey Aruna", "normal", heard.append, threading.Event(),
                              listener=listener, seconds=0.6, spotter=FakeSpotter())
        assert heard == [1, 2] and result["count"] == 2

    def test_the_page_test_can_be_stopped_and_explains_problems(self, vc):
        stop = threading.Event()
        stop.set()
        listener, log = make_listener(vc, b"")
        spotter = FakeSpotter()
        result = vc.test_wake("Hey Aruna", "normal", lambda c: None, stop, listener=listener,
                              spotter=spotter)
        assert result["stopped"] and result["count"] == 0 and spotter.closed
        assert text.wake_test_message(result, None) == text._("wake_test_cancelled")
        listener, log = make_listener(vc, b"", blocked="blocked_device")
        with pytest.raises(audio.MicrophoneError):
            vc.test_wake("Hey Aruna", "normal", lambda c: None, threading.Event(),
                         listener=listener, spotter=FakeSpotter())
        assert log.played == []
        assert text.wake_test_message(None, audio.MicrophoneError("blocked_device")) == \
            text.mic_error("blocked_device")
        assert "Change it in Preferences" in text.wake_test_message(None, ValueError("x"))
        assert text.wake_test_message(None, RuntimeError("busy")) == text._("mic_test_busy")

    def test_the_spotter_needs_the_files(self, vc):
        with pytest.raises(kws.KwsError) as error:
            vc.make_spotter("Hey Aruna", "normal")
        assert error.value.kind == "missing"
        assert "damaged" in text.wake_engine_error(error.value)

    def test_downloading_the_listener(self, vc):
        done = []

        def install_wake(root, progress=None, cancelled=None):
            assert vc._wake._suspended == {"download"}        # the listener lets go of it
            progress(dl.WAKE_SIZE // 2)
            progress(dl.WAKE_SIZE)
            done.append("wake")

        downloads = vc.Downloads(lambda *a, **k: done.append("runtime"),
                                 lambda *a, **k: done.append("model"), install_wake)
        assert downloads.start("wake")
        assert wait_until(lambda: downloads.current() is None)
        assert done == ["wake"] and vc._wake._suspended == set()
        assert vc.spoken[0] == "Downloading Wake phrase listener (sherpa-onnx and an English " \
                               "keyword model), 42.4 MB."
        assert vc.spoken[-1].endswith("downloaded.")

    def test_the_download_question(self, vc):
        question = text.confirm_download("wake", need_runtime=True)
        assert "GitHub" in question and "24.8 MB" in question and "17.6 MB" in question
        assert "42.4 MB" in question and "Apache-2.0" in question and "MIT" in question
        assert "whisper" not in question

    def test_removing_the_listener(self, vc, monkeypatch):
        monkeypatch.setattr(store, "remove_wake", lambda root: (True, False))
        assert vc.controller.remove("wake") == "later"
        monkeypatch.setattr(store, "remove_wake", lambda root: (True, True))
        assert vc.controller.remove("wake") is True
        monkeypatch.setattr(store, "remove_wake", lambda root: (False, True))
        assert vc.controller.remove("wake") is False
        assert vc.controller.installed()["wake"] is False

    def test_register_and_teardown(self, vc):
        import core.commands
        import core.hotkeys
        import core.preferences
        from core.events import EventBus
        bus = EventBus()
        before = {k: list(v) for k, v in core.preferences.get_all_panels().items()}
        try:
            vc.register(bus)
            action = core.hotkeys.actions["Voice Control.toggle_wake"]
            assert action.default_keycode is None                       # no key by default
            assert action.description == "Pause or resume the wake phrase"
            assert "pause the wake phrase" in core.commands.aliases_for(action.id)
            assert "jeda frasa pemanggil" in core.commands.aliases_for(action.id)
            match = core.commands.match("pause the wake phrase", core.commands.commands())
            assert match.best.id == action.id and match.kind == "run"
            assert vc._speech.on_before_speak in bus._listeners["on_before_speak"]
            vc.teardown()
            assert core.commands.aliases_for(action.id) == []
            assert vc._speech.on_before_speak not in bus._listeners.get("on_before_speak", [])
            assert vc._wake._thread is None
        finally:
            core.preferences._panels.clear()
            core.preferences._panels.update(before)
            core.commands.unregister_listener()
            core.commands.remove_aliases("Voice Control.toggle_wake")
            core.hotkeys.actions.pop("Voice Control.toggle_wake", None)


class TestPageLogic:
    """The page's wake phrase methods on a stand-in without windows."""

    def page(self, vc, monkeypatch, phrase="Hey Aruna", enabled=True):
        import voice_control_ui as vui
        said = []
        monkeypatch.setattr(vui, "_announce", lambda message, interrupt=True, delay=0:
                            said.append(message))

        class Field:
            def __init__(self, value=""):
                self.value = value

            def GetValue(self):
                return self.value

            def ChangeValue(self, value):
                self.value = value

            def SetFocus(self):
                raise AssertionError("focus moved")

        fake = types.SimpleNamespace(
            txt_phrase=Field(phrase), txt_advice=Field(), txt_wake_test=Field(),
            chk_wake=types.SimpleNamespace(GetValue=lambda: enabled), said=said,
            _advice_problem=None, _wake_stop=None, _installed={"wake": True})
        fake._usable = lambda: True
        for name in ("ValidateChanges", "_update_advice", "_show_wake_test", "_wake_heard",
                     "_wake_test_done"):
            setattr(fake, name, getattr(vui.VoiceControlPanel, name).__get__(fake))
        return fake

    def test_a_phrase_the_model_cant_hear_isnt_saved_while_on(self, vc, monkeypatch):
        assert self.page(vc, monkeypatch).ValidateChanges() is None
        page = self.page(vc, monkeypatch, phrase="Hey Aruna 2")
        message, control = page.ValidateChanges()
        assert control is page.txt_phrase and message.startswith(text._("wake_advice_digits"))
        assert self.page(vc, monkeypatch, phrase="", enabled=True).ValidateChanges()[0] \
            .startswith(text._("wake_advice_empty"))
        assert self.page(vc, monkeypatch, phrase="", enabled=False).ValidateChanges() is None
        assert self.page(vc, monkeypatch, phrase="Aruna").ValidateChanges() is None   # poor, allowed

    def test_the_advice_is_said_when_it_changes(self, vc, monkeypatch):
        page = self.page(vc, monkeypatch, phrase="Aruna")
        page._update_advice(speak_it=False)
        assert page.txt_advice.value.startswith(text._("wake_advice_one_word")) and not page.said
        page._advice_problem = None
        page._update_advice(speak_it=True)
        assert page.said == [page.txt_advice.value]
        page._update_advice(speak_it=True)                  # the same: not said again
        assert len(page.said) == 1
        page.txt_phrase.value = "Hey Aruna"
        page._update_advice(speak_it=True)
        assert page.said[-1] == text._("wake_advice_note")

    def test_the_test_results_are_shown_and_said(self, vc, monkeypatch):
        page = self.page(vc, monkeypatch)
        page._wake_stop = threading.Event()
        page._wake_heard(1)
        page._wake_heard(2)
        assert page.said == ["Heard it.", "Heard it, 2."]
        page._wake_test_done({"count": 2, "seconds": 20, "stopped": False}, None)
        assert page.txt_wake_test.value == page.said[-1] == \
            "Heard the wake phrase 2 times in 20 seconds."
        assert page._wake_stop is None
        page._wake_heard(3)                                  # after the end: nothing
        assert len(page.said) == 3


class TestText:
    def test_advice(self, vc):
        note = text._("wake_advice_note")
        assert text.wake_advice(None) == note
        assert "Aruna" in note and "High" in note and "English" in note
        for problem in ("one_word", "short", "common", "empty", "digits", "unsupported", "long"):
            advice = text.wake_advice(problem)
            assert advice.endswith(note) and advice != note

    def test_status(self, vc):
        assert text.wake_status(wake.OFF, "Hey Aruna") == ""
        assert text.wake_status(wake.LISTENING, "Hey Aruna") == 'Listening for "Hey Aruna".'
        assert text.wake_status(wake.BUSY, "Hey Aruna") == 'Listening for "Hey Aruna".'
        for state in (wake.PAUSED, wake.QUIET, wake.MISSING, wake.BLOCKED, wake.MIC_ERROR,
                      wake.ENGINE_ERROR):
            assert text.wake_status(state, "x")

    def test_indonesian(self, vc, monkeypatch):
        import core.i18n
        monkeypatch.setattr(core.i18n, "_current_language", "id")
        assert text.wake_status(wake.LISTENING, "Hey Aruna") == 'Mendengarkan "Hey Aruna".'
        assert "kamu" in text._("wake_paused") and "kamu" in text._("confirm_wake")
        assert text.wake_heard(1) == "Terdengar." and text.wake_heard(3) == "Terdengar, 3."

    def test_the_test_messages(self, vc):
        assert text.wake_test_outcome(0, 20) == text._("wake_test_none")
        assert text.wake_test_outcome(1, 20) == "Heard the wake phrase once in 20 seconds."
        assert text.wake_test_outcome(3, 20, stopped=True) == \
            "Test stopped. Heard the wake phrase 3 times."
        assert text.wake_heard(1) == "Heard it." and text.wake_heard(2) == "Heard it, 2."


def test_manifest_and_privacy_words():
    with open(os.path.join(VC_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["version"] == "1.2" and manifest["minimum_core_version"] == "2.7"
    assert "wake phrase" in manifest["description"]
    with open(os.path.join(VC_DIR, "voice_control_wake.py"), encoding="utf-8") as f:
        source = f.read()
    assert "keep=False" in source and "wave.open" not in source and "open(" not in source
