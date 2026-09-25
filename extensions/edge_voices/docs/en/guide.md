# Edge Voices

Edge Voices adds the Microsoft Edge online neural voices to Hariku Voice, with voices for
many languages, including the Indonesian voices Ardi and Gadis. They need the internet:
the text being read is sent to Microsoft.

## Getting started

Edge Voices has no page of its own. You choose its voices in Preferences, Hariku Voice:

1. Open Preferences, Hariku Voice.
2. Tick what Hariku Voice should read, such as "Read reminders with Hariku Voice when
   they are due" or "Read Aruna's answers with Hariku Voice".
3. In "Source", choose "Microsoft Edge neural voices (online)".
4. Choose a "Language", a "Gender" if you like, then a "Voice", such as Gadis or Ardi
   for Indonesian.
5. Set the "Rate (-10 to 10)" and "Volume (0 to 100)", and press Test to hear the
   voice.
6. Press OK.

The list of voices comes from Microsoft, so it takes a moment to fill the first time.

## When the service doesn't answer

The Edge speech service is meant for the Edge browser, and it may stop working at any
time. So choose a backup in "If this voice isn't available, use": a Windows voice, or
"The screen reader". Hariku uses it whenever an Edge voice can't speak, for example
without the internet. After three failures in a row, Hariku leaves the Edge voices
alone for ten minutes, so your announcements don't wait for them.

What an Edge voice has said is saved on your computer, up to 30 MB (the speech not used
for the longest goes first). A phrase said again, like your startup greeting, then plays
at once, even without the internet.

## Privacy

Edge Voices sends text only when an Edge voice speaks: when Edge is your Hariku Voice
source, when you press Test, or when an extension such as World Trip or Orbit speaks
with an Edge voice. It sends the text being read, with the voice and the speed, to
Microsoft's speech service (`speech.platform.bing.com`) over an encrypted connection.
That text can include your name and your reminder titles. The request carries no account
and none of your other data. The list of voices comes from the same service, at most
once a week, and has nothing about you.

"About this source", on the Hariku Voice page, says this too. The saved speech and the
voice list are in `%APPDATA%\Hariku2\voice_cache\edge`; delete that folder to remove
them.
