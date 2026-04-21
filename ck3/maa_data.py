"""
ck3.maa_data
~~~~~~~~~~~~
Static data loader for CK3 Men-at-Arms type definitions.

Reads all *.txt files under game/common/men_at_arms_types/ and builds a
lookup table of unit stats.  Analogous to culture_data.py and province_data.py.

Only the fields useful for strategic analysis are extracted:
  - maa_class  (skirmishers, archers, heavy_infantry, heavy_cavalry, …)
  - damage, toughness, pursuit, screen
  - stack      (regiment size when fully raised)
  - terrain_bonus  (dict[terrain, dict[stat, int]])

Usage:
    from ck3.maa_data import load_maa_definitions, maa_class_label
    defs = load_maa_definitions()
    info = defs.get("zbrojnosh")
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# Data class
# --------------------------------------------------------------------------- #

@dataclass
class MaaDef:
    """Stats for one Men-at-Arms type."""
    key: str
    maa_class: str          # skirmishers | archers | heavy_infantry | heavy_cavalry |
                            # light_cavalry | pikemen | siege_weapon | special
    damage: int
    toughness: int
    pursuit: int
    screen: int
    stack: int              # max regiment size
    terrain_bonus: dict[str, dict[str, int]] = field(default_factory=dict)
    # terrain_bonus: { "hills": {"damage": 8, "toughness": 5}, … }


# --------------------------------------------------------------------------- #
# Human-readable labels
# --------------------------------------------------------------------------- #

_CLASS_LABELS: dict[str, str] = {
    "skirmishers":    "Skirmishers",
    "archers":        "Archers",
    "heavy_infantry": "Heavy Infantry",
    "heavy_cavalry":  "Heavy Cavalry",
    "light_cavalry":  "Light Cavalry",
    "pikemen":        "Pikemen",
    "siege_weapon":   "Siege Weapons",
    "special":        "Special",
}


def maa_class_label(maa_class: str) -> str:
    """Return a human-readable label for a MaA class key."""
    return _CLASS_LABELS.get(maa_class, maa_class.replace("_", " ").title())


# --------------------------------------------------------------------------- #
# Module-level cache
# --------------------------------------------------------------------------- #

_cache: dict[str, MaaDef] | None = None


def load_maa_definitions(path: str | None = None) -> dict[str, MaaDef]:
    """
    Parse all MaA type definitions from the game files.

    Returns a dict keyed by unit type name (e.g. "zbrojnosh", "light_footmen").
    Result is cached after the first call.
    """
    global _cache
    if _cache is not None:
        return _cache

    base = Path(path) if path else (
        Path(__file__).parent.parent / "game" / "common" / "men_at_arms_types"
    )

    result: dict[str, MaaDef] = {}
    for txt_file in sorted(base.glob("*.txt")):
        if txt_file.name.startswith("_"):
            continue
        _parse_file(txt_file, result)

    _cache = result
    return result


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

# Matches "key = value" pairs where value is a bare word or number (not a block)
_KV_RE = re.compile(r"^(\w+)\s*=\s*([^\{\s][^\s]*)$")


def _parse_file(path: Path, out: dict[str, MaaDef]) -> None:
    """
    Depth-tracking parser that extracts top-level unit blocks.

    Layout of a unit block:
        unit_key = {          # depth 0→1
            type = heavy_infantry
            damage = 34
            toughness = 20
            pursuit = 0
            screen = 10
            stack = 100
            terrain_bonus = {      # depth 1→2
                hills = {          # depth 2→3
                    damage = 8
                    toughness = 5
                }
                mountains = { damage = 6 }
            }
            counters = { ... }     # skipped (depth 1→2 non-terrain block)
            …
        }

    Any other nested blocks (can_recruit, illustration, …) are skipped by
    tracking depth.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return

    depth = 0
    unit_key: str | None = None
    in_terrain_bonus = False
    terrain_key: str | None = None

    # Working state for the current unit
    maa_class = ""
    damage = toughness = pursuit = screen = stack = 0
    terrain_bonus: dict[str, dict[str, int]] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Skip blank lines, comments, @-variable assignments
        if not line or line.startswith("#") or line.startswith("@"):
            continue

        # Count brace opens and closes on this line
        opens  = line.count("{")
        closes = line.count("}")

        # ── Opening a new block ───────────────────────────────────────────── #
        if opens and not closes:
            # "key = {" pattern — the key is what matters
            name_match = re.match(r"^(\w+)\s*=\s*\{", line)
            if name_match:
                block_name = name_match.group(1)
                if depth == 0:
                    # Start of a new top-level unit definition
                    unit_key = block_name
                    maa_class = ""
                    damage = toughness = pursuit = screen = stack = 0
                    terrain_bonus = {}
                    in_terrain_bonus = False
                    terrain_key = None
                elif depth == 1 and unit_key and block_name == "terrain_bonus":
                    in_terrain_bonus = True
                elif depth == 2 and in_terrain_bonus:
                    # Opening a per-terrain block, e.g. "hills = {"
                    terrain_key = block_name
                    terrain_bonus.setdefault(terrain_key, {})
            depth += opens

        elif closes and not opens:
            # Pure closing brace(s)
            depth -= closes
            if in_terrain_bonus and terrain_key and depth == 2:
                terrain_key = None
            elif in_terrain_bonus and depth == 1:
                in_terrain_bonus = False
            elif unit_key and depth == 0:
                # Finished the top-level unit block — emit
                if maa_class:   # only emit if we found a type field
                    out[unit_key] = MaaDef(
                        key=unit_key,
                        maa_class=maa_class,
                        damage=damage,
                        toughness=toughness,
                        pursuit=pursuit,
                        screen=screen,
                        stack=stack,
                        terrain_bonus=terrain_bonus,
                    )
                unit_key = None

        elif opens and closes:
            # Inline block: "key = { k = v k2 = v2 }" — single-line form
            # Only care about terrain sub-entries at depth 2
            if depth == 2 and in_terrain_bonus:
                terrain_match = re.match(r"^(\w+)\s*=\s*\{([^}]*)\}", line)
                if terrain_match:
                    tname = terrain_match.group(1)
                    inner = terrain_match.group(2)
                    stats: dict[str, int] = {}
                    for kv in re.finditer(r"(\w+)\s*=\s*(-?\d+)", inner):
                        _maybe_set_int(stats, kv.group(1), kv.group(2))
                    if stats:
                        terrain_bonus.setdefault(tname, {}).update(stats)
            # No depth change since opens == closes

        else:
            # ── Plain key = value line ────────────────────────────────────── #
            m = _KV_RE.match(line)
            if not m:
                continue
            k, v = m.group(1), m.group(2)

            if depth == 1 and unit_key:
                # Top-level unit field
                if k == "type":
                    maa_class = v
                elif k == "damage":
                    damage = _to_int(v)
                elif k == "toughness":
                    toughness = _to_int(v)
                elif k == "pursuit":
                    pursuit = _to_int(v)
                elif k == "screen":
                    screen = _to_int(v)
                elif k == "stack":
                    stack = _to_int(v)

            elif depth == 3 and in_terrain_bonus and terrain_key:
                # Stat inside a per-terrain block
                _maybe_set_int(terrain_bonus[terrain_key], k, v)


def _to_int(v: str) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _maybe_set_int(d: dict, k: str, v: str) -> None:
    """Store k→int(v) in d if v is a number."""
    try:
        d[k] = int(float(v))
    except (ValueError, TypeError):
        pass
