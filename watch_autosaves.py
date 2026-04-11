#!/usr/bin/env python3
"""
watch_autosaves.py  —  run this on your gaming PC while playing CK3.

What it does:
  - Watches your CK3 save games folder for any autosave.ck3 that changes
  - Copies each new version into sample-saves/ in this repo, named by timestamp

Usage (from the repo root on the PC, in a terminal):
    python watch_autosaves.py

Leave it running in the background while you play.  Ctrl-C to stop.

Requirements: Python 3.6+

Configuration: edit the constants below if needed.
"""

import os
import sys
import time
import shutil
import hashlib
from pathlib import Path
from datetime import datetime


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Where CK3 stores saves on Windows (expand %USERPROFILE% automatically)
CK3_SAVE_DIR = Path(os.environ.get("USERPROFILE", "C:/Users/User")) / (
    "Documents/Paradox Interactive/Crusader Kings III/save games"
)

# Where copies land inside this repo
REPO_ROOT    = Path(__file__).parent
DEST_DIR     = REPO_ROOT / "sample-saves"

# How often to check for changes (seconds)
POLL_INTERVAL = 60

# Only watch files matching this name (CK3 autosave filename)
AUTOSAVE_NAME = "autosave.ck3"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    if not CK3_SAVE_DIR.exists():
        print(f"ERROR: CK3 save directory not found:\n  {CK3_SAVE_DIR}")
        print("Edit CK3_SAVE_DIR in this script and try again.")
        sys.exit(1)

    DEST_DIR.mkdir(exist_ok=True)
    print(f"Watching:  {CK3_SAVE_DIR}")
    print(f"Saving to: {DEST_DIR}")
    print(f"Polling every {POLL_INTERVAL}s.  Ctrl-C to stop.\n")

    # Track path → last_hash so we only act on genuine changes
    seen: dict[Path, str] = {}

    while True:
        try:
            _scan(seen)
        except Exception as exc:
            print(f"[{_now()}] Warning: scan error: {exc}")
        time.sleep(POLL_INTERVAL)


def _scan(seen: dict):
    """Walk the save directory looking for changed autosave.ck3 files."""
    for path in CK3_SAVE_DIR.rglob(AUTOSAVE_NAME):
        try:
            current_hash = _file_hash(path)
        except OSError:
            continue  # file locked or deleted mid-read

        first_seen = path not in seen
        seen[path] = current_hash

        if first_seen:
            # First encounter at startup — record hash but don't copy,
            # so we don't collect a stale save from a previous session.
            print(f"[{_now()}] Tracking: {path.parent.name}/{path.name}")
            continue

        if seen[path] != current_hash:
            seen[path] = current_hash
            _copy_snapshot(path)


def _copy_snapshot(source: Path):
    """Copy a changed autosave into sample-saves/ with a timestamp name."""
    campaign = source.parent.name  # subfolder CK3 creates per campaign
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest_name = f"{ts}_{campaign}.ck3"
    dest = DEST_DIR / dest_name

    try:
        shutil.copy2(source, dest)
        print(f"[{_now()}] Copied → sample-saves/{dest_name}")
    except OSError as e:
        print(f"[{_now()}] ERROR copying: {e}")


def _file_hash(path: Path) -> str:
    """MD5 of a file — fast enough for ~10 MB saves."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
