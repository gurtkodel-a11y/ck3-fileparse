#!/usr/bin/env python3
"""
repack_partial.py — build a .ck3 save with select top-level keys re-serialized.

Usage:
    # Pure passthrough (should be identical to wsonly baseline)
    python scripts/repack_partial.py <save.ck3> <output.ck3>

    # Re-serialize one or more specific keys
    python scripts/repack_partial.py <save.ck3> <output.ck3> --active living
    python scripts/repack_partial.py <save.ck3> <output.ck3> --active living coat_of_arms

    # List all top-level keys and their section token counts
    python scripts/repack_partial.py <save.ck3> --list-keys

Workflow:
    1. Run with no --active flags to produce a passthrough repack.
       This should load in-game identically to the original save.
    2. Add one key at a time with --active to test that key's serialization.
    3. If the save stops loading, the last key added is the culprit.
"""

import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parse_gamestate import parse
from serialize_gamestate import (
    compact_whitespace,
    repack_save,
    rebuild_gamestate,
    split_sections,
)

TOKENRE = re.compile(r'"(?:[^"\\]|\\.)*"|[{}=]|[^\s{}="]+')


def _extract_gamestate(ck3_path: Path) -> str:
    with open(ck3_path, "rb") as f:
        raw = f.read()
    zip_off = raw.find(b"PK\x03\x04")
    if zip_off == -1:
        raise ValueError(f"{ck3_path}: no embedded ZIP found (not a 1.18+ save?)")
    with zipfile.ZipFile(io.BytesIO(raw[zip_off:])) as zf:
        data = zf.read("gamestate")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def cmd_list_keys(ck3_path: Path) -> None:
    print(f"Reading {ck3_path.name} …", file=sys.stderr)
    text = _extract_gamestate(ck3_path)
    compact = compact_whitespace(re.sub(r"#[^\n]*", "", text))
    sections = split_sections(compact)

    from collections import defaultdict
    key_counts: dict[str, int] = defaultdict(int)
    key_tokens: dict[str, int] = defaultdict(int)
    key_order: dict[str, int] = {}

    for idx, (key, section_text) in enumerate(sections):
        key_counts[key] += 1
        key_tokens[key] += len(TOKENRE.findall(section_text))
        if key not in key_order:
            key_order[key] = idx

    rows = sorted(key_order.items(), key=lambda x: x[1])
    print(f"\n{'Key':<40} {'Occurrences':>12} {'Total tokens':>14}")
    print("-" * 70)
    for key, _ in rows:
        print(f"  {key:<38} {key_counts[key]:>12,} {key_tokens[key]:>14,}")


def cmd_repack(ck3_path: Path, output_path: Path, active_keys: frozenset) -> None:
    print(f"Reading {ck3_path.name} …", file=sys.stderr)
    text = _extract_gamestate(ck3_path)

    if active_keys:
        print(f"Parsing (needed for: {', '.join(sorted(active_keys))}) …",
              file=sys.stderr)
        data = parse(text)
    else:
        data = None

    print("Rebuilding gamestate …", file=sys.stderr)
    gamestate = rebuild_gamestate(text, active_keys=active_keys, data=data)

    # Quick token-count comparison
    orig_compact = compact_whitespace(re.sub(r"#[^\n]*", "", text))
    orig_tc = len(TOKENRE.findall(orig_compact))
    rt_tc   = len(TOKENRE.findall(gamestate))
    mismatches = sum(1 for a, b in zip(TOKENRE.findall(orig_compact),
                                        TOKENRE.findall(gamestate)) if a != b)
    print(f"Token count: orig={orig_tc:,}  rebuilt={rt_tc:,}  "
          f"delta={rt_tc - orig_tc:+,}  positional mismatches={mismatches:,}",
          file=sys.stderr)

    print(f"Repacking → {output_path.name} …", file=sys.stderr)
    repack_save(gamestate, str(ck3_path), str(output_path))


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    ck3_path = Path(args[0])
    if not ck3_path.exists():
        print(f"Error: {ck3_path} not found", file=sys.stderr)
        sys.exit(1)

    if "--list-keys" in args:
        cmd_list_keys(ck3_path)
        return

    if len(args) < 2:
        print("Error: output path required", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args[1])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    active_keys: frozenset[str] = frozenset()
    if "--active" in args:
        idx = args.index("--active")
        active_keys = frozenset(args[idx + 1 :])

    cmd_repack(ck3_path, output_path, active_keys)


if __name__ == "__main__":
    main()
