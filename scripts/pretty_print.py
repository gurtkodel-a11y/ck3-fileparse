#!/usr/bin/env python3
"""
pretty_print.py — indent a compacted Clausewitz gamestate for human reading.

Usage:
    python scripts/pretty_print.py <gamestate.txt> [<output.txt>]
    python scripts/pretty_print.py <gamestate.txt> --key provinces [<output.txt>]

With no output path, writes to stdout.
With --key, extracts and pretty-prints only that top-level key's section.

Input can be either a raw extracted gamestate (with comments and original
whitespace) or already-compacted text — both are normalised before formatting.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from serialize_gamestate import compact_whitespace, split_sections


def pretty_print(compact_text: str) -> str:
    """Convert compacted Clausewitz text to indented human-readable form."""
    out: list[str] = []
    indent = 0
    in_string = False
    prev_backslash = False
    last_nonws = ''

    for ch in compact_text:
        if in_string:
            out.append(ch)
            if prev_backslash:
                prev_backslash = False
            elif ch == '\\':
                prev_backslash = True
            elif ch == '"':
                in_string = False
                last_nonws = '"'

        else:
            if ch == '"':
                in_string = True
                out.append(ch)
                last_nonws = '"'

            elif ch == '{':
                # Anonymous sub-block (not right after '='): needs its own line.
                if last_nonws and last_nonws != '=':
                    while out and out[-1] in (' ', '\t'):
                        out.pop()
                    if not out or out[-1] != '\n':
                        out.append('\n')
                    out.append('\t' * indent)
                out.append('{')
                indent += 1
                out.append('\n')
                out.append('\t' * indent)
                last_nonws = '{'

            elif ch == '}':
                indent = max(0, indent - 1)
                while out and out[-1] in (' ', '\t', '\n'):
                    out.pop()
                out.append('\n')
                out.append('\t' * indent)
                out.append('}')
                last_nonws = '}'

            elif ch == '=':
                out.append('=')
                last_nonws = '='

            elif ch == ' ':
                # Space = token separator in compact form.
                # Replace with newline + current indent so each value/pair gets
                # its own line.  Skip if we're already at the start of a line
                # (e.g. immediately after '{').
                if last_nonws and last_nonws not in ('{', '}'):
                    while out and out[-1] == ' ':
                        out.pop()
                    out.append('\n')
                    out.append('\t' * indent)

            else:
                # After '}', compact_whitespace drops the space before the
                # next key, so we need to inject the newline+indent here.
                if last_nonws == '}':
                    out.append('\n')
                    out.append('\t' * indent)
                out.append(ch)
                last_nonws = ch

    return ''.join(out)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    input_path = Path(args[0])
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    key_filter = None
    if '--key' in args:
        idx = args.index('--key')
        if idx + 1 >= len(args):
            print("Error: --key requires a key name", file=sys.stderr)
            sys.exit(1)
        key_filter = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    output_path = Path(args[1]) if len(args) > 1 else None

    print(f"Reading {input_path.name} …", file=sys.stderr)
    text = input_path.read_text(encoding='utf-8', errors='replace')

    compact = compact_whitespace(re.sub(r'#[^\n]*', '', text))

    if key_filter:
        sections = split_sections(compact)
        matches = [s for k, s in sections if k == key_filter]
        if not matches:
            print(f"Error: key '{key_filter}' not found in top-level sections",
                  file=sys.stderr)
            sys.exit(1)
        compact = ' '.join(matches)
        print(f"Extracted {len(matches)} occurrence(s) of '{key_filter}'",
              file=sys.stderr)

    print("Pretty-printing …", file=sys.stderr)
    result = pretty_print(compact)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding='utf-8')
        print(f"Wrote {output_path}  ({len(result):,} chars)", file=sys.stderr)
    else:
        sys.stdout.write(result)


if __name__ == '__main__':
    main()
