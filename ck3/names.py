"""
ck3.names
~~~~~~~~~
Utilities for decoding and formatting CK3 character names.

CK3 save files use a compact ASCII encoding for non-ASCII characters:
  - European diacritics: uppercase letter + "_"  →  accented lowercase
      A_ → á    E_ → é    I_ → í    O_ → ó    U_ → ú
      C_ → ç    N_ → ñ    Z_ → ź    S_ → š
      R_ → ř    L_ → ł
    Double-letter forms encode caron (háček) variants:
      CC_ → č   EE_ → ě
  - CJK characters: "_XXXX" where XXXX is the Unicode code point in hex
      Daheng_5927_4EA8  →  Daheng大亨

Public API:
    decode_name(raw)              decode a raw save-file name string
    house_prefix_name(house)      return (prefix, name) for a dynasty house
    name_ordinal(char, gs, char_id)  1-based ordinal within the dynasty house (for "II", "III" …)
    char_label(char, gs, char_id) full formatted name string
"""

from __future__ import annotations
import re


# ── Diacritic decoding ────────────────────────────────────────────────────── #

_UPPER_DIACRITICS: dict[str, str] = {
    # Single-letter forms (acute, cedilla, etc.)
    "A": "á", "E": "é", "I": "í", "O": "ó", "U": "ú",
    "C": "ç", "N": "ñ", "Z": "ź", "S": "š",
    "R": "ř", "L": "ł",
    # Double-letter forms (caron / háček)
    "CC": "č", "EE": "ě",
}

# Double-letter forms must come first in the alternation so they win over
# the single-letter forms when both could match (e.g. "CC_" vs "C_").
_DIACRITIC_RE  = re.compile(r"(CC|EE|[AEIOUCNZSLR])_")
_CJK_RE        = re.compile(r"_([0-9A-Fa-f]{4})")

# Characters that begin a new "word" — diacritics after these should be uppercase
_WORD_STARTERS = frozenset((" ", "-", "\t"))


def decode_name(raw: str) -> str:
    """
    Decode a CK3 save-file character name to readable Unicode.

    The encoding convention is: uppercase letter + "_" marks a diacritic.
    The accented letter is uppercase when the sequence appears at the start
    of the name or after a space/hyphen (i.e. at the start of a word).

    Examples::
        decode_name("LorcA_n")              → "Lorcán"
        decode_name("BE_oA_ed")             → "Béoáed"
        decode_name("O_lafr")               → "Ólafr"
        decode_name("A_ine")                → "Áine"
        decode_name("RO_gnvaldr")           → "Rógnvaldr"
        decode_name("CU__Uladh")            → "Cú Uladh"
        decode_name("Daheng_5927_4EA8")     → "Daheng大亨"
        decode_name("KiliC_")               → "Kiliç"
    """
    if not raw or "_" not in raw:
        return raw

    def _replace_diacritic(m: re.Match) -> str:
        letter = m.group(1)
        decoded_lower = _UPPER_DIACRITICS.get(letter, letter.lower())
        # Capitalise when at the start of the string or after a word-starter
        at_word_start = m.start() == 0 or raw[m.start() - 1] in _WORD_STARTERS
        return decoded_lower.upper() if at_word_start else decoded_lower

    # CJK codepoints must be decoded first: chained codepoints like
    # "_5D6C_540D" put a hex digit (e.g. "C") right against the next
    # underscore, which the diacritic pass would otherwise misread as its
    # own "C_" diacritic marker and corrupt the codepoint.
    result = _CJK_RE.sub(lambda m: chr(int(m.group(1), 16)), raw)
    result = _DIACRITIC_RE.sub(_replace_diacritic, result)
    # Remaining underscores are word separators (e.g. "CU__Uladh" → "Cú Uladh")
    # or stray artefacts; replace with a space and collapse extras.
    result = result.replace("-_", "-")
    result = re.sub(r"_+", " ", result).strip()
    return result


# ── Dynasty house naming ──────────────────────────────────────────────────── #

def house_prefix_name(house: dict) -> tuple[str, str]:
    """
    Return (prefix, name) for a dynasty house record.

    prefix  — dynastic prefix, e.g. "ua", "de", "av", "" if none
    name    — house name, e.g. "Briain", "Orsini", "Carthaigh"

    How names are derived:
      - If the house has a 'name' field (localization key "dynn_Foo") → strip "dynn_" → "Foo"
      - Otherwise derive from 'key': "house_british_isles_briain" → last segment → "Briain"
    How prefixes are derived:
      - 'prefix' field holds a localization key "dynnp_ua" → strip "dynnp_" → "ua"

    Procedurally-generated houses (no historical 'name' string) sometimes carry
    a bare numeric 'key' — an ID into the game's dynamic name generator rather
    than a "house_*" string we can derive text from. There's no name data
    available for these in the save, so they fall back to "".
    """
    raw_name   = house.get("name", "")
    raw_prefix = house.get("prefix", "")
    key        = house.get("key", "")

    if isinstance(raw_name, str) and raw_name:
        name = decode_name(raw_name.removeprefix("dynn_"))
    elif isinstance(key, str) and key:
        # "house_british_isles_briain" → strip "house_" → split → last part → capitalize
        without_house = key.removeprefix("house_")
        parts = without_house.split("_")
        name = parts[-1].capitalize() if parts else ""
    else:
        name = ""

    prefix = decode_name(raw_prefix.removeprefix("dynnp_")) if isinstance(raw_prefix, str) and raw_prefix else ""

    return prefix, name


# ── Name ordinal ─────────────────────────────────────────────────────────── #

_ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]


def name_ordinal(char: dict, gs, char_id: int) -> int:
    """
    Return the 1-based ordinal for this character's given name within their
    dynasty house (scanning both living and dead_unprunable records).

    Returns 1 if the character is the only (or first) bearer of that name
    in the house.  Returns 2 for the second, etc.

    Note: fully-pruned dead ancestors are absent from the save file; the
    ordinal may therefore be lower than the game displays when ancestors
    have been pruned.
    """
    raw_name = char.get("first_name", "")
    house_id = char.get("dynasty_house")
    if not raw_name or house_id is None:
        return 1

    matches: list[tuple[str, int]] = []  # (birth_date, char_id)

    for cid_str, c in gs.living.items():
        if c.get("first_name") == raw_name and c.get("dynasty_house") == house_id:
            matches.append((c.get("birth", ""), int(cid_str)))
    for cid_str, c in gs.dead.items():
        if c.get("first_name") == raw_name and c.get("dynasty_house") == house_id:
            matches.append((c.get("birth", ""), int(cid_str)))

    if len(matches) <= 1:
        return 1

    def _date_key(birth: str) -> tuple:
        try:
            parts = birth.split(".")
            return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 1, int(parts[2]) if len(parts) > 2 else 1)
        except (ValueError, IndexError):
            return (0, 0, 0)

    matches.sort(key=lambda x: _date_key(x[0]))
    for i, (_, cid) in enumerate(matches, 1):
        if cid == char_id:
            return i
    return 1


# ── Tier labels (masculine and feminine) ─────────────────────────────────── #

_TIER_LABEL_M: dict[str, str] = {
    "e": "Emperor", "k": "King",   "d": "Duke",     "c": "Count",    "b": "Baron",
}
_TIER_LABEL_F: dict[str, str] = {
    "e": "Empress", "k": "Queen",  "d": "Duchess",  "c": "Countess", "b": "Baroness",
}


def title_ruler_label(title: dict, female: bool = False) -> str:
    """
    Build a human-readable ruler label from a title record.

    Uses the title key prefix for the rank label (e, k, d, c, b) and
    title_name_data.name for the place name.  Pass female=True for the
    feminine form (Duchess, Countess, Queen, …).

    Examples::
        c_desmond, female=False  → "Count of Desmond"
        c_desmond, female=True   → "Countess of Desmond"
        d_munster                → "Duke of Munster"
        k_england                → "King of England"
    """
    if not isinstance(title, dict):
        return ""
    key = title.get("key", "")
    tier = key[0] if key else "b"
    labels = _TIER_LABEL_F if female else _TIER_LABEL_M
    label = labels.get(tier, "Lady" if female else "Lord")

    name_data = title.get("title_name_data", {})
    raw_place = name_data.get("name", "") if isinstance(name_data, dict) else ""
    if raw_place:
        place = decode_name(raw_place)
    else:
        # Derive from key: c_desmond → "Desmond"
        place = key[2:].replace("_", " ").title() if len(key) > 2 else key

    return f"{label} of {place}" if place else label


# ── Full character label ──────────────────────────────────────────────────── #

def char_label(char: dict, gs, char_id: int, *, include_title: bool = True) -> str:
    """
    Return a rich formatted name for a character.

    Format:  "{GivenName}[ {Roman ordinal}][ {prefix} {HouseName}][, {TierLabel} of {Place}]"

    include_title=False omits the title clause (useful for narrow columns).

    Examples::
        "Murchad Briain, Duke of Munster"
        "Muiredach Carthaigh, Count of Desmond"
        "Rógnvaldr II av Vedrafjord, Count of Ormond"
        "Brian Briain"          (unlanded)
        "Gwenllian"             (unlanded, no house info)
        "Áine"                  (female, unlanded, no house)
    """
    given = decode_name(char.get("first_name", str(char_id)))
    is_female = char.get("female") == "yes"

    # Ordinal (II, III, …) — only appended when > 1
    ordinal = name_ordinal(char, gs, char_id)
    ordinal_str = f" {_ROMAN[ordinal]}" if 1 < ordinal < len(_ROMAN) else ""

    # House / dynasty suffix
    house_part = ""
    house_id = char.get("dynasty_house")
    if house_id is not None:
        house = gs.dynasty_house(house_id)
        if house:
            prefix, name = house_prefix_name(house)
            if name:
                house_part = f" {prefix} {name}".rstrip() if prefix else f" {name}"

    # Title clause
    title_part = ""
    if include_title:
        gs.build_indices()
        titles = gs.titles_held_by(char_id)
        if titles:
            best = None
            best_order = 99
            tier_order = {"e": 0, "k": 1, "d": 2, "c": 3, "b": 4}
            for t in titles:
                if not isinstance(t, dict):
                    continue
                key = t.get("key", "")
                order = tier_order.get(key[0] if key else "b", 9)
                if order < best_order:
                    best_order = order
                    best = t
            if best:
                title_part = ", " + title_ruler_label(best, female=is_female)

    return given + ordinal_str + house_part + title_part
