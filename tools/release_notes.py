# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The release notes of one Hariku version, taken from What's New
(docs/<language>/whats_new.txt), for the update window's "What's new" box
(version.json's release_notes and release_notes_<language>) and the GitHub
release. release.yml runs it before building, so a version without a What's
New entry in every language isn't released:

    python tools/release_notes.py 2.12.1 --json notes.json --text notes_en.txt

What's New is wrapped at about 78 columns. In a text box, which wraps by
itself, and for a screen reader going line by line, each paragraph and each
"- " item becomes one line, with a blank line between them.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# language -> (file, the word each version's header starts with)
SOURCES = {
    "en": (os.path.join("docs", "en", "whats_new.txt"), "Version"),
    "id": (os.path.join("docs", "id", "whats_new.txt"), "Versi"),
}
MAX_CHARS = 8000


def section_lines(text, version, word):
    """The lines of `version`'s entry, without its header and underline.
    Raises KeyError when there is none."""
    lines = text.splitlines()
    header = re.compile(rf"^{re.escape(word)} {re.escape(version)}(\s|$)")
    any_header = re.compile(rf"^{re.escape(word)} \d+\.\d+")
    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        raise KeyError(f"no '{word} {version}' in What's New")
    body = []
    for line in lines[start + 1:]:
        if any_header.match(line):
            break
        body.append(line)
    while body and (not body[0].strip() or set(body[0].strip()) == {"="}):
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body


def unwrap(lines):
    """Paragraphs and "- " items, each on one line, a blank line between."""
    items, current = [], None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            current = None
            continue
        if stripped.startswith("- ") or current is None:
            current = [stripped]
            items.append(current)
        else:
            current.append(stripped)
    return "\n\n".join(" ".join(item) for item in items)


def notes(version, language, root=ROOT):
    path, word = SOURCES[language]
    with open(os.path.join(root, path), encoding="utf-8") as f:
        text = f.read()
    result = unwrap(section_lines(text, version, word))
    if not result:
        raise KeyError(f"the '{word} {version}' entry of What's New is empty")
    return result[:MAX_CHARS]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("--json", help="write {language: notes} here")
    parser.add_argument("--text", help="write the English notes here (the GitHub release)")
    parser.add_argument("--root", default=ROOT)
    args = parser.parse_args(argv)
    try:
        found = {lang: notes(args.version, lang, args.root) for lang in SOURCES}
    except KeyError as e:
        print(f"Release notes: {e.args[0]}. Write the What's New entry first.", file=sys.stderr)
        return 1
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(found, f, ensure_ascii=False, indent=1)
    if args.text:
        with open(args.text, "w", encoding="utf-8") as f:
            f.write(found["en"] + "\n")
    if not args.json and not args.text:
        sys.stdout.reconfigure(encoding="utf-8")
        print(found["en"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
