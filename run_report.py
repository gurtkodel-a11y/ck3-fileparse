#!/usr/bin/env python3
"""
run_report.py — Generate human-readable military and religion reports
for a CK3 save file.

Usage:
    python3 run_report.py <gamestate.txt> [char_id]

If char_id is omitted, the played_character from the save is used.
"""

import sys
from pathlib import Path

# Make sure the repo root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from parse_gamestate import parse
from ck3.gamestate import GameState
from ck3.evaluators.military import MilitaryEvaluator
from ck3.evaluators.religion import ReligionEvaluator
from ck3.evaluators.hierarchy import HierarchyEvaluator


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
    # highest tier first
    tier = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}
    titles.sort(key=lambda k: tier.get(k[0], 9) if k else 9)
    title_str = " | ".join(titles[:3])
    return f"{name}  [{title_str}]  (id {char_id})"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run_report.py <gamestate.txt> [char_id]", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {path.name} …", file=sys.stderr)
    text = path.read_text(encoding="utf-8", errors="ignore")

    print("Parsing …", file=sys.stderr)
    raw = parse(text)

    gs = GameState(raw)
    gs.build_indices()

    # Resolve character id
    if len(sys.argv) >= 3:
        char_id = int(sys.argv[2])
    else:
        char_id = gs.played_character_id
        if char_id is None:
            print("Cannot determine played_character — pass char_id explicitly.", file=sys.stderr)
            sys.exit(1)

    print(f"\nCharacter: {_char_display(gs, char_id)}\n", file=sys.stderr)

    divider = "\n" + "=" * 72 + "\n"

    # ── Military ──────────────────────────────────────────────────────────── #
    mil = MilitaryEvaluator(gs, char_id)
    mil_report = mil.report()
    print(divider)
    print(mil_report.summary())

    # ── Religion ──────────────────────────────────────────────────────────── #
    rel = ReligionEvaluator(gs, char_id)
    rel_report = rel.report()
    print(divider)
    print(rel_report.summary())

    # ── Hierarchy ─────────────────────────────────────────────────────────── #
    hier = HierarchyEvaluator(gs, char_id)
    hier_report = hier.report()
    print(divider)
    print(hier_report.summary())

    print(divider)


if __name__ == "__main__":
    main()
