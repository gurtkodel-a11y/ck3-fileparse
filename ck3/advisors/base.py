"""
ck3.advisors.base
~~~~~~~~~~~~~~~~~
Shared base class and utilities for all council advisors.

Advisors are "level 2": they interpret evaluator output and produce
strategic assessments aimed at a human reader (or an LLM).  Each advisor
focuses on one council domain; the Council class wires them together and
ensures evaluator reports are built only once.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ck3.advisors import Council


# --------------------------------------------------------------------------- #
# Shared output primitives
# --------------------------------------------------------------------------- #

@dataclass
class Priority:
    """One actionable item surfaced by an advisor."""
    text: str
    urgency: str          # "high" | "medium" | "low"
    detail: str = ""

    def format(self) -> str:
        prefix = {"high": "[!]", "medium": "[ ]", "low": "[-]"}.get(self.urgency, "[ ]")
        out = f"  {prefix} {self.text}"
        if self.detail:
            out += f"\n      {self.detail}"
        return out


# --------------------------------------------------------------------------- #
# Base advisor
# --------------------------------------------------------------------------- #

class BaseAdvisor(ABC):
    """Common interface for all council advisors."""

    role: str = "Advisor"           # overridden per subclass

    def __init__(self, council: "Council"):
        self.council = council
        self.gs = council.gs
        self.char_id = council.char_id

    @abstractmethod
    def advise(self):
        """Build and return the advisor's structured brief."""
        ...

    # ── Shared helpers ─────────────────────────────────────────────────────── #

    @staticmethod
    def _power_label(ratio: float) -> str:
        """Describe a power ratio (player / other) in plain language."""
        if ratio >= 2.0:
            return "dominant"
        if ratio >= 1.2:
            return "strong advantage"
        if ratio >= 0.85:
            return "roughly matched"
        if ratio >= 0.5:
            return "outnumbered"
        return "critically outnumbered"

    @staticmethod
    def _fmt_priorities(priorities: list[Priority]) -> str:
        if not priorities:
            return "  (none identified)"
        return "\n".join(p.format() for p in priorities)
