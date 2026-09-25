# Filter

Filter makes the calendar skip the dates you don't need. Move only between dates that
have reminders, only between empty dates, or only between dates with a reminder whose
title contains a word, such as dentist.

## Getting started

In Hariku's main window, press Shift+F. The "Filter Dates" window opens. Filter's windows
and messages are in English only.

## Setting a filter

1. Press Shift+F.
2. Under "Filter by Reminder Status", choose "All Dates", "Only Dates with Reminders" or
  "Only Empty Dates" with the arrow keys.
3. To look for a word, press Tab to reach the field in "Filter by Keyword" (its label is
  "Only show dates with reminders containing") and type the word. Capital letters don't
  matter.
4. Press Enter, or "Apply".

Hariku says "Filters applied." and what the filter is, such as "Dates with reminders
only" or "Keyword: "dentist"". If the date you are on doesn't match, Hariku moves to the
nearest date that does, up to about a month away.

## Moving around with a filter on

Move through the calendar as usual. When you land on a date that doesn't match, Hariku
jumps ahead to the next date that does, looking up to a year ahead, and then back. If no
date matches, it says "No further dates match the current filter."

Because it always looks ahead first, Left Arrow takes you back to the date you were on
when the day before it doesn't match. To look further back, use Up Arrow (a month back)
or Page Up (a year back).

## Turning the filter off

Press Shift+F, then "Reset". Hariku says "Filters reset." at once; press Close or Escape
to leave the window. Choosing "All Dates", clearing the word and pressing Apply does the
same.

The filter isn't saved: it also ends when Hariku closes.

## Hearing the current filter

The action "Announce current filter status" says which filter is on, such as "Dates with
reminders only", or "No filter active". It has no key at first; give it one in Input
Gestures, or type "announce current filter status" in Aruna (Ctrl+Alt+Backspace).

## Keys and commands

- Shift+F: open the Filter Dates window.
- Announce current filter status: no key at first.

Shift+F works in Hariku's main window. You can change keys in Preferences, Input
Gestures, under Filter.

In Aruna (Ctrl+Alt+Backspace), "open filter dialog" opens the window, and "announce
current filter status" says which filter is on.
