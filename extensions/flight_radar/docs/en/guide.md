# Flight Radar

Flight Radar tells you which aircraft are flying near you: the nearest few with one key, a
list of everything in range, and, if you like, an announcement when one passes overhead or
reports an emergency. You can also track a flight anywhere in the world by its number, and
open LiveATC in your browser to listen to air traffic control. It needs Hariku 2.8 or
newer.

## Getting started

Flight Radar uses your main place from Preferences, Places (Preferences opens with
Ctrl+P). You can choose another of your places, or a place of its own (a city, a street
address or exact coordinates), in Preferences, Flight Radar.

Then press P in Hariku's main window to hear what's flying nearby, or Shift+P to open the
radar list. You can also open Aruna, Hariku's command bar, with Ctrl+Alt+Backspace and
type "planes nearby" or "flight list".

## What's flying nearby

Press P. Hariku says "Checking the radar..." and then reads the 3 nearest aircraft within
your radar radius (25 kilometres unless you change it), nearest first, and how many more
there are. For each aircraft you hear:

- its name: the airline and flight number, such as Garuda Indonesia 155, or its
  registration and country, or "Unidentified aircraft"
- where it is flying from and to, when Hariku finds a route that fits where the aircraft
  is
- the aircraft type, such as Boeing 737-800
- how far away it is and in which direction
- its altitude, and whether it is climbing, descending or level

An aircraft that reports an emergency is said first, starting with "Attention".

If you ask again within 15 seconds, you hear the same radar. If the service can't be
reached, Hariku says why and, when it has a radar from the last 2 minutes, reads that one
with its time.

## The radar list

Press Shift+P to open the Flight Radar window. The list shows every aircraft within your
radar radius, nearest first, one sentence per row. The row of an aircraft in an emergency
starts with "Emergency".

- Arrow through the list. "Details of the selected aircraft" shows more about it: its
  registration, type, speed, heading, how fast it climbs or descends, its squawk code with
  what the code means, any status it reports, and which airport Listen to ATC would open.
- Enter, or the Details button, reads the details aloud (Hariku looks up the route first).
- Refresh gets a new radar. Hariku then says how many aircraft are in range, with any
  emergency first.
- Listen to ATC opens LiveATC for the selected aircraft (see "Listening to air traffic
  control" below).
- Track... opens Track a Flight with the selected aircraft filled in.
- Close, or Escape, closes the window.

Below the details, a line says when the radar was updated and which service it came from.

## Overhead alerts

To hear aircraft as they pass over you, open Preferences, Flight Radar, tick "Announce
aircraft passing overhead", choose the "Overhead alert distance" (1, 2, 3, 5 or 10
kilometres; 5 by default) and press OK.

While Hariku is running, it checks about every 30 seconds. When an aircraft in the air
comes within that distance, Hariku plays a sound and says "Overhead", followed by the
aircraft. Each aircraft is announced once, then not again for 10 minutes. Alerts stay
silent during quiet hours (Preferences, Quiet Hours).

## The emergency watch

Tick "Watch for emergencies in the background" in Preferences, Flight Radar. While Hariku
is running, it checks about every 60 seconds (every 30 with overhead alerts on). When an
aircraft within your radar radius squawks an emergency code (7500, 7600 or 7700) or
reports an emergency, such as low fuel or a radio failure, Hariku plays a sound and says
"Attention", the aircraft, what it reports and where it is.

Hariku words it as what the aircraft's transponder says, since codes are sometimes set by
mistake. Each aircraft and emergency is announced once, then not again for 30 minutes. The
watch is silent during quiet hours, and nothing is saved up for afterwards.

## Tracking a flight

Press Shift+T to open Track a Flight. Type a flight number or a registration, such as GA
408, QZ 7510 or PK-GPA, and press Enter. The airline's 3-letter ICAO code works too, such
as GIA 408. If Hariku doesn't know a 2-letter airline code, it asks you to type the
3-letter one instead.

Hariku finds the flight anywhere in the world and tells you where it is: its route when
known, how far it is from the nearest airport Hariku knows, its altitude and whether it is
climbing or descending. If the flight isn't transmitting right now (it may still be on the
ground or outside coverage), Hariku says so. Either way, it starts tracking it. If the
lookup itself fails, Hariku tells you why and tracks nothing. You can track up to 3
flights.

While Hariku is running, it checks your tracked flights about every minute (every 30
seconds with overhead alerts on) and tells you, with a sound, when a flight:

- takes off
- passes near you (within your overhead alert distance)
- comes within 50 kilometres of its destination (when its route is known)
- lands

Tracking stops by itself an hour after landing, or after 24 hours. Tracked flights stay
tracked when you restart Hariku, and they still report during quiet hours, since you asked
for them.

In the Track a Flight window, "Tracked flights (up to 3)" shows each flight with its last
position and when it was checked. Stop tracking (or Delete) stops the selected flight, and
Check now looks them all up and tells you where they are.

To hear where all your tracked flights are without opening the window, press T in Hariku's
main window.

## Listening to air traffic control

Press Shift+L to open LiveATC's web page in your browser, for the airport nearest to your
place. Hariku knows every large and medium airport in Indonesia, and the big airports near
Indonesia and in the region, such as Singapore, Kuala Lumpur, Bangkok, Manila, Perth and
Darwin.

For Jakarta Soekarno-Hatta (WIII) and Surabaya (WARR), Hariku opens LiveATC's listening
page for that airport's feed. For other airports, it opens LiveATC's search page for the
airport, which shows whether a live feed exists.

In the radar list, Listen to ATC picks the airport the selected aircraft is most likely
talking to: its destination when it is descending, where it came from when it is climbing,
otherwise the nearer of the two. You hear the whole frequency, not just that aircraft.

Hariku never plays the radio itself. Rules on listening to aviation radio differ by
country.

## Settings

Open Preferences, Flight Radar:

- "Place": the place to use. "The main place" is the default; you can also pick another of
  your places, or "Its own place…" for a place just for Flight Radar.
- "Radar radius": 10, 25 (the default) or 50 kilometres.
- "Units": "Metric: kilometres, metres, km/h" or "Aviation: nautical miles, feet, knots".
- "Include aircraft on the ground": off by default.
- "Announce aircraft passing overhead" and "Overhead alert distance": see above.
- "Watch for emergencies in the background": see above.

### A place of its own

With "Its own place…" chosen, find the place in one of three ways, then press OK:

- A city: type it in "City to search for (press Enter to search)" and press Enter or
  Search, then pick it in "City search results".
- A street address: type it in "Street address to search for (press Enter to search)" and
  press Enter or Find address, then pick it in "Address search results".
- Exact coordinates: paste them, such as -6.2088, 106.8456, or a map link from Google
  Maps, Apple Maps or OpenStreetMap, in "Coordinates or map link (press Enter to use)",
  and press Enter or Use. Hariku tells you the point it found and how far it is from the
  nearest airport.

For an address or coordinates, "Name for this place" gives it a name (Home by default).
"Its own place" shows the place that is saved.

## Keys and commands

These keys work in Hariku's main window:

- P: What's flying nearby? Speak the nearest aircraft
- Shift+P: Open the flight radar list
- T: Where are my tracked flights? Speak their positions
- Shift+T: Track a flight
- Shift+L: Listen to air traffic control (opens LiveATC in your browser)

You can change them in Preferences, Input Gestures.

In Aruna (Ctrl+Alt+Backspace):

- "what's flying nearby", "planes nearby", "nearby planes", "flights nearby", "pesawat",
  "pesawat terdekat" or "radar pesawat": What's flying nearby?
- "flight list", "radar list" or "daftar pesawat": the radar list
- "tracked flights", "where are my flights" or "penerbangan yang dilacak": where your
  tracked flights are
- "track a flight" and "listen to air traffic control" also work, by the actions' names.

## Privacy

Flight Radar connects only when you use it: when you ask what is flying nearby, open the
radar list, track a flight, or turn on overhead alerts or the emergency watch (which then
check every 30 to 60 seconds, but not during quiet hours).

- Your exact place stays on your computer. Each radar check sends only that point rounded
  to about 1 kilometre, with a slightly wider radius, to adsb.fi (`opendata.adsb.fi`), or
  to adsb.lol (`api.adsb.lol`) if adsb.fi doesn't answer. Hariku works out each aircraft's
  distance and direction from your exact point itself.
- To say where a flight is going, Hariku sends only its callsign to adsbdb
  (`api.adsbdb.com`). Routes are kept in memory and never saved.
- Tracking a flight sends only its flight number or registration to adsb.fi (or adsb.lol),
  about once a minute (twice with overhead alerts on) while you track it, never your
  location.
- Searching for a city sends the text you typed, and your Hariku language, to Open-Meteo's
  city search (`geocoding-api.open-meteo.com`).
- Searching for an address sends the address you typed, and your Hariku language, to
  OpenStreetMap's Nominatim service. Pasted coordinates and full map links are read on
  your computer; a short Google Maps link is sent to Google once, to find the coordinates
  it points to.
- Listen to ATC opens a liveatc.net page in your browser. Hariku itself sends nothing to
  LiveATC.
