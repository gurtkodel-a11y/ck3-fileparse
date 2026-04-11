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

from ck3.gamestate import GameState, _ensure_list


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

        char_name = char.get("first_name", str(self.char_id))

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

        return MilitaryReport(
            char_id=self.char_id,
            char_name=char_name,
            game_date=gs.date,
            realm_strength=realm_strength,
            own_armies=own_armies,
            allied_armies=allied_armies,
            enemy_armies=enemy_armies,
            active_wars=wars,
        )

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    def _char_name(self, char_id: int) -> str:
        c = self.gs.character(char_id)
        return c.get("first_name", str(char_id)) if c else str(char_id)

    def _realm_strength(self, char: dict) -> RealmStrength:
        gs = self.gs
        ld = char.get("landed_data", {})

        levy_cap    = ld.get("levy", 0) or 0
        current_str = ld.get("current_strength", 0) or 0
        max_str     = ld.get("strength", 0) or 0
        maa_cap     = max(0, max_str - levy_cap)
        power       = ld.get("power", 0) or 0

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
                "name":   kc.get("first_name", str(k_id)),
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

def _participants(war: dict, side: str) -> list[int]:
    side_data = war.get(side, {})
    if not isinstance(side_data, dict):
        return []
    ids = []
    for p in _ensure_list(side_data.get("participants", [])):
        if isinstance(p, dict) and "character" in p:
            ids.append(int(p["character"]))
    return ids
