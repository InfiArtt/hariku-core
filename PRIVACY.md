# Privacy

Hariku does not collect analytics or telemetry. Your calendar, reminders,
routines, profile (your name, birthday and the placeholders you add in
Preferences, Profile), places (Preferences, Places), settings, and extension
data stay on your computer, in `%APPDATA%\Hariku2`. Hariku Voice with the built-in Windows voices speaks on
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

## Places

Your places (Preferences, Places: their names, such as Home or Office, where
they are, and which one is your main place) are saved only on your computer, in
`Places.json`. Hariku never sends your list of places anywhere, and never
uses your device's location. The exact point of a place stays on your
computer: the extensions below send a service at most the place rounded to
about 1 kilometre (latitude and longitude to 2 decimals), and several send
nothing about it at all.

Finding a place connects only when you ask for it on the Places page (or an
extension's own place search):

- Searching for an address sends the text you typed and your Hariku language
  to OpenStreetMap's Nominatim service (`nominatim.openstreetmap.org`), only
  when you press Enter or the Search button, never while you type. Hariku
  asks at most once a second, answers the same search again from memory, and
  names itself and its website in the request, as Nominatim's usage policy
  asks. This is covered by the
  [OpenStreetMap Foundation privacy policy](https://osmfoundation.org/wiki/Privacy_Policy).
- Searching for a city sends the text you typed and your Hariku language to
  Open-Meteo's city search (`geocoding-api.open-meteo.com`).
- Pasted coordinates and full map links (Google Maps, Apple Maps,
  OpenStreetMap) are read on your computer. A short Google Maps link
  (`maps.app.goo.gl` or `goo.gl/maps`) is sent to Google once, when you press
  Use, to find the coordinates it points to; the page it leads to is never
  opened.

The first time you start Hariku 2.8, it makes "Home" from what was already
on your computer (Flight Radar's exact home, or else the Weather city),
without connecting to anything.

## The welcome

The welcome (the first start, and Help, Welcome Dialog) saves your name,
nickname, birthday and city only on your computer, like Preferences, Profile
and Places. While it is open it connects only for these:

- Finding your city sends the text you typed and your Hariku language to
  Open-Meteo's city search (`geocoding-api.open-meteo.com`), when you press
  Enter or Search.
- The weather in your city: the city's point rounded to about 1 kilometre
  goes to Open-Meteo (`api.open-meteo.com`), for the city you choose or the
  main place you already have. See Open-Meteo's
  [terms and privacy policy](https://open-meteo.com/en/terms).
- The extension store listing from GitHub Pages, to suggest extensions.
  Nothing is downloaded until you press Finish; then only the extensions you
  ticked are downloaded from Hariku's GitHub releases.

"Try it" (meeting Aruna) answers on your computer and sends nothing.

## Weather

The Weather extension sends nothing until it has a place: your main place,
another of your places, or a city of its own chosen in its settings. After
that, it fetches the forecast from Open-Meteo (`api.open-meteo.com`) when
Hariku starts, about every 30 minutes, and when you ask for the weather. The
request contains the place rounded to about 1 kilometre (2 decimals) and its
time zone, never the exact point or your device's location. (Before Hariku
2.8 it sent the chosen city's centre to 4 decimals.) Searching for a city in
the Weather settings sends the text you typed to Open-Meteo's city search
(`geocoding-api.open-meteo.com`). Open-Meteo's
handling of these requests is covered by its
[terms and privacy policy](https://open-meteo.com/en/terms#privacy). The Morning
Briefing extension makes no connections of its own.

## Sea Conditions and Air Quality

These two extensions work like Weather. Each uses your main place, another of
your places, or a place of its own chosen in its settings (such as a beach for
Sea Conditions), and sends nothing until it has one. After that, each fetches
its data from Open-Meteo when Hariku starts, about every 30 minutes, and when
you ask: Sea Conditions from `marine-api.open-meteo.com`, Air Quality from
`air-quality-api.open-meteo.com`. The request contains the place rounded to
about 1 kilometre (2 decimals) and its time zone, never the exact point or your
device's location. (Before Hariku 2.8 they sent the place to 4 decimals.)
Searching for a place sends the text you typed to Open-Meteo's city search, as
described for Weather above.

## Earthquakes and Tsunami

The Earthquakes and Tsunami extension downloads BMKG's public earthquake files
from `data.bmkg.go.id`. With the tsunami alert on (the default) or any other
BMKG alert on, it checks the latest-earthquake file about once a minute while
Hariku runs. It also downloads BMKG's recent lists when you open them. If you
turn on worldwide alerts, or show worldwide earthquakes in the list, it
downloads the U.S. Geological Survey's public feeds from
`earthquake.usgs.gov`.

These requests contain none of your data. Your location (your main place,
another of your places, or a city of its own chosen in its settings) stays on
your computer: the extension downloads the same files for everyone and works
out distances itself. Searching for a city sends the text you typed to
Open-Meteo's city search, as described for Weather above.

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

Your location (your main place, another of your places, or a city of its own
chosen in its settings) is never sent; distances, directions, and sunrise and
sunset are worked out on your computer.

## Flight Radar

The Flight Radar extension connects only when you use it: when you ask what is
flying nearby, open the radar list, or turn on overhead alerts or the
emergency watch (which then check every 30 to 60 seconds).

Your location is your main place, another of your places, or a place of its
own set in the Flight Radar settings (a city, an address, or coordinates you
pasted). It is never your device's location. The exact point stays on your
computer. Each check sends only that point rounded to about 1 km, with a
slightly wider radius, to adsb.fi (`opendata.adsb.fi`), or to adsb.lol
(`api.adsb.lol`) if adsb.fi doesn't answer. Hariku then works out each
aircraft's distance and direction from your exact point itself.

- To say where a flight is going, it sends only that flight's callsign to
  adsbdb (`api.adsbdb.com`). Routes are kept in memory and never saved.
- Searching for a city sends the text you typed to Open-Meteo's city search,
  as described for Weather above.
- Searching for an address, pasted coordinates and map links work as
  described under Places above (Flight Radar uses the same search).
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
favourite airports, Cockpit finds the airport nearest to your main place (or
another of your places, chosen in its settings) by sending a box of 1 degree
around that place, or 3 degrees if nothing is found (roughly 110 or 330
kilometres), with its corners rounded to 0.1 degree. It keeps only that place's
name and its point rounded to about 1 kilometre, to know the airport was found
for it. It never sends your own location or anything from your profile. The Cockpit sound
theme is generated on your computer. NOAA's handling of these requests is
covered by the [National Weather Service privacy policy](https://www.weather.gov/privacy).

## Placeholders and the startup greeting

Placeholders such as %weather%, %sleep%, %airportweather% and %reminders%, and
the startup greeting you write on the Profile page, only use what Hariku and
its extensions already have on your computer: filling them in never makes a
connection. When Windows starts Hariku, the greeting waits until Windows
reports a network connection; Hariku only asks Windows, it contacts nothing.

## Reminders typed as a sentence

The quick reminder (N) and the reminder dialog's "Or type it in one sentence"
field read what you type on your computer, with rules built into Hariku. No AI
and no online service is involved: the sentence is never sent anywhere, and it
is not stored. Only the reminder you save is kept, like any other reminder.

## Aruna, the command bar

Aruna (Ctrl+Alt+Backspace) works out what you typed or said on your
computer, with rules built into Hariku: it compares your words with the names
of Hariku's actions. No AI and no online service is involved, and what you
type is not stored. A command you run makes the connections that command
makes when you use its own key (the latest earthquake downloads BMKG's file,
for example), as described on this page.

## Clipboard History

The Clipboard History extension sends nothing over the internet. Copied text
stays in memory until you close Hariku. If you turn on "Remember history after
restarting Hariku", it is saved in `%APPDATA%\Hariku2` on your computer; pinned
items are always saved there. Copies that password managers mark as private
are never recorded.

## Timer & Alarm

The Timer & Alarm extension sends nothing over the internet. What you type or
say to Aruna to set an alarm or a timer is read on your computer, with rules
built into Hariku (no AI and no online service), and is not stored; only the
alarm or timer you set is kept (its name, when it is due and how often it
repeats), with your sound and ring settings, in `%APPDATA%\Hariku2` on your
computer. To stop a ring when you press a key, it asks Windows when the
keyboard or mouse was last used, only while something rings or after a ring
you missed; it never records which keys you press. Its sounds are Windows' own
alarm sounds on your computer or tones that come with the extension.

## World Trip

The World Trip extension connects only when you take a trip or ask something
during one, and it only ever sends the destination, never anything about you:
- Finding the city you asked for sends its name, as you typed or said it, to
  Open-Meteo's geocoding (`geocoding-api.open-meteo.com`), searched in English
  and in Hariku's language; to name the city in your language, in English and
  in its own language, the city found is looked up again by its GeoNames
  number. The weather sends the destination's point, rounded to about 1
  kilometre, to Open-Meteo (`api.open-meteo.com`). See Open-Meteo's
  [terms and privacy](https://open-meteo.com/en/terms).
- The radio asks the free Radio Browser directory (`*.api.radio-browser.info`)
  for stations with the destination's country code and its point rounded to
  about 1 kilometre, and tells it which station started playing (its station
  id), as the directory asks its users to. The station you hear streams from
  that station's own server, which sees your IP address like any radio player.
  See [Radio Browser](https://www.radio-browser.info).
- "Tell me about this city" sends the city's (or country's) name to Wikipedia
  (`id.wikipedia.org` or `en.wikipedia.org`). See the
  [Wikimedia privacy policy](https://foundation.wikimedia.org/wiki/Policy:Privacy_policy).
- A greeting or phrase spoken in a native voice goes through Hariku Voice:
  with an Edge voice, its text is sent to Microsoft's speech service (see Edge
  Voices below); Piper and Windows voices speak on your computer.

The distance and flight time from your main place are worked out on your
computer: your places never leave it. Station lists and Wikipedia summaries are
kept for a day and a week, keyed by the destination's rounded point, in
`%APPDATA%\Hariku2`, with your settings and the number of trips you took. "Any
key skips the flight" asks Windows when the keyboard or mouse was last used,
only during a flight; it never records which keys you press. Its sounds are
generated and come with the extension.

## Orbit

The Orbit extension is a multiplayer game, so it talks to a game server: the
address in Preferences, Orbit, by default `infiartt.com` (Hariku's developer
runs it). It connects only when you open Orbit, press Connect or give it a
command (or when Hariku starts, if you turn that on), always over an
encrypted connection (`wss://`; an unencrypted `ws://` address is refused
unless it is this computer). `infiartt.com` is served through Cloudflare,
which, like any web host, sees your IP address; see the
[Cloudflare privacy policy](https://www.cloudflare.com/privacypolicy/).

- What is sent: the first time you join, your character's name and job; every
  time, a random secret made on your computer when you first joined that
  server (it stands for a password; the server keeps only a salted hash of it
  and cannot read it back), Hariku's language, and what you type or say in
  Orbit. When you leave, a goodbye; when the window has been closed and you
  have been idle for five minutes, that you're away. Nothing else about you:
  not your profile, places or reminders.
- What the server keeps: your character's name, job, the description you
  write, credits, things, where it is, its progress (XP and level, the daily
  streak, what it mined and harvested, its farm plots, the rooms it has
  visited, its friends list and its beacon), cooldowns and missions, the
  voice number you chose for others to hear, its pet (a name and a kind),
  its ship (model, name, where it's docked or flying, fuel and cargo), the
  events it took part in (and how much it helped), its achievements, its
  lottery tickets for the week's draw, its best score and how many games it
  played at each arcade cabinet, its crew and its role there, how far it got
  in each season of the hunt (its riddle, how many tries and wrong answers,
  when it may try again, when it finished and in which place; the answers
  you type are only checked, never kept), what it won or lost at the casino
  in all (and its bets of the last hour, a minute at a time, for the hourly
  limit), how many trades it made, when it was made and last seen, and
  whether an admin muted or banned it. There is no password and no email. If
  an admin bans you, a salted hash of your IP address is kept for 7 days.
  Trade offers, coin-flip challenges and crew invitations are kept only in
  the server's memory, until they are answered or run out.
- Moving your character to another computer: the server keeps only a keyed
  hash of the transfer code, for 10 minutes or until it is used. After a
  move, the hash of the old computer's secret is kept so that computer can be
  told the character moved. A short log of transfers (the character, what
  happened, when) is kept for the admins, as is a log of what admins do.
  To limit guessing, the server remembers wrong codes per connection
  address for 15 minutes, in memory only.
- Chat is not stored. What you say is passed on to the players in the same
  place, a whisper to one player, a shout to everyone online, crew chat to
  your crew's members online, and then it is gone: the server writes no
  chat, secrets, codes or IP addresses to its log (only names, and who
  joined, left or was muted). Other players see your character's name, job
  and rank, where it is, what you say and do, what it wears, its pet, its
  public progress (level, what it mined and harvested, its achievements, and
  its place on the leaderboards: credits, level, ore, crops, the daily
  streak and casino winnings), its crew and its description. Big casino
  wins, the lottery's winner, new arcade high scores (the tables show
  everyone's best), how far players got in the hunt (and its board) and some
  achievements are announced to everyone online. Admins are left off the
  leaderboards and the hunt's board.
- "Remind me" makes an ordinary Hariku reminder on your computer; the server
  isn't told.
- On your computer, in `%APPDATA%\Hariku2`: your Orbit settings (including the
  players you ignore) and, for each server you joined, its secret and your
  character's name (`OrbitAccounts`). Anyone who copies that secret can play
  as your character on that server. `orbit_sounds` holds your own sound
  files if you add any, and `orbit_sound_cache` copies of Orbit's sounds made
  for your volume and for where things happen.
- Orbit's messages, other players' words and your own are read with Hariku
  Voice: with an Edge voice, that text is sent to Microsoft's speech service
  (see Edge Voices below); Piper and Windows voices speak on your computer.
  Orbit never records or sends your voice: what you say in the game is the
  text you typed (or said to Aruna, see Voice Control), and the other
  players' computers read it in the character voice you chose. Orbit's sounds come with
  the extension (some synthesized, some made from Kenney's public-domain
  recordings); nothing is downloaded for them. Credits are only for playing:
  they have no real-money value and can't be bought or cashed out, and the
  casino's games use only these credits.

## Dropbox

The Dropbox extension talks to Dropbox only after you connect it in
Preferences, Dropbox, and only with your own sign-in. From then on, whenever
Hariku runs, it keeps a connection to Dropbox to hear about changes, until you
disconnect. Hariku's developer receives nothing. Everything goes to Dropbox over encrypted connections
(`api.dropboxapi.com`, and `notify.dropboxapi.com` to hear about changes); see
the [Dropbox privacy policy](https://www.dropbox.com/privacy).

- Signing in happens in your browser, on `dropbox.com`. Dropbox then sends the
  browser back to a small listener on this computer (`http://127.0.0.1:17613`,
  open only while you sign in, reachable only from this computer) with a
  one-time code; when that port is taken, you paste the code into Hariku
  instead. The code is traded for a sign-in with PKCE, a secret made for that
  one sign-in, so Hariku has no app secret to leak. Hariku asks for four
  permissions: your account's name and email, the details of your files and
  folders (not their contents), reading shared links, and making shared links.
- What is sent: the paths (folders and names) of the files you change in your
  Dropbox folder, to ask Dropbox whether it has that version yet (it answers
  with the size and times); the path of a file whose link you copy, or the
  name you search for; and requests for what changed in your account, for the
  files and folders shared with you, and for the names of people who changed
  or shared something. When a file has no shared link yet, copying its link
  makes one with your account's usual link settings.
- Hariku never uploads, downloads or reads your files' contents: the Dropbox
  desktop app syncs them. To follow your files, Hariku reads the app's
  `info.json` to find the Dropbox folder, lets Windows tell it which files in
  that folder changed, and reads only their names, sizes and times (never an
  online-only file, which would download it).
- To know which file you're on in File Explorer, Hariku asks File Explorer
  through a short PowerShell command on this computer; nothing about it is
  sent anywhere except that file's path when you copy its link.
- On your computer, in `%APPDATA%\Hariku2`: `DropboxAccount` (the sign-in,
  encrypted with Windows' Data Protection API so only your Windows account on
  this computer can read it, and your Dropbox account's name, email and id),
  `Dropbox` (what to announce) and `DropboxShared` (which shared files and
  folders were already there, so only new ones are announced). The
  short-lived access token is only kept in memory. Tokens are never written
  to the log.
- "Disconnect Dropbox" asks Dropbox to revoke the sign-in and deletes it and
  `DropboxShared` from this computer.

## Calculator & Converter

The Calculator & Converter extension works out sums, units, coin flips, dice,
random numbers, split bills and discounts on your computer, with rules built
into Hariku (no AI and no online service). What you type or say is not stored;
only the last result is kept in memory for five minutes, so "tambah 5" and
"copy the result" can use it. It is copied to the clipboard only when you ask,
or after every answer if you turn that on.

Only currency conversions go online. The first time you convert money in a
while, Hariku downloads the day's reference exchange rates of all currencies
at once from Frankfurter (`api.frankfurter.dev`), a free service without an
API key or account that publishes central banks' daily rates. The request is
the same for everybody: it carries no currency, no amount and nothing about
you, only what every web request carries, such as your IP address and a Hariku
user agent. See [Frankfurter](https://frankfurter.dev). The rates are kept for
a few hours, and saved in `%APPDATA%\Hariku2` (`CalculatorRates`) with the
time they were fetched, so they can still answer for up to a week when you are
offline. Your settings (home currency, decimals, data sizes, copying) are
saved there too (`Calculator`).

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

## Voice Control

The Voice Control extension lets you talk to Aruna, Hariku's command bar. Your
speech is recognised on your computer by whisper.cpp, a program that runs
without the internet:

- While it listens, the microphone's sound is kept in memory only. When you
  stop speaking, it is handed to the whisper.cpp program on your computer
  through a local connection (127.0.0.1) that nothing outside your computer
  can reach, and then dropped. It is never saved to disk and never sent
  anywhere. What was recognised is handled like text you typed.
- It listens only after you press Ctrl+Alt+Backspace (or, if you turned that on,
  when Aruna opens, or when you say the wake phrase, below), and it stops on
  its own after a second or two of silence, after 12 seconds, or when you
  press the key again. Hariku plays a tone when listening starts and another
  when it ends.
- It keeps each speech model's measured speed in its settings in
  `%APPDATA%\Hariku2`, to choose a model automatically. It keeps nothing you
  said.

**The wake phrase** (Voice Control 1.1) is off until you turn on "Listen for
a wake phrase" in Preferences, Voice Control. Only while it is on, Hariku
keeps the microphone open in the background and listens for your phrase
("Hey Aruna", or one you type) with sherpa-onnx, a small keyword spotter that
runs on your computer:

- Every tenth of a second of sound goes to the keyword spotter in memory and
  is dropped straight away. Nothing is recorded, saved to disk or sent
  anywhere, and the keyword spotter can only tell whether your phrase was
  said; it doesn't turn anything else into text. Only when it hears the
  phrase does Aruna open and listen to your command, as described above.
- It doesn't listen while Voice Control listens to a command, while Hariku or
  your screen reader speaks through Hariku, while you have paused it (the
  "Pause or resume the wake phrase" command), during quiet hours if you ticked
  that, or while Windows' privacy settings block the microphone. Turn the
  option off, or remove the wake phrase listener, and the microphone is
  closed.
- The settings (whether it is on, the phrase, its sensitivity and the quiet
  hours choice) are kept with Voice Control's other settings in
  `%APPDATA%\Hariku2`.

It connects only when you press Download in Preferences, Voice Control:

- The whisper.cpp program (the official `whisper-bin-x64.zip`, release
  b5130) from GitHub (`github.com` and its download server,
  `release-assets.githubusercontent.com` or `objects.githubusercontent.com`).
- The speech models you choose (tiny, base or small) from Hugging Face
  (`huggingface.co` and its download servers, `*.hf.co`).
- The wake phrase listener: the official sherpa-onnx v1.13.8 Windows build
  and its English keyword model, from the sherpa-onnx releases on GitHub (the
  same GitHub servers).

These requests go over encrypted connections. Like every web request they
include your IP address, and they carry a user agent that names Hariku and its
version, but no identifier, no account and none of your data. Hugging Face's
handling of them is covered by the
[Hugging Face Privacy Policy](https://huggingface.co/privacy), and GitHub's by
the GitHub General Privacy Statement linked above. Hariku refuses to download
from any other server, even when redirected, and deletes any file whose
SHA-256 doesn't match the one built into the extension.

Everything is stored in `%APPDATA%\Hariku2\voice_control`: the program in
`runtime`, the models in `models`, the wake phrase listener in `wake`, and
`server.log`, the messages the whisper.cpp program printed the last time it
ran (it holds no recognised text). Remove the program, a model or the wake
phrase listener on the Voice Control page, or delete that folder to remove
everything.

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
