# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# ============================================================
# Routines engine — pure, dependency-free automation logic so it can be unit
# tested. iOS-Shortcuts-style: a routine has a list of CONDITIONS (all must be
# true = trigger) and a list of ACTIONS (run in order). This module only decides
# WHEN a routine should fire and expands text placeholders; the side-effecting
# action runners live in main.py (they need core.api / wx).
# ============================================================
import re

# ---- Condition checkers: each takes (params, ctx) -> bool -------------------
# ctx is a snapshot of current state gathered by main.py, e.g.:
#   {"now_hm": "08:00", "weekday": 0, "date": "2026-09-23",
#    "battery": 42, "charging": False, "idle_seconds": 12.0,
#    "active_process": "chrome.exe", "active_title": "…",
#    "clipboard": "…", "online": True}

def _c_time(params, ctx):
    return ctx.get("now_hm") == params.get("time")

def _c_day_of_week(params, ctx):
    return ctx.get("weekday") in (params.get("days") or [])

def _c_battery_below(params, ctx):
    b = ctx.get("battery")
    return b is not None and b <= int(params.get("value", 20))

def _c_battery_above(params, ctx):
    b = ctx.get("battery")
    return b is not None and b >= int(params.get("value", 80))

def _c_is_charging(params, ctx):
    return bool(ctx.get("charging")) == bool(params.get("charging", True))

def _c_user_idle(params, ctx):
    return (ctx.get("idle_seconds") or 0) >= int(params.get("minutes", 5)) * 60

def _c_app_active(params, ctx):
    want = (params.get("process") or "").strip().lower()
    return bool(want) and want in (ctx.get("active_process") or "").lower()

def _c_window_title(params, ctx):
    want = (params.get("text") or "").strip().lower()
    return bool(want) and want in (ctx.get("active_title") or "").lower()

def _c_clipboard_contains(params, ctx):
    want = params.get("text") or ""
    return bool(want) and want in (ctx.get("clipboard") or "")

def _c_online(params, ctx):
    return bool(ctx.get("online")) == bool(params.get("online", True))


def _c_run_every(params, ctx):
    """Fire every N minutes. Pure/ctx-driven: reads the current epoch time from
    ctx["now_ts"] and the routine's own last-fire time from ctx["run_every_last"]
    (runtime injects it per routine before evaluating, and stamps it when the
    routine fires). Returns True once the interval has elapsed; combined with the
    engine's rising-edge should_fire this yields exactly one fire per interval."""
    now_ts = ctx.get("now_ts")
    if now_ts is None:
        return False
    try:
        minutes = float(params.get("minutes", 5))
    except (TypeError, ValueError):
        return False
    interval = minutes * 60.0
    if interval <= 0:
        return False
    last = ctx.get("run_every_last")
    if last is None:
        return True  # never run before -> due now
    return (now_ts - last) >= interval


def _c_event_today(params, ctx):
    """True when a Hariku reminder exists for today. With optional text, only
    reminders whose title contains it count. Reads ctx["reminders_today"]."""
    reminders = ctx.get("reminders_today") or []
    want = (params.get("text") or "").strip().lower()
    if not want:
        return len(reminders) > 0
    for r in reminders:
        title = (r.get("title") or "") if isinstance(r, dict) else str(r)
        if want in title.lower():
            return True
    return False


def _c_wifi_ssid(params, ctx):
    """True when the current Wi-Fi network name contains the given text."""
    want = (params.get("text") or "").strip().lower()
    ssid = (ctx.get("wifi_ssid") or "").lower()
    return bool(want) and want in ssid


def _c_ram_above(params, ctx):
    r = ctx.get("ram_percent")
    return r is not None and r >= int(params.get("value", 80))


def _c_cpu_above(params, ctx):
    c = ctx.get("cpu_percent")
    return c is not None and c >= int(params.get("value", 80))


# --- Event triggers: true only during the bus event that set ctx["event"]. -----
# (app startup, calendar date selected, a reminder firing.)
def _c_on_startup(params, ctx):
    return ctx.get("event") == "app_startup"


def _c_on_date_selected(params, ctx):
    return ctx.get("event") == "date_selected"


def _c_on_reminder_fired(params, ctx):
    if ctx.get("event") != "reminder_fired":
        return False
    want = (params.get("text") or "").strip().lower()
    if not want:
        return True
    ev = ctx.get("event_data") or {}
    title = (ev.get("title") or "") if isinstance(ev, dict) else str(ev)
    return want in title.lower()


# Conditions that are event-driven (fire on the event, not by rising edge).
EVENT_CONDITION_TYPES = {"on_startup", "on_date_selected", "on_reminder_fired"}


CONDITION_CHECKERS = {
    "time": _c_time,
    "day_of_week": _c_day_of_week,
    "battery_below": _c_battery_below,
    "battery_above": _c_battery_above,
    "is_charging": _c_is_charging,
    "user_idle": _c_user_idle,
    "app_active": _c_app_active,
    "window_title": _c_window_title,
    "clipboard_contains": _c_clipboard_contains,
    "online": _c_online,
    "run_every": _c_run_every,
    "event_today": _c_event_today,
    "wifi_ssid": _c_wifi_ssid,
    "ram_above": _c_ram_above,
    "cpu_above": _c_cpu_above,
    "on_startup": _c_on_startup,
    "on_date_selected": _c_on_date_selected,
    "on_reminder_fired": _c_on_reminder_fired,
}

# Human labels for the UI (order matters).
CONDITION_LABELS = [
    ("time", "At a specific time (HH:MM)"),
    ("day_of_week", "On certain days of the week"),
    ("battery_below", "Battery at or below (%)"),
    ("battery_above", "Battery at or above (%)"),
    ("is_charging", "While charging / not charging"),
    ("user_idle", "After idle for N minutes"),
    ("app_active", "When an app is in focus"),
    ("window_title", "When the window title contains"),
    ("clipboard_contains", "When the clipboard contains"),
    ("online", "When online / offline"),
    ("run_every", "Run every N minutes"),
    ("event_today", "A reminder exists today"),
    ("wifi_ssid", "Connected to Wi-Fi network"),
    ("ram_above", "RAM usage at or above (%)"),
    ("cpu_above", "CPU usage at or above (%)"),
    ("on_startup", "When Hariku starts up"),
    ("on_date_selected", "When a date is selected"),
    ("on_reminder_fired", "When a reminder fires"),
]

ACTION_LABELS = [
    ("tts", "Speak text"),
    ("notification", "Show a notification"),
    ("open_url", "Open a URL"),
    ("play_sound", "Play a sound"),
    ("set_variable", "Set a variable"),
    ("delay", "Wait (seconds)"),
    ("open_app", "Open an app or command"),
    ("open_file", "Open a file"),
    ("lock_screen", "Lock the screen"),
    ("set_volume", "Set system volume"),
    ("copy_to_clipboard", "Copy text to clipboard"),
    ("type_text", "Type text into focused field"),
    ("add_reminder", "Add a Hariku reminder"),
    ("goto_date", "Go to a date in the calendar"),
    ("speak_agenda", "Speak the agenda for a day"),
    ("run_routine", "Run another routine"),
]


# Param specs for the UI: type -> list of (key, label, kind).
# kind in: text / int / bool / days. The UI renders fields from these, so adding
# a new condition/action = add its checker/runner + an entry here.
COND_SPECS = {
    "time": [("time", "Time (HH:MM)", "text")],
    "day_of_week": [("days", "Days", "days")],
    "battery_below": [("value", "Percent", "int")],
    "battery_above": [("value", "Percent", "int")],
    "is_charging": [("charging", "Must be charging", "bool")],
    "user_idle": [("minutes", "Idle minutes", "int")],
    "app_active": [("process", "Process (e.g. chrome.exe)", "text")],
    "window_title": [("text", "Title contains", "text")],
    "clipboard_contains": [("text", "Clipboard contains", "text")],
    "online": [("online", "Must be online", "bool")],
    "run_every": [("minutes", "Every N minutes", "int")],
    "event_today": [("text", "Title contains (optional)", "text")],
    "wifi_ssid": [("text", "Wi-Fi name contains", "text")],
    "ram_above": [("value", "Percent", "int")],
    "cpu_above": [("value", "Percent", "int")],
    "on_startup": [],
    "on_date_selected": [],
    "on_reminder_fired": [("text", "Reminder title contains (optional)", "text")],
}
ACTION_SPECS = {
    "tts": [("text", "Text to speak", "text")],
    "notification": [("title", "Title", "text"), ("message", "Message", "text")],
    "open_url": [("url", "URL (http/https)", "text")],
    "play_sound": [("sound", "Sound file (e.g. move.wav)", "text")],
    "set_variable": [("name", "Variable name", "text"), ("value", "Value", "text")],
    "delay": [("seconds", "Seconds", "int")],
    "open_app": [("path", "Program or command", "text")],
    "open_file": [("path", "File path", "text")],
    "lock_screen": [],
    "set_volume": [("level", "Volume (0-100)", "int")],
    "copy_to_clipboard": [("text", "Text to copy", "text")],
    "type_text": [("text", "Text to type", "text")],
    "add_reminder": [("title", "Reminder title", "text"),
                     ("time", "Time (HH:MM)", "text"),
                     ("date", "Date (YYYY-MM-DD, blank = today)", "text")],
    "goto_date": [("date", "Date (YYYY-MM-DD, blank = today)", "text")],
    "speak_agenda": [("date", "Date (YYYY-MM-DD, blank = today)", "text")],
    "run_routine": [("name", "Routine name", "text")],
}


def check_all_conditions(conditions, ctx):
    """A routine fires when EVERY condition is true (AND). No conditions => never
    auto-fires (it can still be Run Now)."""
    conditions = conditions or []
    if not conditions:
        return False
    for cond in conditions:
        fn = CONDITION_CHECKERS.get(cond.get("type"))
        if fn is None:
            return False
        try:
            if not fn(cond.get("params", {}), ctx):
                return False
        except Exception:
            return False
    return True


# Routines' own placeholder tokens, with a short description for the builder's
# "Insert placeholder" menu (order matters).
ROUTINE_TOKENS = [
    ("time", "current time"),
    ("date", "today's date"),
    ("battery", "battery level in percent"),
    ("app", "the program in focus"),
    ("clipboard", "the text on the clipboard"),
    ("ssid", "the Wi-Fi network name"),
    ("ram", "memory use in percent"),
    ("cpu", "processor use in percent"),
    ("events", "number of reminders today"),
]

# The pre-1.1 syntax, kept so existing routines keep working: {time} … {var:NAME}.
_BRACE_RE = re.compile(r"\{(%s|var:[^{}]*)\}" % "|".join(t for t, _d in ROUTINE_TOKENS))


def routine_token_values(ctx):
    """Current values of the Routines tokens, as text."""
    return {
        "time": ctx.get("now_hm", "") or "",
        "date": ctx.get("date", "") or "",
        "battery": str(ctx["battery"]) if ctx.get("battery") is not None else "",
        "app": ctx.get("active_process", "") or "",
        "clipboard": ctx.get("clipboard", "") or "",
        "ssid": ctx.get("wifi_ssid", "") or "",
        "ram": str(ctx["ram_percent"]) if ctx.get("ram_percent") is not None else "",
        "cpu": str(ctx["cpu_percent"]) if ctx.get("cpu_percent") is not None else "",
        "events": str(len(ctx.get("reminders_today") or [])),
    }


def process_placeholders(text, ctx, variables=None):
    """Expand iOS-Shortcuts-style magic tokens in `text`, in a single pass (an
    inserted value is never expanded again). Both syntaxes work:
       %time% %date% %battery% %app% %clipboard% %ssid% %ram% %cpu% %events%
       %var:NAME%, plus the profile's %myname%, %mynickname% and the user's own
       keys (core.personal; case-insensitive), and the older
       {time} … {events} {var:NAME} (exact case).
    Variables are looked up first, then the Routines tokens, then the profile.
    Unknown tokens are left as they are."""
    if not text:
        return text
    import core.personal  # core 2.7+
    variables = variables or {}
    tokens = routine_token_values(ctx)
    extra = dict(tokens)
    extra.update({"var:%s" % name: val for name, val in variables.items()})
    text = str(text)
    out, done = [], 0
    for m in _BRACE_RE.finditer(text):
        # Text between {…} tokens holds the %…% ones; each piece is expanded once.
        out.append(core.personal.expand(text[done:m.start()], extra))
        key = m.group(1)
        if key.startswith("var:"):
            name = key[4:]
            out.append(str(variables[name]) if name in variables else m.group(0))
        else:
            out.append(tokens[key])
        done = m.end()
    out.append(core.personal.expand(text[done:], extra))
    return "".join(out)


# --------------------------------------------------------------------------- #
# The builder's "Insert placeholder" menu (pure, so it's testable without wx).
# The profile part and Hariku's dynamic placeholders come from core.personal,
# which the Profile page's greeting field uses too.
# --------------------------------------------------------------------------- #
def placeholder_menu_entries(name="", nickname="", fields=(), variables=(), birthday="",
                             age="", title="", dynamic=None):
    """(token, label) pairs for the builder's Insert placeholder menu: the
    profile, the user's own keys, the Routines tokens, Hariku's dynamic
    placeholders and those extensions registered (core.personal.menu_entries),
    then this routine's variables. E.g. ("%myname%", "%myname%: your name (Rafli)")."""
    import core.personal  # core 2.7+
    entries = core.personal.menu_entries(name=name, nickname=nickname, title=title,
                                         birthday=birthday, age=age, fields=fields,
                                         tokens=ROUTINE_TOKENS, dynamic=dynamic)
    seen = set()
    for var in variables or ():
        var = str(var or "").strip()
        # "_…" names are internal (e.g. the run-routine depth guard).
        if not var or var.startswith("_") or "%" in var or var in seen:
            continue
        seen.add(var)
        entries.append(("%%var:%s%%" % var, "%%var:%s%%: the variable %s" % (var, var)))
    return entries


def insert_placeholder(value, start, end, token):
    """Put `token` into `value` at the caret, or in place of a partly selected
    stretch start..end (core.personal.insert_placeholder). Returns
    (new_value, caret after the token)."""
    import core.personal  # core 2.7+
    return core.personal.insert_placeholder(value, start, end, token)


def is_event_routine(routine):
    """True if any condition is an event trigger (startup / date selected /
    reminder fired). Such routines fire on the event itself, not by rising edge."""
    return any(c.get("type") in EVENT_CONDITION_TYPES
               for c in (routine.get("conditions") or []))


def should_fire(routine, ctx, met_last):
    """Decide whether a routine should run now.
    - EVENT routines (contain an event trigger) fire EVERY time their conditions
      match — the bus event that produced this ctx is the edge.
    - STATE routines use a rising edge: fire only when conditions transition from
      not-met to met, so they run once per trigger instead of every check.
    `met_last` is a dict {routine_id: bool} the caller keeps and this updates."""
    rid = routine.get("id")
    if not routine.get("enabled", True):
        met_last[rid] = False
        return False
    met = check_all_conditions(routine.get("conditions"), ctx)
    if is_event_routine(routine):
        met_last[rid] = False
        return met
    fire = met and not met_last.get(rid, False)
    met_last[rid] = met
    return fire
