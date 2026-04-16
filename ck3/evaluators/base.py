"""
ck3.evaluators.base
~~~~~~~~~~~~~~~~~~~~
Shared utilities used by all evaluators.  Import from here rather than
duplicating these helpers across evaluator modules.
"""

from __future__ import annotations

# Re-export from gamestate so evaluators have a single import point.
from ck3.gamestate import _ensure_list  # noqa: F401


# --------------------------------------------------------------------------- #
# Tier ordering
# --------------------------------------------------------------------------- #

_TIER_MAP = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}


def _tier_order(tier: str) -> int:
    """Sortable integer for a title-tier letter (e < k < d < c < b)."""
    return _TIER_MAP.get(tier, 9)


# --------------------------------------------------------------------------- #
# Contract-group labels
# --------------------------------------------------------------------------- #

def _contract_label(contract_group: str) -> str:
    return {
        "feudal_vassal":   "Feudal vassals",
        "tribal_vassal":   "Tribal vassals",
        "clan_vassal":     "Clan vassals",
        "republic_vassal": "Republic vassals",
    }.get(contract_group, contract_group.replace("_", " ").title())


# --------------------------------------------------------------------------- #
# War participant helpers
# --------------------------------------------------------------------------- #

def _participants(war: dict, side: str) -> list[int]:
    """Return character IDs for one side of a war record."""
    side_data = war.get(side, {})
    if not isinstance(side_data, dict):
        return []
    ids = []
    for p in _ensure_list(side_data.get("participants", [])):
        if isinstance(p, dict) and "character" in p:
            ids.append(int(p["character"]))
    return ids


# --------------------------------------------------------------------------- #
# Title-key display helpers
# --------------------------------------------------------------------------- #

_TIER_LABEL = {"e": "Emperor", "k": "King", "d": "Duke", "c": "Count", "b": "Baron"}


def title_place(key: str) -> str:
    """Strip the tier prefix from a title key and return the place name.

    Examples::
        'c_desmond'  → 'Desmond'
        'k_england'  → 'England'
        'b_prague'   → 'Prague'

    Returns '(unknown)' for empty/None keys.
    """
    if not key:
        return "(unknown)"
    name = key[2:] if len(key) > 2 and key[1] == "_" else key
    return name.replace("_", " ").title()


def title_full_label(key: str) -> str:
    """Build a full title label from a key string.

    Examples::
        'k_ireland'  → 'King of Ireland'
        'c_desmond'  → 'Count of Desmond'
        'd_munster'  → 'Duke of Munster'

    Returns '(no title)' for empty/None keys.
    """
    if not key:
        return "(no title)"
    tier = key[0]
    label = _TIER_LABEL.get(tier, "Lord")
    place = key[2:].replace("_", " ").title() if len(key) > 2 else key
    return f"{label} of {place}"
