"""
ck3.advisors.steward
~~~~~~~~~~~~~~~~~~~~
Steward advisor — domain management, development, and buildings.

Draws on:
  - TerrainReport   (holdings, dev, control, terrain, building categories)

Uses TerrainReport query methods for targeted follow-up:
  - holdings_by_type(), holdings_with_category(), holdings_by_terrain()
"""

from __future__ import annotations
from dataclasses import dataclass, field

from ck3.advisors.base import BaseAdvisor, Priority


# --------------------------------------------------------------------------- #
# Output dataclass
# --------------------------------------------------------------------------- #

@dataclass
class StewardBrief:
    """Structured output from the Steward advisor."""
    char_name: str
    game_date: str

    # Domain composition
    total_holdings: int
    type_counts: dict          # holding_type → count
    total_dev: int
    avg_dev: float
    terrain_counts: dict
    building_cats: dict

    # Highlights
    highest_dev: list[dict]    # [{barony, county, dev, terrain}]
    lowest_dev: list[dict]
    low_control: list[str]     # county keys with control < threshold
    building_gaps: list[str]   # category names missing from domain entirely

    # Vassal domain overview
    vassal_dev_total: int
    vassal_dev_avg: float
    vassal_low_control_count: int

    # Analysis
    observations: list[str]
    priorities: list[Priority]

    def summary(self) -> str:
        lines = [
            f"Steward's Brief — {self.char_name}  [{self.game_date}]",
            "=" * 70,
        ]

        # ── Domain overview ───────────────────────────────────────────────── #
        type_str = "  ".join(
            f"{cnt} {t}" for t, cnt in sorted(self.type_counts.items(), key=lambda x: -x[1])
        )
        terrain_str = "  ".join(
            f"{t}×{cnt}" for t, cnt in sorted(self.terrain_counts.items(), key=lambda x: -x[1])
        ) or "—"
        lines += [
            "\n--- Domain Overview ---",
            f"  Holdings:    {self.total_holdings}  ({type_str})",
            f"  Development: {self.total_dev} total  ({self.avg_dev:.1f} avg)",
            f"  Terrain:     {terrain_str}",
        ]

        cat_parts = [f"{cat} {n}" for cat, n in sorted(self.building_cats.items()) if n]
        if cat_parts:
            lines.append(f"  Buildings:   " + "  ".join(cat_parts))

        if self.low_control:
            lines.append(
                f"  Low control: {', '.join(self.low_control)}"
            )

        # ── Development highlights ─────────────────────────────────────────── #
        lines.append("\n--- Development Priorities ---")
        lines.append(f"  {'Holding':<28}  {'County':<20}  Dev  Terrain")
        if self.lowest_dev:
            lines.append("  Lowest development (invest here first):")
            for h in self.lowest_dev:
                lines.append(f"    {h['barony']:<26}  {h['county']:<20}  {h['dev']:>3}  {h['terrain']}")
        if self.highest_dev:
            lines.append("  Best-developed (anchor holdings):")
            for h in self.highest_dev:
                lines.append(f"    {h['barony']:<26}  {h['county']:<20}  {h['dev']:>3}  {h['terrain']}")

        # ── Building gaps ─────────────────────────────────────────────────── #
        if self.building_gaps:
            lines.append(f"\n  Building categories absent from domain: {', '.join(self.building_gaps)}")

        # ── Vassal domains ────────────────────────────────────────────────── #
        lines += [
            f"\n--- Vassal Domain Summary ---",
            f"  Total vassal dev: {self.vassal_dev_total}  avg {self.vassal_dev_avg:.1f}",
        ]
        if self.vassal_low_control_count:
            lines.append(
                f"  Vassal low-control counties: {self.vassal_low_control_count} "
                "(may suppress levy contribution)"
            )

        # ── Observations & priorities ─────────────────────────────────────── #
        if self.observations:
            lines.append("\n--- Assessment ---")
            for obs in self.observations:
                lines.append(f"  {obs}")

        lines.append("\n--- Priorities ---")
        lines.append(self._fmt_priorities(self.priorities))

        return "\n".join(lines)

    @staticmethod
    def _fmt_priorities(priorities):
        from ck3.advisors.base import BaseAdvisor
        return BaseAdvisor._fmt_priorities(priorities)


# --------------------------------------------------------------------------- #
# Advisor
# --------------------------------------------------------------------------- #

_EXPECTED_CATEGORIES = {
    "fortification", "military", "agriculture", "commerce", "religious", "urban",
}
_DEV_TARGET = 15         # holdings below this are candidates for investment


class StewardAdvisor(BaseAdvisor):
    role = "Steward"

    def advise(self) -> StewardBrief:
        ter = self.council.terrain_report
        ds = ter.domain_summary
        holdings = ter.domain_holdings

        # ── Development highlights ─────────────────────────────────────────── #
        sorted_by_dev = sorted(holdings, key=lambda h: h.development)
        lowest = [
            {"barony": h.barony_name, "county": h.county_name,
             "dev": h.development, "terrain": h.terrain}
            for h in sorted_by_dev[:3]
        ]
        highest = [
            {"barony": h.barony_name, "county": h.county_name,
             "dev": h.development, "terrain": h.terrain}
            for h in sorted_by_dev[-3:][::-1]
        ]

        # ── Building gaps ─────────────────────────────────────────────────── #
        present_cats = {cat for cat, n in ds.category_totals.items() if n > 0}
        # Only flag gaps in categories achievable on the holding types present
        holding_types = set(ds.type_counts.keys())
        relevant_expected = _EXPECTED_CATEGORIES.copy()
        if "castle" not in holding_types and "tribal" not in holding_types:
            relevant_expected.discard("fortification")
            relevant_expected.discard("military")
        gaps = sorted(relevant_expected - present_cats)

        # ── Vassal summary ─────────────────────────────────────────────────── #
        v_devs = [v.total_development for v in ter.vassal_profiles]
        vassal_dev_total = sum(v_devs)
        vassal_dev_avg = vassal_dev_total / len(v_devs) if v_devs else 0.0
        vassal_low_ctrl = sum(v.low_control_count for v in ter.vassal_profiles)

        # ── Observations ─────────────────────────────────────────────────── #
        observations = []

        if ds.avg_development < 10:
            observations.append(
                f"Domain development is low (avg {ds.avg_development:.1f}). "
                "Prioritise development investment before expanding."
            )
        elif ds.avg_development >= 14:
            observations.append(
                f"Domain is well-developed (avg {ds.avg_development:.1f}). "
                "Focus shifts toward building breadth and specialist structures."
            )

        if ds.low_control:
            observations.append(
                f"{len(ds.low_control)} county(-ies) with low control "
                "suppress levy and tax income. Assign marshal to improve control."
            )

        if gaps:
            observations.append(
                f"Building categories not yet present: {', '.join(gaps)}. "
                "Diversifying would improve income and force quality."
            )

        # terrain-type specific note
        farmland_count = ds.terrain_counts.get("farmlands", 0)
        if farmland_count > 0:
            farm_holdings = ter.holdings_by_terrain("farmlands")
            ag_covered = [h for h in farm_holdings if h.building_cats.get("agriculture", 0) > 0]
            if len(ag_covered) < farmland_count:
                observations.append(
                    f"{farmland_count - len(ag_covered)} farmland holding(s) lack agriculture "
                    "buildings — highest-yield investment available."
                )

        if vassal_low_ctrl > 0:
            observations.append(
                f"{vassal_low_ctrl} vassal holding(s) have low control, "
                "which may suppress levy contributions to your armies."
            )

        # ── Priorities ────────────────────────────────────────────────────── #
        priorities: list[Priority] = []

        if ds.low_control:
            priorities.append(Priority(
                f"Raise county control in: {', '.join(ds.low_control[:3])}.",
                "high",
                "Assign marshal; consider holding local court.",
            ))

        under_target = [h for h in holdings if h.development < _DEV_TARGET]
        if under_target:
            focus = min(under_target, key=lambda h: h.development)
            priorities.append(Priority(
                f"Develop {focus.barony_name} ({focus.county_name}) — "
                f"currently at {focus.development}.",
                "medium",
                f"Terrain: {focus.terrain}. Target dev ≥ {_DEV_TARGET} before branching into new holdings.",
            ))

        if "agriculture" in gaps or "commerce" in gaps:
            missing = [c for c in ("agriculture", "commerce") if c in gaps]
            priorities.append(Priority(
                f"Add {' and '.join(missing)} buildings to increase income base.",
                "medium",
            ))

        return StewardBrief(
            char_name=ter.char_name,
            game_date=ter.game_date,
            total_holdings=ds.total_holdings,
            type_counts=ds.type_counts,
            total_dev=ds.total_development,
            avg_dev=ds.avg_development,
            terrain_counts=ds.terrain_counts,
            building_cats=ds.category_totals,
            highest_dev=highest,
            lowest_dev=lowest,
            low_control=ds.low_control,
            building_gaps=gaps,
            vassal_dev_total=vassal_dev_total,
            vassal_dev_avg=vassal_dev_avg,
            vassal_low_control_count=vassal_low_ctrl,
            observations=observations,
            priorities=priorities,
        )
