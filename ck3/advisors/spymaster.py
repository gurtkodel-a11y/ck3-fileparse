"""
ck3.advisors.spymaster
~~~~~~~~~~~~~~~~~~~~~~
Spymaster advisor — intrigue, leverage, and hidden threats.

Draws on:
  - RelationshipsReport  (hooks, personal relations, notable opinions, factions)
"""

from __future__ import annotations
from dataclasses import dataclass, field

from ck3.advisors.base import BaseAdvisor, Priority


# --------------------------------------------------------------------------- #
# Output dataclass
# --------------------------------------------------------------------------- #

@dataclass
class SpymasterBrief:
    """Structured output from the Spymaster advisor."""
    char_name: str
    game_date: str

    # Leverage inventory
    favor_hooks_held: list[dict]       # [{name, expires}]
    house_head_hooks_held: list[dict]  # [{name}]
    hooks_on_player: list[dict]        # [{name, type, expires}]

    # Threat actors
    nemeses: list[dict]                # [{name, location, titles}]
    rivals: list[dict]                 # [{name, location, titles}]
    strong_haters: list[dict]          # opinion < -20 on player: [{name, score, modifiers}]

    # Active factions
    factions: list[dict]               # [{type, demand, members}]

    # Notable patterns
    crime_opinions: list[dict]         # opinions driven by crime modifiers

    # Analysis
    observations: list[str]
    priorities: list[Priority]

    def summary(self) -> str:
        lines = [
            f"Spymaster's Brief — {self.char_name}  [{self.game_date}]",
            "=" * 70,
        ]

        # ── Leverage held ─────────────────────────────────────────────────── #
        total_hooks = len(self.favor_hooks_held) + len(self.house_head_hooks_held)
        lines.append(f"\n--- Leverage Held ({total_hooks} hooks) ---")
        for h in self.favor_hooks_held:
            lines.append(f"  favor_hook      on {h['name']:<24}  expires {h['expires']}")
        for h in self.house_head_hooks_held:
            lines.append(f"  house_head_hook on {h['name']}")

        # ── Vulnerability ─────────────────────────────────────────────────── #
        if self.hooks_on_player:
            lines.append(f"\n--- Hooks Held on You ({len(self.hooks_on_player)}) ---")
            for h in self.hooks_on_player:
                exp = f"  expires {h['expires']}" if h.get("expires") else ""
                lines.append(f"  {h['type']:<18}  held by {h['name']}{exp}")

        # ── Threat actors ─────────────────────────────────────────────────── #
        if self.nemeses or self.rivals:
            lines.append(f"\n--- Personal Enemies ---")
            for n in self.nemeses:
                titles = ", ".join(n["titles"][:2]) if n["titles"] else "unlanded"
                lines.append(f"  NEMESIS  {n['name']:<24}  [{titles}]  {n['location']}")
            for r in self.rivals:
                titles = ", ".join(r["titles"][:2]) if r["titles"] else "unlanded"
                lines.append(f"  rival    {r['name']:<24}  [{titles}]  {r['location']}")

        if self.strong_haters:
            lines.append(f"\n--- Strong Negative Opinions of You ---")
            for o in self.strong_haters:
                mods = "; ".join(f"{m['modifier']} {m['value']:+d}" for m in o["modifiers"][:3])
                lines.append(f"  {o['name']:<24}  {o['score']:+d}  ({mods})")

        # ── Active factions ───────────────────────────────────────────────── #
        if self.factions:
            lines.append(f"\n--- Active Factions Against You ({len(self.factions)}) ---")
            for f in self.factions:
                lines.append(
                    f"  {f['type']:<30}  demand: {f['demand']}  "
                    f"members: {f['member_count']}"
                )

        # ── Crime opinions ────────────────────────────────────────────────── #
        if self.crime_opinions:
            lines.append(f"\n--- Unresolved Crimes/Grievances ---")
            for o in self.crime_opinions:
                mods = "; ".join(f"{m['modifier']} {m['value']:+d}" for m in o["modifiers"])
                direction = "they of you" if o["direction"] == "other_of_player" else "you of them"
                lines.append(f"  {o['name']:<24}  [{direction}]  {mods}")

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

_HATE_THRESHOLD = -20    # opinions below this flagged as threat actors
_CRIME_KEYWORDS = (
    "crime", "murder", "betrayal", "tyrant", "attempted_murder",
    "imprisoned", "humiliated",
)


class SpymasterAdvisor(BaseAdvisor):
    role = "Spymaster"

    def advise(self) -> SpymasterBrief:
        rel = self.council.relationships_report

        # ── Hooks inventory ───────────────────────────────────────────────── #
        favor_held = [
            {"name": h.other_name, "expires": h.expiration_date}
            for h in rel.hooks_held if h.hook_type == "favor_hook"
        ]
        house_held = [
            {"name": h.other_name}
            for h in rel.hooks_held if h.hook_type == "house_head_hook"
        ]
        on_player = [
            {"name": h.other_name, "type": h.hook_type, "expires": h.expiration_date}
            for h in rel.hooks_on_player
        ]

        # ── Personal enemies ──────────────────────────────────────────────── #
        nemeses = [
            {
                "name": r.other_name,
                "location": r.other_location,
                "titles": r.other_titles,
            }
            for r in rel.personal_relations
            if r.relation_type == "nemesis" and r.direction == "player_to_other"
        ]
        rivals = [
            {
                "name": r.other_name,
                "location": r.other_location,
                "titles": r.other_titles,
            }
            for r in rel.personal_relations
            if r.relation_type == "rival" and r.direction == "player_to_other"
        ]

        # ── Strong negative opinions ──────────────────────────────────────── #
        strong_haters = [
            {
                "name": op.other_name,
                "score": op.total_value,
                "modifiers": op.modifiers,
                "direction": op.direction,
            }
            for op in rel.notable_opinions
            if op.direction == "other_of_player" and op.total_value <= _HATE_THRESHOLD
        ]
        strong_haters.sort(key=lambda o: o["score"])

        # ── Crime opinions (in either direction) ─────────────────────────── #
        crime_opinions = []
        for op in rel.notable_opinions:
            crime_mods = [
                m for m in op.modifiers
                if any(kw in m.get("modifier", "").lower() for kw in _CRIME_KEYWORDS)
            ]
            if crime_mods:
                crime_opinions.append({
                    "name": op.other_name,
                    "score": op.total_value,
                    "direction": op.direction,
                    "modifiers": crime_mods,
                })

        # ── Factions ─────────────────────────────────────────────────────── #
        factions = [
            {
                "type": f.faction_type,
                "demand": f.demand,
                "member_count": f.member_count,
                "members": f.member_names,
            }
            for f in rel.factions_against
        ]

        # ── Observations ─────────────────────────────────────────────────── #
        observations = []

        total_hooks_held = len(favor_held) + len(house_held)
        if total_hooks_held >= 10:
            observations.append(
                f"{total_hooks_held} hooks in hand ({len(favor_held)} favor, "
                f"{len(house_held)} house-head). Strong position for coercion and compliance."
            )

        if on_player:
            observations.append(
                f"{len(on_player)} hook(s) held on you. "
                "Each is a potential forced demand — identify the holders and their likely intentions."
            )

        if nemeses:
            for n in nemeses:
                loc = n["location"]
                titles = n["titles"]
                if loc == "other_court" and not titles:
                    observations.append(
                        f"Nemesis {n['name']} is unlanded and in another court — "
                        "low immediate threat, but a potential tool for rivals."
                    )
                elif titles:
                    observations.append(
                        f"Nemesis {n['name']} holds titles: {', '.join(titles[:2])}. "
                        "A landed nemesis can act; consider neutralising."
                    )

        if crime_opinions:
            observations.append(
                f"{len(crime_opinions)} unresolved crime/grievance opinion(s) in the record. "
                "These create persistent enemies who may scheme or join factions."
            )

        if factions:
            total_faction_members = sum(f["member_count"] for f in factions)
            observations.append(
                f"{len(factions)} active faction(s) with {total_faction_members} member(s). "
                "Faction demands escalate to war if membership grows unchecked."
            )
        else:
            observations.append("No active factions — internal stability is good.")

        # ── Priorities ────────────────────────────────────────────────────── #
        priorities: list[Priority] = []

        if factions:
            priorities.append(Priority(
                f"Neutralise active faction(s): bribe leaders or find grounds to imprison them.",
                "high",
            ))

        if strong_haters:
            worst = strong_haters[0]
            priorities.append(Priority(
                f"Monitor {worst['name']} (opinion {worst['score']:+d}) — strong hatred can drive scheming.",
                "medium" if worst["score"] > -50 else "high",
                "Gift, honorary title, or preemptive imprisonment if they hold power.",
            ))

        if on_player:
            priorities.append(Priority(
                f"Identify and address {len(on_player)} hook(s) held on you before they are called.",
                "medium",
            ))

        if crime_opinions and not factions:
            priorities.append(Priority(
                "Resolve lingering crime-based grudges before they organise into factions.",
                "low",
            ))

        return SpymasterBrief(
            char_name=rel.char_name,
            game_date=rel.game_date,
            favor_hooks_held=favor_held,
            house_head_hooks_held=house_held,
            hooks_on_player=on_player,
            nemeses=nemeses,
            rivals=rivals,
            strong_haters=strong_haters,
            factions=factions,
            crime_opinions=crime_opinions,
            observations=observations,
            priorities=priorities,
        )
