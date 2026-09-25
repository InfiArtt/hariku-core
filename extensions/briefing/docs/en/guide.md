# Morning Briefing

Morning Briefing speaks a short summary of your day: a greeting, the date, today's
reminders and news from your other extensions. In the evening, a second summary tells you
what you finished today and what is coming tomorrow. It needs Hariku 2.7 or newer.

## Getting started

In Hariku's main window, press B for the morning briefing and Shift+B for the evening
summary. From anywhere, open Aruna (Ctrl+Alt+Backspace) and type or say "briefing" or
"evening summary". Both can also play by themselves: see Playing it automatically below.

## What the morning briefing says

In this order:

1. A greeting for the time of day, such as "Good morning, Budi." It uses the title and
   the name Hariku calls you from Preferences, Profile. On your birthday it adds "Happy
   birthday!".
2. Today's date, in the date format you chose in Preferences.
3. Today's reminders that aren't done yet, in time order, each with its time: "You have 2
   reminders today. 09:00, Stand-up. 14:00, Call Budi." It reads up to 10 and then says
   how many more there are. Repeating reminders count too, and placeholders in their
   titles are filled in.
4. A sentence from each of your other extensions that has news for today.

With no reminders you hear "You have no reminders today.", and when all are done, "All of
today's reminders are done."

## What your other extensions add

Morning Briefing has no list to tick. Each installed extension that takes part adds its
own sentence after your reminders, and only when it has recent data:

- Weather: the weather now, and today's high, low and chance of rain.
- Earthquakes & Tsunami: an earthquake near you in the last 24 hours, according to BMKG.
- Sea Conditions: the waves and the next high tide.
- Air Quality: the air quality index.
- Space: sunset and the moon phase, and today's rocket launches.
- Sleep Pattern: how long you slept last night.
- Timer & Alarm: today's alarms that are still to come.
- Cockpit: your airport's weather, in Captain mode or with "Add airport weather to the
  Morning Briefing (without Captain mode)" ticked.

To leave one out, turn off its own option where it has one (such as Cockpit's), or
disable that extension in the Extension Manager (Ctrl+X). The briefing only reads what
the extensions already have, so it never waits for the internet.

## The evening summary

Press Shift+B, or tell Aruna "evening summary" or "ringkasan malam". In this order:

1. A greeting, and "Happy birthday!" on your birthday.
2. How today went: "You finished 3 of 5 reminders today. Not done yet:", then the ones
   left, in time order. Or "You finished all of today's reminders.", or "You had no
   reminders today."
3. Tomorrow: how many reminders you have, and the first one with its time. For example
   "Tomorrow you have 1 reminder: 08:00, Dentist." Or "You have no reminders tomorrow."
4. What extensions add for tomorrow: Weather says tomorrow's weather ("Tomorrow: light
   rain, 31 degrees."), and Cockpit in Captain mode your airport's forecast.

## Playing it automatically

In Preferences, Morning Briefing:

- "Play the briefing the first time Hariku starts each day": off by default. When it is
  on, the briefing plays a few seconds after Hariku starts, once a day. If Hariku greets
  you when it starts ("Greet me when Hariku starts" in Preferences, Profile), the
  briefing waits for that greeting and leaves out its own.
- "Play the evening summary automatically every evening": off by default.
- "Time of the evening summary:": from 18:00 to 23:00, in steps of half an hour; 20:00 by
  default.

The morning briefing plays when Hariku starts, not at a set hour. If Hariku runs all
night, press B in the morning. The evening summary plays once each evening: if Hariku
isn't running at the time you chose, it plays as soon as Hariku is running, until
midnight.

## Hearing it with Hariku Voice

Your screen reader reads the briefing and the evening summary. To have another voice read
them, tick "Read the Briefing and the evening summary with Hariku Voice" in Preferences,
Hariku Voice. Press S in Hariku's main window to stop Hariku Voice.

## Keys and commands

- B: Play the morning briefing.
- Shift+B: Play the evening summary.

The keys work in Hariku's main window. Change them in Preferences, Input Gestures, under
"Morning Briefing". You can make a key global there, so it works outside Hariku too.

In Aruna, typed or spoken:

- The morning briefing: "briefing", "morning briefing", "briefing pagi" or "ringkasan
  pagi".
- The evening summary: "evening summary", "ringkasan malam" or "rangkuman malam".

Both only speak, so the text also shows in Aruna's Last result.

## Privacy

Morning Briefing makes no connections of its own. It reads your reminders and what your
extensions already have on your computer. If Hariku Voice reads it with an online voice,
such as Edge Voices, the text goes to that voice's service.
