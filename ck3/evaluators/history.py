"""
ck3.evaluators.history
~~~~~~~~~~~~~~~~~~~~~~
Session history evaluator: reconstructs major title-change events from
landed_titles history blocks, covering a requested date range.

CK3 saves do NOT store completed war records — active_wars contains only
ongoing wars; finished wars are gone. Title history blocks are the best
available proxy: when a title changes hands via conquest, the entry records
the date, transfer type, and new holder.

Epistemic design principles:
  1. Confidence scales with cluster size (titles sharing the same date and
     new holder). One title is weaker evidence than five.
  2. conquest_claim identifies the claimant who received the title, NOT
     necessarily the character who led the war. In CK3 you can press a claim
     on behalf of someone else; they receive the title without fighting.
  3. Peaceful transfer types (succession, grants, revocations) are reported
     separately and never cited as evidence of warfare.
  4. De jure cascades (a duchy changing hands pulls its counties under the
     new duke) are NOT reflected in title history — only the duchy-level
     change appears.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from ck3.gamestate import GameState
from ck3.names import decode_name


# ── Date utilities ────────────────────────────────────────────────────────────

def _date_key(date_str: str) -> tuple[int, int, int]:
    """Numeric sort key for 'YYYY.M.D' strings; safe across multi-century spans."""
    try:
        parts = date_str.split(".")
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0,
                int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return (0, 0, 0)


def _date_ge(a: str, b: str) -> bool:
    return _date_key(a) >= _date_key(b)


# ── Transfer type classification ──────────────────────────────────────────────

_WAR_TYPES = frozenset({"conquest", "conquest_claim", "conquest_holy_war"})
_FACTION_TYPES = frozenset({"faction_demand"})
_PEACEFUL_TYPES = frozenset({
    "appointment_succession", "granted", "revoked",
    "abdication", "usurped", "created", "destroyed",
})

_TYPE_LABEL = {
    "conquest":            "conquest",
    "conquest_claim":      "conquest (pressed claim)",
    "conquest_holy_war":   "holy war conquest",
    "faction_demand":      "faction demand",
    "appointment_succession": "succession",
    "granted":             "granted by liege",
    "revoked":             "revoked by liege",
    "abdication":          "abdication",
    "usurped":             "usurpation",
    "created":             "title created",
    "destroyed":           "title destroyed",
    "succession":          "succession",
}

_TIER_ORDER = "ekdcb"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class TitleTransfer:
    title_key:       str
    date:            str
    transfer_type:   str               # raw type string
    new_holder_id:   Optional[int]
    prev_holder_id:  Optional[int]
    new_holder_name: str = ""
    prev_holder_name: str = ""

    def is_war(self) -> bool:
        return self.transfer_type in _WAR_TYPES

    def is_faction(self) -> bool:
        return self.transfer_type in _FACTION_TYPES

    def tier(self) -> str:
        return self.title_key[0] if self.title_key else "?"

    def tier_order(self) -> int:
        t = self.tier()
        return _TIER_ORDER.index(t) if t in _TIER_ORDER else len(_TIER_ORDER)


@dataclass
class TransferCluster:
    """
    A group of title transfers sharing the same date and new holder —
    the natural unit of evidence for a single war or event.
    """
    date:             str
    new_holder_id:    Optional[int]
    new_holder_name:  str
    transfers:        list[TitleTransfer] = field(default_factory=list)
    confidence:       str = ""          # "possible" / "probable" / "strong"
    confidence_notes: list[str] = field(default_factory=list)

    def dominant_type(self) -> str:
        """Most informative transfer type in this cluster."""
        for preferred in ("conquest_holy_war", "conquest_claim", "conquest",
                          "faction_demand"):
            if any(t.transfer_type == preferred for t in self.transfers):
                return preferred
        types = {t.transfer_type for t in self.transfers}
        return next(iter(types)) if len(types) == 1 else ", ".join(sorted(types))

    def sorted_transfers(self) -> list[TitleTransfer]:
        return sorted(self.transfers, key=lambda t: t.tier_order())


@dataclass
class SessionHistoryReport:
    since_date:           str
    save_date:            str
    war_clusters:         list[TransferCluster]
    faction_clusters:     list[TransferCluster]
    notable_peaceful:     list[TitleTransfer]   # duchy+ grants/revocations/creations
    total_war_transfers:  int = 0
    total_other_transfers: int = 0

    def summary(self) -> str:
        lines = [
            f"Session History — {self.since_date} to {self.save_date}",
            "=" * 70,
        ]

        n_clusters = len(self.war_clusters) + len(self.faction_clusters)
        if n_clusters == 0:
            lines += [
                "",
                "No war or faction title transfers detected in this period.",
                "(Peaceful succession events are not shown. Note: completed war",
                " records are not stored in CK3 saves — only title ownership",
                " changes remain.)",
            ]
        else:
            lines.append(
                f"\n{self.total_war_transfers} war-type title transfer(s) in "
                f"{len(self.war_clusters)} cluster(s)."
            )

        if self.war_clusters:
            lines.append("\n--- War / Conquest Events ---")
            for c in sorted(self.war_clusters, key=lambda x: _date_key(x.date)):
                label = _TYPE_LABEL.get(c.dominant_type(), c.dominant_type())
                lines.append(
                    f"\n  {c.date}  [{c.confidence.upper()}]  {label}"
                )
                lines.append(
                    f"  Recipient: {c.new_holder_name}"
                    + (f" (id {c.new_holder_id})" if c.new_holder_id else "")
                )
                for t in c.sorted_transfers():
                    from_str = (
                        f"from {t.prev_holder_name}"
                        + (f" (id {t.prev_holder_id})" if t.prev_holder_id else "")
                        if t.prev_holder_id else "from unknown"
                    )
                    lines.append(f"    {t.title_key:35s}{from_str}")
                for note in c.confidence_notes:
                    lines.append(f"  > {note}")

        if self.faction_clusters:
            lines.append("\n--- Faction Demand Outcomes ---")
            for c in sorted(self.faction_clusters, key=lambda x: _date_key(x.date)):
                lines.append(
                    f"  {c.date}  {c.new_holder_name} gained via faction demand:"
                )
                for t in c.sorted_transfers():
                    lines.append(f"    {t.title_key}")

        if self.notable_peaceful:
            lines.append("\n--- Notable Peaceful Transfers (duchy+ tier) ---")
            for t in sorted(self.notable_peaceful, key=lambda x: _date_key(x.date)):
                label = _TYPE_LABEL.get(t.transfer_type, t.transfer_type)
                to_str = t.new_holder_name or f"id {t.new_holder_id}"
                from_str = (
                    f" from {t.prev_holder_name}" if t.prev_holder_name else ""
                )
                lines.append(
                    f"  {t.date}  {t.title_key:30s}  {label:22s}→ {to_str}{from_str}"
                )

        lines += [
            "",
            "--- Epistemic Notes ---",
            "  Title history records ownership changes, not war records.",
            "  Completed wars are not stored in CK3 saves; these events are",
            "  the closest available proxy.",
            "",
            "  Confidence levels:",
            "    STRONG   5+ titles to same holder same day — strong war evidence",
            "    PROBABLE 2–4 titles to same holder same day — likely one event",
            "    POSSIBLE 1 title — consistent with war but not distinguishable",
            "             from a grant, negotiated transfer, or scripted event",
            "",
            "  'conquest_claim': the named recipient held the claim and received",
            "  the title. Most often they led the war personally; however, a third",
            "  party can press a claim on someone's behalf in CK3, in which case",
            "  the claimant receives the title without having fought themselves.",
            "",
            "  De jure cascade: when a duchy changes hands, its de jure counties",
            "  automatically fall under the new duke. Those vassal shifts are NOT",
            "  recorded as title transfers and will not appear here.",
        ]

        return "\n".join(lines)


# ── Evaluator ─────────────────────────────────────────────────────────────────

class HistoryEvaluator:
    """
    Scan landed_titles history for transfer events in [since_date, save_date].

    Parameters
    ----------
    gs          : GameState (built indices not required)
    since_date  : 'YYYY.M.D' — lower bound (inclusive); events before this are skipped
    char_id     : optional — if set, only events where this character is the
                  new OR previous holder are returned
    """

    def __init__(self, gs: GameState, since_date: str,
                 char_id: Optional[int] = None):
        self.gs = gs
        self.since_date = since_date
        self.char_id = char_id

    def report(self) -> SessionHistoryReport:
        transfers = self._collect_transfers()

        if self.char_id is not None:
            transfers = [
                t for t in transfers
                if t.new_holder_id == self.char_id
                or t.prev_holder_id == self.char_id
            ]

        war_clusters, faction_clusters = self._cluster(transfers)

        notable_peaceful = [
            t for t in transfers
            if t.transfer_type in _PEACEFUL_TYPES
            and t.tier() in ("e", "k", "d")
        ]

        total_war = sum(len(c.transfers) for c in war_clusters)
        total_other = len(transfers) - total_war

        return SessionHistoryReport(
            since_date=self.since_date,
            save_date=self.gs.date,
            war_clusters=war_clusters,
            faction_clusters=faction_clusters,
            notable_peaceful=notable_peaceful,
            total_war_transfers=total_war,
            total_other_transfers=total_other,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _collect_transfers(self) -> list[TitleTransfer]:
        results: list[TitleTransfer] = []

        for title in self.gs.titles.values():
            if not isinstance(title, dict):
                continue
            key = title.get("key", "")
            history = title.get("history")
            if not isinstance(history, dict) or not history:
                continue

            # Sort dates numerically (plain string sort fails across centuries)
            sorted_dates = sorted(history.keys(), key=_date_key)

            for i, date in enumerate(sorted_dates):
                if not _date_ge(date, self.since_date):
                    continue

                entry = history[date]

                if isinstance(entry, int):
                    transfer_type = "succession"
                    new_holder_id = entry
                elif isinstance(entry, dict):
                    transfer_type = entry.get("type", "unknown")
                    new_holder_id = entry.get("holder")
                    if new_holder_id is None:
                        # destroyed / no holder — record if notable tier
                        if key[0:1] in ("e", "k", "d") and transfer_type == "destroyed":
                            results.append(TitleTransfer(
                                title_key=key, date=date,
                                transfer_type=transfer_type,
                                new_holder_id=None, prev_holder_id=None,
                            ))
                        continue
                else:
                    continue

                # Previous holder
                prev_holder_id: Optional[int] = None
                if i > 0:
                    prev_entry = history[sorted_dates[i - 1]]
                    if isinstance(prev_entry, int):
                        prev_holder_id = prev_entry
                    elif isinstance(prev_entry, dict):
                        prev_holder_id = prev_entry.get("holder")

                results.append(TitleTransfer(
                    title_key=key,
                    date=date,
                    transfer_type=transfer_type,
                    new_holder_id=new_holder_id,
                    prev_holder_id=prev_holder_id,
                    new_holder_name=self._name(new_holder_id),
                    prev_holder_name=self._name(prev_holder_id) if prev_holder_id else "",
                ))

        return results

    def _name(self, char_id: Optional[int]) -> str:
        if char_id is None:
            return ""
        char = self.gs.character(char_id)
        if char is None:
            # May be dead
            dead = self.gs.dead.get(str(char_id))
            if dead:
                raw = dead.get("first_name", "")
                return decode_name(raw) if raw else f"id {char_id}"
            return f"id {char_id}"
        raw = char.get("first_name", "")
        return decode_name(raw) if raw else f"id {char_id}"

    def _cluster(
        self, transfers: list[TitleTransfer]
    ) -> tuple[list[TransferCluster], list[TransferCluster]]:
        war_map:     dict[tuple, TransferCluster] = {}
        faction_map: dict[tuple, TransferCluster] = {}

        for t in transfers:
            if t.is_war():
                key = (t.date, t.new_holder_id)
                if key not in war_map:
                    war_map[key] = TransferCluster(
                        date=t.date,
                        new_holder_id=t.new_holder_id,
                        new_holder_name=t.new_holder_name,
                    )
                war_map[key].transfers.append(t)
            elif t.is_faction():
                key = (t.date, t.new_holder_id)
                if key not in faction_map:
                    faction_map[key] = TransferCluster(
                        date=t.date,
                        new_holder_id=t.new_holder_id,
                        new_holder_name=t.new_holder_name,
                    )
                faction_map[key].transfers.append(t)

        war_clusters = list(war_map.values())
        for c in war_clusters:
            _annotate_confidence(c)

        faction_clusters = list(faction_map.values())
        for c in faction_clusters:
            c.confidence = "confirmed"
            c.confidence_notes = ["Faction demand outcome recorded directly in title history."]

        return war_clusters, faction_clusters


# ── Confidence annotation (module-level so it's easy to test) ────────────────

def _annotate_confidence(cluster: TransferCluster) -> None:
    n = len(cluster.transfers)
    notes: list[str] = []

    # Cluster-size confidence
    if n >= 5:
        cluster.confidence = "strong"
        notes.append(
            f"{n} titles transferred to the same holder on the same date. "
            "Strong evidence of a single war outcome — coincidental same-day "
            "transfers at this scale are very unlikely."
        )
    elif n >= 2:
        cluster.confidence = "probable"
        notes.append(
            f"{n} titles transferred to the same holder on the same date. "
            "Probable single event, but simultaneous independent transfers "
            "are possible (e.g., a liege granting multiple titles at once)."
        )
    else:
        cluster.confidence = "possible"
        notes.append(
            "Single title transfer. Consistent with a war outcome but "
            "indistinguishable from a grant, negotiated deal, scripted event, "
            "or inheritance on the same date as another change."
        )

    # Type-specific caveats
    types = {t.transfer_type for t in cluster.transfers}
    if "conquest_claim" in types:
        notes.append(
            "'conquest_claim': the recipient held the claim and received the title. "
            "This is most often the war leader — but in CK3 a third party can press "
            "a claim on someone's behalf, in which case the claimant receives the title "
            "without having personally fought."
        )
    if "conquest" in types:
        notes.append(
            "'conquest' (no formal claim): typically a de jure war or similar CB "
            "where the winner took a title without holding a prior claim to it."
        )
    if "conquest_holy_war" in types:
        notes.append(
            "'conquest_holy_war': title taken via a declared holy war."
        )

    cluster.confidence_notes = notes
