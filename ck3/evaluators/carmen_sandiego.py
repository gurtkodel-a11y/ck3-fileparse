"""
ck3.evaluators.carmen_sandiego
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"Where in the world is...?" — resolves where a character physically is right
now, whether they're traveling (and where to/why), and what activity (if
any) they're hosting or attending. Built because a realm-wide strategic
report has no reason to mention that the player is currently away at their
liege's coronation — but that's exactly the kind of thing worth a quick,
targeted lookup.

Data sources (none of this is in the per-character evaluators already):
  - alive_data.location.{location, travel_plan} — current map-province ID
    and (if traveling) a pointer into gs.travel_plans
  - alive_data.involved_activity_data — {activity, intent} if attending
  - gs.activities[activity_id] — type, host, attendee list, phase
  - gs.travel_plans[travel_plan_id] — departure/destination provinces +
    arrival dates

Usage::
    from ck3.evaluators.carmen_sandiego import locate
    loc = locate(gs, char_id=32778)
    print(loc.summary())
"""

from __future__ import annotations
from dataclasses import dataclass

from ck3.gamestate import GameState
from ck3.names import decode_name
from ck3.evaluators.character import _resolve_location

_ACTIVITY_LABELS: dict[str, str] = {
    "activity_coronation": "Coronation",
    "activity_tournament": "Tournament",
    "activity_wedding": "Wedding",
    "activity_great_hunt": "Great Hunt",
    "activity_feast": "Feast",
    "activity_pilgrimage": "Pilgrimage",
    "activity_diplomatic_visit": "Diplomatic Visit",
    "activity_war_council": "War Council",
    "activity_council_meeting": "Council Meeting",
}


def _humanize(prefix: str, key: str) -> str:
    return key.removeprefix(prefix).replace("_", " ").title()


def _activity_label(activity_type: str | None) -> str:
    if not activity_type:
        return "unknown activity"
    return _ACTIVITY_LABELS.get(activity_type, _humanize("activity_", activity_type))


@dataclass
class CharacterLocation:
    char_id: int
    name: str
    location_province_id: int | None
    location_name: str

    is_imprisoned: bool
    prison_type: str | None
    imprisoner_id: int | None
    imprisoner_name: str | None

    activity_id: int | None
    activity_type: str | None
    activity_role: str | None        # "hosting" | "attending"
    activity_host_id: int | None
    activity_host_name: str | None
    activity_intent: str | None
    fellow_attendee_count: int

    is_traveling: bool
    travel_destination_province_id: int | None
    travel_destination_name: str | None
    travel_estimated_arrival: str | None

    def summary(self) -> str:
        lines = [f"{self.name}  (id {self.char_id})"]

        if self.is_imprisoned:
            who = f" by {self.imprisoner_name}" if self.imprisoner_name else ""
            lines.append(f"  Imprisoned{who} ({self.prison_type or 'unknown'}) at {self.location_name}")
        else:
            lines.append(f"  Currently at: {self.location_name}")

        if self.activity_type:
            label = _activity_label(self.activity_type)
            if self.activity_role == "hosting":
                lines.append(f"  Hosting: {label}  ({self.fellow_attendee_count} attendees)")
            else:
                host = f"  hosted by {self.activity_host_name}" if self.activity_host_name else ""
                lines.append(f"  Attending: {label}{host}  ({self.fellow_attendee_count} other attendees)")
            if self.activity_intent:
                lines.append(f"    Intent: {self.activity_intent}")

        if self.is_traveling and self.travel_destination_name:
            eta = f"  (ETA {self.travel_estimated_arrival})" if self.travel_estimated_arrival else ""
            lines.append(f"  En route to: {self.travel_destination_name}{eta}")

        return "\n".join(lines)


def locate(gs: GameState, char_id: int) -> CharacterLocation:
    char = gs.character(char_id)
    if char is None:
        raise ValueError(f"Character {char_id} not found")

    name = decode_name(char.get("first_name", ""))
    ad = char.get("alive_data", {})
    if not isinstance(ad, dict):
        ad = {}

    # ── Location ──────────────────────────────────────────────────────── #
    raw_loc = ad.get("location")
    province_id: int | None = None
    travel_plan_id = None
    if isinstance(raw_loc, dict):
        province_id = raw_loc.get("location")
        travel_plan_id = raw_loc.get("travel_plan")
    elif isinstance(raw_loc, int):
        province_id = raw_loc
    location_name = _resolve_location(province_id, gs) if province_id else "unknown"

    # ── Imprisonment ─────────────────────────────────────────────────── #
    prison_data = ad.get("prison_data")
    is_imprisoned = isinstance(prison_data, dict)
    prison_type = prison_data.get("type") if is_imprisoned else None
    imprisoner_id = prison_data.get("imprisoner") if is_imprisoned else None
    imprisoner_name = None
    if imprisoner_id is not None:
        imprisoner = gs.character(imprisoner_id)
        if imprisoner:
            imprisoner_name = decode_name(imprisoner.get("first_name", ""))

    # ── Activity ─────────────────────────────────────────────────────── #
    activity_id = None
    activity_type = None
    activity_role = None
    activity_host_id = None
    activity_host_name = None
    activity_intent = None
    fellow_attendee_count = 0

    involved = ad.get("involved_activity_data")
    if isinstance(involved, dict) and involved.get("activity") is not None:
        activity_id = involved.get("activity")
        intent = involved.get("intent")
        if isinstance(intent, dict) and intent.get("type"):
            activity_intent = _humanize("", intent["type"])

    if activity_id is not None:
        activity = gs.activities.get(str(activity_id)) or gs.activities.get(activity_id)
        if isinstance(activity, dict):
            activity_type = activity.get("type")
            activity_host_id = activity.get("host")
            attending = activity.get("attending", [])
            if not isinstance(attending, list):
                attending = [attending] if attending else []
            if activity_host_id == char_id:
                activity_role = "hosting"
                fellow_attendee_count = len(attending)
            else:
                activity_role = "attending"
                fellow_attendee_count = max(len(attending) - 1, 0)
                if activity_host_id is not None:
                    host = gs.character(activity_host_id)
                    if host:
                        activity_host_name = decode_name(host.get("first_name", ""))

    # ── Travel ───────────────────────────────────────────────────────── #
    is_traveling = False
    travel_dest_province = None
    travel_dest_name = None
    travel_eta = None

    if travel_plan_id is not None:
        plan = gs.travel_plans.get(str(travel_plan_id)) or gs.travel_plans.get(travel_plan_id)
        if isinstance(plan, dict):
            destinations = plan.get("data", {}).get("destinations", [])
            # Find the first destination not yet arrived at — that's where they're headed.
            for dest in destinations:
                if not isinstance(dest, dict):
                    continue
                if dest.get("arrival_date", "-1.1.1") == "-1.1.1":
                    is_traveling = True
                    travel_dest_province = dest.get("province")
                    travel_eta = dest.get("estimated_arrival_date")
                    if travel_dest_province:
                        travel_dest_name = _resolve_location(travel_dest_province, gs)
                    break

    return CharacterLocation(
        char_id=char_id,
        name=name,
        location_province_id=province_id,
        location_name=location_name,
        is_imprisoned=is_imprisoned,
        prison_type=prison_type,
        imprisoner_id=imprisoner_id,
        imprisoner_name=imprisoner_name,
        activity_id=activity_id,
        activity_type=activity_type,
        activity_role=activity_role,
        activity_host_id=activity_host_id,
        activity_host_name=activity_host_name,
        activity_intent=activity_intent,
        fellow_attendee_count=fellow_attendee_count,
        is_traveling=is_traveling,
        travel_destination_province_id=travel_dest_province,
        travel_destination_name=travel_dest_name,
        travel_estimated_arrival=travel_eta,
    )
