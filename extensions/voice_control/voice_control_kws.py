# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The keyword spotter: sherpa-onnx's C API (sherpa-onnx-c-api.dll, v1.13.8,
Apache-2.0) through ctypes (no wx, no network).

sherpa-onnx's open-vocabulary keyword spotting is a very small streaming
speech recogniser that can only decode the phrases it is given, so any
phrase works without training. Audio goes in as 16 kHz float samples; a
detection comes back as the phrase's name.

The structures below copy sherpa-onnx/c-api/c-api.h of the v1.13.8 tag field
for field (same order, same types); a different DLL version is refused,
because a changed structure would be read wrong. Only these calls are used:
SherpaOnnxGetVersionStr, SherpaOnnxCreateKeywordSpotter,
SherpaOnnxDestroyKeywordSpotter, SherpaOnnxCreateKeywordStream,
SherpaOnnxDestroyOnlineStream, SherpaOnnxOnlineStreamAcceptWaveform,
SherpaOnnxOnlineStreamInputFinished, SherpaOnnxIsKeywordStreamReady,
SherpaOnnxDecodeKeywordStream, SherpaOnnxResetKeywordStream,
SherpaOnnxGetKeywordResult and SherpaOnnxDestroyKeywordResult.

Careful: sherpa-onnx ends the whole process (exit(-1)) when a keyword holds a
token that isn't in tokens.txt. Spotter() therefore refuses keywords with any
token it doesn't find in tokens.txt itself, before sherpa-onnx sees them.
"""
import array
import ctypes
import logging
import os
import sys
import threading

logger = logging.getLogger(__name__)

VERSION = "1.13.8"
C_API_DLL = "sherpa-onnx-c-api.dll"
ONNXRUNTIME_DLL = "onnxruntime.dll"
PROVIDERS_DLL = "onnxruntime_providers_shared.dll"
RUNTIME_FILES = (C_API_DLL, ONNXRUNTIME_DLL, PROVIDERS_DLL)
SAMPLE_RATE = 16000
FEATURE_DIM = 80
MAX_ACTIVE_PATHS = 4
NUM_TRAILING_BLANKS = 1
# The Visual C++ runtime the official "shared-MD" build needs.
CRT_DLLS = ("msvcp140.dll", "msvcp140_1.dll", "vcruntime140.dll", "vcruntime140_1.dll")

c_char_p = ctypes.c_char_p
c_int32 = ctypes.c_int32
c_float = ctypes.c_float


class KwsError(Exception):
    """kind: "missing" (a file isn't there), "load" (the DLLs didn't load;
    `detail` names a missing Visual C++ runtime DLL when that's why),
    "version" (another sherpa-onnx), "path" (a folder name sherpa-onnx can't
    open), "keywords" (a token the model doesn't have) or "create"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = str(detail or "")


# ------------------------------------------------------------
# c-api.h (v1.13.8)
# ------------------------------------------------------------

class FeatureConfig(ctypes.Structure):
    _fields_ = [("sample_rate", c_int32), ("feature_dim", c_int32)]


class OnlineTransducerModelConfig(ctypes.Structure):
    _fields_ = [("encoder", c_char_p), ("decoder", c_char_p), ("joiner", c_char_p)]


class OnlineParaformerModelConfig(ctypes.Structure):
    _fields_ = [("encoder", c_char_p), ("decoder", c_char_p)]


class OnlineZipformer2CtcModelConfig(ctypes.Structure):
    _fields_ = [("model", c_char_p)]


class OnlineNemoCtcModelConfig(ctypes.Structure):
    _fields_ = [("model", c_char_p)]


class OnlineToneCtcModelConfig(ctypes.Structure):
    _fields_ = [("model", c_char_p)]


class OnlineModelConfig(ctypes.Structure):
    _fields_ = [
        ("transducer", OnlineTransducerModelConfig),
        ("paraformer", OnlineParaformerModelConfig),
        ("zipformer2_ctc", OnlineZipformer2CtcModelConfig),
        ("tokens", c_char_p),
        ("num_threads", c_int32),
        ("provider", c_char_p),
        ("debug", c_int32),
        ("model_type", c_char_p),
        ("modeling_unit", c_char_p),
        ("bpe_vocab", c_char_p),
        ("tokens_buf", c_char_p),
        ("tokens_buf_size", c_int32),
        ("nemo_ctc", OnlineNemoCtcModelConfig),
        ("t_one_ctc", OnlineToneCtcModelConfig),
    ]


class KeywordSpotterConfig(ctypes.Structure):
    _fields_ = [
        ("feat_config", FeatureConfig),
        ("model_config", OnlineModelConfig),
        ("max_active_paths", c_int32),
        ("num_trailing_blanks", c_int32),
        ("keywords_score", c_float),
        ("keywords_threshold", c_float),
        ("keywords_file", c_char_p),
        ("keywords_buf", c_char_p),
        ("keywords_buf_size", c_int32),
    ]


class KeywordResult(ctypes.Structure):
    _fields_ = [
        ("keyword", c_char_p),
        ("tokens", c_char_p),
        ("tokens_arr", ctypes.POINTER(c_char_p)),
        ("count", c_int32),
        ("timestamps", ctypes.POINTER(c_float)),
        ("start_time", c_float),
        ("json", c_char_p),
    ]


def _declare(dll):
    """Argument and result types of the functions used (our own CDLL
    instance, so nobody else's declarations change)."""
    spotter = stream = ctypes.c_void_p
    table = {
        "SherpaOnnxGetVersionStr": ([], c_char_p),
        "SherpaOnnxCreateKeywordSpotter": ([ctypes.POINTER(KeywordSpotterConfig)], spotter),
        "SherpaOnnxDestroyKeywordSpotter": ([spotter], None),
        "SherpaOnnxCreateKeywordStream": ([spotter], stream),
        "SherpaOnnxDestroyOnlineStream": ([stream], None),
        "SherpaOnnxOnlineStreamAcceptWaveform": ([stream, c_int32, ctypes.POINTER(c_float),
                                                  c_int32], None),
        "SherpaOnnxOnlineStreamInputFinished": ([stream], None),
        "SherpaOnnxIsKeywordStreamReady": ([spotter, stream], c_int32),
        "SherpaOnnxDecodeKeywordStream": ([spotter, stream], None),
        "SherpaOnnxResetKeywordStream": ([spotter, stream], None),
        "SherpaOnnxGetKeywordResult": ([spotter, stream], ctypes.POINTER(KeywordResult)),
        "SherpaOnnxDestroyKeywordResult": ([ctypes.POINTER(KeywordResult)], None),
    }
    for name, (args, result) in table.items():
        fn = getattr(dll, name)
        fn.argtypes = args
        fn.restype = result
    return dll


# ------------------------------------------------------------
# Loading the DLLs (once per process; they stay loaded)
# ------------------------------------------------------------

_lock = threading.Lock()
_loaded = {}          # folder -> the C API


def _module_loaded(name):
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        return bool(kernel32.GetModuleHandleW(name))
    except Exception:
        return False


def missing_crt(folder, system_dir=None, exe_dir=None, loaded=None):
    """The Visual C++ runtime DLLs Windows can't find for the official
    "shared-MD" build: not already loaded in Hariku (wxPython brings some),
    not next to the DLLs, next to Hariku, or in System32. [] when none is
    missing."""
    system_dir = system_dir or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                            "System32")
    exe_dir = exe_dir or os.path.dirname(os.path.abspath(sys.executable))
    loaded = loaded or _module_loaded
    missing = []
    for name in CRT_DLLS:
        if loaded(name):
            continue
        if any(os.path.isfile(os.path.join(d, name)) for d in (folder, exe_dir, system_dir)):
            continue
        missing.append(name)
    return missing


def load(folder, cdll=None):
    """The C API from `folder` (the three DLLs), loaded once. onnxruntime.dll
    is loaded first from the same folder by its full path, so Windows' own
    onnxruntime.dll (Windows 11 has one) is never used instead. Raises
    KwsError."""
    folder = os.path.abspath(folder)
    cdll = cdll or ctypes.CDLL
    with _lock:
        if folder in _loaded:
            return _loaded[folder]
        for name in RUNTIME_FILES:
            if not os.path.isfile(os.path.join(folder, name)):
                raise KwsError("missing", name)
        try:
            cdll(os.path.join(folder, ONNXRUNTIME_DLL))
            dll = _declare(cdll(os.path.join(folder, C_API_DLL)))
        except OSError as e:
            missing = missing_crt(folder)
            raise KwsError("load", ", ".join(missing) if missing else str(e)) from None
        version = (dll.SherpaOnnxGetVersionStr() or b"").decode("ascii", "replace")
        if version != VERSION:
            raise KwsError("version", version)
        _loaded[folder] = dll
        return dll


def native_path(path, short_path=None):
    """A path as the bytes sherpa-onnx opens (its C++ opens files with
    narrow strings, which Windows reads in the ANSI code page): plain ASCII
    as is; otherwise the 8.3 short name when it is ASCII, else the ANSI
    code page. KwsError("path") when neither can name it."""
    path = os.path.abspath(path)
    if path.isascii():
        return path.encode("ascii")
    short = (short_path or _short_path)(path)
    if short and short.isascii():
        return short.encode("ascii")
    try:
        return path.encode("mbcs", "strict")
    except (UnicodeEncodeError, LookupError):
        raise KwsError("path", path) from None


def _short_path(path):
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                               ctypes.c_uint32]
        kernel32.GetShortPathNameW.restype = ctypes.c_uint32
        buffer = ctypes.create_unicode_buffer(1024)
        if kernel32.GetShortPathNameW(path, buffer, 1024):
            return buffer.value
    except Exception:
        pass
    return None


def read_tokens(path):
    """The tokens of tokens.txt ("<token> <id>" per line), as a set."""
    tokens = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                tokens.add(parts[0])
    return tokens


def check_keywords(text, tokens):
    """Refuse (KwsError "keywords") keyword lines sherpa-onnx would end
    Hariku over: a word that is neither a token of tokens.txt nor a ":score",
    "#threshold" or "@name", a line without tokens, or a bad number."""
    lines = text.split("\n")
    if not lines or not text.strip():
        raise KwsError("keywords", "no keywords")
    for line in lines:
        words = line.split()
        if not any(word in tokens for word in words):
            raise KwsError("keywords", f"no tokens in {line!r}")
        for word in words:
            if word in tokens:
                continue
            if word[0] in ":#" and len(word) > 1:
                try:
                    value = float(word[1:])
                except ValueError:
                    raise KwsError("keywords", word) from None
                if not 0.0 < value < 100.0:
                    raise KwsError("keywords", word)
            elif word[0] == "@" and len(word) > 1:
                continue
            else:
                raise KwsError("keywords", word)


# ------------------------------------------------------------
# A spotter with one stream
# ------------------------------------------------------------

class Spotter:
    """A keyword spotter and its stream. `keywords` is sherpa-onnx's keyword
    text ("▁HE Y ▁A RU N A :1.0 #0.25 @HEY_ARUNA", one per line); `files`
    maps "tokens", "encoder", "decoder" and "joiner" to paths. Not thread
    safe: one thread feeds it. Raises KwsError."""

    def __init__(self, runtime_dir, files, keywords, threshold=0.25, score=1.0, threads=1,
                 dll=None, max_active_paths=MAX_ACTIVE_PATHS):
        for key in ("tokens", "encoder", "decoder", "joiner"):
            if not os.path.isfile(files.get(key, "")):
                raise KwsError("missing", key)
        check_keywords(keywords, read_tokens(files["tokens"]))
        self._dll = dll or load(runtime_dir)
        self._spotter = None
        self._stream = None
        # Kept alive while sherpa-onnx reads them.
        self._strings = {key: native_path(files[key]) for key in ("tokens", "encoder",
                                                                   "decoder", "joiner")}
        self._keywords = keywords.encode("utf-8")
        config = KeywordSpotterConfig()
        config.feat_config.sample_rate = SAMPLE_RATE
        config.feat_config.feature_dim = FEATURE_DIM
        transducer = config.model_config.transducer
        transducer.encoder = self._strings["encoder"]
        transducer.decoder = self._strings["decoder"]
        transducer.joiner = self._strings["joiner"]
        config.model_config.tokens = self._strings["tokens"]
        config.model_config.num_threads = max(1, int(threads))
        config.model_config.provider = b"cpu"
        config.model_config.debug = 0
        config.max_active_paths = int(max_active_paths)
        config.num_trailing_blanks = NUM_TRAILING_BLANKS
        config.keywords_score = float(score)
        config.keywords_threshold = float(threshold)
        config.keywords_buf = self._keywords
        config.keywords_buf_size = len(self._keywords)
        spotter = self._dll.SherpaOnnxCreateKeywordSpotter(ctypes.byref(config))
        if not spotter:
            raise KwsError("create", "the keyword spotter could not be created")
        self._spotter = spotter
        self.new_stream()

    @property
    def closed(self):
        return self._spotter is None

    def new_stream(self):
        """Start over with an empty stream (after a pause: nothing heard
        before it counts)."""
        if self._spotter is None:
            raise KwsError("create", "closed")
        self._drop_stream()
        stream = self._dll.SherpaOnnxCreateKeywordStream(self._spotter)
        if not stream:
            raise KwsError("create", "no stream")
        self._stream = stream

    def _drop_stream(self):
        stream, self._stream = self._stream, None
        if stream:
            self._dll.SherpaOnnxDestroyOnlineStream(stream)

    def accept(self, samples):
        """Add float samples (an array("f") or a sequence, -1..1, 16 kHz);
        returns the names of the keywords detected (the stream starts over
        after each)."""
        if self._stream is None:
            return []
        if not isinstance(samples, array.array) or samples.typecode != "f":
            samples = array.array("f", samples)
        if len(samples):
            buffer = (c_float * len(samples)).from_buffer(samples)
            self._dll.SherpaOnnxOnlineStreamAcceptWaveform(self._stream, SAMPLE_RATE, buffer,
                                                          len(samples))
        return self._decode()

    def finish(self):
        """The input has ended (a file): decode what is left."""
        if self._stream is None:
            return []
        self._dll.SherpaOnnxOnlineStreamInputFinished(self._stream)
        return self._decode()

    def _decode(self):
        dll, spotter, stream = self._dll, self._spotter, self._stream
        found = []
        while dll.SherpaOnnxIsKeywordStreamReady(spotter, stream):
            dll.SherpaOnnxDecodeKeywordStream(spotter, stream)
            result = dll.SherpaOnnxGetKeywordResult(spotter, stream)
            if not result:
                continue
            try:
                keyword = result.contents.keyword or b""
            finally:
                dll.SherpaOnnxDestroyKeywordResult(result)
            if keyword:
                found.append(keyword.decode("utf-8", "replace"))
                dll.SherpaOnnxResetKeywordStream(spotter, stream)
        return found

    def close(self):
        self._drop_stream()
        spotter, self._spotter = self._spotter, None
        if spotter:
            self._dll.SherpaOnnxDestroyKeywordSpotter(spotter)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def pcm_to_float(pcm):
    """16-bit little-endian PCM bytes as an array("f") of -1..1."""
    samples = array.array("h")
    samples.frombytes(bytes(pcm[:len(pcm) - len(pcm) % 2]))
    if sys.byteorder != "little":
        samples.byteswap()
    return array.array("f", [s / 32768.0 for s in samples])
