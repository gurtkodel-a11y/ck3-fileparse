"""
ck3.evaluators.relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Level-1 relationships evaluator — surfaces the full web of formal and personal
relationships visible around a character.

Supersedes hierarchy.py (which covered hierarchical sections only).

Sections:
  1. Hierarchical Position  — liege chain upward
  2. Vassals               — direct vassal contracts, faction flags
  3. Factions              — active factions targeting the player
  4. Alliances             — lateral alliance bonds
  5. Hooks                 — leverage held / held on player
  6. Family                — spouse(s), children, parents, dynasty
  7. Your Court            — courtiers grouped by role
  8. Personal Relations    — scripted bonds (friend, rival, lover, …)
  9. Notable Opinions      — significant temporary opinion modifiers

Usage:
    from ck3.evaluators.relationships import RelationshipsEvaluator
    ev = RelationshipsEvaluator(gs, char_id=18269)
    report = ev.report()
    print(report.summary())
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

from ck3.gamestate import GameState, _ensure_list
from ck3.names import decode_name, char_label, house_prefix_name, title_ruler_label


# --------------------------------------------------------------------------- #
# Data classes — hierarchical (carried over from hierarchy.py)
# --------------------------------------------------------------------------- #

@dataclass
class LiegeRecord:
    """One rung in the hierarchy above the player."""
    char_id: int
    char_name: str
    highest_title_key: str
    highest_title_tier: str
    contract_group: str
    is_top: bool


@dataclass
class VassalRecord:
    """A character who holds a direct vassal contract under the player."""
    char_id: int
    char_name: str
    contract_group: str
    contract_date: str
    titles: list[str]
    highest_title_tier: str
    levy_capacity: int
    total_strength: int
    in_faction_against_liege: bool
    faction_types: list[str]


@dataclass
class AllianceRecord:
    """A lateral alliance between the player and another character."""
    ally_id: int
    ally_name: str
    ally_titles: list[str]
    bond_count: int
    is_negotiated: bool
    mediator_own_id: int | None
    mediator_own_name: str | None
    mediator_ally_id: int | None
    mediator_ally_name: str | None


@dataclass
class HookRecord:
    """A leverage relationship between two characters."""
    other_id: int
    other_name: str
    hook_type: str
    expiration_date: str
    direction: str    # "player_holds" | "held_on_player"


@dataclass
class FactionRecord:
    """A faction that is actively working against the player."""
    faction_id: str
    faction_type: str
    demand: str
    member_ids: list[int]
    member_names: list[str]
    member_count: int


# --------------------------------------------------------------------------- #
# Data classes — personal / familial (new)
# --------------------------------------------------------------------------- #

@dataclass
class FamilyMemberRecord:
    """A character related to the player by blood or marriage."""
    char_id: int
    char_name: str
    relation: str           # "primary_spouse" | "spouse" | "former_spouse" | "child" | "father" | "mother"
    titles: list[str]       # highest-tier titles held; empty if unlanded
    dynasty_house_id: int | None
    location: str           # "player_court" | "own_realm" | "other_court" | "unlanded" | "deceased"
    is_dead: bool
    death_date: str         # from dead_data.date; empty string if alive


@dataclass
class CourtierRecord:
    """A character resident in the player's court."""
    char_id: int
    char_name: str
    role: str               # "council" | "knight" | "court_position" | "courtier"
    court_position_type: str | None   # e.g. "court_physician_court_position"
    titles: list[str]       # usually empty — courtiers are typically unlanded
    family_relation: str | None       # e.g. "child" if also a family member


@dataclass
class PersonalRelationRecord:
    """A scripted personal bond between the player and another character."""
    other_id: int
    other_name: str
    relation_type: str      # "friend" | "rival" | "lover" | "nemesis" | …
    direction: str          # "player_to_other" | "other_to_player"
    other_titles: list[str]
    other_location: str     # "player_court" | "own_realm" | "other_court" | "unlanded"


@dataclass
class OpinionRecord:
    """A set of notable temporary opinion modifiers between the player and another character."""
    other_id: int
    other_name: str
    direction: str          # "player_of_other" | "other_of_player"
    total_value: int
    modifiers: list[dict]   # [{modifier, value, expiration_date}]


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

@dataclass
class RelationshipsReport:
    """Full level-1 relationships report for one character."""
    char_id: int
    char_name: str
    game_date: str

    # Hierarchical
    is_independent: bool
    liege_chain: list[LiegeRecord]
    direct_vassals: list[VassalRecord]
    factions_against: list[FactionRecord]
    alliances: list[AllianceRecord]
    hooks_held: list[HookRecord]
    hooks_on_player: list[HookRecord]

    # Personal / familial
    family: list[FamilyMemberRecord]
    dynasty_house_name: str
    dynasty_house_founded: str
    dynasty_house_head_id: int | None
    dynasty_prestige: float
    courtiers: list[CourtierRecord]
    personal_relations: list[PersonalRelationRecord]
    notable_opinions: list[OpinionRecord]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"Relationships Report — {self.char_name} (id {self.char_id})  [{self.game_date}]",
            "=" * 70,
        ]

        # ── 1. Position ──────────────────────────────────────────────────── #
        lines.append("\n--- Hierarchical Position ---")
        if self.is_independent:
            lines.append("  Independent ruler — no liege above you.")
        else:
            for i, lg in enumerate(self.liege_chain):
                depth = "  " + ("  " * i)
                top_mark = "  [sovereign]" if lg.is_top else ""
                lines.append(
                    f"{depth}↑ {lg.char_name}  [{lg.highest_title_key}]"
                    f"  ({lg.contract_group}){top_mark}"
                )

        # ── 2. Vassals ───────────────────────────────────────────────────── #
        lines.append(f"\n--- Direct Vassals ({len(self.direct_vassals)}) ---")
        by_type: dict[str, list[VassalRecord]] = {}
        for v in self.direct_vassals:
            by_type.setdefault(v.contract_group, []).append(v)
        for ctype, vassals in sorted(by_type.items()):
            lines.append(f"  [{_contract_label(ctype)}]")
            for v in sorted(vassals, key=lambda x: (_tier_order(x.highest_title_tier), x.char_name)):
                faction_flag = "  ⚠ IN FACTION" if v.in_faction_against_liege else ""
                faction_detail = f" ({', '.join(v.faction_types)})" if v.faction_types else ""
                title_str = _humanize_title_key(v.titles[0]) if v.titles else "(no title)"
                lines.append(
                    f"    {v.char_name:<28}  {title_str:<26}"
                    f"  levy {v.levy_capacity:>5,}  total {v.total_strength:>5,}"
                    f"{faction_flag}{faction_detail}"
                )

        # ── 3. Factions ──────────────────────────────────────────────────── #
        if self.factions_against:
            lines.append(f"\n--- Factions Against You ({len(self.factions_against)}) ---")
            for f in self.factions_against:
                lines.append(
                    f"  {f.faction_type:<35}  demand: {f.demand}"
                    f"  ({f.member_count} members)"
                )
                if f.member_names:
                    lines.append(f"    Members: {', '.join(f.member_names[:5])}")

        # ── 4. Alliances ─────────────────────────────────────────────────── #
        lines.append(f"\n--- Alliances ({len(self.alliances)}) ---")
        for a in sorted(self.alliances, key=lambda x: x.ally_name):
            title_str = _humanize_title_key(a.ally_titles[0]) if a.ally_titles else "(unlanded)"
            bonds_str = f"  [{a.bond_count} bonds]" if a.bond_count > 1 else ""
            if a.is_negotiated:
                via = "negotiated"
            elif a.mediator_own_name and a.mediator_ally_name:
                via = f"via {a.mediator_own_name} ↔ {a.mediator_ally_name}"
            elif a.mediator_ally_name:
                via = f"via {a.mediator_ally_name}"
            else:
                via = "marriage"
            lines.append(f"  {a.ally_name:<28}  [{title_str}]{bonds_str}  — {via}")

        # ── 5. Hooks ─────────────────────────────────────────────────────── #
        if self.hooks_held:
            lines.append(f"\n--- Hooks You Hold on Others ({len(self.hooks_held)}) ---")
            for h in sorted(self.hooks_held, key=lambda x: x.hook_type):
                exp = "" if h.expiration_date == "9999.1.1" else f"  expires {h.expiration_date}"
                lines.append(f"  {h.hook_type:<28}  on {h.other_name}{exp}")
        if self.hooks_on_player:
            lines.append(f"\n--- Hooks Others Hold on You ({len(self.hooks_on_player)}) ---")
            for h in sorted(self.hooks_on_player, key=lambda x: x.hook_type):
                exp = "" if h.expiration_date == "9999.1.1" else f"  expires {h.expiration_date}"
                lines.append(f"  {h.hook_type:<28}  held by {h.other_name}{exp}")

        # ── 6. Family ────────────────────────────────────────────────────── #
        lines.append(f"\n--- Family ---")
        if self.dynasty_house_name:
            head_note = "  (you are head)" if self.dynasty_house_head_id == self.char_id else ""
            lines.append(
                f"  House: {self.dynasty_house_name}  "
                f"founded {self.dynasty_house_founded}"
                f"  prestige {self.dynasty_prestige:.0f}{head_note}"
            )

        # Group family by relation type for display
        _relation_order = ["primary_spouse", "spouse", "former_spouse", "father", "mother", "child"]
        family_by_rel: dict[str, list[FamilyMemberRecord]] = {}
        for fm in self.family:
            family_by_rel.setdefault(fm.relation, []).append(fm)

        for rel in _relation_order:
            members = family_by_rel.get(rel, [])
            if not members:
                continue
            label = rel.replace("_", " ").title()
            for fm in members:
                if fm.is_dead:
                    status = f"deceased {fm.death_date}" if fm.death_date else "deceased"
                    lines.append(
                        f"  {label:<18}  {fm.char_name:<22}  (id {fm.char_id})"
                        f"  [{status}]"
                    )
                else:
                    title_str = fm.titles[0] if fm.titles else "unlanded"
                    loc_note = {
                        "player_court": "your court",
                        "own_realm":    "own realm",
                        "other_court":  "other court",
                        "unlanded":     "unlanded",
                    }.get(fm.location, fm.location)
                    lines.append(
                        f"  {label:<18}  {fm.char_name:<22}  (id {fm.char_id})"
                        f"  [{title_str}]  {loc_note}"
                    )

        # ── 7. Your Court ────────────────────────────────────────────────── #
        lines.append(f"\n--- Your Court ({len(self.courtiers)}) ---")
        _role_order = ["council", "knight", "court_position", "courtier"]
        courtiers_by_role: dict[str, list[CourtierRecord]] = {}
        for c in self.courtiers:
            courtiers_by_role.setdefault(c.role, []).append(c)

        for role in _role_order:
            members = courtiers_by_role.get(role, [])
            if not members:
                continue
            label = {
                "council":        "Council",
                "knight":         "Knights",
                "court_position": "Court Positions",
                "courtier":       "Courtiers",
            }.get(role, role.title())
            lines.append(f"  [{label}]")
            for c in sorted(members, key=lambda x: x.char_name):
                fam_note = f"  ({c.family_relation})" if c.family_relation else ""
                pos_note = f"  — {c.court_position_type}" if c.court_position_type else ""
                title_str = c.titles[0] if c.titles else ""
                title_note = f"  [{title_str}]" if title_str else ""
                lines.append(
                    f"    {c.char_name:<22}  (id {c.char_id})"
                    f"{title_note}{pos_note}{fam_note}"
                )

        # ── 8. Personal Relations ────────────────────────────────────────── #
        lines.append(f"\n--- Personal Relations ({len(self.personal_relations)}) ---")
        if not self.personal_relations:
            lines.append("  (none recorded)")
        else:
            # Group by relation type
            by_type: dict[str, list[PersonalRelationRecord]] = {}
            for pr in self.personal_relations:
                by_type.setdefault(pr.relation_type, []).append(pr)
            for rtype in sorted(by_type.keys()):
                for pr in by_type[rtype]:
                    dir_str = "→" if pr.direction == "player_to_other" else "←"
                    title_str = pr.other_titles[0] if pr.other_titles else "unlanded"
                    loc = {
                        "player_court": "your court",
                        "own_realm":    "own realm",
                        "other_court":  "other court",
                        "unlanded":     "unlanded",
                    }.get(pr.other_location, pr.other_location)
                    lines.append(
                        f"  {rtype:<20} {dir_str}  {pr.other_name:<22}"
                        f"  (id {pr.other_id})  [{title_str}]  {loc}"
                    )

        # ── 9. Notable Opinions ──────────────────────────────────────────── #
        if self.notable_opinions:
            lines.append(f"\n--- Notable Opinions ({len(self.notable_opinions)}) ---")
            toward_player = [o for o in self.notable_opinions if o.direction == "other_of_player"]
            from_player   = [o for o in self.notable_opinions if o.direction == "player_of_other"]

            if toward_player:
                lines.append("  [Others → You]")
                for o in sorted(toward_player, key=lambda x: x.total_value):
                    mod_strs = [
                        f"{m['modifier']} {m['value']:+d}" for m in o.modifiers
                    ]
                    lines.append(
                        f"    {o.other_name:<22}  {o.total_value:>+5}"
                        f"  ({'; '.join(mod_strs)})"
                    )
            if from_player:
                lines.append("  [You → Others]")
                for o in sorted(from_player, key=lambda x: x.total_value):
                    mod_strs = [
                        f"{m['modifier']} {m['value']:+d}" for m in o.modifiers
                    ]
                    lines.append(
                        f"    {o.other_name:<22}  {o.total_value:>+5}"
                        f"  ({'; '.join(mod_strs)})"
                    )

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Evaluator
# --------------------------------------------------------------------------- #

# Scripted relation types that represent meaningful personal bonds
_PERSONAL_RELATION_TYPES = {
    "friend", "best_friend", "rival", "nemesis", "lover", "soulmate",
    "crush", "old_flame", "mentor", "student", "intrigue_mentor",
    "intrigue_student", "guardian", "ward", "soldier_friend",
    "oaf", "bully", "grudge", "victim",
}

# Scripted relation types that are "pending" / informational (less narrative weight)
_POTENTIAL_RELATION_TYPES = {
    "potential_friend", "potential_rival", "potential_lover", "potential_hook",
    "wedding_good_fertility",
}

# Minimum abs(total opinion value) to surface in notable opinions
_OPINION_THRESHOLD = 10


class RelationshipsEvaluator:
    def __init__(self, gs: GameState, char_id: int):
        self.gs = gs
        self.char_id = char_id
        gs.build_indices()
        # Build court-positions lookup once
        self._court_positions_db: dict[str, dict] = (
            gs._raw.get("court_positions", {}).get("database", {})
        )
        # Cache opinions list
        self._opinions_list: list[dict] = _ensure_list(
            gs._raw.get("opinions", {}).get("active_opinions", [])
        )

    def report(self) -> RelationshipsReport:
        gs = self.gs
        char = gs.character(self.char_id)
        if char is None:
            raise ValueError(f"Character {self.char_id} not found in living")

        char_name = char_label(char, gs, self.char_id)

        # Hierarchical sections
        liege_chain = self._liege_chain()
        is_independent = len(liege_chain) == 0
        direct_vassals = self._direct_vassals()
        factions_against = self._factions_against()
        faction_members: dict[int, list[str]] = {}
        for f in factions_against:
            for mid in f.member_ids:
                faction_members.setdefault(mid, []).append(f.faction_type)
        for v in direct_vassals:
            ftypes = faction_members.get(v.char_id, [])
            v.in_faction_against_liege = bool(ftypes)
            v.faction_types = ftypes
        alliances, hooks_held, hooks_on_player = self._relations()

        # Personal / familial sections
        family, dyn_name, dyn_founded, dyn_head_id, dyn_prestige = self._family(char)
        family_ids = {fm.char_id: fm.relation for fm in family}
        courtiers = self._courtiers(family_ids)
        personal_relations = self._personal_relations()
        notable_opinions = self._notable_opinions()

        return RelationshipsReport(
            char_id=self.char_id,
            char_name=char_name,
            game_date=gs.date,
            is_independent=is_independent,
            liege_chain=liege_chain,
            direct_vassals=direct_vassals,
            factions_against=factions_against,
            alliances=alliances,
            hooks_held=hooks_held,
            hooks_on_player=hooks_on_player,
            family=family,
            dynasty_house_name=dyn_name,
            dynasty_house_founded=dyn_founded,
            dynasty_house_head_id=dyn_head_id,
            dynasty_prestige=dyn_prestige,
            courtiers=courtiers,
            personal_relations=personal_relations,
            notable_opinions=notable_opinions,
        )

    # ---------------------------------------------------------------------- #
    # Hierarchical helpers (carried over from hierarchy.py)
    # ---------------------------------------------------------------------- #

    def _char_name(self, char_id: int | None) -> str:
        if char_id is None:
            return "unknown"
        c = self.gs.character(char_id)
        return decode_name(c.get("first_name", str(char_id))) if c else str(char_id)

    def _highest_title(self, char_id: int) -> tuple[str, str]:
        titles = self.gs.titles_held_by(char_id)
        best_key, best_tier = "", "b"
        best_order = 99
        for t in titles:
            if not isinstance(t, dict):
                continue
            key = t.get("key", "")
            tier = key[0] if key else "b"
            order = _tier_order(tier)
            if order < best_order:
                best_order = order
                best_key = key
                best_tier = tier
        return best_key, best_tier

    def _all_title_keys(self, char_id: int) -> list[str]:
        titles = self.gs.titles_held_by(char_id)
        keyed = [
            (t.get("key", ""), t.get("key", "b")[0] if t.get("key") else "b")
            for t in titles if isinstance(t, dict) and t.get("key")
        ]
        keyed.sort(key=lambda x: _tier_order(x[1]))
        return [k for k, _ in keyed]

    def _liege_chain(self) -> list[LiegeRecord]:
        gs = self.gs
        chain = []
        seen = {self.char_id}
        current_id = self.char_id
        for _ in range(10):
            contract = gs.contract_for_vassal(current_id)
            if contract is None:
                break
            liege_id = contract.get("liege")
            if liege_id is None or liege_id in seen:
                break
            seen.add(liege_id)
            title_key, title_tier = self._highest_title(liege_id)
            is_top = gs.contract_for_vassal(liege_id) is None
            chain.append(LiegeRecord(
                char_id=liege_id,
                char_name=self._char_name(liege_id),
                highest_title_key=title_key,
                highest_title_tier=title_tier,
                contract_group=contract.get("contract_group", "unknown"),
                is_top=is_top,
            ))
            current_id = liege_id
        return chain

    def _direct_vassals(self) -> list[VassalRecord]:
        gs = self.gs
        vassals = []
        for contract in gs.contracts_for_liege(self.char_id):
            if not isinstance(contract, dict):
                continue
            vassal_id = contract.get("vassal")
            if vassal_id is None:
                continue
            vc = gs.character(vassal_id)
            vname = char_label(vc, gs, vassal_id, include_title=False) if vc else str(vassal_id)
            title_keys = self._all_title_keys(vassal_id)
            highest_tier = title_keys[0][0] if title_keys else "b"
            levy_cap, total_str = 0, 0
            if vc:
                vld = vc.get("landed_data", {})
                levy_cap  = vld.get("levy", 0) or 0
                total_str = vld.get("strength", 0) or 0
            vassals.append(VassalRecord(
                char_id=vassal_id,
                char_name=vname,
                contract_group=contract.get("contract_group", "unknown"),
                contract_date=contract.get("date", ""),
                titles=title_keys,
                highest_title_tier=highest_tier,
                levy_capacity=levy_cap,
                total_strength=total_str,
                in_faction_against_liege=False,
                faction_types=[],
            ))
        return vassals

    def _factions_against(self) -> list[FactionRecord]:
        gs = self.gs
        results = []
        for fid, f in gs.factions.items():
            if not isinstance(f, dict):
                continue
            if f.get("target") != self.char_id:
                continue
            raw_members = _ensure_list(f.get("members", []))
            # Members are either plain ints or {'character': X, 'faction': Y} dicts
            members = [
                m["character"] if isinstance(m, dict) else m
                for m in raw_members
            ]
            member_names = [
                char_label(gs.character(m), gs, m, include_title=False)
                if gs.character(m) else self._char_name(m)
                for m in members[:8]
            ]
            results.append(FactionRecord(
                faction_id=str(fid),
                faction_type=f.get("type", "unknown"),
                demand=f.get("demand", "unknown"),
                member_ids=list(members),
                member_names=member_names,
                member_count=len(members),
            ))
        return results

    def _relations(self) -> tuple[list[AllianceRecord], list[HookRecord], list[HookRecord]]:
        gs = self.gs
        alliance_accum: dict[int, tuple[int, dict, bool]] = {}
        hooks_held: list[HookRecord] = []
        hooks_on_player: list[HookRecord] = []

        for rel in gs.active_relations:
            if not isinstance(rel, dict):
                continue
            first  = rel.get("first")
            second = rel.get("second")
            if first != self.char_id and second != self.char_id:
                continue
            other_id = second if first == self.char_id else first
            player_is_first = (first == self.char_id)

            bonds = _ensure_list(rel.get("alliances", []))
            if bonds:
                other_titles = self._all_title_keys(other_id)
                other_is_ruler = any(k[0] in ("e", "k", "d", "c") for k in other_titles)
                if other_is_ruler:
                    first_bond = next((b for b in bonds if isinstance(b, dict)), {})
                    if other_id in alliance_accum:
                        prev_count, prev_bond, prev_pif = alliance_accum[other_id]
                        alliance_accum[other_id] = (prev_count + len(bonds), prev_bond, prev_pif)
                    else:
                        alliance_accum[other_id] = (len(bonds), first_bond, player_is_first)

            for key, val in rel.items():
                if not key.startswith("active_hook_"):
                    continue
                if not isinstance(val, dict):
                    continue
                hook_type = val.get("type", "unknown_hook")
                expiry = val.get("expiration_date", "9999.1.1")
                hook_holder_is_first = (key[-1] == "0")
                if hook_holder_is_first == player_is_first:
                    hooks_held.append(HookRecord(
                        other_id=other_id,
                        other_name=self._char_name(other_id),
                        hook_type=hook_type,
                        expiration_date=expiry,
                        direction="player_holds",
                    ))
                else:
                    hooks_on_player.append(HookRecord(
                        other_id=other_id,
                        other_name=self._char_name(other_id),
                        hook_type=hook_type,
                        expiration_date=expiry,
                        direction="held_on_player",
                    ))

        alliances: list[AllianceRecord] = []
        for ally_id, (bond_count, first_bond, player_is_first) in alliance_accum.items():
            med0 = first_bond.get("allied_through_0")
            med1 = first_bond.get("allied_through_1")
            is_negotiated = (
                (med0 == self.char_id or med0 == ally_id) and
                (med1 == self.char_id or med1 == ally_id)
            )
            if is_negotiated:
                med_own_id, med_own_name = None, None
                med_ally_id, med_ally_name = None, None
            else:
                med0_titles = self._all_title_keys(med0) if med0 else []
                med0_is_player_side = (
                    med0 == self.char_id or
                    not any(k[0] in ("e", "k") for k in med0_titles)
                )
                if med0_is_player_side:
                    med_own_id  = med0
                    med_own_name  = self._char_name(med0) if med0 and med0 != self.char_id else None
                    med_ally_id = med1
                    med_ally_name = self._char_name(med1) if med1 else None
                else:
                    med_own_id  = med1
                    med_own_name  = self._char_name(med1) if med1 and med1 != self.char_id else None
                    med_ally_id = med0
                    med_ally_name = self._char_name(med0) if med0 else None
            alliances.append(AllianceRecord(
                ally_id=ally_id,
                ally_name=self._char_name(ally_id),
                ally_titles=self._all_title_keys(ally_id)[:2],
                bond_count=bond_count,
                is_negotiated=is_negotiated,
                mediator_own_id=med_own_id,
                mediator_own_name=med_own_name,
                mediator_ally_id=med_ally_id,
                mediator_ally_name=med_ally_name,
            ))
        return alliances, hooks_held, hooks_on_player

    # ---------------------------------------------------------------------- #
    # Family helpers
    # ---------------------------------------------------------------------- #

    def _char_location(self, char_id: int) -> str:
        """Classify where a character resides relative to the player."""
        c = self.gs.character(char_id)
        if c is None:
            return "unknown"
        titles = self.gs.titles_held_by(char_id)
        if any(isinstance(t, dict) and t.get("key", "")[0] in ("e", "k", "d", "c")
               for t in titles):
            return "own_realm"
        cd = c.get("court_data", {})
        if isinstance(cd, dict):
            employer = cd.get("employer")
            if employer == self.char_id:
                return "player_court"
            if employer is not None:
                return "other_court"
        return "unlanded"

    def _family(
        self, char: dict
    ) -> tuple[list[FamilyMemberRecord], str, str, int | None, float]:
        """
        Build the family member list and dynasty summary.
        Returns (members, house_name, house_founded, house_head_id, dynasty_prestige).
        Includes dead characters from dead_unprunable (fully pruned characters are omitted).
        """
        gs = self.gs
        fd = char.get("family_data", {}) if isinstance(char.get("family_data"), dict) else {}
        members: list[FamilyMemberRecord] = []
        seen: set[int] = set()

        def _add(char_id: int, relation: str):
            if char_id in seen:
                return
            seen.add(char_id)
            # Prefer living record; fall back to dead_unprunable
            c = gs.character(char_id)
            is_dead = False
            death_date = ""
            if c is None:
                c = gs.dead.get(str(char_id))
                if c is None:
                    return   # fully pruned — nothing we can do
                is_dead = True
                dd = c.get("dead_data", {})
                death_date = dd.get("date", "") if isinstance(dd, dict) else ""

            location = "deceased" if is_dead else self._char_location(char_id)
            members.append(FamilyMemberRecord(
                char_id=char_id,
                char_name=decode_name(c.get("first_name", str(char_id))),
                relation=relation,
                titles=[] if is_dead else self._all_title_keys(char_id),
                dynasty_house_id=c.get("dynasty_house"),
                location=location,
                is_dead=is_dead,
                death_date=death_date,
            ))

        primary_spouse = fd.get("primary_spouse")
        if primary_spouse:
            _add(int(primary_spouse), "primary_spouse")

        former_spouse_ids = {int(x) for x in _ensure_list(fd.get("former_spouses", []))}

        for sp_id in _ensure_list(fd.get("spouse", [])):
            sp_int = int(sp_id)
            if sp_int != (primary_spouse or -1) and sp_int not in former_spouse_ids:
                _add(sp_int, "spouse")

        for sp_id in former_spouse_ids:
            _add(sp_id, "former_spouse")

        for par_key in ("father", "mother"):
            par_id = fd.get(par_key)
            if par_id:
                _add(int(par_id), par_key)

        for child_id in _ensure_list(fd.get("child", [])):
            _add(int(child_id), "child")

        # Dynasty house summary
        house_id = char.get("dynasty_house")
        dh = gs.dynasty_house(house_id) if house_id else None
        if dh:
            pfx, hname = house_prefix_name(dh)
            house_name = f"{pfx} {hname}".strip() if pfx else hname
        else:
            house_name = ""
        house_founded = dh.get("found_date", "") if dh else ""
        house_head_id = int(dh["head_of_house"]) if dh and dh.get("head_of_house") else None

        # Dynasty prestige
        dyn_prestige = 0.0
        if dh:
            dyn_id = dh.get("dynasty")
            if dyn_id:
                dyn = gs.dynasties.get(str(dyn_id))
                if isinstance(dyn, dict):
                    dyn_prestige = dyn.get("prestige", {}).get("accumulated", 0.0) or 0.0

        return members, house_name, house_founded, house_head_id, dyn_prestige

    # ---------------------------------------------------------------------- #
    # Court helpers
    # ---------------------------------------------------------------------- #

    def _courtiers(self, family_ids: dict[int, str]) -> list[CourtierRecord]:
        """Find all characters resident in the player's court."""
        gs = self.gs
        courtiers: list[CourtierRecord] = []

        for cid_str, c in gs.living.items():
            if not isinstance(c, dict):
                continue
            cd = c.get("court_data", {})
            if not isinstance(cd, dict):
                continue
            if cd.get("employer") != self.char_id:
                continue

            char_id = int(cid_str)
            name = decode_name(c.get("first_name", cid_str))
            titles = self._all_title_keys(char_id)

            # Determine role — priority: council > knight > court_position > courtier
            has_council  = cd.get("council_task") is not None
            has_knight   = cd.get("knight") == "yes"
            pos_ids      = _ensure_list(cd.get("court_positions", []))
            court_pos_type: str | None = None

            if has_council:
                role = "council"
            elif has_knight:
                role = "knight"
            elif pos_ids:
                role = "court_position"
                # Resolve the first position type from the court_positions database
                pos_entry = self._court_positions_db.get(str(pos_ids[0]))
                if isinstance(pos_entry, dict):
                    court_pos_type = pos_entry.get("court_position")
            else:
                role = "courtier"

            family_relation = family_ids.get(char_id)

            courtiers.append(CourtierRecord(
                char_id=char_id,
                char_name=name,
                role=role,
                court_position_type=court_pos_type,
                titles=titles,
                family_relation=family_relation,
            ))

        return courtiers

    # ---------------------------------------------------------------------- #
    # Personal relation helpers
    # ---------------------------------------------------------------------- #

    def _personal_relations(self) -> list[PersonalRelationRecord]:
        """Extract scripted personal bonds involving the player."""
        gs = self.gs
        results: list[PersonalRelationRecord] = []

        for entry in self._opinions_list:
            if not isinstance(entry, dict):
                continue
            sr = entry.get("scripted_relations")
            if not sr or not isinstance(sr, dict):
                continue

            owner  = entry.get("owner")
            target = entry.get("target")

            if owner == self.char_id:
                direction = "player_to_other"
                other_id  = target
            elif target == self.char_id:
                direction = "other_to_player"
                other_id  = owner
            else:
                continue

            if other_id is None:
                continue
            other_id = int(other_id)

            for rel_type in sr:
                if rel_type not in _PERSONAL_RELATION_TYPES:
                    continue
                other_titles = self._all_title_keys(other_id)
                results.append(PersonalRelationRecord(
                    other_id=other_id,
                    other_name=self._char_name(other_id),
                    relation_type=rel_type,
                    direction=direction,
                    other_titles=other_titles,
                    other_location=self._char_location(other_id),
                ))

        return results

    # ---------------------------------------------------------------------- #
    # Opinion helpers
    # ---------------------------------------------------------------------- #

    def _notable_opinions(self) -> list[OpinionRecord]:
        """Extract significant temporary opinion modifiers involving the player."""
        results: list[OpinionRecord] = []

        for entry in self._opinions_list:
            if not isinstance(entry, dict):
                continue
            if "temporary_opinion" not in entry:
                continue

            owner  = entry.get("owner")
            target = entry.get("target")

            if owner == self.char_id:
                direction = "player_of_other"
                other_id  = target
            elif target == self.char_id:
                direction = "other_of_player"
                other_id  = owner
            else:
                continue

            if other_id is None:
                continue
            other_id = int(other_id)

            total, mods = _parse_opinion_modifiers(entry)
            if not mods:
                continue
            if abs(total) < _OPINION_THRESHOLD:
                continue

            results.append(OpinionRecord(
                other_id=other_id,
                other_name=self._char_name(other_id),
                direction=direction,
                total_value=total,
                modifiers=mods,
            ))

        return results


# --------------------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------------------- #

_TIER_MAP = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}


def _tier_order(tier: str) -> int:
    return _TIER_MAP.get(tier, 9)


def _humanize_title_key(key: str) -> str:
    """Convert a raw title key like 'c_desmond' to 'Count of Desmond'."""
    if not key:
        return "(no title)"
    _RULER_LABEL = {"e": "Emperor", "k": "King", "d": "Duke", "c": "Count", "b": "Baron"}
    tier = key[0] if key else "b"
    label = _RULER_LABEL.get(tier, "Lord")
    place = key[2:].replace("_", " ").title() if len(key) > 2 else key
    return f"{label} of {place}"


def _contract_label(contract_group: str) -> str:
    return {
        "feudal_vassal":   "Feudal vassals",
        "tribal_vassal":   "Tribal vassals",
        "clan_vassal":     "Clan vassals",
        "republic_vassal": "Republic vassals",
    }.get(contract_group, contract_group.replace("_", " ").title())


def _parse_opinion_modifiers(entry: dict) -> tuple[int, list[dict]]:
    """
    Parse the temporary_opinion field of an opinion entry.
    Returns (total_value, list_of_modifier_dicts).
    Handles both single-dict and list forms (Clausewitz parser duplicate merging).
    """
    raw = entry.get("temporary_opinion")
    if raw is None:
        return 0, []
    mods_raw = raw if isinstance(raw, list) else [raw]
    mods: list[dict] = []
    total = 0
    for m in mods_raw:
        if not isinstance(m, dict):
            continue
        val = m.get("value", 0)
        val_int = int(val) if isinstance(val, (int, float)) else 0
        total += val_int
        mods.append({
            "modifier":        m.get("modifier", "unknown"),
            "value":           val_int,
            "expiration_date": m.get("expiration_date", ""),
        })
    return total, mods
