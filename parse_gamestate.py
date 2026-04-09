#!/usr/bin/env python3
"""
Parser for CK3 gamestate files.

Parses recursive block structures of the form:
  tag = value
  tag = { ... }

Outputs a list of top-level items with their tag and type (block or primitive).
"""

import re
import sys
from typing import List, Dict, Tuple


def parse_gamestate(content: str) -> List[Dict[str, str]]:
    """
    Parse a CK3 gamestate file and return top-level items.
    
    Args:
        content: The file content as a string
        
    Returns:
        List of dictionaries with 'tag' and 'type' keys
    """
    # Remove comments (lines starting with #)
    lines = []
    for line in content.split('\n'):
        comment_pos = line.find('#')
        if comment_pos != -1:
            line = line[:comment_pos]
        lines.append(line)
    content = '\n'.join(lines)
    
    # Normalize whitespace: collapse all whitespace to single spaces
    # This simplifies parsing since whitespace doesn't matter in CK3 files
    content = re.sub(r'\s+', ' ', content.strip())
    
    top_level_items = []
    pos = 0
    content_len = len(content)
    
    while pos < content_len:
        # Skip whitespace (now just single spaces after normalization)
        while pos < content_len and content[pos] == ' ':
            pos += 1
        
        if pos >= content_len:
            break
        
        # Parse a top-level item: tag = value
        tag, value, new_pos = parse_item(content, pos)
        
        if tag:  # Skip empty tags (tag already stripped)
            # Determine type
            item_type = "block" if value and value.startswith('{') else "primitive"
            
            top_level_items.append({
                'tag': tag,
                'type': item_type
            })
        
        pos = new_pos
    
    return top_level_items


def parse_item(content: str, pos: int) -> Tuple[str, str, int]:
    """
    Parse a single item: tag = value
    
    Returns:
        Tuple of (tag, value, new_position)
    """
    # Find the equals sign
    equals_pos = content.find('=', pos)
    if equals_pos == -1:
        return None, None, len(content)
    
    # Extract tag (left-hand side) - can contain alphanumeric, underscores, dots, dashes, etc.
    # Strip whitespace (though content is already normalized)
    tag = content[pos:equals_pos].strip()
    
    # Move past the equals sign
    pos = equals_pos + 1
    
    # Skip whitespace after = (content is normalized, so just single spaces)
    while pos < len(content) and content[pos] == ' ':
        pos += 1
    
    if pos >= len(content):
        return tag, "", pos
    
    # Check if it's a block
    if content[pos] == '{':
        # Parse block
        value, pos = parse_block(content, pos)
        return tag, value, pos
    else:
        # Parse primitive value
        value, pos = parse_primitive(content, pos)
        return tag, value, pos


def parse_block(content: str, pos: int) -> Tuple[str, int]:
    """
    Parse a block: { ... }
    
    Returns:
        Tuple of (block_content, new_position)
    """
    if content[pos] != '{':
        raise ValueError(f"Expected '{{' at position {pos}")
    
    start_pos = pos
    pos += 1
    depth = 1
    
    while pos < len(content) and depth > 0:
        if content[pos] == '{':
            depth += 1
        elif content[pos] == '}':
            depth -= 1
        pos += 1
    
    # Extract the entire block including braces
    block_content = content[start_pos:pos]
    return block_content, pos


def parse_primitive(content: str, pos: int) -> Tuple[str, int]:
    """
    Parse a primitive value (until next top-level item or end of content).
    
    Primitive values can be:
    - Numbers
    - Strings (quoted or unquoted)
    - Until we hit a new top-level assignment (tag = value)
    
    Returns:
        Tuple of (value, new_position)
    """
    start_pos = pos
    
    # If it starts with a quote, find the matching quote
    if pos < len(content) and content[pos] == '"':
        pos += 1
        # Find the closing quote (handling escaped quotes)
        while pos < len(content):
            if content[pos] == '"' and (pos == start_pos + 1 or content[pos - 1] != '\\'):
                pos += 1
                break
            pos += 1
        value = content[start_pos:pos]
        return value, pos
    
    # For unquoted primitives, parse until we see a pattern that indicates
    # a new top-level assignment: " tag = " 
    # Tags in CK3 can contain alphanumeric, underscores, dots, dashes, etc.
    
    # Find the end of the primitive value by looking ahead for new assignments
    end_pos = pos
    while end_pos < len(content):
        # Look ahead to see if we've reached a new top-level assignment
        remaining = content[end_pos:]
        
        # Check if we've hit the start of a new assignment
        # Match: space(s), then tag (can contain word chars, dots, dashes, etc.), then space(s), then =
        # Tags typically start with a letter or underscore
        # Note: content is normalized, so \s+ is effectively just ' +'
        match = re.match(r'^\s+([a-zA-Z_][a-zA-Z0-9_.-]*)\s*=', remaining)
        if match:
            # Found a new top-level assignment, stop here
            break
        
        # Also stop if we hit a brace (shouldn't happen, but safety check)
        if content[end_pos] in ['{', '}']:
            break
        
        end_pos += 1
    
    # Extract the primitive value (strip leading/trailing spaces)
    value = content[start_pos:end_pos].strip()
    return value, end_pos


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: python parse_gamestate.py <gamestate_file>", file=sys.stderr)
        sys.exit(1)
    
    filename = sys.argv[1]
    
    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        items = parse_gamestate(content)
        
        # Output results
        print(f"Found {len(items)} top-level items:\n")
        for item in items:
            print(f"Tag: {item['tag']}, Type: {item['type']}")
        
        # Optionally output as JSON
        if '--json' in sys.argv:
            import json
            print("\nJSON output:")
            print(json.dumps(items, indent=2))
    
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing file: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

