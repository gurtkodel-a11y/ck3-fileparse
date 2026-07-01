"""
ck3.evaluators.character
~~~~~~~~~~~~~~~~~~~~~~~~~
Character profile — intrinsic attributes plus extrinsic situational data.

Works for any character ID (not just the played character).  Suitable as a
standalone snapshot or as a building block for the narrative tooling layer.

Usage::
    from ck3.evaluators.character import character_profile
    profile = character_profile(gs, char_id=37766)
    print(profile.summary())
"""

from __future__ import annotations
from dataclasses import dataclass, field

from ck3.gamestate import GameState
from ck3.names import decode_name
from ck3.trait_data import trait_category, trait_skill_bonus
from ck3.evaluators.base import title_full_label, title_place


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SKILL_KEYS = ("dip", "mar", "stew", "int", "lea", "prow")

SKILL_LABELS = {
    "dip":  "Dipl",
    "mar":  "Mart",
    "stew": "Stew",
    "int":  "Intr",
    "lea":  "Lear",
    "prow": "Prow",
}

_LIFESTYLE_STEMS = (
    "diplomacy", "martial", "stewardship", "intrigue", "learning", "wanderer",
)

# Council task type → human-readable role label
_COUNCIL_TASK_LABELS: dict[str, str] = {
    "task_foreign_affairs":          "Chancellor",
    "task_collect_taxes":            "Steward",
    "task_organize_levies":          "Marshal",
    "task_disrupt_schemes":          "Spymaster",
    "task_religious_relations":      "Court Chaplain",
    "task_spouse_default":           "Consort (Council)",
    "task_chancellor_default":       "Chancellor",
    "task_marshal_default":          "Marshal",
    "task_steward_default":          "Steward",
    "task_spymaster_default":        "Spymaster",
    "task_court_chaplain_default":   "Court Chaplain",
}

# Fallback: match by prefix of the task type key
_COUNCIL_TASK_PREFIXES: list[tuple[str, str]] = [
    ("task_foreign",    "Chancellor"),
    ("task_collect",    "Steward"),
    ("task_realm",      "Steward"),
    ("task_steward",    "Steward"),
    ("task_organize",   "Marshal"),
    ("task_train",      "Marshal"),
    ("task_marshal",    "Marshal"),
    ("task_disrupt",    "Spymaster"),
    ("task_hostile",    "Spymaster"),
    ("task_counter",    "Spymaster"),
    ("task_spymaster",  "Spymaster"),
    ("task_religious",  "Court Chaplain"),
    ("task_convert",    "Court Chaplain"),
    ("task_promote",    "Court Chaplain"),
    ("task_chaplain",   "Court Chaplain"),
    ("task_court_chap", "Court Chaplain"),
    ("task_spouse",     "Consort (Council)"),
]

_PERSONAL_RELATION_TYPES = frozenset({
    "friend", "best_friend", "rival", "nemesis", "lover", "soulmate",
    "crush", "old_flame", "mentor", "student", "intrigue_mentor",
    "intrigue_student", "guardian", "ward", "soldier_friend",
    "oaf", "bully", "grudge", "victim",
})


# --------------------------------------------------------------------------- #
# Label helpers
# --------------------------------------------------------------------------- #

def _health_label(h: float) -> str:
    if h < 1.0:  return "dying"
    if h < 2.0:  return "very poor"
    if h < 3.0:  return "poor"
    if h < 4.0:  return "below average"
    if h < 5.0:  return "normal"
    if h < 6.5:  return "good"
    return "robust"


def _focus_label(focus_type: str | None) -> str:
    if not focus_type:
        return ""
    if focus_type.startswith("education_"):
        skill = focus_type[len("education_"):]
        return f"{skill.replace('_', ' ').title()} (education)"
    if focus_type.endswith("_focus"):
        inner = focus_type[: -len("_focus")]
        for stem in _LIFESTYLE_STEMS:
            if inner.startswith(stem + "_"):
                sub = inner[len(stem) + 1:].replace("_", " ").title()
                return f"{stem.title()} — {sub}"
            if inner == stem:
                return stem.title()
        return inner.replace("_", " ").title()
    return focus_type.replace("_", " ").title()


def _edu_label(trait_name: str) -> str:
    rest = trait_name[len("education_"):] if trait_name.startswith("education_") else trait_name
    parts = rest.rsplit("_", 1)
    skill = parts[0].replace("_", " ").title()
    if len(parts) == 2 and parts[1].isdigit():
        return f"{skill}, tier {parts[1]}"
    return skill


def _perk_label(perk_key: str) -> str:
    return perk_key.removesuffix("_perk").replace("_", " ").title()


def _lang_label(lang_key: str) -> str:
    return lang_key.removeprefix("language_").replace("_", " ").title()


def _parse_date(date_str: str) -> tuple[int, int, int]:
    try:
        parts = str(date_str).split(".")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 1, int(parts[2]) if len(parts) > 2 else 1
    except (ValueError, IndexError):
        return 0, 1, 1


def _compute_age(birth: str, current: str) -> int:
    by, bm, bd = _parse_date(birth)
    cy, cm, cd = _parse_date(current)
    age = cy - by
    if (cm, cd) < (bm, bd):
        age -= 1
    return max(age, 0)


def _council_role_label(task_type: str) -> str:
    label = _COUNCIL_TASK_LABELS.get(task_type)
    if label:
        return label
    for prefix, role in _COUNCIL_TASK_PREFIXES:
        if task_type.startswith(prefix):
            return role
    return task_type.replace("_", " ").title()


def _court_position_label(pos_key: str) -> str:
    return (pos_key
            .removesuffix("_court_position")
            .replace("_", " ")
            .title())


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #

@dataclass
class PersonalRelation:
    """A scripted personal bond involving this character."""
    other_id: int
    other_name: str
    relation_type: str       # "friend" | "rival" | "lover" | "nemesis" | …
    direction: str           # "char_to_other" | "other_to_char"


@dataclass
class FamilyRef:
    """Minimal reference to a family member."""
    char_id: int
    name: str


@dataclass
class CharacterProfile:
    """
    Intrinsic + extrinsic snapshot for one character.

    Intrinsic fields (age, health, skills, traits, focus, perks, languages)
    are always present.  Extrinsic fields are populated for living characters;
    dead characters get zero/empty/None values.
    """

    # --- Identity ---
    char_id: int
    name: str
    birth_date: str
    age: int
    gender: str                      # "male" | "female"
    is_alive: bool
    death_date: str                  # empty if alive

    # --- Vitals ---
    health: float
    fertility: float

    # --- Faith & culture ---
    faith: str
    culture: str

    # --- Skills ---
    skills: dict[str, int]           # base values
    effective_skills: dict[str, int] # base + education + trait bonuses

    # --- Traits ---
    education_trait: str | None
    personality_traits: list[str]
    lifestyle_traits: list[str]
    commander_traits: list[str]
    physical_traits: list[str]
    other_traits: list[str]

    # --- Lifestyle ---
    focus: str | None
    perks: list[str]
    languages: list[str]

    # --- Physical situation ---
    location_province_id: int | None  # map-province ID from alive_data.location
    location_name: str                # decoded county/barony display name
    is_imprisoned: bool
    prison_type: str | None           # "house_arrest" | "dungeon" | …
    imprisoner_id: int | None
    at_activity: bool                 # currently at an event/activity

    # --- Resources ---
    gold: float
    prestige_currency: float          # spendable prestige
    prestige_accumulated: float       # lifetime accumulated
    piety_currency: float
    piety_accumulated: float
    dread: float                      # rulers only (landed_data.dread)
    legitimacy: float                 # newer DLC; 0.0 if absent

    # --- Domain ---
    domain_title_keys: list[str]      # title keys of directly held titles
    domain_title_labels: list[str]    # display labels, e.g. "Count of Korehari" or
                                       # "the Kiyohara Family" — resolved from
                                       # title_name_data.name where the save provides
                                       # one (procedurally-named/landless titles don't
                                       # follow the "Tier of Key" pattern at all)
    realm_capital_key: str | None
    realm_capital_label: str | None   # resolved display name (see domain_title_labels)

    # --- Positions held ---
    council_role: str | None          # "Chancellor" | "Marshal" | … | None
    council_employer_id: int | None   # who they serve as council member
    court_position_types: list[str]   # court position keys held

    # --- Succession ---
    heir_id: int | None               # primary heir char_id

    # --- Key family ---
    primary_spouse: FamilyRef | None
    children: list[FamilyRef]
    father: FamilyRef | None
    mother: FamilyRef | None

    # --- Liege ---
    liege_id: int | None
    liege_name: str
    liege_title_key: str | None

    # --- Scripted personal relations ---
    personal_relations: list[PersonalRelation]

    # --- Community leaders ---
    dynasty_head_id: int | None
    faith_head_id: int | None         # char who holds the faith head title
    faith_head_title_key: str | None
    culture_head_id: int | None

    # ------------------------------------------------------------------ #
    # Derived display properties
    # ------------------------------------------------------------------ #

    @property
    def health_label(self) -> str:
        return _health_label(self.health)

    @property
    def focus_label(self) -> str:
        return _focus_label(self.focus)

    @property
    def education_label(self) -> str:
        return _edu_label(self.education_trait) if self.education_trait else ""

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #

    def summary(self) -> str:
        lines = []

        header = f"{self.name}  (id {self.char_id})"
        lines.append(header)
        lines.append("-" * len(header))

        # Vitals
        gender_str = "F" if self.gender == "female" else "M"
        vitals = f"Age {self.age}  {gender_str}  Born {self.birth_date}"
        if not self.is_alive:
            vitals += f"  |  Died {self.death_date}" if self.death_date else "  |  Deceased"
        else:
            vitals += f"  |  Health {self.health:.1f} ({self.health_label})"
            vitals += f"  |  Fertility {self.fertility:.2f}"
        lines.append(vitals)

        lines.append(f"Faith: {self.faith or '—'}  |  Culture: {self.culture or '—'}")

        # Skills
        def _skill_row(d: dict[str, int]) -> str:
            return "  ".join(f"{SKILL_LABELS[s]} {d.get(s, 0):>2}" for s in SKILL_KEYS)

        lines.append(f"Base skills: {_skill_row(self.skills)}")
        lines.append(f"Eff. skills: {_skill_row(self.effective_skills)}  (excl. perks/artifacts)")

        if self.education_label:
            lines.append(f"Education:   {self.education_label}")
        if self.focus:
            lines.append(f"Focus:       {self.focus_label}")
        if self.personality_traits:
            lines.append(f"Personality: {', '.join(self.personality_traits)}")
        if self.lifestyle_traits:
            lines.append(f"Lifestyle:   {', '.join(self.lifestyle_traits)}")
        if self.commander_traits:
            lines.append(f"Commander:   {', '.join(self.commander_traits)}")
        if self.physical_traits:
            lines.append(f"Physical:    {', '.join(self.physical_traits)}")
        if self.other_traits:
            lines.append(f"Other:       {', '.join(self.other_traits)}")
        if self.perks:
            perk_strs = [_perk_label(p) for p in self.perks]
            header_str = f"Perks ({len(perk_strs)}):"
            perk_text = ", ".join(perk_strs)
            indent = " " * (len(header_str) + 1)
            wrapped = _wrap_text(perk_text, 72 - len(header_str) - 1, indent)
            lines.append(f"{header_str} {wrapped}")
        if self.languages:
            lines.append(f"Languages: {', '.join(_lang_label(l) for l in self.languages)}")

        if not self.is_alive:
            return "\n".join(lines)

        # ── Situation ────────────────────────────────────────────────────── #
        lines.append("")
        lines.append("--- Situation ---")

        loc_str = self.location_name or (f"province {self.location_province_id}" if self.location_province_id else "unknown")
        status_parts = [f"Location: {loc_str}"]
        if self.is_imprisoned:
            prison_str = self.prison_type.replace("_", " ").title() if self.prison_type else "Imprisoned"
            status_parts.append(f"STATUS: {prison_str}")
        if self.at_activity:
            status_parts.append("At event/activity")
        lines.append("  " + "  |  ".join(status_parts))

        # ── Resources ────────────────────────────────────────────────────── #
        lines.append("")
        lines.append("--- Resources ---")
        res_parts = [f"Gold {self.gold:.0f}"]
        res_parts.append(f"Prestige {self.prestige_currency:.0f} ({self.prestige_accumulated:.0f} acc.)")
        res_parts.append(f"Piety {self.piety_currency:.0f} ({self.piety_accumulated:.0f} acc.)")
        if self.dread:
            res_parts.append(f"Dread {self.dread:.1f}")
        if self.legitimacy:
            res_parts.append(f"Legitimacy {self.legitimacy:.1f}")
        lines.append("  " + "  |  ".join(res_parts))

        # ── Domain ───────────────────────────────────────────────────────── #
        if self.domain_title_keys:
            lines.append("")
            lines.append(f"--- Domain ({len(self.domain_title_keys)} titles) ---")
            if self.realm_capital_label:
                lines.append(f"  Capital: {self.realm_capital_label}")
            # Show top 8 titles
            for label in self.domain_title_labels[:8]:
                lines.append(f"  {label}")
            if len(self.domain_title_keys) > 8:
                lines.append(f"  … and {len(self.domain_title_keys) - 8} more")

        # ── Positions ────────────────────────────────────────────────────── #
        positions: list[str] = []
        if self.council_role:
            employer_note = f" (for {self.council_employer_id})" if self.council_employer_id else ""
            positions.append(f"{self.council_role}{employer_note}")
        for pos in self.court_position_types:
            positions.append(_court_position_label(pos))
        if positions:
            lines.append("")
            lines.append("--- Positions ---")
            for pos in positions:
                lines.append(f"  {pos}")

        # ── Succession ───────────────────────────────────────────────────── #
        if self.heir_id is not None:
            lines.append("")
            lines.append(f"--- Heir ---")
            lines.append(f"  id {self.heir_id}")

        # ── Liege ────────────────────────────────────────────────────────── #
        lines.append("")
        lines.append("--- Hierarchy ---")
        if self.liege_id:
            liege_title = self.liege_title_key[2:].replace("_", " ").title() if self.liege_title_key and len(self.liege_title_key) > 2 else self.liege_title_key or "?"
            lines.append(f"  Liege: {self.liege_name}  ({liege_title})  id {self.liege_id}")
        else:
            lines.append("  Independent ruler")

        # ── Family ───────────────────────────────────────────────────────── #
        lines.append("")
        lines.append("--- Family ---")
        if self.primary_spouse:
            lines.append(f"  Spouse:   {self.primary_spouse.name}  (id {self.primary_spouse.char_id})")
        if self.father:
            lines.append(f"  Father:   {self.father.name}  (id {self.father.char_id})")
        if self.mother:
            lines.append(f"  Mother:   {self.mother.name}  (id {self.mother.char_id})")
        if self.children:
            child_str = ", ".join(f"{c.name} ({c.char_id})" for c in self.children[:6])
            if len(self.children) > 6:
                child_str += f" … +{len(self.children) - 6} more"
            lines.append(f"  Children: {child_str}")

        # ── Personal relations ───────────────────────────────────────────── #
        if self.personal_relations:
            lines.append("")
            lines.append("--- Personal Relations ---")
            by_type: dict[str, list[PersonalRelation]] = {}
            for pr in self.personal_relations:
                by_type.setdefault(pr.relation_type, []).append(pr)
            for rtype in sorted(by_type.keys()):
                names = ", ".join(
                    f"{pr.other_name} ({pr.other_id})"
                    for pr in by_type[rtype]
                )
                lines.append(f"  {rtype.replace('_', ' ').title():<20} {names}")

        # ── Community leaders ────────────────────────────────────────────── #
        lines.append("")
        lines.append("--- Community Leaders ---")
        if self.dynasty_head_id is not None:
            you = "  (you)" if self.dynasty_head_id == self.char_id else ""
            lines.append(f"  Dynasty head:  id {self.dynasty_head_id}{you}")
        if self.faith_head_id is not None:
            title_note = ""
            if self.faith_head_title_key:
                title_note = f"  [{self.faith_head_title_key[2:].replace('_', ' ').title() if len(self.faith_head_title_key) > 2 else self.faith_head_title_key}]"
            lines.append(f"  Faith head:    id {self.faith_head_id}{title_note}")
        elif self.faith_head_title_key:
            lines.append(f"  Faith head:    {self.faith_head_title_key}  (holder unknown)")
        if self.culture_head_id is not None:
            you = "  (you)" if self.culture_head_id == self.char_id else ""
            lines.append(f"  Culture head:  id {self.culture_head_id}{you}")

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Location resolution
# --------------------------------------------------------------------------- #

def _resolve_location(province_id: int, gs: GameState) -> str:
    """
    Convert a map-province ID from alive_data.location.location to a
    human-readable county (or barony) display name.

    Strategy:
    1. Reverse-map province_id → barony_key via province_data.
    2. Find the title record for the barony in the save → get its county parent.
    3. Fall back to showing the barony name if no county parent is found.
    """
    try:
        from ck3.province_data import load_barony_provinces, load_county_capitals
        barony_provinces = load_barony_provinces()
        prov_to_barony = {v: k for k, v in barony_provinces.items()}
        barony_key = prov_to_barony.get(province_id)
        if not barony_key:
            return f"province {province_id}"

        # Try to find the county this barony belongs to via county_capitals reverse map
        county_caps = load_county_capitals()           # county_key → capital_barony_key
        barony_to_county = {v: k for k, v in county_caps.items()}
        county_key = barony_to_county.get(barony_key)

        if county_key:
            # Prefer county name
            t = gs.title_by_key(county_key)
            if t and isinstance(t.get("title_name_data"), dict):
                raw_name = t["title_name_data"].get("name", "")
                if raw_name:
                    return decode_name(str(raw_name))
            return county_key[2:].replace("_", " ").title() if len(county_key) > 2 else county_key

        # Fall back to barony name
        t = gs.title_by_key(barony_key)
        if t and isinstance(t.get("title_name_data"), dict):
            raw_name = t["title_name_data"].get("name", "")
            if raw_name:
                return decode_name(str(raw_name))
        return barony_key[2:].replace("_", " ").title() if len(barony_key) > 2 else barony_key
    except Exception:
        return f"province {province_id}"


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #

def character_profile(gs: GameState, char_id: int) -> CharacterProfile:
    """
    Build a CharacterProfile for any character by ID.

    Checks living characters first, then dead_unprunable.  Returns a minimal
    profile (is_alive=False, resources/domain all zero/empty) for dead
    characters that are still in the save.  Raises ValueError if not found.
    """
    char = gs.character(char_id)
    is_alive = True
    death_date = ""

    if char is None:
        char = gs.dead.get(str(char_id))
        if char is None:
            raise ValueError(f"Character {char_id} not found in living or dead_unprunable")
        is_alive = False
        dd = char.get("dead_data", {})
        death_date = dd.get("date", "") if isinstance(dd, dict) else ""

    name = decode_name(char.get("first_name", str(char_id)))
    birth_date = str(char.get("birth", ""))
    age = _compute_age(birth_date, gs.date) if birth_date else 0
    gender = "female" if char.get("female") == "yes" else "male"

    # ── Skills ──────────────────────────────────────────────────────────── #
    raw_skills = char.get("skill", [])
    if isinstance(raw_skills, list):
        skills = {k: int(raw_skills[i]) if i < len(raw_skills) else 0
                  for i, k in enumerate(SKILL_KEYS)}
    else:
        skills = {k: 0 for k in SKILL_KEYS}

    # ── Faith & culture ──────────────────────────────────────────────────── #
    def _resolve_faith(c: dict) -> str:
        fid = c.get("faith", "")
        if not fid:
            return ""
        rec = gs.faith(str(fid)) or {}
        tag = rec.get("tag", fid)
        return str(tag).replace("_", " ").title()

    def _resolve_culture(c: dict) -> str:
        cid = c.get("culture", "")
        if not cid:
            return ""
        rec = gs.culture(str(cid)) or {}
        n = rec.get("name", rec.get("culture_template", cid))
        return str(n).replace("_", " ").title()

    faith   = _resolve_faith(char)
    culture = _resolve_culture(char)

    if not faith or not culture:
        house_id = char.get("dynasty_house")
        if house_id:
            house   = gs.dynasty_house(house_id) or {}
            head_id = house.get("head_of_house")
            if head_id:
                head = gs.character(head_id) or {}
                if not faith:
                    faith = _resolve_faith(head)
                if not culture:
                    culture = _resolve_culture(head)

    # ── Traits ──────────────────────────────────────────────────────────── #
    raw_trait_ids = char.get("traits", [])
    if not isinstance(raw_trait_ids, list):
        raw_trait_ids = [raw_trait_ids] if raw_trait_ids else []

    _PERSONALITY_CATS = {"personality", "childhood"}
    _LIFESTYLE_CATS   = {"lifestyle"}
    _COMMANDER_CATS   = {"commander", "winter_commander"}

    education_trait: str | None   = None
    personality_traits: list[str] = []
    lifestyle_traits: list[str]   = []
    commander_traits: list[str]   = []
    physical_traits: list[str]    = []
    other_traits: list[str]       = []

    for tid in raw_trait_ids:
        name_str = gs.trait_name(int(tid))
        if name_str.startswith("education_"):
            education_trait = name_str
        else:
            cat = trait_category(name_str)
            if cat in _PERSONALITY_CATS:
                personality_traits.append(name_str)
            elif cat in _LIFESTYLE_CATS:
                lifestyle_traits.append(name_str)
            elif cat in _COMMANDER_CATS:
                commander_traits.append(name_str)
            elif cat == "physical":
                physical_traits.append(name_str)
            else:
                other_traits.append(name_str)

    # Effective skills: base + education + all trait bonuses
    effective_skills = dict(skills)
    traits_to_sum = (
        ([education_trait] if education_trait else [])
        + personality_traits + lifestyle_traits
        + commander_traits + physical_traits + other_traits
    )
    for tname in traits_to_sum:
        for skill_key, bonus in trait_skill_bonus(tname).items():
            short = {"diplomacy": "dip", "martial": "mar", "stewardship": "stew",
                     "intrigue": "int", "learning": "lea", "prowess": "prow"}.get(skill_key)
            if short and short in effective_skills:
                effective_skills[short] += bonus

    # ── alive_data fields ────────────────────────────────────────────────── #
    ad = char.get("alive_data") if is_alive else None
    if not isinstance(ad, dict):
        ad = {}

    health    = float(ad.get("health",    0.0) or 0.0)
    fertility = float(ad.get("fertility", 0.0) or 0.0)

    raw_focus = ad.get("focus")
    focus: str | None = None
    if isinstance(raw_focus, dict):
        focus = raw_focus.get("type")

    perks = ad.get("perk", [])
    if not isinstance(perks, list):
        perks = [perks] if perks else []

    languages = ad.get("languages", [])
    if not isinstance(languages, list):
        languages = [languages] if languages else []

    # ── Location ─────────────────────────────────────────────────────────── #
    location_province_id: int | None = None
    location_name = ""
    if is_alive:
        raw_loc = ad.get("location")
        if isinstance(raw_loc, dict):
            location_province_id = raw_loc.get("location")
        elif isinstance(raw_loc, int):
            location_province_id = raw_loc
        if location_province_id is not None:
            location_name = _resolve_location(location_province_id, gs)

    # ── Imprisonment ─────────────────────────────────────────────────────── #
    is_imprisoned = False
    prison_type: str | None = None
    imprisoner_id: int | None = None
    if is_alive:
        pd = ad.get("prison_data")
        if isinstance(pd, dict):
            is_imprisoned = True
            prison_type   = pd.get("type")
            imprisoner_id = pd.get("imprisoner")

    # ── Activity ─────────────────────────────────────────────────────────── #
    at_activity = False
    if is_alive:
        act_data = ad.get("activity_data")
        at_activity = bool(act_data) and act_data != []

    # ── Resources ────────────────────────────────────────────────────────── #
    gold = 0.0
    prestige_currency = 0.0
    prestige_accumulated = 0.0
    piety_currency = 0.0
    piety_accumulated = 0.0
    dread = 0.0
    legitimacy = 0.0

    if is_alive:
        raw_gold = ad.get("gold", {})
        if isinstance(raw_gold, dict):
            gold = float(raw_gold.get("value", 0) or 0)
        elif isinstance(raw_gold, (int, float)):
            gold = float(raw_gold)

        raw_prestige = ad.get("prestige", {})
        if isinstance(raw_prestige, dict):
            prestige_currency    = float(raw_prestige.get("currency",    0) or 0)
            prestige_accumulated = float(raw_prestige.get("accumulated", 0) or 0)

        raw_piety = ad.get("piety", {})
        if isinstance(raw_piety, dict):
            piety_currency    = float(raw_piety.get("currency",    0) or 0)
            piety_accumulated = float(raw_piety.get("accumulated", 0) or 0)

        ld = char.get("landed_data", {}) if isinstance(char.get("landed_data"), dict) else {}
        dread      = float(ld.get("dread",      0) or 0)
        legitimacy = float(ld.get("legitimacy", 0) or 0)

    # ── Domain ───────────────────────────────────────────────────────────── #
    domain_title_keys: list[str] = []
    domain_title_labels: list[str] = []
    realm_capital_key: str | None = None
    realm_capital_label: str | None = None

    ld = char.get("landed_data", {}) if isinstance(char.get("landed_data"), dict) else {}
    if is_alive and ld:
        gs.build_indices()
        domain_ids = ld.get("domain", [])
        if not isinstance(domain_ids, list):
            domain_ids = [domain_ids] if domain_ids else []
        for did in domain_ids:
            t = gs.title(did)
            if t and isinstance(t, dict):
                key = t.get("key", "")
                if key:
                    domain_title_keys.append(key)
                    domain_title_labels.append(title_full_label(key, t))

        cap_id = ld.get("realm_capital")
        if cap_id:
            t = gs.title(cap_id)
            if t and isinstance(t, dict):
                realm_capital_key = t.get("key")
                realm_capital_label = title_place(realm_capital_key, t)

    # ── Council / court positions ────────────────────────────────────────── #
    council_role: str | None = None
    council_employer_id: int | None = None
    court_position_types: list[str] = []

    if is_alive:
        cd = char.get("court_data", {})
        if isinstance(cd, dict):
            task_rec = gs.council_task_for_char(char_id)
            if task_rec and isinstance(task_rec, dict):
                task_type = task_rec.get("type", "")
                council_role        = _council_role_label(task_type) if task_type else None
                council_employer_id = task_rec.get("court_owner")

        for pos_entry in gs.court_positions_for_char(char_id):
            pos_type = pos_entry.get("court_position", "")
            if pos_type:
                court_position_types.append(pos_type)

    # ── Succession ───────────────────────────────────────────────────────── #
    heir_id: int | None = None
    if is_alive and ld:
        succ = ld.get("succession", [])
        if isinstance(succ, list) and succ:
            heir_id = int(succ[0])
        elif isinstance(succ, int):
            heir_id = succ

    # ── Family ───────────────────────────────────────────────────────────── #
    def _ref(cid: int | str | None) -> FamilyRef | None:
        if cid is None:
            return None
        cid = int(cid)
        c = gs.character(cid) or gs.dead.get(str(cid)) or {}
        n = decode_name(c.get("first_name", str(cid)))
        return FamilyRef(char_id=cid, name=n)

    fd = char.get("family_data", {}) if isinstance(char.get("family_data"), dict) else {}
    primary_spouse = _ref(fd.get("primary_spouse"))
    father         = _ref(fd.get("father"))
    mother         = _ref(fd.get("mother"))
    child_ids_raw  = fd.get("child", [])
    if not isinstance(child_ids_raw, list):
        child_ids_raw = [child_ids_raw] if child_ids_raw else []
    children = [r for cid in child_ids_raw if (r := _ref(cid)) is not None]

    # ── Liege ────────────────────────────────────────────────────────────── #
    liege_id: int | None = None
    liege_name = ""
    liege_title_key: str | None = None

    if is_alive:
        gs.build_indices()
        contract = gs.contract_for_vassal(char_id)
        if contract and isinstance(contract, dict):
            liege_id = contract.get("liege")
            if liege_id:
                lc = gs.character(liege_id)
                if lc:
                    liege_name = decode_name(lc.get("first_name", str(liege_id)))
                    l_titles = gs.titles_held_by(liege_id)
                    best_order = 99
                    for t in l_titles:
                        if not isinstance(t, dict):
                            continue
                        k = t.get("key", "")
                        order = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}.get(k[0] if k else "b", 9)
                        if order < best_order:
                            best_order = order
                            liege_title_key = k

    # ── Personal relations ───────────────────────────────────────────────── #
    # Deduplicate by (other_id, relation_type) — the same bond appears in
    # both the owner-side and target-side opinion entries.
    personal_relations: list[PersonalRelation] = []
    _seen_relations: set[tuple[int, str]] = set()
    if is_alive:
        for entry in gs.opinions_list():
            if not isinstance(entry, dict):
                continue
            sr = entry.get("scripted_relations")
            if not sr or not isinstance(sr, dict):
                continue
            owner  = entry.get("owner")
            target = entry.get("target")
            if owner == char_id:
                direction = "char_to_other"
                other_id  = target
            elif target == char_id:
                direction = "other_to_char"
                other_id  = owner
            else:
                continue
            if other_id is None:
                continue
            other_id = int(other_id)
            other_c  = gs.character(other_id) or {}
            other_name = decode_name(other_c.get("first_name", str(other_id)))
            for rel_type in sr:
                if rel_type not in _PERSONAL_RELATION_TYPES:
                    continue
                key = (other_id, rel_type)
                if key in _seen_relations:
                    continue
                _seen_relations.add(key)
                personal_relations.append(PersonalRelation(
                    other_id=other_id,
                    other_name=other_name,
                    relation_type=rel_type,
                    direction=direction,
                ))

    # ── Community leaders ────────────────────────────────────────────────── #
    dynasty_head_id: int | None    = None
    faith_head_id: int | None      = None
    faith_head_title_key: str | None = None
    culture_head_id: int | None    = None

    house_id = char.get("dynasty_house")
    if house_id:
        dh = gs.dynasty_house(house_id)
        if dh:
            raw_head = dh.get("head_of_house")
            dynasty_head_id = int(raw_head) if raw_head is not None else None

    faith_id = char.get("faith")
    if not faith_id:
        # Unlanded characters often have no stored faith; fall back to house head
        hid = char.get("dynasty_house")
        if hid:
            _dh = gs.dynasty_house(hid) or {}
            _hhead = _dh.get("head_of_house")
            if _hhead:
                _hc = gs.character(_hhead) or {}
                faith_id = _hc.get("faith")
    if faith_id:
        frec = gs.faith(str(faith_id)) or {}
        head_title_id = frec.get("religious_head")
        if head_title_id is not None:
            ht = gs.title(head_title_id)
            if ht and isinstance(ht, dict):
                faith_head_title_key = ht.get("key")
                holder = ht.get("holder")
                if holder is not None:
                    faith_head_id = int(holder)

    culture_id = char.get("culture")
    if culture_id:
        crec = gs.culture(str(culture_id)) or {}
        raw_cult_head = crec.get("head")
        if raw_cult_head is not None:
            culture_head_id = int(raw_cult_head)

    return CharacterProfile(
        char_id=char_id,
        name=name,
        birth_date=birth_date,
        age=age,
        gender=gender,
        is_alive=is_alive,
        death_date=death_date,
        health=health,
        fertility=fertility,
        faith=faith,
        culture=culture,
        skills=skills,
        effective_skills=effective_skills,
        education_trait=education_trait,
        personality_traits=personality_traits,
        lifestyle_traits=lifestyle_traits,
        commander_traits=commander_traits,
        physical_traits=physical_traits,
        other_traits=other_traits,
        focus=focus,
        perks=perks,
        languages=languages,
        location_province_id=location_province_id,
        location_name=location_name,
        is_imprisoned=is_imprisoned,
        prison_type=prison_type,
        imprisoner_id=imprisoner_id,
        at_activity=at_activity,
        gold=gold,
        prestige_currency=prestige_currency,
        prestige_accumulated=prestige_accumulated,
        piety_currency=piety_currency,
        piety_accumulated=piety_accumulated,
        dread=dread,
        legitimacy=legitimacy,
        domain_title_keys=domain_title_keys,
        domain_title_labels=domain_title_labels,
        realm_capital_key=realm_capital_key,
        realm_capital_label=realm_capital_label,
        council_role=council_role,
        council_employer_id=council_employer_id,
        court_position_types=court_position_types,
        heir_id=heir_id,
        primary_spouse=primary_spouse,
        children=children,
        father=father,
        mother=mother,
        liege_id=liege_id,
        liege_name=liege_name,
        liege_title_key=liege_title_key,
        personal_relations=personal_relations,
        dynasty_head_id=dynasty_head_id,
        faith_head_id=faith_head_id,
        faith_head_title_key=faith_head_title_key,
        culture_head_id=culture_head_id,
    )


# --------------------------------------------------------------------------- #
# Utilities
# --------------------------------------------------------------------------- #

def _wrap_text(text: str, width: int, indent: str) -> str:
    """Wrap a comma-separated string to fit within width, indenting continuation lines."""
    if len(text) <= width:
        return text
    items = [s.strip() for s in text.split(",")]
    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for item in items:
        needed = len(item) + (2 if current else 0)
        if current and current_len + needed > width:
            lines.append(", ".join(current))
            current = [item]
            current_len = len(item)
        else:
            current.append(item)
            current_len += needed
    if current:
        lines.append(", ".join(current))
    return f"\n{indent}".join(lines)
