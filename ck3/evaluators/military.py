"""
ck3.evaluators.military
~~~~~~~~~~~~~~~~~~~~~~~
Level-1 military evaluator: surfaces the raw military situation for a
character without making strategic judgements (those come at level 2).

Output is plain dicts/lists — easy to feed into pandas or print.

Usage:
    from ck3.evaluators.military import MilitaryEvaluator
    ev = MilitaryEvaluator(gs, char_id=18269)
    report = ev.report()
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

from ck3.gamestate import GameState
from ck3.names import decode_name, char_label
from ck3.geography import kingdom_to_region, zone_between
from ck3.evaluators.base import (
    _ensure_list, _participants, title_full_label,
)


# --------------------------------------------------------------------------- #
# Data classes (structured output)
# --------------------------------------------------------------------------- #

@dataclass
class FieldArmy:
    """A single army on the map."""
    army_id: str
    owner_id: int
    owner_name: str
    commander_id: int | None
    commander_name: str | None
    location_province: int
    current_troops: int
    max_troops: int
    combat_power: int
    is_raiding: bool
    is_retreating: bool
    relationship: str        # "own" | "allied" | "enemy" | "neutral"


@dataclass
class ActiveWar:
    """One active war."""
    war_id: str
    start_date: str
    casus_belli: str
    attacker_ids: list[int]
    attacker_names: list[str]
    defender_ids: list[int]
    defender_names: list[str]
    targeted_title_ids: list[int]
    subject_role: str        # "attacker" | "defender" | "observer"


@dataclass
class RealmStrength:
    """The character's own realm-wide military resources."""
    char_id: int
    total_troops: int        # levy + MaA currently raised (current_strength)
    total_max: int           # levy cap + MaA cap combined (strength)
    levy_capacity: int       # maximum possible levy (levy field in landed_data)
    maa_capacity: int        # maximum men-at-arms = total_max - levy_capacity
    combat_power: int        # game's internal power metric (bonuses included)
    domain_garrisons: list[dict]   # per-province garrison info
    knights: list[dict]      # each knight: id, name, prowess, power


@dataclass
class NearbyRuler:
    """Military profile of a politically or geographically relevant ruler."""
    char_id: int
    char_name: str
    highest_title_key: str
    highest_title_tier: str
    political_relation: str   # "liege"|"vassal"|"ally"|"at_war"|"geo_neighbor"
    geo_zone: int             # 0=local, 1=nearby, 2=continental, 3=global
    levy_capacity: int
    maa_capacity: int
    total_max: int
    current_troops: int
    combat_power: int
    faith_tag: str


@dataclass
class MilitaryReport:
    """Full level-1 military report for one character."""
    char_id: int
    char_name: str
    game_date: str
    realm_strength: RealmStrength
    own_armies: list[FieldArmy]
    allied_armies: list[FieldArmy]
    enemy_armies: list[FieldArmy]
    active_wars: list[ActiveWar]
    nearby_rulers: list[NearbyRuler]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        """Human-readable one-page summary."""
        lines = [
            f"Military Report — {self.char_name} (id {self.char_id})  [{self.game_date}]",
            "=" * 70,
        ]

        rs = self.realm_strength
        lines += [
            "\n--- Realm Strength ---",
            f"  Levy capacity:     {rs.levy_capacity:>6,}",
            f"  Men-at-arms cap:   {rs.maa_capacity:>6,}",
            f"  ─────────────────────────",
            f"  Total max:         {rs.total_max:>6,}",
            f"  Currently raised:  {rs.total_troops:>6,}  (levy + MaA combined)",
            f"  Combat power:      {rs.combat_power:>6,}  (game internal metric)",
            f"  Knights ({len(rs.knights)}):",
        ]
        for k in rs.knights:
            lines.append(f"    {k['name']:<24}  prowess {k['prowess']}  power {k['power']}")

        lines.append(f"\n--- Own Armies ({len(self.own_armies)}) ---")
        for a in self.own_armies:
            cmd = a.commander_name or "no commander"
            lines.append(
                f"  Army {a.army_id:<12}  prov {a.location_province:<6}"
                f"  {a.current_troops:>5}/{a.max_troops:<5} troops"
                f"  power {a.combat_power:>6}  cmd: {cmd}"
                + ("  [RAIDING]" if a.is_raiding else "")
                + ("  [RETREATING]" if a.is_retreating else "")
            )

        lines.append(f"\n--- Allied Armies ({len(self.allied_armies)}) ---")
        for a in self.allied_armies:
            lines.append(
                f"  {a.owner_name:<24}  army {a.army_id:<12}"
                f"  prov {a.location_province:<6}  {a.current_troops:>5}/{a.max_troops:<5}"
                f"  power {a.combat_power:>6}"
            )

        lines.append(f"\n--- Enemy Armies ({len(self.enemy_armies)}) ---")
        for a in self.enemy_armies:
            lines.append(
                f"  {a.owner_name:<24}  army {a.army_id:<12}"
                f"  prov {a.location_province:<6}  {a.current_troops:>5}/{a.max_troops:<5}"
                f"  power {a.combat_power:>6}"
            )

        lines.append(f"\n--- Active Wars ({len(self.active_wars)}) ---")
        for w in self.active_wars:
            atk = ", ".join(w.attacker_names) or "unknown"
            dfn = ", ".join(w.defender_names) or "unknown"
            role = w.subject_role.upper()
            lines.append(
                f"  [{role}] {w.casus_belli}  since {w.start_date}\n"
                f"    Attackers: {atk}\n"
                f"    Defenders: {dfn}"
            )

        # ── Nearby Rulers ─────────────────────────────────────────────────── #
        _REL_ORDER = {"liege": 0, "vassal": 1, "ally": 2, "at_war": 3, "geo_neighbor": 4}
        _ZONE_LABEL = {0: "local", 1: "nearby", 2: "continental", 3: "global"}

        groups: dict[str, list[NearbyRuler]] = {}
        for nr in self.nearby_rulers:
            groups.setdefault(nr.political_relation, []).append(nr)

        _GROUP_HEADER = {
            "liege":        "Liege",
            "vassal":       "Direct Vassals",
            "ally":         "Allies",
            "at_war":       "Active War Enemies",
            "geo_neighbor": "Geographic Neighbors (local/nearby)",
        }

        lines.append(f"\n--- Nearby Rulers — Political & Geographic Context ({len(self.nearby_rulers)}) ---")
        _GEO_NEIGHBOR_DISPLAY_LIMIT = 30

        for rel in ("liege", "vassal", "ally", "at_war", "geo_neighbor"):
            rulers = groups.get(rel, [])
            if not rulers:
                continue
            rulers.sort(key=lambda r: (-r.total_max, r.char_name))
            display = rulers[:_GEO_NEIGHBOR_DISPLAY_LIMIT] if rel == "geo_neighbor" else rulers
            omitted = len(rulers) - len(display)
            lines.append(f"  [{_GROUP_HEADER[rel]}]")
            for r in display:
                zone_str = _ZONE_LABEL.get(r.geo_zone, "?")
                lines.append(
                    f"    {r.char_name:<32}  {title_full_label(r.highest_title_key):<28}"
                    f"  levy {r.levy_capacity:>5,}  total {r.total_max:>5,}"
                    f"  power {int(r.combat_power):>6,}  [{zone_str}]  {r.faith_tag}"
                )
            if omitted:
                lines.append(f"    … and {omitted} more (county+ tier, zone 0–1)")

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Evaluator
# --------------------------------------------------------------------------- #

class MilitaryEvaluator:
    def __init__(self, gs: GameState, char_id: int):
        self.gs = gs
        self.char_id = char_id
        gs.build_indices()

    def report(self) -> MilitaryReport:
        gs = self.gs
        char = gs.character(self.char_id)
        if char is None:
            raise ValueError(f"Character {self.char_id} not found in living")

        char_name = char_label(char, gs, self.char_id)

        # Determine war sides first — needed to classify armies
        wars = self._active_wars()
        enemy_ids: set[int] = set()
        allied_ids: set[int] = set()
        for w in wars:
            if w.subject_role == "attacker":
                allied_ids.update(w.attacker_ids)
                enemy_ids.update(w.defender_ids)
            elif w.subject_role == "defender":
                allied_ids.update(w.defender_ids)
                enemy_ids.update(w.attacker_ids)
        allied_ids.discard(self.char_id)

        realm_strength = self._realm_strength(char)
        own_armies, allied_armies, enemy_armies = self._classify_armies(
            enemy_ids, allied_ids
        )

        player_region = self._player_region(char)
        ally_ids_rel = self._ally_ids_from_relations()
        all_ally_ids = allied_ids | ally_ids_rel
        nearby_rulers = self._nearby_rulers(player_region, enemy_ids, all_ally_ids)

        return MilitaryReport(
            char_id=self.char_id,
            char_name=char_name,
            game_date=gs.date,
            realm_strength=realm_strength,
            own_armies=own_armies,
            allied_armies=allied_armies,
            enemy_armies=enemy_armies,
            active_wars=wars,
            nearby_rulers=nearby_rulers,
        )

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    def _player_region(self, char: dict) -> str:
        """Determine the player's geographic region from their highest-tier title."""
        gs = self.gs
        ld = char.get("landed_data", {})
        domain_ids = _ensure_list(ld.get("domain", []))
        tier_order = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}
        best_tier = 99
        best_region = "global"
        for title_id in domain_ids:
            t = gs.title(title_id)
            if not isinstance(t, dict):
                continue
            key = t.get("key", "")
            if not key:
                continue
            tier = tier_order.get(key[0], 9)
            if tier < best_tier:
                kingdom_key = gs.title_key_to_kingdom(key)
                region = kingdom_to_region(kingdom_key)
                if region != "global":
                    best_tier = tier
                    best_region = region
        return best_region

    def _ally_ids_from_relations(self) -> set[int]:
        """Collect ally char IDs from active_relations alliance bonds."""
        gs = self.gs
        allies: set[int] = set()
        for rel in gs.active_relations:
            if not isinstance(rel, dict):
                continue
            first = rel.get("first")
            second = rel.get("second")
            if first != self.char_id and second != self.char_id:
                continue
            if not _ensure_list(rel.get("alliances", [])):
                continue
            other_id = second if first == self.char_id else first
            # Only count rulers — unlanded "allies" are just marriage mediators
            if gs.titles_held_by(other_id):
                allies.add(other_id)
        return allies

    def _nearby_rulers(
        self,
        player_region: str,
        enemy_ids: set[int],
        ally_ids: set[int],
    ) -> list[NearbyRuler]:
        """
        Build a list of politically or geographically relevant rulers with
        their full military strength profile.

        Includes:
          - Direct liege (if any)
          - Direct vassals
          - Formal allies (from active_relations)
          - Active war enemies
          - Any landed ruler whose highest title falls in zone 0 or 1
        """
        gs = self.gs
        tier_order = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}

        # Determine liege and vassal IDs
        liege_contract = gs.contract_for_vassal(self.char_id)
        liege_id: int | None = liege_contract.get("liege") if liege_contract else None

        vassal_ids: set[int] = set()
        for contract in gs.contracts_for_liege(self.char_id):
            if isinstance(contract, dict) and contract.get("vassal") is not None:
                vassal_ids.add(contract["vassal"])

        # Gather each landed character's highest title (skip the player)
        char_best_title: dict[int, tuple[str, str]] = {}   # char_id → (key, tier)
        for tid, title in gs.titles.items():
            if not isinstance(title, dict):
                continue
            holder_id = title.get("holder")
            if holder_id is None or holder_id == self.char_id:
                continue
            key = title.get("key", "")
            if not key:
                continue
            tier = key[0]
            order = tier_order.get(tier, 4)
            prev = char_best_title.get(holder_id)
            if prev is None or order < tier_order.get(prev[1], 4):
                char_best_title[holder_id] = (key, tier)

        results: list[NearbyRuler] = []
        for char_id, (title_key, title_tier) in char_best_title.items():
            kingdom_key = gs.title_key_to_kingdom(title_key)
            char_region = kingdom_to_region(kingdom_key)
            geo_zone = zone_between(player_region, char_region)

            # Classify political relation
            if char_id == liege_id:
                relation = "liege"
            elif char_id in vassal_ids:
                relation = "vassal"
            elif char_id in ally_ids:
                relation = "ally"
            elif char_id in enemy_ids:
                relation = "at_war"
            elif geo_zone <= 1:
                # Only county-tier and above — barons are too numerous to be useful
                if tier_order.get(title_tier, 4) > 3:
                    continue
                relation = "geo_neighbor"
            else:
                continue  # not relevant

            char = gs.character(char_id)
            if not char:
                continue

            ld = char.get("landed_data", {})
            levy_cap   = int(ld.get("levy", 0) or 0)
            total_max  = int(ld.get("strength", 0) or 0)
            current    = int(ld.get("current_strength", 0) or 0)
            power      = int(ld.get("power", 0) or 0)
            maa_cap    = max(0, total_max - levy_cap)

            faith_id  = str(char.get("faith", ""))
            faith_data = gs.faith(faith_id) or {}
            faith_tag  = faith_data.get("tag", faith_id)

            results.append(NearbyRuler(
                char_id=char_id,
                char_name=char_label(char, gs, char_id),
                highest_title_key=title_key,
                highest_title_tier=title_tier,
                political_relation=relation,
                geo_zone=geo_zone,
                levy_capacity=levy_cap,
                maa_capacity=maa_cap,
                total_max=total_max,
                current_troops=current,
                combat_power=power,
                faith_tag=faith_tag,
            ))

        return results

    def _char_name(self, char_id: int) -> str:
        c = self.gs.character(char_id)
        return decode_name(c.get("first_name", str(char_id))) if c else str(char_id)

    def _realm_strength(self, char: dict) -> RealmStrength:
        gs = self.gs
        ld = char.get("landed_data", {})

        levy_cap = ld.get("levy", 0) or 0
        max_str  = ld.get("strength", 0) or 0
        maa_cap  = max(0, max_str - levy_cap)
        power    = ld.get("power", 0) or 0

        # Sum current troops from active army units owned by the player.
        # landed_data.current_strength reflects max available capacity, not
        # raised troops — it only decreases when armies take casualties.
        current_str = 0
        for army_id, army in gs.armies.items():
            if not isinstance(army, dict):
                continue
            unit_id = army.get("unit")
            if unit_id is None:
                continue
            unit = gs.units.get(str(unit_id))
            if not isinstance(unit, dict):
                continue
            if unit.get("owner") != self.char_id:
                continue
            current_str += gs.army_strength(army_id)["current"]

        # Domain garrisons
        garrisons = []
        for title_id in _ensure_list(ld.get("domain", [])):
            t = gs.title(title_id)
            if not t:
                continue
            prov_id = t.get("capital")
            if prov_id is None:
                continue
            prov = gs.provinces.get(str(prov_id), {})
            holding = prov.get("holding", {}) if isinstance(prov, dict) else {}
            garrisons.append({
                "title_key":    t.get("key", str(title_id)),
                "province_id":  prov_id,
                "holding_type": holding.get("type", "unknown"),
                "garrison_id":  holding.get("garrison"),
                "levy_id":      holding.get("levy"),
                "fort_level":   prov.get("fort_level", 0) if isinstance(prov, dict) else 0,
            })

        # Knights
        knights = []
        for k_id in _ensure_list(char.get("playable_data", {}).get("knights", [])):
            kc = gs.character(k_id)
            if not kc:
                continue
            skills = kc.get("skill", [])
            prowess = skills[5] if len(skills) > 5 else 0
            knights.append({
                "id":     k_id,
                "name":   decode_name(kc.get("first_name", str(k_id))),
                "prowess": prowess,
                "power":  prowess * 100,   # CK3 approximation: each prowess ≈ 100 power
            })

        return RealmStrength(
            char_id=self.char_id,
            total_troops=current_str,
            total_max=max_str,
            levy_capacity=levy_cap,
            maa_capacity=maa_cap,
            combat_power=power,
            domain_garrisons=garrisons,
            knights=knights,
        )

    def _classify_armies(
        self,
        enemy_ids: set[int],
        allied_ids: set[int],
    ) -> tuple[list[FieldArmy], list[FieldArmy], list[FieldArmy]]:
        gs = self.gs
        own, allied, enemy = [], [], []

        for army_id, army in gs.armies.items():
            if not isinstance(army, dict):
                continue
            # Find the unit record for this army to get owner + location
            unit_id = army.get("unit")
            if unit_id is None:
                continue
            unit = gs.units.get(str(unit_id))
            if not unit or not isinstance(unit, dict):
                continue

            owner_id = unit.get("owner")
            if owner_id is None:
                continue
            location = unit.get("location", 0)

            strength = gs.army_strength(army_id)
            commander_id = army.get("commander")
            fa = FieldArmy(
                army_id=str(army_id),
                owner_id=owner_id,
                owner_name=self._char_name(owner_id),
                commander_id=commander_id,
                commander_name=self._char_name(commander_id) if commander_id else None,
                location_province=location,
                current_troops=strength["current"],
                max_troops=strength["max"],
                combat_power=strength["power"],
                is_raiding=bool(army.get("raid_army")),
                is_retreating=unit.get("retreating") is not None,
                relationship="own",
            )

            if owner_id == self.char_id:
                fa.relationship = "own"
                own.append(fa)
            elif owner_id in enemy_ids:
                fa.relationship = "enemy"
                enemy.append(fa)
            elif owner_id in allied_ids:
                fa.relationship = "allied"
                allied.append(fa)
            # neutral armies are omitted from the report (too noisy at level 1)

        return own, allied, enemy

    def _active_wars(self) -> list[ActiveWar]:
        gs = self.gs
        wars = []
        for wid, war in gs.wars_involving(self.char_id):
            if not isinstance(war, dict):
                continue

            atk_ids  = _participants(war, "attacker")
            def_ids  = _participants(war, "defender")

            if self.char_id in atk_ids:
                role = "attacker"
            elif self.char_id in def_ids:
                role = "defender"
            else:
                role = "observer"

            cb = war.get("casus_belli", {})
            cb_type = cb.get("type", "unknown") if isinstance(cb, dict) else "unknown"
            targeted = _ensure_list(cb.get("targeted_titles", []) if isinstance(cb, dict) else [])

            wars.append(ActiveWar(
                war_id=str(wid),
                start_date=war.get("start_date", ""),
                casus_belli=cb_type,
                attacker_ids=atk_ids,
                attacker_names=[self._char_name(i) for i in atk_ids],
                defender_ids=def_ids,
                defender_names=[self._char_name(i) for i in def_ids],
                targeted_title_ids=targeted,
                subject_role=role,
            ))
        return wars


# --------------------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------------------- #

