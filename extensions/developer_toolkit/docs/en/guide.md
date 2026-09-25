# Developer Toolkit

Tools for people who write Hariku extensions: a Python console that runs inside Hariku, a
record of the events Hariku sends, Hariku's log, a list of loaded extensions you can
reload, and a packer that turns an extension folder into a `.hrk` file. Its window is in
English.

## Getting started

Press Ctrl+Alt+D anywhere in Windows, or choose "Developer Toolkit" in the menu of
Hariku's tray icon. The window has five tabs: "REPL Console", "Event Sniffer", "Log
Viewer", "Extension Inspector" and "HRK Packer". Press Ctrl+Tab to move between them. The
"Close" button closes the window.

## Running Python code

The "REPL Console" tab runs Python code inside Hariku.

1. Type your code in "Python Code (multi-line supported):". Tab types a tab in this box;
   to leave it, press Ctrl+M to go to the output, then Tab.
2. Press F5, or the "Execute (F5)" button.
3. The result appears in "Output:" and the first 200 characters are spoken. Printed text,
   errors, and the value of an expression (after ">>>") all go there.

Ctrl+M moves between the code box and the output. "Clear Output" and "Clear Input" empty
them. These names are ready to use: `wx`, `core`, `api` (Hariku's `core.api`), `bus` (the
event bus), `speak` and `help`. What you define stays until you close the Toolkit.

Your code has full access to Hariku, so a mistake can change your data or stop Hariku.

## Watching events

The "Event Sniffer" tab records every event Hariku's parts send each other, with the time
and the first part of each argument. It starts when Hariku loads the extension and keeps
the last 500 events.

- "Refresh (F5)" shows the list and says how many events there are and the latest one.
- "Clear Events" empties the list.
- "Stop Sniffer" stops recording; the same button then reads "Start Sniffer".

## Reading the log

The "Log Viewer" tab shows Hariku's debug log, `hariku_debug.log` in the `hariku2` folder
of your Windows temp folder. The path is shown after "Log File:".

- "Refresh (F5)" loads it again and says how many lines it read.
- "Show last 200 lines only" is on at first; untick it to see the whole log.
- "Auto-refresh (3s)" reloads the log every 3 seconds, without speaking.
- "Copy All" copies what is shown to the clipboard.
- "Open Log Folder" opens the folder in File Explorer.

## Reloading an extension

The "Extension Inspector" tab lists the extensions Hariku has loaded, under "Loaded
Extensions in Memory:", with their ID, name, version, mode (Unpacked or Zipped) and
module. Select one, then:

- "Inspect Module" shows its details (author, file, whether it is official) and the public
  names it has, in the box below the buttons.
- "Force Reload Selected" calls the extension's `teardown()` and loads it again from its
  folder, so a change you made takes effect without restarting Hariku.
- "Refresh List" reads the list again.

A reload doesn't undo what the old copy registered. Event handlers it subscribed stay
subscribed unless its `teardown()` removes them, so restart Hariku before you trust a
test.

## Packing an extension

The "HRK Packer" tab packs an extension folder into a `.hrk` file, the packed form Hariku
loads extensions from.

1. Press "Browse..." and choose the extension's folder. The folder picker starts in
   Hariku's extensions folder.
2. Press "Validate & Pack into .hrk".

The packer checks that `manifest.json` exists and has name, version, author, description,
main, language and minimum_core_version, and that the main file exists. It then deletes
the `__pycache__` folders inside your folder and packs the rest into `<folder name>.hrk`
next to the folder. Files and folders whose names start with a dot are left out, and an
older `.hrk` with the same name is replaced. "Packer Output:" shows each step and where
the file went.

## Keys and commands

- Ctrl+Alt+D, anywhere in Windows: open Developer Toolkit.
- Ctrl+Tab: next tab.
- F5, in the code box or the output of the REPL Console: run the code.
- F5, in the text of the Event Sniffer or the Log Viewer: refresh.
- Ctrl+M, in the REPL Console: move between the code box and the output.

The key to open the Toolkit is under "Developer Toolkit" in Preferences, Input Gestures,
where you can change it. Aruna runs it by its name: type "open developer toolkit".
