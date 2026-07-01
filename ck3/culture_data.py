"""
ck3.culture_data
~~~~~~~~~~~~~~~~
Loads static culture definitions from CK3 game files.

Provides:
  - CultureDef dataclass
  - load_culture_definitions() → dict[str, CultureDef]
  - pillar_label(key) — humanise a culture pillar key
  - tradition_label(key) — humanise a tradition key

Source: game/common/culture/cultures/*.txt
Excludes 00_dead.txt and files starting with '_'.

Culture file format (Clausewitz text, simplified):
  czech = {
      ethos = ethos_bureaucratic
      heritage = heritage_west_slavic
      language = language_czech_slovak
      martial_custom = martial_custom_male_only
      head_determination = head_determination_domain
      traditions = {
          tradition_mountaineer_ruralism
          tradition_hard_working
          ...
      }
      dlc_tradition = { ... }   # handled: extracts trait value
      ...
  }

Religion family labels for display (keys from save file):
  rf_abrahamic → "Abrahamic"
  rf_eastern   → "Eastern/Dharmic"
  rf_sinitic   → "Sinitic"
  rf_pagan     → "Pagan"
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


_ROOT = Path(__file__).parent.parent   # project root (ck3-fileparse/)

# Module-level cache
_culture_cache: dict[str, "CultureDef"] | None = None


# --------------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------------- #

RELIGION_FAMILY_LABELS: dict[str, str] = {
    "rf_abrahamic": "Abrahamic",
    "rf_eastern":   "Eastern/Dharmic",
    "rf_sinitic":   "Sinitic",
    "rf_pagan":     "Pagan",
}


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass
class CultureDef:
    """Static definition of one culture, loaded from game files."""
    key: str
    language: str          # e.g. "language_czech_slovak"
    heritage: str          # e.g. "heritage_west_slavic"
    ethos: str             # e.g. "ethos_bureaucratic"
    martial_custom: str    # e.g. "martial_custom_male_only"
    head_determination: str  # e.g. "head_determination_domain"
    traditions: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #

# Matches top-level culture name lines: "czech = {"
_CULTURE_RE = re.compile(r"^([a-z][a-z0-9_]*)\s*=\s*\{")

# Matches simple key = value lines (unquoted value)
_KV_RE = re.compile(r"^\s*([a-z_]+)\s*=\s*([^\s{#]+)")

# Simple atom (tradition name in a traditions block, no "=")
_ATOM_RE = re.compile(r"^\s*(tradition_[a-z_]+)\s*(?:#.*)?$")

# dlc_tradition block: trait = tradition_xxx
_DLC_TRAIT_RE = re.compile(r"^\s*trait\s*=\s*(tradition_[a-z_]+)")


def _parse_culture_file(path: Path, result: dict[str, CultureDef]) -> None:
    """Parse one culture file, adding entries to result in place."""
    current_key: str | None = None
    fields: dict[str, str] = {}
    traditions: list[str] = []
    depth = 0               # overall brace depth
    culture_depth = 0       # depth at which the culture block opened
    in_traditions = False   # are we inside a traditions = { } block?
    in_dlc = False          # are we inside a dlc_tradition = { } block?
    traditions_depth = 0    # depth at which traditions block opened

    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            opens = stripped.count("{")
            closes = stripped.count("}")

            # Detect entering a traditions or dlc_tradition block
            if current_key is not None and depth == culture_depth + 1:
                if "traditions" in stripped and "=" in stripped and "{" in stripped:
                    in_traditions = True
                    traditions_depth = depth
                    depth += opens - closes
                    continue
                if "dlc_tradition" in stripped and "=" in stripped and "{" in stripped:
                    in_dlc = True
                    depth += opens - closes
                    continue

            # Inside a traditions block — collect tradition_ atoms
            if in_traditions:
                m = _ATOM_RE.match(line)
                if m:
                    traditions.append(m.group(1))
                depth += opens - closes
                if depth <= traditions_depth:
                    in_traditions = False
                continue

            # Inside a dlc_tradition block — extract trait value
            if in_dlc:
                m = _DLC_TRAIT_RE.match(line)
                if m:
                    traditions.append(m.group(1))
                depth += opens - closes
                if current_key is not None and depth <= culture_depth + 1:
                    in_dlc = False
                continue

            # Outside any culture block — look for a new culture definition
            if current_key is None:
                cm = _CULTURE_RE.match(line)
                if cm:
                    current_key = cm.group(1)
                    fields = {}
                    traditions = []
                    culture_depth = depth
                    depth += opens - closes
                else:
                    depth += opens - closes
                continue

            # Inside a culture block at depth > culture_depth
            depth += opens - closes

            # Exiting the culture block
            if depth <= culture_depth:
                result[current_key] = CultureDef(
                    key=current_key,
                    language=fields.get("language", ""),
                    heritage=fields.get("heritage", ""),
                    ethos=fields.get("ethos", ""),
                    martial_custom=fields.get("martial_custom", ""),
                    head_determination=fields.get("head_determination", ""),
                    traditions=traditions,
                )
                current_key = None
                in_traditions = False
                in_dlc = False
                continue

            # Simple key = value at culture-block depth
            if depth == culture_depth + 1:
                m = _KV_RE.match(line)
                if m:
                    fields[m.group(1)] = m.group(2)

    # Handle file that ends without closing brace (shouldn't happen, but safe)
    if current_key is not None:
        result[current_key] = CultureDef(
            key=current_key,
            language=fields.get("language", ""),
            heritage=fields.get("heritage", ""),
            ethos=fields.get("ethos", ""),
            martial_custom=fields.get("martial_custom", ""),
            head_determination=fields.get("head_determination", ""),
            traditions=traditions,
        )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def load_culture_definitions(path: str | Path | None = None) -> dict[str, CultureDef]:
    """
    Return mapping of culture_key → CultureDef for all cultures.

    Source: game/common/culture/cultures/*.txt
    Skips 00_dead.txt and any file starting with '_'.
    Cached after first load.
    """
    global _culture_cache
    if _culture_cache is not None:
        return _culture_cache

    if path is None:
        path = _ROOT / "game" / "common" / "culture" / "cultures"
    path = Path(path)
    if not path.exists():
        _culture_cache = {}
        return _culture_cache

    result: dict[str, CultureDef] = {}
    for filepath in sorted(path.glob("*.txt")):
        fname = filepath.name
        if fname.startswith("_") or fname == "00_dead.txt":
            continue
        _parse_culture_file(filepath, result)

    _culture_cache = result
    return _culture_cache


def pillar_label(key: str) -> str:
    """
    Humanise a culture pillar key by stripping its type prefix.

    Examples:
      "language_west_slavic"    → "West Slavic"
      "heritage_west_slavic"    → "West Slavic"
      "ethos_bureaucratic"      → "Bureaucratic"
      "martial_custom_male_only" → "Male Only"
      "head_determination_domain" → "Domain"
    """
    for prefix in (
        "language_",
        "heritage_",
        "ethos_",
        "martial_custom_",
        "head_determination_",
    ):
        if key.startswith(prefix):
            return key[len(prefix):].replace("_", " ").title()
    return key.replace("_", " ").title()


# Internal DLC/patch codenames used as a second-level infix on some tradition
# keys (e.g. "tradition_tgp_imperial_peace" — "tgp" was the Japan content
# patch's dev codename). These carry no display meaning, so strip them too.
_TRADITION_DLC_INFIXES = ("tgp_", "mpo_", "ep1_", "ep2_", "ep3_", "ep4_",
                          "fp1_", "fp2_", "fp3_", "fp4_", "fp5_", "ce1_")


def tradition_label(key: str) -> str:
    """
    Humanise a tradition key by stripping 'tradition_' prefix (and any
    internal DLC codename infix immediately after it).

    Example: "tradition_chivalry" → "Chivalry"
    Example: "tradition_tgp_imperial_peace" → "Imperial Peace"
    """
    rest = key.removeprefix("tradition_")
    for infix in _TRADITION_DLC_INFIXES:
        if rest.startswith(infix):
            rest = rest[len(infix):]
            break
    return rest.replace("_", " ").title()
