"""
ck3.advisors.chancellor
~~~~~~~~~~~~~~~~~~~~~~~
Chancellor advisor — diplomacy, foreign relations, and internal politics.

Draws on:
  - RelationshipsReport  (vassals, alliances, liege, opinions, hooks)
  - MilitaryReport       (nearby rulers for external power assessments)
  - CultureReport        (cultural/linguistic affinities among neighbors)
"""

from __future__ import annotations
from dataclasses import dataclass, field

from ck3.advisors.base import BaseAdvisor, Priority


# --------------------------------------------------------------------------- #
# Output dataclass
# --------------------------------------------------------------------------- #

@dataclass
class ChancellorBrief:
    """Structured output from the Chancellor advisor."""
    char_name: str
    game_date: str

    # Hierarchical position
    is_independent: bool
    liege_name: str | None
    liege_title: str | None

    # Vassal opinion audit
    vassal_count: int
    vassal_opinion_buckets: dict   # "loyal" / "neutral" / "dissatisfied" / "unknown"

    # Alliances
    alliance_count: int
    alliance_summary: list[dict]   # [{name, titles, type}]
    strong_unallied: list[dict]    # zone-0/1 rulers with high power and no alliance

    # External landscape (zone 0-1, county+, sorted by power)
    key_external: list[dict]       # [{name, power, relation, faith, zone}]

    # Cultural/heritage neighbours
    same_heritage: list[str]       # culture names sharing heritage
    same_language: list[str]

    # Hooks held
    favor_hooks_held: int
    house_head_hooks_held: int
    hooks_held_on_player: int

    # Analysis
    observations: list[str]
    priorities: list[Priority]

    def summary(self) -> str:
        lines = [
            f"Chancellor's Brief — {self.char_name}  [{self.game_date}]",
            "=" * 70,
        ]

        # ── Position ─────────────────────────────────────────────────────── #
        if self.is_independent:
            lines.append("\n  Position: Independent ruler.")
        else:
            lines.append(f"\n  Position: Vassal of {self.liege_name} ({self.liege_title}).")

        # ── Vassal audit ─────────────────────────────────────────────────── #
        lines.append(f"\n--- Vassal Politics ({self.vassal_count} direct vassals) ---")
        for bucket, count in self.vassal_opinion_buckets.items():
            if count:
                lines.append(f"  {bucket:<14}: {count}")

        # ── Alliances ────────────────────────────────────────────────────── #
        lines.append(f"\n--- Alliances ({self.alliance_count}) ---")
        if self.alliance_summary:
            for a in self.alliance_summary:
                atype = "negotiated" if a.get("negotiated") else "dynastic"
                lines.append(f"  {a['name']:<28}  {', '.join(a['titles'][:2])}  [{atype}]")
        else:
            lines.append("  None.")

        if self.strong_unallied:
            lines.append(f"\n  Notable unallied neighbors (potential alliance targets):")
            for r in self.strong_unallied[:5]:
                lines.append(f"    {r['name']:<28}  {r['power']:,} power  {r['faith']}")

        # ── External landscape ───────────────────────────────────────────── #
        lines.append(f"\n--- Key External Rulers (zone 0–1) ---")
        for r in self.key_external[:12]:
            zone_str = "local " if r["zone"] == 0 else "nearby"
            lines.append(
                f"  {r['name']:<34}  {r['power']:>7,}  {zone_str}  "
                f"{r['relation']:<12}  {r['faith']}"
            )

        # ── Cultural affinities ──────────────────────────────────────────── #
        if self.same_heritage:
            lines.append(f"\n  Same heritage: {', '.join(self.same_heritage)}")
        if self.same_language:
            lines.append(f"  Same language: {', '.join(self.same_language)}")

        # ── Hooks ────────────────────────────────────────────────────────── #
        lines.append(
            f"\n  Hooks held: {self.favor_hooks_held} favor  "
            f"{self.house_head_hooks_held} house-head  |  "
            f"held on player: {self.hooks_held_on_player}"
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

_OPINION_LOYAL      = 30    # opinion ≥ this → loyal
_OPINION_DISSATISFIED = -10 # opinion ≤ this → dissatisfied


class ChancellorAdvisor(BaseAdvisor):
    role = "Chancellor"

    def advise(self) -> ChancellorBrief:
        rel = self.council.relationships_report
        mil = self.council.military_report
        cul = self.council.culture_report

        # ── Hierarchical position ─────────────────────────────────────────── #
        liege_name = liege_title = None
        if rel.liege_chain:
            top = rel.liege_chain[0]
            liege_name = top.char_name
            liege_title = top.highest_title_label

        # ── Vassal opinion audit ──────────────────────────────────────────── #
        # Buckets: use notable_opinions to characterise each vassal
        vassal_ids = {v.char_id for v in rel.direct_vassals}
        opinion_by_char = {}
        for op in rel.notable_opinions:
            if op.direction == "other_of_player" and op.other_id in vassal_ids:
                opinion_by_char[op.other_id] = op.total_value

        buckets = {"very loyal (>50)": 0, "loyal (0–50)": 0,
                   "neutral": 0, "dissatisfied (<0)": 0}
        for v in rel.direct_vassals:
            score = opinion_by_char.get(v.char_id)
            if score is None:
                buckets["neutral"] += 1
            elif score > 50:
                buckets["very loyal (>50)"] += 1
            elif score >= 0:
                buckets["loyal (0–50)"] += 1
            else:
                buckets["dissatisfied (<0)"] += 1

        # ── Alliances ─────────────────────────────────────────────────────── #
        allied_ids = {a.ally_id for a in rel.alliances}
        alliance_summary = [
            {
                "name": a.ally_name,
                "titles": a.ally_titles,
                "negotiated": a.is_negotiated,
            }
            for a in rel.alliances
        ]

        # Strong unallied neighbors (zone 0-1, county+, not a vassal or liege)
        liege_ids = {r.char_id for r in rel.liege_chain}
        vassal_ids_all = {v.char_id for v in rel.direct_vassals}
        strong_unallied = [
            {
                "name": r.char_name,
                "power": r.combat_power,
                "faith": r.faith_tag,
                "zone": r.geo_zone,
            }
            for r in mil.nearby_rulers
            if (r.geo_zone <= 1
                and r.political_relation == "geo_neighbor"
                and r.char_id not in allied_ids
                and r.char_id not in liege_ids
                and r.char_id not in vassal_ids_all
                and r.combat_power >= 50_000)
        ]
        strong_unallied.sort(key=lambda r: -r["power"])

        # ── Key external rulers ───────────────────────────────────────────── #
        key_external = [
            {
                "name": r.char_name,
                "power": r.combat_power,
                "relation": r.political_relation,
                "faith": r.faith_tag,
                "zone": r.geo_zone,
            }
            for r in mil.nearby_rulers
            if r.geo_zone <= 1 and r.political_relation not in ("vassal",)
        ]
        key_external.sort(key=lambda r: -r["power"])

        # ── Cultural affinities ───────────────────────────────────────────── #
        same_heritage = [
            c.name for c in cul.cultures
            if c.relation_to_player == "same_heritage" and c.zone <= 1
        ]
        same_language = [
            c.name for c in cul.cultures
            if c.relation_to_player == "same_language" and c.zone <= 1
        ]

        # ── Hooks ─────────────────────────────────────────────────────────── #
        favor_held = sum(1 for h in rel.hooks_held if h.hook_type == "favor_hook")
        house_held = sum(1 for h in rel.hooks_held if h.hook_type == "house_head_hook")
        on_player = len(rel.hooks_on_player)

        # ── Observations ─────────────────────────────────────────────────── #
        observations = []

        # Vassal loyalty
        diss = buckets["dissatisfied (<0)"]
        if diss > 0:
            observations.append(
                f"{diss} direct vassal(s) hold a negative opinion. "
                "Identify and address before discontent becomes factional."
            )
        elif buckets["very loyal (>50)"] >= len(rel.direct_vassals) // 2:
            observations.append("Vassal loyalty is broadly strong — a product of sustained cultivation.")

        # Alliance depth vs. local power
        total_allied_power = sum(
            r.combat_power for r in mil.nearby_rulers if r.political_relation == "ally"
        )
        if not rel.alliances:
            observations.append("No alliances — diplomatically isolated.")
        elif len(rel.alliances) == 1:
            observations.append(
                "Only one alliance. A single bond breaking would leave the realm isolated."
            )

        # Heritage neighbours — natural diplomatic partners
        if same_heritage:
            observations.append(
                f"Shared heritage with {', '.join(same_heritage[:3])} creates "
                "natural common ground for diplomatic approaches."
            )

        # Hook leverage
        total_hooks = favor_held + house_held
        if total_hooks >= 10:
            observations.append(
                f"{total_hooks} hooks held (favor: {favor_held}, house-head: {house_held}). "
                "Significant leverage for coercive diplomacy and internal control."
            )

        # ── Priorities ────────────────────────────────────────────────────── #
        priorities: list[Priority] = []

        if diss > 0:
            priorities.append(Priority(
                f"Reconcile {diss} dissatisfied vassal(s).",
                "high",
                "Gift, scheme, or honorary title to move opinions above zero.",
            ))

        if rel.factions_against:
            priorities.append(Priority(
                f"Address {len(rel.factions_against)} active faction(s) against you.",
                "high",
                "Identify leaders; bribe or imprison before demands escalate.",
            ))

        if strong_unallied and len(rel.alliances) < 3:
            top_target = strong_unallied[0]
            priorities.append(Priority(
                f"Pursue alliance with {top_target['name']} ({top_target['power']:,} power).",
                "medium",
                "Largest unallied local power; a dynastic marriage or negotiation would close the gap.",
            ))

        if on_player > 0:
            priorities.append(Priority(
                f"{on_player} hook(s) held on you — assess who holds them and whether demands are imminent.",
                "medium",
            ))

        return ChancellorBrief(
            char_name=rel.char_name,
            game_date=rel.game_date,
            is_independent=rel.is_independent,
            liege_name=liege_name,
            liege_title=liege_title,
            vassal_count=len(rel.direct_vassals),
            vassal_opinion_buckets=buckets,
            alliance_count=len(rel.alliances),
            alliance_summary=alliance_summary,
            strong_unallied=strong_unallied,
            key_external=key_external,
            same_heritage=same_heritage,
            same_language=same_language,
            favor_hooks_held=favor_held,
            house_head_hooks_held=house_held,
            hooks_held_on_player=on_player,
            observations=observations,
            priorities=priorities,
        )
