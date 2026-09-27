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
build_sdk.py - Hariku V2 Developer SDK Packager
===============================================
This script bundles the files third-party developers need to start building
extensions for Hariku V2: the VS Code configs, the template extension, the
packager, the API documentation and the store submission guidelines.

Output: Hariku_V2_Developer_SDK.zip (in the project root, or --output PATH)

The published SDK now lives at https://github.com/InfiArtt/hariku-sdk. A
workflow there syncs it from this repository every day: DEVELOPERS.md,
tools/packager.py, .vscode/ and docs/en/extension_store/ (as store_guidelines/)
from the latest release tag, and template_extension/ from main. The SDK adds
examples and a checker of its own, and publishes Hariku_V2_Developer_SDK.zip
as a release for each Hariku release. This script stays for local builds.

The store's internal review guidelines (review_guidelines.txt) are never
shipped, here or in the SDK repository.
"""

import argparse
import os
import zipfile

SDK_REPOSITORY = "https://github.com/InfiArtt/hariku-sdk"

# Files and directories to include in the SDK ZIP.
# Format: (Source Path relative to project root, Destination Path inside the ZIP)
SDK_CONTENTS = [
    ("DEVELOPERS.md", "DEVELOPERS.md"),
    (".vscode", ".vscode"),
    ("template_extension", "template_extension"),
    ("tools/packager.py", "tools/packager.py"),
    ("docs/en/extension_store", "store_guidelines"),
]

# Internal documents that developers don't get: the store's review guidelines
# are for reviewers only (the July 2026 SDK announcement promised this).
EXCLUDED_FILES = {"review_guidelines.txt"}
EXCLUDED_DIRS = {"__pycache__", ".git"}


def _files(project_root):
    """(source file, path inside the ZIP) of everything the SDK contains."""
    for src_rel, dst_rel in SDK_CONTENTS:
        src_path = os.path.join(project_root, src_rel)
        if not os.path.exists(src_path):
            print(f"[WARNING] Source not found: {src_rel}")
            continue
        if os.path.isfile(src_path):
            if os.path.basename(src_path) not in EXCLUDED_FILES:
                yield src_path, dst_rel
            continue
        for root, dirs, files in os.walk(src_path):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
            for file in sorted(files):
                if file in EXCLUDED_FILES or file.endswith((".pyc", ".pyo")):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, src_path)
                yield file_path, os.path.join(dst_rel, rel_path).replace(os.sep, "/")


def build_sdk(output_filename=None, project_root=None):
    """Build the SDK ZIP and return its path."""
    project_root = project_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_filename = output_filename or os.path.join(project_root, "Hariku_V2_Developer_SDK.zip")

    print("=" * 60)
    print("  Building Hariku V2 Developer SDK")
    print(f"  (published SDK: {SDK_REPOSITORY})")
    print("=" * 60)

    # Remove existing zip if it exists
    if os.path.exists(output_filename):
        os.remove(output_filename)

    packed_files = 0
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path, zip_dst_path in _files(project_root):
            zf.write(file_path, zip_dst_path)
            print(f"[ADD] {zip_dst_path}")
            packed_files += 1

    # The review guidelines must never leave the repository.
    with zipfile.ZipFile(output_filename) as zf:
        leaked = [n for n in zf.namelist() if os.path.basename(n) in EXCLUDED_FILES]
    if leaked:
        os.remove(output_filename)
        raise RuntimeError(f"Internal files ended up in the SDK: {leaked}")

    size_bytes = os.path.getsize(output_filename)
    size_kb = size_bytes / 1024

    print("\n" + "=" * 60)
    print(f"[SUCCESS] SDK successfully bundled!")
    print(f"Output: {output_filename}")
    print(f"Files:  {packed_files}")
    print(f"Size:   {size_kb:.1f} KB")
    print("=" * 60)
    return output_filename


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the Hariku V2 Developer SDK ZIP locally.")
    parser.add_argument("--output", "-o", help="Where to write the ZIP "
                        "(default: Hariku_V2_Developer_SDK.zip in the project root).")
    args = parser.parse_args(argv)
    build_sdk(args.output)


if __name__ == "__main__":
    main()
