#!/usr/bin/env python3
# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The hunt's seasons: from an authoring file (answers in plain text) to the
file the server reads (answers only as keyed hashes). Standard library only.

    python orbit_hunt_tool.py build private/season1.authoring.json private/season1.hunt.json
    python orbit_hunt_tool.py check private/season1.hunt.json
    python orbit_hunt_tool.py try private/season1.hunt.json 2 "my answer"
    python orbit_hunt_tool.py template

Keep both files out of the repository (servers/orbit/private/ is ignored by
git): the riddles, where their clues are and what unlocks them would spoil
the hunt, and the repository is public. Copy only the built file to the
server (~/orbit/private/) and point config.json's "hunt" at it.

An authoring file is the season with, for each stage, "accept": every
answer it takes (both languages, other spellings); "build" replaces them with
"answers", HMAC-SHA256 hashes under a new random "salt" (or the authoring
file's own). Answers are compared lower case, without accents, spaces or
punctuation: "Time Capsule Room" and "timecapsuleroom" are the same.

{
  "season": 1,
  "title": {"en": "...", "id": "..."},        the season's name
  "intro": {"en": "...", "id": "..."},        said before the first riddle
  "prize": {"first": 5000, "others": [2500, 1000], "rest": 250,
            "title": "title_chord_keeper"},   credits by place; a thing for the first
  "rival": {"name": {"en": ..., "id": ...}, "hours": 48},
  "stages": [
    {"id": "s1",
     "riddle": {"en": ..., "id": ...},        what "hunt" says
     "found": {"en": ..., "id": ...},         said when it's solved
     "accept": ["answer", "jawaban"],         (authoring only)
     "clues": [{"room": "archive", "text": {"en": ..., "id": ...},
                "requires": {"thing": "scanner", "worn": "headlamp", "hours": [22, 4]},
                "tones": [1, 3, 2, 4]}],      "requires" and "tones" are optional
     "hints": [{"en": ..., "id": ...}]}       released one at a time by admins
  ]
}
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orbit_hunt  # noqa: E402
import orbit_world  # noqa: E402

TEMPLATE = {
    "season": 2,
    "title": {"en": "The Lost Chord, season 2", "id": "Nada yang Hilang, musim 2"},
    "intro": {"en": "Write the season's story here.", "id": "Tulis cerita musimnya di sini."},
    "prize": {"first": 5000, "others": [2500, 1000], "rest": 250, "title": "title_chord_keeper"},
    "rival": {"name": {"en": "Meridian Grey", "id": "Meridian Kelabu"}, "hours": 48},
    "stages": [{"id": "s1", "riddle": {"en": "The riddle.", "id": "Teka-tekinya."},
                "found": {"en": "Found!", "id": "Ketemu!"}, "accept": ["answer", "jawaban"],
                "clues": [{"room": "archive", "text": {"en": "A clue.", "id": "Sebuah petunjuk."}}],
                "hints": [{"en": "A hint.", "id": "Sebuah petunjuk tambahan."}]}],
}


def _world():
    return orbit_world.World.load()


def main(argv=None):
    try:
        return _run(list(sys.argv[1:] if argv is None else argv))
    except (OSError, ValueError, IndexError) as e:      # HuntError is a ValueError
        print(f"Not done: {e}", file=sys.stderr)
        return 1


def _run(args):
    command = args[0] if args else ""
    if command == "build" and len(args) == 3:
        with open(args[1], encoding="utf-8") as f:
            authoring = json.load(f)
        hunt = orbit_hunt.build(authoring, _world())
        with open(args[2], "w", encoding="utf-8", newline="\n") as f:
            json.dump(hunt, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"Built season {hunt['season']}: {len(hunt['stages'])} stages -> {args[2]}")
        return 0
    if command == "check" and len(args) == 2:
        hunt = orbit_hunt.load(args[1], _world())
        print(f"Season {hunt['season']}: {len(hunt['stages'])} stages, fine.")
        return 0
    if command == "try" and len(args) == 4:
        hunt = orbit_hunt.load(args[1], _world())
        stage = hunt["stages"][int(args[2]) - 1]
        tried = orbit_hunt.answer_hash(hunt["salt"], hunt["season"], stage["id"], args[3])
        right = tried in stage["answers"]
        print("right" if right else "wrong")
        return 0 if right else 1
    if command == "template":
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
