# CK3 Fileparse — Project Guide

## Goal

Build a Python toolkit that reads Crusader Kings III save files and produces
accurate, human-readable analyses of the game state.  The immediate use case 
is as a validation tool to ensure that the underlying parser code is representing
the gamestate correctly---the player compares the tool's output against their 
the actual game as experienced through CKIII to check accuracy.  The longer-term 
vision is an AI tool that can allow people to engage with the game in a more natural 
language form, and perhaps from a more first-person perspective (unlike the usual 
game interface, which presents more content from the third-person point of view 
in many cases).

The project proceeds in layers:

1. **Parse** — convert the raw Clausewitz text format into Python dicts
2. **Model** — wrap the parsed data in a structured `GameState` object with
   lookup indices
3. **Evaluate** — domain-specific modules that extract and organise
   meaningful facts from `GameState` (military, culture, diplomacy, etc.)
4. **Report** — human-readable summaries of evaluator output.

Only layers 1–3 are complete.  Layer 4 exists as plain-text summaries
produced by each evaluator's `summary()` method.

---

## Save File Pipeline

```
[Gaming PC]  watch_autosaves.py
                 ↓  copies new manual .ck3 saves to sample-saves/
[Mac]        extract_snapshots.py
                 ↓  unzips old-format saves; invokes ck3-melt for binary saves
             sample-saves/extracted/*.txt   ← plaintext Clausewitz format
                 ↓
             parse_gamestate.parse()        ← tokeniser + iterative parser
                 ↓
             ck3.gamestate.GameState        ← structured model + indices
                 ↓
             ck3.evaluators.*              ← domain evaluators
```

**Save formats encountered:**
- Old format (pre-1.13): ZIP containing a plaintext `gamestate` entry
- New format (1.18+): `SAV0` plaintext header (~32 KB) followed by an embedded
  ZIP archive containing a plaintext `gamestate` entry — **no ck3-melt needed**;
  `extract_snapshots.py` detects this automatically and extracts directly

All `.ck3` files in `sample-saves/` are the 1.18+ header+ZIP format and have
been extracted to `sample-saves/extracted/`.  The extracted `.txt` files are
gitignored (too large to push); they live only on the local Mac.

---

## Codebase Map

```
parse_gamestate.py          Clausewitz tokeniser + iterative parser
run_report.py               CLI: parse a save, run selected evaluators, print report

ck3/
  __init__.py
  gamestate.py              GameState wrapper + all lookup indices
  geography.py              Region definitions + interaction-proximity zones
  names.py                  Name decoding, house labels, ordinals, char_label()
  province_data.py          Static game data loader: terrain + barony→province bridge
  evaluators/
    __init__.py
    military.py             MilitaryEvaluator  → MilitaryReport
    culture.py              CultureEvaluator   → CultureReport
    relationships.py        RelationshipsEvaluator → RelationshipsReport
    terrain.py              TerrainEvaluator   → TerrainReport

assessments/                Written strategic assessments (context for LLM advisor)
  Vratislav_II_1066-09-20_assessment.txt
  Vratislav_II_1072-09-13_assessment.txt

game/
  common/
    province_terrain/
      00_province_terrain.txt   map_province_id → terrain string (static CK3 data)
    landed_titles/
      00_landed_titles.txt      barony→province bridge + county capital lookup

sample-saves/
  extracted/                16 saves extracted to plaintext (gitignored):
    Duke_Vratislav_II_of_Bohemia_1066_09_15.txt   (62 MB)   char (use default)
    Duke_Vratislav_II_of_Bohemia_1066_09_20.txt   (62 MB)   char (use default)
    Duke_Vratislav_II_of_Bohemia_1067_01_13.txt   (68 MB)   char (use default)
    Duke_Vratislav_II_of_Bohemia_1072_09_13.txt   (89 MB)   char (use default)
    Petty_King_Murchad_of_Munster_1066_09_15.txt  (62 MB)   char 31762
    Petty_King_Murchad_of_Munster_1069_11_28.txt  (81 MB)   char 31762
    Petty_King_Murchad_of_Munster_1071_01_07.txt  (86 MB)   char 31762
    Petty_King_Murchad_of_Munster_1076_04_09.txt  (96 MB)   char 31762
    Petty_King_Murchad_of_Munster_1077_04_14.txt  (98 MB)   char 31762
    Petty_King_Murchad_of_Munster_1080_01_07.txt (104 MB)   char 31762
    Petty_King_Murchad_of_Munster_1080_10_08.txt (105 MB)   char 31762
    Petty_King_Murchad_of_Munster_1081_07_01.txt (105 MB)   char 31762
    Petty_King_Murchad_of_Munster_1083_08_13.txt (109 MB)   char 31762
    Petty_King_Murchad_of_Munster_1085_03_09.txt (112 MB)   char 31762
    Petty_King_Murchad_of_Munster_1085_10_05.txt (113 MB)   char 31762
    Petty_King_Brian_II_of_Munster_1093_01_03.txt (161 MB)  char 36303  [multiplayer — specify ID explicitly]
```

---

## Key Design Decisions

### Parser (`parse_gamestate.py`)
- Iterative stack-based parser to avoid Python recursion limits on large saves
- Duplicate keys in a block are merged into lists (common in Clausewitz format)
- Unquoted atoms are coerced to `int` or `float` where possible

### GameState (`ck3/gamestate.py`)
- All indices are built lazily on first call to `build_indices()`
- Indices built: titles-by-holder, units-by-owner, wars-by-character,
  vassal-contracts-by-liege/vassal, title-key-to-kingdom
- The `vassal_contracts` data lives at `raw["vassal_contracts"]["database"]`
  (one level deeper than the top-level key)
- Active relations live as a flat list at `raw["relations"]["active_relations"]`
- Multiplayer saves: `played_character` key appears twice → parser merges to list;
  handled with `isinstance(_played, list)` guard

### Names (`ck3/names.py`)
- CK3 encoding: `X_` (uppercase + underscore) = accented lowercase; `_XXXX` = CJK
  hex codepoint; remaining `_` = word separator
- `decode_name(raw)` — decodes a raw save-file name string
- `house_prefix_name(house)` — returns `(prefix, name)` from house record
- `name_ordinal(char, gs, char_id)` — 1-based ordinal within dynasty house by
  birth-date sort (limitation: fully pruned dead ancestors absent from save)
- `char_label(char, gs, char_id)` — full formatted name including ordinal, house,
  and highest title (gender-aware); `include_title=False` for narrow columns
- `title_ruler_label(title, female)` — "Count of X", "Duchess of X", etc.

### Geography (`ck3/geography.py`)
- Regions are coarse groupings of kingdom-tier title keys
- "Proximity" (zone 0–3) is explicitly **not** pure physical distance — it
  approximates *interaction likelihood*, shaped by terrain, sea routes,
  political structure, and the de-jure title network
- The de-jure hierarchy is intentionally used: it naturally encodes barriers
  and channels of interaction that physical distance alone misses
- Future work: terrain cost weights, sea-lane bonuses, cultural affinity

### Evaluators — general principles
- Each evaluator takes `GameState` + `char_id` and returns a structured
  dataclass report
- Evaluators are "level 1": they surface raw facts, not strategic judgements
- `summary()` on each report produces a human-readable text block
- Strategic interpretation ("level 2") is the future LLM advisor's job

---

## Evaluator Status & Validation Notes

### Military (`ck3/evaluators/military.py`)
**Validated against murchad.txt (1087.3.24) and Vratislav II 1066–1072**

- `RealmStrength` correctly separates:
  - `levy_capacity` — max levy from `landed_data.levy`
  - `maa_capacity` — computed as `strength - levy` (men-at-arms)
  - `total_troops` — current raised troops, summed from active army unit objects
  - `total_max` — combined maximum (from `strength`)
- `total_troops` is computed by iterating `gs.armies` and summing
  `gs.army_strength(army_id)["current"]` for armies owned by the character.
  **Not** from `landed_data.current_strength`, which equals `strength` (max) when
  no armies are deployed.
- Combat power is the game's internal metric; not directly visible to the player
  but directionally correct
- Knights are listed with prowess and approximate power (prowess × 100)

**Nearby Rulers section:**
- `NearbyRuler` dataclass and `nearby_rulers` field on `MilitaryReport`
- Covers five relationship categories: liege, direct vassals, allies, active war
  enemies, and geographic neighbors (zone 0–1, county+ tier only)
- Allies sourced from both active wars and `active_relations` alliance bonds
- Geographic neighbors capped at 30 in the summary (sorted by total strength
  descending); full list available in the dataclass
- Power values stored and displayed as integers (save file sometimes has floats)

**Known gaps:**
- No breakdown of current levy vs. current MaA (save doesn't store them separately)
- Neutral armies are omitted from the field army report (intentional — too noisy)

### Culture (`ck3/evaluators/culture.py`)
**Validated against murchad.txt (1087.3.24)**

Religion is one axis of culture; future work will add ethnicity/language groups
and cultural innovations.  Current content:

- Faith profiles include fervor, tenets, doctrines, religious head, title count,
  and top rulers
- Geographic zone filtering groups faiths into:
  - Local/nearby (full detail with rulers and tenets)
  - Continental (summary rows)
  - Global major (>50 titles, name + count only)
  - Global minor (omitted)
- Zone is computed from the player's capital kingdom → region, then
  `zone_between(player_region, faith_region)` using region adjacency graph
- `own_religion` uses `graphical_faith` as a proxy for religion family
  (e.g. `catholic_gfx`); true religion names require static game data files

**Known gaps:**
- `hostile` relation type removed; currently only "own", "same_religion", "other"
  — religious hostility would need game data files to compute
- Cultural group / language family not yet surfaced (save stores `culture` key
  per character and `culture_template` in cultures db — not yet parsed)

### Relationships (`ck3/evaluators/relationships.py`)
**Validated against murchad.txt (1087.3.24) and Vratislav II 1066–1072**

Supersedes `hierarchy.py`.  Covers nine sections:
1. **Position** — liege chain upward
2. **Vassals** — direct vassal contracts with levy/strength, faction flags
3. **Factions** — active factions targeting the player
4. **Alliances** — lateral alliances with bond count and mediator info
5. **Hooks** — favor hooks and house-head hooks held/held-on-player
6. **Family** — spouse(s), children, parents, dynasty prestige
7. **Court** — courtiers grouped by role (council, knight, court position)
8. **Personal Relations** — scripted bonds (friend, rival, lover, …)
9. **Notable Opinions** — significant temporary opinion modifiers

**Key data source quirks discovered:**
- Alliance `active_relations` creates derivative entries for mediating
  spouses/children — filter: only count if other party holds a county+ title
- A single marriage can produce multiple bond entries (intentional CK3 bookkeeping)
- Negotiated alliances detected when both `allied_through` chars are the principals
- `active_hook_0` held by `first`, `active_hook_1` by `second`

**Validated results (murchad.txt):**
- Independent ruler ✓
- 3 feudal vassals: Ruaidrí (d_connacht), Muiredach (c_desmond), Ólafr (c_ormond) ✓
- 2 alliances: William of England [2 bonds, via Prince William ↔ Princess Áine],
  Murchad mac Diarmait [c_dublin, negotiated] ✓
- Robin's favor hook on player (expires 1091.2.16) ✓

**Additional validated results (Vratislav II 1066–1072):**
- Theocracy vassal (bishop) identified correctly ✓
- Rival relationship surfaced ✓
- Faction members format change between saves handled: was flat `[int]`, became
  `[{'character': X, 'faction': Y}]` — normalised on read

**Known gaps:**
- Factions not yet validated (Murchad had none at this date)
- Sub-vassal counts and indirect vassal totals not yet surfaced
- Opinion scores not yet parsed (live in `raw["opinions"]` but structure not explored)

### Province Data (`ck3/province_data.py`)
Static game data loader used by `TerrainEvaluator`.  All caches are module-level
(populated lazily on first call).

- `load_province_terrain()` → `dict[int, str]` — map_province_id → terrain string
  - Source: `game/common/province_terrain/00_province_terrain.txt`
- `load_barony_provinces()` → `dict[str, int]` — barony_key → map_province_id
- `load_county_capitals()` → `dict[str, str]` — county_key → capital barony_key
  - Both sourced from `game/common/landed_titles/00_landed_titles.txt` in a
    single pass (capital = first `b_*` child within each `c_*` block)
- `WATER_TERRAIN = frozenset({"sea", "coastal_sea"})` — excluded from holding profiles
- Default terrain when a province is absent: `"plains"`

**ID systems:** CK3 uses two distinct province numbering systems.
  - Save-file title database IDs: sequential, save-specific
  - Map province IDs: static, from game data files
  The lookup chain is: `title_db_id → title.key (b_*) → barony_to_map_province → terrain_map`
  For county-seat titles (c_*), resolve through `county_capitals` first.

### Terrain (`ck3/evaluators/terrain.py`)
**Validated against Vratislav II 1066–1072**

Reports holding geography using authoritative CK3 static data (not inferred).

Key dataclasses: `HoldingProfile`, `DomainSummary`, `VassalProfile`, `TerrainReport`

- `HoldingProfile` fields: barony_key, county_key, holding_type, terrain,
  fort_level, development, development_progress, county_control, buildings,
  building_cats, special_features
- `DomainSummary` aggregates: type_counts, total/avg development, low_control
  holdings, terrain_counts, category_totals
- Vassal profiles include terrain and building summary for each direct vassal's domain
- Building categories mapped via `_BUILDING_CATEGORY` prefix dict:
  fortification, military, agriculture, commerce, resource, religious, urban, tribal

**Key implementation notes:**
- Domain list may contain duchy-tier (d_*) entries as seat titles — skipped in
  `_profile_one()`; deduplication guard on province_id prevents double-counting
  when duchy capital shares province with county capital
- County-seat titles (c_*) resolved through `county_capitals` map before barony
  province lookup
- Vassal profiles built by calling `contracts_for_liege()` and profiling each
  vassal's domain the same way as the player's

**Known gaps:**
- Building benefit values not yet extracted (only names/categories surfaced)
- Special features (wonders, holy sites) detection is heuristic — based on
  building key patterns, not game data

---

## Running the Report

```bash
python3 run_report.py sample-saves/extracted/<save>.txt
# explicit character ID:
python3 run_report.py sample-saves/extracted/<save>.txt 18269
# specific modules only:
python3 run_report.py sample-saves/extracted/<save>.txt --modules military
python3 run_report.py sample-saves/extracted/<save>.txt 18269 --modules culture relationships
```

Available modules: `military`, `culture`, `relationships`, `terrain` (default: all four).
Parse/load progress goes to stderr; report content to stdout.

---

## What To Work On Next

Suggested priorities (not binding):

- **Validate new saves**: Murchad saves 1069–1085, Brian II 1093 — run reports
  and spot-check against the game; Vratislav 1067 extracted but not yet reported on
- **Economy evaluator**: gold income, development, buildings — the third major
  pillar of CK3 gameplay alongside military and diplomacy
- **Opinion scores**: parse `raw["opinions"]` to surface which vassals like/
  dislike the player and why — important for predicting faction risk
- **Sub-vassals**: the current relationships report only shows direct vassals;
  a "realm tree" view would be more complete
- **Nearby ruler name encoding**: some names in the nearby-rulers section still
  show raw encoding (e.g. `HA_mA_lA_inen`) — their first_name goes through
  `char_label` but the title-key display is unaffected; review character coverage
- **LLM advisor layer**: feed evaluator output into Claude to generate
  strategic commentary — this is the long-term goal of the whole project
- **Assessments workflow**: `assessments/` directory holds written strategic
  analyses keyed to specific save snapshots; these are intended as context for
  the future LLM advisor layer
