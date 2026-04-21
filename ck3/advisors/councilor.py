"""
ck3.advisors.councilor
~~~~~~~~~~~~~~~~~~~~~~
Councilor (Chaplain) advisor — religious relations and faith affairs.

Draws on:
  - CultureReport   (faith profiles, fervor, holy wars, nearby faiths)
"""

from __future__ import annotations
from dataclasses import dataclass, field

from ck3.advisors.base import BaseAdvisor, Priority
from ck3.culture_data import RELIGION_FAMILY_LABELS


# --------------------------------------------------------------------------- #
# Output dataclass
# --------------------------------------------------------------------------- #

@dataclass
class CouncilorBrief:
    """Structured output from the Councilor advisor."""
    char_name: str
    game_date: str

    # Own faith
    own_faith: str
    own_religion: str
    own_family: str
    fervor: float
    religious_head_name: str | None
    own_titles_held: int

    # Nearby faith landscape
    same_faith_zone01: list[dict]    # faiths sharing your faith, zone 0-1
    same_religion_zone01: list[dict] # same religion, different faith
    hostile_zone01: list[dict]       # pagan/enemy faiths nearby
    holy_wars: list[dict]

    # Analysis
    observations: list[str]
    priorities: list[Priority]

    def summary(self) -> str:
        fam_label = RELIGION_FAMILY_LABELS.get(self.own_family, self.own_family)
        lines = [
            f"Councilor's Brief — {self.char_name}  [{self.game_date}]",
            "=" * 70,
            f"\n--- Your Faith ---",
            f"  Faith:    {self.own_faith}  (fervor {self.fervor:.1f})",
            f"  Religion: {self.own_religion}  ({fam_label})",
            f"  Titles held by your faith: {self.own_titles_held}",
        ]
        if self.religious_head_name:
            lines.append(f"  Religious head: {self.religious_head_name}")

        # ── Same religion, nearby ────────────────────────────────────────── #
        if self.same_religion_zone01:
            lines.append(f"\n--- Neighbouring Faiths (Same Religion) ---")
            for f in self.same_religion_zone01:
                zone_str = "local " if f["zone"] == 0 else "nearby"
                lines.append(
                    f"  {f['tag']:<28}  fervor {f['fervor']:>5.1f}  "
                    f"titles {f['titles']:>5}  {zone_str}"
                )

        # ── Nearby hostile/pagan faiths ──────────────────────────────────── #
        if self.hostile_zone01:
            lines.append(f"\n--- Nearby Hostile / Pagan Faiths ---")
            for f in self.hostile_zone01:
                zone_str = "local " if f["zone"] == 0 else "nearby"
                lines.append(
                    f"  {f['tag']:<28}  fervor {f['fervor']:>5.1f}  "
                    f"titles {f['titles']:>5}  {zone_str}  [{f['family']}]"
                )

        # ── Holy wars ────────────────────────────────────────────────────── #
        if self.holy_wars:
            lines.append(f"\n--- Holy Wars ({len(self.holy_wars)}) ---")
            for w in self.holy_wars:
                you = "  *** YOU ARE INVOLVED ***" if w["involves_player"] else ""
                lines.append(
                    f"  {w['cb']}  {w['attacker_faith']} → {w['defender_faith']}{you}"
                )
        else:
            lines.append("\n  No active holy wars.")

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

_LOW_FERVOR  = 50.0
_HIGH_FERVOR = 90.0
_PAGAN_FAMILIES = {"rf_pagan"}


class CouncilorAdvisor(BaseAdvisor):
    role = "Councilor"

    def advise(self) -> CouncilorBrief:
        cul = self.council.culture_report

        own_faith_profile = next(
            (f for f in cul.faiths if f.relation_to_player == "same_faith"), None
        )
        own_titles = own_faith_profile.titles_held if own_faith_profile else 0
        head_name = own_faith_profile.religious_head_name if own_faith_profile else None

        # ── Nearby faith breakdown ─────────────────────────────────────────── #
        same_religion = [
            {"tag": f.tag, "fervor": f.fervor, "titles": f.titles_held,
             "zone": f.zone, "family": f.religion_family}
            for f in cul.faiths
            if f.relation_to_player == "same_religion" and f.zone <= 1
        ]

        hostile = [
            {"tag": f.tag, "fervor": f.fervor, "titles": f.titles_held,
             "zone": f.zone, "family": f.religion_family}
            for f in cul.faiths
            if f.relation_to_player == "other" and f.zone <= 1 and f.titles_held >= 5
        ]
        hostile.sort(key=lambda f: -f["titles"])

        holy_wars = [
            {
                "cb": w.cb_type,
                "attacker_faith": w.attacker_faith,
                "defender_faith": w.defender_faith,
                "involves_player": w.involves_player,
            }
            for w in cul.holy_wars
        ]

        # ── Observations ─────────────────────────────────────────────────── #
        observations = []

        if cul.own_faith_fervor < _LOW_FERVOR:
            observations.append(
                f"Faith fervor is low ({cul.own_faith_fervor:.1f}). "
                "Heresy risk rises as fervor falls; consider supporting the church."
            )
        elif cul.own_faith_fervor >= _HIGH_FERVOR:
            observations.append(
                f"Faith fervor is high ({cul.own_faith_fervor:.1f}) — "
                "crusade calls and missionary pressure will be strong."
            )

        local_pagans = [f for f in hostile if "pagan" in f["family"] and f["zone"] == 0]
        if local_pagans:
            names = ", ".join(f["tag"] for f in local_pagans[:3])
            total_pagan_titles = sum(f["titles"] for f in local_pagans)
            observations.append(
                f"Pagan faiths are present within your local zone: {names} "
                f"({total_pagan_titles} titles). Crusade or conversion pressure may apply."
            )

        nearby_pagans = [f for f in hostile if "pagan" in f["family"] and f["zone"] == 1]
        if nearby_pagans:
            total = sum(f["titles"] for f in nearby_pagans)
            observations.append(
                f"{len(nearby_pagans)} pagan faith(s) in the nearby zone "
                f"({total} titles total) — monitor for missionary opportunities."
            )

        if holy_wars:
            player_wars = [w for w in holy_wars if w["involves_player"]]
            if player_wars:
                observations.append("You are a participant in an active holy war.")
            else:
                observations.append(
                    f"{len(holy_wars)} holy war(s) in progress nearby — "
                    "the religious landscape is in flux."
                )

        if not head_name:
            observations.append(
                "Your faith has no recognised religious head. "
                "This reduces doctrinal authority and piety generation."
            )

        # ── Priorities ────────────────────────────────────────────────────── #
        priorities: list[Priority] = []

        if cul.own_faith_fervor < _LOW_FERVOR:
            priorities.append(Priority(
                "Shore up faith fervor — found a holy order or support the church.",
                "high",
            ))

        if local_pagans:
            priorities.append(Priority(
                f"Convert or subjugate local pagan territories.",
                "medium",
                "Local pagans reduce religious cohesion and are valid crusade/holy-war targets.",
            ))

        if not head_name and cul.own_religion_tag not in ("", "0"):
            priorities.append(Priority(
                "Seek recognition of a religious head for your faith.",
                "low",
                "A head provides piety bonuses and doctrinal legitimacy.",
            ))

        return CouncilorBrief(
            char_name=cul.char_name,
            game_date=cul.game_date,
            own_faith=cul.own_faith_tag,
            own_religion=cul.own_religion_tag,
            own_family=cul.own_religion_family,
            fervor=cul.own_faith_fervor,
            religious_head_name=head_name,
            own_titles_held=own_titles,
            same_faith_zone01=[],   # same faith is just the player's own; shown in header
            same_religion_zone01=same_religion,
            hostile_zone01=hostile,
            holy_wars=holy_wars,
            observations=observations,
            priorities=priorities,
        )
