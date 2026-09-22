# Hariku V2 — Extension Packager
# ============================================================
# Packages an extension folder into a distributable .hrk file.
#
# Usage:
#   python tools/packager.py <folder_path> [--output <dir>]
#
# Examples:
#   python tools/packager.py extensions/my_extension
#   python tools/packager.py template_extension --output dist
#   python tools/packager.py  (interactive mode, will ask for folder)
# ============================================================

import os
import sys
import json
import zipfile
import argparse
import shutil

# Files and folders that should NEVER be included in the .hrk
IGNORED_NAMES = {
    "__pycache__",
    ".git",
    ".vscode",
    ".idea",
    ".DS_Store",
    "Thumbs.db",
    ".hrk_mtime",
}

IGNORED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".log",
}


def validate_manifest(folder_path):
    """Validate that the manifest.json exists and has all required fields."""
    manifest_path = os.path.join(folder_path, "manifest.json")
    
    if not os.path.exists(manifest_path):
        print(f"  [ERROR] manifest.json not found in: {folder_path}")
        return None
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  [ERROR] manifest.json is not valid JSON: {e}")
        return None
    
    required_fields = ["name", "version", "description", "main", "author", "language", "minimum_core_version"]
    missing = [f for f in required_fields if f not in manifest]
    
    if missing:
        print(f"  [ERROR] manifest.json is missing required fields: {missing}")
        print(f"  Required fields: {required_fields}")
        return None
    
    # Check that the entry point file exists
    main_file = os.path.join(folder_path, manifest["main"])
    if not os.path.exists(main_file):
        print(f"  [ERROR] Entry point file '{manifest['main']}' not found in the extension folder.")
        return None
    
    return manifest


def should_include(name):
    """Check if a file/folder should be included in the .hrk."""
    if name in IGNORED_NAMES:
        return False
    _, ext = os.path.splitext(name)
    if ext.lower() in IGNORED_EXTENSIONS:
        return False
    return True


def count_files(folder_path):
    """Count total files that will be packaged."""
    total = 0
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if should_include(d)]
        for f in files:
            if should_include(f):
                total += 1
    return total


def package_extension(folder_path, output_dir=None):
    """Package the extension folder into a .hrk file."""
    folder_path = os.path.abspath(folder_path)
    
    if not os.path.isdir(folder_path):
        print(f"  [ERROR] '{folder_path}' is not a valid directory.")
        return False
    
    # Validate manifest
    print(f"\n  Validating manifest.json...")
    manifest = validate_manifest(folder_path)
    if manifest is None:
        return False
    
    ext_name = manifest["name"]
    ext_version = manifest["version"]
    ext_id = os.path.basename(folder_path)
    
    print(f"  [OK] Extension: {ext_name} v{ext_version}")
    print(f"  [OK] Author: {manifest['author']}")
    print(f"  [OK] Min Core: {manifest['minimum_core_version']}")
    
    # Determine output path
    if output_dir is None:
        output_dir = os.path.dirname(folder_path)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    hrk_filename = f"{ext_id}.hrk"
    hrk_path = os.path.join(output_dir, hrk_filename)
    
    # Clean __pycache__ before packaging
    for root, dirs, files in os.walk(folder_path):
        for d in dirs:
            if d == "__pycache__":
                cache_path = os.path.join(root, d)
                shutil.rmtree(cache_path)
                print(f"  [CLEAN] Removed: {cache_path}")
    
    # Package
    file_count = count_files(folder_path)
    print(f"\n  Packaging {file_count} files into {hrk_filename}...")
    
    packed = 0
    with zipfile.ZipFile(hrk_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(folder_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if should_include(d)]
            
            for filename in files:
                if not should_include(filename):
                    continue
                
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, folder_path)
                zf.write(file_path, arcname)
                packed += 1
    
    # Report
    hrk_size = os.path.getsize(hrk_path)
    if hrk_size < 1024:
        size_str = f"{hrk_size} bytes"
    elif hrk_size < 1024 * 1024:
        size_str = f"{hrk_size / 1024:.1f} KB"
    else:
        size_str = f"{hrk_size / (1024 * 1024):.2f} MB"
    
    print(f"\n  ============================================")
    print(f"  [SUCCESS] Packaged successfully!")
    print(f"  File: {hrk_path}")
    print(f"  Size: {size_str}")
    print(f"  Files packed: {packed}")
    print(f"  ============================================\n")
    return True


def interactive_mode():
    """Run the packager in interactive mode."""
    print("\n  ============================================")
    print("  Hariku V2 Extension Packager")
    print("  ============================================\n")
    
    folder = input("  Enter extension folder path: ").strip()
    if not folder:
        print("  [ERROR] No folder specified.")
        return False
    
    # Remove surrounding quotes if present
    folder = folder.strip('"').strip("'")
    
    if not os.path.isdir(folder):
        print(f"  [ERROR] '{folder}' is not a valid directory.")
        return False
    
    output = input("  Output directory (press Enter for same as source): ").strip()
    output = output.strip('"').strip("'") if output else None
    
    return package_extension(folder, output)


def main():
    parser = argparse.ArgumentParser(
        description="Hariku V2 Extension Packager — Package extension folders into .hrk files."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help="Path to the extension folder to package."
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory for the .hrk file. Defaults to the parent of the extension folder."
    )
    
    args = parser.parse_args()
    
    if args.folder is None:
        # Interactive mode
        success = interactive_mode()
    else:
        success = package_extension(args.folder, args.output)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
