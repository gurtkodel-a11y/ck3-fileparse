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

Layers 1–3 are complete.  Layer 4 (Evaluate) exists as plain-text summaries
from each evaluator's `summary()` method.  Layer 5 (Advise) is the council
advisor layer in `ck3/advisors/`, which interprets evaluator output and
produces strategic briefs structured around the five CK3 council roles.

---

## Save File Pipeline

```
[Gaming PC]  scripts/watch_autosaves.py
                 ↓  copies new manual .ck3 saves to sample-saves/
[Mac]        scripts/extract_snapshots.py
                 ↓  unzips old-format saves; invokes ck3-melt for binary saves
             sample-saves/extracted/*.txt   ← plaintext Clausewitz format
                 ↓
             parse_gamestate.parse()        ← tokeniser + iterative parser
                 ↓
             ck3.gamestate.GameState        ← structured model + indices
                 ↓
             ck3.evaluators.*              ← domain evaluators (level 1: facts)
                 ↓
             ck3.advisors.*               ← council advisors (level 2: interpretation)
```

**Save formats encountered:**
- Old format (pre-1.13): ZIP containing a plaintext `gamestate` entry
- New format (1.18+): `SAV0` plaintext header (~32 KB) followed by an embedded
  ZIP archive containing a plaintext `gamestate` entry — **no ck3-melt needed**;
  `scripts/extract_snapshots.py` detects this automatically and extracts directly

All `.ck3` files in `sample-saves/` are the 1.18+ header+ZIP format and have
been extracted to `sample-saves/extracted/`.  The extracted `.txt` files are
gitignored (too large to push); they live only on the local Mac.

---

## Codebase Map

```
parse_gamestate.py          Clausewitz tokeniser + iterative parser
run_report.py               CLI: parse a save, run selected evaluators, print report
run_council.py              CLI: parse a save, run selected council advisors, print briefs

scripts/
  watch_autosaves.py        Run on gaming PC: watches for new saves, copies to sample-saves/
  extract_snapshots.py      Run on Mac: extracts .ck3 save files to plaintext

ck3/
  __init__.py
  gamestate.py              GameState wrapper + all lookup indices
  geography.py              Region definitions + interaction-proximity zones
  names.py                  Name decoding, house labels, ordinals, char_label()
  province_data.py          Static game data loader: terrain + barony→province bridge
  culture_data.py           Static culture definitions loader: CultureDef, pillar/tradition labels,
                            RELIGION_FAMILY_LABELS
  maa_data.py               Static MaA type definitions loader: MaaDef, maa_class_label(),
                            load_maa_definitions() — reads game/common/men_at_arms_types/
  advisors/
    __init__.py             Council class — lazy report cache + advisor access
    base.py                 BaseAdvisor, Priority dataclass, shared helpers
    marshal.py              MarshalAdvisor   → MarshalBrief
    chancellor.py           ChancellorAdvisor → ChancellorBrief
    steward.py              StewardAdvisor   → StewardBrief
    councilor.py            CouncilorAdvisor → CouncilorBrief
    spymaster.py            SpymasterAdvisor → SpymasterBrief
  evaluators/
    __init__.py
    base.py                 Shared utilities: _ensure_list, _tier_order, _contract_label,
                            _participants, title_place(), title_full_label()
    military.py             MilitaryEvaluator  → MilitaryReport
    culture.py              CultureEvaluator   → CultureReport
    relationships.py        RelationshipsEvaluator → RelationshipsReport
    terrain.py              TerrainEvaluator   → TerrainReport

assessments/                Written strategic assessments (context for LLM advisor)
  Vratislav_II_1066-09-20_assessment.txt
  Vratislav_II_1072-09-13_assessment.txt
  Vratislav_II_1083-09-14_assessment.txt
  Vratislav_II_1088-01-02_assessment.txt

game/
  common/
    province_terrain/
      00_province_terrain.txt   map_province_id → terrain string (static CK3 data)
    landed_titles/
      00_landed_titles.txt      barony→province bridge + county capital lookup
    buildings/                  building definitions (loaded by province_data.load_building_categories())
    culture/cultures/           culture definitions (loaded by culture_data.load_culture_definitions())
    men_at_arms_types/          MaA type definitions (loaded by maa_data.load_maa_definitions())

sample-saves/
  extracted/                16 saves extracted to plaintext (gitignored):
    Duke_Vratislav_II_of_Bohemia_1066_09_15.txt   (62 MB)   char (use default)
    Duke_Vratislav_II_of_Bohemia_1066_09_20.txt   (62 MB)   char (use default)
    Duke_Vratislav_II_of_Bohemia_1067_01_13.txt   (68 MB)   char (use default)
    Duke_Vratislav_II_of_Bohemia_1072_09_13.txt   (89 MB)   char (use default)
    King_Vratislav_of_Bohemia_1083_09_14.txt      (110 MB)  char (use default)
    King_Vratislav_of_Bohemia_1088_01_02.txt      (118 MB)  char (use default)
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
**Validated against murchad.txt (1087.3.24) and Vratislav II 1066–1088**

- `RealmStrength` correctly separates:
  - `levy_capacity` — max levy from `landed_data.levy`
  - `maa_capacity` — computed as `strength - levy` (men-at-arms)
  - `total_troops` — current raised troops, summed from active army unit objects
  - `total_max` — combined maximum (from `strength`)
  - `maa_regiments` — list of player's MaA regiments with type stats from game files
- `total_troops` is computed by iterating `gs.armies` and summing
  `gs.army_strength(army_id)["current"]` for armies owned by the character.
  **Not** from `landed_data.current_strength`, which equals `strength` (max) when
  no armies are deployed.
- Combat power is the game's internal metric; not directly visible to the player
  but directionally correct
- Knights are listed with prowess and approximate power (prowess × 100)

**MaA Regiments (new):**
- Sourced from `gs.regiments` — filter by `r.get('owner') == char_id` and `r.get('type')` present
- Each regiment: `{key, maa_class, class_label, size, damage, toughness, pursuit, screen, terrain_bonus}`
- `terrain_bonus` is a `dict[terrain, dict[stat, int]]` from static game data
- Displayed in summary with damage modifier per terrain type for tactically relevant bonuses
- Regiment type → `maa_data.MaaDef` lookup via `load_maa_definitions()` (109 types from 10 files)
- Unknown types surface with class "unknown" and zero stats (not silently dropped)
- `maa_data.maa_class_label()` humanises class keys: "heavy_infantry" → "Heavy Infantry"

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
**Validated against Vratislav II 1083 and Murchad 1080**

Now covers both culture identity and faith.  Static data loaded from
`ck3/culture_data.py` (236 cultures from `game/common/culture/cultures/*.txt`).

**Culture section (new):**
- `own_culture_template` resolved from `character.culture` → `culture_manager.cultures[id].culture_template`
- Pillars: `language`, `heritage`, `ethos`, `martial_custom`, `head_determination` — sourced
  directly from the save's culture record (already embedded, no game-file lookup needed)
- `own_traditions`: list of tradition keys, displayed via `tradition_label()` from `culture_data.py`
- `own_culture_era`: derived from `culture_era_data` — last era with `left` key is graduated; the
  next era is current; falls back to last entered if all completed
- `CultureProfile` per culture: template, name, language, heritage, ethos, traditions, era,
  relation (same_culture/same_heritage/same_language/other), titles_held, rulers, zone, head
- Geographic zone filtering: local/nearby (full detail), continental (summary), global major (≥20 titles)
- `RELIGION_FAMILY_LABELS` maps `rf_*` keys to human names (Abrahamic, Eastern/Dharmic, etc.)

**Faith section (unchanged from before):**
- Faith profiles with fervor, tenets, doctrines, religious head, title count, top rulers
- Zone-filtered display (local/nearby full detail, continental summary, global major >50 titles)

**Known gaps:**
- `hostile` relation type not yet computed (would need faith doctrine cross-reference)
- Culture hybridisation / divergence not surfaced (save has the data; not yet parsed)

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

- `HoldingProfile` fields: barony_key, county_key, barony_name, county_name,
  holding_type, terrain, fort_level, development, development_progress,
  county_control, buildings, building_cats, special_features
  - `barony_name`/`county_name`: decoded display names from `title_name_data.name`
    (falling back to key-stripping)
- `DomainSummary` aggregates: type_counts, total/avg development, low_control
  holdings, terrain_counts, category_totals
- Vassal profiles include terrain and building summary for each direct vassal's domain
- Building categories sourced from `province_data.load_building_categories()`:
  fortification, military, agriculture, commerce, resource, religious, urban, tribal,
  administrative, duchy_capital, special

**Public query API on `TerrainReport`** (for targeted follow-up after the summary):
- `holdings_by_terrain(terrain)` → `list[HoldingProfile]`
- `holdings_by_type(holding_type)` → `list[HoldingProfile]`
- `holdings_with_category(category)` → `list[HoldingProfile]`
- `special_holdings()` → `list[HoldingProfile]`  (holdings with `points_of_interest`)
- `holding_detail(barony_key)` → `HoldingProfile | None`
- `vassal_profile(char_id)` → `VassalProfile | None`

**Public method on `TerrainEvaluator`**:
- `vassal_holdings(vassal_id)` → `list[HoldingProfile]` — per-holding detail for
  one vassal (the report carries only aggregate `VassalProfile` stats)

**Module-level standalone utilities** (no `GameState` needed; pure static data;
intended as building blocks for `geography.py` path/travel calculations):
- `terrain_for_key(key)` — resolves a `b_*` or `c_*` title key to a terrain string
- `terrain_summary(keys)` — terrain-type counts for a list of barony/county keys;
  excludes water terrain

**Key implementation notes:**
- Domain list may contain duchy-tier (d_*) entries as seat titles — skipped in
  `_profile_one()`; deduplication guard on province_id prevents double-counting
  when duchy capital shares province with county capital
- County-seat titles (c_*) resolved through `county_capitals` map before barony
  province lookup
- Vassal profiles built by calling `contracts_for_liege()` and profiling each
  vassal's domain the same way as the player's
- `special_features` sourced from `province.points_of_interest` (save field)

**Known gaps:**
- Building benefit values not yet extracted (only names/categories surfaced)
- Special features list is whatever the save records in `points_of_interest` —
  not cross-referenced against game data (wonders, holy sites may appear as raw keys)

---

## Advisor Layer (`ck3/advisors/`)

Level-2 analysis: interprets evaluator output and produces strategic briefs
structured around the five CK3 council roles.

### Design

- **`Council`** (`__init__.py`) — central hub; owns `GameState` + `char_id`;
  lazily builds and caches all four evaluator reports so multiple advisors
  share them without re-computing.
- **`BaseAdvisor`** (`base.py`) — common interface: `advise()` returns a brief
  dataclass with a `summary()` method; shared helpers (`_power_label`,
  `Priority` dataclass with `urgency` ∈ high/medium/low).
- Each advisor pulls from the reports it needs and uses query APIs (e.g.
  `terrain_report.holdings_by_terrain()`) for targeted follow-up.
- Output dataclasses carry structured fields for programmatic access **and**
  a `summary()` that produces narrative prose (contrast with evaluators, which
  produce tabular fact summaries).

### Advisors

| Role | Class | Reports used | Focus |
|------|-------|-------------|-------|
| Marshal | `MarshalAdvisor` | Military, Terrain | Power posture, threats, wars, knights, defensibility |
| Chancellor | `ChancellorAdvisor` | Relationships, Military, Culture | Vassals, alliances, external relations, hooks, heritage affinities |
| Steward | `StewardAdvisor` | Terrain | Domain dev, building gaps, control, vassal domain summary |
| Councilor | `CouncilorAdvisor` | Culture | Faith fervor, nearby hostile/pagan faiths, holy wars |
| Spymaster | `SpymasterAdvisor` | Relationships | Hook inventory, enemies, crime opinions, factions |

### Output structure

Each `*Brief` dataclass holds:
- Structured fields (for programmatic access or LLM context injection)
- `observations: list[str]` — synthesised analytical notes
- `priorities: list[Priority]` — ranked actionable items with urgency tags
- `summary() -> str` — human-readable narrative brief

### Known gaps / future work

- Advisors currently work from top-level report data; deeper targeted queries
  (e.g. "which specific vassal to prioritise?", "what building to build next
  and where?") are possible by adding query calls but not yet written
- No cross-advisor synthesis — each brief is independent; a future `council.full_brief()`
  could identify conflicts and consensus across roles
- MarshalAdvisor does not yet reference `own_armies` / `enemy_armies` during
  active wars (those fields exist in `MilitaryReport`)

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

```bash
# Council advisor briefs (level 2)
python3 run_council.py sample-saves/extracted/<save>.txt
python3 run_council.py sample-saves/extracted/<save>.txt 18269
python3 run_council.py sample-saves/extracted/<save>.txt --advisors marshal chancellor
```

Available advisors: `marshal`, `chancellor`, `steward`, `councilor`, `spymaster` (default: all five).

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
