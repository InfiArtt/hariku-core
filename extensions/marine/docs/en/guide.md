# Sea Conditions

Sea Conditions tells you the waves, the swell, the sea temperature and the tide (rising or
falling, and the next high and low tide) for a beach, port or coastal town, and shows the
next days and tides in a window. The data comes from Open-Meteo.com, with no account or
key. It needs Hariku 2.8 or newer.

## Getting started

In Hariku's main window, press O to hear the sea now and Shift+O for the sea forecast.
From anywhere, open Aruna (Ctrl+Alt+Backspace) and type or say "sea conditions" or
"kondisi laut".

Sea Conditions uses your main place from Preferences, Places (Ctrl+P opens Preferences).
Places inland have no sea data, so if your home is inland, choose a beach or port in
Preferences, Sea Conditions (see Choosing the place).

## Hearing the sea now

Press O. You hear the place, the waves (height, sea state, where they come from and their
period), the swell, the sea temperature and the tide. For example: "Kuta: Waves 0.8
metres, slight, from the southwest, period 9 seconds. Swell 0.6 metres. Sea temperature 29
degrees. The tide is rising: high tide at about 21:40, low tide tomorrow at about 03:10."

The word after the height is the sea state, on the WMO scale that BMKG also uses: calm,
smooth, slight, moderate, rough, very rough, high seas, very high seas or phenomenal seas.
Tide times are rounded to 10 minutes, so Hariku says "at about".

If Hariku got the data in the last 10 minutes, you hear it at once. Otherwise it says
"Getting the sea conditions..." and speaks when the answer arrives. Without internet, you
hear the last data from the past 12 hours, with the time it is from. For a place inland
you hear, for example, "No sea data for Home. Choose a beach or port in Preferences, Sea
Conditions."

## The sea forecast

Press Shift+O. The Sea Forecast window has two lists:

- "Next days at", with the place: one line per day, from today, for 7 days. Each has the
  highest waves and their sea state, where they come from, the longest period, the
  highest swell, and that day's high and low tides.
- "Next tides:": each coming high and low tide, with its day, its time and how far above
  or below mean sea level the water is. For example: "High tide today at about 21:40, 0.9
  metres above mean sea level."

Tab moves between the lists, and the arrow keys move through each one. A line below says
when the data was updated. Refresh gets new data, and Close or Escape closes the window.
Data older than 10 minutes is updated by itself when the window opens.

## The high-wave alert

Sea Conditions can tell you once a day when the waves at your place get high. In
Preferences, Sea Conditions:

- "Announce high waves once a day": off by default.
- "Announce when waves reach:": from "1 metre, slight" to "6 metres, high seas"; "2.5
  metres, rough" by default.

When the highest wave expected today (now, or in today's forecast) reaches that height, a
sound plays and you hear, for example, "Sea alert for Kuta: waves up to 2.6 metres today,
rough." Hariku checks each time the data is updated: when Hariku starts and about every
30 minutes. During quiet hours (Preferences, Quiet Hours) it stays silent, and the first
check after quiet hours looks at the waves again.

## Choosing the place

Open Preferences, Sea Conditions. The "Place:" list has "The main place" (the default),
each of your other places, and "Its own place…" for a place just for this extension, such
as a beach. To use a place of its own:

1. Choose "Its own place…" in "Place:".
2. In "Beach, port or coastal town to search for, for its own place (press Enter to
   search):", type at least 2 letters of the name and press Enter.
3. Focus moves to "Search results:". Select the place and press OK.

"Its own place:" shows the place that is saved.

Keep in mind:

- Sea data comes from global ocean models. The numbers describe the sea area near the
  place, roughly 5 to 25 kilometres across, not a single beach.
- Tide times are estimates from the model's sea level. Don't rely on them for navigation
  or safety at sea.

## In the Morning Briefing

With the Morning Briefing extension, the briefing includes the sea: "Sea at Kuta: waves
0.8 metres, slight, next high tide at about 21:40." It uses data from the last 3 hours
only; Sea Conditions updates it in the background when Hariku starts and about every 30
minutes.

## Keys and commands

- O: Speak the sea conditions.
- Shift+O: Open the sea forecast.

The keys work in Hariku's main window. Change them in Preferences, Input Gestures, under
"Sea Conditions". You can make a key global there, so it works outside Hariku too.

In Aruna, typed or spoken:

- The sea now: "sea conditions", "waves", "kondisi laut", "ombak" or "gelombang laut". It
  only speaks, so the answer also shows in Aruna's Last result.
- The forecast window: say its name, "Open the sea forecast" or "Buka prakiraan laut".

## Privacy

Sea Conditions sends nothing until it has a place. Then it asks Open-Meteo's Marine API
(`marine-api.open-meteo.com`) when Hariku starts, about every 30 minutes, and when you
ask. The request holds the place rounded to about 1 kilometre and its time zone, never the
exact point. Searching for a place sends what you typed and your Hariku language to
Open-Meteo's city search (`geocoding-api.open-meteo.com`). The last data is kept on your
computer.
