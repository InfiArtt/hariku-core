# Sound Themes

Sound Themes changes the sounds Hariku plays, like a colour theme for your ears. Make
themes from your own WAV files, switch between them, and import or export them as ZIP
files. Sound themes from Hariku 1 can be imported too.

## Getting started

Open Preferences, Sound Themes. The page has two lists, each with its buttons:

- "Themes": first "Default, Hariku's own sounds", then your themes. Each row says
  whether the theme is in use and how many sounds of its own it has.
- "Sounds in", followed by the selected theme's name: every Hariku sound with what it is
  for, such as "confirm, confirmation". For your own themes the row also says "this
  theme's sound" or "default sound".

The buttons act at once, so there is nothing to save with OK.

## Using a theme

Select a theme in "Themes" and press "Use this theme" (or Enter). Hariku says, for
example, "Theme Ocean applied." The theme stays in use, also after a restart: Hariku
even starts with the theme's start sound. To go back to Hariku's own sounds, use
Default.

To switch quickly, press Shift+S in Hariku's main window, or ask Aruna for "next sound
theme". Hariku moves to the next theme (after the last one comes Default again), says
its name and plays its start sound.

## Making your own theme

1. Press "New theme...", type a name in "Theme name" and press OK. A new theme has no
   sounds of its own yet, so it sounds just like Default.
2. In the "Sounds in" list, select a sound and press Play (or Enter) to hear it.
3. Press "Replace with a WAV file..." and choose your sound. The theme now plays your
   file for that sound.
4. Do the same for every sound you want to change, then use the theme.

"Reset to default" (or Delete in the sounds list) removes the theme's own copy of the
selected sound, so it plays Hariku's sound again.

A sound must be an uncompressed PCM WAV file of at most 5 MB. A theme name can be up to
60 characters long, can't contain `< > : " / \ | ? *`, can't start or end with a dot,
and can't be Default.

Default is Hariku's own sounds and can't be changed. To build on a theme, including
Default, select it and press "Duplicate...": the copy starts with the same sounds.

The list also holds Aruna's two sounds, aruna_send and aruna_reply, and listen and
listen_end, the tones Voice Control plays when it starts and stops listening.

## Theme folders

Each theme is a folder in `%APPDATA%\Hariku2\sound_themes`, holding WAV files named like
Hariku's sounds, such as `confirm.wav`. A sound the folder doesn't have plays Hariku's
own. "Open theme folder" opens the selected theme's folder, so you can also copy
sounds into it yourself.

## Renaming and deleting a theme

"Rename..." gives the selected theme a new name; a theme in use stays in use. "Delete"
(or Delete in the themes list) removes a theme and all its sounds, after asking you.
The theme in use can't be deleted: use another theme first.

## Importing and exporting

Press "Import..." and choose a ZIP file of WAV sounds, or a Hariku 1 sound theme
(`.hrk`). Hariku makes a new theme named after the file and tells you how many sounds it
imported. Only WAV files named like Hariku's sounds are used, from any folder inside the
ZIP; Hariku tells you how many others it left out. A file can hold at most 20 MB of
sounds. From a Hariku 1 theme, sounds that are the same as Hariku's own are left out, so
they stay "default sound".

Press "Export..." to save the selected theme's own sounds as a ZIP file, to share the
theme or keep a copy. Exporting Default saves all of Hariku's own sounds, a handy start
for a theme of your own.

## Keys and commands

- Shift+S, in Hariku's main window: "Switch to the next sound theme". Change the key in
  Preferences, Input Gestures.
- Aruna understands "next sound theme", "ganti tema suara" and "tema suara berikutnya".
- In the "Themes" list: Enter uses the theme, Delete deletes it.
- In the "Sounds in" list: Enter plays the sound, Delete resets it to default.
