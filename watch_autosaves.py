#!/usr/bin/env python3
"""
watch_autosaves.py  —  run this on your gaming PC while playing CK3.

Watches your CK3 save games folder for new manual saves and copies them
into sample-saves/ in this repo.  Autosaves and Ironman saves are ignored.

A save is considered:
  - Manual:  any .ck3 file whose name doesn't start with "autosave"
  - Non-Ironman:  the file is a valid ZIP (Ironman saves are binary)

Usage (from the repo root on the PC, in a terminal):
    python watch_autosaves.py

Save your game at interesting moments, note your situation, and the file
will appear in sample-saves/ ready to analyse.  Ctrl-C to stop.

Requirements: Python 3.6+

Configuration: edit CK3_SAVE_DIR below if needed.
"""

import os
import sys
import time
import shutil
import zipfile
from pathlib import Path
from datetime import datetime


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CK3_SAVE_DIR = Path(os.environ.get("USERPROFILE", "C:/Users/User")) / (
    "Documents/Paradox Interactive/Crusader Kings III/save games"
)

REPO_ROOT     = Path(__file__).parent
DEST_DIR      = REPO_ROOT / "sample-saves"

POLL_INTERVAL = 120   # seconds between scans


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
    print(f"Polling every {POLL_INTERVAL}s — Ctrl-C to stop.\n")
    print("Waiting for manual saves (autosaves and Ironman saves are ignored)...\n")

    # Files seen on startup — don't copy pre-existing saves
    known: set[Path] = set(_find_manual_saves())
    if known:
        print(f"Ignoring {len(known)} pre-existing save(s).")

    while True:
        try:
            _scan(known)
        except Exception as exc:
            print(f"[{_now()}] Warning: {exc}")
        time.sleep(POLL_INTERVAL)


def _scan(known: set):
    for path in _find_manual_saves():
        if path in known:
            continue
        known.add(path)
        _copy_save(path)


def _find_manual_saves() -> list[Path]:
    """Return all .ck3 files that are manual (non-autosave) and non-Ironman (valid ZIP)."""
    results = []
    for path in CK3_SAVE_DIR.rglob("*.ck3"):
        if path.name.lower().startswith("autosave"):
            continue
        if _is_zip(path):
            results.append(path)
    return results


def _is_zip(path: Path) -> bool:
    """Return True if the file is a ZIP archive (i.e. not a binary Ironman save)."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"PK"
    except OSError:
        return False


def _copy_save(source: Path):
    """Copy a new manual save into DEST_DIR, preserving the original filename."""
    dest = DEST_DIR / source.name
    # If a file with this name already exists (e.g. player re-saved over the same slot),
    # add a timestamp suffix to avoid overwriting.
    if dest.exists():
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest = DEST_DIR / f"{source.stem}_{ts}.ck3"

    try:
        shutil.copy2(source, dest)
        print(f"[{_now()}] Copied: {source.name} → {dest.name}")
    except OSError as e:
        print(f"[{_now()}] ERROR copying {source.name}: {e}")


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
