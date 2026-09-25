# Cockpit

Cockpit brings pilot vibes to Hariku. It reads the aviation weather of your airports: the
latest report (METAR), decoded into plain sentences, and the forecast (TAF). Captain mode
puts the airport weather in your Morning Briefing and evening summary, and can have Hariku
call you Captain. There is also a Cockpit sound theme. It needs Hariku 2.8 or newer.

The data comes from the NOAA Aviation Weather Center. It is for information only, not for
flight planning.

## Getting started

1. Open Preferences, Cockpit (Preferences opens with Ctrl+P).
2. In "ICAO code of an airport to add (press Enter to add)", type the airport's 4-letter
  ICAO code, such as WIDD for Batam or WIII for Jakarta, and press Enter. The first
  airport in your list is your default airport.
3. Press Q in Hariku's main window to hear its weather, or Shift+Q to see all your
  airports.

You don't have to add airports: without favourites, Cockpit uses the airport with a
weather report nearest to your main place from Preferences, Places, up to about 300
kilometres away.

## Hearing your airport's weather

Press Q. Hariku reads the latest report of your default airport:

- the airport and its code, "automatic station" when it is one, and when the report was
  made, in local time and in Zulu (UTC); for a report more than 2 hours old, how old it is
- the wind, the visibility, weather such as rain, mist or a thunderstorm, and the clouds
  with their heights
- the temperature and dew point, and the QNH (the air pressure pilots set on the
  altimeter)
- when the report has them: runway visual range, wind shear, recent weather and the trend
  expected in the next hours
- the flight category (VFR, marginal VFR, IFR or low IFR) with what it means

Reports are fetched at most every 10 minutes, so pressing Q again sooner repeats the one
Hariku has. When the service can't be reached, Hariku says why and then reads the last
report, with the time it was fetched, as long as it is less than 12 hours old.

Without favourite airports, the first press says "Looking for the airport nearest to",
then your place, then which airport it chose, followed by its weather. Hariku remembers
that airport for your place.

To also hear the report in its original code, tick "Also read the raw report" in
Preferences, Cockpit.

## The Airport Weather window

Press Shift+Q to open the Airport Weather window:

- "Your airports": one row per airport, with its name, its code, "default" for the first
  one, and a short summary: the sky, the temperature, the wind and the flight category.
- "Decoded report and forecast": the selected airport's report in sentences, then its
  forecast: when it was issued, how long it is valid, and each period, such as
  "temporarily" or a chance in percent, with the highest and lowest temperatures.
- "Raw codes": the report and the forecast as they were sent.
- Buttons: Refresh, Add airport..., Remove, Make default and Close (or Escape).

When the window opens, Hariku fetches what is out of date: reports older than 10 minutes
and forecasts older than 30 minutes. If you press Refresh while everything is fresh,
Hariku says it is already up to date.

## Managing your airports

You can keep up to 20 favourite airports. Manage them in Preferences, Cockpit, in
"Favourite airports (the first one is your default)", or in the Airport Weather window:

- To add one, type its ICAO code and press Enter or Add (in the window: Add airport...,
  which asks for the code). Hariku checks the code with the weather service first, then
  tells you the airport's name, and whether it has a recent report.
- Remove removes the selected airport.
- Make default moves the selected airport to the top of the list.

These buttons act at once; you don't need to press OK.

Without favourites, the list shows the nearest airport Hariku found. It can't be removed,
but as soon as you add your own airports, they are used instead. To find the nearest
airport for a different one of your places, choose it in "Place, for the nearest airport
when you have no favourites".

## Captain mode

In Preferences, Cockpit, tick "Captain mode" and press OK. Captain mode:

- adds a short line to your Morning Briefing: the time in Zulu and your default airport's
  wind, visibility, weather, clouds, temperature and QNH
- adds tomorrow morning's forecast for your default airport to the evening summary
- keeps your default airport's report and forecast up to date in the background, about
  every 30 minutes
- spells airport codes in the pilots' alphabet, such as "Whiskey India Delta Delta"

When you turn it on, Hariku asks two questions (Yes or No): whether it should call you
Captain, if you have no title in Preferences, Profile yet, and whether to set a cockpit
greeting for when Hariku starts. That greeting welcomes you aboard by your title and
nickname, and says the local and Zulu time, your airport's weather and your reminders.
When you turn Captain mode off, Hariku offers to remove the title and the greeting again.

## Airport weather in the briefing without Captain mode

Tick "Add airport weather to the Morning Briefing (without Captain mode)" to hear a short
line in the Morning Briefing: the sky, temperature and wind at your default airport. It
needs at least one favourite airport.

Without Captain mode, Hariku doesn't fetch anything in the background. The Morning
Briefing only reads what is already on your computer, so the line appears when the last
report is less than 3 hours old, for example after you pressed Q.

## The %airportweather% placeholder

Write %airportweather% in your startup greeting (Preferences, Profile), a reminder or a
routine, and Hariku fills in your default airport's weather from the last report: the
wind, visibility, weather, clouds, temperature and QNH. When there is no report from the
last 3 hours, it stays empty.

## The Cockpit sound theme

Press "Install the Cockpit sound theme" in Preferences, Cockpit. It adds a theme called
Cockpit to the Sound Themes extension: a two-tone cabin chime for information and
reminders, a single chime for confirmations, a short low double beep for errors and a
rising chime when Hariku starts. The sounds are made on your computer.

The Sound Themes extension has to be installed and turned on first. To use the theme, open
Preferences, Sound Themes, choose Cockpit and press "Use this theme".

## Settings

Open Preferences, Cockpit:

- "Captain mode": see above. Off by default.
- "Install the Cockpit sound theme": see above.
- "Favourite airports (the first one is your default)", with "ICAO code of an airport to
  add (press Enter to add)", Add, Remove and Make default.
- "Place, for the nearest airport when you have no favourites": the main place (the
  default) or another of your places.
- "Also read the raw report": Q also reads the report in its original code.
- "Add airport weather to the Morning Briefing (without Captain mode)".

Captain mode and the two checkboxes are saved when you press OK; the airport buttons act
at once.

## Keys and commands

These keys work in Hariku's main window:

- Q: Pilot weather: speak the decoded METAR of your default airport
- Shift+Q: Airport weather: open your airports with their METAR and TAF

You can change them in Preferences, Input Gestures.

In Aruna (Ctrl+Alt+Backspace), "pilot weather", "metar" or "cuaca pilot" speaks the
weather, and "airport weather" or "cuaca bandara" opens the Airport Weather window.

## Privacy

Cockpit downloads reports and forecasts from the NOAA Aviation Weather Center
(`aviationweather.gov`), with no account or key: when you ask for them (at most every 10
minutes for a report and every 30 minutes for a forecast), when you add an airport (to
check its code) and, only in Captain mode, in the background about every 30 minutes. These
requests contain only the ICAO codes of your airports.

To find the nearest airport, Cockpit sends a box of about 110 kilometres around your
place, or about 330 kilometres if nothing is found, with its corners rounded to 0.1
degree. It never sends your own location or anything from your profile.
