#!/usr/bin/env python3
"""
run_matchmaker.py — Screen for betrothal/marriage candidates against the
most recent CK3 save.

Same save-discovery/extraction logic as run_latest.py (no separate
extraction step needed on Windows). Usage:

    python run_matchmaker.py --char 37766                       # Judita, defaults
    python run_matchmaker.py --char 37766 --age-window 8
    python run_matchmaker.py --char 37766 --track noble --max-zone 1
    python run_matchmaker.py --char 37766 --faith same_religion --allow-vices
"""

import io
import sys
import zipfile
import argparse
from pathlib import Path

# ── Set this to your CK3 save directory ──────────────────────────────────────
SAVES_DIR = Path(r"C:\Users\kkado\Documents\Paradox Interactive\Crusader Kings III\save games")
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding='utf-8')

from parse_gamestate import parse
from ck3.gamestate import GameState
from ck3.evaluators.matchmaker import find_candidates

_BINARY_MAGIC = (b"SAV0", b"U1\x01", b"U1\x00")


def _extract_gamestate(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "gamestate" in zf.namelist():
                    raw = zf.read("gamestate")
                    if not any(raw.startswith(m) for m in _BINARY_MAGIC):
                        return raw.decode("utf-8", errors="replace")
        except zipfile.BadZipFile:
            pass
    if any(data.startswith(m) for m in _BINARY_MAGIC):
        offset = data.find(b"PK\x03\x04")
        if offset != -1:
            try:
                with zipfile.ZipFile(io.BytesIO(data[offset:])) as zf:
                    if "gamestate" in zf.namelist():
                        raw = zf.read("gamestate")
                        if not any(raw.startswith(m) for m in _BINARY_MAGIC):
                            return raw.decode("utf-8", errors="replace")
            except zipfile.BadZipFile:
                pass
    sys.exit(f"Cannot extract {path.name}: binary format requires ck3-melt.")


def _find_latest(saves_dir: Path) -> tuple[Path, str]:
    saves = sorted(saves_dir.glob("*.ck3"), key=lambda p: p.stat().st_mtime)
    for candidate in reversed(saves):
        data = candidate.read_bytes()
        is_bare_zip = data[:2] == b"PK"
        is_sav0 = any(data.startswith(m) for m in _BINARY_MAGIC)
        if not (is_bare_zip or is_sav0):
            continue
        try:
            if is_sav0:
                offset = data.find(b"PK\x03\x04")
                if offset == -1:
                    continue
                with zipfile.ZipFile(io.BytesIO(data[offset:])) as zf:
                    if "gamestate" not in zf.namelist():
                        continue
                    gs_bytes = zf.read("gamestate")
            else:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    if "gamestate" not in zf.namelist():
                        continue
                    gs_bytes = zf.read("gamestate")
            if any(gs_bytes.startswith(m) for m in _BINARY_MAGIC):
                continue
            return candidate, gs_bytes.decode("utf-8", errors="replace")
        except zipfile.BadZipFile:
            continue
    sys.exit("No parseable .ck3 save found (all files are binary — use ck3-melt).")


def main():
    ap = argparse.ArgumentParser(description="Screen for spouse/betrothal candidates.")
    ap.add_argument("--saves-dir", type=Path, default=SAVES_DIR,
                     help="Directory containing .ck3 save files (overrides SAVES_DIR constant)")
    ap.add_argument("--char", type=int, required=True, metavar="CHAR_ID",
                     help="Character ID of the person being matched (e.g. your child)")
    ap.add_argument("--age-window", type=int, default=6,
                     help="Age band +/- this many years from the subject (default 6)")
    ap.add_argument("--min-age", type=int, default=None)
    ap.add_argument("--max-age", type=int, default=None)
    ap.add_argument("--faith", choices=["same_faith", "same_religion", "any"], default="same_faith")
    ap.add_argument("--track", choices=["any", "noble", "lowborn"], default="any")
    ap.add_argument("--max-zone", type=int, default=None, metavar="0-3",
                     help="Cap proximity zone: 0=local 1=nearby 2=continental 3=global")
    ap.add_argument("--allow-vices", action="store_true",
                     help="Don't filter out candidates with vice personality traits")
    ap.add_argument("--require-virtue", action="store_true",
                     help="Only keep candidates with at least one virtue trait")
    ap.add_argument("--limit", type=int, default=25)

    args = ap.parse_args()

    saves_dir: Path = args.saves_dir
    if not saves_dir.exists():
        sys.exit(f"Saves directory not found: {saves_dir}")

    latest, text = _find_latest(saves_dir)
    print(f"Save:    {latest.name}", file=sys.stderr)
    print("Parsing …", file=sys.stderr)
    raw = parse(text)

    gs = GameState(raw)
    gs.build_indices()

    report = find_candidates(
        gs, args.char,
        age_window=args.age_window,
        min_age=args.min_age,
        max_age=args.max_age,
        faith_mode=args.faith,
        exclude_vices=not args.allow_vices,
        require_virtue=args.require_virtue,
        track=args.track,
        max_zone=args.max_zone,
        limit=args.limit,
    )

    print()
    print(report.summary(limit=args.limit))


if __name__ == "__main__":
    main()
