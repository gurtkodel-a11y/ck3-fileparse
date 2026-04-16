"""
ck3.evaluators.terrain
~~~~~~~~~~~~~~~~~~~~~~
Level-1 terrain evaluator: characterises the geographic and economic
composition of a character's realm and their neighbours' territories.

Because terrain type is stored in static game data files (not the save),
terrain character is inferred from building types.  CK3's building system
is terrain-gated: only forested provinces can build logging camps, only
coastal ones can build tradeports, etc.  These serve as reliable proxies.

Usage:
    from ck3.evaluators.terrain import TerrainEvaluator
    ev = TerrainEvaluator(gs, char_id=32674)
    report = ev.report()
    print(report.summary())
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from ck3.gamestate import GameState
from ck3.names import decode_name, char_label, title_ruler_label
from ck3.geography import kingdom_to_region
from ck3.province_data import (
    load_province_terrain, load_barony_provinces, load_county_capitals,
    load_building_categories,
    WATER_TERRAIN, _DEFAULT_TERRAIN,
)
from ck3.evaluators.base import _ensure_list, title_place



_HOLDING_TYPE_SHORT = {
    "castle_holding":          "castle",
    "city_holding":            "city",
    "church_holding":          "church",
    "tribal_holding":          "tribal",
    "temple_citadel_holding":  "temple_citadel",
    "nomad_holding":           "nomad",
    "herder_holding":          "herder",
}

# Maps the prefix of a holding's primary_building → short holding type.
# Source: game/common/holdings/00_holdings.txt (primary_building field).
# Used as a fallback when the province record lacks an explicit holding.type.
_PRIMARY_BUILDING_TYPE: dict[str, str] = {
    "castle":        "castle",
    "city":          "city",
    "temple":        "church",
    "tribe":         "tribal",
    "temple_citadel": "temple_citadel",
    "nomadic_camp":  "nomad",
    "herder_camp":   "herder",
}

# Display abbreviation for each holding type (used in compact vassal table).
_TYPE_ABBREV: dict[str, str] = {
    "castle":          "cas",
    "city":            "cit",
    "church":          "chu",
    "tribal":          "tri",
    "temple_citadel":  "tct",
    "nomad":           "nom",
    "herder":          "hrd",
}

_CONTROL_WARN = 75   # county control below this is flagged


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass
class HoldingProfile:
    """Detailed profile of one barony/holding."""
    barony_key: str
    county_key: str
    barony_name: str           # decoded display name (from title_name_data, falling back to key)
    county_name: str           # decoded display name (from title_name_data, falling back to key)
    holding_type: str          # short form: castle / city / church / tribal / unknown
    terrain: str               # from game/common/province_terrain (plains, hills, mountains, …)
    fort_level: int
    development: int
    development_progress: float
    county_control: float
    buildings: list[str]       # raw building type strings present
    building_cats: dict[str, int]   # category → count of buildings
    special_features: list[str]     # points_of_interest strings


@dataclass
class DomainSummary:
    """Aggregate statistics across all of the player's directly-held holdings."""
    total_holdings: int
    type_counts: dict[str, int]        # holding_type → count
    total_development: int
    avg_development: float
    low_control: list[str]             # county keys with control < _CONTROL_WARN
    terrain_counts: dict[str, int]     # terrain_type → count of holdings
    category_totals: dict[str, int]    # building category → total building count


@dataclass
class VassalProfile:
    """Terrain/holding summary for one direct vassal."""
    char_id: int
    char_name: str             # given name + house only (no title clause)
    highest_title_key: str
    title_label: str           # e.g. "Duke of Brno" from title_ruler_label
    holding_count: int
    type_counts: dict[str, int]
    total_development: int
    avg_development: float
    low_control_count: int
    terrain_counts: dict[str, int]


@dataclass
class TerrainReport:
    """Full level-1 terrain report for one character."""
    char_id: int
    char_name: str
    game_date: str
    domain_holdings: list[HoldingProfile]
    domain_summary: DomainSummary
    vassal_profiles: list[VassalProfile]

    def summary(self) -> str:
        lines = [
            f"Terrain Report — {self.char_name} (id {self.char_id})  [{self.game_date}]",
            "=" * 70,
        ]

        # ── Domain Summary ─────────────────────────────────────────────── #
        ds = self.domain_summary
        type_str = "  ".join(
            f"{cnt} {t}" for t, cnt in sorted(ds.type_counts.items(), key=lambda x: -x[1])
        )
        terrain_str = "  ".join(
            f"{t}×{cnt}" for t, cnt in sorted(ds.terrain_counts.items(), key=lambda x: -x[1])
        ) or "—"
        lines += [
            "\n--- Domain Overview ---",
            f"  Holdings:        {ds.total_holdings}  ({type_str})",
            f"  Development:     {ds.total_development} total  ({ds.avg_development:.1f} avg per holding)",
            f"  Terrain:         {terrain_str}",
        ]
        if ds.low_control:
            lines.append(f"  Low control (<{_CONTROL_WARN}):  " + ", ".join(title_place(k) for k in ds.low_control))

        cat_parts = []
        for cat in (
            "fortification", "military", "agriculture", "commerce",
            "resource", "religious", "urban", "tribal",
            "administrative", "duchy_capital", "special",
        ):
            n = ds.category_totals.get(cat, 0)
            if n:
                cat_parts.append(f"{cat} {n}")
        if cat_parts:
            lines.append(f"  Buildings:       " + "  ".join(cat_parts))

        # ── Per-holding detail ─────────────────────────────────────────── #
        lines.append(f"\n--- Domain Holdings ({len(self.domain_holdings)}) ---")
        lines.append(
            f"  {'Barony':<28}  {'County':<20}  {'Type':<7}  "
            f"{'Dev':>3}  {'Ctrl':>4}  {'Fort':>4}  Terrain / Notable"
        )
        lines.append("  " + "-" * 90)
        for h in sorted(self.domain_holdings, key=lambda x: (-x.development, x.county_key)):
            specials = "  [" + " ".join(h.special_features) + "]" if h.special_features else ""
            ctrl_str = f"{h.county_control:.0f}%" if h.county_control else " —"
            fort_str = str(h.fort_level) if h.fort_level else "—"
            lines.append(
                f"  {h.barony_name:<28}  {h.county_name:<20}  {h.holding_type:<7}  "
                f"{h.development:>3}  {ctrl_str:>5}  {fort_str:>4}  {h.terrain}{specials}"
            )

        # ── Vassal Profiles ────────────────────────────────────────────── #
        if self.vassal_profiles:
            lines.append(f"\n--- Vassal Territories ({len(self.vassal_profiles)}) ---")
            lines.append(
                f"  {'Name':<28}  {'Title':<24}  {'Hold':>4}  "
                f"{'Dev':>3}  {'AvgDev':>6}  {'LowCtrl':>7}  Terrain"
            )
            lines.append("  " + "-" * 90)
            for v in sorted(self.vassal_profiles, key=lambda x: -x.total_development):
                terrain = "  ".join(
                    f"{t}×{cnt}" for t, cnt in sorted(v.terrain_counts.items(), key=lambda x: -x[1])
                ) or "—"
                lines.append(
                    f"  {v.char_name:<28}  {v.title_label:<24}  "
                    f"{v.holding_count:>4}  {v.total_development:>3}  "
                    f"{v.avg_development:>6.1f}  {v.low_control_count:>7}  {terrain}"
                )

        return "\n".join(lines)

    # ---------------------------------------------------------------------- #
    # Query methods — targeted follow-up after seeing the report
    # ---------------------------------------------------------------------- #

    def holdings_by_terrain(self, terrain: str) -> list[HoldingProfile]:
        """All domain holdings on a given terrain type (e.g. 'mountains', 'plains')."""
        return [h for h in self.domain_holdings if h.terrain == terrain]

    def holdings_by_type(self, holding_type: str) -> list[HoldingProfile]:
        """All domain holdings of a given type: 'castle', 'city', 'church', 'tribal', etc."""
        return [h for h in self.domain_holdings if h.holding_type == holding_type]

    def holdings_with_category(self, category: str) -> list[HoldingProfile]:
        """Domain holdings that have at least one building in the given category."""
        return [h for h in self.domain_holdings if h.building_cats.get(category, 0) > 0]

    def special_holdings(self) -> list[HoldingProfile]:
        """Domain holdings with special features (wonders, holy sites, points of interest)."""
        return [h for h in self.domain_holdings if h.special_features]

    def holding_detail(self, barony_key: str) -> HoldingProfile | None:
        """Look up one domain holding by its barony key (e.g. 'b_prague')."""
        for h in self.domain_holdings:
            if h.barony_key == barony_key:
                return h
        return None

    def vassal_profile(self, char_id: int) -> VassalProfile | None:
        """Look up a direct vassal's summary profile by character ID."""
        for v in self.vassal_profiles:
            if v.char_id == char_id:
                return v
        return None


# --------------------------------------------------------------------------- #
# Evaluator
# --------------------------------------------------------------------------- #

class TerrainEvaluator:
    def __init__(self, gs: GameState, char_id: int):
        self.gs = gs
        self.char_id = char_id
        gs.build_indices()

        # Cache county_manager data: county_key → {development, county_control, ...}
        cm = gs._raw.get("county_manager", {})
        self._county_data: dict[str, dict] = cm.get("counties", {})

        # Static lookups (loaded once from game files, cached globally)
        self._terrain_map: dict[int, str] = load_province_terrain()
        self._barony_provinces: dict[str, int] = load_barony_provinces()
        self._county_capitals: dict[str, str] = load_county_capitals()

    def report(self) -> TerrainReport:
        gs = self.gs
        char = gs.character(self.char_id)
        if char is None:
            raise ValueError(f"Character {self.char_id} not found in living")

        char_name = char_label(char, gs, self.char_id)
        domain_holdings = self._profile_domain(char)
        domain_summary = self._summarise(domain_holdings)
        vassal_profiles = self._vassal_profiles()

        return TerrainReport(
            char_id=self.char_id,
            char_name=char_name,
            game_date=gs.date,
            domain_holdings=domain_holdings,
            domain_summary=domain_summary,
            vassal_profiles=vassal_profiles,
        )

    def vassal_holdings(self, vassal_id: int) -> list[HoldingProfile]:
        """
        Full per-holding profile for one direct vassal.

        VassalProfile in the report carries only aggregate statistics; call
        this when per-holding detail (buildings, fort level, control, terrain)
        is needed for a specific vassal.
        """
        vassal_char = self.gs.character(vassal_id)
        if not vassal_char:
            return []
        return self._profile_domain(vassal_char)

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    def _county_key_for(self, title: dict) -> str:
        """Walk de_jure_liege upward until we find a c_* key."""
        gs = self.gs
        key = title.get("key", "")
        if key.startswith("c_"):
            return key
        liege_id = title.get("de_jure_liege")
        if liege_id is None:
            return ""
        liege = gs.title(liege_id)
        if not liege:
            return ""
        liege_key = liege.get("key", "")
        return liege_key if liege_key.startswith("c_") else ""

    def _buildings_from_province(self, prov: dict) -> list[str]:
        """Extract all building type strings from a province's holding."""
        holding = prov.get("holding", {})
        if not isinstance(holding, dict):
            return []
        result = []
        for slot in _ensure_list(holding.get("buildings", [])):
            if isinstance(slot, dict):
                btype = slot.get("type")
                if btype:
                    result.append(btype)
            elif isinstance(slot, list):
                for item in slot:
                    if isinstance(item, dict):
                        btype = item.get("type")
                        if btype:
                            result.append(btype)
        return result

    def _classify_buildings(self, buildings: list[str]) -> dict[str, int]:
        """Return category → count for a list of building types."""
        cat_map = load_building_categories()
        cats: dict[str, int] = {}
        for btype in buildings:
            cat = cat_map.get(btype)
            if cat:
                cats[cat] = cats.get(cat, 0) + 1
        return cats

    def _profile_one(self, title_id: int | str) -> HoldingProfile | None:
        """Build a HoldingProfile for one county/barony title from the player's domain."""
        gs = self.gs
        title = gs.title(title_id)
        if not isinstance(title, dict):
            return None

        # Skip duchy/kingdom/empire titles — they appear in landed_data.domain
        # as the seat entry and share a province_id with their capital county,
        # which would create a duplicate holding row.
        key_check = title.get("key", "")
        if key_check and key_check[0] in ("d", "k", "e"):
            return None

        barony_key = key_check or str(title_id)
        province_id = title.get("capital")
        county_key = self._county_key_for(title)

        # Province data
        prov: dict = {}
        if province_id is not None:
            prov = gs.provinces.get(str(province_id), {}) or {}
        holding = prov.get("holding", {}) if isinstance(prov, dict) else {}
        raw_type = holding.get("type", "") if isinstance(holding, dict) else ""
        holding_type = _HOLDING_TYPE_SHORT.get(raw_type, raw_type or "")

        buildings = self._buildings_from_province(prov)
        building_cats = self._classify_buildings(buildings)

        # Fallback: if the province record has no usable holding.type, infer
        # the type from whichever primary building is present in the slot.
        # Primary buildings (castle_01, city_01, temple_01, tribe_01, …) are
        # always present when a holding exists and uniquely identify its type.
        if not holding_type or holding_type not in _HOLDING_TYPE_SHORT.values():
            for btype in buildings:
                inferred = _PRIMARY_BUILDING_TYPE.get(_btype_prefix(btype))
                if inferred:
                    holding_type = inferred
                    break
            else:
                holding_type = holding_type or "unknown"

        fort_level = int(prov.get("fort_level", 0)) if isinstance(prov, dict) else 0
        special_features = _ensure_list(prov.get("points_of_interest", [])) if isinstance(prov, dict) else []

        # Terrain: resolve through barony → map_province_id → terrain string.
        # Domain titles may be c_* (county seats) or b_* (baronies).
        # For counties, use the capital barony from the static landed_titles.
        lookup_key = barony_key
        if barony_key.startswith("c_"):
            lookup_key = self._county_capitals.get(barony_key, barony_key)
        map_prov_id = self._barony_provinces.get(lookup_key)
        terrain = self._terrain_map.get(map_prov_id, _DEFAULT_TERRAIN) if map_prov_id is not None else _DEFAULT_TERRAIN

        # Skip water provinces (sea zones in the domain list — shouldn't normally occur)
        if terrain in WATER_TERRAIN:
            return None

        # Decoded display names — use title_name_data.name + decode_name when available,
        # falling back to the key-stripping approach.
        name_data = title.get("title_name_data", {}) if isinstance(title, dict) else {}
        raw_barony_name = name_data.get("name", "") if isinstance(name_data, dict) else ""
        barony_name = decode_name(raw_barony_name) if raw_barony_name else title_place(barony_key)
        # County title record requires a key-lookup (O(n)); key-stripping is fine here.
        county_name = title_place(county_key)

        # County data
        county = self._county_data.get(county_key, {})
        development = int(county.get("development", 0))
        dev_progress = float(county.get("development_progress", 0))
        control = float(county.get("county_control", 100))

        return HoldingProfile(
            barony_key=barony_key,
            county_key=county_key,
            barony_name=barony_name,
            county_name=county_name,
            holding_type=holding_type,
            terrain=terrain,
            fort_level=fort_level,
            development=development,
            development_progress=dev_progress,
            county_control=control,
            buildings=buildings,
            building_cats=building_cats,
            special_features=special_features,
        )

    def _profile_domain(self, char: dict) -> list[HoldingProfile]:
        ld = char.get("landed_data", {})
        domain_ids = _ensure_list(ld.get("domain", []))
        profiles = []
        seen_provinces: set[int] = set()
        for tid in domain_ids:
            hp = self._profile_one(tid)
            if not hp:
                continue
            # Deduplicate: duchy titles and their capital county share the same
            # province_id, so after duchy-tier skipping this shouldn't trigger,
            # but guard anyway.
            title = self.gs.title(tid)
            prov_id = title.get("capital") if isinstance(title, dict) else None
            if prov_id is not None:
                if prov_id in seen_provinces:
                    continue
                seen_provinces.add(prov_id)
            profiles.append(hp)
        return profiles

    def _summarise(self, holdings: list[HoldingProfile]) -> DomainSummary:
        type_counts: dict[str, int] = {}
        terrain_counts: dict[str, int] = {}
        cat_totals: dict[str, int] = {}
        low_control: list[str] = []
        total_dev = 0

        for h in holdings:
            type_counts[h.holding_type] = type_counts.get(h.holding_type, 0) + 1
            total_dev += h.development
            if h.county_control < _CONTROL_WARN:
                if h.county_key and h.county_key not in low_control:
                    low_control.append(h.county_key)
            terrain_counts[h.terrain] = terrain_counts.get(h.terrain, 0) + 1
            for cat, cnt in h.building_cats.items():
                cat_totals[cat] = cat_totals.get(cat, 0) + cnt

        n = len(holdings)
        return DomainSummary(
            total_holdings=n,
            type_counts=type_counts,
            total_development=total_dev,
            avg_development=total_dev / n if n else 0.0,
            low_control=sorted(low_control),
            terrain_counts=terrain_counts,
            category_totals=cat_totals,
        )

    def _vassal_profiles(self) -> list[VassalProfile]:
        gs = self.gs
        profiles = []
        tier_order = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}

        for contract in gs.contracts_for_liege(self.char_id):
            if not isinstance(contract, dict):
                continue
            vassal_id = contract.get("vassal")
            if vassal_id is None:
                continue
            vassal_char = gs.character(vassal_id)
            if not vassal_char:
                continue

            # Highest title (save the record for title_ruler_label)
            best_key = ""
            best_title = None
            best_order = 99
            for t in gs.titles_held_by(vassal_id):
                if not isinstance(t, dict):
                    continue
                k = t.get("key", "")
                o = tier_order.get(k[0], 9) if k else 9
                if o < best_order:
                    best_order = o
                    best_key = k
                    best_title = t

            is_female = vassal_char.get("female") == "yes"
            title_label = title_ruler_label(best_title, female=is_female) if best_title else title_place(best_key)

            # Holdings profile
            holdings = self._profile_domain(vassal_char)
            if not holdings:
                continue
            summary = self._summarise(holdings)

            profiles.append(VassalProfile(
                char_id=vassal_id,
                char_name=char_label(vassal_char, gs, vassal_id, include_title=False),
                highest_title_key=best_key,
                title_label=title_label,
                holding_count=summary.total_holdings,
                type_counts=summary.type_counts,
                total_development=summary.total_development,
                avg_development=summary.avg_development,
                low_control_count=len(summary.low_control),
                terrain_counts=summary.terrain_counts,
            ))

        return profiles


# --------------------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------------------- #

def _btype_prefix(btype: str) -> str:
    """Strip trailing _01/_02/… level suffix to get the building family prefix."""
    parts = btype.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return btype


# --------------------------------------------------------------------------- #
# Standalone province / terrain utilities
#
# These work purely from static game data (no GameState needed) and are
# intended as building blocks for geography.py path and travel calculations.
# --------------------------------------------------------------------------- #

def terrain_for_key(key: str) -> str:
    """
    Return the terrain type string for a barony or county key.

    For county keys (c_*) the capital barony is resolved first via the static
    landed_titles data.  Returns _DEFAULT_TERRAIN ('plains') when the key is
    not found in game data.

    Examples::
        terrain_for_key('b_prague')     → 'plains'
        terrain_for_key('c_bohemia')    → 'plains'  (via capital barony)
        terrain_for_key('b_innsbruck')  → 'mountains'
    """
    lookup = key
    if key.startswith("c_"):
        lookup = load_county_capitals().get(key, key)
    prov_id = load_barony_provinces().get(lookup)
    if prov_id is None:
        return _DEFAULT_TERRAIN
    return load_province_terrain().get(prov_id, _DEFAULT_TERRAIN)


def terrain_summary(keys: list[str]) -> dict[str, int]:
    """
    Return terrain-type counts for a collection of barony or county keys.

    Accepts a mix of b_* and c_* keys.  Water terrain (sea, coastal_sea) is
    excluded.  Intended for characterising the terrain along a route or within
    a region — geography.py can pass a path of province keys here to get a
    terrain breakdown.

    Example::
        terrain_summary(['b_prague', 'b_brno', 'b_innsbruck'])
        → {'plains': 2, 'mountains': 1}
    """
    counts: dict[str, int] = {}
    for key in keys:
        t = terrain_for_key(key)
        if t not in WATER_TERRAIN:
            counts[t] = counts.get(t, 0) + 1
    return counts


