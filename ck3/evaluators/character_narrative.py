"""
ck3.evaluators.character_narrative
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Personal-scale narrative evaluator: walks a character's entries in
character_memory_manager and renders them as a chronological life story —
births, deaths, marriages, rivalries, imprisonments, battles — rather than
the fact-table shape the other evaluators use.

This is the "Personal" (and, by necessity, some "Family") rung of a wider
narrative ladder the project is building toward — Personal, Family, Court,
Holdings, Domain, Local, Continental, Global — not "narrative" in general.
Other rungs (court intrigue, domain-level events, realm/continental history)
are future evaluators in their own right; see ideas/ideas.txt.

Built because a strategic report has no reason to mention that a child
died of consumption while fostered abroad, but that's exactly the kind of
beat worth surfacing on its own.

Caveat (load-bearing, not cosmetic): CK3 memories carry an end_date and
appear to decay — most we've observed expire ~130 years after creation.
Fine for a living character's own lifetime, but this is NOT a permanent
archive; very old memories on long-dead ancestors may already be gone from
the save. See ideas/ideas.txt for the follow-up on working around this.

Usage::
    from ck3.evaluators.character_narrative import life_story
    story = life_story(gs, char_id=37766)
    print(story.summary())
"""

from __future__ import annotations
from dataclasses import dataclass, field

from ck3.gamestate import GameState
from ck3.names import decode_name
from ck3.evaluators.character import _parse_date, _compute_age  # noqa: F401  (shared date math)


# --------------------------------------------------------------------------- #
# Event classification
# --------------------------------------------------------------------------- #
# "major" events are the emotionally/strategically significant beats worth
# surfacing by default; "minor" events are flavor/background color, shown
# only when explicitly requested. Both lists are hand-curated against the
# 61 memory types observed in CK3 saves as of the All Under Heaven era —
# new types will fall back to a generic rendering rather than being dropped.

_MAJOR_TYPES = frozenset({
    "child_born", "child_premature", "child_stillborn", "twins_born", "first_born",
    "married", "spouse_died", "relative_died", "friend_died", "best_friend_died",
    "lover_died", "rival_died", "became_rivals", "became_nemesis", "broke_up_lovers",
    "imprisoned", "imprisoned_other", "tortured_memory", "torturer_memory",
    "ascended_throne_memory", "war_won", "war_lost", "knight_sacrificed_memory",
    "lost_title_memory", "accolade_created", "became_acclaimed",
    "completed_rites_of_passage", "saved_from_assault_memory", "ignored_assault_memory",
    "ce1_contracted_epidemic", "witnessed_death_battle_good_killer",
    "became_incapable_due_to_battle_concussion",
})

_MINOR_TYPES = frozenset({
    "became_friends", "became_lovers", "became_soulmates", "became_grudge",
    "developed_crush", "had_sex", "had_a_threesome_memory", "seduced_family",
    "childhood_education_guardian", "childhood_education_no_guardian",
    "ward_education_completed", "passed_child_exam_memory", "failed_child_exam_memory",
    "passed_provincial_exam_memory", "failed_provincial_exam_memory",
    "battle_won_memory", "battle_lost_memory", "defensive_war", "offensive_war",
    "joined_allys_war", "good_tour", "memory_big_city_visited", "favourite_toy_marbles",
    "establish_house_fief_memory", "picked_creation_aspect_memory",
    "picked_destruction_aspect_memory", "picked_serenity_aspect_memory",
    "released_from_prison_memory", "witnessed_a_coronation_memory",
})

# Per-type participant-role template. {name} placeholders are filled from
# the memory's resolved participants (role key -> decoded character name);
# missing roles render as "someone" rather than raising.
_TEMPLATES: dict[str, str] = {
    "child_born":               "{child} was born",
    "child_premature":          "{child} was born prematurely",
    "child_stillborn":          "lost a child to stillbirth",
    "twins_born":               "twins were born",
    "first_born":               "{child}, first-born, arrived",
    "married":                  "married {spouse}",
    "spouse_died":              "{spouse} (spouse) died",
    "relative_died":            "{dead_relation} (relative) died",
    "friend_died":              "{friend} (friend) died",
    "best_friend_died":         "{best_friend} (best friend) died",
    "lover_died":               "{lover} (lover) died",
    "rival_died":               "{rival} (rival) died",
    "became_rivals":            "became rivals with {rival}",
    "became_nemesis":           "became nemesis with {nemesis}",
    "became_friends":           "became friends with {new_relation}",
    "became_lovers":            "became lovers with {new_relation}",
    "became_soulmates":         "became soulmates with {new_relation}",
    "became_grudge":            "developed a grudge against {new_relation}",
    "broke_up_lovers":          "broke up with {lover}",
    "developed_crush":          "developed a crush on {crush}",
    "imprisoned":               "was imprisoned by {imprisoner}",
    "imprisoned_other":         "imprisoned {prisoner}",
    "released_from_prison_memory": "was released from prison",
    "tortured_memory":          "was tortured by {torturer}",
    "torturer_memory":          "tortured {victim}",
    "ascended_throne_memory":   "ascended to the throne",
    "war_won":                  "won a war",
    "war_lost":                 "lost a war",
    "defensive_war":            "fought a defensive war against {other_party}",
    "offensive_war":            "fought an offensive war against {other_party}",
    "joined_allys_war":         "joined an ally's war",
    "witnessed_a_coronation_memory": "witnessed {host}'s coronation",
    "battle_won_memory":        "won a battle",
    "battle_lost_memory":       "lost a battle",
    "knight_sacrificed_memory": "a knight was sacrificed in their service",
    "lost_title_memory":        "lost a title to {new_holder}",
    "accolade_created":         "created an accolade",
    "became_acclaimed":         "became acclaimed",
    "completed_rites_of_passage": "completed their rites of passage",
    "saved_from_assault_memory": "was saved from an assault",
    "ignored_assault_memory":   "ignored an assault",
    "ce1_contracted_epidemic":  "contracted an epidemic disease",
    "witnessed_death_battle_good_killer": "witnessed a notable death in battle",
    "became_incapable_due_to_battle_concussion": "was incapacitated by a battle concussion",
    "seduced_family":           "seduced a member of {family_member}'s family",
    "childhood_education_guardian": "was raised under a guardian's care",
    "childhood_education_no_guardian": "grew up without a guardian",
    "ward_education_completed": "{ward} completed their education as a ward",
    "passed_child_exam_memory": "passed a childhood exam",
    "failed_child_exam_memory": "failed a childhood exam",
    "passed_provincial_exam_memory": "passed a provincial exam",
    "failed_provincial_exam_memory": "failed a provincial exam",
    "good_tour":                "enjoyed a good tour",
    "memory_big_city_visited":  "visited a great city",
    "favourite_toy_marbles":    "had a favourite toy: marbles",
    "establish_house_fief_memory": "established a house fief",
    "picked_creation_aspect_memory": "embraced the aspect of Creation",
    "picked_destruction_aspect_memory": "embraced the aspect of Destruction",
    "picked_serenity_aspect_memory": "embraced the aspect of Serenity",
    "had_sex":                  "had a romantic encounter",
    "had_a_threesome_memory":   "had a romantic encounter",
}


@dataclass
class NarrativeEvent:
    date: str
    event_type: str
    description: str
    is_major: bool
    age_at_event: int | None
    participants: dict[str, str]   # role -> decoded name

    def line(self) -> str:
        age = f"(age {self.age_at_event}) " if self.age_at_event is not None else ""
        return f"  {self.date}  {age}{self.description}"


@dataclass
class NarrativeReport:
    char_id: int
    name: str
    birth_date: str
    events: list[NarrativeEvent] = field(default_factory=list)

    def major_events(self) -> list[NarrativeEvent]:
        return [e for e in self.events if e.is_major]

    def summary(self, include_minor: bool = False) -> str:
        events = self.events if include_minor else self.major_events()
        lines = [
            f"Life Story — {self.name} (id {self.char_id}), born {self.birth_date}",
            "=" * 60,
        ]
        if not events:
            lines.append("  (no recorded memories)")
        else:
            lines.extend(e.line() for e in sorted(events, key=lambda e: _parse_date(e.date)))
        return "\n".join(lines)


def _humanize_fallback(event_type: str) -> str:
    return event_type.removesuffix("_memory").replace("_", " ")


def _resolve_char_name(gs: GameState, char_id: int) -> str:
    pchar = gs.character(char_id) or gs.dead.get(str(char_id))
    return decode_name(pchar.get("first_name", "")) if pchar else f"id {char_id}"


def _resolve_participants(gs: GameState, mem: dict) -> dict[str, str]:
    participants: dict[str, str] = {}
    raw_participants = mem.get("participants", {})
    if isinstance(raw_participants, dict):
        for role, pid in raw_participants.items():
            if isinstance(pid, int):
                participants[role] = _resolve_char_name(gs, pid)
    return participants


def _render(event_type: str, participants: dict[str, str]) -> str:
    template = _TEMPLATES.get(event_type)
    if template:
        try:
            # Fill known roles; any role used by the template but absent
            # in participants falls back to "someone" rather than raising.
            return template.format(**{**{k: "someone" for k in _template_keys(template)}, **participants})
        except (KeyError, IndexError):
            pass
    desc = _humanize_fallback(event_type)
    if participants:
        desc += " (" + ", ".join(participants.values()) + ")"
    return desc


def _build_memory_owner_index(gs: GameState) -> dict[str, int]:
    """mid -> owning char_id, built from every living character's alive_data.memories list."""
    owner: dict[str, int] = {}
    for cid_str, char in gs.living.items():
        if not isinstance(char, dict):
            continue
        ad = char.get("alive_data", {})
        if not isinstance(ad, dict):
            continue
        mem_ids = ad.get("memories", [])
        if not isinstance(mem_ids, list):
            mem_ids = [mem_ids] if mem_ids else []
        for mid in mem_ids:
            owner[str(mid)] = int(cid_str)
    return owner


def life_story(gs: GameState, char_id: int) -> NarrativeReport:
    """
    Reconstruct a character's life events from character_memory_manager.

    Dead characters lose their alive_data.memories pointer entirely once
    moved to dead_unprunable — there's no "memories" field left on the dead
    record. As a fallback, we scan every *other* living character's memory
    list for entries that name this character as a participant (e.g. a
    parent's 'relative_died' memory naming their dead child) and surface
    those, tagged with whose memory it was. This is how a dead character's
    own death shows up in their own story at all — they can't remember it,
    but the people who survived them can.
    """
    char = gs.character(char_id)
    is_dead = char is None
    if is_dead:
        char = gs.dead.get(str(char_id))
    if char is None:
        raise ValueError(f"Character {char_id} not found")

    name = decode_name(char.get("first_name", ""))
    birth_date = str(char.get("birth", ""))

    ad = char.get("alive_data", {})
    mem_ids = ad.get("memories", []) if isinstance(ad, dict) else []
    if not isinstance(mem_ids, list):
        mem_ids = [mem_ids] if mem_ids else []

    cmm = gs.memories
    events: list[NarrativeEvent] = []

    for mid in mem_ids:
        mem = cmm.get(str(mid)) or cmm.get(mid)
        if not isinstance(mem, dict):
            continue
        event_type = mem.get("type", "")
        date = mem.get("creation_date", "")
        participants = _resolve_participants(gs, mem)
        age = _compute_age(birth_date, date) if birth_date and date else None
        events.append(NarrativeEvent(
            date=date,
            event_type=event_type,
            description=_render(event_type, participants),
            is_major=event_type in _MAJOR_TYPES,
            age_at_event=age,
            participants=participants,
        ))

    if not mem_ids:
        # Dead (or otherwise memory-less) character: fall back to scanning
        # other characters' memories for ones that mention this person.
        owner_index = _build_memory_owner_index(gs)
        for mid, mem in cmm.items():
            if not isinstance(mem, dict):
                continue
            raw_participants = mem.get("participants", {})
            if not isinstance(raw_participants, dict):
                continue
            if char_id not in raw_participants.values():
                continue
            owner_id = owner_index.get(str(mid))
            owner_name = None
            if owner_id is not None:
                owner_char = gs.character(owner_id)
                if owner_char:
                    owner_name = decode_name(owner_char.get("first_name", ""))
            event_type = mem.get("type", "")
            date = mem.get("creation_date", "")
            participants = _resolve_participants(gs, mem)
            desc = _render(event_type, participants)
            if owner_name:
                desc = f"(per {owner_name}'s memory) {desc}"
            age = _compute_age(birth_date, date) if birth_date and date else None
            events.append(NarrativeEvent(
                date=date,
                event_type=event_type,
                description=desc,
                is_major=event_type in _MAJOR_TYPES,
                age_at_event=age,
                participants=participants,
            ))

    return NarrativeReport(char_id=char_id, name=name, birth_date=birth_date, events=events)


def _template_keys(template: str) -> list[str]:
    import string
    return [name for _, name, _, _ in string.Formatter().parse(template) if name]
