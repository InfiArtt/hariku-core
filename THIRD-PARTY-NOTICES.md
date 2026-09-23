# Third-Party Notices

Hariku bundles or depends on the third-party components below. Each remains under
its own license; those licenses are compatible with Hariku's GPL-3.0-or-later
distribution. This is a convenience summary — the authoritative terms ship with
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

## Bundled/vendored code

- **comtypes** — vendored under `extensions/window_teleporter/lib/comtypes/`.
  License: MIT. Used for COM automation on Windows.
- **pyvda** — vendored under `extensions/window_teleporter/lib/pyvda/`.
  License: MIT. Used for Windows virtual-desktop control.

## Native components

- **nvdaControllerClient64.dll** — the NVDA Controller Client, distributed by
  NV Access so applications can send speech/braille to NVDA.
- **SAAPI64.dll** — the System Access API client, for the System Access screen
  reader.
- **Tolk** (embedded via cytolk) routes output to whichever screen reader is
  running (NVDA, JAWS, System Access, ZoomText, SAPI, …).

These native clients are redistributed for the purpose of interoperating with
the respective screen readers.

---

If you redistribute Hariku, keep this file and the bundled license texts intact.
If any entry here is inaccurate for the exact version you ship, defer to the
license file inside that component.
