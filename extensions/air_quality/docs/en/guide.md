# Air Quality

Air Quality tells you how clean the air is where you are: the air quality index with its
category, fine and coarse particles (PM2.5 and PM10), the UV index and a short tip. It
also shows the next hours and days, and can warn you once a day when the air turns
unhealthy. It needs Hariku 2.8 or newer.

## Getting started

Air Quality uses your main place from Preferences, Places (Preferences opens with Ctrl+P).
If you have no place yet, add one there, or give Air Quality a city of its own in
Preferences, Air Quality.

Then press U in Hariku's main window to hear the air quality, and Shift+U to open the
forecast. You can also open Aruna, Hariku's command bar, with Ctrl+Alt+Backspace and type
"air quality".

## Hearing the air quality

Press U. Hariku says, in this order:

- the place, the air quality index (0 to 500) and its category: good, moderate, unhealthy
  for sensitive groups, unhealthy, very unhealthy or hazardous
- when the air isn't good, the pollutant that drives the index, such as ozone or fine
  particles
- PM2.5 and PM10, in micrograms per cubic metre
- the UV index and its category: low, moderate, high, very high or extreme
- a short tip for the category, such as who should take it easy outdoors

If the last reading is less than 10 minutes old, you hear it at once. Otherwise Hariku
says "Getting the air quality..." and fetches a new one. If the service can't be reached,
Hariku tells you why and then reads the last reading it has, with the time it was fetched,
as long as it is less than 12 hours old.

Hariku also refreshes the air quality by itself when it starts and about every 30 minutes,
so the answer is usually ready.

## The forecast window

Press Shift+U to open the Air Quality Forecast window. It has two lists:

- The next hours at your place: one row every 3 hours for about a day, with the index,
  PM2.5 and, when it is above zero, the UV index.
- "Next days (highest values)": one row per day from today, up to 5 days, with the highest
  index, PM2.5 and UV index of that day.

Each row is one sentence, so the arrow keys read a whole hour or day at a time. Below the
lists, a line says when the data was updated. Press Refresh to fetch it again, and Close
or Escape to close the window.

## The unhealthy air alert

To be warned when the air gets bad, open Preferences, Air Quality and tick "Announce once
a day when the air becomes unhealthy (index 151 or more)", then press OK.

When the index reaches 151 or more, Hariku plays a sound and says the place, the index,
the category and the tip. It does this at most once a day, and only from data less than an
hour old. During quiet hours (Preferences, Quiet Hours) it stays silent; the next check
after quiet hours looks at the air again.

## In the Morning Briefing

When the last reading is less than 3 hours old, the Morning Briefing includes one sentence
with the place, the index and its category. There is nothing to turn on.

## Settings

Open Preferences, Air Quality:

- "Place": the place to use. "The main place" is the default; you can also pick another of
  your places, or "Its own place…" for a city just for Air Quality.
- With "Its own place…" chosen, type the city in "City to search for, for its own place
  (press Enter to search)" and press Enter or Search. Pick your city in "Search results"
  and press OK. "Its own place" shows the city that is saved.
- "Announce once a day when the air becomes unhealthy (index 151 or more)": the alert
  above. Off by default.

## About the numbers

- The index is the US Air Quality Index (US AQI) of the U.S. EPA. Its categories are like
  those of Indonesia's ISPU, but the numbers are worked out differently, so they may not
  match ISPU readings.
- The data comes from a global model (CAMS) with cells about 40 kilometres across (about
  10 in Europe). The numbers describe the wider area, not your street.
- The tips follow the U.S. EPA's general guidance for each category. They are not medical
  advice.

## Keys and commands

These keys work in Hariku's main window:

- U: Speak the air quality
- Shift+U: Open the air quality forecast

You can change them in Preferences, Input Gestures.

In Aruna (Ctrl+Alt+Backspace), "air quality", "pollution", "kualitas udara" or "polusi
udara" speaks the air quality. For the forecast, type its name: "open the air quality
forecast".

## Privacy

Air quality data comes from Open-Meteo (`air-quality-api.open-meteo.com`), with no account
or key. Nothing is sent until you have a place. After that, Hariku asks when it starts,
about every 30 minutes, and when you ask. Each request contains your place rounded to
about 1 kilometre, and its time zone, never the exact point.

Searching for a city sends the text you typed, and your Hariku language, to Open-Meteo's
city search (`geocoding-api.open-meteo.com`).
