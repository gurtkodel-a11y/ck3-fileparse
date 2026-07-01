"""
ck3.evaluators.base
~~~~~~~~~~~~~~~~~~~~
Shared utilities used by all evaluators.  Import from here rather than
duplicating these helpers across evaluator modules.
"""

from __future__ import annotations

# Re-export from gamestate so evaluators have a single import point.
from ck3.gamestate import _ensure_list  # noqa: F401
from ck3.names import decode_name


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
_TIER_LABEL_F = {"e": "Empress", "k": "Queen", "d": "Duchess", "c": "Countess", "b": "Baroness"}


def _title_place_name(key: str, title: dict | None) -> str:
    """
    Resolve a title's place name, preferring the save's own
    title_name_data.name (handles procedurally-named/landless titles like
    "c_nf_kiyohara" → "Kiyohara Family") over guessing from the key.
    """
    if isinstance(title, dict):
        name_data = title.get("title_name_data", {})
        raw_name = name_data.get("name", "") if isinstance(name_data, dict) else ""
        if isinstance(raw_name, str) and raw_name:
            return decode_name(raw_name)
    name = key[2:] if len(key) > 2 and key[1] == "_" else key
    return name.replace("_", " ").title()


def title_place(key: str, title: dict | None = None) -> str:
    """Return the place name for a title key.

    Examples::
        'c_desmond'  → 'Desmond'
        'k_england'  → 'England'
        'b_prague'   → 'Prague'

    Pass the title's own record as *title* when available — some titles
    (procedurally-named family/clan-headship titles in particular) have a
    display name in title_name_data.name that doesn't match the key at all.

    Returns '(unknown)' for empty/None keys.
    """
    if not key:
        return "(unknown)"
    return _title_place_name(key, title)


def title_full_label(key: str, title: dict | None = None, female: bool = False) -> str:
    """Build a full title label from a key string.

    Examples::
        'k_ireland'  → 'King of Ireland'
        'c_desmond'  → 'Count of Desmond'
        'd_munster'  → 'Duke of Munster'

    Pass the title's own record as *title* when available — see title_place().
    Pass female=True for the feminine form (Duchess, Countess, Queen, …) —
    e.g. when labelling a title for its current female holder.

    Returns '(no title)' for empty/None keys.
    """
    if not key:
        return "(no title)"
    tier = key[0]
    labels = _TIER_LABEL_F if female else _TIER_LABEL
    label = labels.get(tier, "Lady" if female else "Lord")
    place = _title_place_name(key, title)
    return f"{label} of {place}"
