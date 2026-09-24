# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import wx
import wx.adv
import json
import os
import uuid
import datetime
import threading
import time
import logging
import core.api
import core.personal
from core.events import bus

logger = logging.getLogger(__name__)

REMINDERS_DIR = core.api.get_storage_dir("CoreReminders")
REMINDERS_FILE = os.path.join(REMINDERS_DIR, "reminders.json")

active_notifications = {}
_daemon_running = False

# [Stability] Missed reminders that came due while the app was closed/asleep are
# still fired when it next runs, as long as they are no older than this window.
# Older overdue reminders are marked seen silently to avoid a flood of dialogs.
CATCHUP_WINDOW = datetime.timedelta(hours=24)

def load_reminders():
    """[Stability] Load reminders. Only if the main file EXISTS but is corrupt
    does it fall back to the '.bak' backup; a missing file means 'no reminders'."""
    if not os.path.exists(REMINDERS_FILE):
        return []
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load reminders: {e}")
        bak = REMINDERS_FILE + ".bak"
        if os.path.exists(bak):
            try:
                with open(bak, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.warning("Reminders file was corrupt; recovered from backup (.bak).")
                return data
            except Exception as e2:
                logger.error(f"Reminders backup also failed to load: {e2}")
    return []

def expanded_copy(r):
    """A copy of reminder `r` for announcing or showing it: %placeholders% in its
    title and notes are filled in from the profile. The stored text stays raw."""
    shown = dict(r)
    for key in ("title", "notes"):
        if isinstance(shown.get(key), str):
            shown[key] = core.personal.expand(shown[key])
    return shown

def get_reminders_for_date(date_str):
    reminders = load_reminders()
    day_reminders = []
    for r in reminders:
        if r.get("date") == date_str:
            day_reminders.append(r)
        elif (not r.get("is_done")) and r.get("recurrence", "none") != "none" \
                and _recurring_hits(r, date_str):
            # [Recurring] Show a display-only copy of the reminder on this
            # matching date (firing still uses the stored next-occurrence date).
            virtual = dict(r)
            virtual["date"] = date_str
            day_reminders.append(virtual)

    # Allow extensions to inject items into the agenda
    payload = {"date": date_str, "reminders": day_reminders}
    bus.emit("on_fetch_agenda", payload)

    return payload["reminders"]

def save_reminders(reminders):
    try:
        core.api.atomic_write_json(REMINDERS_FILE, reminders)
    except Exception as e:
        logger.error(f"Failed to save reminders: {e}")

RECURRENCES = ("none", "daily", "weekly", "monthly", "yearly")

def add_reminder(title, date_str, time_str, recurrence="none", interval=1):
    reminders = load_reminders()
    reminders.append({
        "id": str(uuid.uuid4()),
        "title": title,
        "date": date_str,
        "time": time_str,
        "is_done": False,
        "recurrence": recurrence if recurrence in RECURRENCES else "none",
        "interval": max(1, int(interval or 1)),
    })
    save_reminders(reminders)

def mark_as_done(rem_id):
    reminders = load_reminders()
    for r in reminders:
        if r["id"] == rem_id:
            r["is_done"] = True
            save_reminders(reminders)
            
            from core.speech import speak
            speak(f"Reminder '{core.personal.expand(r['title'])}' marked as done.", interrupt=True)
            break

def delete_reminder(rem_id):
    reminders = load_reminders()
    new_reminders = [r for r in reminders if r["id"] != rem_id]
    save_reminders(new_reminders)
    
    # Notify extensions that an item was requested to be deleted
    from core.events import bus
    bus.emit("on_agenda_item_deleted", rem_id)
    
    from core.speech import speak
    speak("Reminder deleted.", interrupt=True)

def snooze_reminder(rem_id, minutes=5):
    import datetime
    reminders = load_reminders()
    for r in reminders:
        if r["id"] == rem_id:
            # Snooze relative to NOW (handles reminders fired late via catch-up).
            new_dt = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
            r["date"] = new_dt.strftime("%Y-%m-%d")
            r["time"] = new_dt.strftime("%H:%M")
            # Re-arm so the daemon fires it again at the new time.
            r["notified"] = False
            r.pop("notified_at", None)
            save_reminders(reminders)
            
            from core.speech import speak
            speak(f"Reminder '{core.personal.expand(r['title'])}' snoozed for {minutes} minutes.", interrupt=True)
            break

class ReminderDialog(wx.Dialog):
    def __init__(self, parent, reminder_data):
        super().__init__(parent, title="Hariku Reminder", size=(350, 150))
        self.reminder_data = reminder_data
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label=f"Reminder: {reminder_data['title']}")
        font = lbl.GetFont()
        font.SetPointSize(12)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        lbl.SetFont(font)
        
        # Wrap the label text if it is too long.
        lbl.Wrap(300)
        vbox.Add(lbl, 1, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 20)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        btn_snooze = wx.Button(self, label="Snooze (5 min)")
        btn_done = wx.Button(self, label="Mark as Done")
        btn_done.SetDefault()
        
        hbox.Add(btn_snooze, 0, wx.RIGHT, 10)
        hbox.Add(btn_done, 0, wx.LEFT, 10)
        
        vbox.Add(hbox, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 15)
        
        self.SetSizer(vbox)
        self.CentreOnParent()
        
        btn_snooze.Bind(wx.EVT_BUTTON, self.OnSnooze)
        btn_done.Bind(wx.EVT_BUTTON, self.OnDone)
        
    def OnSnooze(self, event):
        self.EndModal(1)
        
    def OnDone(self, event):
        self.EndModal(2)

def show_notification(r):
    # Speak and show the text with the profile's %placeholders% filled in; the
    # event and the stored reminder keep the raw text.
    shown = expanded_copy(r)
    message = f"Reminder: {shown['title']}"

    # Let extensions (e.g. Routines) react to a reminder firing.
    try:
        bus.emit("on_reminder_fired", r)
    except Exception:
        pass

    top_window = wx.GetApp().GetTopWindow()
    if not top_window: return
    
    from core.speech import speak
    speak(message, interrupt=True)
    
    from core.sounds import play_sound
    play_sound(r"C:\Windows\Media\Windows Notify Calendar.wav")
    
    dlg = ReminderDialog(top_window, shown)
    dlg.Raise()
    result = dlg.ShowModal()
    
    if result == 1:
        snooze_reminder(r["id"], 5)
    elif result == 2:
        mark_as_done(r["id"])
        
    dlg.Destroy()

def _add_months(d, months):
    """Add whole months to a datetime, clamping the day to the target month's end
    (e.g. Jan 31 + 1 month -> Feb 28/29)."""
    import calendar
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return d.replace(year=y, month=m, day=day)


def _next_occurrence(date_str, time_str, recurrence, interval, now):
    """[Recurring] Return the next occurrence date (YYYY-MM-DD) strictly AFTER
    `now`, advancing from (date_str, time_str) by `interval` steps of the given
    recurrence. Skips over any missed occurrences so a long-overdue recurring
    reminder re-arms once to the next future slot instead of firing repeatedly."""
    try:
        dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except (ValueError, KeyError, TypeError):
        return date_str
    interval = max(1, int(interval or 1))

    def step(d):
        if recurrence == "daily":
            return d + datetime.timedelta(days=interval)
        if recurrence == "weekly":
            return d + datetime.timedelta(weeks=interval)
        if recurrence == "monthly":
            return _add_months(d, interval)
        if recurrence == "yearly":
            return _add_months(d, 12 * interval)
        return d

    guard = 0
    while dt <= now and guard < 10000:
        nxt = step(dt)
        if nxt <= dt:   # safety: unknown recurrence / no progress
            break
        dt = nxt
        guard += 1
    return dt.strftime("%Y-%m-%d")


def _recurring_hits(r, target_str):
    """[Recurring] Does recurring reminder `r` fall on the date `target_str`
    (other than its own stored date)? Lets the agenda show it on every matching
    day, not only its next stored occurrence. Congruence is taken from the
    stored date, which stays in the same class as it re-arms."""
    rec = r.get("recurrence", "none")
    if rec == "none":
        return False
    try:
        import calendar
        base = datetime.datetime.strptime(r["date"], "%Y-%m-%d").date()
        target = datetime.datetime.strptime(target_str, "%Y-%m-%d").date()
    except (ValueError, KeyError, TypeError):
        return False
    if target == base:
        return False  # exact-date match is handled separately
    interval = max(1, int(r.get("interval", 1) or 1))
    delta_days = (target - base).days
    if rec == "daily":
        return delta_days % interval == 0
    if rec == "weekly":
        return delta_days % (7 * interval) == 0
    if rec == "monthly":
        if target.day != min(base.day, calendar.monthrange(target.year, target.month)[1]):
            return False
        months = (target.year - base.year) * 12 + (target.month - base.month)
        return months % interval == 0
    if rec == "yearly":
        if (target.month != base.month or
                target.day != min(base.day, calendar.monthrange(target.year, base.month)[1])):
            return False
        return (target.year - base.year) % interval == 0
    return False


def _reminder_due_state(r, now):
    """
    [Catch-up] Pure decision helper (unit-tested): given reminder `r` and the
    current time `now`, decide what should happen. Returns one of:
      'skip'    - done, already notified (new 'notified' or legacy 'notified_at'),
                  or unparseable date/time
      'pending' - not due yet
      'fire'    - due now, or missed within CATCHUP_WINDOW -> show notification
      'stale'   - overdue beyond CATCHUP_WINDOW -> mark seen silently, no dialog
    """
    if r.get("is_done") or r.get("notified") or "notified_at" in r:
        return "skip"
    try:
        due = datetime.datetime.strptime(f"{r['date']} {r['time']}", "%Y-%m-%d %H:%M")
    except (ValueError, KeyError, TypeError):
        return "skip"
    if due > now:
        return "pending"
    return "fire" if (now - due) <= CATCHUP_WINDOW else "stale"


def _reminder_loop():
    while _daemon_running:
        reminders = load_reminders()
        now = datetime.datetime.now()

        modified = False
        for r in reminders:
            state = _reminder_due_state(r, now)
            if state not in ("fire", "stale"):
                continue
            if state == "fire":
                wx.CallAfter(show_notification, r)
            else:
                logger.info(f"Skipping stale reminder '{r.get('title', '')}' due {r.get('date')} {r.get('time')}")

            rec = r.get("recurrence", "none")
            if rec and rec != "none":
                # [Recurring] Re-arm to the next future occurrence instead of ending.
                r["date"] = _next_occurrence(r["date"], r["time"], rec, r.get("interval", 1), now)
                r["notified"] = False
                r.pop("notified_at", None)
            else:
                r["notified"] = True
            modified = True

        if modified:
            save_reminders(reminders)

        time.sleep(30)

def init(bus):
    global _daemon_running
    if not _daemon_running:
        _daemon_running = True
        t = threading.Thread(target=_reminder_loop, daemon=True)
        t.start()
        
        def stop_daemon():
            global _daemon_running
            _daemon_running = False
            
        bus.subscribe("on_unload", stop_daemon)
