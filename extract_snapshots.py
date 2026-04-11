#!/usr/bin/env python3
"""
extract_snapshots.py  —  run this on the Mac after copying over new snapshots.

CK3 save files come in two formats:
  - Old (pre-1.13): ZIP containing plaintext 'gamestate' entry
  - New (1.13+):    Binary token format, either bare (.ck3) or zip-wrapped

The new binary format requires 'ck3-melt' from the rakaly project to convert
back to plaintext.  Install it and make sure it's on your PATH:
  https://github.com/rakaly/ck3-save/releases

Usage:
    python extract_snapshots.py            # extract all new snapshots
    python extract_snapshots.py --list     # show extraction status only
    python extract_snapshots.py --force    # re-extract everything
"""

import sys
import shutil
import subprocess
import zipfile
from pathlib import Path


REPO_ROOT     = Path(__file__).parent
SNAPSHOT_DIR  = REPO_ROOT / "sample-saves"
EXTRACTED_DIR = REPO_ROOT / "sample-saves" / "extracted"

# Binary save magic bytes (CK3 1.13+)
_BINARY_MAGIC = (b'SAV0', b'U1\x01', b'U1\x00')


def main():
    force = "--force" in sys.argv
    list_ = "--list"  in sys.argv

    EXTRACTED_DIR.mkdir(exist_ok=True)

    snapshots = sorted(SNAPSHOT_DIR.glob("*.ck3"))
    if not snapshots:
        print("No .ck3 snapshots found in sample-saves/")
        return

    for snap in snapshots:
        out_path = EXTRACTED_DIR / f"{snap.stem}.txt"

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
        done = len(snapshots) - len(pending)
        print(f"Done. {done}/{len(snapshots)} snapshots extracted.")


def _extract(snap: Path, out_path: Path):
    """Detect format and extract to plaintext."""
    fmt = _detect_format(snap)

    if fmt == "plaintext_zip":
        _extract_plaintext_zip(snap, out_path)
    elif fmt == "binary":
        _extract_binary(snap, out_path)
    else:
        print(f"  SKIP {snap.name}: unrecognised format")


def _detect_format(snap: Path) -> str:
    """Return 'plaintext_zip', 'binary', or 'unknown'."""
    with open(snap, "rb") as f:
        header = f.read(8)

    # ZIP magic
    if header[:2] == b'PK':
        # Peek inside: if gamestate entry is plaintext it's the old format
        try:
            with zipfile.ZipFile(snap) as zf:
                if "gamestate" in zf.namelist():
                    inner = zf.read("gamestate")[:8]
                    if any(inner.startswith(m) for m in _BINARY_MAGIC):
                        return "binary"   # zip-wrapped binary
                    return "plaintext_zip"
        except zipfile.BadZipFile:
            pass
        return "unknown"

    # Bare binary (SAV01 / U1 header)
    if any(header.startswith(m) for m in _BINARY_MAGIC):
        return "binary"

    return "unknown"


def _extract_plaintext_zip(snap: Path, out_path: Path):
    """Old format: ZIP containing a plaintext 'gamestate' entry."""
    try:
        with zipfile.ZipFile(snap) as zf:
            data = zf.read("gamestate")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        out_path.write_text(text, encoding="utf-8")
        size_mb = out_path.stat().st_size / 1_048_576
        print(f"  OK  {snap.name}  →  {out_path.name}  ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"  ERROR {snap.name}: {e}")


def _extract_binary(snap: Path, out_path: Path):
    """New binary format: requires ck3-melt on PATH."""
    melt = shutil.which("ck3-melt")
    if melt is None:
        print(f"  SKIP {snap.name}: binary format requires 'ck3-melt' on PATH")
        print(f"    Download: https://github.com/rakaly/ck3-save/releases")
        return

    try:
        # ck3-melt writes <stem>_melted.ck3 next to the input file by default;
        # we redirect stdout instead with --stdout if supported, otherwise
        # move the output file into place.
        result = subprocess.run(
            [melt, "--stdout", str(snap)],
            capture_output=True,
        )
        if result.returncode == 0 and result.stdout:
            # --stdout worked
            try:
                text = result.stdout.decode("utf-8")
            except UnicodeDecodeError:
                text = result.stdout.decode("latin-1")
            out_path.write_text(text, encoding="utf-8")
            size_mb = out_path.stat().st_size / 1_048_576
            print(f"  OK  {snap.name}  →  {out_path.name}  ({size_mb:.1f} MB)")
        else:
            # Fallback: ck3-melt writes a file, find and move it
            melted = snap.parent / f"{snap.stem}_melted.ck3"
            result2 = subprocess.run([melt, str(snap)], capture_output=True)
            if result2.returncode != 0:
                err = (result2.stderr or result2.stdout).decode(errors="replace")
                print(f"  ERROR {snap.name}: ck3-melt failed: {err[:200]}")
                return
            if not melted.exists():
                # Some versions write next to the binary, look for it
                candidates = list(snap.parent.glob(f"{snap.stem}*melted*"))
                if candidates:
                    melted = candidates[0]
                else:
                    print(f"  ERROR {snap.name}: ck3-melt ran but output not found")
                    return
            melted.rename(out_path)
            size_mb = out_path.stat().st_size / 1_048_576
            print(f"  OK  {snap.name}  →  {out_path.name}  ({size_mb:.1f} MB)")

    except Exception as e:
        print(f"  ERROR {snap.name}: {e}")


if __name__ == "__main__":
    main()
