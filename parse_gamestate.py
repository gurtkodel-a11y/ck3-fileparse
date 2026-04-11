#!/usr/bin/env python3
"""
Parser for CK3 gamestate files (Paradox Clausewitz engine format).

Converts the save file into nested Python dicts/lists suitable for
analysis with standard Python libraries.

Data model:
  - Named blocks  → dict  (duplicate keys are merged into lists)
  - Anonymous blocks → list
  - Quoted strings  → str  (quotes stripped)
  - Integers        → int
  - Floats          → float
  - Everything else → str
"""

import re
import sys
import json
from typing import Any, List, Tuple


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Token types
TOK_OPEN  = '{'
TOK_CLOSE = '}'
TOK_EQ    = '='
TOK_ATOM  = 'ATOM'   # unquoted word / number / date
TOK_STR   = 'STR'    # quoted string (quotes stripped)

_TOKEN_RE = re.compile(
    r'"((?:[^"\\]|\\.)*)"'   # quoted string  → group 1
    r'|([{}=])'              # single-char tokens → group 2
    r'|([^\s{}="]+)',        # unquoted atom  → group 3
    re.ASCII,
)


def tokenize(text: str) -> List[Tuple[str, str]]:
    """Return a list of (token_type, value) pairs."""
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        if m.group(1) is not None:
            tokens.append((TOK_STR, m.group(1)))
        elif m.group(2) is not None:
            tokens.append((m.group(2), m.group(2)))
        else:
            tokens.append((TOK_ATOM, m.group(3)))
    return tokens


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------

def _coerce(s: str) -> Any:
    """Try to convert an unquoted atom to int or float; otherwise keep as str."""
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------

def _parse_block(tokens: list, pos: int) -> Tuple[Any, int]:
    """
    Parse the contents of a { ... } block.

    Returns (value, next_pos) where value is either:
      - a dict  (when the block contains key=value pairs)
      - a list  (when the block contains bare values)
    """
    pos += 1  # consume '{'

    # Peek ahead to decide block kind.
    # If the first non-brace content token is followed by '=', it's a named block.
    # We treat mixed blocks (rare edge cases) as named, collecting bare values
    # under a synthetic '' key as a list.
    result_dict: dict = {}
    result_list: list = []
    is_named = False

    while pos < len(tokens) and tokens[pos][0] != TOK_CLOSE:
        tok_type, tok_val = tokens[pos]

        # Named assignment: ATOM/STR = value
        if (tok_type in (TOK_ATOM, TOK_STR)
                and pos + 1 < len(tokens)
                and tokens[pos + 1][0] == TOK_EQ):
            is_named = True
            key = tok_val
            pos += 2  # consume key and '='

            if pos < len(tokens) and tokens[pos][0] == TOK_OPEN:
                value, pos = _parse_block(tokens, pos)
            elif pos < len(tokens) and tokens[pos][0] != TOK_CLOSE:
                raw = tokens[pos][1]
                value = raw if tokens[pos][0] == TOK_STR else _coerce(raw)
                pos += 1
            else:
                value = None

            # Merge duplicate keys → list
            if key in result_dict:
                existing = result_dict[key]
                if isinstance(existing, list) and not isinstance(existing, _TaggedList):
                    existing.append(value)
                else:
                    result_dict[key] = [existing, value]
            else:
                result_dict[key] = value

        # Bare value (anonymous list element)
        elif tok_type == TOK_OPEN:
            child, pos = _parse_block(tokens, pos)
            result_list.append(child)
        elif tok_type in (TOK_ATOM, TOK_STR):
            raw = tok_val
            result_list.append(raw if tok_type == TOK_STR else _coerce(raw))
            pos += 1
        else:
            pos += 1  # skip unexpected token

    if pos < len(tokens):
        pos += 1  # consume '}'

    if is_named:
        # If there were also bare values in a named block, stash them
        if result_list:
            result_dict[''] = result_list
        return result_dict, pos
    else:
        return result_list, pos


class _TaggedList(list):
    """Marker so we don't accidentally re-wrap a list of dupe values."""
    pass


def parse(text: str) -> dict:
    """
    Parse a full CK3 gamestate text and return the top-level dict.
    """
    # Strip comments
    text = re.sub(r'#[^\n]*', '', text)

    tokens = tokenize(text)
    result: dict = {}
    pos = 0
    n = len(tokens)

    while pos < n:
        tok_type, tok_val = tokens[pos]

        if tok_type in (TOK_ATOM, TOK_STR) and pos + 1 < n and tokens[pos + 1][0] == TOK_EQ:
            key = tok_val
            pos += 2  # key + '='

            if pos < n and tokens[pos][0] == TOK_OPEN:
                value, pos = _parse_block(tokens, pos)
            elif pos < n:
                raw = tokens[pos][1]
                value = raw if tokens[pos][0] == TOK_STR else _coerce(raw)
                pos += 1
            else:
                value = None

            if key in result:
                existing = result[key]
                if isinstance(existing, list) and not isinstance(existing, dict):
                    existing.append(value)
                else:
                    result[key] = [existing, value]
            else:
                result[key] = value
        else:
            pos += 1  # skip stray tokens

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_gamestate.py <gamestate_file> [--json] [--keys]",
              file=sys.stderr)
        sys.exit(1)

    filename = sys.argv[1]

    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Error: '{filename}' not found.", file=sys.stderr)
        sys.exit(1)

    print("Tokenizing...", file=sys.stderr)
    data = parse(text)

    if '--keys' in sys.argv:
        print(f"Top-level keys ({len(data)}):")
        for k, v in data.items():
            kind = type(v).__name__
            if isinstance(v, dict):
                kind = f"dict({len(v)} keys)"
            elif isinstance(v, list):
                kind = f"list({len(v)} items)"
            print(f"  {k!r:40s} → {kind}")

    elif '--json' in sys.argv:
        print(json.dumps(data, indent=2, default=str))

    else:
        print(f"Parsed {len(data)} top-level keys.")
        print("Re-run with --keys to list them, or --json for full output.")


if __name__ == '__main__':
    main()
