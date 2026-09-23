# Hariku V2

Hariku ("My Day") is a keyboard-driven calendar and productivity app for Windows,
built for blind and low-vision people who use a screen reader. It speaks through
whatever screen reader is running (NVDA, JAWS, and others) using
Tolk, and falls back to Windows SAPI when none is present. The core stays small,
and almost everything else is an extension.

## What it does

- **Screen-reader first.** Speech is queued so it never talks over itself, with
  sound cues, full keyboard navigation, a Braille-output toggle, and an F1
  cheat-sheet for the shortcuts.
- **Calendar and reminders.** Move around dates quickly and set reminders that
  repeat daily, weekly, monthly, or yearly. Anything you missed while the app was
  closed is caught up the next time you open it.
- **Extensions.** A plugin system with an in-app store. The bundled ones include
  World Clock, a Markdown reader, and Routines, an automation builder modeled on
  iOS Shortcuts that pairs a trigger with actions and can pass variables between
  them.
- **Low-vision options.** Scale the interface font and switch to a high-contrast
  theme.
- **Hard to break.** Saves are atomic, a crash handler catches failures,
  extensions load only after a SHA-256 trust check and your consent, and the
  auto-updater verifies what it downloads.

## Running from source

Requires Windows and Python 3.10.

```bat
py -3.10 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python hariku.py
```

Run the tests with `python -m pytest`.

## Building the installer

Hariku compiles with Nuitka (the exact command is in `how-to.txt`) and packages
with Inno Setup (`file.iss`). GitHub Actions builds each release from a version
tag (`.github/workflows/release.yml`) and publishes the installer alongside an
`update/version.json` manifest.

## Code signing policy

Windows releases are built and published only by the GitHub Actions release
workflow in this repository. Builds made on a personal machine are never signed
or published. A release contains the Hariku executables and the
`HarikuV2-Setup.exe` installer, all built from this source.

Releases are currently unsigned. We are working on free code signing through
the SignPath Foundation's open source program.

Team roles:

- Committers and reviewers: Rafli ([@raf-li](https://github.com/raf-li))
- Approvers: Rafli ([@raf-li](https://github.com/raf-li))

## Privacy

Hariku collects no analytics or telemetry. [PRIVACY.md](PRIVACY.md) lists every
case where it connects to the internet.

## Writing extensions

Start with [DEVELOPERS.md](DEVELOPERS.md) for the extension API, and
`template_extension/` for a minimal skeleton. An extension talks to Hariku only
through the documented `core.*` API and its manifest.

## License

Hariku is free software under the GNU General Public License v3.0 or later, with
the Hariku Extension Exception ([LICENSE-EXCEPTION](LICENSE-EXCEPTION)). The core
stays copyleft, but a third-party extension that uses only the documented
extension API can be released under any license, including a proprietary or
commercial one.

- Core and official extensions: `GPL-3.0-or-later` (see [LICENSE](LICENSE)).
- Third-party extensions: your choice, under the extension exception.
- Bundled third-party libraries: see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Contributing

Issues and pull requests are welcome. When you contribute to Hariku's own source,
you agree to license those contributions under `GPL-3.0-or-later`.
