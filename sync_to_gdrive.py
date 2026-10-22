#!/usr/bin/env python3
import os
import subprocess
import json
import sys

GDRIVE_BIN = "/Users/lucassachse/.gemini/antigravity/bin/gdrive"
TARGET_FOLDER_ID = "1uLjaxlIPB_HQJZJ1cjpdWaBz_SRF5Mex"  # "Fantasy Football Dashboard" inside "Data Analytics Projects"
PROJECT_DIR = "/Users/lucassachse/Library/Mobile Documents/com~apple~CloudDocs/Gemini Projects/Fantasy Dashboard/Fantasy-Football-Dashboard"

# Files and patterns to ignore
IGNORED_PREFIXES = ('.', '~', '__pycache__')
IGNORED_FILES = {'uv.lock'}
IGNORED_DIRS = {'.git', '.venv', '.agents', '~', '__pycache__'}

def get_remote_files(folder_id):
    """Retrieve existing files in Google Drive folder."""
    cmd = [GDRIVE_BIN, "readonly", "ls", "--json", folder_id]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️ Error fetching files from Google Drive: {result.stderr}")
        return {}
    try:
        data = json.loads(result.stdout)
        return {item["name"]: item["id"] for item in data}
    except Exception as e:
        print(f"⚠️ Error parsing JSON: {e}")
        return {}

def get_local_files():
    """List root project files to synchronize."""
    files_to_sync = []
    for entry in os.scandir(PROJECT_DIR):
        if entry.is_file():
            name = entry.name
            if name.startswith(IGNORED_PREFIXES) or name in IGNORED_FILES:
                continue
            files_to_sync.append((name, entry.path))
    return files_to_sync

def sync():
    print("=" * 60)
    print("☁️ GOOGLE DRIVE DAILY BACKUP PIPELINE")
    print("=" * 60)
    print(f"📂 Source: {PROJECT_DIR}")
    print(f"🎯 Target GDrive Folder ID: {TARGET_FOLDER_ID}")
    
    remote_files = get_remote_files(TARGET_FOLDER_ID)
    local_files = get_local_files()

    print(f"📄 Found {len(local_files)} local project files to sync.")
    print(f"☁️ Found {len(remote_files)} existing files in Google Drive folder.\n")

    uploaded = 0
    updated = 0

    for filename, filepath in sorted(local_files):
        if filename in remote_files:
            file_id = remote_files[filename]
            print(f"🔄 Updating: {filename}...")
            res = subprocess.run([GDRIVE_BIN, "mutate", "update", file_id, filepath], capture_output=True, text=True)
            if res.returncode == 0:
                updated += 1
            else:
                print(f"   ⚠️ Update failed for {filename}: {res.stderr.strip()}")
        else:
            print(f"⬆️ Uploading new file: {filename}...")
            res = subprocess.run([GDRIVE_BIN, "mutate", "upload", filepath, "--parent", TARGET_FOLDER_ID], capture_output=True, text=True)
            if res.returncode == 0:
                uploaded += 1
            else:
                print(f"   ⚠️ Upload failed for {filename}: {res.stderr.strip()}")

    print("\n" + "=" * 60)
    print(f"✅ Sync complete! Uploaded {uploaded} new files, updated {updated} existing files.")
    print("=" * 60)

if __name__ == "__main__":
    sync()
