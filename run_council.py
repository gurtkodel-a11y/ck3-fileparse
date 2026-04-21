#!/usr/bin/env python3
"""
run_council.py — Generate council advisor briefs for a CK3 save file.

Usage:
    python3 run_council.py <gamestate.txt> [char_id] [--advisors ADVISOR ...]

Advisors: marshal, chancellor, steward, councilor, spymaster  (default: all)

Examples:
    python3 run_council.py save.txt
    python3 run_council.py save.txt 18269
    python3 run_council.py save.txt --advisors marshal chancellor
    python3 run_council.py save.txt 18269 --advisors spymaster
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parse_gamestate import parse
from ck3.gamestate import GameState
from ck3.advisors import Council

ALL_ADVISORS = ["marshal", "chancellor", "steward", "councilor", "spymaster"]


def _char_display(gs: GameState, char_id: int) -> str:
    c = gs.character(char_id)
    if not c:
        return f"(unknown char {char_id})"
    name = c.get("first_name", "?")
    dyn = c.get("dynasty_house")
    if dyn:
        house = gs.dynasty_house(dyn)
        if house:
            name += f" {house.get('name', '')}"
    title_recs = gs.titles_held_by(char_id)
    titles = [t.get("key", "") for t in title_recs if isinstance(t, dict)]
    tier = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}
    titles.sort(key=lambda k: tier.get(k[0], 9) if k else 9)
    title_str = " | ".join(titles[:3])
    return f"{name}  [{title_str}]  (id {char_id})"


def main():
    parser = argparse.ArgumentParser(
        description="Generate CK3 council advisor briefs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("savefile", help="Path to extracted gamestate .txt file")
    parser.add_argument("char_id", nargs="?", type=int,
                        help="Character ID (default: played character)")
    parser.add_argument(
        "--advisors", "-a",
        nargs="+",
        choices=ALL_ADVISORS,
        metavar="ADVISOR",
        help=f"Advisors to run: {', '.join(ALL_ADVISORS)} (default: all)",
    )

    args = parser.parse_args()

    path = Path(args.savefile)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    advisors = args.advisors or ALL_ADVISORS

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
            print("Cannot determine played_character — pass char_id explicitly.",
                  file=sys.stderr)
            sys.exit(1)

    print(f"\nCharacter: {_char_display(gs, char_id)}\n", file=sys.stderr)

    council = Council(gs, char_id)

    divider = "\n" + "=" * 72 + "\n"
    print(divider)
    print(council.brief(advisors))
    print(divider)


if __name__ == "__main__":
    main()
