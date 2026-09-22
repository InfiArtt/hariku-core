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

def get_reminders_for_date(date_str):
    reminders = load_reminders()
    day_reminders = [r for r in reminders if r["date"] == date_str]
    
    # Allow extensions to inject items into the agenda
    payload = {"date": date_str, "reminders": day_reminders}
    bus.emit("on_fetch_agenda", payload)
    
    return payload["reminders"]

def save_reminders(reminders):
    try:
        core.api.atomic_write_json(REMINDERS_FILE, reminders)
    except Exception as e:
        logger.error(f"Failed to save reminders: {e}")

def add_reminder(title, date_str, time_str):
    reminders = load_reminders()
    reminders.append({
        "id": str(uuid.uuid4()),
        "title": title,
        "date": date_str,
        "time": time_str,
        "is_done": False
    })
    save_reminders(reminders)

def mark_as_done(rem_id):
    reminders = load_reminders()
    for r in reminders:
        if r["id"] == rem_id:
            r["is_done"] = True
            save_reminders(reminders)
            
            from core.speech import speak
            speak(f"Reminder '{r['title']}' marked as done.", interrupt=True)
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
            speak(f"Reminder '{r['title']}' snoozed for {minutes} minutes.", interrupt=True)
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
        
        # Bungkus text text wrap jika kepanjangan
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
    message = f"Reminder: {r['title']}"
    
    top_window = wx.GetApp().GetTopWindow()
    if not top_window: return
    
    from core.speech import speak
    speak(message, interrupt=True)
    
    from core.sounds import play_sound
    play_sound(r"C:\Windows\Media\Windows Notify Calendar.wav")
    
    dlg = ReminderDialog(top_window, r)
    dlg.Raise()
    result = dlg.ShowModal()
    
    if result == 1:
        snooze_reminder(r["id"], 5)
    elif result == 2:
        mark_as_done(r["id"])
        
    dlg.Destroy()

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
            if state == "fire":
                wx.CallAfter(show_notification, r)
                r["notified"] = True
                modified = True
            elif state == "stale":
                logger.info(f"Skipping stale reminder '{r.get('title', '')}' due {r.get('date')} {r.get('time')}")
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
