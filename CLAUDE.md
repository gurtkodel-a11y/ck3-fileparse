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

## DLC Coverage

**Owned DLCs (as of 2026-06-25):** The Royal Court, Tours and Tournaments,
The Northern Lords, Wards and Wardens, Coronations, All Under Heaven, plus
whatever base-game content predates these.  `game/dlc_metadata/00_dlc_metadata.txt`
lists every DLC the *game itself* ships with — that file is not a record of what
the player owns, so don't treat its presence as confirmation of ownership.

**Status: mid-overhaul.** We are going through the codebase DLC-by-DLC to make
sure parsing/evaluation doesn't silently misread or skip fields introduced by
newer mechanics. This is in progress, not finished — if a report looks wrong
or a script throws an unexpected `KeyError`/falls into a generic "unknown"
bucket, **a missed DLC field is a likely first suspect**, especially for the
mechanics below. Treat this as a standing hypothesis to check when something
otherwise looks intractable, not just a one-time pass.

Known risk areas identified so far (not yet fixed — flagged for follow-up):

- **The Royal Court** — no top-level indices for `artifacts`, `inspirations`,
  or feast records in `ck3/gamestate.py`; `character.py` reads `court_data`
  but never reads artifact bonuses despite a comment implying it does.
- **The Northern Lords** — `ck3/evaluators/military.py` treats `raid_army` as
  a simple boolean; raid duration/target/loot fields aren't modeled.
- **Wards and Wardens** — `ward` exists in the personal-relations type set
  (`character.py`, `relationships.py`), but unknown/variant ward relation
  subtypes are silently dropped by the type filter rather than surfaced.
- **Coronations** — `legitimacy` is read with a safe fallback, but regalia
  ownership/quality and "uncrowned" ruler state are not read anywhere.
- **All Under Heaven** — `ck3/evaluators/base.py`'s `_contract_label()`
  hardcodes four vassal-contract government types (feudal/tribal/clan/republic);
  a new bureaucratic/Celestial-Empire government type would fall through to a
  generic `.title()` label instead of a proper one. `ck3/evaluators/history.py`'s
  `_WAR_TYPES`/`_PEACEFUL_TYPES` frozensets are similarly closed sets that a new
  title-transfer type (e.g. mandate-of-heaven related) could fall outside of.

When investigating a discrepancy against in-game behavior, check whether the
underlying save field is new/changed for one of these DLCs before assuming the
parser logic itself is wrong.

**Region/mechanic-specific deep dives live in `mechanics/`, not here** — load
the relevant file only when a save actually uses that mechanic, rather than
carrying the detail in this always-loaded file. Currently:
- `mechanics/japan_ritsuryo_soryo.md` — Ritsuryō/Sōryō government types, Noble
  Family titles (e.g. "the Kiyohara Family"), and the Domicile/manor mechanic.
  Relevant whenever a character's `landed_data.government` is
  `japan_administrative_government` or `japan_feudal_government`.

**Fixed during the playtest 4 (Japan) shakeout:**
- `ck3/names.py`'s `house_prefix_name()` crashed on procedurally-generated
  dynasty houses with a bare numeric `key` instead of a `house_*` string —
  now falls back gracefully.
- `ck3/culture_data.py`'s `tradition_label()` left internal DLC codenames
  (`tgp`, `mpo`, `ep1-4`, `fp1-5`, `ce1`) in tradition display names
  ("Tgp Imperial Peace" → "Imperial Peace").
- Title display across `ck3/evaluators/base.py` (`title_place`,
  `title_full_label`), `culture.py`, `military.py`, and `character.py`
  previously derived place names by guessing from the title *key*
  (`c_nf_kiyohara` → "Nf Kiyohara"). Procedurally-named/landless titles
  (clan-headship titles, generated noble-family titles — very common in
  this densely-populated, multi-region save) store their real name in
  `title_name_data.name` instead, which the key-guessing approach ignored
  entirely. All four now prefer the save's own name data when available
  (`c_nf_kiyohara` → "the Kiyohara Family"); this also fixed several
  previously-mislabeled non-Japan titles ("Hre" → "Holy Roman Empire").
  `gs.title_by_key()` was added to gamestate.py to support this.
  Remaining gap: `ck3/evaluators/relationships.py`'s vassal/ally/family
  title labels and the Chancellor advisor's raw alliance-title dump still
  use the old key-only path — lower exposure (most direct vassals/family
  hold ordinary landed titles) but not yet audited.

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

**Windows direct access:** On the gaming PC, live `.ck3` saves are at
`%USERPROFILE%\Documents\Paradox Interactive\Crusader Kings III\save games\`.
The 1.18+ format is a plain ZIP (after skipping the `SAV0` header), so
`zipfile.ZipFile` reads them directly — no extraction step needed.
Skip `autosave*.ck3` and any file whose embedded `gamestate` starts with
binary magic bytes (`SAV0`, `U1\x01`, `U1\x00`), which mark ironman saves.

---

## Codebase Map

```
parse_gamestate.py          Clausewitz tokeniser + iterative parser
run_report.py               CLI: parse a save, run selected evaluators, print report
run_council.py              CLI: parse a save, run selected council advisors, print briefs
run_latest.py               Windows convenience: finds the most recent non-ironman .ck3 in
                            %USERPROFILE%\...\save games\, extracts on-the-fly via zipfile,
                            and runs the full report — no separate extraction step needed.
                            Usage: python run_latest.py [--modules military] [--char ID]

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
  trait_data.py             Static trait loader: _parse_traits() single-pass → categories +
                            skill bonuses; load_trait_categories(), load_trait_skill_bonuses(),
                            trait_category(key), trait_skill_bonus(key)
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
    character.py            character_profile(gs, char_id) → CharacterProfile
    history.py              HistoryEvaluator(gs, since_date, char_id?) → SessionHistoryReport
                            Reconstructs major events from landed_titles history blocks.
                            CK3 saves do not store completed war records; title ownership
                            changes (conquest_claim, conquest, holy_war, faction_demand)
                            are the best available proxy. Confidence scales with cluster
                            size (titles sharing the same date + new holder). Epistemic
                            caveats baked in: conquest_claim identifies the claimant, not
                            necessarily the war leader; de jure cascades are not recorded.
    military.py             MilitaryEvaluator  → MilitaryReport
    culture.py              CultureEvaluator   → CultureReport
    relationships.py        RelationshipsEvaluator → RelationshipsReport
    terrain.py              TerrainEvaluator   → TerrainReport
    matchmaker.py           find_candidates(gs, char_id, **filters) → MatchmakerReport
                            Screens the save's unmarried population for betrothal/marriage
                            candidates. Filters: faith_mode, age_window, track (noble/
                            lowborn), max_zone, exclude_vices, require_virtue. Classifies
                            CK3 personality traits as virtue/vice (hardcoded; game files
                            don't tag this). Falls back to house-head for faith/culture
                            on unlanded characters. Uses geography.py zone system.
    carmen_sandiego.py      locate(gs, char_id) → CharacterLocation
                            "Where in the world is...?" — current location, imprisonment,
                            activity (hosting/attending + intent + host), and travel plan
                            (destination + ETA). Sources: alive_data.location,
                            involved_activity_data, gs.activities, gs.travel_plans.
    character_narrative.py  life_story(gs, char_id) → NarrativeReport
                            Personal-scale narrative: walks character_memory_manager and
                            renders a character's life as a chronological story (births,
                            deaths, marriages, rivalries, battles, imprisonments...).
                            Dead characters lose their own memories pointer; falls back
                            to scanning living characters' memories for ones naming the
                            dead person as a participant (e.g. a parent's relative_died).
                            See ideas/ideas.txt for the memory-decay follow-up.
                            *Naming note*: "character_narrative" = the Personal rung of a
                            broader multi-scale Narrative concept (Personal/Family/Court/
                            Holdings/Domain/Local/Continental/Global). Other rungs are
                            future work; "narrative" is reserved for the wider concept.

assessments/                Written strategic assessments + action plans (context for LLM advisor)
  archive/                  Retired playtests — pre-DLC-overhaul era (see "DLC Coverage" above)
    misc/                   Loose assessments predating the playtest folder structure
    playtest1/               Vratislav II of Bohemia — first run
    playtest2/               Vratislav II of Bohemia — second run (plans/ + plans/archive/)
    playtest3/               King Malcolm III of Scotland
  playtest4/                Toryo Takenori of the Kiyohara — active playtest (post-DLC-overhaul)
    plans/                  (empty — plans to be added as play proceeds)
  playtest5/                Vratislav II Přemyslid — DLC-overhaul re-run (active alongside 4)
    plans/                  1066-11-11.txt, 1068-04-10.txt, 1075-07-12.txt (and subsequent)

game/
  common/
    province_terrain/
      00_province_terrain.txt   map_province_id → terrain string (static CK3 data)
    landed_titles/
      00_landed_titles.txt      barony→province bridge + county capital lookup
    buildings/                  building definitions (loaded by province_data.load_building_categories())
    culture/cultures/           culture definitions (loaded by culture_data.load_culture_definitions())
    men_at_arms_types/          MaA type definitions (loaded by maa_data.load_maa_definitions())
    traits/
      00_traits.txt             All trait definitions: category, physical flag, skill bonuses
                                (loaded by trait_data._parse_traits())

sample-saves/               See sample-saves/README.md for the full data-hygiene convention.
  README.md                 Folder roles, retirement convention, naming convention
  playtestN/                Saves for an in-progress playtest; multiple can be active in parallel
  archive/<playtest-name>/  Retired playtest saves, named to match assessments/archive/<playtest-name>/
  validation/               Evaluator/parser test fixtures (murchad.txt, dunkeld.txt, etc.) —
                            not tied to a playtest; referenced by the "Validated against ..." notes below
  extracted/                Gitignored, regenerable plaintext cache (not part of the archive/validation split)
```

---

## Key Design Decisions

### Parser (`parse_gamestate.py`)
- Iterative stack-based parser to avoid Python recursion limits on large saves
- Duplicate keys in a block are merged into lists (common in Clausewitz format)
- Unquoted atoms are coerced to `int` or `float` where possible
- **`parse()` takes file TEXT content, not a filename.** Pass
  `Path(f).read_text(encoding='utf-8', errors='ignore')` — passing a raw filename
  string returns an empty dict silently (the string doesn't match Clausewitz format).
  `run_latest.py` and `run_report.py` handle this correctly; be careful in ad-hoc scripts.

### GameState (`ck3/gamestate.py`)
- All indices are built lazily on first call to `build_indices()`
- Indices built: titles-by-holder, units-by-owner, wars-by-character,
  vassal-contracts-by-liege/vassal, title-key-to-kingdom
- The `vassal_contracts` data lives at `raw["vassal_contracts"]["database"]`
  (one level deeper than the top-level key)
- Active relations live as a flat list at `raw["relations"]["active_relations"]`
- Multiplayer saves: `played_character` key appears twice → parser merges to list;
  handled with `isinstance(_played, list)` guard

**Active wars raw structure** (`raw["wars"]["active_wars"]`):
- This is a **dict** with integer war IDs as string keys, **not a list**.
  Iterate with `.items()`; values are either `'none'` (string) or a war dict.
- War dict keys: `attacker`, `defender`, `start_date`, `casus_belli`,
  `battle_results`, `called_to_war`, `name`, (optional) `reached_max_score_date`
- `attacker` / `defender` sub-dicts: each has a `participants` list; each
  participant has `{character, date, casualties, ...}`; the first participant
  is typically the war leader / main character.
- `called_to_war`: list of char IDs summoned as allies (by either side).
- `casus_belli`: dict with `type` key (e.g. `claimant_faction_war`,
  `peasant_war`, `claim_cb`, `independence_faction_war`, etc.)
- `battle_results`: list of battle records, each with sub-dicts
  `attacker`/`defender` (containing `commander`, `size`, `casualties`) plus
  `province`, `war_score` (cumulative after this battle), `attacker_won`,
  `attacker_initiated`.
- The `MilitaryEvaluator` only surfaces wars for the *played character*; vassal
  wars appear in `active_wars` but are not highlighted in any current report.

### Names (`ck3/names.py`)
- CK3 encoding: `X_` (uppercase + underscore) = accented lowercase; `_XXXX` = CJK
  hex codepoint; remaining `_` = word separator
- Single-letter diacritics: `A_→á  E_→é  I_→í  O_→ó  U_→ú  C_→ç  N_→ñ
  Z_→ź  S_→š  R_→ř  L_→ł`
- Double-letter carons (háček): `CC_→č/Č  EE_→ě/Ě` — regex puts these **first**
  so they win over the single-letter `C_` and `E_` forms
- Capitalisation rule: diacritic is uppercase when the match starts at position 0
  or immediately follows a space or hyphen (word-start detection)
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

**Mercenaries (known gap, surfaced playtest5):**
- Active mercenary contracts (`mercenary_company_manager.mercenary_companies`,
  filtered by `hired_by == char_id`) are NOT currently surfaced in the report.
- The underlying `landed_data.strength`/`power` fields the report reads DO
  include currently-hired mercenary capacity, so the "Total max / Combat power"
  numbers already reflect active contracts — but the report gives no indication
  of this, making it impossible to tell from the report alone which fraction of
  "own forces" is a temporary rented asset about to lapse.
- Enhancement needed: add an "Active Mercenary Contracts" section showing hired
  company size, type, and `hired_until` date so readers can see what's temporary.

**War retargeting (documented in module, surfaced playtest5):**
- Winning a claim war for a title does NOT resolve other parties' independent
  claim wars over the same title — they retarget to the new holder. The report
  reflects this correctly (a new war entry appears) but a future enhancement
  could proactively flag "this war's target recently changed hands" by cross-
  referencing `active_wars`'s targeted_titles against recent title history.
  Documented in the `military.py` module docstring and `ActiveWar` dataclass.

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

**Bug fixed (playtest5, 1075):** `_char_location()` was labelling any landed
character as `"own_realm"` simply for holding a title, even fully independent/
foreign rulers. Consequence: independent dukes who became personal rivals (e.g.
Otakar of Styria, Ordulf of Angria) appeared as "own realm" rivals in the report,
implying they were Bohemian vassals when they weren't. Fixed: `_char_location()`
now walks the vassal-contract liege chain back to the player before asserting
"own_realm"; added a `"foreign_ruler"` category for landed characters who don't
appear in that chain. Both display-label dicts updated to render it as "foreign
ruler".

**Known gaps:**
- Factions not yet validated (Murchad had none at this date)
- Sub-vassal counts and indirect vassal totals not yet surfaced
- Opinion scores not yet parsed (`raw["opinions"]` uses `owner`/`target` field
  names, not `first`/`second` — confirmed structure in playtest5)

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

### Character Profile (`ck3/evaluators/character.py`)
**Validated against Playtest 2 cast, Vratislav II 1066.10.5**

Standalone function (not a class-based evaluator) that works for any character ID,
not just the played character.  Designed as a building block for the narrative
tooling layer.

```python
from ck3.evaluators.character import character_profile
profile = character_profile(gs, char_id=32778)
print(profile.summary())
```

**`CharacterProfile` fields:**

*Intrinsic (identity, vitals, skills, traits):*

| Field | Type | Notes |
|-------|------|-------|
| `char_id` | `int` | |
| `name` | `str` | decoded via `decode_name()` |
| `birth_date` | `str` | `"YYYY.M.D"` |
| `age` | `int` | completed years at `gs.date` |
| `gender` | `str` | `"male"` \| `"female"` |
| `is_alive` | `bool` | |
| `death_date` | `str` | empty if alive |
| `health` | `float` | raw 0–10 value; `.health_label` → prose |
| `fertility` | `float` | |
| `faith` | `str` | humanised tag, e.g. `"Catholic"` |
| `culture` | `str` | display name, e.g. `"Czech"` |
| `skills` | `dict[str,int]` | **base** values from save (`dip mar stew int lea prow`) |
| `effective_skills` | `dict[str,int]` | base + education + trait bonuses (excl. perks/artifacts) |
| `education_trait` | `str\|None` | `"education_stewardship_5"` etc.; None until adult |
| `personality_traits` | `list[str]` | `category=personality` or `childhood` |
| `lifestyle_traits` | `list[str]` | `category=lifestyle` (perk-tree rewards) |
| `commander_traits` | `list[str]` | `category=commander` or `winter_commander` |
| `physical_traits` | `list[str]` | `physical=yes` in game file (congenital/body traits) |
| `other_traits` | `list[str]` | health, fame, court_type, unknown |
| `focus` | `str\|None` | child education focus OR adult lifestyle focus key |
| `perks` | `list[str]` | unlocked lifestyle perk keys |
| `languages` | `list[str]` | `language_*` keys |

*Extrinsic — physical situation (alive characters only; dead characters get zero/empty):*

| Field | Type | Notes |
|-------|------|-------|
| `location_province_id` | `int\|None` | map-province ID from `alive_data.location.location` |
| `location_name` | `str` | decoded county (or barony) name at current location |
| `is_imprisoned` | `bool` | `alive_data.prison_data` present |
| `prison_type` | `str\|None` | `"house_arrest"` \| `"dungeon"` \| … |
| `imprisoner_id` | `int\|None` | char_id of the imprisoner |
| `at_activity` | `bool` | currently at an event/activity |

*Extrinsic — resources:*

| Field | Type | Notes |
|-------|------|-------|
| `gold` | `float` | `alive_data.gold.value` |
| `prestige_currency` | `float` | spendable prestige (`alive_data.prestige.currency`) |
| `prestige_accumulated` | `float` | lifetime total (`alive_data.prestige.accumulated`) |
| `piety_currency` | `float` | |
| `piety_accumulated` | `float` | |
| `dread` | `float` | from `landed_data.dread`; rulers only |
| `legitimacy` | `float` | newer DLC field; 0.0 if absent |

*Extrinsic — domain & positions:*

| Field | Type | Notes |
|-------|------|-------|
| `domain_title_keys` | `list[str]` | title keys of directly held titles (from `landed_data.domain`) |
| `realm_capital_key` | `str\|None` | key of the realm capital title |
| `council_role` | `str\|None` | `"Chancellor"` \| `"Marshal"` \| `"Steward"` \| `"Spymaster"` \| `"Court Chaplain"` \| `"Consort (Council)"` |
| `council_employer_id` | `int\|None` | char_id of the liege whose council they serve |
| `court_position_types` | `list[str]` | court position keys from `court_positions.database` |
| `heir_id` | `int\|None` | primary heir from `landed_data.succession[0]` |

*Extrinsic — relationships (brief; full detail in RelationshipsEvaluator):*

| Field | Type | Notes |
|-------|------|-------|
| `liege_id` | `int\|None` | direct liege from vassal contract |
| `liege_name` | `str` | first name of liege |
| `liege_title_key` | `str\|None` | highest title key held by liege |
| `primary_spouse` | `FamilyRef\|None` | `FamilyRef(char_id, name)` |
| `children` | `list[FamilyRef]` | all children from `family_data.child` |
| `father` | `FamilyRef\|None` | |
| `mother` | `FamilyRef\|None` | |
| `personal_relations` | `list[PersonalRelation]` | scripted bonds (friend/rival/lover/nemesis/…); deduped |

*Extrinsic — community leaders:*

| Field | Type | Notes |
|-------|------|-------|
| `dynasty_head_id` | `int\|None` | head of the character's dynasty house |
| `faith_head_id` | `int\|None` | char who currently holds the faith head title |
| `faith_head_title_key` | `str\|None` | e.g. `"k_papal_state"` |
| `culture_head_id` | `int\|None` | character designated as culture head (`culture.head`) |

**Data sources:**
- Location: `alive_data.location.location` is a **map-province ID** (not a title DB ID).
  Resolved via `province_data.load_barony_provinces()` reverse-map → county name.
- Council role: `court_data.council_task` → `council_task_manager.active[id].type` →
  role label.  Task type → role mapping in `_COUNCIL_TASK_LABELS` / `_COUNCIL_TASK_PREFIXES`.
- Court positions: `court_positions.database` entries where `employee == char_id`.
- Faith/culture leader fallback: unlanded characters often lack stored faith/culture;
  falls back to the dynasty house head's values for both display and leader lookup.
- Personal relations deduplicated by `(other_id, relation_type)` — the same bond
  appears in both the owner-side and target-side opinion entries.

**GameState helpers added:**
- `gs.council_task_for_char(char_id)` → `dict | None` — the `council_task_manager` record
- `gs.court_positions_for_char(char_id)` → `list[dict]` — court position entries where employee
- `gs.opinions_list()` → `list[dict]` — cached `opinions.active_opinions`
- `gs.council_tasks` — direct reference to `council_task_manager.active` dict
- `gs.court_positions_db` — direct reference to `court_positions.database` dict
- `gs.activities` — `activity_manager.database` dict (activity_id → record with
  `type`, `host`, `attending` list, `creation_date`, `active_start_date`,
  phase info, and per-attendee `variables`). Used by `carmen_sandiego.py`.
- `gs.travel_plans` — `travel_plans.database` dict (plan_id → record with
  `data.data.owner`, `data.data.activity`, `data.destinations` list each having
  `province`, `arrival_date`, `estimated_arrival_date`). Used by `carmen_sandiego.py`.
- `gs.memories` — `character_memory_manager.database` dict (memory_id → record with
  `type`, `creation_date`, `end_date`, `participants`). Memories decay ~130 years
  after creation; dead characters lose their personal `alive_data.memories` pointer
  entirely. Used by `character_narrative.py`.
- `gs.claims_held_by(char_id)` → `list[dict]` — titles this character holds a claim
  on, read from `alive_data.claim` (each: `{title_id, title_key, title, pressed}`).
  CK3 does not log claim-grant events persistently anywhere in the save — no
  provenance trail, only the resulting claim entry.

**Effective skill computation (`trait_data.py`):**
- `_parse_traits()` — single pass over `game/common/traits/00_traits.txt`; returns
  `(categories, skill_bonuses)` where `skill_bonuses = {trait_key: {skill_key: int}}`
- Skill bonus keys in the file: `diplomacy martial stewardship intrigue learning prowess`
  (collected only at depth 1; nested `culture_modifier` blocks are ignored)
- `physical = yes` flag overrides the file-level `category` with `"physical"` —
  matches the in-game "Physical" trait group shown to the player
- Effective = base + Σ bonuses across education_trait + all non-education traits
- **Not included**: lifestyle perk bonuses, equipped artifacts, council positions,
  buildings, realm laws, or temporary event modifiers

**Known gaps:**
- Perk bonus values not yet extracted from perk tree files
- Artifact skill bonuses not surfaced
- Dead characters return a minimal profile (skills, traits from save; no alive_data fields)
- Activity type not decoded (only presence/absence detected via `activity_data`)
- `renown` not separately tracked (accessible via `gs.dynasties[dyn_id].prestige.accumulated`)

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

**Windows (gaming PC) — convenience workflow:**

```powershell
# Run on the most recent save directly from the CK3 save folder (no extraction step):
python run_latest.py
python run_latest.py --modules military relationships
python run_latest.py --char 32778

# Redirect output to a file for easier reading:
$env:PYTHONIOENCODING='utf-8'; python run_latest.py > report.txt
```

**Targeted queries (all read the most recent save automatically):**

```bash
# Betrothal/marriage candidate screen
python run_matchmaker.py --char 37766
python run_matchmaker.py --char 37766 --track noble --max-zone 1
python run_matchmaker.py --char 37766 --faith same_religion --allow-vices

# Character location, activity, and travel
python run_carmen_sandiego.py --char 32778 31798 29180

# Personal-scale life story (births, deaths, marriages, battles, rivalries…)
python run_character_narrative.py --char 32778
python run_character_narrative.py --char 38396 --minor   # include flavor events
```

**Windows encoding note:** The default Windows console encoding (cp1252) cannot
represent Czech characters (ř, š, č, etc.) and will raise `UnicodeEncodeError`.
Fix: set `$env:PYTHONIOENCODING='utf-8'` in PowerShell before running, or redirect
output to a file (which triggers UTF-8 automatically). `run_latest.py` calls
`sys.stdout.reconfigure(encoding='utf-8')` at startup and handles this automatically.

---

## What To Work On Next

Suggested priorities (not binding):

**DLC overhaul (see "DLC Coverage" above) — active:**
- Walk through the known risk areas listed there (Royal Court artifacts,
  Northern Lords raiding, Wards and Wardens relation types, Coronations
  regalia, All Under Heaven government/title-transfer types) and bring each
  up to the same level of coverage as the existing evaluators
- New save files from these DLCs are the best test fixtures — diff evaluator
  output against actual in-game state the same way we validate other modules

**Playtest 5 — Vratislav II Přemyslid, King of Bohemia (active, DLC-overhaul re-run):**
- Saves: `sample-saves/playtest5/` (1066–1077 checkpoints)
- Current state as of 1077.7.14: King of Bohemia (crowned ~1072), Duke of Meissen
  via conquest (granted to Benno → now Heimrich von Lóningen after Benno's death),
  Lausitz claim still held and pressed, 4 alliances (Bavaria via Judita↔Siegfried,
  Schmalkalden via Břetislav↔Hildegard, Ota/Konrád negotiated). Dedo (Lausitz)
  growing in power; Meissen's contribution to realm levy reduced after Benno's death
  and succession reorganization. Active rivals: Jaromír (personal), Otakar (Styria),
  Ordulf (Angria/Westfalen). Anselmo (Pope) -60 opinion, ongoing.
- Plans: `assessments/playtest5/plans/` (1066-11-11, 1068-04-10, 1075-07-12 plan files)
- Running concurrently with playtest4 (Japan)

**Playtest 4 — Toryo Takenori of the Kiyohara, Duke of Mutsu, Japan (active):**
- Saves: `sample-saves/playtest4/` (Toryo_Kiyohara_Takenori_of_the_Kiyohara_Ichizoku_1066_09_15.ck3)
- First post-DLC-overhaul save (Royal Court, Northern Lords, Wards and Wardens,
  Coronations, All Under Heaven content all in scope) — see "DLC Coverage" above
- Plans folder at `assessments/playtest4/plans/` is ready for action plans as play proceeds
- No assessment written yet — playtest just started; paused while playtest5 began

**Playtests 1–3 — archived (pre-DLC-overhaul era):**
- Vratislav II of Bohemia (two runs) and King Malcolm III of Scotland; see
  `assessments/archive/` and `sample-saves/archive/`

**Evaluator gaps:**
- **Economy evaluator**: gold income, development, buildings — the third major
  pillar of CK3 gameplay alongside military and diplomacy
- **Opinion scores**: parse `raw["opinions"]` to surface which vassals like/
  dislike the player and why — important for predicting faction risk
- **Sub-vassals**: the current relationships report only shows direct vassals;
  a "realm tree" view would be more complete

**General:**
- **Validate new saves**: Murchad saves 1069–1085, Brian II 1093 — run reports
  and spot-check against the game
- **Nearby ruler name encoding**: some names in the nearby-rulers section still
  show raw encoding (e.g. `HA_mA_lA_inen`) — their first_name goes through
  `char_label` but the title-key display is unaffected; review character coverage
- **LLM advisor layer**: feed evaluator + character profile output into Claude to
  generate strategic and narrative commentary — the long-term goal of the project
- **Assessments workflow**: each `assessments/playtest*/` directory holds both
  strategic write-ups (assessment files) and action plans (`plans/` subfolder),
  co-located per playtest — together the intended context corpus for the LLM advisor
