"""
ck3.evaluators.matchmaker
~~~~~~~~~~~~~~~~~~~~~~~~~~
Screens the save's population for plausible spouse/betrothal candidates for
a given character (typically an unlanded child, but works for any living,
unmarried character).

Codifies the ad-hoc screen used for Judita's first betrothal pass: pull
everyone of the opposite gender within a sensible age window, drop anyone
already married/betrothed or too closely related, classify personality into
virtue/vice, split into a "noble" track (has a dynasty house — relevant for
title-driven alliances) and a "lowborn" track (no house — relevant for
matrilineal marriages), and rank by personality first, then by how close the
match is geographically/politically.

Usage::
    from ck3.evaluators.matchmaker import find_candidates
    report = find_candidates(gs, char_id=37766)   # Judita
    print(report.summary())

    # Same-faith Saxon nobles only, slightly wider age window:
    report = find_candidates(gs, char_id=37766, age_window=8, track="noble")
"""

from __future__ import annotations
from dataclasses import dataclass, field

from ck3.gamestate import GameState
from ck3.names import decode_name, house_prefix_name
from ck3.geography import kingdom_to_region, zone_between
from ck3.evaluators.character import _parse_date, _compute_age  # noqa: F401  (shared date math)


# --------------------------------------------------------------------------- #
# Personality classification
# --------------------------------------------------------------------------- #
# CK3's personality traits come in opposed pairs (game/common/traits/00_traits.txt
# defines them back-to-back but does not itself tag a side as "virtue"/"vice" —
# this mapping is CK3-domain knowledge, not data read from the save or game files.
# Childhood/flavor traits (curious, pensive, rowdy, bossy, ambitious, content,
# stubborn, fickle, eccentric, shy, gregarious, charming) are deliberately left
# unclassified: they aren't moral traits, and several (rowdy, bossy, curious,
# pensive) are just placeholders most children carry before their personality
# is rolled at adulthood.

VIRTUE_TRAITS: frozenset[str] = frozenset({
    "chaste", "temperate", "generous", "diligent", "calm", "patient",
    "humble", "honest", "brave", "just", "zealous", "trusting",
    "compassionate", "forgiving",
})

VICE_TRAITS: frozenset[str] = frozenset({
    "lustful", "gluttonous", "greedy", "lazy", "wrathful", "impatient",
    "arrogant", "deceitful", "craven", "arbitrary", "cynical", "paranoid",
    "callous", "sadistic", "vengeful",
})

_TIER_ORDER = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #

@dataclass
class MatchCandidate:
    char_id: int
    name: str
    age: int
    gender: str                    # "male" | "female"
    faith_tag: str
    religion_type: str
    culture_name: str | None

    traits: list[str]
    virtues: list[str]
    vices: list[str]

    is_noble: bool                 # has a dynasty house
    house_name: str | None
    track: str                     # "noble" | "lowborn"

    employer_id: int | None
    employer_name: str | None
    region: str                    # from geography.py, "global" if unresolved
    proximity_zone: int | None     # 0-3, None if region couldn't be resolved

    @property
    def score(self) -> int:
        """Higher is better: virtues count positively, vices count double against."""
        return len(self.virtues) - 2 * len(self.vices)

    def line(self) -> str:
        track_tag = "Noble" if self.is_noble else "Lowborn"
        house = f"  house: {self.house_name}" if self.house_name else ""
        zone = {0: "local", 1: "nearby", 2: "continental", 3: "global"}.get(self.proximity_zone, "unknown")
        virtues = ", ".join(self.virtues) if self.virtues else "-"
        vices = ", ".join(self.vices) if self.vices else "none"
        return (
            f"  {self.name:<20} (id {self.char_id})  age {self.age:>2}  [{track_tag}]{house}\n"
            f"      virtues: {virtues}  |  vices: {vices}\n"
            f"      faith: {self.faith_tag}  culture: {self.culture_name or '?'}  "
            f"proximity: {zone}  employer: {self.employer_name or '-'}"
        )


@dataclass
class MatchmakerReport:
    subject_id: int
    subject_name: str
    subject_age: int
    subject_gender: str
    subject_region: str
    candidates: list[MatchCandidate] = field(default_factory=list)

    def noble_candidates(self) -> list[MatchCandidate]:
        return [c for c in self.candidates if c.track == "noble"]

    def lowborn_candidates(self) -> list[MatchCandidate]:
        return [c for c in self.candidates if c.track == "lowborn"]

    def summary(self, limit: int = 10) -> str:
        lines = [
            f"Matchmaker — candidates for {self.subject_name} "
            f"(id {self.subject_id}, age {self.subject_age})",
            "=" * 60,
            f"{len(self.candidates)} candidate(s) found "
            f"({len(self.noble_candidates())} noble, {len(self.lowborn_candidates())} lowborn)",
            "",
        ]
        nobles = self.noble_candidates()[:limit]
        lowborn = self.lowborn_candidates()[:limit]
        if nobles:
            lines.append("--- Noble / alliance track ---")
            lines.extend(c.line() for c in nobles)
            lines.append("")
        if lowborn:
            lines.append("--- Lowborn / matrilineal track ---")
            lines.extend(c.line() for c in lowborn)
        if not nobles and not lowborn:
            lines.append("  (no candidates matched the current filters)")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _gender(char: dict) -> str:
    return "female" if char.get("female") else "male"


def _is_unavailable(char: dict) -> bool:
    """True if the character is already married or betrothed."""
    fd = char.get("family_data", {})
    if not isinstance(fd, dict):
        return False
    return bool(fd.get("primary_spouse") or fd.get("spouse") or fd.get("betrothed"))


def _classify_traits(gs: GameState, char: dict) -> tuple[list[str], list[str], list[str]]:
    trait_ids = char.get("traits", [])
    if not isinstance(trait_ids, list):
        trait_ids = [trait_ids]
    names = gs.trait_names([t for t in trait_ids if isinstance(t, int)])
    virtues = [t for t in names if t in VIRTUE_TRAITS]
    vices = [t for t in names if t in VICE_TRAITS]
    return names, virtues, vices


def _house_name(gs: GameState, house_id) -> str | None:
    if house_id is None:
        return None
    house = gs.dynasty_house(house_id)
    if not house:
        return None
    try:
        prefix, name = house_prefix_name(house)
    except Exception:
        return None
    return f"{prefix} {name}".strip() if prefix else name


def _house_head(gs: GameState, char: dict) -> dict | None:
    house_id = char.get("dynasty_house")
    if house_id is None:
        return None
    house = gs.dynasty_house(house_id)
    head_id = house.get("head_of_house") if house else None
    return gs.character(head_id) if head_id else None


def _resolve_field(gs: GameState, char: dict, field_name: str):
    """Unlanded characters often lack 'faith'/'culture' directly; fall back to
    their dynasty house head's value, same convention as character_profile()."""
    value = char.get(field_name)
    if value:
        return value
    head = _house_head(gs, char)
    return head.get(field_name) if head else None


def _faith_info(gs: GameState, char: dict) -> tuple[str, str]:
    """Return (faith_tag, religion_type) for a character, e.g. ('catholic', 'christianity_religion')."""
    faith_id = _resolve_field(gs, char, "faith")
    faith = gs.faith(faith_id) if faith_id is not None else None
    if not faith:
        return "unknown", "unknown"
    tag = faith.get("tag", "unknown")
    religion = gs.religion(faith.get("religion")) if faith.get("religion") is not None else None
    religion_type = religion.get("religion_type", "unknown") if religion else "unknown"
    return tag, religion_type


def _culture_name(gs: GameState, char: dict) -> str | None:
    culture_id = _resolve_field(gs, char, "culture")
    culture = gs.culture(culture_id) if culture_id is not None else None
    return culture.get("name") if culture else None


def _char_region(gs: GameState, char_id: int, char: dict, _depth: int = 0) -> str:
    """
    Resolve a character's geographic region via their own highest title,
    falling back to their employer's domain (recursively, since an unlanded
    courtier's "location" is really their employer's realm). Gives up after
    3 hops and returns "global" (unresolved) rather than risking a cycle.
    """
    if _depth > 3:
        return "global"

    best_tier = 99
    best_region = None
    for title in gs.titles_held_by(char_id):
        key = title.get("key", "")
        if not key:
            continue
        tier = _TIER_ORDER.get(key[0], 9)
        if tier < best_tier:
            region = kingdom_to_region(gs.title_key_to_kingdom(key))
            if region != "global":
                best_tier = tier
                best_region = region
    if best_region:
        return best_region

    cd = char.get("court_data", {})
    employer_id = cd.get("employer") if isinstance(cd, dict) else None
    if employer_id is None:
        return "global"
    employer = gs.character(employer_id)
    if employer is None:
        return "global"
    return _char_region(gs, employer_id, employer, _depth + 1)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def find_candidates(
    gs: GameState,
    char_id: int,
    *,
    age_window: int = 6,
    min_age: int | None = None,
    max_age: int | None = None,
    faith_mode: str = "same_faith",   # "same_faith" | "same_religion" | "any"
    exclude_vices: bool = True,
    require_virtue: bool = False,
    track: str = "any",               # "any" | "noble" | "lowborn"
    max_zone: int | None = None,      # filter out candidates beyond this proximity zone
    exclude_house_ids: set | None = None,
    exclude_ids: set | None = None,
    limit: int = 25,
) -> MatchmakerReport:
    """
    Screen gs.living for spouse/betrothal candidates for *char_id*.

    Defaults mirror the manual Judita screen: opposite gender, same faith,
    age within +/-6 years, no vice personality traits, ranked by personality
    score then by geographic/political proximity to the subject.
    """
    gs.build_indices()
    subject = gs.character(char_id)
    if subject is None:
        raise ValueError(f"Character {char_id} not found")

    subject_gender = _gender(subject)
    target_gender = "male" if subject_gender == "female" else "female"

    birth = str(subject.get("birth", ""))
    subject_age = _compute_age(birth, gs.date) if birth else 0
    if min_age is None:
        min_age = max(0, subject_age - age_window)
    if max_age is None:
        max_age = subject_age + age_window

    subject_faith_tag, subject_religion_type = _faith_info(gs, subject)
    subject_region = _char_region(gs, char_id, subject)

    exclude_house_ids = set(exclude_house_ids or ())
    if subject.get("dynasty_house") is not None:
        exclude_house_ids.add(subject.get("dynasty_house"))
    exclude_ids = set(exclude_ids or ())
    exclude_ids.add(char_id)

    candidates: list[MatchCandidate] = []
    for cid_str, char in gs.living.items():
        if not isinstance(char, dict):
            continue
        cid = int(cid_str)
        if cid in exclude_ids:
            continue
        if _gender(char) != target_gender:
            continue
        if _is_unavailable(char):
            continue
        house_id = char.get("dynasty_house")
        if house_id is not None and house_id in exclude_house_ids:
            continue

        birth = str(char.get("birth", ""))
        if not birth:
            continue
        age = _compute_age(birth, gs.date)
        if age < min_age or age > max_age:
            continue

        faith_tag, religion_type = _faith_info(gs, char)
        if faith_mode == "same_faith" and faith_tag != subject_faith_tag:
            continue
        if faith_mode == "same_religion" and religion_type != subject_religion_type:
            continue

        traits, virtues, vices = _classify_traits(gs, char)
        if exclude_vices and vices:
            continue
        if require_virtue and not virtues:
            continue

        is_noble = house_id is not None
        cand_track = "noble" if is_noble else "lowborn"
        if track != "any" and track != cand_track:
            continue

        region = _char_region(gs, cid, char)
        proximity_zone = None if region == "global" and subject_region == "global" else zone_between(subject_region, region)
        if max_zone is not None and proximity_zone is not None and proximity_zone > max_zone:
            continue

        cd = char.get("court_data", {})
        employer_id = cd.get("employer") if isinstance(cd, dict) else None
        employer_name = None
        if employer_id is not None:
            employer = gs.character(employer_id)
            if employer:
                employer_name = decode_name(employer.get("first_name", ""))

        candidates.append(MatchCandidate(
            char_id=cid,
            name=decode_name(char.get("first_name", "")),
            age=age,
            gender=target_gender,
            faith_tag=faith_tag,
            religion_type=religion_type,
            culture_name=_culture_name(gs, char),
            traits=traits,
            virtues=virtues,
            vices=vices,
            is_noble=is_noble,
            house_name=_house_name(gs, house_id),
            track=cand_track,
            employer_id=employer_id,
            employer_name=employer_name,
            region=region,
            proximity_zone=proximity_zone,
        ))

    candidates.sort(key=lambda c: (
        -c.score,
        c.proximity_zone if c.proximity_zone is not None else 99,
        abs(c.age - subject_age),
    ))

    return MatchmakerReport(
        subject_id=char_id,
        subject_name=decode_name(subject.get("first_name", "")),
        subject_age=subject_age,
        subject_gender=subject_gender,
        subject_region=subject_region,
        candidates=candidates[:limit],
    )
