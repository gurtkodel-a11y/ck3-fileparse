#!/usr/bin/env python3
"""
run_latest.py — Find the most recent .ck3 save, extract it, and run all reports.

Set SAVES_DIR to your CK3 saves folder, then:
    python run_latest.py
    python run_latest.py --modules military
    python run_latest.py --char 12345
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

ALL_MODULES = ["military", "culture", "relationships", "terrain"]
_BINARY_MAGIC = (b"SAV0", b"U1\x01", b"U1\x00")


def _extract_gamestate(path: Path) -> str:
    data = path.read_bytes()

    # Old format: bare ZIP containing plaintext gamestate
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "gamestate" in zf.namelist():
                    raw = zf.read("gamestate")
                    if not any(raw.startswith(m) for m in _BINARY_MAGIC):
                        return raw.decode("utf-8", errors="replace")
        except zipfile.BadZipFile:
            pass

    # 1.18+ format: SAV0 plaintext header + embedded ZIP with plaintext gamestate
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

    sys.exit(
        f"Cannot extract {path.name}: binary format requires ck3-melt.\n"
        "  Download: https://github.com/rakaly/ck3-save/releases"
    )


def main():
    ap = argparse.ArgumentParser(description="Report on the most recent CK3 save.")
    ap.add_argument(
        "--saves-dir", type=Path, default=SAVES_DIR,
        help="Directory containing .ck3 save files (overrides SAVES_DIR constant)",
    )
    ap.add_argument("--char", type=int, metavar="CHAR_ID",
                    help="Override the played character ID")
    ap.add_argument(
        "--modules", "-m", nargs="+", choices=ALL_MODULES, metavar="MODULE",
        help=f"Modules to run: {', '.join(ALL_MODULES)} (default: all)",
    )
    args = ap.parse_args()

    saves_dir: Path = args.saves_dir
    if not saves_dir.exists():
        sys.exit(f"Saves directory not found: {saves_dir}")

    saves = sorted(saves_dir.glob("*.ck3"), key=lambda p: p.stat().st_mtime)
    if not saves:
        sys.exit(f"No .ck3 files found in {saves_dir}")

    # Walk from most recent to oldest, skipping files that can't be extracted
    latest = None
    text = None
    for candidate in reversed(saves):
        data = candidate.read_bytes()
        # Skip pure binary saves (ironman / autosave_exit) that require ck3-melt
        is_bare_zip = data[:2] == b"PK"
        is_sav0 = any(data.startswith(m) for m in _BINARY_MAGIC)
        if not (is_bare_zip or is_sav0):
            continue
        # For SAV0, check the embedded gamestate isn't binary
        if is_sav0:
            offset = data.find(b"PK\x03\x04")
            if offset == -1:
                continue
            try:
                with zipfile.ZipFile(io.BytesIO(data[offset:])) as zf:
                    if "gamestate" not in zf.namelist():
                        continue
                    gs_bytes = zf.read("gamestate")
                    if any(gs_bytes.startswith(m) for m in _BINARY_MAGIC):
                        continue
                    latest = candidate
                    text = gs_bytes.decode("utf-8", errors="replace")
                    break
            except zipfile.BadZipFile:
                continue
        elif is_bare_zip:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    if "gamestate" not in zf.namelist():
                        continue
                    gs_bytes = zf.read("gamestate")
                    if any(gs_bytes.startswith(m) for m in _BINARY_MAGIC):
                        continue
                    latest = candidate
                    text = gs_bytes.decode("utf-8", errors="replace")
                    break
            except zipfile.BadZipFile:
                continue

    if latest is None:
        sys.exit("No parseable .ck3 save found (all files are binary — use ck3-melt).")

    print(f"Save:       {latest.name}", file=sys.stderr)
    print(f"Modified:   {latest.stat().st_mtime:.0f}", file=sys.stderr)

    print("Parsing …", file=sys.stderr)
    raw = parse(text)

    gs = GameState(raw)
    gs.build_indices()

    char_id = args.char or gs.played_character_id
    if char_id is None:
        sys.exit("Cannot determine played character — pass --char ID explicitly.")

    print(f"Character:  id {char_id}", file=sys.stderr)

    modules = args.modules or ALL_MODULES
    divider = "\n" + "=" * 72 + "\n"

    if "military" in modules:
        from ck3.evaluators.military import MilitaryEvaluator
        print(divider)
        print(MilitaryEvaluator(gs, char_id).report().summary())

    if "culture" in modules:
        from ck3.evaluators.culture import CultureEvaluator
        print(divider)
        print(CultureEvaluator(gs, char_id).report().summary())

    if "relationships" in modules:
        from ck3.evaluators.relationships import RelationshipsEvaluator
        print(divider)
        print(RelationshipsEvaluator(gs, char_id).report().summary())

    if "terrain" in modules:
        from ck3.evaluators.terrain import TerrainEvaluator
        print(divider)
        print(TerrainEvaluator(gs, char_id).report().summary())

    print(divider)


if __name__ == "__main__":
    main()
