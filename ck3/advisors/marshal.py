"""
ck3.advisors.marshal
~~~~~~~~~~~~~~~~~~~~
Marshal advisor — military strategy in peace and wartime.

Draws on:
  - MilitaryReport  (realm strength, nearby rulers, active wars, knights)
  - TerrainReport   (defensibility of domain, mountain/river holdings)
"""

from __future__ import annotations
from dataclasses import dataclass, field

from ck3.advisors.base import BaseAdvisor, Priority


# --------------------------------------------------------------------------- #
# Output dataclass
# --------------------------------------------------------------------------- #

@dataclass
class MarshalBrief:
    """Structured output from the Marshal advisor."""
    char_name: str
    game_date: str

    # Posture
    own_max: int
    own_power: int
    posture: str              # "dominant" | "strong advantage" | "roughly matched" | …

    # Threat landscape
    liege: dict | None        # {name, total, power, zone}
    top_threats: list[dict]   # [{name, total, power, relation, zone, faith}], sorted by power
    ally_pool: list[dict]     # [{name, total, power}]

    # Current operations
    at_war: bool
    active_wars: list[dict]   # [{cb, role, enemies}]

    # Forces
    knights: list[dict]       # [{name, prowess, power}]
    avg_knight_prowess: float

    # Terrain context
    defensible_holdings: int  # count of mountains/hills/forest in domain
    total_holdings: int

    # Analysis
    observations: list[str]
    priorities: list[Priority]

    def summary(self) -> str:
        lines = [
            f"Marshal's Brief — {self.char_name}  [{self.game_date}]",
            "=" * 70,
        ]

        # ── Strength overview ────────────────────────────────────────────── #
        lines += [
            "\n--- Military Posture ---",
            f"  Own forces:   {self.own_max:,} max troops   combat power {self.own_power:,}",
            f"  Posture:      {self.posture} vs. local field",
        ]

        if self.liege:
            ratio = self.own_max / max(self.liege["total"], 1)
            lines.append(
                f"  Liege ({self.liege['name']}):  "
                f"{self.liege['total']:,} troops — "
                f"you are at {ratio:.0%} of liege strength"
            )

        # ── Active wars ──────────────────────────────────────────────────── #
        if self.at_war:
            lines.append(f"\n--- Active Wars ({len(self.active_wars)}) ---")
            for w in self.active_wars:
                lines.append(f"  {w['cb']}  [{w['role']}]  vs. {', '.join(w['enemies'][:3])}")
        else:
            lines.append("\n  No active wars.")

        # ── Threat landscape ─────────────────────────────────────────────── #
        lines.append(f"\n--- Local Threat Landscape (top {min(8, len(self.top_threats))}) ---")
        for r in self.top_threats[:8]:
            ratio = self.own_max / max(r["total"], 1)
            rel = f"[{r['relation']}]" if r["relation"] != "geo_neighbor" else ""
            lines.append(
                f"  {r['name']:<34}  {r['total']:>5,} troops  "
                f"power {r['power']:>7,}  ratio {ratio:.2f}  {rel}"
            )

        # ── Allied pool ──────────────────────────────────────────────────── #
        if self.ally_pool:
            total_allied = sum(a["total"] for a in self.ally_pool)
            lines.append(f"\n  Allied military pool: {total_allied:,} additional max troops")
            for a in self.ally_pool:
                lines.append(f"    + {a['name']:<28}  {a['total']:,}")

        # ── Knights ──────────────────────────────────────────────────────── #
        lines.append(f"\n--- Knights ({len(self.knights)})  avg prowess {self.avg_knight_prowess:.1f} ---")
        for k in self.knights:
            lines.append(f"  {k['name']:<22}  prowess {k['prowess']:>2}  power {k['power']:,}")

        # ── Observations & priorities ─────────────────────────────────────── #
        if self.observations:
            lines.append("\n--- Assessment ---")
            for obs in self.observations:
                lines.append(f"  {obs}")

        lines.append("\n--- Priorities ---")
        lines.append(self._fmt_priorities(self.priorities))

        return "\n".join(lines)

    @staticmethod
    def _fmt_priorities(priorities: list[Priority]) -> str:
        from ck3.advisors.base import BaseAdvisor
        return BaseAdvisor._fmt_priorities(priorities)


# --------------------------------------------------------------------------- #
# Advisor
# --------------------------------------------------------------------------- #

_DEFENSIBLE = {"mountains", "hills", "forest"}
_THREAT_RELATIONS = {"geo_neighbor", "at_war"}


class MarshalAdvisor(BaseAdvisor):
    role = "Marshal"

    def advise(self) -> MarshalBrief:
        mil = self.council.military_report
        ter = self.council.terrain_report
        rs = mil.realm_strength

        # ── Liege and ally pool ───────────────────────────────────────────── #
        liege_rec = next((r for r in mil.nearby_rulers if r.political_relation == "liege"), None)
        liege = (
            {"name": liege_rec.char_name, "total": liege_rec.total_max, "power": liege_rec.combat_power}
            if liege_rec else None
        )

        allies = [r for r in mil.nearby_rulers if r.political_relation == "ally"]
        ally_pool = [{"name": a.char_name, "total": a.total_max, "power": a.combat_power}
                     for a in sorted(allies, key=lambda r: -r.total_max)]

        # ── Threat landscape: non-liege, non-vassal, zone 0-1 ────────────── #
        threats = [
            r for r in mil.nearby_rulers
            if r.political_relation in _THREAT_RELATIONS or (
                r.political_relation == "geo_neighbor" and r.geo_zone <= 1
            )
        ]
        threats.sort(key=lambda r: -r.combat_power)
        top_threats = [
            {
                "name": r.char_name,
                "total": r.total_max,
                "power": r.combat_power,
                "relation": r.political_relation,
                "zone": r.geo_zone,
                "faith": r.faith_tag,
            }
            for r in threats
        ]

        # ── Posture: compare own power to the median of top local threats ── #
        local_powers = [r["power"] for r in top_threats[:5]]
        median_threat = sorted(local_powers)[len(local_powers) // 2] if local_powers else 1
        posture = self._power_label(rs.combat_power / max(median_threat, 1))

        # ── Knights ──────────────────────────────────────────────────────── #
        knights = rs.knights
        avg_prowess = (
            sum(k["prowess"] for k in knights) / len(knights) if knights else 0.0
        )

        # ── Terrain defensibility from domain ────────────────────────────── #
        defensible = sum(
            1 for h in ter.domain_holdings if h.terrain in _DEFENSIBLE
        )

        # ── Active wars ──────────────────────────────────────────────────── #
        wars_summary = [
            {
                "cb": w.casus_belli,
                "role": w.subject_role,
                "enemies": w.defender_names if w.subject_role == "attacker" else w.attacker_names,
            }
            for w in mil.active_wars
        ]

        # ── Observations ────────────────────────────────────────────────── #
        observations = []

        # Power vs. liege
        if liege:
            liege_ratio = rs.combat_power / max(liege["power"], 1)
            observations.append(
                f"At {liege_ratio:.0%} of liege power — "
                + ("sufficient to command respect within the empire."
                   if liege_ratio >= 0.5
                   else "dependent on Imperial goodwill for external defence.")
            )

        # Pagan or hostile neighbors
        pagan_threats = [r for r in top_threats[:10] if "pagan" in r["faith"]]
        if pagan_threats:
            names = ", ".join(r["name"] for r in pagan_threats[:3])
            observations.append(
                f"Unconverted neighbors present a persistent border risk: {names}."
            )

        # Knight quality
        if avg_prowess < 8:
            observations.append(
                f"Knight quality is below average (mean prowess {avg_prowess:.1f}). "
                "Replacing low-prowess knights would improve battlefield performance."
            )
        elif avg_prowess >= 12:
            observations.append(
                f"Knight corps is excellent (mean prowess {avg_prowess:.1f})."
            )

        # Alliance depth
        allied_strength = sum(a["total"] for a in ally_pool)
        if not ally_pool:
            observations.append(
                "No military alliances. Isolated in any coalition scenario."
            )
        elif allied_strength < rs.total_max:
            observations.append(
                f"Allied pool ({allied_strength:,}) is smaller than own forces. "
                "Additional alliances would improve coalition capacity."
            )

        # Defensibility
        def_pct = defensible / max(len(ter.domain_holdings), 1)
        if def_pct >= 0.4:
            observations.append(
                f"{defensible} of {len(ter.domain_holdings)} domain holdings sit on defensible terrain "
                f"(mountains/hills/forest) — a strong natural base."
            )

        # ── Priorities ───────────────────────────────────────────────────── #
        priorities: list[Priority] = []

        if mil.active_wars:
            priorities.append(Priority(
                "Resolve active war(s) before raising additional strategic commitments.",
                "high",
            ))

        # Identify the single largest non-allied threat
        hostile_threats = [r for r in top_threats if r["relation"] != "ally"]
        if hostile_threats:
            top = hostile_threats[0]
            ratio = rs.combat_power / max(top["power"], 1)
            if ratio < 0.85:
                priorities.append(Priority(
                    f"Address power gap with {top['name']} ({top['total']:,} troops).",
                    "high" if ratio < 0.5 else "medium",
                    "Build levies, recruit MaA, or secure an alliance to close the gap.",
                ))

        if not ally_pool:
            priorities.append(Priority(
                "Establish at least one military alliance.",
                "high" if not mil.active_wars else "medium",
                "Isolation means any coalition attack cannot be answered in kind.",
            ))

        if avg_prowess < 8:
            priorities.append(Priority(
                "Improve knight roster — current average prowess is low.",
                "medium",
                "Look for high-prowess courtiers and invite knights with prowess ≥ 12.",
            ))

        if rs.maa_capacity < rs.levy_capacity * 0.2:
            priorities.append(Priority(
                "Men-at-arms capacity is low relative to levy — consider MaA buildings.",
                "low",
                "MaA are more reliable than levies in offensive campaigns.",
            ))

        return MarshalBrief(
            char_name=mil.char_name,
            game_date=mil.game_date,
            own_max=rs.total_max,
            own_power=rs.combat_power,
            posture=posture,
            liege=liege,
            top_threats=top_threats,
            ally_pool=ally_pool,
            at_war=bool(mil.active_wars),
            active_wars=wars_summary,
            knights=knights,
            avg_knight_prowess=avg_prowess,
            defensible_holdings=defensible,
            total_holdings=len(ter.domain_holdings),
            observations=observations,
            priorities=priorities,
        )
