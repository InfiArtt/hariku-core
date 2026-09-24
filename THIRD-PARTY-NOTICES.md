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

## Bundled/vendored code

- **comtypes**: vendored under `extensions/window_teleporter/lib/comtypes/`.
  License: MIT. Used for COM automation on Windows.
- **pyvda**: vendored under `extensions/window_teleporter/lib/pyvda/`.
  License: MIT. Used for Windows virtual-desktop control.

## Protocol references

- **edge-tts** (https://github.com/rany2/edge-tts, LGPL-3.0): the Edge Voices
  extension (`extensions/edge_voices/`) is an independent implementation of the
  Microsoft Edge "Read Aloud" speech protocol, written from the details edge-tts
  documents (the endpoint, trusted client token, Sec-MS-GEC token and message
  formats). No edge-tts code is included; it is credited here for the research.

## Downloaded on request (not bundled)

- **Piper** (https://github.com/rhasspy/piper, MIT): the Piper Voices extension
  (`extensions/piper_voices/`) downloads the official Windows build of Piper
  (`piper_windows_amd64.zip`, release 2023.11.14-2, which also contains
  espeak-ng and ONNX Runtime under their own licenses) from GitHub when the
  user downloads their first voice, and checks it against a SHA-256 pinned in
  the extension. It runs `piper.exe` as a separate program. Neither Piper nor
  any voice is included in Hariku or its installer.
- **Piper voices** (https://huggingface.co/rhasspy/piper-voices): each voice
  has its own license, which depends on the dataset it was trained on. The
  extension shows each voice's model card (dataset and license) and its size
  before the user chooses to download it; some cards, such as the Indonesian
  `id_ID-news_tts-medium`, don't name a clear license, and the extension says so.

- **whisper.cpp** (https://github.com/ggml-org/whisper.cpp, MIT): the Voice
  Control extension (`extensions/voice_control/`) downloads the official
  Windows x64 build (`whisper-bin-x64.zip`, release b5130; the libraries in it,
  such as ggml, come under their own licenses) from GitHub when the user presses
  Download, and checks it against a SHA-256 pinned in the extension. It runs
  `whisper-server.exe` as a separate program that answers on 127.0.0.1 only.
  whisper.cpp is not included in Hariku or its installer.
- **Whisper speech models** (OpenAI, https://github.com/openai/whisper, MIT),
  in whisper.cpp's format from https://huggingface.co/ggerganov/whisper.cpp:
  `ggml-tiny.bin`, `ggml-base.bin` and `ggml-small.bin`, each downloaded only
  when the user chooses it and checked against a SHA-256 pinned in the
  extension. No model is included in Hariku or its installer.

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
