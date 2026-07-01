"""
ck3.trait_data
~~~~~~~~~~~~~~
Static loader for CK3 trait definitions from game/common/traits/00_traits.txt.

Public API:
    load_trait_categories()    → dict[str, str]          (trait_key → category)
    load_trait_skill_bonuses() → dict[str, dict[str,int]] (trait_key → {skill: bonus})
    trait_category(key)        → str    (single lookup, "unknown" fallback)
    trait_skill_bonus(key)     → dict[str, int]  (empty dict if none)

Skill keys: diplomacy, martial, stewardship, intrigue, learning, prowess

Categories present in game data:
    education, lifestyle, personality, childhood, commander, winter_commander,
    health, fame, court_type
    (traits with physical=yes are returned as category "physical")
"""

from __future__ import annotations
import re
import pathlib
from functools import lru_cache

_GAME_DIR      = pathlib.Path(__file__).parent.parent / "game"
_TRAIT_OPEN_RE = re.compile(r'^(\w+)\s*=\s*\{')
_COMMENT_RE    = re.compile(r'#.*')
_SKILL_KEYS    = frozenset({"diplomacy", "martial", "stewardship", "intrigue", "learning", "prowess"})
_SKILL_RE      = re.compile(r'^(diplomacy|martial|stewardship|intrigue|learning|prowess)\s*=\s*(-?\d+)')


@lru_cache(maxsize=1)
def _parse_traits() -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    """Single-pass parse of 00_traits.txt.

    Returns:
        categories    — {trait_key: effective_category}
        skill_bonuses — {trait_key: {skill_key: bonus_int}}

    Traits with ``physical = yes`` override their file-level category with
    ``"physical"``, matching the in-game UI grouping.
    Skill bonuses are collected only at depth 1 (direct trait body), so nested
    ``culture_modifier`` blocks are ignored.
    """
    path = _GAME_DIR / "common" / "traits" / "00_traits.txt"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return {}, {}

    categories:    dict[str, str]            = {}
    skill_bonuses: dict[str, dict[str, int]] = {}
    physical:      set[str]                  = set()

    current_trait: str | None = None
    depth = 0

    for line in text.splitlines():
        line_clean = _COMMENT_RE.sub("", line).strip()
        if not line_clean:
            continue

        opens  = line_clean.count("{")
        closes = line_clean.count("}")

        if depth == 0:
            if opens > 0:
                m = _TRAIT_OPEN_RE.match(line_clean)
                current_trait = m.group(1) if m else None
            depth += opens - closes
            if depth <= 0:
                current_trait = None
                depth = 0
        else:
            if depth == 1 and current_trait:
                m = re.match(r'^category\s*=\s*(\w+)', line_clean)
                if m:
                    categories[current_trait] = m.group(1)
                elif re.match(r'^physical\s*=\s*yes', line_clean):
                    physical.add(current_trait)
                else:
                    m = _SKILL_RE.match(line_clean)
                    if m:
                        skill_bonuses.setdefault(current_trait, {})[m.group(1)] = int(m.group(2))
            depth += opens - closes
            if depth <= 0:
                current_trait = None
                depth = 0

    # Physical flag overrides file-level category
    raw_cats = {k: ("physical" if k in physical else v) for k, v in categories.items()}
    for k in physical:
        raw_cats.setdefault(k, "physical")

    return raw_cats, skill_bonuses


def load_trait_categories() -> dict[str, str]:
    """Return {trait_key: category_string} for all traits."""
    return _parse_traits()[0]


def load_trait_skill_bonuses() -> dict[str, dict[str, int]]:
    """Return {trait_key: {skill_key: bonus}} for traits that grant skill bonuses."""
    return _parse_traits()[1]


def trait_category(key: str) -> str:
    """Return the category for a trait key, or 'unknown' if not found."""
    return load_trait_categories().get(key, "unknown")


def trait_skill_bonus(key: str) -> dict[str, int]:
    """Return the skill bonus dict for a trait key, or {} if it grants none."""
    return load_trait_skill_bonuses().get(key, {})
