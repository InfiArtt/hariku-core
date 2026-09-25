# Ghost Taskbar Cleaner

Removes ghost icons from the Windows system tray: icons of programs that closed or crashed
but stay in the notification area until the mouse passes over them.

## Cleaning the tray

Press Ctrl+Alt+C, anywhere in Windows. Hariku tells the notification area, and the hidden
icons area too, that the mouse passed over every spot of it, so Windows notices which
icons belong to programs that are gone and removes them. Your real mouse pointer doesn't
move.

When it's done, Hariku says "System tray cleared." If it can't find the tray, it says
"Failed to find Windows System Tray."

## Keys and commands

- Ctrl+Alt+C, anywhere in Windows: Clear Ghost Icons from System Tray.

You can change the key in Preferences, Input Gestures, under "Ghost Taskbar". Aruna runs
it by its name: type "clear ghost icons from system tray".
