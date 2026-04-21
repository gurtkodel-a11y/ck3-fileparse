"""
ck3.advisors
~~~~~~~~~~~~
Level-2 advisor layer — strategic interpretation above the raw evaluators.

Each advisor mirrors one seat on the CK3 council:

  Marshal     — military strategy: strength, threats, wars, knights
  Chancellor  — diplomacy: vassals, alliances, external relations, hooks
  Steward     — domain management: development, buildings, control
  Councilor   — religious affairs: faith, fervor, nearby faiths, holy wars
  Spymaster   — intrigue: leverage, enemies, schemes, factions

The Council class owns the GameState and lazily builds evaluator reports,
sharing them across all advisors so each report is computed only once.

Usage:
    from ck3.advisors import Council
    council = Council(gs, char_id)

    # Individual advisors
    brief = council.marshal.advise()
    print(brief.summary())

    # Full council brief
    print(council.brief())

    # Selective brief
    print(council.brief(["marshal", "chancellor"]))
"""

from __future__ import annotations
from ck3.gamestate import GameState


_ALL_ADVISORS = ["marshal", "chancellor", "steward", "councilor", "spymaster"]


class Council:
    """
    Central hub for level-2 analysis.

    Owns one GameState + char_id and exposes all five council advisors.
    Evaluator reports are built lazily on first access and cached, so running
    multiple advisors does not re-parse the same data.
    """

    def __init__(self, gs: GameState, char_id: int):
        self.gs = gs
        self.char_id = char_id
        self._reports: dict = {}

    # ── Evaluator report access (lazy, cached) ────────────────────────────── #

    @property
    def military_report(self):
        """MilitaryReport — built once, shared by Marshal and Chancellor."""
        if "military" not in self._reports:
            from ck3.evaluators.military import MilitaryEvaluator
            self._reports["military"] = MilitaryEvaluator(self.gs, self.char_id).report()
        return self._reports["military"]

    @property
    def culture_report(self):
        """CultureReport — built once, shared by Councilor and Chancellor."""
        if "culture" not in self._reports:
            from ck3.evaluators.culture import CultureEvaluator
            self._reports["culture"] = CultureEvaluator(self.gs, self.char_id).report()
        return self._reports["culture"]

    @property
    def relationships_report(self):
        """RelationshipsReport — built once, shared by Chancellor and Spymaster."""
        if "relationships" not in self._reports:
            from ck3.evaluators.relationships import RelationshipsEvaluator
            self._reports["relationships"] = RelationshipsEvaluator(self.gs, self.char_id).report()
        return self._reports["relationships"]

    @property
    def terrain_report(self):
        """TerrainReport — built once, used by Steward (and optionally Marshal)."""
        if "terrain" not in self._reports:
            from ck3.evaluators.terrain import TerrainEvaluator
            self._reports["terrain"] = TerrainEvaluator(self.gs, self.char_id).report()
        return self._reports["terrain"]

    # ── Advisor access ────────────────────────────────────────────────────── #

    @property
    def marshal(self):
        """Marshal — military strategy."""
        from ck3.advisors.marshal import MarshalAdvisor
        return MarshalAdvisor(self)

    @property
    def chancellor(self):
        """Chancellor — diplomacy and internal politics."""
        from ck3.advisors.chancellor import ChancellorAdvisor
        return ChancellorAdvisor(self)

    @property
    def steward(self):
        """Steward — domain management and development."""
        from ck3.advisors.steward import StewardAdvisor
        return StewardAdvisor(self)

    @property
    def councilor(self):
        """Councilor (Chaplain) — religious affairs."""
        from ck3.advisors.councilor import CouncilorAdvisor
        return CouncilorAdvisor(self)

    @property
    def spymaster(self):
        """Spymaster — intrigue, leverage, and hidden threats."""
        from ck3.advisors.spymaster import SpymasterAdvisor
        return SpymasterAdvisor(self)

    # ── Full council brief ────────────────────────────────────────────────── #

    def brief(self, advisors: list[str] | None = None) -> str:
        """
        Run all (or selected) advisors and return a combined brief.

        Args:
            advisors: subset of ["marshal", "chancellor", "steward",
                                  "councilor", "spymaster"].
                      Defaults to all five in that order.
        """
        selected = advisors or _ALL_ADVISORS
        divider = "\n" + "=" * 72 + "\n"
        parts = [getattr(self, name).advise().summary() for name in selected]
        return divider.join(parts)
