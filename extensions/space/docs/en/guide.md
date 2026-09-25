# Space

Space tells you where the International Space Station (ISS) is right now, lists the next
rocket launches and reminds you before the ones you choose, and says today's sunrise,
sunset and moon phase. It needs Hariku 2.8 or newer.

## Getting started

Space uses your main place from Preferences, Places (Preferences opens with Ctrl+P) to say
how far away the ISS is and when the sun rises and sets. You can choose another place, or
a city just for Space, in Preferences, Space.

- Press A in Hariku's main window to hear where the ISS is.
- "Upcoming rocket launches" and "Sun and Moon" have no key. Run them from Aruna, Hariku's
  command bar (Ctrl+Alt+Backspace): type "rocket launches" or "sun and moon". You can also
  give them a key in Preferences, Input Gestures.

## Where is the ISS?

Press A. Hariku says "Checking where the ISS is..." and then tells you:

- how far away the ISS is and in which direction from your place, and the country it is
  over, or that it is over the ocean
- its altitude and speed
- whether it is in sunlight or in Earth's shadow
- when it is at least 10 degrees above your horizon: how high it is and in which direction
  to look, and, if your sky is dark while the station is in sunlight, that you may be able
  to see it

Without a place, you hear the country below the ISS (or its coordinates) and a reminder to
set a place.

Hariku asks for the position at most every 10 seconds, so pressing A again sooner repeats
the last answer. If the service failed a moment ago, Hariku tells you how many seconds to
wait before trying again.

## Upcoming rocket launches

Run "Upcoming rocket launches" to open the Upcoming Rocket Launches window. The list shows
up to 10 launches, soonest first, one sentence each: the rocket and payload, when, the
launch site and the status, such as Go, to be determined or on hold. Times are in your
place's time zone, or your computer's time when your place has none. When the launch time
isn't fixed yet, the row says so, for example "time not yet fixed".

- Arrow through the list. The Details box below shows everything known about the selected
  launch: the time and how long until then, the launch window, status, launch provider,
  launch pad, mission type and orbit.
- Enter, or the Details button, reads the details aloud.
- Refresh gets a new list. To stay within the launch service's limits, it works when the
  list is more than 15 minutes old; otherwise Hariku says when it was last updated or when
  you can refresh again.
- Remind me sets a reminder for the selected launch (see below).
- Close, or Escape, closes the window.

The window opens with the list saved on your computer and fetches a new one by itself when
the saved one is more than an hour old.

## Launch reminders

Select a launch in the list and press Remind me. Hariku confirms, and the row now ends
with "reminder set". On that launch the button becomes Cancel reminder.

Before the launch, Hariku plays a sound and says, for example, "Rocket launch in 30
minutes", followed by the name, the time and the launch site. Choose how long before in
Preferences, Space: 10 minutes, 30 minutes (the default) or 1 hour.

- Only launches with an exact time can have a reminder.
- You can have up to 20 launch reminders.
- Launch times often move. While you have a reminder, Hariku updates the launch list at
  most once an hour, and the reminder follows the new time. If a launch moves by at least
  your reminder time, you are reminded again for the new time.
- Hariku has to be running to remind you. A reminder is removed by itself some hours after
  its launch.

## Sun and Moon

Run "Sun and Moon". Hariku says your place and today's date, the time of sunrise and
sunset and how long the day is (after sunset, also tomorrow's sunrise), the moon phase and
how much of the moon is lit, and when the next full moon and the next new moon are.

All of this is calculated on your computer, without the internet. Without a place you only
hear the moon.

## In the Morning Briefing

Space adds a sentence to the Morning Briefing: today's sunset and the moon phase (only the
moon without a place), and any rocket launch with an exact time later today, from a launch
list fetched in the last 24 hours.

## Settings

Open Preferences, Space:

- "Place": the place to use. "The main place" is the default; you can also pick another of
  your places, or "Its own place…" for a city just for Space.
- With "Its own place…" chosen, type the city in "City to search for, for its own place
  (press Enter to search)" and press Enter or Search. Pick your city in "Search results"
  and press OK. The field "Its own place, for the ISS distance, sunrise and sunset" shows
  the city that is saved.
- "Launch reminders, how long before the launch": 10 minutes, 30 minutes or 1 hour.

## Keys and commands

- A (in Hariku's main window): Where is the ISS?
- No key: Upcoming rocket launches
- No key: Sun and Moon

Actions without a key can get one in Preferences, Input Gestures, where you can also
change A.

In Aruna (Ctrl+Alt+Backspace):

- "where is the iss", "iss", "space station", "di mana iss" or "stasiun luar angkasa":
  Where is the ISS?
- "rocket launches", "launches" or "peluncuran roket": Upcoming rocket launches
- "sun and moon", "sunrise", "sunset", "matahari dan bulan" or "matahari terbit": Sun and
  Moon

## Privacy

Your place never leaves your computer: the distance to the ISS, sunrise and sunset are
worked out here. Space connects only when you use it, except while you have a launch
reminder: then it refreshes the launch list at most once an hour.

- Where is the ISS? asks `api.wheretheiss.at` for the station's position, then sends that
  position (the station's, not yours) back to the same service to learn which country it
  is over.
- The launch list comes from The Space Devs (`ll.thespacedevs.com`). Your launch reminders
  stay on your computer.
- Searching for a city sends the text you typed, and your Hariku language, to Open-Meteo's
  city search (`geocoding-api.open-meteo.com`).
