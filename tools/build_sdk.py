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
This script bundles all the necessary files for third-party developers
to start building extensions for Hariku V2, including VS Code configs,
the template extension, API documentation, and store submission guidelines.

Output: Hariku_V2_Developer_SDK.zip
"""

import os
import zipfile
import shutil

# Files and directories to include in the SDK ZIP.
# Format: (Source Path relative to project root, Destination Path inside the ZIP)
SDK_CONTENTS = [
    ("DEVELOPERS.md", "DEVELOPERS.md"),
    (".vscode", ".vscode"),
    ("template_extension", "template_extension"),
    ("docs/en/extension_store", "store_guidelines"),
]

def build_sdk():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_filename = os.path.join(project_root, "Hariku_V2_Developer_SDK.zip")
    
    print("=" * 60)
    print("  Building Hariku V2 Developer SDK")
    print("=" * 60)
    
    # Remove existing zip if it exists
    if os.path.exists(output_filename):
        os.remove(output_filename)
        
    packed_files = 0
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        for src_rel, dst_rel in SDK_CONTENTS:
            src_path = os.path.join(project_root, src_rel)
            
            if not os.path.exists(src_path):
                print(f"[WARNING] Source not found: {src_rel}")
                continue
                
            if os.path.isfile(src_path):
                zf.write(src_path, dst_rel)
                print(f"[ADD] {dst_rel}")
                packed_files += 1
            elif os.path.isdir(src_path):
                for root, dirs, files in os.walk(src_path):
                    # Skip __pycache__ etc if present
                    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
                    for file in files:
                        # Skip internal documents that developers shouldn't see
                        if file == "review_guidelines.txt":
                            continue
                            
                        file_path = os.path.join(root, file)
                        # Calculate relative path inside the destination folder
                        rel_path = os.path.relpath(file_path, src_path)
                        zip_dst_path = os.path.join(dst_rel, rel_path)
                        zf.write(file_path, zip_dst_path)
                        print(f"[ADD] {zip_dst_path}")
                        packed_files += 1
                        
    size_bytes = os.path.getsize(output_filename)
    size_kb = size_bytes / 1024
    
    print("\n" + "=" * 60)
    print(f"[SUCCESS] SDK successfully bundled!")
    print(f"Output: {output_filename}")
    print(f"Files:  {packed_files}")
    print(f"Size:   {size_kb:.1f} KB")
    print("=" * 60)

if __name__ == "__main__":
    build_sdk()
