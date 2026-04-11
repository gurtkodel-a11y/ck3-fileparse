"""
ck3.evaluators.hierarchy
~~~~~~~~~~~~~~~~~~~~~~~~
Level-1 social hierarchy evaluator.

CK3 characters exist inside one or more overlapping social hierarchies.
The most common is the feudal system of lieges and vassals, but the same
data structures also represent tribal confederations, clan networks,
merchant republics, and ecclesiastical arrangements.  This evaluator
surfaces all of them in a uniform way.

The report has four sections:

  1. Position  — where the player sits in the hierarchy above them
                 (independent ruler / immediate liege / chain to the top)

  2. Vassals   — everyone who owes direct obligations to the player,
                 with the type of contract, their titles, military
                 contribution, and any faction threat they pose

  3. Alliances — lateral alliances (typically through marriage or
                 personal agreement), and the character through whom
                 each alliance is mediated

  4. Hooks     — leverage relationships: favour hooks, house-head hooks,
                 blackmail, etc. — both held by the player and held
                 on the player

Usage:
    from ck3.evaluators.hierarchy import HierarchyEvaluator
    ev = HierarchyEvaluator(gs, char_id=18269)
    report = ev.report()
    print(report.summary())
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

from ck3.gamestate import GameState, _ensure_list


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass
class LiegeRecord:
    """One rung in the hierarchy above the player."""
    char_id: int
    char_name: str
    highest_title_key: str    # e.g. "e_hre", "k_england"
    highest_title_tier: str   # "e" | "k" | "d" | "c" | "b"
    contract_group: str       # feudal_vassal / tribal_vassal / clan_vassal / republic_vassal
    is_top: bool              # True if they have no liege of their own


@dataclass
class VassalRecord:
    """A character who holds a direct vassal contract under the player."""
    char_id: int
    char_name: str
    contract_group: str       # feudal_vassal / tribal_vassal / clan_vassal / republic_vassal
    contract_date: str
    titles: list[str]         # all title keys held, highest tier first
    highest_title_tier: str   # "k" | "d" | "c" | "b"
    levy_capacity: int        # max levy from landed_data.levy (0 if not landed)
    total_strength: int       # total max troops (levy + MaA)
    in_faction_against_liege: bool   # True if in a faction targeting the player
    faction_types: list[str]  # faction type names if in_faction_against_liege


@dataclass
class AllianceRecord:
    """A lateral alliance between the player and another character."""
    ally_id: int
    ally_name: str
    ally_titles: list[str]    # highest-tier titles of the ally
    bond_count: int           # number of alliance bonds (>1 if multiple marriages reinforce it)
    is_negotiated: bool       # True if direct personal alliance (no marriage mediator)
    mediator_own_id: int | None    # character on player's side (None if negotiated)
    mediator_own_name: str | None
    mediator_ally_id: int | None   # character on ally's side (None if negotiated)
    mediator_ally_name: str | None


@dataclass
class HookRecord:
    """A leverage relationship between two characters."""
    other_id: int
    other_name: str
    hook_type: str            # e.g. "favor_hook", "house_head_hook", "blackmail_hook"
    expiration_date: str      # "9999.1.1" = permanent
    direction: str            # "player_holds" | "held_on_player"


@dataclass
class FactionRecord:
    """A faction that is actively working against the player."""
    faction_id: str
    faction_type: str         # e.g. "independence_faction", "claimant_faction"
    demand: str               # what the faction wants
    member_ids: list[int]
    member_names: list[str]
    member_count: int


@dataclass
class HierarchyReport:
    """Full level-1 social hierarchy report for one character."""
    char_id: int
    char_name: str
    game_date: str
    is_independent: bool
    liege_chain: list[LiegeRecord]     # immediate liege first, then their liege, etc.
    direct_vassals: list[VassalRecord]
    alliances: list[AllianceRecord]
    hooks_held: list[HookRecord]       # player holds these on others
    hooks_on_player: list[HookRecord]  # others hold these on the player
    factions_against: list[FactionRecord]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"Hierarchy Report — {self.char_name} (id {self.char_id})  [{self.game_date}]",
            "=" * 70,
        ]

        # ── Position ─────────────────────────────────────────────────────── #
        lines.append("\n--- Your Position in the Hierarchy ---")
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

        # ── Vassals ──────────────────────────────────────────────────────── #
        lines.append(f"\n--- Direct Vassals ({len(self.direct_vassals)}) ---")
        # Group by contract type for readability
        by_type: dict[str, list[VassalRecord]] = {}
        for v in self.direct_vassals:
            by_type.setdefault(v.contract_group, []).append(v)

        for ctype, vassals in sorted(by_type.items()):
            label = _contract_label(ctype)
            lines.append(f"  [{label}]")
            for v in sorted(vassals, key=lambda x: (_tier_order(x.highest_title_tier), x.char_name)):
                faction_flag = "  ⚠ IN FACTION" if v.in_faction_against_liege else ""
                faction_detail = f" ({', '.join(v.faction_types)})" if v.faction_types else ""
                title_str = v.titles[0] if v.titles else "(no title)"
                lines.append(
                    f"    {v.char_name:<22}  {title_str:<28}"
                    f"  levy {v.levy_capacity:>5,}  total {v.total_strength:>5,}"
                    f"{faction_flag}{faction_detail}"
                )

        # Faction summary
        if self.factions_against:
            lines.append(f"\n--- Factions Against You ({len(self.factions_against)}) ---")
            for f in self.factions_against:
                lines.append(
                    f"  {f.faction_type:<35}  demand: {f.demand}"
                    f"  ({f.member_count} members)"
                )
                if f.member_names:
                    lines.append(f"    Leaders: {', '.join(f.member_names[:5])}")

        # ── Alliances ────────────────────────────────────────────────────── #
        lines.append(f"\n--- Alliances ({len(self.alliances)}) ---")
        for a in sorted(self.alliances, key=lambda x: x.ally_name):
            title_str = a.ally_titles[0] if a.ally_titles else "(unlanded)"
            bonds_str = f"  [{a.bond_count} bonds]" if a.bond_count > 1 else ""
            if a.is_negotiated:
                via = "negotiated"
            elif a.mediator_own_name and a.mediator_ally_name:
                via = f"via {a.mediator_own_name} ↔ {a.mediator_ally_name}"
            elif a.mediator_ally_name:
                via = f"via {a.mediator_ally_name}"
            else:
                via = "marriage"
            lines.append(f"  {a.ally_name:<22}  [{title_str}]{bonds_str}  — {via}")

        # ── Hooks ────────────────────────────────────────────────────────── #
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

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Evaluator
# --------------------------------------------------------------------------- #

class HierarchyEvaluator:
    def __init__(self, gs: GameState, char_id: int):
        self.gs = gs
        self.char_id = char_id
        gs.build_indices()

    def report(self) -> HierarchyReport:
        gs = self.gs
        char = gs.character(self.char_id)
        if char is None:
            raise ValueError(f"Character {self.char_id} not found in living")

        char_name = char.get("first_name", str(self.char_id))

        liege_chain = self._liege_chain()
        is_independent = len(liege_chain) == 0

        direct_vassals = self._direct_vassals()
        factions_against = self._factions_against()

        # Annotate vassals with faction membership
        faction_members: dict[int, list[str]] = {}
        for f in factions_against:
            for mid in f.member_ids:
                faction_members.setdefault(mid, []).append(f.faction_type)
        for v in direct_vassals:
            ftypes = faction_members.get(v.char_id, [])
            v.in_faction_against_liege = bool(ftypes)
            v.faction_types = ftypes

        alliances, hooks_held, hooks_on_player = self._relations()

        return HierarchyReport(
            char_id=self.char_id,
            char_name=char_name,
            game_date=gs.date,
            is_independent=is_independent,
            liege_chain=liege_chain,
            direct_vassals=direct_vassals,
            alliances=alliances,
            hooks_held=hooks_held,
            hooks_on_player=hooks_on_player,
            factions_against=factions_against,
        )

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    def _char_name(self, char_id: int | None) -> str:
        if char_id is None:
            return "unknown"
        c = self.gs.character(char_id)
        return c.get("first_name", str(char_id)) if c else str(char_id)

    def _highest_title(self, char_id: int) -> tuple[str, str]:
        """Return (title_key, tier_prefix) for the highest title held by char_id."""
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
        """All title keys held by char_id, sorted highest tier first."""
        titles = self.gs.titles_held_by(char_id)
        keyed = [(t.get("key", ""), t.get("key", "b")[0] if t.get("key") else "b")
                 for t in titles if isinstance(t, dict) and t.get("key")]
        keyed.sort(key=lambda x: _tier_order(x[1]))
        return [k for k, _ in keyed]

    def _liege_chain(self) -> list[LiegeRecord]:
        """Walk up the vassal-contract chain from the player to the top."""
        gs = self.gs
        chain = []
        seen = {self.char_id}
        current_id = self.char_id

        for _ in range(10):   # safety limit
            contract = gs.contract_for_vassal(current_id)
            if contract is None:
                break
            liege_id = contract.get("liege")
            if liege_id is None or liege_id in seen:
                break
            seen.add(liege_id)

            title_key, title_tier = self._highest_title(liege_id)
            # Is this liege themselves independent?
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
        """All characters holding a vassal contract directly under the player."""
        gs = self.gs
        vassals = []

        for contract in gs.contracts_for_liege(self.char_id):
            if not isinstance(contract, dict):
                continue
            vassal_id = contract.get("vassal")
            if vassal_id is None:
                continue

            vc = gs.character(vassal_id)
            vname = vc.get("first_name", str(vassal_id)) if vc else str(vassal_id)

            title_keys = self._all_title_keys(vassal_id)
            highest_tier = title_keys[0][0] if title_keys else "b"

            # Military contribution from their landed_data
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
                in_faction_against_liege=False,   # filled in after factions computed
                faction_types=[],
            ))

        return vassals

    def _factions_against(self) -> list[FactionRecord]:
        """Factions whose target is the player."""
        gs = self.gs
        results = []

        for fid, f in gs.factions.items():
            if not isinstance(f, dict):
                continue
            if f.get("target") != self.char_id:
                continue

            members = _ensure_list(f.get("members", []))
            member_names = [self._char_name(m) for m in members[:8]]

            results.append(FactionRecord(
                faction_id=str(fid),
                faction_type=f.get("type", "unknown"),
                demand=f.get("demand", "unknown"),
                member_ids=list(members),
                member_names=member_names,
                member_count=len(members),
            ))

        return results

    def _relations(
        self,
    ) -> tuple[list[AllianceRecord], list[HookRecord], list[HookRecord]]:
        """Parse active_relations for alliances and hooks involving the player."""
        gs = self.gs
        # ally_id → (bond_count, first_bond_dict, player_is_first)
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

            # ── Alliances ─────────────────────────────────────── #
            bonds = _ensure_list(rel.get("alliances", []))
            if bonds:
                # Only treat as a real alliance if the other party holds at least
                # a county-level title.  Unlanded characters in alliance relation
                # entries are mediators (spouses/children) whose own relation to
                # the player is a derivative of the main ruler-level alliance.
                other_titles = self._all_title_keys(other_id)
                other_is_ruler = any(
                    k[0] in ("e", "k", "d", "c") for k in other_titles
                )
                if other_is_ruler:
                    first_bond = next((b for b in bonds if isinstance(b, dict)), {})
                    if other_id in alliance_accum:
                        prev_count, prev_bond, prev_pif = alliance_accum[other_id]
                        alliance_accum[other_id] = (prev_count + len(bonds), prev_bond, prev_pif)
                    else:
                        alliance_accum[other_id] = (len(bonds), first_bond, player_is_first)

            # ── Hooks ─────────────────────────────────────────── #
            for key, val in rel.items():
                if not key.startswith("active_hook_"):
                    continue
                if not isinstance(val, dict):
                    continue
                hook_type = val.get("type", "unknown_hook")
                expiry = val.get("expiration_date", "9999.1.1")

                # Convention: active_hook_0 is held by 'first', active_hook_1 by 'second'
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

        # Build final AllianceRecord list from accumulator
        alliances: list[AllianceRecord] = []
        for ally_id, (bond_count, first_bond, player_is_first) in alliance_accum.items():
            med0 = first_bond.get("allied_through_0")
            med1 = first_bond.get("allied_through_1")
            # allied_through_0 mediates the alliance on behalf of whoever
            # appears first in the relation — not necessarily the player.
            # Detect negotiated alliance: mediators ARE the principals themselves.
            is_negotiated = (
                (med0 == self.char_id or med0 == ally_id) and
                (med1 == self.char_id or med1 == ally_id)
            )
            # Identify which mediator is on the player's side vs ally's side.
            # We use the heuristic that the mediator whose ID appears in the
            # player's title-holding network is on the player's side.
            if is_negotiated:
                med_own_id, med_own_name = None, None
                med_ally_id, med_ally_name = None, None
            else:
                # Assign: if med0 is a descendant/relative of the player
                # (i.e. holds no top titles and is in living) that's player-side.
                # Simpler heuristic: med0 owns no kingdom titles → likely player's child/spouse
                med0_titles = self._all_title_keys(med0) if med0 else []
                med0_is_player_side = (
                    med0 == self.char_id or
                    not any(k[0] in ("e", "k") for k in med0_titles)
                )
                if med0_is_player_side:
                    med_own_id, med_own_name = med0, self._char_name(med0) if med0 and med0 != self.char_id else None
                    med_ally_id, med_ally_name = med1, self._char_name(med1) if med1 else None
                else:
                    med_own_id, med_own_name = med1, self._char_name(med1) if med1 and med1 != self.char_id else None
                    med_ally_id, med_ally_name = med0, self._char_name(med0) if med0 else None

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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_TIER_MAP = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}

def _tier_order(tier: str) -> int:
    return _TIER_MAP.get(tier, 9)


def _contract_label(contract_group: str) -> str:
    return {
        "feudal_vassal":    "Feudal vassals",
        "tribal_vassal":    "Tribal vassals",
        "clan_vassal":      "Clan vassals",
        "republic_vassal":  "Republic vassals",
    }.get(contract_group, contract_group.replace("_", " ").title())
