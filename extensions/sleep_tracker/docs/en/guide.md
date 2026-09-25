# Sleep Pattern

Sleep Pattern estimates when you slept from when you used the computer, like a phone's
sleep tracker: a long break from the keyboard and mouse at night is probably sleep. Hear
last night's sleep, look back at your nights and averages, and find out when you stayed
up late. It is an estimate from computer use, not a medical measurement. It needs Hariku
2.7 or newer.

## Getting started

Tracking starts as soon as the extension is installed. Leave Hariku running when you go to
bed. The computer may sleep or shut down for the night: when Hariku runs again, it counts
that time as a break from the computer. Only time when the computer was on but Hariku was
closed stays unknown.

The next morning, press Z in Hariku's main window to hear how you slept.

## Hearing last night's sleep

Press Z, or type "how did I sleep" in Aruna (Ctrl+Alt+Backspace). Hariku says something
like "You probably slept from 23:40 to 06:05, about 6 hours 25 minutes. 20 minutes less
than your 7-day average." The length is rounded to 5 minutes.

It also tells you when you went to sleep after your bedtime ("You stayed up until
01:30."), and about naps of an hour and a half or more between 09:00 and 18:00. After a
night without sleep, it says "You stayed up all night, then probably slept from ..." When
Hariku can't tell, it says why, for example that it wasn't running for much of the night.

## Sleep history

Press Shift+Z to open "Sleep history".

- "Summary" gives your average sleep and usual bedtime and waking time over the last 7
  nights, how many of those nights you stayed up late, and your average over the last 30
  nights.
- "Nights, newest first" lists each night by its morning's date, with what Hariku found:
  "Friday 25 September: You probably slept from 23:40 to 06:05, about 6 hours 25 minutes."
- "Details", or Enter on a night, shows everything about it, one fact per line: how often
  and how long you used the computer during the sleep, time without data, whether you
  stayed up late, naps, how it compares with your average, and how much of the night
  Hariku has data for. Enter or Escape closes it.

Hariku keeps 90 days of history.

## When it wasn't sleep

If you listened to something for hours without touching the computer, Hariku may take it
for sleep. Select that night in the sleep history and press "This wasn't sleep". It no
longer counts in your averages. The button then reads "Undo "wasn't sleep"", to take it
back.

## Staying up late

Your bedtime (00:00 at first) decides when going to sleep counts as staying up late. Set
it in the settings. To be reminded, turn on "Remind me to rest if I'm still using the
computer 30 minutes after bedtime": once a night, between 30 minutes after your bedtime
and 06:00, if you are still using the keyboard or mouse, Hariku says "It's 00:45. Don't
forget to rest.", with the name Hariku calls you, and plays a sound unless you turn the
sound off.

## In the Morning Briefing and in placeholders

When you woke up less than 12 hours ago, the Morning Briefing adds your sleep: "Last
night you slept about 6 hours 25 minutes, from 23:40 to 06:05."

The placeholder %sleep% gives the same length, such as "about 6 hours 25 minutes", in a
reminder, a routine or your startup greeting on the Profile page. It stays empty when
Hariku doesn't know how you slept.

## Settings

Open Preferences (Ctrl+P) and go to the Sleep Pattern page.

- "Track my sleep from when I use the computer": on at first. Time with tracking off
  stays unknown.
- "Bedtime (going to sleep later counts as staying up late)": 22:00 to 02:00, in half
  hours; 00:00 at first.
- "Shortest sleep to count": 2, 3 or 4 hours; 3 hours at first.
- "Ignore short computer use during sleep": "Don't ignore any", or up to 5, 10 or 15
  minutes; 10 minutes at first. Checking the time at 3 a.m. then doesn't split your
  sleep in two.
- "Remind me to rest if I'm still using the computer 30 minutes after bedtime": off at
  first.
- "Play a sound with the reminder": on at first.
- "About sleep tracking": what is recorded, and that it's an estimate.
- "Clear sleep history": deletes everything recorded and your corrections, after asking.
  This can't be undone. The sleep history window has the same button, "Clear all
  history".

Press OK to save.

## What is recorded

Once a minute, Hariku asks Windows whether the keyboard or mouse was used, and saves only
that: used, not used, or unknown, for each minute. It never records what you typed, which
keys you pressed, or which apps you used. The record stays on your computer for 90 days,
and nothing leaves it.

## Keys and commands

- Z: speak last night's sleep.
- Shift+Z: open the sleep history.
- In the sleep history: Enter shows the details of the selected night, and Escape closes
  the window.

Z and Shift+Z work in Hariku's main window. You can change them in Preferences, Input
Gestures, under Sleep Pattern, and make them global there, so they work outside Hariku
too.

In Aruna (Ctrl+Alt+Backspace), "how did I sleep", "last night's sleep", "tidur semalam"
or "tidurku semalam" speaks last night's sleep, and the answer also shows in Aruna's "Last
result". "Open the sleep history" opens the history.
