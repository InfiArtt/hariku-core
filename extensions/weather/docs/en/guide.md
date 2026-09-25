# Weather

Weather tells you the weather now and shows a 7-day forecast for one place. The data comes
from Open-Meteo.com, with no account or key. It needs Hariku 2.8 or newer.

## Getting started

Weather uses your main place from Preferences, Places (Ctrl+P opens Preferences). If you
have no place yet, add one there, or choose a city just for Weather in Preferences,
Weather.

Then, in Hariku's main window:

- Shift+W speaks the weather now.
- "Open the weather forecast" opens the forecast window. It has no key at first: run it
  from Aruna (Ctrl+Alt+Backspace), or give it a key in Input Gestures.

## Hearing the weather now

Press Shift+W, or tell Aruna "weather" or "cuaca". You hear the place, the sky, the
temperature and how it feels, the humidity and the wind, then today's high, low and chance
of rain. For example: "Home: Light rain, 27 degrees, feels like 30. Humidity 80 percent,
wind 12 kilometres per hour. Today: high 31, low 24, 70 percent chance of rain."

If Hariku got the weather in the last 10 minutes, you hear it at once. Otherwise it says
"Getting the weather..." and speaks when the answer arrives. Without internet, you hear
the last weather from the past 12 hours, with the time it is from.

## The 7-day forecast

Run "Open the weather forecast", or tell Aruna "weather forecast" or "prakiraan cuaca".
The Weather Forecast window lists one day per line, from today: the date, the sky, the
high and low, and the chance of rain. Move from day to day with the arrow keys. The label
of the list says which temperature unit it uses.

Below the list, a line says when the forecast was updated. Refresh gets a new forecast,
and Close or Escape closes the window. A forecast older than 10 minutes is updated by
itself when the window opens.

## Choosing the place

Open Preferences, Weather. The "Place:" list has:

- "The main place", with its name: your main place from Preferences, Places. This is the
  default.
- Each of your other places, by name.
- "Its own place…": a city just for Weather.

To use a city of its own:

1. Choose "Its own place…" in "Place:".
2. In "City to search for, for its own place (press Enter to search):", type at least 2
   letters of the city and press Enter.
3. Focus moves to "Search results:". Select your city and press OK.

"Its own place:" shows the city that is saved. The search only works while "Its own
place…" is chosen. If you remove a place that Weather uses, it uses the main place again.

## Settings

In Preferences, Weather:

- "Place:": which place to use (see above).
- "Units:": "Celsius, kilometres per hour" (the default) or "Fahrenheit, miles per hour".

## The weather in your briefing and texts

Weather updates the forecast in the background when Hariku starts and about every 30
minutes, so these are ready without waiting:

- The Morning Briefing (B) says the weather now and today's high, low and chance of rain:
  "Weather in Home: Light rain, 27 degrees, high 31, low 24, 70 percent chance of rain."
- The evening summary (Shift+B) says tomorrow's weather: "Tomorrow: light rain, 31
  degrees."
- %weather% in a reminder, a routine or your startup greeting becomes the weather now,
  such as "light rain, 25 degrees".

They use a forecast from the last 3 hours only. Without one, the briefing leaves the
weather out and %weather% stays empty.

## Keys and commands

- Shift+W: Speak the current weather.
- No key: Open the weather forecast.

The keys work in Hariku's main window. Change them, or give the forecast a key, in
Preferences, Input Gestures, under "Weather". You can make a key global there, so it works
outside Hariku too.

In Aruna, typed or spoken:

- The weather now: "weather", "current weather", "weather today", "temperature", "cuaca",
  "cuaca hari ini", "cuaca sekarang", "suhu" or "berapa suhu". It only speaks, so the
  answer also shows in Aruna's Last result.
- The forecast window: "weather forecast", "forecast", "weather tomorrow", "prakiraan
  cuaca", "ramalan cuaca" or "cuaca besok".

## Privacy

Weather sends nothing until it has a place. Then it asks Open-Meteo (`api.open-meteo.com`)
for the forecast when Hariku starts, about every 30 minutes, and when you ask. The request
holds the place rounded to about 1 kilometre and its time zone, never the exact point.
Searching for a city sends what you typed and your Hariku language to Open-Meteo's city
search (`geocoding-api.open-meteo.com`). The last forecast is kept on your computer.
