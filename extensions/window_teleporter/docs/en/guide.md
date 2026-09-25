# Window Teleporter

Pin up to ten windows to slots and jump straight back to any of them with one key, faster
than looking for it with Alt+Tab. It also switches between Windows virtual desktops. All
its keys work anywhere in Windows.

## Slots and their letters

Each slot has a letter from the top row of the keyboard: Q is slot 1, W slot 2, E slot 3,
R slot 4, T slot 5, Y slot 6, U slot 7, I slot 8, O slot 9 and P slot 10. The same letters
pick virtual desktops 1 to 10.

Slots are kept only while Hariku runs; they are empty again after Hariku restarts.

## Pinning a window

Go to the window you want and press Ctrl+Shift with the slot's letter, such as
Ctrl+Shift+Q for slot 1. Hariku says the window's title and the slot, such as "Pinned
Notepad to slot 1." Pinning another window to the same slot replaces the old one.

## Jumping to a pinned window

Press Ctrl+Alt with the slot's letter, such as Ctrl+Alt+Q for slot 1. The window comes to
the front, restored if it was minimized, and Hariku says "Teleporting to" and its title.

If the window has been closed, Hariku says "Slot 1 is empty or the window was closed." and
empties the slot.

## Checking a slot

Press Ctrl+Alt+Shift with the slot's letter to hear what is in it, such as "Slot 1
contains:" and the title. It's the title the window had when you pinned it.

## Virtual desktops

Press Alt+Shift with a letter to switch to that virtual desktop: Alt+Shift+Q for desktop
1, Alt+Shift+W for desktop 2, and so on. Hariku says "Switched to Desktop 2."

To go to any desktop by its number, press Alt+Shift+D, type the number at "Enter target
Virtual Desktop number:" and press Enter. If that desktop doesn't exist, Hariku says it
failed to jump to it.

## Keys and commands

- Ctrl+Shift+Q to Ctrl+Shift+P: Pin Window to Slot 1 to 10.
- Ctrl+Alt+Q to Ctrl+Alt+P: Teleport to Slot 1 to 10.
- Ctrl+Alt+Shift+Q to Ctrl+Alt+Shift+P: Check Window in Slot 1 to 10.
- Alt+Shift+Q to Alt+Shift+P: Jump to Virtual Desktop 1 to 10.
- Alt+Shift+D: Jump to Any Desktop.

The actions are under "window_teleporter" in Preferences, Input Gestures, where you can
change any key. If another program already holds one of these keys, Hariku can't take it;
give that action another key. Project System uses Ctrl+Shift+P too, for opening its
Project Manager; if you have both, move one of them.

Aruna runs these actions by their names, such as "teleport to slot 1" or "jump to virtual
desktop 2".
