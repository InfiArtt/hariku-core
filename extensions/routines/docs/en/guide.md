# Routines

Routines runs a chain of actions for you when the moment comes, in the style of iOS
Shortcuts. A routine has conditions, which say when, and actions, which say what: "at
07:00 on weekdays, say good morning and open my news site". It needs Hariku 2.7 or newer.

Routines' windows are in English only.

## Getting started

Routines has no key at first. Open Aruna (Ctrl+Alt+Backspace), type "manage routines" and
press Enter. The "Routines" window opens on the list of your routines, each with its
state, such as "Good morning — On".

To give it a key, open Preferences (Ctrl+P), Input Gestures, and look under Routines for
"Manage Routines (Shortcuts)".

## Making your first routine

This routine greets you at 07:00 on weekdays.

1. In the Routines window, press "Add". The "Edit Routine" window opens on "Name". Type
  Good morning.
2. Press Tab until you reach "Add condition", and press it. In "Type", choose "At a
  specific time (HH:MM)". Tab to "Time (HH:MM)", type 07:00, and press OK.
3. Tab to "Add condition" again and press it. Choose "On certain days of the week", tick
  Mon to Fri, and press OK.
4. Tab to "Add action" and press it. "Speak text" is already chosen. In "Text to speak",
  type: Good morning, %myname%. It's %time%. Press OK.
5. Press OK to save the routine.

From then on, at 07:00 on weekdays, your screen reader says "Good morning, Rafli. It's
07:00."

## The Routines window

- "Add" makes a new routine.
- "Edit", or Enter on the list, changes the selected routine.
- "Delete" deletes it, after asking.
- "Toggle On/Off" turns it off, or on again. A routine that is off never runs by itself.
- "Run Now" runs its actions at once, whatever its conditions say, even when it is off.
- "Close", or Escape, closes the window.

Each change is saved at once.

## Editing a routine

The "Edit Routine" window has, in Tab order:

- "Name", and "Enabled".
- "When ALL of these are true": the conditions. Each one is a group named after it, such
  as "1. At a specific time (HH:MM) → 07:00", with the buttons "Edit", "Remove", "Move
  Up" and "Move Down". The "Add condition" button comes after them.
- "Then do (in order)": the actions, in the order they run, with the same buttons, and
  "Add action".
- OK saves the routine, and Cancel leaves it as it was.

Adding or editing a condition or an action opens a small window: choose the "Type" first,
then Tab to its settings, and press OK. A routine without a name is saved as "Untitled
routine".

## When a routine runs

- A routine runs when all its conditions are true at the same time.
- It runs once when they become true, and again only after they have stopped being true
  and become true again. "Battery at or below (%)" set to 20 runs once when the battery
  drops to 20%, not every minute after that.
- Three conditions are moments rather than states: "When Hariku starts up", "When a date
  is selected" and "When a reminder fires". A routine with one of them runs every time
  that moment comes, as long as its other conditions are true.
- A routine without conditions never runs by itself; use "Run Now".
- Routines are checked every minute, and whenever something they watch changes, such as
  the window in focus, the clipboard, the power or the network. They run only while
  Hariku is running.
- Quiet hours don't silence routines.

## Conditions

- "At a specific time (HH:MM)": the time, 24-hour, with two digits for the hour: 07:00,
  not 7:00.
- "On certain days of the week": tick the days, Mon to Sun.
- "Battery at or below (%)" and "Battery at or above (%)": a percent. On a computer
  without a battery, these are never true.
- "While charging / not charging": tick "Must be charging" for while charging, or untick
  it for while not charging.
- "After idle for N minutes": how many minutes without using the keyboard or mouse.
- "When an app is in focus": part of the program's file name, such as chrome.exe or
  winword.
- "When the window title contains": part of the title of the window in focus.
- "When the clipboard contains": text on the clipboard. Here capital letters must match.
- "When online / offline": tick "Must be online" for online, or untick it for offline.
- "Run every N minutes": the routine runs every so many minutes, starting at the first
  check after Hariku starts or after you add it.
- "A reminder exists today": today has a reminder. With a word in "Title contains
  (optional)", only a reminder whose title contains it counts.
- "Connected to Wi-Fi network": part of the Wi-Fi network's name.
- "RAM usage at or above (%)" and "CPU usage at or above (%)": a percent.
- "When Hariku starts up".
- "When a date is selected": each time you move to a date in the calendar.
- "When a reminder fires": each time a reminder comes up. With a word in "Reminder title
  contains (optional)", only reminders whose title contains it count.

Apart from the clipboard, capital letters don't matter in the text you look for.

## Actions

- "Speak text": your screen reader says the text.
- "Show a notification": a Windows notification with a "Title" and a "Message".
- "Open a URL": opens a web page in your browser. The address must start with http:// or
  https://.
- "Play a sound": one of Hariku's sounds by its file name, such as move.wav or info.wav.
- "Set a variable": keeps a value under a name, for the actions after it (see Placeholders
  and variables).
- "Wait (seconds)": pauses before the next action, 60 seconds at most.
- "Open an app or command": starts a program, with its arguments if you like, such as
  `notepad`. Put a full path in double quotes: `"C:\Program Files\App\app.exe"`. Windows
  variables such as %USERPROFILE% work. A link such as `spotify:` opens its app. It is not
  a command prompt, so pipes and other shell tricks don't work.
- "Open a file": opens a file with its usual program, such as
  `%USERPROFILE%\Documents\list.txt`.
- "Lock the screen": locks Windows.
- "Set system volume": despite its name, it sets the volume of Hariku's own sounds, 0 to
  100, the same volume F5 and F6 change.
- "Copy text to clipboard".
- "Type text into focused field": types the text, a moment later, into whatever has the
  focus. A new line is typed as Enter.
- "Add a Hariku reminder": a "Reminder title", a "Time (HH:MM)", which is 09:00 when left
  empty, and a "Date (YYYY-MM-DD, blank = today)".
- "Go to a date in the calendar": selects that date in the calendar, today when left
  empty.
- "Speak the agenda for a day": reads the reminders of that date, today when left empty.
- "Run another routine": runs the actions of the routine with that name; capital letters
  don't matter. Routines that run each other stop after 5 steps, so they can't loop
  forever.

Actions run one after the other, in the background.

## Placeholders and variables

In the text of an action you can write placeholders, which are filled in when the routine
runs:

- %time% (the time, HH:MM), %date% (today, YYYY-MM-DD), %battery% (battery percent),
  %app% (the program in focus), %clipboard% (the text on the clipboard), %ssid% (the Wi-Fi
  network's name), %ram% and %cpu% (memory and processor use in percent), and %events%
  (how many reminders today)
- your profile's placeholders, such as %myname% and %mynickname%, your own from
  Preferences, Profile, and Hariku's and your extensions', such as %greeting% or %weather%
- %var:NAME%, the value of a variable a "Set a variable" action saved as NAME

The action window's "Insert placeholder" button lists them all, and puts the one you
choose where the cursor was in the text field you used last. The older form with braces,
such as {time}, still works.

A variable keeps its value until Hariku closes, and your other routines can read it too.

## The Routines log

"View Routines Log" opens "Routines Log", the last 100 runs, newest first. Each line gives
the time, the routine's name, "auto" when it ran by itself or "manual" for Run Now, and
"ok", or the errors when an action failed. "Clear" empties it. The log is kept until
Hariku closes.

It has no key at first; type "view routines log" in Aruna, or give it a key in Input
Gestures.

## Keys and commands

Both of Routines' actions start without a key. In Preferences, Input Gestures, under
Routines, you can give a key to "Manage Routines (Shortcuts)" and "View Routines Log",
and make it global, so it works outside Hariku too.

In Aruna (Ctrl+Alt+Backspace), type "manage routines" to open the Routines window, or
"view routines log" for the log.
