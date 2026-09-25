# Clipboard History

Clipboard History keeps a list of the text you copy, so you can find it, pin it and copy
it again later. It needs Hariku 2.4 or newer.

## Getting started

Copy text anywhere in Windows as usual, with Ctrl+C. While Hariku is running, each copy is
added to the history. In Hariku's main window, press V to open the history, or Shift+V to
hear the last text you copied.

## Copying something again

1. Press V. The "Clipboard history" window opens on the list of items, newest first.
2. Arrow through the list. Each row gives the start of the text and when you copied it,
  such as "Meeting at 10 / Room 4, 2 minutes ago". The "Full text" box below the list
  shows the whole of the selected item.
3. Press Enter, or "Copy". The window closes and Hariku says "Copied. Press Control+V to
  paste."
4. Paste it where you need it with Ctrl+V.

Hariku never pastes into other programs by itself.

## Searching the history

The "Filter" box is just before the list: press Shift+Tab from the list to reach it. Type
one or more words, and only the items that contain all of them stay in the list. When you
stop typing, Hariku says how many items match. Capital letters don't matter. Press Enter
to go back to the list.

## Pinning items

Pin the texts you use often, such as your address. Select an item and press "Pin". A
pinned item moves to the top of the list, starts with "Pinned:", is never pushed out by
new copies, and is still there after Hariku restarts. Press the same button, now called
"Unpin", to unpin it.

## Deleting items

- Select an item and press Delete, or the "Delete" button. A pinned item asks first.
- "Clear all" deletes every item that isn't pinned, after asking. Pinned items stay.

## Hearing the last copied text

Press Shift+V. Hariku reads the text you copied last. A very long text stops after about
4,000 characters; open the history to read all of it.

## What is recorded

Clipboard History records copied text. It leaves out:

- text copied from password managers such as KeePass, 1Password and Bitwarden, which mark
  their copies as private
- a copy of the same text as the last one; copying an older text again moves it back to
  the top
- empty text, and text over 100 KB
- anything copied while recording is paused, or while Hariku isn't running
- the text you copy back from the history itself

The history stays in memory and is gone when Hariku closes, unless you turn on "Remember
history after restarting Hariku". Pinned items are always saved on your computer. Nothing
is sent over the internet.

## Settings

Open Preferences (Ctrl+P) and go to the Clipboard History page.

- "History size": 25, 50 or 100 items; 50 at first. When the list is full, the oldest
  item that isn't pinned goes. Pinned items don't count.
- "Remember history after restarting Hariku": off at first. When it's on, the history is
  saved on your computer. Turning it off deletes the saved history at once, except the
  pinned items.
- "Pause recording": nothing new is recorded until you untick it. The history window's
  title then ends with "(recording paused)".
- "Privacy": a short note on what is kept and where.

Press OK to save.

## Keys and commands

- V: open the clipboard history.
- Shift+V: speak the last copied text.
- In the history: Enter copies the selected item, Delete deletes it, and Escape closes
  the window.

V and Shift+V work in Hariku's main window. You can change them in Preferences, Input
Gestures, under Clipboard History, and make them global there, so they work outside
Hariku too.

In Aruna (Ctrl+Alt+Backspace), "clipboard history", "clipboard" or "riwayat clipboard"
opens the history. "Last copied text" or "teks terakhir disalin" reads the last copy, and
the text also shows in Aruna's "Last result".
