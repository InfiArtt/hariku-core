# Privacy

Hariku does not collect analytics or telemetry. Your calendar, reminders,
routines, settings, and extension data stay on your computer, in
`%APPDATA%\Hariku2`.

This page lists every case where Hariku and the extensions bundled with it
connect to the internet. It does not cover extensions you install from the
store or from other sources, which can make their own connections.

## Automatic connections

When Hariku starts, it downloads a few small files from GitHub Pages
(`infiartt.github.io`):

- `version.json`, to see whether a newer version of Hariku exists. If one does,
  Hariku shows a dialog before downloading anything.
- The extension store listing, to see whether your extensions have updates. You
  can stop this by setting extension updates to "Do nothing" in Settings.
- The list of trusted extension hashes, which Hariku uses to check extensions
  from the store before loading them.

If the Calendar Integration extension is enabled, it also downloads holiday
data for the selected country (Indonesia by default) from GitHub Pages, and it
fetches any calendar (ICS) links you add from the servers that host them.

These requests carry only what every web request carries, such as your IP
address and a Hariku user agent. They contain no identifier, no account
details, and none of your data. GitHub's handling of them is covered by the
[GitHub General Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).

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

## Accounts and the Lounge

The Account Manager and Hariku Lounge extensions connect to infiartt.com only
after you sign in. They send your sign-in details and the chat messages you
post. The [infiartt.com privacy policy](https://infiartt.com/privacy) covers
that data.
