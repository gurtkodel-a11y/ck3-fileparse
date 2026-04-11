#!/usr/bin/env python3
"""
extract_snapshots.py  —  run this on the Mac after git-pulling new snapshots.

CK3 .ck3 files are zip archives containing a 'gamestate' file (the raw text)
plus a small 'meta' file.  This script unpacks any snapshots that haven't been
extracted yet, producing a .txt file ready for parse_gamestate.parse().

Usage:
    python extract_snapshots.py            # extract all new snapshots
    python extract_snapshots.py --list     # show extraction status only
    python extract_snapshots.py --force    # re-extract everything
"""

import sys
import zipfile
from pathlib import Path


REPO_ROOT     = Path(__file__).parent
SNAPSHOT_DIR  = REPO_ROOT / "sample-saves"
EXTRACTED_DIR = REPO_ROOT / "sample-saves" / "extracted"


def main():
    force  = "--force" in sys.argv
    list_  = "--list"  in sys.argv

    EXTRACTED_DIR.mkdir(exist_ok=True)

    snapshots = sorted(SNAPSHOT_DIR.glob("*.ck3"))
    if not snapshots:
        print("No .ck3 snapshots found in snapshots/")
        return

    for snap in snapshots:
        stem = snap.stem                          # e.g. 2026-04-10_14-32-05_campaign_autosave
        out_path = EXTRACTED_DIR / f"{stem}.txt"

        if list_:
            status = "extracted" if out_path.exists() else "pending"
            print(f"  [{status:<9}]  {snap.name}")
            continue

        if out_path.exists() and not force:
            continue

        _extract(snap, out_path)

    if not list_:
        pending = [s for s in snapshots
                   if not (EXTRACTED_DIR / f"{s.stem}.txt").exists()]
        print(f"Done. {len(snapshots) - len(pending)}/{len(snapshots)} snapshots extracted.")


def _extract(snap: Path, out_path: Path):
    """Unzip a .ck3 file and write the 'gamestate' entry as plain text."""
    try:
        with zipfile.ZipFile(snap) as zf:
            names = zf.namelist()
            if "gamestate" not in names:
                print(f"  SKIP {snap.name}: no 'gamestate' entry (names: {names})")
                return
            data = zf.read("gamestate")

        # gamestate is Latin-1 / Windows-1252 in older versions, UTF-8 in newer.
        # Try UTF-8 first, fall back to latin-1.
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")

        out_path.write_text(text, encoding="utf-8")
        size_mb = out_path.stat().st_size / 1_048_576
        print(f"  OK  {snap.name}  →  {out_path.name}  ({size_mb:.1f} MB)")

    except zipfile.BadZipFile:
        print(f"  ERROR {snap.name}: not a valid zip (still being written?)")
    except Exception as e:
        print(f"  ERROR {snap.name}: {e}")


if __name__ == "__main__":
    main()
