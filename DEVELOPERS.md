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

---

## API Reference

All core modules are available via standard Python imports. No installation needed.

### Speech

```python
from core.speech import speak, TOLK_LOADED
```

| Function / Variable | Description |
|---|---|
| `speak(text, interrupt=False)` | Speak text through the active screen reader (NVDA, JAWS, etc.). Set `interrupt=True` to cut off any current speech. |
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
| `set_theme_dir(path_or_None)` | *(core 2.6)* Use a folder of `.wav` files named like Hariku's sounds as the active theme; `None` goes back to the built-in sounds. Only plain file names are looked up in it, never paths. |
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
| `reminders.load_reminders()` | `list[dict]` | Load all reminders. Each dict contains `id`, `title`, `date` (YYYY-MM-DD), `time` (HH:MM), and `is_done` (bool). It may also carry an internal `notified` flag once the reminder has fired — leave that field alone. |
| `reminders.get_reminders_for_date(date_str)` | `list[dict]` | Get all reminders for a specific date (`"YYYY-MM-DD"`). |
| `reminders.add_reminder(title, date_str, time_str)` | None | Create a new reminder. A unique UUID is assigned automatically. `date_str` = `"YYYY-MM-DD"`, `time_str` = `"HH:MM"`. |
| `reminders.delete_reminder(rem_id)` | None | Delete a reminder by its UUID. Speaks confirmation. |
| `reminders.mark_as_done(rem_id)` | None | Mark a reminder as done by its UUID. Speaks confirmation. |
| `reminders.snooze_reminder(rem_id, minutes=5)` | None | Snooze a reminder — pushes its date/time forward by the specified number of minutes. Speaks confirmation. |

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
| `core.api.set_autostart(enable=True)` | Configures the Windows Registry to run Hariku automatically on system startup. Pass `False` to remove the autostart entry. |

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
| `on_before_speak` | `payload` | Fired immediately before Hariku speaks. `payload` is a dict with `"text"`, `"interrupt"`, and `"cancel"`. Extensions can modify the text, toggle interrupt, or set `"cancel": True` to prevent speech. |
| `on_date_changed` | `date_str` | When the user navigates to a different date on the calendar. |
| `on_ui_ready` | `main_window` | When the main window is fully initialized. You receive the `MainWindow` instance as an argument. |
| `on_unload` | None | When the application is shutting down. Save state here. |
| `on_core_preferences_updated` | None | When the user applies changes in General Settings. |
| `on_build_general_settings_panel` | `panel, sizer` | When the General Settings panel is being constructed. Use this to inject your own controls into the General Settings page. |
| `on_apply_general_settings_panel` | `panel` | When the user applies General Settings. Use this to read values from your injected controls. |
| `on_build_tray_menu` | `menu, frame` | When the system tray right-click menu is being built. Use this to add your own menu items to the tray icon context menu. |
| `on_build_tray_tooltip` | `tooltip_data` | When the tray icon tooltip is being updated. `tooltip_data` is a dict with a `"text"` key — modify `tooltip_data["text"]` to append your own information. |
| `on_open_preferences` | `tab_name` | When the Preferences dialog is requested to open (optionally to a specific tab). |
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
- Python standard library (`json`, `os`, `datetime`, `zoneinfo`, `urllib`, `sqlite3`, `socket`, `ssl`, `html`, `csv`, `re`, `math`, `collections`, `threading`, `subprocess`, `hashlib`, `xml`, `http`, etc.)
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
