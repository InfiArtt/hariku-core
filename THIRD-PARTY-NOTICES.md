# Third-Party Notices

Hariku bundles or depends on the third-party components below. Each remains under
its own license; those licenses are compatible with Hariku's GPL-3.0-or-later
distribution. This is a convenience summary; the authoritative terms ship with
each component.

## Python dependencies (see `requirements.txt`)

| Component | Purpose | License (typical) |
|---|---|---|
| wxPython | GUI toolkit | wxWindows Library License (LGPL-style, GPL-compatible) |
| cytolk / Tolk | Screen-reader output abstraction | LGPL-3.0 / MIT |
| cryptography | Encryption primitives | Apache-2.0 / BSD-3-Clause |
| pyperclip | Clipboard access | BSD-3-Clause |
| tzdata | IANA time-zone database | Apache-2.0 / public domain data |
| packaging | Version parsing | Apache-2.0 / BSD-2-Clause |
| Nuitka | Build-time compiler (not shipped in the app) | Apache-2.0 |

## The official extensions

The official extensions (World Clock, Orbit, Voice Control, Piper Voices and
the others) are not part of this repository or of Hariku's installer: they are
installed separately, from the Extension Store, and maintained by InfiArtt in a
repository of their own. The third-party code, media, programs and models they
bundle or download are listed in that repository's notices.

## Native components

- **nvdaControllerClient64.dll**: the NVDA Controller Client from NV Access,
  which lets applications send speech and braille to NVDA. License: LGPL-2.1.
- **Tolk** (embedded via cytolk) routes output to whichever screen reader is
  running (NVDA, JAWS, ZoomText, and others), or to Windows SAPI when none is.
  License: LGPL-3.0.

Release builds do not include `SAAPI64.dll`, the System Access client that
comes with the cytolk package, because it is not distributed under an open
source license. System Access users hear Hariku through SAPI instead.

---

If you redistribute Hariku, keep this file and the bundled license texts intact.
If any entry here is inaccurate for the exact version you ship, defer to the
license file inside that component.
