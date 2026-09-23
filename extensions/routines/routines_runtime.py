# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Glue for the Routines extension: persistence, current-state context, the
# trigger evaluation loop wired to the V2 event bus, action execution, and
# registration. Pure trigger logic is in engine.py; action runners in actions.py;
# UI in ui.py (imported lazily to avoid an import cycle).
import logging
import threading
import datetime
import time

import core.api
import core.hotkeys
from core.events import bus

import routines_engine as engine
import routines_actions as actions

logger = logging.getLogger(__name__)

DATA_KEY = "Routines"
_variables = {}       # magic-variable store
_met_last = {}        # routine_id -> was-met-last-check (rising-edge trigger)
_run_every_last = {}  # routine_id -> epoch ts of last fire (for run_every)
_prev_cpu_times = None  # (idle, kernel, user) FILETIME totals for CPU% delta

# --- In-memory execution log (last N runs; shown by the log viewer) ---
_LOG = []
_LOG_LOCK = threading.Lock()
_LOG_MAX = 100

_EVENTS = ["on_minute_tick", "on_clipboard_changed", "on_power_changed",
           "on_active_window_changed", "on_user_idle", "on_user_active",
           "on_network_changed"]


# --- Persistence ---
def load_routines():
    data = core.api.load_data(DATA_KEY)
    return data.get("routines", []) if isinstance(data, dict) else []


def save_routines(routines):
    core.api.save_data(DATA_KEY, {"routines": routines})


# --- System-state helpers (every syscall wrapped; robust fallbacks) ---
def _get_reminders_today(date_str):
    try:
        import core.reminders
        return core.reminders.get_reminders_for_date(date_str) or []
    except Exception:
        return []


_SSID_CACHE_SECONDS = 30
_ssid_cache = (0.0, "")


def _get_wifi_ssid():
    """Current Wi-Fi SSID, cached for a short while because `netsh` takes a few
    hundred milliseconds and evaluation runs on the UI thread."""
    global _ssid_cache
    stamp, ssid = _ssid_cache
    if time.time() - stamp < _SSID_CACHE_SECONDS:
        return ssid
    ssid = _query_wifi_ssid()
    _ssid_cache = (time.time(), ssid)
    return ssid


def _query_wifi_ssid():
    """Current Wi-Fi SSID via `netsh wlan show interfaces`, or "" if unknown."""
    try:
        import subprocess
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
            startupinfo=si, timeout=5)
        if result.returncode != 0:
            return ""
        state = ""
        ssid = ""
        for line in result.stdout.splitlines():
            s = line.strip()
            if s.startswith("State") and ":" in s:
                state = s.split(":", 1)[1].strip().lower()
            elif s.startswith("SSID") and not s.startswith("BSSID") and ":" in s:
                val = s.split(":", 1)[1].strip()
                if val:
                    ssid = val
        return ssid if "connected" in state else ""
    except Exception:
        return ""


def _get_ram_percent():
    """RAM load percentage via GlobalMemoryStatusEx, or None."""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.dwMemoryLoad)
    except Exception:
        pass
    return None


def _get_cpu_percent():
    """System CPU usage %, computed from the delta between consecutive
    GetSystemTimes samples. Returns None on the first sample (no baseline)."""
    global _prev_cpu_times
    try:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD),
                        ("dwHighDateTime", wintypes.DWORD)]

        idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
        ok = ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        if not ok:
            return None

        def _q(ft):
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

        cur = (_q(idle), _q(kernel), _q(user))
        prev = _prev_cpu_times
        _prev_cpu_times = cur
        if prev is None:
            return None
        idle_d = cur[0] - prev[0]
        # kernel time already includes idle time; total busy = (kernel+user) - idle
        total_d = (cur[1] - prev[1]) + (cur[2] - prev[2])
        if total_d <= 0:
            return None
        busy = total_d - idle_d
        return max(0, min(100, int(round(100.0 * busy / total_d))))
    except Exception:
        return None


# Context fields that are slow to collect, and what in a routine asks for them.
_COSTLY_FIELDS = {
    "wifi_ssid": ("wifi_ssid", "{ssid}"),
    "ram_percent": ("ram_above", "{ram}"),
    "cpu_percent": ("cpu_above", "{cpu}"),
}


def _costly_fields_needed(routines):
    """Which slow context fields any of these routines reads, through a condition
    type or a placeholder in one of its text parameters."""
    needed = set()
    for routine in routines:
        items = (routine.get("conditions") or []) + (routine.get("actions") or [])
        types = {item.get("type") for item in items}
        texts = " ".join(str(v) for item in items
                         for v in (item.get("params") or {}).values()
                         if isinstance(v, str))
        for field, (cond_type, token) in _COSTLY_FIELDS.items():
            if cond_type in types or token in texts:
                needed.add(field)
    return needed


# --- Current-state context (add new fields here for new conditions) ---
def build_context(event=None, event_data=None, needed=None):
    """Snapshot of system state for routine evaluation. `needed` limits the slow
    fields (see _COSTLY_FIELDS) to those a routine uses; None collects all."""
    def want(field):
        return needed is None or field in needed

    now = datetime.datetime.now()
    try:
        power = core.api.get_power_status()
    except Exception:
        power = {"battery_percent": 255, "charging": False}
    battery = power.get("battery_percent")
    if battery in (255, None):
        battery = None
    try:
        win = core.api.get_active_window_info()
    except Exception:
        win = {"title": "", "process": ""}
    try:
        idle = core.api.get_user_idle_time()
    except Exception:
        idle = 0.0
    try:
        clip = core.api.get_clipboard()
    except Exception:
        clip = ""
    try:
        online = core.api.is_network_online()
    except Exception:
        online = True
    date_str = now.strftime("%Y-%m-%d")
    return {
        "now_hm": now.strftime("%H:%M"),
        "now_ts": time.time(),
        "weekday": now.weekday(),
        "date": date_str,
        "battery": battery,
        "charging": bool(power.get("charging")),
        "idle_seconds": idle,
        "active_process": win.get("process", ""),
        "active_title": win.get("title", ""),
        "clipboard": clip,
        "online": online,
        "reminders_today": _get_reminders_today(date_str),
        "wifi_ssid": _get_wifi_ssid() if want("wifi_ssid") else "",
        "ram_percent": _get_ram_percent() if want("ram_percent") else None,
        "cpu_percent": _get_cpu_percent() if want("cpu_percent") else None,
        "event": event,             # set only when triggered by a specific event
        "event_data": event_data,   # e.g. the selected date or the fired reminder
    }


# --- Execution log ---
def _log_add(name, source, errors):
    entry = {"ts": time.time(),
             "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "name": name or "Untitled",
             "source": source,
             "errors": list(errors or [])}
    with _LOG_LOCK:
        _LOG.append(entry)
        if len(_LOG) > _LOG_MAX:
            del _LOG[:len(_LOG) - _LOG_MAX]


def get_log():
    """A copy of the execution log (oldest first). The viewer reverses it."""
    with _LOG_LOCK:
        return list(_LOG)


def clear_log():
    with _LOG_LOCK:
        _LOG.clear()


# --- Execution ---
def _run_actions(routine, ctx, source="auto"):
    name = routine.get("name", "Untitled")

    def worker():
        errors = []
        for action in routine.get("actions", []):
            fn = actions.ACTION_RUNNERS.get(action.get("type"))
            if not fn:
                continue
            try:
                fn(action.get("params", {}), ctx, _variables)
            except Exception as e:
                logger.error(f"[Routines] action '{action.get('type')}' failed: {e}")
                errors.append(f"{action.get('type')}: {e}")
        _log_add(name, source, errors)

    threading.Thread(target=worker, daemon=True).start()


def _has_run_every(routine):
    return any(c.get("type") == "run_every"
               for c in (routine.get("conditions") or []))


def evaluate_all(*_args, event=None, event_data=None, **_kwargs):
    # Runs on the UI thread for every monitored event, so do no work at all
    # unless some routine is enabled, and collect slow state only on demand.
    try:
        routines = load_routines()
        active = [r for r in routines if r.get("enabled", True)]
        if not active:
            for routine in routines:
                _met_last[routine.get("id")] = False
            return
        ctx = build_context(event=event, event_data=event_data,
                            needed=_costly_fields_needed(active))
        for routine in routines:
            rid = routine.get("id")
            # Inject this routine's own last-fire time so _c_run_every can decide.
            ctx["run_every_last"] = _run_every_last.get(rid)
            if engine.should_fire(routine, ctx, _met_last):
                logger.info(f"[Routines] '{routine.get('name')}' triggered.")
                if _has_run_every(routine):
                    _run_every_last[rid] = ctx.get("now_ts")
                _run_actions(routine, ctx, "auto")
    except Exception as e:
        logger.error(f"[Routines] evaluate_all error: {e}")


def run_now(routine):
    _run_actions(routine, build_context(), "manual")


# --- Event-based triggers: fire on the bus event itself (not state polling) ---
def _ev_startup(*_a, **_k):
    evaluate_all(event="app_startup")


def _ev_date_selected(*a, **_k):
    evaluate_all(event="date_selected", event_data=(a[0] if a else None))


def _ev_reminder_fired(*a, **_k):
    evaluate_all(event="reminder_fired", event_data=(a[0] if a else None))


_EVENT_TRIGGERS = [
    ("on_app_startup", _ev_startup),
    ("on_date_changed", _ev_date_selected),
    ("on_reminder_fired", _ev_reminder_fired),
]


def _open_manage():
    import routines_ui as ui  # lazy import to avoid a cycle (ui imports runtime)
    ui.open_manage_dialog()


def _open_log():
    import routines_log_viewer as log_viewer  # lazy import (log_viewer imports runtime)
    parent = getattr(core.api, "main_window_instance", None)
    log_viewer.show_log(parent)


# --- Registration ---
def register(_bus):
    logger.info("Routines extension loaded.")
    for ev in _EVENTS:
        bus.subscribe(ev, evaluate_all)
    for name, handler in _EVENT_TRIGGERS:
        bus.subscribe(name, handler)
    core.hotkeys.register_action("Routines", "manage_routines",
                                 "Manage Routines (Shortcuts)", None, False, _open_manage)
    core.hotkeys.register_action("Routines", "view_routines_log",
                                 "View Routines Log", None, False, _open_log)


def teardown():
    for ev in _EVENTS:
        try:
            bus.unsubscribe(ev, evaluate_all)
        except Exception:
            pass
    for name, handler in _EVENT_TRIGGERS:
        try:
            bus.unsubscribe(name, handler)
        except Exception:
            pass
    logger.info("Routines extension unloaded.")
