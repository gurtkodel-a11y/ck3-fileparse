#!/usr/bin/env python3
"""
run_character_narrative.py — Print a character's personal-scale life story
(births, deaths, marriages, rivalries, battles, ...) reconstructed from
character_memory_manager, against the most recent CK3 save.

Same save-discovery/extraction logic as run_latest.py. Usage:

    python run_character_narrative.py --char 37766
    python run_character_narrative.py --char 37766 38396 --minor
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
from ck3.evaluators.character_narrative import life_story

_BINARY_MAGIC = (b"SAV0", b"U1\x01", b"U1\x00")


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
    ap = argparse.ArgumentParser(description="Print a character's life story.")
    ap.add_argument("--saves-dir", type=Path, default=SAVES_DIR,
                     help="Directory containing .ck3 save files (overrides SAVES_DIR constant)")
    ap.add_argument("--char", type=int, nargs="+", required=True, metavar="CHAR_ID",
                     help="One or more character IDs")
    ap.add_argument("--minor", action="store_true",
                     help="Include minor/flavor events, not just major life beats")
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

    print()
    for char_id in args.char:
        print(life_story(gs, char_id).summary(include_minor=args.minor))
        print()


if __name__ == "__main__":
    main()
