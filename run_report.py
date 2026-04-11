#!/usr/bin/env python3
"""
run_report.py — Generate human-readable reports for a CK3 save file.

Usage:
    python3 run_report.py <gamestate.txt> [char_id] [--modules MODULE ...]

Modules: military, religion, relationships  (default: all)

Examples:
    python3 run_report.py save.txt                        # all modules
    python3 run_report.py save.txt 18269                  # explicit char
    python3 run_report.py save.txt --modules military
    python3 run_report.py save.txt 18269 --modules religion relationships
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parse_gamestate import parse
from ck3.gamestate import GameState

ALL_MODULES = ["military", "religion", "relationships"]


def _char_display(gs: GameState, char_id: int) -> str:
    c = gs.character(char_id)
    if not c:
        return f"(unknown char {char_id})"
    name = c.get("first_name", "?")
    dyn  = c.get("dynasty_house")
    if dyn:
        house = gs.dynasty_house(dyn)
        if house:
            name += f" {house.get('name', '')}"
    title_recs = gs.titles_held_by(char_id)
    titles = [t.get("key","") for t in title_recs if isinstance(t, dict)]
    tier = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}
    titles.sort(key=lambda k: tier.get(k[0], 9) if k else 9)
    title_str = " | ".join(titles[:3])
    return f"{name}  [{title_str}]  (id {char_id})"


def main():
    parser = argparse.ArgumentParser(
        description="Generate CK3 save reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("savefile", help="Path to extracted gamestate .txt file")
    parser.add_argument("char_id", nargs="?", type=int, help="Character ID (default: played character)")
    parser.add_argument(
        "--modules", "-m",
        nargs="+",
        choices=ALL_MODULES,
        metavar="MODULE",
        help=f"Modules to run: {', '.join(ALL_MODULES)} (default: all)",
    )

    args = parser.parse_args()

    path = Path(args.savefile)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    modules = args.modules or ALL_MODULES

    print(f"Reading {path.name} …", file=sys.stderr)
    text = path.read_text(encoding="utf-8", errors="ignore")

    print("Parsing …", file=sys.stderr)
    raw = parse(text)

    gs = GameState(raw)
    gs.build_indices()

    char_id = args.char_id
    if char_id is None:
        char_id = gs.played_character_id
        if char_id is None:
            print("Cannot determine played_character — pass char_id explicitly.", file=sys.stderr)
            sys.exit(1)

    print(f"\nCharacter: {_char_display(gs, char_id)}\n", file=sys.stderr)

    divider = "\n" + "=" * 72 + "\n"

    if "military" in modules:
        from ck3.evaluators.military import MilitaryEvaluator
        print(divider)
        print(MilitaryEvaluator(gs, char_id).report().summary())

    if "religion" in modules:
        from ck3.evaluators.religion import ReligionEvaluator
        print(divider)
        print(ReligionEvaluator(gs, char_id).report().summary())

    if "relationships" in modules:
        from ck3.evaluators.relationships import RelationshipsEvaluator
        print(divider)
        print(RelationshipsEvaluator(gs, char_id).report().summary())

    print(divider)


if __name__ == "__main__":
    main()
