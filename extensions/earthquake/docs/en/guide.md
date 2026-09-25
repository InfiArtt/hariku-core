# Earthquakes & Tsunami

Earthquakes & Tsunami tells you BMKG's latest earthquake, lists recent earthquakes in
Indonesia (and, if you like, strong ones worldwide from USGS), and speaks alerts: for
earthquakes BMKG says have tsunami potential, and, if you turn them on, for earthquakes
near you or felt in your region. It needs Hariku 2.8 or newer.

**Hariku is not an official warning system. Always follow BMKG and your local
authorities.**

## Getting started

In Hariku's main window, press G to hear the latest earthquake and Shift+G for the list of
recent ones. From anywhere, open Aruna (Ctrl+Alt+Backspace) and type or say "latest
earthquake" or "gempa terbaru".

The tsunami alert is on from the start. Distances and nearby alerts use your main place
from Preferences, Places (Ctrl+P opens Preferences). The other alerts and the place are in
Preferences, Earthquakes & Tsunami.

## Hearing the latest earthquake

Press G. You hear BMKG's latest earthquake:

- its magnitude, its depth and BMKG's description of where it was;
- how far it is from your place and in which direction, such as "120 kilometres south of
  Home";
- the time, in BMKG's time zone (such as WIB), and how long ago;
- where it was felt, on the MMI scale, when BMKG reports it;
- BMKG's statement about tsunami potential.

BMKG's own words (the location, where it was felt, the tsunami statement) stay in
Indonesian, as BMKG wrote them. When BMKG says there is tsunami potential, the report
starts with "Tsunami potential, according to BMKG.", with a sound if alert sounds are on.

If Hariku checked BMKG in the last 30 seconds, you hear it at once. Otherwise it says
"Checking BMKG..." first. Without internet, you hear the last data from the past 6 hours,
with the time it is from. An earthquake you've heard with G isn't announced again as an
alert, unless BMKG later adds tsunami potential to it.

## Recent earthquakes

Press Shift+G. The Recent Earthquakes window lists one earthquake per line, newest first:
magnitude, where, depth, time and distance from your place. A line starts with "Tsunami
potential, according to BMKG." when BMKG says so, and ends with where it was felt when
BMKG reports it. The list has BMKG's recent strong earthquakes (magnitude 5 and above),
BMKG's felt earthquakes, and the ones Hariku's alert checks saw in the last two days.

- Move through the list with the arrow keys. The Details box below it shows everything
  about the selected earthquake: magnitude, time, location, coordinates, depth, distance,
  where it was felt, BMKG's statement and the source.
- Enter on the list, or the Details button, speaks the details.
- "Include strong earthquakes worldwide from USGS (magnitude 5 and above, last 24 hours)"
  adds USGS earthquakes that BMKG didn't report. Their lines end with "Source: USGS."
  Hariku remembers this choice.
- Refresh gets the lists again. Close or Escape closes the window.

The window gets fresh lists when it opens, unless they are less than 2 minutes old.

## Alerts

While Hariku is running, it checks BMKG's latest earthquake about every minute (when any
BMKG alert is on) and USGS about every 5 minutes (when worldwide alerts are on). Each
earthquake is announced once. Earthquakes more than an hour old aren't announced (three
hours for tsunami potential), so starting Hariku doesn't replay old news.

Choose the alerts in Preferences, Earthquakes & Tsunami:

- "Announce earthquakes BMKG says have tsunami potential, wherever they are
  (recommended)": on by default. This alert interrupts your screen reader, and it still
  comes when BMKG adds tsunami potential to an earthquake you already heard about.
- "Announce earthquakes near me": off by default. It uses "Alert distance:" (100, 300, 500
  or 1,000 kilometres; 300 by default) and "Minimum magnitude for earthquakes near me:"
  (3.0 to 6.0; 4.0 by default).
- "Announce earthquakes BMKG reports as felt in my region": off by default. See Felt
  alerts below.
- "Announce strong earthquakes anywhere in the world (USGS, magnitude 6.5 and above)": off
  by default. When USGS has set its tsunami flag, Hariku says so, and that the flag alone
  doesn't mean a tsunami happened.
- "Play a sound with alerts": on by default. Tsunami potential has a sound of its own.

Each time Hariku runs, the first alert ends with "Hariku is not an official warning
system. Always follow BMKG and your local authorities." (If you first hear tsunami
potential with G, that report carries it instead.) An earthquake announced from BMKG
isn't announced again from USGS, and the other way round.

### Felt alerts

BMKG's felt reports name the towns and regencies where people felt the earthquake. Hariku
looks there for your place's city or town (never the name you gave the place, such as
Home). For a city of its own, it also looks for the city's regency when the search found
one. To add names, such as your regency, type them in "Other region names to look for in
felt reports, such as your regency (comma separated, optional):". The line below that
field tells you which names Hariku looks for.

### Quiet hours

During quiet hours (Preferences, Quiet Hours), only tsunami alerts are spoken. Other
earthquake alerts are skipped and aren't repeated later.

## Choosing the place

Open Preferences, Earthquakes & Tsunami. The "Place:" list has "The main place" (the
default), each of your other places, and "Its own place…" for a city just for this
extension. To use a city of its own:

1. Choose "Its own place…" in "Place:".
2. In "City to search for, for its own place (press Enter to search):", type at least 2
   letters of the city and press Enter.
3. Focus moves to "City search results:". Select your city and press OK.

"Its own place, for distances and nearby alerts:" shows the city that is saved.

## In the Morning Briefing

With the Morning Briefing extension, the briefing mentions an earthquake that BMKG
reported within your alert distance in the last 24 hours: "Earthquake near you in the
last 24 hours, according to BMKG: ...", with its magnitude, distance and time, and
whether BMKG reported tsunami potential. It uses the "Alert distance:" setting even when
nearby alerts are off, and only data Hariku already has.

## Keys and commands

- G: Speak the latest earthquake from BMKG.
- Shift+G: Open the list of recent earthquakes.

The keys work in Hariku's main window. Change them in Preferences, Input Gestures, under
"Earthquakes". You can make a key global there, so it works outside Hariku too.

In Aruna, typed or spoken:

- The latest earthquake: "latest earthquake", "earthquake", "last earthquake", "gempa",
  "gempa terbaru", "gempa terkini", "info gempa" or "gempa bumi terbaru". It only speaks,
  so the answer also shows in Aruna's Last result.
- The list: "recent earthquakes", "list of earthquakes", "daftar gempa" or "daftar gempa
  terbaru".

## Privacy

Earthquakes & Tsunami downloads BMKG's public earthquake files from `data.bmkg.go.id`:
about once a minute while a BMKG alert is on (the tsunami alert is on by default), and
when you ask. With worldwide alerts or the worldwide list, it also downloads the public
USGS feeds from `earthquake.usgs.gov`. These requests hold none of your data: everyone
gets the same files, and distances are worked out on your computer, so your place never
leaves it. Searching for a city sends what you typed and your Hariku language to
Open-Meteo's city search (`geocoding-api.open-meteo.com`). Earthquake data: BMKG (Badan
Meteorologi, Klimatologi, dan Geofisika) and USGS.
