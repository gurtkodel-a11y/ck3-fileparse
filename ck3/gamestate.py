"""
ck3.gamestate
~~~~~~~~~~~~~
Wraps the raw parsed dict from parse_gamestate.parse() and builds
fast lookup indices used by all evaluators.

Usage:
    from parse_gamestate import parse
    from ck3.gamestate import GameState

    with open("murchad.txt", encoding="utf-8", errors="ignore") as f:
        raw = parse(f.read())

    gs = GameState(raw)
    char = gs.character(18269)
"""

from __future__ import annotations
from typing import Any


class GameState:
    def __init__(self, raw: dict):
        self._raw = raw

        # ------------------------------------------------------------------ #
        # Core tables (direct references into the parsed dict)
        # ------------------------------------------------------------------ #
        self.living: dict        = raw.get("living", {})
        self.dead: dict          = raw.get("dead_unprunable", {})
        self.traits_lookup: list = raw.get("traits_lookup", [])

        _lt_root                 = raw.get("landed_titles", {})
        self.titles: dict        = _lt_root.get("landed_titles", {})

        _dyn_root                = raw.get("dynasties", {})
        self.dynasty_houses: dict = _dyn_root.get("dynasty_house", {})
        self.dynasties: dict      = _dyn_root.get("dynasties", {})

        _armies_root             = raw.get("armies", {})
        self.armies: dict        = _armies_root.get("armies", {})
        self.regiments: dict     = _armies_root.get("regiments", {})
        self.army_regiments: dict = _armies_root.get("army_regiments", {})

        self.units: dict         = raw.get("units", {})
        self.provinces: dict     = raw.get("provinces", {})

        _wars_root               = raw.get("wars", {})
        self.active_wars: dict   = _wars_root.get("active_wars", {})

        _rel_root                = raw.get("religion", {})
        self.faiths: dict        = _rel_root.get("faiths", {})
        self.religions: dict     = _rel_root.get("religions", {})

        _cult_root               = raw.get("culture_manager", {})
        self.cultures: dict      = _cult_root.get("cultures", {})

        self.vassal_contracts: dict = raw.get("vassal_contracts", {}).get("database", {})
        self.active_relations: list = _ensure_list(raw.get("relations", {}).get("active_relations", []))
        self.factions: dict      = raw.get("faction_manager", {}).get("factions", {})

        self.date: str           = raw.get("date", "")
        _played = raw.get("played_character", {})
        if isinstance(_played, list):
            _played = _played[0]   # duplicate key merge; all entries are identical
        self.played_character_id: int = _played.get("character")

        # ------------------------------------------------------------------ #
        # Indices (built once, reused by all evaluators)
        # ------------------------------------------------------------------ #
        self._titles_by_holder:    dict[int, list[str]] = {}   # char_id → [title_id, ...]
        self._units_by_owner:      dict[int, list[str]] = {}   # char_id → [unit_id, ...]
        self._wars_by_char:        dict[int, list[str]] = {}   # char_id → [war_id, ...]
        self._title_key_to_kingdom: dict[str, str] = {}        # title_key → kingdom_key
        self._contracts_by_liege:  dict[int, list[str]] = {}   # liege_id → [contract_id, ...]
        self._contract_by_vassal:  dict[int, str] = {}         # vassal_id → contract_id
        self._built = False

    # ---------------------------------------------------------------------- #
    # Public helpers
    # ---------------------------------------------------------------------- #

    def build_indices(self):
        """Build all lookup indices. Called lazily on first use."""
        if self._built:
            return
        self._build_title_index()
        self._build_unit_index()
        self._build_war_index()
        self._build_title_key_to_kingdom_index()
        self._build_contract_indices()
        self._built = True

    def title_key_to_kingdom(self, title_key: str) -> str:
        """
        Return the kingdom-tier (k_*) or empire-tier (e_*) title key that
        is the de-jure liege of *title_key*.  Returns *title_key* itself if
        it is already kingdom/empire tier, or if the hierarchy is unknown.
        """
        self.build_indices()
        return self._title_key_to_kingdom.get(title_key, title_key)

    def character(self, char_id: int | str) -> dict | None:
        """Return the living character record for *char_id*, or None."""
        return self.living.get(str(char_id))

    def title(self, title_id: int | str) -> dict | None:
        """Return the landed_title record for *title_id* (integer key)."""
        return self.titles.get(str(title_id))

    def title_by_key(self, key: str) -> dict | None:
        """Return the first title whose 'key' field matches *key* (e.g. 'k_ireland')."""
        for t in self.titles.values():
            if isinstance(t, dict) and t.get("key") == key:
                return t
        return None

    def trait_name(self, trait_id: int) -> str:
        """Resolve a trait integer to its string name."""
        try:
            return self.traits_lookup[trait_id]
        except (IndexError, TypeError):
            return f"trait_{trait_id}"

    def trait_names(self, trait_ids: list[int]) -> list[str]:
        return [self.trait_name(t) for t in trait_ids]

    def faith(self, faith_id: int | str) -> dict | None:
        return self.faiths.get(str(faith_id))

    def religion(self, religion_id: int | str) -> dict | None:
        return self.religions.get(str(religion_id))

    def culture(self, culture_id: int | str) -> dict | None:
        return self.cultures.get(str(culture_id))

    def dynasty_house(self, house_id: int | str) -> dict | None:
        return self.dynasty_houses.get(str(house_id))

    # ---------------------------------------------------------------------- #
    # Indexed lookups (require build_indices())
    # ---------------------------------------------------------------------- #

    def titles_held_by(self, char_id: int) -> list[dict]:
        """All title records directly held by char_id."""
        self.build_indices()
        return [self.titles[tid] for tid in self._titles_by_holder.get(char_id, [])
                if tid in self.titles]

    def units_owned_by(self, char_id: int) -> list[dict]:
        """All unit records owned by char_id."""
        self.build_indices()
        return [self.units[uid] for uid in self._units_by_owner.get(char_id, [])
                if uid in self.units]

    def wars_involving(self, char_id: int) -> list[tuple[str, dict]]:
        """List of (war_id, war_record) for all wars that include char_id."""
        self.build_indices()
        return [(wid, self.active_wars[wid])
                for wid in self._wars_by_char.get(char_id, [])
                if wid in self.active_wars]

    def army_for_unit(self, unit: dict) -> dict | None:
        """Given a unit record, return the army record it belongs to."""
        army_id = unit.get("army")
        if army_id is None:
            return None
        return self.armies.get(str(army_id))

    def regiment_strength(self, regiment_id: int | str) -> dict:
        """Return {'current': int, 'max': int, 'power': int} for a regiment."""
        ar = self.army_regiments.get(str(regiment_id))
        if not ar or ar == "none":
            return {"current": 0, "max": 0, "power": 0}
        cached = ar.get("cached", {}) if isinstance(ar, dict) else {}
        return {
            "current": cached.get("current", 0),
            "max":     cached.get("max", 0),
            "power":   cached.get("power", 0),
        }

    def army_strength(self, army_id: int | str) -> dict:
        """Aggregate strength across all regiments in an army."""
        army = self.armies.get(str(army_id))
        if not army or not isinstance(army, dict):
            return {"current": 0, "max": 0, "power": 0}
        total = {"current": 0, "max": 0, "power": 0}
        for reg_id in army.get("regiments", []):
            s = self.regiment_strength(reg_id)
            for k in total:
                total[k] += s[k]
        return total

    # ---------------------------------------------------------------------- #
    # Index builders (private)
    # ---------------------------------------------------------------------- #

    def _build_title_index(self):
        for tid, t in self.titles.items():
            if not isinstance(t, dict):
                continue
            holder = t.get("holder")
            if holder is not None:
                self._titles_by_holder.setdefault(int(holder), []).append(tid)

    def _build_unit_index(self):
        for uid, u in self.units.items():
            if not isinstance(u, dict):
                continue
            owner = u.get("owner")
            if owner is not None:
                self._units_by_owner.setdefault(int(owner), []).append(uid)

    def _build_war_index(self):
        for wid, war in self.active_wars.items():
            if not isinstance(war, dict):
                continue
            for side in ("attacker", "defender"):
                side_data = war.get(side, {})
                for p in _ensure_list(side_data.get("participants", [])):
                    char_id = p.get("character") if isinstance(p, dict) else None
                    if char_id is not None:
                        self._wars_by_char.setdefault(int(char_id), []).append(wid)

    def _build_contract_indices(self):
        for cid, c in self.vassal_contracts.items():
            if not isinstance(c, dict):
                continue
            vassal = c.get("vassal")
            liege  = c.get("liege")
            if vassal is not None and liege is not None:
                self._contracts_by_liege.setdefault(int(liege), []).append(cid)
                self._contract_by_vassal[int(vassal)] = cid

    def contracts_for_liege(self, liege_id: int) -> list[dict]:
        """All vassal contracts where *liege_id* is the liege."""
        self.build_indices()
        return [self.vassal_contracts[cid]
                for cid in self._contracts_by_liege.get(liege_id, [])
                if cid in self.vassal_contracts]

    def contract_for_vassal(self, vassal_id: int) -> dict | None:
        """The single vassal contract for *vassal_id* (each vassal has at most one liege)."""
        self.build_indices()
        cid = self._contract_by_vassal.get(vassal_id)
        return self.vassal_contracts.get(cid) if cid else None

    def _build_title_key_to_kingdom_index(self):
        """
        Build a mapping from every title key to its de-jure kingdom (k_* / e_*)
        ancestor by traversing the de_jure_liege chain.
        """
        # Pass 1: collect per-title {key, de_jure_liege_key}
        # Use title ID strings as the canonical identifier.
        id_to_key: dict[str, str] = {}
        id_to_liege_id: dict[str, str] = {}
        key_to_id: dict[str, str] = {}

        for tid_str, t in self.titles.items():
            if not isinstance(t, dict):
                continue
            key = t.get("key", "")
            if key:
                id_to_key[tid_str] = key
                key_to_id[key] = tid_str
            liege = t.get("de_jure_liege")
            if liege is not None:
                id_to_liege_id[tid_str] = str(liege)

        # Pass 2: for each title, walk up until we hit k_* / e_* (max 6 steps)
        def _find_kingdom(tid_str: str, depth: int = 0) -> str:
            key = id_to_key.get(tid_str, "")
            if not key:
                return ""
            if key.startswith("k_") or key.startswith("e_"):
                return key
            if depth >= 6:
                return key
            liege_id = id_to_liege_id.get(tid_str)
            if liege_id is None:
                return key
            return _find_kingdom(liege_id, depth + 1)

        for tid_str, key in id_to_key.items():
            kingdom_key = _find_kingdom(tid_str)
            if kingdom_key:
                self._title_key_to_kingdom[key] = kingdom_key


# --------------------------------------------------------------------------- #
# Utilities
# --------------------------------------------------------------------------- #

def _ensure_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]
