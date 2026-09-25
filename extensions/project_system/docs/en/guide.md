# Project System

Break a project into tasks with deadlines, tick them off, and hear how far along the
project is. Hariku also tells you when you move to a date that has project tasks due.

## Getting started

Press Ctrl+Shift+P in Hariku's main window. The "Project Manager" window opens with the
list "Your Projects:". Each project shows its progress in brackets, such as "[50%]
Website", or "[DONE]" once all its tasks are done, followed by its description if it has
one.

The Project Manager and the tasks window have no close button: press Alt+F4 to close them.

## Adding a project

1. Press "New Project".
2. Type the name at "Enter project name:" and press Enter.
3. Type a short description at "Enter short description (optional):", or leave it empty,
   and press Enter.

A project's name and description can't be changed later.

## Adding tasks

Select a project and press "Manage Tasks". A window titled "Tasks for:" followed by the
project's name opens, with its tasks under "Tasks:". A task reads like "[ ] Buy paint
(Due: 2026-10-01)", with "[X]" instead of "[ ]" when it's done.

1. Press "Add Task".
2. Type the task at "Enter task name:" and press Enter.
3. Type the deadline at "Enter deadline (YYYY-MM-DD):", such as 2026-10-01, and press
   Enter. It starts as the date selected in the calendar.

A deadline written another way is refused with "Invalid date format. Please use
YYYY-MM-DD."

## Finishing tasks

Select a task and press "Toggle Done". Hariku says how far along the project is, such as
"Task completed. Project 'Website' is now 50% complete." When the last task is done,
Hariku congratulates you and the project shows "[DONE]". Pressing "Toggle Done" on a
finished task makes it unfinished again.

## Deleting tasks and projects

- "Delete" in the tasks window deletes the selected task at once, without asking.
- "Delete" in the Project Manager asks "Are you sure you want to delete the project ...?"
  first, then deletes the project and all its tasks.

## Deadlines in the calendar

When you move to a date in Hariku's calendar, Hariku counts the unfinished tasks due on
that date and names up to three, such as "Task: Buy paint for project Website." The count
is said as "due today" whichever date you are on.

## Keys and commands

- Ctrl+Shift+P, in Hariku's main window: Open Project Manager.

Window Teleporter uses Ctrl+Shift+P too, for pinning a window to slot 10. If you have
both, give one of them another key in Preferences, Input Gestures; this one is under
"Project System". Aruna runs it by its name: type "open project manager".
