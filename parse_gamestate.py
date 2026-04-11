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
# Iterative parser (explicit stack — no recursion limit issues)
# ---------------------------------------------------------------------------

# Each stack frame is a tuple:
#   (result_dict, result_list, is_named, pending_key)
# pending_key is set when we've consumed "key =" and are about to parse the value.

def parse(text: str) -> dict:
    """
    Parse a full CK3 gamestate text and return the top-level dict.
    Uses an explicit stack so deeply-nested saves don't hit Python's
    recursion limit.
    """
    # Strip comments
    text = re.sub(r'#[^\n]*', '', text)

    tokens = tokenize(text)
    n = len(tokens)
    pos = 0

    # Stack of open frames: (result_dict, result_list, is_named, pending_key)
    # The bottom frame is the top-level document.
    stack = [({}, [], False, None)]

    while pos < n:
        tok_type, tok_val = tokens[pos]

        result_dict, result_list, is_named, pending_key = stack[-1]

        # ------------------------------------------------------------------ #
        # Opening brace — push a new frame
        # ------------------------------------------------------------------ #
        if tok_type == TOK_OPEN:
            pos += 1
            stack.append(({}, [], False, None))
            continue

        # ------------------------------------------------------------------ #
        # Closing brace — pop the frame and attach to parent
        # ------------------------------------------------------------------ #
        if tok_type == TOK_CLOSE:
            pos += 1
            if len(stack) <= 1:
                continue  # stray '}' at top level — skip it
            stack.pop()

            # Build the completed value
            if is_named:
                if result_list:
                    result_dict[''] = result_list
                value = result_dict
            else:
                value = result_list

            # Attach to parent
            parent_dict, parent_list, parent_named, parent_key = stack[-1]
            if parent_key is not None:
                # We were filling a named value
                _dict_insert(parent_dict, parent_key, value)
                stack[-1] = (parent_dict, parent_list, True, None)
            else:
                # Bare block inside a list
                parent_list.append(value)
                stack[-1] = (parent_dict, parent_list, parent_named, None)
            continue

        # ------------------------------------------------------------------ #
        # Key = ... assignment
        # ------------------------------------------------------------------ #
        if (tok_type in (TOK_ATOM, TOK_STR)
                and pos + 1 < n
                and tokens[pos + 1][0] == TOK_EQ):
            key = tok_val
            pos += 2  # consume key + '='

            # Mark frame as named and record pending key
            stack[-1] = (result_dict, result_list, True, key)

            # If the value is a block, the next iteration's TOK_OPEN handles it.
            # If it's a primitive, consume it now.
            if pos < n and tokens[pos][0] != TOK_OPEN:
                if tokens[pos][0] == TOK_CLOSE:
                    # key = } — treat as key = None, don't consume '}'
                    _dict_insert(result_dict, key, None)
                    stack[-1] = (result_dict, result_list, True, None)
                else:
                    raw = tokens[pos][1]
                    value = raw if tokens[pos][0] == TOK_STR else _coerce(raw)
                    pos += 1
                    _dict_insert(result_dict, key, value)
                    stack[-1] = (result_dict, result_list, True, None)
            continue

        # ------------------------------------------------------------------ #
        # Bare value (anonymous list element)
        # ------------------------------------------------------------------ #
        raw = tok_val
        value = raw if tok_type == TOK_STR else _coerce(raw)
        result_list.append(value)
        pos += 1

    # The bottom frame is the top-level document (always a named dict)
    result_dict, result_list, _, _ = stack[0]
    return result_dict


def _dict_insert(d: dict, key: str, value: Any) -> None:
    """Insert key→value into d, merging duplicates into a list."""
    if key in d:
        existing = d[key]
        if isinstance(existing, list):
            existing.append(value)
        else:
            d[key] = [existing, value]
    else:
        d[key] = value


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
