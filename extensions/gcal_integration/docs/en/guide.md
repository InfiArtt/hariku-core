# Google Calendar Reader

Read your Google Calendar events and public holidays in Hariku's calendar. It only reads
from Google: events you add or change in Hariku stay on this computer and never go back to
Google. Its windows are in English.

While it's on, Enter on a date, and "Add reminder..." in the Reminders menu, open its "New
Event" window instead of Hariku's reminder window; see Adding your own events.

## Getting started

1. Open Preferences and go to the "Google Calendar" page.
2. At "Private iCal URL (.ics):", paste your calendar's secret address. To find it, open
   Google Calendar on the web, go to Settings, select your calendar, then Integrate
   Calendar, and copy "Secret address in iCal format".
3. If you want holidays too, choose a country or a religion at "Public Holidays
   Calendar:".
4. Press OK. Hariku downloads your events.

Keep the secret address to yourself: anyone who has it can read your calendar. Another
calendar's `.ics` address works too, if it starts with `https://` or `http://`.

Hariku downloads the events again each time it starts and every 60 minutes, as long as a
calendar address or a holiday calendar is set. If a download fails, for example without an
internet connection, the events from that address are gone from Hariku until a later
download works. Your own events always stay.

## Hearing a day's events

Select a date in the calendar and press Shift+C. Hariku says how many events there are and
the first one, such as "2 events. Next: 09:00 Team meeting at Room 3". Press Shift+C twice
quickly to hear them all. All-day events come first, said as "All day:", and events you
added in Hariku end with "(local)". A day without events gives "No events for this date."

## Events in the agenda

Press Space on a date to open its agenda: the events come after your reminders, with their
place after "at", and "[GCal]" for events from Google or "[Local]" for your own.

## Adding your own events

Press Enter on a date, or Shift+A. The "New Event" window opens with:

- "Title:"
- "All day event": tick it for an event without a time.
- "Start Date (YYYY-MM-DD):", which starts as the selected date, and "Start Time
  (HH:MM):".
- "End Date (YYYY-MM-DD):" and "End Time (HH:MM):".
- "Location:" and "Description:"
- "Repeat:": Does not repeat, Daily, Weekly, Monthly or Yearly.
- "Status:": Confirmed, Tentative or Cancelled.

Press "Save". Hariku says "Event saved:" and the title.

Your events stay in Hariku and never go to Google. They don't ring or remind you; they are
there to read. To add a Hariku reminder while this extension is on, press N for a quick
reminder, or tell Aruna, such as "remind me to call Mum tomorrow at 8".

## Editing your events

Select the date and press Shift+E. Choose one of your own events in the list "Select an
event to edit:", change it in the "Edit Event" window and press "Save". Events from Google
can't be edited, and editing works for events that don't repeat.

## Deleting or hiding events

Use the action "Delete or hide an event" (it has no key), or "Delete Selected" in the
agenda. Choose the event:

- One of your own events is deleted.
- An event from Google is only hidden in Hariku: "Event hidden from view. Note: it still
  exists in your Google Calendar."

For a repeating event, this removes or hides all its dates. A hidden event can't be shown
again from Hariku.

## Public holidays

"Public Holidays Calendar:" lists "None", Christian, Islamic, Jewish and Orthodox
holidays, and over a hundred countries and regions. The holidays come from Google's public
holiday calendars and show like your other events. Indonesia's holidays are in Indonesian.

## Historical notes

At "Historical Data Country Code (e.g. ID, US):" you set the country, ID (Indonesia) at
first, whose notes about the history of certain dates Hariku downloads with your events.
Leave it empty to download none.

On a date that has at least one event, press I. If there's a note for that date, it opens
in a window called "Historical Information" that you read in browse mode. Otherwise Hariku
says "No historical info available for this date."

## Syncing now

The action "Sync with Google Calendar now" (it has no key) downloads your events at once.
Hariku says "Syncing with Google Calendar..." but doesn't announce when it's done. When
neither a calendar address nor a holiday calendar is set, it says "Please configure a
Google Calendar URL in settings first."

## Importing from Hariku V1

The "Import Events from Hariku V1" button on the settings page reads the events file of
Hariku V1 and adds its events as your own all-day events; the ones that came back every
year repeat yearly. A message then shows how many it imported. Press it only once: a
second press adds the same events again.

## Settings

In Preferences, Google Calendar:

- "Private iCal URL (.ics):": your calendar's secret address.
- "Historical Data Country Code (e.g. ID, US):": the country for historical notes.
- "Public Holidays Calendar:": the holidays to show, or "None".
- "Import Events from Hariku V1": see Importing from Hariku V1.

When you change one of the first three and press OK, Hariku downloads again at once.

## Keys and commands

In Hariku's main window:

- Shift+C: Read events for selected date (tap twice for all).
- I: View Historical Context.
- Shift+A: Add a new event (Enter on a date does the same).
- Shift+E: Edit a local event.
- Delete or hide an event: no key.
- Sync with Google Calendar now: no key.

They are under "Google Calendar" in Preferences, Input Gestures, where you can change or
add keys. Aruna runs them by their names, such as "sync with google calendar now".

## Privacy

Each time it downloads, Google Calendar Reader connects to:

- the server of your calendar address, Google for a Google Calendar, to get your events;
- Google Calendar (calendar.google.com), for the holiday calendar you chose;
- GitHub Pages (infiartt.github.io), for the historical notes of your country code.

These requests only ask for those files; they carry nothing else about you beyond what
every web request carries, such as your IP address. Your own events, your hidden events
and the downloaded copy stay on your computer.
