"""
ck3.evaluators.culture
~~~~~~~~~~~~~~~~~~~~~~~
Level-1 culture evaluator: surfaces the cultural landscape visible to a
character — their own culture, nearby cultures, language groups, faiths, and
holy wars in progress.

Religion is one important axis of culture; this module surfaces faith data
alongside cultural identity so both can be considered together.

Usage:
    from ck3.evaluators.culture import CultureEvaluator
    ev = CultureEvaluator(gs, char_id=18269)
    report = ev.report()
    print(report.summary())
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from ck3.gamestate import GameState, _ensure_list
from ck3.geography import KINGDOM_TO_REGION, zone_between, kingdom_to_region
from ck3.names import decode_name, char_label


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass
class FaithProfile:
    """Everything knowable about a single faith from the save file."""
    faith_id: str
    tag: str                      # e.g. "catholic", "sunni"
    religion_id: str              # integer ID (as str) of the parent religion
    religion_tag: str             # e.g. "christianity", "islam"
    religion_family: str          # e.g. "rf_christian", "rf_islam", "rf_pagan"
    fervor: float
    religious_head_id: int | None # character ID, or None if no head
    religious_head_name: str | None
    doctrines: list[str]
    tenets: list[str]
    relation_to_player: str       # "same_faith" | "same_religion" | "same_family" | "other"
    titles_held: int              # how many titles (all tiers) are held by chars of this faith
    rulers_of_faith: list[dict]   # [{id, name, highest_title_key, highest_tier}]
    zone: int                     # proximity to player: 0=local, 1=nearby, 2=continental, 3=global


@dataclass
class HolyWar:
    """A war whose casus belli is explicitly religious."""
    war_id: str
    cb_type: str
    start_date: str
    attacker_faith: str
    defender_faith: str
    attacker_ids: list[int]
    attacker_names: list[str]
    defender_ids: list[int]
    defender_names: list[str]
    involves_player: bool


@dataclass
class CultureReport:
    """Full level-1 culture report for one character."""
    char_id: int
    char_name: str
    game_date: str
    # ── Faith / Religion ──────────────────────────────────────────────────── #
    own_faith_id: str
    own_faith_tag: str
    own_faith_fervor: float
    own_religion_id: str          # integer ID (as str) of the player's parent religion
    own_religion_tag: str         # e.g. "christianity", "islam"
    own_religion_family: str      # e.g. "rf_christian", "rf_islam", "rf_pagan"
    player_region: str            # geographic region of the player's capital kingdom
    faiths: list[FaithProfile]    # all faiths with at least one title-holding ruler
    holy_wars: list[HolyWar]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"Culture Report — {self.char_name} (id {self.char_id})  [{self.game_date}]",
            "=" * 70,
        ]

        # ── Religion section ─────────────────────────────────────────────── #
        lines += [
            "\n--- Religion ---",
            f"Your faith:    {self.own_faith_tag}  (fervor {self.own_faith_fervor:.1f})",
            f"Your religion: {self.own_religion_tag}",
            f"Your family:   {self.own_religion_family}",
        ]

        own = next((f for f in self.faiths if f.relation_to_player == "same_faith"), None)
        if own:
            lines += [
                f"Titles held by your faith: {own.titles_held}",
                f"Tenets:    {', '.join(own.tenets) or 'none'}",
                f"Doctrines: {', '.join(own.doctrines[:6])}{'...' if len(own.doctrines) > 6 else ''}",
            ]
            if own.religious_head_name:
                lines.append(f"Religious head: {own.religious_head_name} (id {own.religious_head_id})")

        # ── Zone 0+1: Local & Nearby — full detail ────────────────────────── #
        local_nearby = [f for f in self.faiths if f.zone <= 1]
        local_nearby.sort(key=lambda f: (f.relation_to_player != "same_faith", f.relation_to_player, -f.titles_held))

        lines.append(f"\n--- Faiths in Your Region & Neighbours ({len(local_nearby)}) ---")
        lines.append(f"  {'faith':<28}  {'fervor':>6}  {'titles':>6}  {'zone':<6}  {'relation':<13}")
        for f in local_nearby:
            marker = " ◄ YOUR FAITH" if f.relation_to_player == "same_faith" else ""
            zone_label = "local " if f.zone == 0 else "nearby"
            lines.append(
                f"  {f.tag:<28}  {f.fervor:>6.1f}  {f.titles_held:>6}  {zone_label}  {f.relation_to_player:<13}{marker}"
            )
            if f.religion_tag != f.tag:
                lines.append(f"    Religion: {f.religion_tag}  ({f.religion_family})")
            if f.tenets:
                lines.append(f"    Tenets: {', '.join(f.tenets)}")
            if f.religious_head_name:
                lines.append(f"    Head: {f.religious_head_name}")
            top_rulers = f.rulers_of_faith[:5]
            if top_rulers:
                ruler_strs = [
                    f"{r['name']} ({r['highest_title_key']})" for r in top_rulers
                ]
                lines.append(f"    Rulers: {', '.join(ruler_strs)}")

        # ── Zone 2: Continental — summary rows ────────────────────────────── #
        continental = [f for f in self.faiths if f.zone == 2]
        continental.sort(key=lambda f: -f.titles_held)

        lines.append(f"\n--- Continental Faiths (broader Europe / Med / Near East) ({len(continental)}) ---")
        lines.append(f"  {'faith':<28}  {'fervor':>6}  {'titles':>6}  {'relation':<13}")
        for f in continental:
            head = f"  head: {f.religious_head_name}" if f.religious_head_name else ""
            lines.append(
                f"  {f.tag:<28}  {f.fervor:>6.1f}  {f.titles_held:>6}  {f.relation_to_player:<13}{head}"
            )

        # ── Zone 3: Global — only major faiths (>50 titles) ──────────────── #
        global_major = [f for f in self.faiths if f.zone == 3 and f.titles_held >= 50]
        global_minor_count = sum(1 for f in self.faiths if f.zone == 3 and f.titles_held < 50)
        global_major.sort(key=lambda f: -f.titles_held)

        lines.append(f"\n--- Major Faiths Beyond the Horizon ({len(global_major)} shown, {global_minor_count} minor omitted) ---")
        lines.append(f"  {'faith':<28}  {'fervor':>6}  {'titles':>6}")
        for f in global_major:
            lines.append(
                f"  {f.tag:<28}  {f.fervor:>6.1f}  {f.titles_held:>6}"
            )

        # ── Holy Wars ────────────────────────────────────────────────────── #
        lines.append(f"\n--- Holy Wars ({len(self.holy_wars)}) ---")
        for w in self.holy_wars:
            you = "  *** INVOLVES YOU ***" if w.involves_player else ""
            atk = ", ".join(w.attacker_names)
            dfn = ", ".join(w.defender_names)
            lines += [
                f"  {w.cb_type}  since {w.start_date}{you}",
                f"    {w.attacker_faith} → attacks → {w.defender_faith}",
                f"    Attackers: {atk}",
                f"    Defenders: {dfn}",
            ]

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Evaluator
# --------------------------------------------------------------------------- #

# CB types that indicate a holy/religious war
_HOLY_WAR_CBS = {
    "great_holy_war_cb",
    "holy_war_cb",
    "religious_cb",
    "crusade_cb",
    "jihad_cb",
}

# Tier ordering for "highest title" selection
_TIER_ORDER = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}


class CultureEvaluator:
    def __init__(self, gs: GameState, char_id: int):
        self.gs = gs
        self.char_id = char_id
        gs.build_indices()

    def report(self) -> CultureReport:
        gs = self.gs
        char = gs.character(self.char_id)
        if char is None:
            raise ValueError(f"Character {self.char_id} not found in living")

        char_name = decode_name(char.get("first_name", str(self.char_id)))
        own_faith_id = str(char.get("faith", ""))
        own_faith = gs.faith(own_faith_id) or {}
        own_faith_tag = own_faith.get("tag", own_faith_id)
        own_faith_fervor = own_faith.get("fervor", 0.0)

        own_religion_id = str(own_faith.get("religion", ""))
        own_religion = gs.religion(own_religion_id) or {}
        own_religion_tag = own_religion.get("tag", own_religion_id)
        own_religion_family = own_religion.get("family", "")

        # Determine player's geographic region from their capital kingdom
        player_region = self._player_region(char)

        faith_profiles = self._build_faith_profiles(
            own_faith_id, own_religion_id, own_religion_family, player_region
        )
        holy_wars = self._find_holy_wars()

        return CultureReport(
            char_id=self.char_id,
            char_name=char_name,
            game_date=gs.date,
            own_faith_id=own_faith_id,
            own_faith_tag=own_faith_tag,
            own_faith_fervor=own_faith_fervor,
            own_religion_id=own_religion_id,
            own_religion_tag=own_religion_tag,
            own_religion_family=own_religion_family,
            player_region=player_region,
            faiths=faith_profiles,
            holy_wars=holy_wars,
        )

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    def _char_name(self, char_id: int) -> str:
        c = self.gs.character(char_id)
        return decode_name(c.get("first_name", str(char_id))) if c else str(char_id)

    def _player_region(self, char: dict) -> str:
        """
        Determine the player's geographic region from their highest-tier title.
        Falls back to 'global' if nothing can be resolved.
        """
        gs = self.gs
        ld = char.get("landed_data", {})
        domain_ids = _ensure_list(ld.get("domain", []))

        best_tier = 99
        best_region = "global"
        tier_order = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}

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

    def _build_faith_profiles(
        self,
        own_faith_id: str,
        own_religion_id: str,
        own_religion_family: str,
        player_region: str,
    ) -> list[FaithProfile]:
        gs = self.gs

        # Count titles per faith and collect rulers
        faith_title_count: dict[str, int] = defaultdict(int)
        faith_rulers: dict[str, list[dict]] = defaultdict(list)

        for tid, title in gs.titles.items():
            if not isinstance(title, dict):
                continue
            holder_id = title.get("holder")
            if holder_id is None:
                continue
            char = gs.character(holder_id)
            if not char:
                continue
            faith_id = str(char.get("faith", ""))
            if not faith_id:
                continue

            faith_title_count[faith_id] += 1

            # Track rulers (one entry per character per faith, keep highest title)
            title_key = title.get("key", "")
            tier_prefix = title_key[0] if title_key else "b"
            tier_order = _TIER_ORDER.get(tier_prefix, 4)

            existing = next(
                (r for r in faith_rulers[faith_id] if r["id"] == holder_id), None
            )
            if existing is None:
                faith_rulers[faith_id].append({
                    "id": holder_id,
                    "name": decode_name(char.get("first_name", str(holder_id))),
                    "highest_title_key": title_key,
                    "highest_tier": tier_prefix,
                    "_tier_order": tier_order,
                })
            elif tier_order < existing["_tier_order"]:
                existing["highest_title_key"] = title_key
                existing["highest_tier"] = tier_prefix
                existing["_tier_order"] = tier_order

        # Build profiles for faiths that have any rulers
        profiles = []
        for faith_id, count in faith_title_count.items():
            faith_data = gs.faith(faith_id) or {}
            tag = faith_data.get("tag", faith_id)
            fervor = faith_data.get("fervor", 0.0)

            religion_id = str(faith_data.get("religion", ""))
            religion_data = gs.religion(religion_id) or {}
            religion_tag = religion_data.get("tag", religion_id)
            religion_family = religion_data.get("family", "")

            doctrines = _ensure_list(faith_data.get("doctrine", []))
            tenets = [d for d in doctrines if d.startswith("tenet_")]
            core_docs = [d for d in doctrines if not d.startswith("tenet_")]

            head_id = faith_data.get("religious_head")
            # 4294967295 is the sentinel for "no head" in Paradox saves
            if head_id is not None and int(head_id) == 4294967295:
                head_id = None
            head_name = self._char_name(head_id) if head_id else None

            # Classify relationship to player's faith (four levels of closeness)
            if faith_id == own_faith_id:
                relation = "same_faith"
            elif religion_id == own_religion_id:
                relation = "same_religion"
            elif religion_family == own_religion_family:
                relation = "same_family"
            else:
                relation = "other"

            # Clean up internal sort key before exposing
            rulers = faith_rulers[faith_id]
            for r in rulers:
                r.pop("_tier_order", None)

            # Compute geographic zone from the faith's rulers' highest titles
            zone = self._faith_zone(rulers, player_region)

            profiles.append(FaithProfile(
                faith_id=faith_id,
                tag=tag,
                religion_id=religion_id,
                religion_tag=religion_tag,
                religion_family=religion_family,
                fervor=fervor,
                religious_head_id=head_id,
                religious_head_name=head_name,
                doctrines=core_docs,
                tenets=tenets,
                relation_to_player=relation,
                titles_held=count,
                rulers_of_faith=rulers,
                zone=zone,
            ))

        return profiles

    def _faith_zone(self, rulers: list[dict], player_region: str) -> int:
        """
        Return the proximity zone (0–3) for a faith based on where its
        highest-tier rulers hold titles.  Takes the minimum zone across all
        rulers (i.e. the closest any ruler is to the player).
        """
        gs = self.gs
        best = 3
        for ruler in rulers:
            title_key = ruler.get("highest_title_key", "")
            if not title_key:
                continue
            kingdom_key = gs.title_key_to_kingdom(title_key)
            faith_region = kingdom_to_region(kingdom_key)
            z = zone_between(player_region, faith_region)
            if z < best:
                best = z
            if best == 0:
                break
        return best

    def _find_holy_wars(self) -> list[HolyWar]:
        gs = self.gs
        holy_wars = []

        for wid, war in gs.active_wars.items():
            if not isinstance(war, dict):
                continue
            cb = war.get("casus_belli", {})
            cb_type = cb.get("type", "") if isinstance(cb, dict) else ""
            if not any(hw in cb_type for hw in _HOLY_WAR_CBS):
                continue

            atk_ids = _participants(war, "attacker")
            def_ids = _participants(war, "defender")

            atk_faith = self._dominant_faith(atk_ids)
            def_faith = self._dominant_faith(def_ids)

            involves = (self.char_id in atk_ids or self.char_id in def_ids)

            holy_wars.append(HolyWar(
                war_id=str(wid),
                cb_type=cb_type,
                start_date=war.get("start_date", ""),
                attacker_faith=atk_faith,
                defender_faith=def_faith,
                attacker_ids=atk_ids,
                attacker_names=[self._char_name(i) for i in atk_ids],
                defender_ids=def_ids,
                defender_names=[self._char_name(i) for i in def_ids],
                involves_player=involves,
            ))

        return holy_wars

    def _dominant_faith(self, char_ids: list[int]) -> str:
        """Return the faith tag of the first char_id that has one."""
        for cid in char_ids:
            c = self.gs.character(cid)
            if c:
                fid = str(c.get("faith", ""))
                faith = self.gs.faith(fid)
                if faith:
                    return faith.get("tag", fid)
        return "unknown"


# --------------------------------------------------------------------------- #
# Helpers
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
