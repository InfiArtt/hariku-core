# Hariku V2 — Extension Developer Guide

Welcome to the Hariku V2 extension development guide. This document covers everything you need to build, test, and distribute extensions for Hariku.

## Table of Contents

- [Quick Start](#quick-start)
- [Extension Structure](#extension-structure)
- [Manifest Reference](#manifest-reference)
- [API Reference](#api-reference)
  - [Speech](#speech)
  - [Data Storage](#data-storage)
  - [UI Dialogs](#ui-dialogs)
  - [Document Viewer](#document-viewer)
  - [Web View](#web-view)
  - [Calendar](#calendar)
  - [Clipboard](#clipboard)
  - [Timers & Threading](#timers--threading)
  - [Hotkeys](#hotkeys)
  - [Settings Panel](#settings-panel)
  - [Event Bus](#event-bus)
  - [Sounds](#sounds)
  - [Volume Control](#volume-control)
  - [Reminders](#reminders)
  - [Reminders from a Sentence](#reminders-from-a-sentence)
  - [Personal Profile](#personal-profile)
  - [Placeholders from Extensions](#placeholders-from-extensions)
  - [Quiet Hours](#quiet-hours)
  - [Places](#places)
  - [Hariku Voice](#hariku-voice)
  - [The Command Bar (Aruna)](#the-command-bar-aruna)
  - [Morning Briefing and Evening Summary](#morning-briefing-and-evening-summary)
  - [Translation (i18n)](#translation-i18n)
  - [Constants](#constants)
  - [App Utilities](#app-utilities)
  - [Main Window Access](#main-window-access)
  - [Extension Manager](#extension-manager)
  - [Extension Store](#extension-store)
  - [Telemetry](#telemetry)
- [Lifecycle Events](#lifecycle-events)
  - [Bus Events](#bus-events)
  - [The `teardown()` Function](#the-teardown-function)
- [Bundling Third-Party Libraries](#bundling-third-party-libraries)
- [Packaging & Distribution](#packaging--distribution)
- [Best Practices](#best-practices)
- [For Translators](#for-translators)
  - [Quick Reminder Languages](#quick-reminder-languages)

---

## Quick Start

1. **Copy** the `template_extension/` folder.
2. **Rename** the copied folder to your extension ID (e.g., `my_tool`).
3. **Edit** `manifest.json` with your extension's metadata.
4. **Write** your logic in `main.py`.
5. **Test** by placing the folder in the `extensions/` directory and running Hariku.
6. **Package** by running:
   ```
   python tools/packager.py my_tool
   ```

That's it! You'll get a `my_tool.hrk` file ready for distribution.

---

## Extension Structure

```
my_extension/
├── manifest.json       # Required — Extension metadata
├── main.py             # Required — Entry point (or whatever "main" points to)
├── my_helper.py        # Optional — Additional Python modules
├── sounds/             # Optional — Custom sound files (.wav)
│   └── notification.wav
├── locales/            # Optional — Translation files
│   ├── en.json
│   └── id.json
└── lib/                # Optional — Bundled third-party libraries
    └── some_library/
        └── __init__.py
```

- The `lib/` folder is automatically added to `sys.path` when your extension loads.
- You can have as many `.py` files as you want; just import them normally.
- **Give each extra `.py` file a name prefixed with your extension ID**, such as
  `my_extension_ui.py` rather than `ui.py`. Every extension's modules share one
  namespace, so a generic name like `ui`, `utils`, or `config` can silently
  resolve to one of Hariku's own packages, a standard library module, or another
  extension's file, and your import gets the wrong module.

---

## Manifest Reference

Every extension **must** have a `manifest.json` in its root folder.

```json
{
    "name": "My Extension",
    "version": "1.0",
    "author": "Your Name",
    "description": "A short description of what this extension does.",
    "main": "main.py",
    "language": "en",
    "minimum_core_version": "2.0"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✅ | Human-readable extension name |
| `version` | string | ✅ | Semantic version (e.g., `"1.0"`, `"2.3.1"`) |
| `author` | string | ✅ | Author name |
| `description` | string | ✅ | Short description |
| `main` | string | ✅ | Entry point filename (usually `"main.py"`) |
| `language` | string | ✅ | Language code (e.g., `"en"`, `"id"`) |
| `minimum_core_version` | string | ✅ | Minimum Hariku core version required (e.g., `"2.0"`) |
| `last_tested_core_version` | string | – | The newest Hariku you tested it with (e.g., `"2.8"`). Optional; see below |

**Compatibility.** Hariku doesn't load an extension that needs a newer core (`minimum_core_version`), and
the Extension Manager shows it, or a store update of it, as "Needs Hariku 2.9" instead of installing it.
Each core also has an oldest extension API it still runs, `core.constants.EXTENSION_API_BACK_COMPAT`
(currently `"1.0"`: no 2.x release has broken older extensions). An extension made for an older core
(its `last_tested_core_version`, or its `minimum_core_version` when it has none) is incompatible: Hariku
doesn't load it and lists it on the Extension Manager's Incompatible tab, as NVDA does for old add-ons.
When a core release does break older extensions, it raises that version; set `last_tested_core_version`
after testing with a new core so your extension keeps running. `tools/publish_extensions.py` copies both
fields into the store's registry (core 2.8+ reads them).

---

## API Reference

All core modules are available via standard Python imports. No installation needed.

### Speech

```python
from core.speech import speak, TOLK_LOADED
```

| Function / Variable | Description |
|---|---|
| `speak(text, interrupt=False)` | Speak text through the active screen reader (NVDA, JAWS, etc.). Set `interrupt=True` to cut off any current speech. *(core 2.7)* Right after the user runs your action from the command bar, Hariku Voice may say it instead (see [The Command Bar](#the-command-bar)); keep calling `speak()`, Hariku decides. |
| `braille(text, interrupt=False)` | *(core 2.7)* Show text on a braille display without speaking it (for text something else reads aloud). Follows the user's braille setting. |
| `silence()` | *(core 2.7)* Stop the screen reader's speech now, for example right before you listen to the microphone (through speakers it would talk into it). Braille is not affected. Returns whether the screen reader was asked. |
| `TOLK_LOADED` | Boolean — `True` if the Tolk speech engine loaded successfully, `False` otherwise. Useful for checking screen reader availability. |

**Example:**
```python
from core.speech import speak, TOLK_LOADED

if TOLK_LOADED:
    speak("Hello, world!")
    speak("Important message!", interrupt=True)
else:
    print("No screen reader detected.")
```

---

### Data Storage

```python
import core.api
```

| Function | Description |
|---|---|
| `core.api.load_data(name)` | Load a JSON dictionary for the given name. Returns `{}` if none exists. |
| `core.api.save_data(name, dict)` | Save a dictionary as JSON. Returns `True` / `False`. |
| `core.api.get_data_path(name)` | Get the absolute filesystem path to the JSON file. |
| `core.api.get_storage_dir(ext_id)` | Get a dedicated folder for storing large files (SQLite, images, etc.). The folder is created automatically if it doesn't exist. |

Data is stored in `%APPDATA%/Hariku2/data/` (compiled) or `hariku2/data/` (dev mode).

**Example:**
```python
# Save
config = core.api.load_data("MyExtension")
config["count"] = config.get("count", 0) + 1
core.api.save_data("MyExtension", config)

# Large file storage
storage = core.api.get_storage_dir("my_extension")
db_path = os.path.join(storage, "database.sqlite3")
```

---

### UI Dialogs

```python
import core.api
```

| Function | Returns | Description |
|---|---|---|
| `core.api.show_message(title, message)` | None | Show an informational dialog with OK button. |
| `core.api.show_toast(title, message, flags=wx.ICON_INFORMATION)` | None | Show a native Windows popup notification (Toast) in the bottom-right corner. It will auto-hide. |
| `core.api.prompt_yes_no(title, message)` | `True` / `False` | Ask a Yes/No question. |
| `core.api.prompt_text(title, message, default="")` | `str` or `None` | Ask for a single line of text. Returns `None` if cancelled. |
| `core.api.prompt_multiline(title, message, default="")` | `str` or `None` | Ask for multi-line text input. Returns `None` if cancelled. |

**Example:**
```python
name = core.api.prompt_text("Greeting", "What is your name?", "World")
if name:
    core.api.show_message("Hello", f"Nice to meet you, {name}!")
```

---

### Document Viewer

```python
from ui.document_viewer import show_document
```

| Function | Description |
|---|---|
| `show_document(parent, title, filename)` | Show a read-only text document in a dialog window. The viewer looks for the file in `docs/{current_language}/` first, then falls back to `docs/en/`. |

This is useful if your extension ships with documentation or help files.

**Example:**
```python
import core.api
from ui.document_viewer import show_document

# Show your extension's help file
parent = core.api.main_window_instance
show_document(parent, "My Extension Help", "my_extension_help.txt")
```

---

### Web View

```python
import core.api
```

Hariku memiliki sistem Web View bawaan yang memungkinkan extension menampilkan konten HTML — termasuk tabel, list, heading, dan link — di dalam jendela terpisah yang **mendukung penuh NVDA Browse Mode**.

Sistem ini berjalan di subprocess terisolasi, sehingga tidak bisa crash proses utama Hariku.

| Function | Returns | Description |
|---|---|---|
| `core.api.show_html_view(html_content, title, width, height)` | `True` / `False` | Render string HTML di jendela terpisah. Mendukung NVDA Browse Mode (H, T, L, K, I). |
| `core.api.show_html_file_view(html_path, title, width, height)` | `True` / `False` | Render file HTML yang sudah ada di disk. |

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `html_content` | str | — | String HTML lengkap (termasuk `<html>`, `<head>`, `<body>`). |
| `html_path` | str | — | Path absolut ke file `.html`. |
| `title` | str | `"Hariku Viewer"` | Judul jendela. |
| `width` | int | `850` | Lebar jendela awal (pixels). |
| `height` | int | `650` | Tinggi jendela awal (pixels). |

**NVDA Browse Mode Shortcuts (di dalam jendela Web View):**

| Shortcut | Fungsi |
|---|---|
| `H` / `Shift+H` | Heading berikutnya / sebelumnya |
| `1` – `6` | Lompat ke heading level tertentu |
| `T` / `Shift+T` | Tabel berikutnya / sebelumnya |
| `L` / `Shift+L` | List berikutnya / sebelumnya |
| `I` / `Shift+I` | Item list berikutnya / sebelumnya |
| `K` / `Shift+K` | Link berikutnya / sebelumnya |
| `ESC` | Tutup jendela Web View |

**Example — Menampilkan HTML sederhana:**
```python
import core.api

html = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>My Report</title></head>
<body>
  <h1>Extension Report</h1>
  <table>
    <tr><th>Event</th><th>Time</th></tr>
    <tr><td>Started</td><td>09:00</td></tr>
    <tr><td>Finished</td><td>10:30</td></tr>
  </table>
  <ul>
    <li><a href="#">Item A</a></li>
    <li><a href="#">Item B</a></li>
  </ul>
</body></html>
"""

core.api.show_html_view(html, title="My Extension Report")
```

**Example — Membuka file HTML dari extension folder:**
```python
import os
import core.api

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
help_file = os.path.join(EXT_DIR, "docs", "help.html")

core.api.show_html_file_view(help_file, title="Extension Help")
```

> **Tip untuk NVDA:** Setelah jendela Web View terbuka, pastikan NVDA sudah dalam **Browse Mode** (tekan `NVDA+Space` untuk berpindah mode jika perlu). Hariku menampilkan info bar di bagian atas jendela sebagai pengingat shortcut.

---

### Calendar

```python
import core.api
```

| Function | Returns | Description |
|---|---|---|
| `core.api.get_selected_date()` | `"YYYY-MM-DD"` or `None` | Get the currently selected date on the calendar. |
| `core.api.set_selected_date(date_str)` | `True` / `False` | Navigate the calendar to a specific date. Accepts `"YYYY-MM-DD"` format. |

**Example:**
```python
today = core.api.get_selected_date()
speak(f"The selected date is {today}")

core.api.set_selected_date("2026-12-25")
```

---

### Clipboard

```python
import core.api
```

| Function | Returns | Description |
|---|---|---|
| `core.api.set_clipboard(text)` | `True` / `False` | Copy text to the system clipboard. |
| `core.api.get_clipboard()` | `str` | Get the current clipboard text. |
| `core.api.get_active_window_info()` | `dict` | Get the currently focused window. Returns `{"title": "Window Title", "process": "notepad.exe"}`. |

**Example:**
```python
core.api.set_clipboard("Copied from Hariku!")
content = core.api.get_clipboard()
```

---

### Timers & Threading

```python
import core.api
```

| Function | Returns | Description |
|---|---|---|
| `core.api.set_timeout(ms, callback, *args)` | timer object | Call a function once after `ms` milliseconds. Call `.Stop()` to cancel. |
| `core.api.set_interval(ms, callback, *args)` | timer object | Call a function repeatedly every `ms` milliseconds. Call `.Stop()` to cancel. |
| `core.api.run_thread(func, callback=None)` | None | Run `func` in a background thread. When done, `callback(result)` is called safely on the UI thread. |

> **Important:** Always stop your timers in `teardown()` to prevent errors after your extension is unloaded.

**Example:**
```python
# One-shot timer
core.api.set_timeout(5000, speak, "5 seconds have passed!")

# Repeating timer
timer = core.api.set_interval(60000, speak, "One minute tick")
# Later: timer.Stop()

# Background HTTP request
def fetch_data():
    import urllib.request
    with urllib.request.urlopen("https://api.example.com/data") as r:
        return r.read().decode()

def on_result(data):
    if data:
        speak(f"Got: {data[:100]}")

core.api.run_thread(fetch_data, on_result)
```

---

### Hotkeys

```python
import core.hotkeys
```

| Function | Description |
|---|---|
| `core.hotkeys.register_action(ext_name, action_name, description, keycode, ctrl, callback, default_shift=False, default_alt=False, default_win=False, default_global=False)` | Register a keyboard shortcut. |
| `core.hotkeys.format_key_name(keycode, ctrl, shift=False, alt=False, win=False)` | Format a key combination into a human-readable string (e.g., `"Ctrl + Shift + J"`). |

**Parameters for `register_action`:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `ext_name` | str | — | Extension name (shown in Settings → Input Gestures) |
| `action_name` | str | — | Unique action ID within your extension |
| `description` | str | — | Human-readable description of the action |
| `keycode` | int / None | — | Default key. Use `ord("X")` for letters, `wx.WXK_F1` for special keys, or `None` for no default |
| `ctrl` | bool | — | Whether Ctrl is held |
| `callback` | callable | — | Function to call when the shortcut is pressed |
| `default_shift` | bool | `False` | Whether Shift is held |
| `default_alt` | bool | `False` | Whether Alt is held |
| `default_win` | bool | `False` | Whether the Windows key is held |
| `default_global` | bool | `False` | If `True`, the hotkey works **system-wide**, even when Hariku is not focused. Useful for utilities like window managers, quick-access tools, etc. |

**Multi-Tap Support (Double Tap / Triple Tap):**
Hariku supports NVDA-style multi-tap input without input lag. To use this, simply add a `tap_count` argument to your callback. Hariku will instantly call your function on the first press (`tap_count=1`), and call it again if the user presses the exact same key quickly (`tap_count=2`, `tap_count=3`, etc.). If your function doesn't need this, you can omit the argument.

- Users can always reassign shortcuts via **Settings → Input Gestures**.
- Users can also toggle any shortcut between local and global from the Input Gestures panel.

**Example — Local hotkey (only works when Hariku is focused):**
```python
import wx
import core.hotkeys
from core.speech import speak

# Optional: Add tap_count parameter to support double taps!
def my_function(tap_count=1):
    if tap_count == 1:
        speak("Action fired!")
    elif tap_count == 2:
        speak("Double tap!")

core.hotkeys.register_action(
    "My Extension",        # Extension name (shown in UI)
    "do_something",        # Unique action ID within extension
    "Do Something Cool",   # Human description
    ord("J"),              # Default key: J
    False,                 # Ctrl: False
    my_function,           # Callback
    default_shift=True,    # Shift+J
    default_alt=False
)
```

**Example — Global hotkey (works even when Hariku is minimized):**
```python
core.hotkeys.register_action(
    "My Extension",
    "quick_action",
    "Quick Action (Global)",
    ord("Q"),              # Default key: Q
    True,                  # Ctrl: True
    my_global_function,
    default_shift=True,    # Ctrl+Shift+Q
    default_global=True    # ← System-wide hotkey!
)
```

---

### Settings Panel

```python
import core.preferences
```

| Function | Description |
|---|---|
| `core.preferences.register_panel(category, name, create_func, apply_func)` | Register a settings panel in the Preferences dialog. |
| `core.preferences.get_all_panels()` | Returns a dictionary of all registered preference panels. Useful for introspection. |

- `create_func(parent)` → Must return a `wx.Panel` instance.
- `apply_func()` → Called when the user clicks OK.

**Example:**
```python
class MySettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.chk = wx.CheckBox(self, label="Enable feature")
        self.chk.SetValue(True)
        vbox.Add(self.chk, 0, wx.ALL, 10)
        
        self.SetSizer(vbox)
    
    def ApplyChanges(self):
        config = core.api.load_data("MyExtension")
        config["enabled"] = self.chk.GetValue()
        core.api.save_data("MyExtension", config)

_panel = None

def create(parent):
    global _panel
    _panel = MySettingsPanel(parent)
    return _panel

def apply():
    if _panel:
        _panel.ApplyChanges()

# In register():
core.preferences.register_panel("My Extension", "", create, apply)
```

---

### Event Bus

```python
from core.events import bus
```

| Function | Description |
|---|---|
| `bus.subscribe(event_name, callback)` | Listen for an event. |
| `bus.emit(event_name, *args, **kwargs)` | Broadcast an event to all listeners. |

You can also emit your own custom events for inter-extension communication.

**Example:**
```python
def on_date_changed(date_str):
    speak(f"Date changed to {date_str}")

bus.subscribe("on_date_changed", on_date_changed)

# Custom event (other extensions can listen to this too)
bus.emit("my_extension.data_updated", {"key": "value"})
```

---

### Sounds

```python
from core.sounds import play_sound, play_internal_sound
```

| Function | Description |
|---|---|
| `play_internal_sound(name)` | Play one of Hariku's sounds by file name. Example: `play_internal_sound("info.wav")`. Since core 2.6 it plays the active sound theme's copy when the theme has one, otherwise the built-in `sounds/info.wav`. |
| `play_sound(filepath)` | Play any `.wav` file from an absolute path. Supports overlapping sounds (multiple sounds can play simultaneously). Returns `True` / `False`. |
| `sound_path(name)` | *(core 2.7)* The file `play_internal_sound(name)` plays: the active theme's copy when it has one, otherwise Hariku's own. Read a sound's length with it. Hariku 2.7 adds `listen.wav` and `listen_end.wav`, the command bar's listening tones (`core.commands.LISTEN_SOUND` and `LISTEN_END_SOUND`). |
| `set_theme_dir(path_or_None, remember=False)` | *(core 2.6)* Use a folder of `.wav` files named like Hariku's sounds as the active theme; `None` goes back to the built-in sounds. Only plain file names are looked up in it, never paths. *(core 2.7)* With `remember=True` the choice is also saved in `Core.json` (`None` forgets it), so the next start plays that theme's `start.wav` before any extension loads; pass it only when the **user** picks a theme. A plain call, such as your `teardown()` handing the sounds back, leaves the saved choice alone. |
| `load_remembered_theme()` | *(core 2.7)* Hariku calls this at startup, before `start.wav`: it uses the remembered folder if it still exists inside `%APPDATA%\Hariku2\sound_themes`. |
| `get_theme_dir()` | *(core 2.6)* The active theme folder, or `None`. |
| `get_builtin_sounds_dir()` | *(core 2.6)* Hariku's own `sounds/` folder. |
| `stop_sound(filepath)` | *(core 2.6)* Stop a sound started with `play_sound` and release its file (Windows keeps a played file open, so call this before replacing or deleting it). |

**Playing Custom Extension Sounds:**
If your extension has its own `sounds/` folder, you can get the absolute path to your extension using `__file__` and play your own sounds:

```python
import os
from core.sounds import play_sound

# __file__ is the path to your main.py
EXT_DIR = os.path.dirname(os.path.abspath(__file__))
MY_SOUND = os.path.join(EXT_DIR, "sounds", "notification.wav")

play_sound(MY_SOUND)
```

---

### Volume Control

```python
from core.sounds import get_global_volume, set_global_volume, volume_up, volume_down
```

| Function | Returns | Description |
|---|---|---|
| `get_global_volume()` | `int` (0–100) | Get the current global volume level. |
| `set_global_volume(vol_percent)` | None | Set and persist the global volume (0–100). Applies to system audio immediately. |
| `volume_up()` | None | Increase volume by 5% and announce the new level via speech. |
| `volume_down()` | None | Decrease volume by 5% and announce the new level via speech. |

**Example:**
```python
from core.sounds import get_global_volume, set_global_volume

current = get_global_volume()
speak(f"Volume is at {current}%")

# Set volume to 50%
set_global_volume(50)
```

---

### Reminders

```python
from core import reminders
```

The reminders module lets you create, query, modify, and delete calendar reminders programmatically. All reminder data is persisted to JSON automatically.

| Function | Returns | Description |
|---|---|---|
| `reminders.load_reminders()` | `list[dict]` | Load all reminders. Each dict contains `id`, `title`, `date` (YYYY-MM-DD), `time` (HH:MM), `is_done` (bool), `recurrence` (`"none"`, `"daily"`, `"weekly"`, `"monthly"` or `"yearly"`) and `interval` (every N days, weeks, months or years). A monthly or yearly reminder may carry `anchor_day`, the day of the month it keeps (a reminder on the 31st falls on 28 February, then on 31 March again). It may also carry an internal `notified` flag once the reminder has fired — leave that field alone. |
| `reminders.get_reminders_for_date(date_str)` | `list[dict]` | Get all reminders for a specific date (`"YYYY-MM-DD"`), repeating ones included. |
| `reminders.add_reminder(title, date_str, time_str, recurrence="none", interval=1)` | None | Create a new reminder. A unique UUID is assigned automatically. `date_str` = `"YYYY-MM-DD"`, `time_str` = `"HH:MM"`. `recurrence` and `interval` make it repeat, e.g. `recurrence="daily", interval=2` for every other day. |
| `reminders.delete_reminder(rem_id)` | None | Delete a reminder by its UUID. Speaks confirmation. |
| `reminders.mark_as_done(rem_id)` | None | Mark a reminder as done by its UUID. Speaks confirmation. |
| `reminders.snooze_reminder(rem_id, minutes=5)` | None | Snooze a reminder — pushes its date/time forward by the specified number of minutes. Speaks confirmation. |
| `reminders.expanded_copy(reminder)` | `dict` | *(core 2.7)* A copy of the reminder with `%placeholders%` in its title (and notes, if any) filled in from the user's profile. Use it when you speak or show a reminder; the stored reminder keeps the raw text. See [Personal Profile](#personal-profile). |

**Example:**
```python
from core import reminders
from core.speech import speak

# Add a reminder for Christmas
reminders.add_reminder("Christmas Party!", "2026-12-25", "18:00")

# List today's reminders
import core.api
today = core.api.get_selected_date()
today_reminders = reminders.get_reminders_for_date(today)

for r in today_reminders:
    speak(f"{r['time']} - {r['title']}")

# Snooze a reminder by 10 minutes
if today_reminders:
    reminders.snooze_reminder(today_reminders[0]["id"], minutes=10)

# Delete a specific reminder
if today_reminders:
    reminders.delete_reminder(today_reminders[0]["id"])
```

---

### Reminders from a Sentence

*(Available since core 2.7.)*

```python
from core import when
import core.quick_reminder
```

The quick reminder (N) reads one sentence, such as "minum obat besok jam 8 pagi, tiap hari" or "call mom tomorrow at 7pm", into a reminder. It uses rules, not AI, and runs on the computer: nothing is sent anywhere. The words come from language packs (see [For Translators](#for-translators)).

| Function | Returns | Description |
|---|---|---|
| `core.quick_reminder.parse_text(text)` | `Result` | Read a sentence with the languages the user has on (the Hariku language, English, Indonesian and the ones added in Preferences, Reminders). |
| `core.quick_reminder.readback(result)` | `str` | What the quick reminder says about a result, in the Hariku language: "Minum obat, Friday 25 September 2026, at 08:00, every day. Save?", or what went wrong. |
| `core.quick_reminder.save_result(result)` | `bool` | Save a result that is `ok` through `reminders.add_reminder`, and say so. |
| `when.parse(text, now=None, language=None, packs=None, default_date=None)` | `Result` | The reader itself, with the packs you choose. `default_date` is the date for a sentence that gives a time but no date. |
| `when.resolve(components, now=None, default_date=None)` | `Result` | Turn relative parts (`when.COMPONENT_FIELDS`: "tomorrow", "8", "evening", "every 2 days") into a date and time with the same rules. Meant for a fallback such as an AI, which then never has to work out a date itself. |

A `Result` has `title`, `date` (`"YYYY-MM-DD"`), `time` (`"HH:MM"`), `recurrence`, `interval`, and:

- `ok`: it can be saved (a title, a date and a time, and no blocking problem).
- `problems`: `"nothing_found"`, `"no_title"`, `"invalid_date"`, `"invalid_time"`, `"unsupported_repeat"` (every hour is not possible), or the warning `"conflict"` (two dates or times; the first one counts).
- `time_assumed` (no time was said: 09:00), `date_assumed`, `in_past`.
- `confidence` (0 to 1), `unparsed` (words that look like a date or time but weren't understood) and `needs_fallback`, for deciding when to ask a person or a fallback.

```python
import core.quick_reminder

result = core.quick_reminder.parse_text("bayar listrik tiap bulan tanggal 5 jam 9")
if result.ok and not result.needs_fallback:
    core.quick_reminder.save_result(result)   # monthly on the 5th, 09:00
```

---

### Personal Profile

*(Available since core 2.7. Declare `"minimum_core_version": "2.7"` to use it.)*

```python
import core.personal
```

The user fills in their profile in Preferences, Profile: their name, what Hariku should call them, the title Hariku puts before that (*core 2.7*: "Kapten", "Pak", "Kak"), their birthday (day and month, the year optional), and their own placeholders (for example `%kantor%` → an office address). Hariku fills in `%myname%`, `%mynickname%`, `%mytitle%`, `%mybirthday%`, `%myage%` and those placeholders in routines, the Morning Briefing and reminder text when a reminder is announced, together with its dynamic placeholders and those extensions register (see [Placeholders from Extensions](#placeholders-from-extensions)). It greets the user when it starts (unless they turn that off), with "Happy birthday!" on their birthday, or says the user's own startup greeting when they wrote one. Read the profile with these functions; the Profile page is the only place that changes it, except `set_title()` and `set_custom_greeting()`, which an extension may call after asking the user (Cockpit's Captain mode does).

| Function | Returns | Description |
|---|---|---|
| `core.personal.get_name()` | `str` | The user's name, or `""` if they gave none. |
| `core.personal.get_nickname()` | `str` | What Hariku should call the user: their nickname, else their name, else `""`. |
| `core.personal.get_title()` | `str` | The title before their name ("Kapten"), or `""`. |
| `core.personal.get_addressed_name()` | `str` | How to address the user: the title and the nickname, `"Kapten Bro"`; either alone, or `""`. Use this to greet them. |
| `core.personal.set_title(title)` | `bool` | Save the title (`""` removes it). Raises `ProfileError` when it is too long. Only after the user agreed. |
| `core.personal.get_custom_greeting()` | `dict` | `{"text", "boot_only"}`: the user's own startup greeting, raw with its placeholders (`""`: the usual greeting), and whether it is only for starts with Windows. |
| `core.personal.set_custom_greeting(text, boot_only=False)` | `bool` | Save it. Only after the user agreed. |
| `core.personal.get_fields()` | `list[tuple]` | The user's own placeholders as an ordered list of `(key, value)`. Keys are lower-case, without `%` signs. |
| `core.personal.get_birthday()` | `tuple` or `None` | The birthday as `(day, month, year)`; `year` is `None` when the user left it out. `None` without a birthday. |
| `core.personal.is_birthday(today=None)` | `bool` | `True` on the user's birthday. `today` is a `date` or `datetime` (default: now). A 29 February birthday counts on 28 February in other years. |
| `core.personal.get_age(today=None)` | `int` or `None` | The user's age in whole years, or `None` without a birth year. |
| `core.personal.birthday_text()` | `str` | The birthday in the user's language: `"24 September"` or `"24 September 1999"`; `""` without one. |
| `core.personal.greeting(now=None, nickname=None, title=None)` | `str` | `"Good morning, Kapten Budi."` for the time of day (with the title and nickname if there are any), followed by `"Happy birthday!"` on the birthday. |
| `core.personal.expand(text, extra=None, now=None, unknown=None)` | `str` | Fill in `%token%` placeholders in `text` (see the rules below). `extra` is an optional dict of your own tokens (`{"city": "Jakarta"}` fills in `%city%`); it is looked up first. `now` is the time for `%time%` and the like. With `unknown=""`, tokens nobody knows are removed instead of left as they are. |
| `core.personal.tidy_spoken(text)` | `str` | Close the gaps an empty placeholder leaves: double spaces, `", ."`, `". ."`. |
| `core.personal.startup_speech(welcome="", now=None, boot=False)` | `str` | What Hariku says when it starts: the user's own greeting (expanded and tidied) or the usual greeting followed by `welcome`. `boot` is whether Windows started Hariku (`core.api.started_with_windows()`). |

**Placeholder rules:**
- A token is `%` + letters, digits or underscores + `%`, e.g. `%myname%`. Matching is case-insensitive: `%MyName%` works too.
- The profile: `%myname%` (the name), `%mynickname%` (the nickname, or the name if there is none), `%mytitle%` (the title), `%mybirthday%` (like `birthday_text()`) and `%myage%` (empty without a birth year). The user's own keys are 1–32 characters of `a`–`z`, `0`–`9` and `_`, and can't be Windows variable names such as `temp` or `userprofile`.
- Dynamic *(core 2.7)*, worked out when the text is used: `%greeting%` ("Good morning", "Selamat pagi"), `%time%` (HH:MM), `%day%` (the weekday), `%date%` ("24 September"), `%zulu%` (HH:MM in UTC), `%reminders%` ("3 reminders today", "no reminders today": today's reminders not done yet) and `%version%` (Hariku's version, e.g. 2.7.0). Routines' own `%time%` and `%date%` win inside routines.
- Looked up in this order: `extra`, the dynamic ones, those extensions registered, then the profile.
- Unknown tokens and lone `%` signs are left as they are, so `"50%"` and `"100% done"` never change.
- Expansion is a single pass: a value that itself contains `%something%` is inserted as it is, never expanded again.
- An empty value expands to `""` (for example `%myname%` when the user gave no name).
- These names are reserved and can't be the user's own keys: `myname`, `mynickname`, `mytitle`, `mybirthday`, `myage`, the dynamic `greeting`, `time`, `day`, `date`, `zulu`, `reminders`, the Routines tokens `battery`, `app`, `clipboard`, `ssid`, `ram`, `cpu`, `events`, `var`, and every name an extension has registered.
- Expand only text you are about to speak or show. Store what the user typed, raw.
- The profile is saved unencrypted in `Core.json`. Don't copy it anywhere else, and never send it over the network without the user asking you to.

**Example:**
```python
import core.personal
from core.speech import speak

nickname = core.personal.get_nickname()
speak(f"Welcome back, {nickname}." if nickname else "Welcome back.")

# "Hi Budi, your parcel goes to Jl. Sudirman 1." (with the profile filled in)
speak(core.personal.expand("Hi %mynickname%, your parcel goes to %kantor%."))

# Your own tokens next to the profile's
speak(core.personal.expand("%myname%, it is %temp% degrees.", extra={"temp": 31}))
```

The `on_reminder_fired` event passes the reminder as stored. To read it aloud, use `core.reminders.expanded_copy(reminder)["title"]` or `core.personal.expand(reminder["title"])`.

Don't greet the user at startup yourself: Hariku already does (when the greeting is on, `core.personal.startup_greeting_enabled()` is `True`), including "Happy birthday!". An extension that also celebrates the user's birthday should skip it on the day when that is `True`, as Lumina does. To be part of the greeting, register a placeholder the user can put in their own greeting.

When Windows started Hariku (`core.api.started_with_windows()` is `True`), the greeting waits until Windows reports a network connection, then about 3 seconds more, 25 seconds at most, so extensions that refresh their data at `on_app_startup` (or on `on_network_changed` with `True`) can have it ready. Manual starts greet 1.5 seconds after the window appears.

### Placeholders from Extensions

*(Available since core 2.7.)*

An extension can add a placeholder that Hariku fills in everywhere it expands text: routines, reminders, the Morning Briefing and the user's startup greeting. The Insert placeholder menus (the Profile page's greeting field and Routines' builder) list it with its description.

| Function | Returns | Description |
|---|---|---|
| `core.personal.register_placeholder(name, provider, description="")` | `str` | Make `%name%` call `provider()`. `name` is 1–32 characters of `a`–`z`, `0`–`9` and `_` and can't be one Hariku uses (raises `ValueError`); registering it again replaces it. `description` is shown in the menus, in the user's language. Returns the name as stored. |
| `core.personal.unregister_placeholder(name)` | `bool` | Remove it; call this in `teardown()`. |
| `core.personal.is_placeholder_registered(name)` | `bool` | Whether `%name%` is registered. |
| `core.personal.get_placeholders(now=None, values=True)` | `list[tuple]` | `[(name, description, current value)]`: Hariku's dynamic placeholders, then the registered ones. |
| `core.personal.menu_entries(...)` | `list[tuple]` | The `(token, label)` pairs of an Insert placeholder menu (the profile, the user's keys, your own `tokens`, then the dynamic and registered placeholders). `core.core_panels.placeholder_menu(entries, on_pick)` makes the `wx.Menu`, and `core.personal.insert_placeholder(value, start, end, token)` puts the chosen token at the caret. |

**Rules for providers:**
- Return a short string from data you already have (your cache): the provider runs on whichever thread is expanding text, so no network requests, no files that may be slow, no waiting. Return `""` when you have nothing recent.
- Write it to fit inside the user's sentence: no capital letter at the start (unless it is a name) and no full stop at the end, e.g. `"light rain, 25 degrees"`.
- An exception or `None` becomes `""`, and the value is put on one line and cut at 300 characters.
- A user's own key with the same name keeps working in their profile, but your placeholder wins when text is filled in.
- If your extension also runs on older cores, import it guarded: `try: import core.personal as personal` / `except ImportError: personal = None`, and check `hasattr(personal, "register_placeholder")`.

```python
import core.personal

def _airport_weather():
    report = _cache.get("latest")          # never fetch here
    return report["short"] if report else ""

def register(bus):
    core.personal.register_placeholder("airportweather", _airport_weather,
                                       _("placeholder_desc"))

def teardown():
    core.personal.unregister_placeholder("airportweather")
```

Hariku's own: Weather adds `%weather%` ("light rain, 25 degrees"), Sleep Pattern `%sleep%` ("about 6 hours 25 minutes") and Cockpit `%airportweather%`.

---

### Quiet Hours

*(Available since core 2.7.)*

The user can set quiet hours in Preferences, Quiet Hours (off by default; 22:00 to 05:00 when turned on). During them, background alerts from extensions stay silent.

| Function | Returns | Description |
|---|---|---|
| `core.personal.is_quiet_time(now=None)` | `bool` | `True` during the user's quiet hours. Ranges past midnight work (22:00–05:00 is quiet at 23:30 and at 04:59, not at 05:00). Always `False` when quiet hours are off. |
| `core.personal.get_quiet_hours()` | `dict` | `{"enabled": bool, "start": "HH:MM", "end": "HH:MM"}`. |

**Rules for alerts:**
- Check `is_quiet_time()` right before you announce something the user didn't ask for at that moment (an aircraft overhead, high waves, a nearby earthquake), and skip the announcement.
- Skip, don't queue: don't save alerts for later. Mark an event-based alert (one earthquake, one emergency) as handled so it isn't announced when quiet hours end. A condition-based alert (the air is unhealthy today) may be announced if it still holds when you next check after quiet hours.
- Keep safety warnings that can't wait: Earthquakes & Tsunami still announces tsunami alerts during quiet hours.
- Keep what the user set up to sound at that time: their reminders, launch reminders, routines, and anything else they scheduled themselves.
- Stop background requests that only feed skipped alerts, but keep your timer running so alerts come back when quiet hours end.

```python
import core.personal

def _on_new_alert(message):
    if core.personal.is_quiet_time():
        return            # dropped, not saved for later
    speak(message)
```

---

### Places

*(Available since core 2.8. Declare `"minimum_core_version": "2.8"` to use it.)*

```python
import core.places
import core.place_search          # finding a place: addresses, cities, map links
from core.places_ui import PlaceChoice
```

The user names the places they use in Preferences, Places (Home, Office, Mum's house) and makes one of them the main place. Use these instead of asking for a city yourself: by default your extension uses the main place, and your settings page offers the user a "Place:" list to pick another one (or, if your extension has one, its own place). Weather, Sea Conditions, Air Quality, Earthquakes & Tsunami, Space, Cockpit and Flight Radar all work this way. Places are saved only on the user's computer (`Places.json`); reading them is cheap, so it is fine from a placeholder provider.

A place is a dict:

| Key | Description |
|---|---|
| `id` | A short id, such as `"3f9a1c2e"`. What you store to remember the user's choice. |
| `name` | The user's name for it, 1 to 40 characters, unique: `"Home"`, `"Rumah Mama"`. |
| `lat`, `lon` | The exact point (floats). Never send them anywhere; see `rounded()`. |
| `label` | The address or city the user chose, such as `"Jalan Merdeka 1, Batam, Kepulauan Riau, Indonesia"`; `""` for pasted coordinates. |
| `timezone` | The IANA zone (`"Asia/Makassar"`) when known (a city found by name), else `None`: use `timezone_for()`. |
| `source` | `"address"`, `"city"` or `"coordinates"`. |
| `city`, `region`, `country` | When known (from the search), else `""`. |

| Function | Returns | Description |
|---|---|---|
| `core.places.get_places()` | `list` | Every place, in the user's order (copies). |
| `core.places.get_place(place_id)` | `dict` or `None` | One place. |
| `core.places.get_main()` / `get_main_id()` | `dict` / `str`, or `None` | The main place, or `None` when the user has no places. |
| `core.places.rounded(place, decimals=2)` | `(lat, lon)` | The point to send a service: 2 decimals is about 1 km. |
| `core.places.distance_km(a, b)` | `float` | Great-circle distance. `a` and `b` can be places, location dicts (`"latitude"`/`"longitude"`) or `(lat, lon)` pairs. |
| `core.places.bearing(a, b)` | `float` | Compass bearing from `a` to `b`, 0 to 360 (0 is north, 90 east). |
| `core.places.timezone_for(place)` | `tzinfo` | The place's time zone, or the computer's own when it has none. |
| `core.places.where_text(place)` / `describe(place)` | `str` | `"Jalan Merdeka 1, Batam (1.1301, 104.0529)"` / `"Home: Jalan Merdeka 1, ..."`. |
| `core.places.set_places(places, main_id=None)` | `list` | Save the whole list (the Places page does this; don't, unless the user asked). Raises `core.places.PlaceError` (`str()` is a message for the user). Emits `on_places_changed`. |

**Which place your extension uses.** Store the user's choice in your own data, never a copy of the place: `"main"`, a place id, or `"own"` for a place of your own (for example a beach). Then:

| Function | Returns | Description |
|---|---|---|
| `core.places.location_for(choice, own_location=None)` | `dict` or `None` | The location to use: `own_location` for `"own"`, else the chosen place (a removed one becomes the main place), as `location_dict()`. `None` when there is none. |
| `core.places.location_dict(place)` | `dict` | A place as `{"name", "latitude", "longitude", "timezone" ("" when unknown), "place_id", "city", "label", ...}`, the shape Hariku's extensions keep their own location in. |
| `core.places.initial_choice(own_location)` | `str` | For settings saved before 2.8: `"own"` when your extension has a place of its own that isn't the main place, else `"main"`. Settle it once in `register()` and save it. |
| `core.places.normalize_choice(value)` | `str` or `None` | A stored choice checked (`None` for anything else). |
| `core.places.choice_entries(own=True)` | `list` | `[(choice, text)]` for a list of your own. |
| `PlaceChoice(parent, sizer, choice, own=True, on_change=None, label=None)` | | The labelled "Place:" list for your settings page (the label is created first, for screen readers). `.key()` is the choice to save, `.set_key(choice)`, `.is_own()`, and `.refresh()` after `on_places_changed`; `.ctrl` is the `wx.Choice`. Pass `own=False` when your extension has no place of its own. |

**Finding a place yourself** (`core.place_search`, the helpers the Places page uses):

| Function | Returns | Description |
|---|---|---|
| `parse_location_text(text)` | `dict` | Pasted coordinates (`"-6.2088, 106.8456"`, `6°12'31.7"S 106°50'44.2"E`, Indonesian LS/BT) or a Google Maps, Apple Maps or OpenStreetMap link, read offline: `{"kind": "coordinates", "latitude", "longitude"}`, or `{"kind": "short_link", "url"}` for a `maps.app.goo.gl` link. Raises `LocationError` (`.kind`). |
| `resolve_short_link(url)` | `(lat, lon)` | Expands a short link (network: only after the user pressed a button, on a worker thread). Only the short-link hosts are fetched. |
| `search_addresses(query, language="en")` | `list` | OpenStreetMap Nominatim (network, worker thread). Only when the user presses Enter or a button, never while they type, with at least 3 characters. Hariku paces every caller together (one request per 1.1 s) and remembers answers. Credit "© OpenStreetMap contributors" on your page. |
| `search_cities(name, language="en")` | `list` | Open-Meteo geocoding (network, worker thread), with each city's time zone. Credit Open-Meteo. |

Both searches return candidates: `{"name", "label", "latitude", "longitude", "timezone", "source", "city", "region", "country"}`; `core.places.place_from_candidate(found, name)` makes a place of one.

**Rules:**
- Send a service `rounded(place)` (or something coarser), never `lat`/`lon`, and say so in your privacy notes. Keep what you cache keyed by the rounded point, so the exact point isn't copied into your data files.
- Store the choice, not the place: when the user edits a place, your extension follows.
- Subscribe to `on_places_changed`: refresh your settings page's list (`PlaceChoice.refresh()`, which keeps the user's choice) and fetch again when the place you use moved.
- Network requests on worker threads only, results back through `wx.CallAfter`.
- To keep working on older cores, import it guarded (`try: import core.places as places` / `except ImportError: places = None`) and fall back to your own city search; otherwise declare `"minimum_core_version": "2.8"`.

```python
import core.api
import core.places
from core.places_ui import PlaceChoice

DATA_KEY = "MyExtension"

def get_location():
    data = core.api.load_data(DATA_KEY)
    return core.places.location_for(data.get("place", "main"))

def _fetch_worker():
    location = get_location()
    if location:
        lat, lon = core.places.rounded(location)     # about 1 km, never the exact point
        ...

class MyPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.place = PlaceChoice(self, sizer, core.api.load_data(DATA_KEY).get("place"),
                                 own=False)
        self.SetSizer(sizer)

    def ApplyChanges(self):
        data = core.api.load_data(DATA_KEY)
        data["place"] = self.place.key()
        core.api.save_data(DATA_KEY, data)
```

Coming later: telling which place the user is at (for example from the Wi-Fi network), for Routines.

### Hariku Voice

*(Available since core 2.7. Declare `"minimum_core_version": "2.7"` to use it.)*

```python
import core.voice
```

In Preferences, Hariku Voice, the user can have four kinds of Hariku's own announcements spoken by a voice they choose instead of their screen reader: the startup greeting, the Briefing and evening summary, reminders when they fire, and *(core 2.7)* answers to commands from the command bar. Everything else stays with the screen reader, and a braille display still gets the text. The first three are off by default. Answers to commands are on by default, because users asked for them in their own voice, but only once the user has set up Hariku Voice (saved its page); until then the screen reader says them. The voices come from *providers*: "Windows voices" (SAPI 5, every voice installed on the computer) is built in and is the fallback; extensions add more (the Edge Voices extension adds Microsoft Edge's online voices).

#### Announcing

| Function | Returns | Description |
|---|---|---|
| `core.voice.announce(text, kind, interrupt=True)` | `bool` | Say one of the announcements. `kind` is `"greeting"`, `"briefing"`, `"reminder"` or `"command"`. When the user hasn't chosen a voice for that kind, this is exactly `core.speech.speak(text, interrupt)`. Otherwise the chosen voice speaks and the braille display gets the text; if the voice fails, the user's fallback Windows voice, then the screen reader. `interrupt=True` stops a Hariku voice that is speaking; `False` waits for it. Returns `True` when a Hariku voice speaks it (the screen reader was not given the text), `False` when the screen reader did. |
| `core.voice.is_enabled(kind)` | `bool` | Whether the user chose a voice for this kind. |
| `core.voice.is_configured()` | `bool` | *(core 2.7)* Whether the user has set up Hariku Voice (saved its page). |
| `core.voice.route_speech(kind, seconds=20)` | `True` | *(core 2.7)* From now until the next key press, or `seconds` at most (60 at most), `core.speech.speak()` speaks with Hariku Voice as an announcement of `kind`, when that kind is on and a voice is available; otherwise the screen reader speaks as usual. Braille still gets every text. The command bar calls `route_speech("command")` right before it runs an action, because actions often answer seconds later, after a download. The key that ran the command doesn't end it; key presses are noticed with `GetLastInputInfo`, never a keyboard hook. A new call replaces the window. |
| `core.voice.stop_routing()` | None | *(core 2.7)* End that window now. |
| `core.voice.routed_kind()` | `str` or `None` | *(core 2.7)* The kind speech is routed as right now. |
| `core.voice.stop()` | None | Stop the Hariku voice now and drop what was waiting. The "Stop Hariku Voice" action (S) does this; so does any key press, unless the user turned that off. |
| `core.voice.is_speaking()` | `bool` | Whether a Hariku voice is speaking or has announcements waiting. |

**Rules:**
- Use `announce()` only for these kinds; the Morning Briefing uses `"briefing"`, the command bar `"command"`. Everything else goes through `core.speech.speak()`, so the user's screen reader stays in charge. An action the user ran from the command bar needs nothing special: its `speak()` is routed for a moment (`route_speech`).
- When `announce()` returns `True`, don't also speak the text. If you show a window for it, keep the text out of what the screen reader reads when the window opens: the core's reminder popup puts it in a read-only field after the buttons, so the screen reader says only the title and the focused button.
- `on_before_speak` fires once for a voiced announcement too (with `"kind"` and `"voice"` in the payload); cancelling it silences the voice. Speech routed by `route_speech()` fires it once, with `"kind": "command"`.
- Quiet hours don't apply: these are the user's own greeting, briefing and reminders.
- The settings are in `Core.json` under `"hariku_voice"`; read them with `core.voice.get_settings()`, but only the Hariku Voice page changes them.

#### Adding a voice source (provider)

```python
core.voice.register_provider(provider_id, name, list_voices, speak, stop,
                             is_available=None, privacy_note="")
core.voice.unregister_provider(provider_id)      # in teardown()
```

| Argument | What Hariku expects |
|---|---|
| `provider_id` | 1–32 characters of `a`–`z`, `0`–`9` and `_`, e.g. `"piper"`. Registering the same id again replaces the provider. `"windows"` is the built-in one and can't be removed. |
| `name` | Shown in the Source list, in the user's language, e.g. `"Piper voices (offline)"`. |
| `list_voices()` | Returns `[{"id", "name", "language", "gender"}]`: your own voice id, the voice's own name (`"Gadis"`, without its language or gender), a BCP-47 tag such as `"id-ID"`, and optionally `"gender"`: `"female"` or `"male"`; leave it out when you don't know. The page picks a voice with three choices: Language (one entry per tag, the user's languages first), Gender ("All voices", then Female and Male if that language has them; only "All voices" when none of its voices has a gender) and Voice (the names, sorted). Extra keys are kept. It may be slow or use the network: Hariku only calls it on a worker thread. Raise when it can't list them; the page says so. |
| `speak(text, voice_id, rate, volume, on_done)` | Start speaking and **return at once**. `voice_id` is `""` when the user picked none: use a default voice (ideally one for Hariku's language). `rate` is -10 to 10 (0 is the voice's normal rate; map it to your own range), `volume` 0 to 100. Call `on_done(None)` when the speech has finished or was stopped, or `on_done(error)` when you could not speak, so Hariku falls back. Call it **exactly once**, from any thread. |
| `stop()` | Stop the current speech now. It must be thread-safe and must not block. After it, call the pending `on_done(None)`; Hariku waits up to 2 seconds for it. |
| `is_available()` | Optional. Return `False` while you know you can't speak (offline, blocked, too many failures), and Hariku goes straight to the fallback. It is asked before every announcement, so it must be fast: no network, no disk. |
| `privacy_note` | Shown on the Hariku Voice page when your source is selected. Say plainly what leaves the computer, e.g. "The text being read is sent to ...". |

Hariku speaks one announcement at a time and doesn't call `speak()` again before your `on_done` (or `stop()`). It also watches for key presses and handles the queue, the fallback and braille itself, so a provider only speaks.

**Providers that make audio files** can let Hariku play them:

| Function | Description |
|---|---|
| `core.voice.play_file(path, volume, on_done)` | Play an MP3 or WAV file at `volume` (0–100) without blocking; `on_done(None)` when it ends or is stopped, `on_done(error)` when it can't be played, exactly once. Pass your own `on_done` straight through. One file plays at a time, on its own MCI device, so Hariku's UI sounds never cut it off. |
| `core.voice.stop_playback()` | Stop that file. Hariku calls it itself when it stops a voice. |
| `core.voice.cache_dir(provider_id)` | A folder for your saved audio, `%APPDATA%\Hariku2\voice_cache\<provider_id>`, created if missing. Keep it small and delete the oldest files first. |

Also available: `core.voice.get_providers()` (`[{"id", "name", "privacy_note"}]`, Windows first), `core.voice.list_voices(provider_id)` (checked, with `"language"` and `"gender"` always present; `"gender"` is `"female"`, `"male"` or `""`), `core.voice.order_voices(voices)` (the user's languages first), `core.voice.language_name(tag)` and `core.voice.preview(text, provider_id, voice_id, rate, volume, stop_on_key=True, on_done=None)` (what the page's Test button does).

```python
import threading
import core.voice

PROVIDER_ID = "piper"

def _list_voices():
    return [{"id": "id_ID-news-medium", "name": "News", "language": "id-ID"}]

def _speak(text, voice_id, rate, volume, on_done):
    def work():
        try:
            path = _synthesize_to_wav(text, voice_id or "id_ID-news-medium", rate)
        except Exception as e:
            on_done(e)                      # Hariku falls back
            return
        core.voice.play_file(path, volume, on_done)
    threading.Thread(target=work, daemon=True).start()

def _stop():
    _cancel_synthesis()                     # its on_done(None) follows

def register(bus):
    core.voice.register_provider(PROVIDER_ID, "Piper voices (offline)", _list_voices,
                                 _speak, _stop, privacy_note="Piper voices run on this computer.")

def teardown():
    core.voice.unregister_provider(PROVIDER_ID)
```

---

### The Command Bar (Aruna)

Users know the command bar as **Aruna** (Sanskrit for dawn). Code keeps the
generic names (`core.commands`, `ui/command_bar.py`, `Hariku Core.command_bar`).

*(Available since core 2.7.)*

```python
import core.commands
```

**Ctrl+Alt+Backspace**, from anywhere (a global hotkey through `RegisterHotKey`; users can move it in Input Gestures), opens a small always-on-top window called "Hariku" with one field, "Say or type a command". Enter runs what was typed:

- A reminder sentence (a trigger such as "ingatkan aku" or "remind me", or a date or time) gets the quick reminder's read-back ("..., Save?"); Enter again or "ya"/"simpan" saves it, "tidak"/"batal" or Escape doesn't.
- Otherwise the text is matched against **every registered hotkey action**, by its description in the user's language and its aliases. A clear winner runs at once: the bar closes, focus goes back to the window that had it, and the action runs as its hotkey would, so a dialog it opens opens as usual. A close call asks "Did you mean …?" (Enter or "ya" runs it). Anything else: "I didn't understand".
- The bar's answers are spoken with Hariku Voice (`announce(text, "command")`), and the action's own `speak()` is routed there for a moment (`core.voice.route_speech`).

Your extension's actions are commands already: register them with `core.hotkeys.register_action` (a key is optional; `None` works) and give them a clear description. Add the other ways people say them:

| Function | Returns | Description |
|---|---|---|
| `core.commands.add_aliases(action_id, aliases, title=None)` | `list` | More ways to say an action, in any language: `add_aliases("Pets.feed", ["kasih makan kucing", "feed the cat"])`. `action_id` is `"<extension name>.<action name>"` as registered. `title` is an optional short name for "Did you mean …?" in the user's language (default: the description). Call it in `register()`. |
| `core.commands.remove_aliases(action_id)` | `bool` | Remove them; call it in `teardown()`. |
| `core.commands.match(text)` | `Match` | Every command scored for `text`: `.best` (a `Command` with `.id`, `.name`, `.title`), `.score`, `.kind` (`"run"`, `"ask"` or `"none"`). |
| `core.commands.decide(text)` | `Decision` | What the bar does with a text: `.kind` is `"reminder"` (`.result`, a `core.when` Result), `"run"` or `"confirm"` (`.command`), `"offer_reminder"`, `"unknown"` or `"empty"`. |
| `core.commands.answer(text)` | `"yes"`, `"no"` or `None` | A spoken or typed answer: "ya", "iya, simpan", "yes", "save" / "tidak", "batal", "no", "cancel", "bukan". |
| `core.commands.looks_like_reminder(text)` | `bool` | A trigger or a date/time in it (a recogniser may listen again more carefully). |
| `core.commands.vocabulary()` | `list` | Every command's name and aliases: the words a speech recogniser should expect. |

How matching works (so you can choose good aliases): case, accents, punctuation and hyphens don't count, a letter said twice counts once, and filler words ("tolong", "ucapkan", "please", "the", "what") are dropped. Words are compared letter by letter, because speech recognisers get words wrong ("Gampak terbaru" still finds "gempa terbaru"). A phrase scores the F1 of how much of the text it explains and how much of it the text says, with words many commands share ("buka", "open", "hari") counting less, and the whole strings are compared too. A command runs at 0.80 or more when it leads the next by 0.10; from 0.55 Hariku asks. Aliases of two or three distinctive words work best; avoid aliases that are only a common word.

**Actions that only answer** *(core 2.8)*. With "Keep Aruna open after an answer" (Preferences, Aruna; on by default), an action that only says something runs with the bar still open, and what it `speak()`s shows in the bar's Last result. Every other action closes the bar first, as above, because it may open a window or act on the window that had the focus (typing into it, moving it). Name yours when it opens nothing and doesn't touch the focused window:

| Function | Returns | Description |
|---|---|---|
| `core.commands.add_answer_actions(action_ids)` | `None` | *(core 2.8)* One id or a list, `"<extension name>.<action name>"`, of actions that only say something. If one opens a window after all, the bar steps aside for it. Declare `"minimum_core_version": "2.8"`, or guard it with `hasattr(core.commands, "add_answer_actions")`. |
| `core.commands.is_answer_action(action_id)` | `bool` | Whether the bar stays open for it (`core.commands.ANSWER_ACTIONS` lists the core's and the official extensions'). |
| `core.commands.bar_settings()` | `dict` | *(core 2.8)* `{"keep_open": bool, "sounds": bool}`, the user's Aruna settings. The bar plays `core.commands.SEND_SOUND` (`aruna_send.wav`) for a typed command and `REPLY_SOUND` (`aruna_reply.wav`) for an answer; sound themes can replace both. |

**Commands with content (intents)** *(core 2.9)*. A command can carry words of its own: "catat beli gula", "timer mie 3 menit", "tambahkan kopi ke daftar belanja", "putar Elshinta". Register a pattern with one `{text}`; Aruna gives your handler what `{text}` held, as typed or heard, and does what your `Reply` says. Declare `"minimum_core_version": "2.9"`.

```python
import core.commands
from core.commands import Reply

def on_note(request):                     # on the UI thread; keep it quick
    note = request.text                   # "beli Gula Aren" (capitals and punctuation kept)
    if not note.strip():
        return None                       # not mine: Aruna carries on as before
    return Reply(f"Catat \"{note}\"?", confirm=lambda: save(note) or "Sudah dicatat.")

def register(bus):
    core.commands.add_intent("Notes.add", ["catat {text}", "note {text}",
                                           "tambahkan {text} ke daftar belanja"],
                             on_note, title="Notes")

def teardown():
    core.commands.remove_intent("Notes.add")
```

| Function | Returns | Description |
|---|---|---|
| `core.commands.add_intent(intent_id, patterns, handler, title=None)` | `Intent` | Patterns in any language, each with exactly one `{text}` and at least one word of its own, before, after or around it. The words are matched like command names (case, accents and punctuation don't count, misheard words like "katat" still match "catat", but a longer word such as "catatan" doesn't), and fillers before the pattern ("tolong", "Aruna") are skipped. When several intents match, the pattern with more words of its own is asked first. A command with content comes before commands and dates ("timer 10 menit" is not a reminder), but after a reminder trigger ("ingatkan aku"). The same id again replaces it. |
| `core.commands.remove_intent(intent_id)` | `bool` | In `teardown()`. |
| `core.commands.match_intents(text)` | `list` | The `IntentMatch`es (`.intent`, `.text`, `.score`) of a text, as Aruna sees them. |

`handler(request)` gets a `core.commands.Request`: `.text` (what `{text}` held), `.full_text`, `.source` (`"typed"` or `"voice"`) and `.intent_id`. It returns `None` when the text isn't for it (Aruna asks the next intent, then handles the text as before), a string to say, or a `Reply`:

| `Reply(...)` | What Aruna does |
|---|---|
| `say="..."` | Shows it in Last result and says it (Hariku Voice for commands). With "Keep Aruna open" off, Aruna closes afterwards. |
| `say="...?", confirm=fn, cancel=fn` | Asks `say`. Enter, "ya" or "yes" calls `confirm()`, whose return value (a string, a `Reply` or `None`) is the answer; Escape, "tidak" or "no" calls `cancel()` and says "OK, cancelled". By voice, Aruna listens for the answer. |
| `wait=True` | You started something slow (on a thread): speak its answer with `core.speech.speak()` when it's ready. Aruna says `say` (if any), shows "Aruna is thinking..." and puts what is spoken in Last result. |
| `then=fn` | Aruna says `say` (if any), closes, gives the focus back to the window the user was in, then calls `fn()`: type into that window, or open a window of yours. |

A handler that raises makes Aruna say "That command didn't work" (and it is logged). Everything your handler and `confirm()` speak with `core.speech.speak()` comes in Hariku Voice, like an action's answer.

**Answers told in steps** *(core 2.9)*. Aruna's Last result collects what is spoken within a moment of the answer's last line. An answer with pauses between its steps (World Trip: the captain's announcement, the engines, the arrival, a phrase in another voice) keeps it open:

| Function | Returns | Description |
|---|---|---|
| `core.commands.hold_answer(seconds)` | `float` | For `seconds` from now (300 at most), what Hariku says goes into Last result, pauses and all: the answer shown keeps growing, and while Aruna is open without one, the speech starts one (without the "answered" sound). Call it again before each step; `0` ends the hold. The next command still starts a new answer; closing Aruna ends everything. |
| `core.commands.show_answer(text)` | `bool` | Add a line to Last result without saying it, for something you play yourself (a phrase spoken with `core.voice.preview()` in another language's voice). Only while Aruna waits for an answer or one is held; returns whether Aruna showed it. |

```python
def on_trip(request):
    start_trip(request.text)          # on a thread; speaks each step as it comes
    return Reply(wait=True)

def before_each_step(seconds):
    core.commands.hold_answer(seconds + 5)
```

Hariku's own aliases for the core and the official extensions are in `core.commands.BUILTIN_ALIASES`. The core also has **Say the time** and **Say today's date** (no key by default) for "jam berapa" and "what time is it".

**A speech recogniser** (the Voice Control extension) registers itself; there is one at a time:

```python
core.commands.register_listener(start, stop, is_available=None, listen_on_open=None, name="")
core.commands.unregister_listener(start)     # in teardown()
```

| Argument | What Hariku expects |
|---|---|
| `start(on_event)` | Start listening and return at once: `True` when it started. Call `on_event(kind, value)` from any thread: `("listening", None)` once the microphone is open, `("recognising", None)` when recording ended, `("text", "...")` with what was said, `("error", "...")` with a message for the user (said through Hariku Voice; listening has ended) or `("stopped", None)` when it ended without text. When it can't start, send `("error", why)` and return `False`. |
| `stop(discard)` | Stop recording now: recognise what was heard, or with `discard=True` drop it and send only `("stopped", None)`. The hotkey or Enter pressed while listening calls `stop(False)`; Escape and closing the bar `stop(True)`. |
| `is_available()` | Fast: whether it can listen (installed, a model downloaded). |
| `listen_on_open()` | Fast: whether to listen as soon as the bar opens. |

Before listening, silence the screen reader (`core.speech.silence()`) and Hariku Voice (`core.voice.stop()`), play `core.commands.LISTEN_SOUND` and start recording after it (its length: `core.sounds.sound_path()`), and play `LISTEN_END_SOUND` when recording ends. After a question it asked by voice ("Did you mean …?", "Save?"), the bar listens again for the answer once the question has been said.

**Rules:**
- Recordings stay in memory or in a temporary file deleted right after use; never send them anywhere without asking the user first, and say so on your page.
- Never install a keyboard hook. Global keys go through `core.hotkeys` (`RegisterHotKey`).

**A future AI fallback:** `core.commands.set_fallback(handler)` registers `handler(text, commands)`, called on a worker thread for a text the rules didn't understand; it returns an action id or `None`. The bar only ever asks "Did you mean …?" about its answer; it never runs it straight away. Reserved for Hariku's own AI extension.

### Morning Briefing and Evening Summary

The Morning Briefing extension speaks a morning briefing (B) and an evening summary (Shift+B), and lets other extensions add a sentence to each through two events. Subscribe in `register(bus)`; the Morning Briefing emits them with a new, empty list:

| Event | Arguments | When |
|---|---|---|
| `on_briefing_collect` | `lines` | While the morning briefing is built. Append what matters today, e.g. `"Weather in Jakarta: light rain, 27 degrees."`. |
| `on_evening_collect` | `lines` | *(Morning Briefing 1.1)* While the evening summary is built. Append what matters for tonight or tomorrow, e.g. `"Tomorrow: light rain, 31 degrees."`. |

The contract is the same for both:
- The handler runs on the UI thread and must return quickly: use data you already have (a cache). No network requests, subprocesses or sleeps. With no data yet, append nothing.
- Append plain text in the user's current language: one short sentence, two at most. Don't call `speak()`; the briefing speaks it.
- Only append; don't change what other extensions added. Non-strings and blank entries are ignored, and an exception in your handler is logged without stopping the briefing.
- Contributions are spoken last, in subscription order.

```python
def _on_evening_collect(lines):
    if _cached_tomorrow:
        lines.append(_cached_tomorrow)   # "Tomorrow: light rain, 31 degrees."

bus.subscribe("on_evening_collect", _on_evening_collect)
```

---

### Translation (i18n)

Hariku V2 uses a JSON-based translation system. No compilation or build tools required.

```python
from core.i18n import get_translator, get_current_language, get_available_languages
```

| Function | Returns | Description |
|---|---|---|
| `get_translator(domain, locales_dir=None)` | `callable` | Returns a `_(key, **kwargs)` function that translates message keys for the given domain. |
| `get_current_language()` | `str` | Returns the active language code (e.g., `"en"`, `"id"`). |
| `get_available_languages(domain)` | `list[dict]` | Returns a list of available language manifests for a domain. |
| `set_language(language_code)` | None | Change the active language and save to config. **Requires app restart** to take full effect. |
| `get_language_manifest(domain, language_code=None)` | `dict` | Returns the manifest dict for a specific language in a domain. If `language_code` is `None`, uses the current language. |
| `format_date(date_obj, format_string)` | `str` | Formats a date using **translated** day and month names. Supports `%A` (full day), `%a` (short day), `%B` (full month), `%b` (short month), `%d`, `%m`, `%Y`. |
| `apply_rtl_layout(window)` | None | Checks the current language manifest for the `rtl` flag and applies Right-To-Left layout mirroring to a `wx.Window`. Call this in your dialog's `__init__` if you support RTL languages. |

#### Adding Translations to Your Extension

1. Create a `locales/` folder inside your extension.
2. Add one JSON file per language (e.g., `en.json`, `id.json`).
3. Each file must have a `manifest` section and a `messages` section.

**Extension structure:**
```
my_extension/
├── manifest.json
├── main.py
└── locales/
    ├── en.json
    └── id.json
```

**Language file format (`locales/en.json`):**
```json
{
    "manifest": {
        "language_name": "English",
        "language_code": "en",
        "translator": "Your Name",
        "email": "you@example.com",
        "version": "1.0",
        "core_version": "2.0",
        "rtl": false
    },
    "messages": {
        "greeting": "Hello, {name}!",
        "btn_save": "Save",
        "status_loading": "Loading data..."
    }
}
```

**Manifest fields:**

| Field | Required | Description |
|---|---|---|
| `language_name` | ✅ | Human-readable name (e.g., "Bahasa Indonesia") |
| `language_code` | ✅ | ISO code (e.g., `"en"`, `"id"`, `"ar"`) |
| `translator` | ✅ | Name of the translator |
| `email` | ✅ | Contact email for translation issues |
| `version` | ✅ | Version of the translation |
| `core_version` | ❌ | Hariku version this translation targets |
| `rtl` | ❌ | Set `true` for right-to-left languages (Arabic, Hebrew) |

**Usage in `main.py`:**
```python
import os
from core.i18n import get_translator

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("my_extension", os.path.join(EXT_DIR, "locales"))

# Simple key lookup (falls back to English, then to the key itself)
speak(_("greeting", name="Rafli"))

# Use in UI labels
wx.Button(panel, label=_("btn_save"))
```

- If a key is missing in the user's language, it automatically falls back to English.
- If the key is also missing in English, the raw key string is returned (e.g., `"btn_save"`).
- Placeholders use Python's `str.format()` syntax: `{name}`, `{count}`, etc.

**Formatting dates with translated names:**
```python
from core.i18n import format_date
from datetime import date

today = date.today()
formatted = format_date(today, "%A, %d %B %Y")
# English: "Thursday, 19 June 2026"
# Indonesian: "Kamis, 19 Juni 2026"
speak(formatted)
```

**Supporting RTL languages:**
```python
from core.i18n import apply_rtl_layout

class MyDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="My Dialog")
        apply_rtl_layout(self)  # Mirrors layout if language is RTL
        # ... build UI ...
```

---

### Constants

```python
from core.constants import APP_NAME, CORE_VERSION, CORE_VERSION_FLOAT
```

| Constant | Type | Value (example) | Description |
|---|---|---|---|
| `APP_NAME` | `str` | `"Hariku"` | The application name. |
| `CORE_VERSION` | `str` | `"2.2.0"` | Full version string of the Hariku core (e.g., `"2.2.0"`). |
| `CORE_VERSION_FLOAT` | `float` | `2.2` | Major.minor version as a float. Used for extension compatibility checks. |

**Example:**
```python
from core.constants import APP_NAME, CORE_VERSION

speak(f"Running {APP_NAME} version {CORE_VERSION}")
```

---

### App Utilities

```python
import core.api
```

These utility functions provide access to common application-level operations.

| Function | Description |
|---|---|
| `core.api.restart_app(safe_mode=False)` | Fully restarts the application. Emits `on_unload`, spawns a new process, and terminates the current one. Set `safe_mode=True` to restart without loading any extensions. |
| `core.api.open_preferences(tab_name=None)` | Opens the Preferences dialog. Optionally pass a `tab_name` string to jump directly to a specific settings tab. |
| `core.api.open_log_viewer()` | Opens the debug log file in the system's default text editor. |
| `core.api.open_data_folder()` | Opens the Hariku data directory (`%APPDATA%/Hariku2`) in Windows Explorer. |
| `core.api.clear_cache()` | Deletes the `.cache` folder inside the extensions directory. Useful for troubleshooting. |
| `core.api.set_autostart(enable=True)` | Configures the Windows Registry to run Hariku automatically on system startup. Pass `False` to remove the autostart entry. *(core 2.7)* The entry starts Hariku with `core.api.AUTOSTART_FLAG` (`--autostart`); Hariku adds it to an older entry by itself. |
| `core.api.started_with_windows()` | *(core 2.7)* `True` when Windows started Hariku (the autostart entry), `False` when the user or a restart did. |

**Path variables:**

| Variable | Description |
|---|---|
| `core.api.USER_DATA_DIR` | Absolute path to `%APPDATA%/Hariku2` — the root data directory. |
| `core.api.DATA_DIR` | Absolute path to `%APPDATA%/Hariku2/data` — where `load_data()` / `save_data()` stores JSON files. |

**Example:**
```python
import core.api
from core.speech import speak

# Open preferences to the "My Extension" tab
core.api.open_preferences("My Extension")

# Get data directory path
speak(f"Data is stored in: {core.api.DATA_DIR}")

# Restart in safe mode (no extensions)
if core.api.prompt_yes_no("Restart", "Restart in safe mode?"):
    core.api.restart_app(safe_mode=True)
```

---

### Main Window Access

```python
import core.api
```

| Variable | Type | Description |
|---|---|---|
| `core.api.main_window_instance` | `wx.Frame` | A global reference to the main Hariku window. Use this as a `parent` when creating your own dialogs, or to interact with the calendar widget. |

**Example:**
```python
import wx
import core.api

# Use as parent for a custom dialog
parent = core.api.main_window_instance

dialog = wx.MessageDialog(parent, "Hello from my extension!", "Custom Dialog")
dialog.ShowModal()
dialog.Destroy()
```

> **Note:** `core.api.main_window_instance` is `None` until the UI has fully initialized. If you need to access the main window, do so after the `on_ui_ready` or `on_app_startup` event.

> **Alternative:** You can also access the main window via wxPython directly with `wx.GetApp().GetTopWindow()`, but using `core.api.main_window_instance` is preferred for clarity.

---

### Extension Manager

```python
from core import extension_manager
```

These functions let your extension query, enable, disable, or inspect other installed extensions at runtime.

| Function / Variable | Returns | Description |
|---|---|---|
| `extension_manager.LOADED_EXTENSIONS` | `dict` | A dictionary of all currently loaded extensions, keyed by `ext_id`. Each value is a dict with keys: `manifest`, `module`, `is_unpacked`, `is_official`. |
| `extension_manager.EXTENSIONS_DIR` | `str` | Absolute path to the user's extensions directory. |
| `extension_manager.get_installed_extensions_info()` | `list[dict]` | Returns a list of **all** installed extensions (enabled and disabled). Each dict has: `id`, `name`, `version`, `author`, `is_official`, `description`, `is_enabled`, `is_unpacked`, `path`. |
| `extension_manager.toggle_extension(ext_id, enable=True)` | None | Enable or disable an extension by its ID. **Takes effect on next restart.** |
| `extension_manager.uninstall_extension(ext_id)` | `True` / `False` | Permanently deletes an extension's `.hrk` file, unpacked folder, and cache. **Use with caution — this is destructive.** |

**Example:**
```python
from core import extension_manager
from core.speech import speak

# List all loaded extensions
for ext_id, ext_data in extension_manager.LOADED_EXTENSIONS.items():
    name = ext_data["manifest"]["name"]
    version = ext_data["manifest"]["version"]
    source = "unpacked (dev)" if ext_data["is_unpacked"] else "packed (.hrk)"
    speak(f"{name} v{version} — {source}")

# Check if a specific extension is loaded
if "diary" in extension_manager.LOADED_EXTENSIONS:
    speak("Diary extension is active!")

# Get info about all installed extensions (including disabled)
all_extensions = extension_manager.get_installed_extensions_info()
for ext in all_extensions:
    status = "enabled" if ext["is_enabled"] else "disabled"
    speak(f"{ext['name']} — {status}")

# Disable an extension (requires restart)
extension_manager.toggle_extension("some_extension", enable=False)
```

---

### Extension Store

```python
from core import store
```

These functions let your extension interact with the Hariku Extension Store (its registry is a JSON file hosted on GitHub Pages; see `core/endpoints.py`).

| Function | Returns | Description |
|---|---|---|
| `store.fetch_registry()` | `list[dict]` | Fetches the full extension registry from the cloud. Each dict contains extension metadata (id, name, version, author, description, download_url, etc.). |
| `store.check_for_updates()` | `list[dict]` | Compares the cloud registry against loaded extensions. Returns a list of update dicts with: `id`, `name`, `current_version`, `new_version`, `download_url`. Only checks packed `.hrk` extensions. |
| `store.download_extension(ext_id, download_url)` | `True` / `False` | Downloads a `.hrk` file to the extensions directory. **Use with caution** — has side effects on the filesystem. |

**Example:**
```python
from core import store
from core.speech import speak

# Check if updates are available
def check():
    updates = store.check_for_updates()
    if updates:
        for u in updates:
            speak(f"{u['name']}: {u['current_version']} → {u['new_version']}")
    else:
        speak("All extensions are up to date!")

import core.api
core.api.run_thread(check)
```

---

### Telemetry

```python
from core import telemetry
```

| Function | Returns | Description |
|---|---|---|
| `telemetry.is_enabled()` | `bool` | Returns `True` if the user has telemetry enabled (opt-out model, defaults to `True`). Useful if your extension collects any usage data — you should respect this setting. |

> **Note:** The core's own telemetry ping is currently **disabled** (its old endpoint was retired and there is no replacement), so the core sends nothing. `is_enabled()` still reflects the user's preference — honor it if your extension collects data.

**Example:**
```python
from core import telemetry

if telemetry.is_enabled():
    # OK to send anonymous usage stats
    pass
else:
    # User has opted out — do not send any data
    pass
```

---

## Lifecycle Events

Hariku provides two mechanisms for lifecycle management: **bus events** (subscription-based) and the **`teardown()` function** (direct call).

### Bus Events

These events are emitted by the Hariku core at specific moments. Subscribe to them in your `register()` function.

| Event | Arguments | When |
|---|---|---|
| `on_app_startup` | None | After all extensions are loaded and the UI is visible. |
| `on_minute_tick` | `datetime.datetime` | Fired every 60 seconds (Heartbeat). Useful for background cron jobs, checking emails, or stock tickers without setting up your own thread. The payload is the current datetime object. |
| `on_clipboard_changed` | `text` | Fired when the OS clipboard text changes. The payload is the new clipboard text. |
| `on_active_window_changed` | `dict` | Fired when the user switches to a different application. The payload is `{"title": "...", "process": "..."}`. |
| `on_user_idle` | `float` | Fired when the user has not touched the mouse or keyboard for more than 5 minutes (300 seconds). Payload is the exact idle time in seconds. |
| `on_user_active` | `float` | Fired when the user returns from being idle (touches mouse/keyboard after being AFK). Payload is the current idle time (close to 0). |
| `on_power_changed` | `dict` | Fired when the laptop is plugged in, unplugged, or battery percentage changes. Payload is `{"ac_line_status": 0/1, "battery_percent": 0-100, "charging": bool}`. |
| `on_network_changed` | `bool` | Fired when the system connects or disconnects from the internet. Payload is `True` (Online) or `False` (Offline). |
| `on_before_speak` | `payload` | Fired immediately before Hariku speaks. `payload` is a dict with `"text"`, `"interrupt"`, and `"cancel"`. Extensions can modify the text, toggle interrupt, or set `"cancel": True` to prevent speech. *(Since 2.7)* When a [Hariku Voice](#hariku-voice) speaks instead of the screen reader, it fires once too, with `"kind"` (`"greeting"`, `"briefing"`, `"reminder"` or `"command"`) and `"voice"` (the provider id) added; cancelling it silences the voice. |
| `on_date_changed` | `date_str` | When the user navigates to a different date on the calendar. |
| `on_ui_ready` | `main_window` | When the main window is fully initialized. You receive the `MainWindow` instance as an argument. |
| `on_unload` | None | When the application is shutting down. Save state here. |
| `on_core_preferences_updated` | None | When the user applies changes in General Settings. |
| `on_build_general_settings_panel` | `panel, sizer` | When the General Settings panel is being constructed. Use this to inject your own controls into the General Settings page. |
| `on_apply_general_settings_panel` | `panel` | When the user applies General Settings. Use this to read values from your injected controls. |
| `on_build_tray_menu` | `menu, frame` | When the system tray right-click menu is being built. Use this to add your own menu items to the tray icon context menu. |
| `on_build_tray_tooltip` | `tooltip_data` | When the tray icon tooltip is being updated. `tooltip_data` is a dict with a `"text"` key — modify `tooltip_data["text"]` to append your own information. |
| `on_open_preferences` | `tab_name` | When the Preferences dialog is requested to open (optionally to a specific tab). |
| `on_places_changed` | None | *(Since 2.8)* When the user saved changes to their places (Preferences, Places). Read them again with `core.places`; see [Places](#places). |
| `on_reminder_fired` | `reminder` | *(Since 2.4)* When a reminder comes due and is announced. `reminder` is the stored dict (`id`, `title`, `date`, `time`, ...), with the raw text; see [Personal Profile](#personal-profile) for filling in its placeholders. |
| `on_fetch_agenda` | `payload` | When the Agenda list is being built for a specific date. `payload` is a dict containing `"date"` (YYYY-MM-DD) and `"reminders"` (list of dicts). Modify `payload["reminders"]` to inject your own agenda items dynamically without saving them to disk. |
| `on_agenda_item_deleted` | `event_id` | Fired when the user presses 'Delete Selected' in the main Agenda Dialog. `event_id` is the ID of the deleted item. Use this to delete your dynamically injected virtual events. |
| `on_enter_pressed` | `payload` | *(Since 2.2.0)* Fired when the user presses Enter on the calendar. `payload` is a dict containing `"date"` (YYYY-MM-DD) and `"handled"` (bool, initially `False`). Set `payload["handled"] = True` to prevent the default Add Reminder dialog from opening, allowing your extension to show its own custom dialog instead. |

**Example — Overriding the Enter key to show a custom dialog:**
```python
import wx
import core.api
from core.speech import speak

def _on_enter(payload):
    date_str = payload["date"]
    payload["handled"] = True  # Block the default Add Reminder dialog

    parent = core.api.main_window_instance
    title = core.api.prompt_text("Quick Event", f"Event title for {date_str}:")
    if title:
        speak(f"You entered: {title}")

def register(event_bus):
    event_bus.subscribe("on_enter_pressed", _on_enter)
```

**Example — Injecting dynamic items into the Agenda list:**
```python
def _on_fetch_agenda(payload):
    date_str = payload.get("date")
    # For example, inject a special event on a specific date
    if date_str == "2026-12-31":
        payload["reminders"].insert(0, {
            "id": "my_ext_new_year",
            "title": "🎉 New Year's Eve Celebration!",
            "date": date_str,
            "time": "23:59",
            "is_done": False
        })

def register(event_bus):
    event_bus.subscribe("on_fetch_agenda", _on_fetch_agenda)
```

**Example — Adding a menu item to the system tray:**
```python
import wx
from core.events import bus
from core.speech import speak

def _on_tray_menu(menu, frame):
    item = menu.Append(wx.ID_ANY, "My Extension Action")
    frame.Bind(wx.EVT_MENU, lambda e: speak("Tray action triggered!"), item)

def register(event_bus):
    event_bus.subscribe("on_build_tray_menu", _on_tray_menu)
```

**Example — Adding info to the tray tooltip:**
```python
def _on_tooltip(tooltip_data):
    tooltip_data["text"] += "\nMy Extension: Active"

def register(event_bus):
    event_bus.subscribe("on_build_tray_tooltip", _on_tooltip)
```

**Example — Injecting controls into General Settings:**
```python
import wx
from core.events import bus
import core.api

_my_checkbox = None

def _on_build_settings(panel, sizer):
    global _my_checkbox
    _my_checkbox = wx.CheckBox(panel, label="Enable My Extension Feature")
    config = core.api.load_data("MyExtension")
    _my_checkbox.SetValue(config.get("feature_enabled", True))
    sizer.Add(_my_checkbox, 0, wx.ALL, 5)

def _on_apply_settings(panel):
    if _my_checkbox:
        config = core.api.load_data("MyExtension")
        config["feature_enabled"] = _my_checkbox.GetValue()
        core.api.save_data("MyExtension", config)

def register(event_bus):
    event_bus.subscribe("on_build_general_settings_panel", _on_build_settings)
    event_bus.subscribe("on_apply_general_settings_panel", _on_apply_settings)
```

### The `teardown()` Function

In addition to the `on_unload` bus event, the extension manager also calls a **`teardown()`** function directly on your extension module when the app shuts down. This is the recommended place to clean up resources like timers, threads, and open files.

Unlike `on_unload` (which is a bus event you subscribe to), `teardown()` is a **module-level function** that the extension manager calls automatically — you just need to define it in your `main.py`.

```python
# main.py

_my_timer = None

def register(bus):
    global _my_timer
    _my_timer = core.api.set_interval(60000, do_something)
    bus.subscribe("on_date_changed", on_date_changed)

def teardown():
    """Called by the extension manager when the app is shutting down.
    Clean up timers, threads, file handles, etc. here."""
    global _my_timer
    if _my_timer:
        _my_timer.Stop()
        _my_timer = None
```

> **When to use which?**
> - Use **`teardown()`** for cleaning up your own resources (stopping timers, closing files, etc.).
> - Use **`on_unload`** via `bus.subscribe()` if you need to coordinate with other extensions or perform a final save.

---

## Bundling Third-Party Libraries

If your extension needs a library that is **not** part of the Python standard library and **not** bundled with Hariku core, you must include it yourself.

### What's already available (no need to bundle):
- Python standard library (`json`, `os`, `datetime`, `zoneinfo`, `urllib`, `sqlite3`, `socket`, `ssl`, `html`, `csv`, `re`, `math`, `collections`, `threading`, `subprocess`, `hashlib`, `xml`, `http`, etc.). *(core 2.8)* `tarfile` and `bz2` too; a compiled Hariku older than 2.8 may lack them, so import them guarded (`try: import tarfile` / `except ImportError:`) if your extension also runs there. The compiled Hariku only contains the modules the core imports (`core/stdlib_includes.py` lists the extra ones), and `tests/test_extension_stdlib.py` fails for an extension that imports anything else.
- `wx` (wxPython) — UI framework
- `cytolk` / `tolk` — Screen reader speech
- `cryptography` — Encryption (Fernet, etc.)
- `pyperclip` — Clipboard
- `tzdata` — IANA time zone database, so `zoneinfo` works on Windows (used for world times)

### How to bundle:
1. Create a `lib/` folder inside your extension.
2. Copy the library's package folder into `lib/`.
3. Import normally — the `lib/` folder is automatically added to `sys.path`.

```
my_extension/
├── manifest.json
├── main.py
└── lib/
    └── requests/
        └── __init__.py
```

```python
# In main.py — just import normally
import requests
```

> **Important:** Only bundle pure-Python libraries. C-extension libraries (`.pyd`, `.dll`) will not work inside `.hrk` files on different machines.

---

## Packaging & Distribution

### Using the Packager

```bash
# Package a specific folder
python tools/packager.py path/to/my_extension

# Specify output directory
python tools/packager.py my_extension --output dist/

# Interactive mode (will prompt for folder)
python tools/packager.py
```

The packager will:
1. ✅ Validate your `manifest.json`
2. 🧹 Clean `__pycache__` folders
3. 📦 Create `my_extension.hrk`
4. 📊 Report the final file size

### Testing During Development

For faster iteration, place your extension as an **unpacked folder** directly in the `extensions/` directory. Hariku will load it directly without needing to package it.

Unpacked folders always take priority over `.hrk` files with the same name.

### Publishing to the Hariku Store

The store is served from GitHub (no separate server): manifests live on GitHub
Pages and `.hrk` binaries are GitHub Release assets. See `core/endpoints.py` for
the exact URLs. To publish your extension:
1. Package your extension into a `.hrk` file.
2. Submit it to the Hariku repo (open an issue / PR at the repository in
   `core/endpoints.py` → `SUPPORT_URL`) for review.
3. Once approved, the maintainers upload the `.hrk` as a Release asset and add
   an entry to `registry.json` (plus its SHA256 to `trusted_extensions.json`) on
   GitHub Pages — after which it appears in the in-app Extension Store.

---

## Best Practices

1. **Always use `core.api.run_thread()`** for network requests. Never block the UI thread.
2. **Use `core.api.load_data()` / `save_data()`** for settings. Don't create your own config files.
3. **Set `interrupt=True`** on `speak()` only when delivering urgent information.
4. **Handle errors gracefully.** Wrap network calls and file I/O in try/except blocks.
5. **Use logging** instead of `print()`:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   logger.info("Extension loaded")
   logger.error("Something went wrong")
   ```
6. **Set `minimum_core_version`** to the lowest version that supports the APIs you use.
7. **Don't hardcode paths.** Use `core.api.get_storage_dir()` for file storage and `core.api.DATA_DIR` for reference.
8. **Keep your extension folder name lowercase** with underscores (e.g., `my_cool_tool`).
9. **Test in both dev mode** (unpacked folder) **and packaged mode** (`.hrk` file) before distributing.
10. **Use `_()` for all user-facing strings** if you want your extension to support multiple languages.
11. **Always define `teardown()`** in your `main.py` to clean up resources (timers, threads, file handles) when the app shuts down. This prevents errors and resource leaks.
12. **Stop your timers in `teardown()`.** Leaving timers running after unload will cause crashes.
13. **Respect the user's telemetry preference.** If your extension collects any data, check `telemetry.is_enabled()` first.
14. **Use `core.api.main_window_instance` as the parent** for any custom `wx.Dialog` you create. This ensures proper window stacking and accessibility.
15. **Use `apply_rtl_layout()`** in your dialogs if you support RTL languages like Arabic or Hebrew.
16. **Use `format_date()` for displaying dates** instead of formatting them yourself — this ensures dates are displayed in the user's language.

---

## For Translators

Hariku's own text is in `locales/en.json` and `locales/id.json`; a new language is a copy of `en.json` with its `manifest` filled in (see [Translation (i18n)](#translation-i18n)). The quick reminder also needs a language pack, so it understands sentences typed in that language.

### Quick Reminder Languages

The quick reminder (N) and the reminder dialog's "Or type it in one sentence" field read a sentence such as "minum obat besok jam 8 pagi, tiap hari" with `core/when.py`. That reader knows no language: every word comes from a language pack, one Python file per language in `core/`: `when_lang_id.py`, `when_lang_en.py` and `when_lang_de.py`. A pack is plain data, no code: a `PACK` dict with the words and an `EXAMPLES` list of sentences with the reminder each must give.

The Hariku language, English and Indonesian are always on; users switch the others on in Preferences, Reminders. Several packs can be on at once, so people can mix languages ("meeting besok jam 3"); how clashes are settled is described at the top of `core/when.py`. What Hariku says back ("..., every day. Save?") comes from the `qr_` keys in `locales/`, in the Hariku language.

#### How to add a language

1. Copy `core/when_lang_en.py` to `core/when_lang_<code>.py`, where `<code>` is the language code (`"fr"`, `"ms"`, `"nl"`...). Set `"code"` and `"name"` (the language's own name, shown in Preferences).
2. Translate the word lists (see the fields below). Write words in lower case; accents are fine. A phrase may have several words ("the day after tomorrow"). Case and punctuation such as commas never matter in what the user types.
3. Fill in `EXAMPLES`: at least five sentences, each with a fixed "now" and the reminder it must give. Cover your language's own forms: its half-hour idiom, its "every Monday", its "in 30 minutes".
4. In `core/when_packs.py`, import the module next to the others (`from core import when_lang_de, when_lang_en, when_lang_id, when_lang_<code>`) and add it to `PACK_MODULES`. The compiled Hariku only contains modules the core imports by name, so a pack that isn't imported there is missing for every installed user.
5. Run the tests:

   ```
   venv\Scripts\python.exe -m pytest tests/test_when.py -q
   ```

   `test_every_pack_file_is_imported_by_name` checks step 4, `test_pack_is_valid` checks the fields and that every pattern compiles, and `test_pack_examples` runs your `EXAMPLES` table with only your pack on.

#### Patterns

Fields marked "pattern" are short templates:

| Write | Means | Example |
|---|---|---|
| `word` | a word the user types | `lagi` |
| `(a\|b c)` | one of the choices | `(lewat\|lebih)` |
| `[a\|b]` | optional | `[menit]` |
| `{h}` | an hour, 0-24, in digits or number words ("9", "neun") | `setengah {h}` |
| `{m}` | minutes, 0-59 | `{h} lewat {m}` |
| `{n}` | a count ("2", "two", "a") | |
| `{unit}` | a unit from `units` (minute, hour, day, week, month, year) | `einmal pro {unit}` |
| `{dur}` | a count and a unit ("30 minutes", "sejam", "half an hour") | `{dur} lagi` |

#### Fields

All lists hold lower-case words or phrases.

| Field | What it holds |
|---|---|
| `code`, `name` | The language code and the language's own name. |
| `date_order` | `"DMY"` or `"MDY"`: how to read 5/10 (5 October or May 10). |
| `numbers` | `{"eight": 8, ...}`: 0-12 at least, plus 15, 20, 30, 45. |
| `count_words` | Words that mean "one" only before a unit ("a", "an", "ein"). |
| `weekdays` | 7 lists, Monday first. Full names, recognised anywhere. |
| `weekday_abbreviations` | 7 lists. Only recognised after a marker ("on Mon", "am Mo"). |
| `weekday_plurals` | 7 lists meaning "every Monday" by themselves ("mondays", "montags"). |
| `months` | 12 lists: full names and abbreviations. Only read next to a day. |
| `relative_days` | `{"tomorrow": 1, ...}`; a value `[days, part_of_day]` adds a part of the day: `"tonight": [0, "evening"]`. |
| `units` | `{"minute": [...], "hour": [...], "day": [...], "week": [...], "month": [...], "year": [...]}`. |
| `counted_units` | `{"half an hour": ["minute", 30], "sejam": ["hour", 1]}`. |
| `parts_of_day` | `[{"part": "morning", "words": [...]}, ...]`. Parts: morning, midday, afternoon, evening, night. Optional `"hours": [first, last]` and `"default": "HH:MM"` replace the defaults of `PARTS_OF_DAY` in `core/when.py` for these words only (hours past 24 are after midnight). |
| `noon`, `midnight` | Words for 12:00 and 00:00 ("noon", "tengah malam"). |
| `meridiem_am`, `meridiem_pm` | "am", "pm". |
| `clock_prefixes` | Words before a clock time: "at", "jam", "um". |
| `clock_suffixes` | Words after one: "o'clock", "Uhr", "WIB". |
| `clock_idioms` | `[{"pattern": ..., "minutes": ...}]`: half and quarter forms. `"minutes"` is added to {h}:00, or `"+m"`/`"-m"` adds or subtracts {m}. "halb {h}" is -30 (halb neun = 08:30, half BEFORE nine) while English "half past {h}" is +30 (half AFTER). |
| `relative_patterns` | Patterns with {dur}: "in {dur}", "{dur} lagi". |
| `weekday_prefixes` | Words before a weekday that change nothing: "on", "hari", "am". |
| `next_before`, `next_after` | "next" words before or after a weekday or a week/month/year: "next Monday", "Senin depan", "nächste Woche". |
| `this_before`, `this_after` | "this" words: "this evening", "malam ini", "nanti malam". |
| `every`, `every_other` | "every", "each" / "every other". |
| `repeat_leads` | Optional words before a repeat: "repeat", "ulangi". |
| `repeat_words` | `{"daily": [...], "weekly": [...], "monthly": [...], "yearly": [...]}`. |
| `repeat_patterns` | Extra "every <dur>" patterns with {dur} or {unit}: "{dur} sekali". |
| `day_prefixes` | Words before a plain day of the month: "tanggal 5". |
| `ordinal_day_prefixes` | Words before an ordinal day: "the 5th", "am 5.". |
| `ordinal_suffixes` | "st", "nd", "rd", "th", or "." for German "5.". |
| `date_connectors` | "of" in "the 5th of October". |
| `fillers` | Small words dropped when they touch a date or time: "at", "pada". |
| `triggers` | Patterns stripped from the start: "[please] remind me [to]". |
| `infinitive_marker` | German "zu": "erinnere mich, die Tabletten zu nehmen" gives "Die Tabletten nehmen". |

#### The EXAMPLES table

`EXAMPLES` is a list of `(now, sentence, expected)`: `now` is `"YYYY-MM-DD HH:MM"`, and `expected` a dict with any of `title`, `date`, `time`, `recurrence`, `interval` and `time_assumed`. The test reads each sentence at that moment with only your pack on, and checks those fields and that the reminder can be saved. From the English pack:

```python
# (now, sentence, expected). Thursday 24 September 2026 10:40 unless noted.
EXAMPLES = [
    ("2026-09-24 10:40", "remind me to call mom tomorrow at 7pm",
     {"title": "Call mom", "date": "2026-09-25", "time": "19:00"}),
    ("2026-09-24 10:40", "pay rent monthly on the 1st",
     {"title": "Pay rent", "date": "2026-10-01", "time": "09:00", "recurrence": "monthly",
      "time_assumed": True}),
    ("2026-09-24 10:40", "team meeting every other week on Friday at 3",
     {"title": "Team meeting", "date": "2026-09-25", "time": "15:00", "recurrence": "weekly",
      "interval": 2}),
]
```

The rules for dates and times (which day "Monday" is, when "at 8" means 20:00, what happens without a time) are the same for every language and are described at the top of `core/when.py`.
