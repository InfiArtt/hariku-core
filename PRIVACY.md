# Privacy

Hariku does not collect analytics or telemetry. Your calendar, reminders,
routines, profile (your name, birthday and the placeholders you add in
Preferences, Profile), settings, and extension data stay on your computer, in
`%APPDATA%\Hariku2`. Hariku Voice with the built-in Windows voices speaks on
your computer too: the text it reads never leaves it.

This page lists every case where Hariku and the official extensions in the
Hariku store connect to the internet. It does not cover third-party
extensions, which can make their own connections.

## Automatic connections

When Hariku starts, it downloads a few small files from GitHub Pages
(`infiartt.github.io`):

- `version.json`, to see whether a newer version of Hariku exists. If one does,
  Hariku shows a dialog before downloading anything.
- The extension store listing, to see whether your extensions have updates. You
  can stop this by setting extension updates to "Do nothing" in Settings.
- The list of trusted extension hashes, which Hariku uses to check extensions
  from the store before loading them.

If the Google Calendar Reader extension is enabled, it also downloads holiday
data for the selected country (Indonesia by default) from GitHub Pages, and it
fetches any calendar (ICS) links you add from the servers that host them.

These requests carry only what every web request carries, such as your IP
address and a Hariku user agent. They contain no identifier, no account
details, and none of your data. GitHub's handling of them is covered by the
[GitHub General Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).

## Weather

The Weather extension sends nothing until you choose a city. After that, it
fetches the forecast from Open-Meteo (`api.open-meteo.com`) when Hariku starts,
about every 30 minutes, and when you ask for the weather. The request contains
the chosen city's coordinates and time zone, not your device's location.
Searching for a city in the Weather settings sends the text you typed to
Open-Meteo's city search (`geocoding-api.open-meteo.com`). Open-Meteo's
handling of these requests is covered by its
[terms and privacy policy](https://open-meteo.com/en/terms#privacy). The Morning
Briefing extension makes no connections of its own.

## Sea Conditions and Air Quality

These two extensions work like Weather. Each uses its own place if you choose
one in its settings, or the Weather city otherwise, and sends nothing until one
of them is set. After that, each fetches its data from Open-Meteo when Hariku
starts, about every 30 minutes, and when you ask: Sea Conditions from
`marine-api.open-meteo.com`, Air Quality from `air-quality-api.open-meteo.com`.
The request contains the place's coordinates and time zone, not your device's
location. Searching for a place sends the text you typed to Open-Meteo's city
search, as described for Weather above.

## Earthquakes and Tsunami

The Earthquakes and Tsunami extension downloads BMKG's public earthquake files
from `data.bmkg.go.id`. With the tsunami alert on (the default) or any other
BMKG alert on, it checks the latest-earthquake file about once a minute while
Hariku runs. It also downloads BMKG's recent lists when you open them. If you
turn on worldwide alerts, or show worldwide earthquakes in the list, it
downloads the U.S. Geological Survey's public feeds from
`earthquake.usgs.gov`.

These requests contain none of your data. Your location stays on your
computer: the extension downloads the same files for everyone and works out
distances itself. Searching for a city sends the text you typed to Open-Meteo's
city search, as described for Weather above.

## Space

The Space extension connects only when you use it. The one exception: while
you have a launch reminder set, it refreshes the launch list at most once an
hour.

- "Where is the ISS?" asks `api.wheretheiss.at` for the space station's
  position, then sends that position (the station's, not yours) back to the
  same service to learn which country it's over.
- The launch list comes from The Space Devs (`ll.thespacedevs.com`). Launch
  reminders are kept on your computer.
- Sunrise, sunset and the moon phase are calculated on your computer.
- Searching for a city sends the text you typed to Open-Meteo's city search,
  as described for Weather above.

Your location is never sent; distances and directions are worked out on your
computer.

## Flight Radar

The Flight Radar extension connects only when you use it: when you ask what is
flying nearby, open the radar list, or turn on overhead alerts or the
emergency watch (which then check every 30 to 60 seconds).

Your location is the place you set in the Flight Radar settings (a city, an
address, or coordinates you pasted), or the Weather city if you haven't set
one. It is never your device's location. The exact point stays on your
computer. Each check sends only that point rounded to about 1 km, with a
slightly wider radius, to adsb.fi (`opendata.adsb.fi`), or to adsb.lol
(`api.adsb.lol`) if adsb.fi doesn't answer. Hariku then works out each
aircraft's distance and direction from your exact point itself.

- To say where a flight is going, it sends only that flight's callsign to
  adsbdb (`api.adsbdb.com`). Routes are kept in memory and never saved.
- Searching for a city sends the text you typed to Open-Meteo's city search,
  as described for Weather above.
- Searching for an address sends the text you typed to OpenStreetMap's
  Nominatim service (`nominatim.openstreetmap.org`), covered by the
  [OpenStreetMap Foundation privacy policy](https://osmfoundation.org/wiki/Privacy_Policy).
- Pasted coordinates and full map links are read on your computer. A short
  Google Maps link (`maps.app.goo.gl`) is sent to Google once, when you press
  Use, to find the coordinates it points to.
- "Listen to ATC" opens a liveatc.net page in your browser. Hariku itself
  sends nothing to LiveATC.
- Tracking a flight sends only its flight number or registration to adsb.fi
  (or adsb.lol), about once a minute while you track it, never your location.
  Tracking stops by itself an hour after landing or after 24 hours.

## Cockpit

The Cockpit extension downloads aviation weather reports (METAR) and forecasts
(TAF) from the NOAA Aviation Weather Center (`aviationweather.gov`): when you
ask for them (at most every 10 minutes for a report and every 30 minutes for
a forecast), when you add an airport (to check its code), and, only while
Captain mode is on, in the background about every 30 minutes. These requests
contain the ICAO codes of your airports, such as WIDD. When you have no
favourite airports, Cockpit finds the airport nearest to your Weather city by
sending a box of 1 degree around that city, or 3 degrees if nothing is found
(roughly 110 or 330 kilometres), with its corners rounded to 0.1 degree. It
never sends your own location or anything from your profile. The Cockpit sound
theme is generated on your computer. NOAA's handling of these requests is
covered by the [National Weather Service privacy policy](https://www.weather.gov/privacy).

## Placeholders and the startup greeting

Placeholders such as %weather%, %sleep%, %airportweather% and %reminders%, and
the startup greeting you write on the Profile page, only use what Hariku and
its extensions already have on your computer: filling them in never makes a
connection. When Windows starts Hariku, the greeting waits until Windows
reports a network connection; Hariku only asks Windows, it contacts nothing.

## Clipboard History

The Clipboard History extension sends nothing over the internet. Copied text
stays in memory until you close Hariku. If you turn on "Remember history after
restarting Hariku", it is saved in `%APPDATA%\Hariku2` on your computer; pinned
items are always saved there. Copies that password managers mark as private
are never recorded.

## Sleep Pattern

The Sleep Pattern extension sends nothing over the internet. Once a minute it
asks Windows whether the keyboard or mouse was used, and saves only that: used,
not used, or unknown, for each minute. It never records what you typed, which
keys you pressed, or which apps or windows you used. The record stays in
`%APPDATA%\Hariku2` for 90 days, and you can clear it in its settings.

## Edge Voices

The Edge Voices extension sends nothing until you choose "Microsoft Edge neural
voices (online)" as the source in Preferences, Hariku Voice. From then on, when
a Hariku Voice announcement is read with an Edge voice (the startup greeting,
the Briefing and evening summary, or a reminder, whichever you turned on), or
you press Test, it sends the text being read, with the chosen voice and speed,
to Microsoft's online speech service for the Edge browser
(`speech.platform.bing.com`) over an encrypted connection. That text can
include your nickname and your reminder titles. The request also carries a
random identifier made up for that request and an Edge browser user agent, but
no account and none of your other data. The list of voices comes from the same
service, at most once a week, and contains nothing about you.

Microsoft's handling of these requests is covered by the
[Microsoft Privacy Statement](https://privacy.microsoft.com/privacystatement).
The service is meant for the Edge browser and may stop working at any time;
Hariku then uses your fallback voice.

The speech that comes back is saved in `%APPDATA%\Hariku2\voice_cache\edge`
(up to 30 MB; the least recently used goes first), so a phrase Hariku says
again, like your greeting, plays at once and without the internet. The voice
list is kept there too. Delete that folder to remove them.

## Piper Voices

The Piper Voices extension speaks entirely on this computer: the text being
read never leaves it, and speaking needs no internet connection. It connects
only when you work with voices in Preferences, Piper Voices:

- When you open that page, it downloads the list of voices (`voices.json`)
  from Hugging Face (`huggingface.co`), at most once a week, or when you press
  "Refresh catalogue".
- When you press Download for a voice, it first downloads that voice's model
  card from Hugging Face, so you can see its dataset, license and size before
  you decide. If you choose Download, it downloads the voice's files from
  Hugging Face and its download servers (`*.hf.co`).
- With your first voice, it also downloads the Piper program (the official
  `piper_windows_amd64.zip`, release 2023.11.14-2) from GitHub (`github.com`
  and its download server, `release-assets.githubusercontent.com` or
  `objects.githubusercontent.com`).

These requests go over encrypted connections. Like every web request they
include your IP address, and they carry a user agent that names Hariku and its
version, but no identifier, no account and none of your data. Hugging Face's
handling of them is covered by the
[Hugging Face Privacy Policy](https://huggingface.co/privacy), and GitHub's by
the GitHub General Privacy Statement linked above. Hariku
refuses to download from any other server, even when redirected, and deletes
any file whose checksum doesn't match: the Piper program must match the
SHA-256 built into the extension, and each voice file the checksum in the
voice list.

Everything is stored in `%APPDATA%\Hariku2\piper`: the Piper program in
`runtime`, each voice in `voices`, and the voice list. What a voice has said
is saved in `%APPDATA%\Hariku2\voice_cache\piper` (up to 30 MB; the least
recently used goes first), so a phrase it says again plays at once. Remove a
voice on the Piper Voices page, or delete those folders to remove everything.

## When you ask for it

- Opening the extension store, or installing or updating an extension,
  downloads from GitHub.
- Menu items such as support and bug reports, and routines you build with the
  "Open URL" action, open web pages in your browser.

## Crash reports

When Hariku crashes, it asks whether to send a crash report. A report goes to
infiartt.com and contains the Hariku version, your Windows version, the app
language, and the error details. The error details include a traceback, which
can contain file paths from your computer. The crash dialog also lets you
choose to always send reports or to never send them.

## Accounts

The Account Manager extension connects to infiartt.com only when you sign in.
You enter your password on infiartt.com in your browser, never in Hariku. Hariku
then receives an access token and your profile (user name and roles) and keeps
them on your computer. The
[infiartt.com privacy policy](https://infiartt.com/privacy) covers that data.
