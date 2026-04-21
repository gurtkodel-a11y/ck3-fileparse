#!/usr/bin/env python3
"""
Clausewitz format serializer for CK3 gamestate dicts.

Converts the Python dict produced by parse_gamestate.parse() back to
Clausewitz text format, suitable for inclusion in a .ck3 save file.

Semantic round-trip guarantee:
    parse(serialize(parse(text))) ≡ parse(text)

Byte-for-byte reproduction is NOT guaranteed — whitespace is normalized,
float precision is clamped to 6 decimal places, and quoting is applied
conservatively.  The game engine accepts both forms.

Key formatting rules derived from inspecting 1.18+ save files:
  - No spaces around '=': key=value, key={
  - Tab indentation at each nesting level
  - Floats written with 6 decimal places: 0.560000
  - Primitive lists written as anonymous inline blocks: key={ v1 v2 v3 }
  - Lists containing dicts written as repeated key assignments: key={...}\nkey={...}
  - The empty-string '' key marks anonymous items inside a named block
"""

from __future__ import annotations

import re
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Scalar formatting
# ---------------------------------------------------------------------------

# Strings that are safe to write without quotes.
# Covers: identifiers, numeric atoms, dates (YYYY.M.D), file paths,
# colours (red/white), and encoded names (HA_mA_lA_inen).
# Everything with spaces, braces, '=', '#', or '"' must be quoted.
_SAFE_ATOM = re.compile(r'^[a-zA-Z0-9_\-.:@+^]+$')


def _needs_quotes(s: str) -> bool:
    """Return True if this string must be wrapped in quotes when serialized."""
    if not s:
        return True
    if not _SAFE_ATOM.match(s):
        return True
    # Quote strings that the parser would re-coerce to a number on re-read,
    # changing the type from str to int/float.  The canonical example is the
    # character name "Nan", which Python's float() happily parses as NaN.
    try:
        int(s)
        return True
    except ValueError:
        pass
    try:
        float(s)
        return True
    except ValueError:
        pass
    return False


def _fmt_scalar(value: Any) -> str:
    """Format a primitive value as a single Clausewitz token."""
    if value is None:
        return "none"
    if isinstance(value, bool):
        # Booleans don't occur in parsed saves (yes/no are str), but guard
        # against mutations that set Python bools.
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}"
    s = str(value)
    if _needs_quotes(s):
        # The parser preserves escape sequences verbatim: a \" in the file
        # is stored as the two characters \ + " in the Python string.
        # We must NOT double-escape; just re-wrap in outer quotes.
        # Only bare " characters (not already preceded by \) need escaping —
        # but the tokenizer regex only captures " inside a quoted string as
        # part of a \. escape, so all " in parsed strings already have a
        # preceding \. Programmatic mutations that set raw Python strings
        # with literal " should pre-escape them as \".
        return f'"{s}"'
    return s


def _is_primitive(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


# ---------------------------------------------------------------------------
# Core serializer
# ---------------------------------------------------------------------------

def serialize(data: dict) -> str:
    """
    Serialize a CK3 gamestate dict to Clausewitz text.

    The top-level dict is written as bare key=value pairs (no enclosing
    braces), matching the structure of an extracted gamestate file.
    """
    out: list[str] = []
    _write_body(data, out, indent=0)
    return "".join(out)


def _write_body(d: dict, out: list[str], indent: int) -> None:
    """Emit all key=value pairs for a dict's contents (no surrounding braces)."""
    tab = "\t" * indent
    for key, value in d.items():
        if key == "":
            # Anonymous items sitting inside a named block — they appeared as
            # bare values (or bare sub-blocks) between the named key=value
            # pairs of the same block.
            items = value if isinstance(value, list) else [value]
            for item in items:
                if isinstance(item, list):
                    # Anonymous sub-block of primitives, e.g. color=rgb { R G B }
                    # where { R G B } appears right after 'color=rgb' in the file.
                    if not item:
                        out.append(f"{tab}{{}}\n")
                    else:
                        vals = " ".join(_fmt_scalar(v) for v in item if _is_primitive(v))
                        out.append(f"{tab}{{ {vals} }}\n")
                elif isinstance(item, dict):
                    # Anonymous named sub-block inside a named outer block.
                    out.append(f"{tab}{{\n")
                    _write_body(item, out, indent + 1)
                    out.append(f"{tab}}}\n")
                else:
                    out.append(f"{tab}{_fmt_scalar(item)}\n")
        elif value is None:
            # key=} edge case from the parser — skip; none has no
            # well-defined serialisation and doesn't appear in practice.
            pass
        elif isinstance(value, list):
            _write_list(key, value, out, indent)
        elif isinstance(value, dict):
            out.append(f"{tab}{key}={{\n")
            _write_body(value, out, indent + 1)
            out.append(f"{tab}}}\n")
        else:
            out.append(f"{tab}{key}={_fmt_scalar(value)}\n")


def _write_list(key: str, items: list, out: list[str], indent: int) -> None:
    """
    Dispatch a list value to the appropriate Clausewitz serialisation form.

    - All primitives  →  anonymous inline block:  key={ v1 v2 v3 }
    - Any non-primitive →  anonymous block of sub-blocks:
                           key={ {k=v} {k=v} }

    The anonymous sub-block form is the only option that round-trips
    correctly for single-element lists: key={ {k=v} } re-parses as
    [{k: v}], while key={k=v} (one bare block) re-parses as {k: v}.
    It also works for multi-element lists and for the empty-slot pattern
    buildings={ {} {type=X} {} }.
    """
    tab = "\t" * indent
    inner = "\t" * (indent + 1)

    if not items:
        out.append(f"{tab}{key}={{}}\n")
        return

    if all(_is_primitive(v) for v in items):
        vals = " ".join(_fmt_scalar(v) for v in items)
        out.append(f"{tab}{key}={{ {vals} }}\n")
    else:
        # Anonymous block of sub-blocks.
        out.append(f"{tab}{key}={{\n")
        for item in items:
            if isinstance(item, dict):
                out.append(f"{inner}{{\n")
                _write_body(item, out, indent + 2)
                out.append(f"{inner}}}\n")
            elif isinstance(item, list):
                # Empty list [] came from an empty anonymous block {}.
                # Non-empty anonymous list is unusual; write inline.
                if not item:
                    out.append(f"{inner}{{}}\n")
                else:
                    vals = " ".join(_fmt_scalar(v) for v in item if _is_primitive(v))
                    out.append(f"{inner}{{ {vals} }}\n")
            else:
                # Primitive mixed in with non-primitives — bare value.
                out.append(f"{inner}{_fmt_scalar(item)}\n")
        out.append(f"{tab}}}\n")


# ---------------------------------------------------------------------------
# Repack helpers (for .ck3 save construction)
# ---------------------------------------------------------------------------

def repack_save(gamestate_text: str, original_ck3_path: str, output_path: str) -> None:
    """
    Repack a serialized gamestate into a .ck3 save file.

    1.18+ saves are structured as:
        <SAV0 plaintext header, ~32 KB>
        <ZIP archive containing a single 'gamestate' entry>

    This function reads the SAV0 header from the original file, then builds
    a new save by replacing the embedded ZIP with one containing the new
    gamestate text.
    """
    import zipfile, io

    # Read the original to locate the embedded ZIP (starts with PK\x03\x04)
    with open(original_ck3_path, "rb") as f:
        original = f.read()

    zip_offset = original.find(b"PK\x03\x04")
    if zip_offset == -1:
        raise ValueError(
            f"{original_ck3_path!r} does not appear to be a 1.18+ SAV0+ZIP save "
            "(no PK signature found)"
        )

    header = original[:zip_offset]

    # Build a new ZIP with the serialized gamestate
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("gamestate", gamestate_text.encode("utf-8"))

    # Write header + new ZIP
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(buf.getvalue())

    size_mb = (len(header) + len(buf.getvalue())) / 1_048_576
    print(f"Wrote {output_path!r}  ({size_mb:.1f} MB)", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Usage:
        python3 serialize_gamestate.py <extracted_gamestate.txt>
            Print the serialized Clausewitz text to stdout.

        python3 serialize_gamestate.py <extracted_gamestate.txt> --roundtrip
            Parse → serialize → re-parse, then compare the two dicts and
            report any structural differences.  Exit 0 if clean.
    """
    if len(sys.argv) < 2:
        print(
            "Usage: python3 serialize_gamestate.py <gamestate.txt> [--roundtrip]",
            file=sys.stderr,
        )
        sys.exit(1)

    from parse_gamestate import parse

    path = sys.argv[1]
    print(f"Parsing {path!r} …", file=sys.stderr)
    with open(path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    data1 = parse(text)

    print("Serializing …", file=sys.stderr)
    serialized = serialize(data1)

    if "--roundtrip" in sys.argv:
        print("Re-parsing serialized output …", file=sys.stderr)
        data2 = parse(serialized)
        diffs = _compare_dicts(data1, data2, path="<root>")
        if diffs:
            print(f"\n{len(diffs)} difference(s) found:\n")
            for d in diffs[:50]:
                print(" ", d)
            if len(diffs) > 50:
                print(f"  … and {len(diffs) - 50} more")
            sys.exit(1)
        else:
            print("Round-trip clean — no structural differences found.", file=sys.stderr)
    else:
        sys.stdout.write(serialized)


def _compare_dicts(
    a: Any, b: Any, path: str, max_diffs: int = 200
) -> list[str]:
    """
    Recursively compare two parsed gamestate values.  Returns a list of
    human-readable difference descriptions (empty = identical).

    Comparison is semantic: int 1 == float 1.0, and float comparison uses
    a small epsilon to absorb 6-decimal-place rounding.
    """
    diffs: list[str] = []
    _diff(a, b, path, diffs, max_diffs)
    return diffs


def _diff(a: Any, b: Any, path: str, diffs: list[str], limit: int) -> None:
    if len(diffs) >= limit:
        return

    if type(a) != type(b):
        # Allow int/float coercion (e.g. 1 vs 1.0 after float serialisation)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(float(a) - float(b)) > 1e-4:
                diffs.append(f"{path}: {a!r} → {b!r}")
            return
        # Allow int parsed as str or vice-versa only if values are equal
        if {type(a), type(b)} <= {int, str}:
            if str(a) == str(b):
                return
        diffs.append(f"{path}: type {type(a).__name__} → {type(b).__name__}  ({a!r} vs {b!r})")
        return

    if isinstance(a, dict):
        keys_a, keys_b = set(a), set(b)
        for k in sorted(keys_a - keys_b):
            diffs.append(f"{path}.{k}: present in original, missing after round-trip")
        for k in sorted(keys_b - keys_a):
            diffs.append(f"{path}.{k}: absent in original, appeared after round-trip")
        for k in sorted(keys_a & keys_b):
            _diff(a[k], b[k], f"{path}.{k}", diffs, limit)

    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: list length {len(a)} → {len(b)}")
            # Still compare up to the shorter length
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{i}]", diffs, limit)

    elif isinstance(a, float):
        if abs(a - b) > 1e-4:
            diffs.append(f"{path}: {a!r} → {b!r}")

    else:
        if a != b:
            diffs.append(f"{path}: {a!r} → {b!r}")


if __name__ == "__main__":
    main()
