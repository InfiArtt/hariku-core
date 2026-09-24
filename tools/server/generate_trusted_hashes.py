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
generate_trusted_hashes.py — Hariku Extension Trust Registry Generator
=======================================================================

Run this script on the server every time you upload a new .hrk to the store.
It scans the given folder, computes the SHA256 of every .hrk file, then
generates two output files:

  1. trusted_extensions.json  — the file served to Hariku clients
  2. trusted_extensions.log   — a summary for your reference (ID, hash, size)

Usage:
  python generate_trusted_hashes.py [hrk_folder] [output_dir]

Example:
  python generate_trusted_hashes.py ./extensions/store ./public/security

If no arguments are given, the defaults are:
  - hrk_folder : ./hrk_store
  - output_dir : ./security_output

Format of the generated trusted_extensions.json:
  {
    "generated_at": "2026-06-20T07:00:00Z",
    "total": 3,
    "trusted": [
      "abc123...",
      "def456...",
      "ghi789..."
    ]
  }

Publish this file to GitHub Pages at the path used by core.endpoints:
  GET https://<owner>.github.io/<repo>/security/trusted_extensions.json
"""

import os
import sys
import json
import hashlib
import datetime
import argparse


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# IDs of extensions considered "official" Hariku — must ALWAYS MATCH
# _OFFICIAL_EXTENSION_IDS in hariku2/core/extension_manager.py
#
# HOW TO ADD A NEW OFFICIAL EXTENSION:
#   1. Add its ID here (folder name / .hrk name without extension).
#   2. Add the same ID to _OFFICIAL_EXTENSION_IDS in core/extension_manager.py.
#   3. Re-run this script and upload trusted_extensions.json to the server.
#   The [Official] badge then appears automatically in the client.
OFFICIAL_EXTENSION_IDS = {
    "developer_toolkit",
    "ghost_taskbar",
    "key_notifier",
    "ambience",
    "project_system",
    "window_teleporter",
    "markdown_reader",
    "lumina",
    "account_manager",
    "world_clock",
    "routines",
    "gcal_integration",
    "filter",
    "quick_expand",
    "weather",
    "briefing",
    "finance",
    "flight_radar",
    "clipboard_history",
    "sound_themes",
    "earthquake",
    "marine",
    "air_quality",
    "space",
    "edge_voices",
    "sleep_tracker",
    "piper_voices",
    # add new official extension IDs here
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_sha256(filepath: str) -> str:
    """Compute the SHA256 hex digest of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest().lower()


def ext_id_from_filename(filename: str) -> str:
    """Derive ext_id from a filename: 'my_extension.hrk' → 'my_extension'."""
    return os.path.splitext(filename)[0]


def format_size(size_bytes: int) -> str:
    """Format a file size into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def scan_hrk_folder(folder: str) -> list[dict]:
    """
    Scan the folder and collect info for every .hrk found.
    Returns a list of dicts with keys: filename, ext_id, path, sha256, size, is_official
    """
    if not os.path.isdir(folder):
        print(f"[ERROR] Folder tidak ditemukan: {folder}")
        sys.exit(1)

    results = []
    hrk_files = sorted(
        f for f in os.listdir(folder) if f.lower().endswith(".hrk")
    )

    if not hrk_files:
        print(f"[WARNING] Tidak ada file .hrk ditemukan di: {folder}")
        return results

    print(f"\nMemindai {len(hrk_files)} file .hrk di: {os.path.abspath(folder)}\n")
    print(f"{'File':<35} {'ID':<25} {'Official':<10} {'Ukuran':<12} SHA256")
    print("-" * 120)

    for filename in hrk_files:
        filepath = os.path.join(folder, filename)
        ext_id   = ext_id_from_filename(filename)
        size     = os.path.getsize(filepath)
        sha256   = compute_sha256(filepath)
        official = ext_id in OFFICIAL_EXTENSION_IDS

        results.append({
            "filename":    filename,
            "ext_id":      ext_id,
            "path":        filepath,
            "sha256":      sha256,
            "size":        size,
            "is_official": official,
        })

        tag = "✓ YES" if official else "  no"
        print(f"{filename:<35} {ext_id:<25} {tag:<10} {format_size(size):<12} {sha256}")

    return results


def generate_trusted_json(results: list[dict], output_dir: str):
    """Write trusted_extensions.json to output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "trusted_extensions.json")

    payload = {
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(results),
        "trusted": [r["sha256"] for r in results],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[OK] trusted_extensions.json ditulis ke: {output_path}")
    return output_path


def generate_log(results: list[dict], output_dir: str):
    """Write a developer reference log to output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, "trusted_extensions.log")
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "=" * 90,
        f"  Hariku Trusted Extension Hash Log",
        f"  Generated: {now}",
        f"  Total: {len(results)} extension(s)",
        "=" * 90,
        "",
    ]

    official_list  = [r for r in results if r["is_official"]]
    community_list = [r for r in results if not r["is_official"]]

    if official_list:
        lines.append("--- Official Extensions ---")
        for r in official_list:
            lines.append(f"  ID       : {r['ext_id']}")
            lines.append(f"  File     : {r['filename']}")
            lines.append(f"  Size     : {format_size(r['size'])}")
            lines.append(f"  SHA256   : {r['sha256']}")
            lines.append("")

    if community_list:
        lines.append("--- Community / Third-Party Extensions ---")
        for r in community_list:
            lines.append(f"  ID       : {r['ext_id']}")
            lines.append(f"  File     : {r['filename']}")
            lines.append(f"  Size     : {format_size(r['size'])}")
            lines.append(f"  SHA256   : {r['sha256']}")
            lines.append("")

    not_official = [r["ext_id"] for r in results if not r["is_official"]]
    if not_official:
        lines.append("-" * 90)
        lines.append("NOTE: Ekstensi berikut ada di folder tapi TIDAK ada di OFFICIAL_EXTENSION_IDS:")
        for eid in not_official:
            lines.append(f"  - {eid}")
        lines.append("Jika ini ekstensi official kamu, tambahkan ID-nya ke OFFICIAL_EXTENSION_IDS")
        lines.append("di script ini DAN di core/extension_manager.py _OFFICIAL_EXTENSION_IDS.")
        lines.append("")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[OK] Log referensi ditulis ke     : {log_path}")
    return log_path


def print_server_reminder(output_dir: str):
    """Remind the developer of the required deploy steps."""
    json_path = os.path.join(output_dir, "trusted_extensions.json")
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         LANGKAH SELANJUTNYA                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  1. Commit file ini ke repo GitHub Pages kamu:                             ║
║     {json_path:<60}  ║
║                                                                              ║
║  2. Pastikan file tersebut dapat diakses di URL:                            ║
║     https://<owner>.github.io/<repo>/security/trusted_extensions.json       ║
║                                                                              ║
║  3. Jika ada ekstensi "official" baru yang belum masuk list,                ║
║     update OFFICIAL_EXTENSION_IDS di:                                       ║
║       - tools/server/generate_trusted_hashes.py  (script ini)              ║
║       - hariku2/core/extension_manager.py         (_OFFICIAL_EXTENSION_IDS) ║
║                                                                              ║
║  4. Untuk installer SHA256 (update checker), jalankan:                      ║
║     python generate_trusted_hashes.py --installer path/ke/latestV2.exe      ║
║     lalu tambahkan nilai "sha256" ke version.json di server.                ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")


def compute_installer_sha256(installer_path: str):
    """Special mode: compute the SHA256 of a single installer file for version.json."""
    if not os.path.isfile(installer_path):
        print(f"[ERROR] File tidak ditemukan: {installer_path}")
        sys.exit(1)

    size   = os.path.getsize(installer_path)
    sha256 = compute_sha256(installer_path)

    print(f"\n  File    : {installer_path}")
    print(f"  Size    : {format_size(size)}")
    print(f"  SHA256  : {sha256}")
    print(f"""
Tambahkan field berikut ke version.json di GitHub Pages kamu:

  {{
    "latest_version": "2.1.0",
    "sha256": "{sha256}",
    "download_url": "https://github.com/<owner>/<repo>/releases/latest/download/HarikuSetup.exe",
    ...
  }}
""")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate Hariku trusted extension hash registry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python generate_trusted_hashes.py
  python generate_trusted_hashes.py ./my_extensions ./output
  python generate_trusted_hashes.py --installer ./release/latestV2.exe
        """
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default="../hrk_store",
        help="Folder yang berisi file .hrk (default: ./hrk_store)"
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="./security_output",
        help="Folder output untuk JSON dan log (default: ./security_output)"
    )
    parser.add_argument(
        "--installer",
        metavar="PATH",
        help="Mode khusus: hitung SHA256 satu file installer .exe untuk version.json"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  Hariku — Trusted Extension Hash Generator")
    print("=" * 60)

    # Installer SHA256 mode.
    if args.installer:
        compute_installer_sha256(args.installer)
        return

    # Folder scan mode.
    results = scan_hrk_folder(args.folder)

    if not results:
        print("\nTidak ada file yang diproses. Selesai.")
        return

    generate_trusted_json(results, args.output)
    generate_log(results, args.output)
    print_server_reminder(args.output)

    print(f"\nSelesai. {len(results)} ekstensi diproses.\n")


if __name__ == "__main__":
    main()
