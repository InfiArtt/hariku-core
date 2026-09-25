# Markdown Reader

Open Markdown files (`.md`) and read them with your screen reader: a list of the headings
to jump through, the text without the Markdown marks, and a web view for NVDA's browse
mode.

## Getting started

To open a file, use the action "Open a Markdown file in the reader", or choose "Open
Markdown File" in the menu of Hariku's tray icon. Pick the file in the "Open Markdown
File" dialog; it shows `.md`, `.markdown` and `.txt` files, or all files.

The action's default key is Ctrl+M in Hariku's main window, but Hariku's own "Minimize to
System Tray" uses Ctrl+M too and normally takes it. Give the action a key of its own in
Preferences, Input Gestures, under "Markdown Reader", or use the tray menu or Aruna.

When the file is open, Hariku says its name and how many lines and headings it has, such
as "Loaded: notes.md — 120 lines, 8 headings".

## The reader window

The window is called "Markdown Reader —" and the file's name. It has:

- "Headings", followed by the count: the list of headings, with deeper levels indented.
- "Content": the text of the file, read-only, to read line by line.
- A status line with the file's name and its number of lines and headings.
- The buttons "Open File...", "Read in Web View", "Copy All" and "Close".

In "Content", the Markdown marks are gone. Links show their text followed by the address
in brackets, pictures show their description, list items start with a bullet, a table
shows each row on a line with "|" between the cells, and code sits between "[Code]" and
"[/Code]". Each heading is followed by a line of dashes.

## Moving by headings

Press Alt+Down for the next heading and Alt+Up for the previous one, from anywhere in the
window. The cursor in "Content" moves to that heading and Hariku says it, so you can read
on from there. If the file has no headings, Hariku says "No headings found".

Moving through the headings list with the arrow keys does the same. Double-clicking a
heading in the list reads its whole section aloud.

## Reading in the web view

Press Ctrl+B, or the "Read in Web View" button, to open the file as a web page in a
separate window, with real headings, lists, tables and links. Hariku says "Opened in Web
View. Use NVDA Browse Mode." There, H moves between headings, 1 to 6 go to a heading
level, T to a table and K to a link. Escape closes the web view.

## Copying the text

Press Ctrl+Shift+C, or the "Copy All" button, to copy the whole text, without the Markdown
marks, to the clipboard.

## Opening another file

Press Ctrl+O, or the "Open File..." button, to open another file in the same window.

## Recent files

The action "Open a recently read Markdown file", Ctrl+Shift+M in Hariku's main window,
shows "Recent Files": the last 10 files you opened, each with its name and folder. Files
that are no longer there are left out. Choose one and press Enter to open it. The last
item, "Clear Recent Files", empties the list.

Files you open with Ctrl+O inside the reader aren't added to this list.

## Keys and commands

In Hariku's main window:

- Ctrl+M: Open a Markdown file in the reader (see Getting started).
- Ctrl+Shift+M: Open a recently read Markdown file.

In the reader window:

- Alt+Down and Alt+Up: next and previous heading.
- Ctrl+B: read in the web view.
- Ctrl+Shift+C: copy all the text.
- Ctrl+O: open another file.
- Escape: close the reader.

You can change the two main keys in Preferences, Input Gestures, under "Markdown Reader".
Aruna runs both actions by their names, such as "open a markdown file in the reader".
