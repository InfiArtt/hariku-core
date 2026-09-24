# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The built-in "Windows voices" provider of Hariku Voice (core/voice.py): SAPI 5
through COM, called with plain ctypes.

Why ctypes and not comtypes: Hariku needs about a dozen SAPI methods. comtypes
would be a new dependency whose type-library wrappers are generated into
comtypes.gen at run time, which a Nuitka build can't do (the wrappers would
have to be pre-generated and kept in sync). Calling the vtables directly needs
no generated code, adds nothing to the build, and is easy to mock in tests.

Voices come from both SAPI voice categories: the classic desktop voices
(HKLM\\SOFTWARE\\Microsoft\\Speech\\Voices, plus any the user installed for
themselves) and the OneCore voices Windows 10 and 11 ship
(HKLM\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices). A voice's id is its SAPI
token id (a registry path).

All COM work happens on one worker thread, a single-threaded apartment that
starts on first use and ends after a while unused. speak() returns at once;
the worker polls ISpVoice::WaitUntilDone and calls on_done when the speech ends
or is stopped (SPF_PURGEBEFORESPEAK).
"""
import ctypes
import ctypes.wintypes as wt
import logging
import queue
import threading
import time
import uuid

logger = logging.getLogger(__name__)

PROVIDER_ID = "windows"
VOICE_CATEGORIES = (
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices",
)

POLL_SECONDS = 0.05
IDLE_EXIT_SECONDS = 300.0     # the worker thread ends after this long unused
RETRY_SECONDS = 60.0          # a SAPI that failed to start is tried again after this
LIST_TIMEOUT_SECONDS = 20.0

S_OK = 0
RPC_E_CHANGED_MODE = -2147417850      # 0x80010106
COINIT_APARTMENTTHREADED = 0x2
CLSCTX_ALL = 0x17

SPF_ASYNC = 0x1
SPF_PURGEBEFORESPEAK = 0x2
SPF_IS_NOT_XML = 0x10

CLSID_SpVoice = "{96749377-3391-11D2-9EE3-00C04F797396}"
IID_ISpVoice = "{6C44DF74-72B9-4992-A1EC-EF996E0422D4}"
CLSID_SpObjectTokenCategory = "{A910187F-0C7A-45AC-92CC-59EDAFB77B53}"
IID_ISpObjectTokenCategory = "{2D3D3845-39AF-4850-BBF9-40B49780011D}"
CLSID_SpObjectToken = "{EF411752-3736-4CB4-9C8C-8EF4CCB58EFE}"
IID_ISpObjectToken = "{14056589-E16C-11D2-BB90-00C04F8EE6C0}"

# Vtable slots. IUnknown takes 0-2.
RELEASE = 2
# ISpDataKey (ISpObjectToken and ISpObjectTokenCategory derive from it)
DATAKEY_GET_STRING_VALUE = 6
DATAKEY_OPEN_KEY = 9
# ISpObjectToken
TOKEN_SET_ID = 15
TOKEN_GET_ID = 16
# ISpObjectTokenCategory
CATEGORY_SET_ID = 15
CATEGORY_ENUM_TOKENS = 18
# IEnumSpObjectTokens
ENUM_ITEM = 7
ENUM_GET_COUNT = 8
# ISpVoice: IUnknown 0-2, ISpNotifySource 3-9, ISpEventSource 10-12, then its own
VOICE_SET_OUTPUT = 13
VOICE_SET_VOICE = 18
VOICE_SPEAK = 20
VOICE_SET_RATE = 28
VOICE_SET_VOLUME = 30
VOICE_WAIT_UNTIL_DONE = 32


class ComError(OSError):
    def __init__(self, hresult, what):
        self.hresult = hresult & 0xFFFFFFFF
        super().__init__(f"{what} failed (HRESULT 0x{self.hresult:08X})")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def guid(text):
    value = uuid.UUID(text)
    result = GUID(value.fields[0], value.fields[1], value.fields[2])
    result.Data4 = (ctypes.c_ubyte * 8)(*value.bytes[8:])
    return result


_prototypes = {}


def vcall(ptr, index, argtypes, *args, what="COM call"):
    """Call vtable slot `index` of the COM interface pointer `ptr` (a c_void_p)
    with `args` typed as `argtypes`. Returns the HRESULT; raises ComError when
    it is a failure."""
    argtypes = tuple(argtypes)
    prototype = _prototypes.get(argtypes)
    if prototype is None:
        prototype = _prototypes[argtypes] = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                                               *argtypes)
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    hresult = prototype(vtable[index])(ptr, *args)
    if hresult < 0:
        raise ComError(hresult, what)
    return hresult


class Interface:
    """A COM interface pointer this module owns one reference to."""

    def __init__(self, ptr):
        self.ptr = ptr if isinstance(ptr, ctypes.c_void_p) else ctypes.c_void_p(ptr)

    def call(self, index, argtypes, *args, what="COM call"):
        return vcall(self.ptr, index, argtypes, *args, what=what)

    def release(self):
        if self.ptr and self.ptr.value:
            try:
                vcall(self.ptr, RELEASE, ())
            except Exception:
                pass
        self.ptr = ctypes.c_void_p()


_ole32_dll = None
_kernel32_dll = None


def _ole32():
    global _ole32_dll
    if _ole32_dll is None:
        dll = ctypes.WinDLL("ole32")
        dll.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]
        dll.CoInitializeEx.restype = ctypes.c_long
        dll.CoUninitialize.argtypes = []
        dll.CoUninitialize.restype = None
        dll.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD,
                                         ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        dll.CoCreateInstance.restype = ctypes.c_long
        dll.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        dll.CoTaskMemFree.restype = None
        _ole32_dll = dll
    return _ole32_dll


def _kernel32():
    global _kernel32_dll
    if _kernel32_dll is None:
        dll = ctypes.WinDLL("kernel32")
        dll.LCIDToLocaleName.argtypes = [wt.DWORD, ctypes.c_wchar_p, ctypes.c_int, wt.DWORD]
        dll.LCIDToLocaleName.restype = ctypes.c_int
        _kernel32_dll = dll
    return _kernel32_dll


def create(clsid, iid, what="CoCreateInstance"):
    ptr = ctypes.c_void_p()
    hresult = _ole32().CoCreateInstance(ctypes.byref(guid(clsid)), None, CLSCTX_ALL,
                                        ctypes.byref(guid(iid)), ctypes.byref(ptr))
    if hresult < 0:
        raise ComError(hresult, what)
    return Interface(ptr)


def take_string(ptr):
    """The text of a COM-allocated LPWSTR out-parameter, which is then freed."""
    if not ptr or not ptr.value:
        return ""
    try:
        return ctypes.wstring_at(ptr.value)
    finally:
        _ole32().CoTaskMemFree(ptr)


def lcid_to_tag(text):
    """SAPI's Language attribute ("409" or "409;9", hex LCIDs) as a BCP-47 tag."""
    first = str(text or "").split(";")[0].strip()
    if not first:
        return ""
    try:
        lcid = int(first, 16)
    except ValueError:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(85)
        if _kernel32().LCIDToLocaleName(lcid, buf, 85, 0):
            return buf.value
    except Exception:
        pass
    return ""


# ------------------------------------------------------------
# SAPI, used only on the worker thread
# ------------------------------------------------------------

class Sapi:
    """One SpVoice and the voice tokens it has used. Create, use and close it
    on the same thread."""

    def __init__(self):
        hresult = _ole32().CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        if hresult < 0 and hresult != RPC_E_CHANGED_MODE:
            raise ComError(hresult, "CoInitializeEx")
        self._uninitialize = hresult >= 0
        self._tokens = {}
        self._voice_id = None
        try:
            self.voice = create(CLSID_SpVoice, IID_ISpVoice, "creating the SAPI voice")
        except Exception:
            self._end_com()
            raise

    # --- listing -------------------------------------------------------------

    def list_voices(self):
        voices, ids, names = [], set(), set()
        for category in VOICE_CATEGORIES:
            try:
                tokens = self._category_tokens(category)
            except ComError as e:
                logger.debug(f"Windows voices: no voices in {category}: {e}")
                continue
            for token in tokens:
                try:
                    info = self._describe(token)
                except ComError as e:
                    logger.debug(f"Windows voices: skipped a voice: {e}")
                    info = None
                finally:
                    token.release()
                if not info:
                    continue
                # A voice registered in both categories is listed once.
                name_key = (info["name"].lower(), info["language"].lower())
                if info["id"] in ids or name_key in names:
                    continue
                ids.add(info["id"])
                names.add(name_key)
                voices.append(info)
        return voices

    def _category_tokens(self, category_id):
        category = create(CLSID_SpObjectTokenCategory, IID_ISpObjectTokenCategory,
                          "creating a voice category")
        try:
            category.call(CATEGORY_SET_ID, (ctypes.c_wchar_p, wt.BOOL), category_id, False,
                          what="ISpObjectTokenCategory::SetId")
            enum_ptr = ctypes.c_void_p()
            category.call(CATEGORY_ENUM_TOKENS,
                          (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)),
                          None, None, ctypes.byref(enum_ptr), what="EnumTokens")
            tokens = Interface(enum_ptr)
            try:
                count = wt.ULONG()
                tokens.call(ENUM_GET_COUNT, (ctypes.POINTER(wt.ULONG),), ctypes.byref(count),
                            what="IEnumSpObjectTokens::GetCount")
                result = []
                for index in range(count.value):
                    token_ptr = ctypes.c_void_p()
                    tokens.call(ENUM_ITEM, (wt.ULONG, ctypes.POINTER(ctypes.c_void_p)), index,
                                ctypes.byref(token_ptr), what="IEnumSpObjectTokens::Item")
                    result.append(Interface(token_ptr))
                return result
            finally:
                tokens.release()
        finally:
            category.release()

    @staticmethod
    def _string(key, value_name):
        out = ctypes.c_void_p()
        try:
            key.call(DATAKEY_GET_STRING_VALUE, (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)),
                     value_name, ctypes.byref(out), what="GetStringValue")
        except ComError:
            return ""
        return take_string(out).strip()

    def _describe(self, token):
        out = ctypes.c_void_p()
        token.call(TOKEN_GET_ID, (ctypes.POINTER(ctypes.c_void_p),), ctypes.byref(out),
                   what="ISpObjectToken::GetId")
        token_id = take_string(out)
        if not token_id:
            return None
        display = self._string(token, None)
        name = language = ""
        attributes_ptr = ctypes.c_void_p()
        try:
            token.call(DATAKEY_OPEN_KEY, (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)),
                       "Attributes", ctypes.byref(attributes_ptr), what="OpenKey")
        except ComError:
            attributes_ptr = None
        if attributes_ptr:
            attributes = Interface(attributes_ptr)
            try:
                name = self._string(attributes, "Name")
                language = lcid_to_tag(self._string(attributes, "Language"))
            finally:
                attributes.release()
        # "Microsoft Zira Desktop - English (United States)": the language has
        # its own column, so the name alone.
        name = name or display.split(" - ")[0].strip() or token_id.rsplit("\\", 1)[-1]
        return {"id": token_id, "name": name, "language": language}

    # --- speaking --------------------------------------------------------------

    def _token(self, voice_id):
        token = self._tokens.get(voice_id)
        if token is None:
            token = create(CLSID_SpObjectToken, IID_ISpObjectToken, "creating a voice token")
            try:
                token.call(TOKEN_SET_ID, (ctypes.c_wchar_p, ctypes.c_wchar_p, wt.BOOL),
                           None, voice_id, False, what="ISpObjectToken::SetId")
            except Exception:
                token.release()
                raise
            self._tokens[voice_id] = token
        return token

    def set_voice(self, voice_id):
        """Use the voice with this token id; "" is the Windows default voice."""
        if voice_id == self._voice_id:
            return
        pointer = self._token(voice_id).ptr if voice_id else None
        self.voice.call(VOICE_SET_VOICE, (ctypes.c_void_p,), pointer, what="ISpVoice::SetVoice")
        self._voice_id = voice_id

    def speak(self, text, rate, volume):
        """Start speaking `text` (plain text, never SAPI XML) and return."""
        self.voice.call(VOICE_SET_RATE, (ctypes.c_long,), int(rate), what="ISpVoice::SetRate")
        self.voice.call(VOICE_SET_VOLUME, (ctypes.c_ushort,), int(volume),
                        what="ISpVoice::SetVolume")
        self.voice.call(VOICE_SPEAK, (ctypes.c_wchar_p, wt.DWORD, ctypes.c_void_p), text,
                        SPF_ASYNC | SPF_PURGEBEFORESPEAK | SPF_IS_NOT_XML, None,
                        what="ISpVoice::Speak")

    def purge(self):
        """Stop speaking now."""
        self.voice.call(VOICE_SPEAK, (ctypes.c_wchar_p, wt.DWORD, ctypes.c_void_p), None,
                        SPF_ASYNC | SPF_PURGEBEFORESPEAK, None, what="ISpVoice::Speak (purge)")

    def is_done(self):
        return self.voice.call(VOICE_WAIT_UNTIL_DONE, (wt.ULONG,), 0,
                               what="ISpVoice::WaitUntilDone") == S_OK

    def close(self):
        for token in self._tokens.values():
            token.release()
        self._tokens.clear()
        self.voice.release()
        self._end_com()

    def _end_com(self):
        if self._uninitialize:
            self._uninitialize = False
            _ole32().CoUninitialize()


# ------------------------------------------------------------
# The worker thread
# ------------------------------------------------------------

def _finish(on_done, error):
    if on_done is None:
        return
    try:
        on_done(error)
    except Exception:
        logger.exception("Windows voices: an on_done callback failed")


class Worker:
    """Runs a Sapi on its own thread. Requests: speak, stop, call(fn)."""

    def __init__(self, engine_factory=Sapi):
        self._factory = engine_factory
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._thread = None
        self._failed = None
        self._failed_at = 0.0

    def available(self):
        return self._failed is None or time.monotonic() - self._failed_at > RETRY_SECONDS

    def _post(self, item, start=True):
        with self._lock:
            if self._thread is None:
                if not start:
                    return False
                self._thread = threading.Thread(target=self._run, daemon=True,
                                                name="hariku-voice-sapi")
                self._thread.start()
            self._queue.put(item)
            return True

    def call(self, fn, timeout=LIST_TIMEOUT_SECONDS):
        """Run fn(engine) on the worker; its result, or what it raised."""
        box, ready = {}, threading.Event()
        self._post(("call", fn, box, ready))
        if not ready.wait(timeout):
            raise TimeoutError("Windows voices did not answer in time")
        if "error" in box:
            raise box["error"]
        return box["result"]

    def speak(self, text, voice_id, rate, volume, on_done):
        self._post(("speak", (text, voice_id, rate, volume), on_done))

    def stop(self):
        self._post(("stop",), start=False)

    def shutdown(self):
        self._post(("exit",), start=False)

    def _run(self):
        from core.voice import _pump_messages
        engine, start_error = None, None
        try:
            engine = self._factory()
            self._failed = None
        except Exception as e:
            start_error = e
            self._failed, self._failed_at = e, time.monotonic()
            logger.warning(f"Windows voices are not available: {e}")
        current = None                 # on_done of the speech in progress
        last_used = time.monotonic()
        try:
            while True:
                try:
                    item = self._queue.get(timeout=POLL_SECONDS)
                except queue.Empty:
                    item = None
                if item is not None:
                    last_used = time.monotonic()
                    op = item[0]
                    if op in ("speak", "stop", "exit") and current is not None:
                        self._purge(engine)
                        _finish(current, None)
                        current = None
                    if op == "speak":
                        current = self._start(engine, start_error, *item[1], item[2])
                    elif op == "call":
                        self._call(engine, start_error, *item[1:])
                    elif op == "exit":
                        with self._lock:
                            if self._queue.empty():
                                self._thread = None
                                break
                if current is not None:
                    try:
                        finished, error = engine.is_done(), None
                    except Exception as e:
                        finished, error = True, e
                    if finished:
                        _finish(current, error)
                        current = None
                    last_used = time.monotonic()
                _pump_messages()
                if current is None and time.monotonic() - last_used > IDLE_EXIT_SECONDS:
                    with self._lock:
                        if self._queue.empty():
                            self._thread = None
                            break
        finally:
            if current is not None:
                _finish(current, None)
            if engine is not None:
                try:
                    engine.close()
                except Exception:
                    logger.exception("Windows voices: closing SAPI failed")

    @staticmethod
    def _purge(engine):
        try:
            engine.purge()
        except Exception as e:
            logger.debug(f"Windows voices: stopping failed: {e}")

    def _start(self, engine, start_error, text, voice_id, rate, volume, on_done):
        if engine is None:
            _finish(on_done, start_error)
            return None
        try:
            engine.set_voice(voice_id or "")
            engine.speak(text, rate, volume)
        except Exception as e:
            _finish(on_done, e)
            return None
        return on_done

    @staticmethod
    def _call(engine, start_error, fn, box, ready):
        try:
            if engine is None:
                raise start_error
            box["result"] = fn(engine)
        except Exception as e:
            box["error"] = e
        ready.set()


_worker = Worker()


def list_voices():
    """Every SAPI voice on this computer, [{"id", "name", "language"}]. Blocks
    until the worker answers."""
    return _worker.call(lambda engine: engine.list_voices())


def speak(text, voice_id, rate, volume, on_done):
    _worker.speak(text, voice_id, rate, volume, on_done)


def stop():
    _worker.stop()


def is_available():
    return _worker.available()


def shutdown():
    _worker.shutdown()
