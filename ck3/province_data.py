"""
ck3.province_data
~~~~~~~~~~~~~~~~~
Loads static province data from CK3 game files.

Provides:
  - Province terrain lookup: map_province_id (int) → terrain type (str)
  - Barony→province bridge: barony_key (str) → map_province_id (int)

The save file assigns its own sequential title database IDs that differ
from the map province IDs used in province_terrain.txt.  The bridge is
game/common/landed_titles/00_landed_titles.txt, where each barony entry
contains "province = <map_province_id>".

Lookup chain used by TerrainEvaluator:
  title_db_id  →  title.key (b_*)
               →  barony_to_map_province[barony_key]
               →  terrain_map[map_province_id]
               →  terrain string
"""

from __future__ import annotations
import re
from pathlib import Path


# Terrain types that represent water — excluded from holding profiles.
WATER_TERRAIN: frozenset[str] = frozenset({"sea", "coastal_sea"})

# Default terrain when a province is absent from the file.
_DEFAULT_TERRAIN = "plains"

_ROOT = Path(__file__).parent.parent   # project root (ck3-fileparse/)

# Module-level caches
_terrain_cache: dict[int, str] | None = None
_barony_cache: dict[str, int] | None = None
_county_capital_cache: dict[str, str] | None = None   # county_key → capital barony_key


# --------------------------------------------------------------------------- #
# Province terrain (map_province_id → terrain string)
# --------------------------------------------------------------------------- #

def load_province_terrain(path: str | Path | None = None) -> dict[int, str]:
    """
    Return mapping of map_province_id → terrain type string.

    Source: game/common/province_terrain/00_province_terrain.txt
    Cached after first load.
    """
    global _terrain_cache
    if _terrain_cache is not None:
        return _terrain_cache

    if path is None:
        path = _ROOT / "game" / "common" / "province_terrain" / "00_province_terrain.txt"

    path = Path(path)
    if not path.exists():
        _terrain_cache = {}
        return _terrain_cache

    result: dict[int, str] = {}
    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("default_"):
                continue
            if "=" not in line:
                continue
            lhs, _, rhs = line.partition("=")
            lhs = lhs.strip()
            rhs = rhs.strip().split("#")[0].strip()
            if lhs.isdigit():
                result[int(lhs)] = rhs

    _terrain_cache = result
    return _terrain_cache


# --------------------------------------------------------------------------- #
# Barony → map province bridge (barony_key → map_province_id)
# --------------------------------------------------------------------------- #

# Matches lines like:  b_london = {
_BARONY_RE = re.compile(r"^\s*(b_\w+)\s*=\s*\{")
# Matches lines like:      province = 1527
_PROVINCE_RE = re.compile(r"^\s*province\s*=\s*(\d+)")


_COUNTY_RE = re.compile(r"^\s*(c_\w+)\s*=\s*\{")


def _load_landed_titles(path: Path) -> tuple[dict[str, int], dict[str, str]]:
    """
    Single-pass parse of landed_titles to build both:
      barony_provinces:  barony_key  → map_province_id
      county_capitals:   county_key  → first (capital) barony_key

    The capital barony of a county is the first b_* block inside the c_* block.
    """
    barony_provinces: dict[str, int] = {}
    county_capitals: dict[str, str] = {}

    current_county: str | None = None
    current_barony: str | None = None
    county_has_capital: bool = False
    depth = 0   # brace depth relative to when we entered the county block
    county_depth: int = 0

    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            stripped = line.strip()

            # Track brace depth to know when we've left a county block
            opens  = stripped.count("{")
            closes = stripped.count("}")

            cm = _COUNTY_RE.match(line)
            if cm:
                current_county = cm.group(1)
                county_has_capital = False
                county_depth = depth
                depth += opens - closes
                continue

            bm = _BARONY_RE.match(line)
            if bm:
                current_barony = bm.group(1)
                # Record capital: first barony in this county
                if current_county and not county_has_capital:
                    county_capitals[current_county] = current_barony
                    county_has_capital = True
                depth += opens - closes
                continue

            if current_barony:
                pm = _PROVINCE_RE.match(line)
                if pm:
                    barony_provinces[current_barony] = int(pm.group(1))

            depth += opens - closes

            # If depth drops to county_depth or below, we've exited the county
            if current_county and depth <= county_depth:
                current_county = None
                current_barony = None
                county_has_capital = False

    return barony_provinces, county_capitals


def load_barony_provinces(path: str | Path | None = None) -> dict[str, int]:
    """Return mapping of barony_key → map_province_id. Cached."""
    global _barony_cache, _county_capital_cache
    if _barony_cache is not None:
        return _barony_cache
    _ensure_loaded(path)
    return _barony_cache  # type: ignore[return-value]


def load_county_capitals(path: str | Path | None = None) -> dict[str, str]:
    """Return mapping of county_key → capital barony_key. Cached."""
    global _barony_cache, _county_capital_cache
    if _county_capital_cache is not None:
        return _county_capital_cache
    _ensure_loaded(path)
    return _county_capital_cache  # type: ignore[return-value]


def _ensure_loaded(path: str | Path | None = None) -> None:
    global _barony_cache, _county_capital_cache
    if _barony_cache is not None:
        return
    if path is None:
        path = _ROOT / "game" / "common" / "landed_titles" / "00_landed_titles.txt"
    path = Path(path)
    if not path.exists():
        _barony_cache = {}
        _county_capital_cache = {}
        return
    _barony_cache, _county_capital_cache = _load_landed_titles(path)

