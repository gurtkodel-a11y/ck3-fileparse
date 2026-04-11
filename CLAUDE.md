# CK3 Fileparse — Project Guide

## Goal

Build a Python toolkit that reads Crusader Kings III save files and produces
accurate, human-readable analyses of the game state.  The immediate use case
is the player comparing the tool's output against their own in-game knowledge
to validate accuracy — but the longer-term vision is an AI advisor layer that
can reason about the game state and offer strategic commentary.

The project proceeds in layers:

1. **Parse** — convert the raw Clausewitz text format into Python dicts
2. **Model** — wrap the parsed data in a structured `GameState` object with
   lookup indices
3. **Evaluate** — domain-specific modules that extract and organise
   meaningful facts from `GameState` (military, religion, diplomacy, etc.)
4. **Report** — human-readable summaries of evaluator output, eventually
   feeding into an LLM advisor

Only layers 1–3 are complete.  Layer 4 exists as plain-text summaries
produced by each evaluator's `summary()` method.  The LLM advisor layer has
not yet been started.

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
- New format (1.13+): binary token format; requires `ck3-melt` from
  https://github.com/rakaly/ck3-save/releases to convert to plaintext

The two `.txt` files in `sample-saves/` (`dunkeld.txt`, `murchad.txt`) were
added directly from ZIP saves.  All `.ck3` files in `sample-saves/` are new
binary format and still need extraction.

---

## Codebase Map

```
parse_gamestate.py          Clausewitz tokeniser + iterative parser
run_report.py               CLI: parse a save, run all evaluators, print report

ck3/
  __init__.py
  gamestate.py              GameState wrapper + all lookup indices
  geography.py              Region definitions + interaction-proximity zones
  evaluators/
    __init__.py
    military.py             MilitaryEvaluator  → MilitaryReport
    religion.py             ReligionEvaluator  → ReligionReport
    hierarchy.py            HierarchyEvaluator → HierarchyReport

sample-saves/
  *.ck3                     Binary saves (need ck3-melt to extract)
  dunkeld.txt               Extracted plaintext — Malcolm III of Scotland, 1066
                            (actually binary U1 format — NOT yet parseable)
  murchad.txt               Extracted plaintext — High King Murchad of Ireland,
                            1087.3.24 — the primary test save
  extracted/                (empty — binary saves not yet extracted)
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
**Validated against murchad.txt (1087.3.24)**

- `RealmStrength` correctly separates:
  - `levy_capacity` — max levy from `landed_data.levy`
  - `maa_capacity` — computed as `strength - levy` (men-at-arms)
  - `total_troops` — current raised troops (levy + MaA combined, from `current_strength`)
  - `total_max` — combined maximum (from `strength`)
- Troop count validated: 1,757 raised of 1,806 max ✓
- Combat power (41,520) is the game's internal metric combining troop power
  with various bonuses; not directly visible to the player but directionally correct
- Knights are listed with prowess and approximate power (prowess × 100)
- Character names with special characters (Ólafr, Ruaidhrí, etc.) show garbled
  due to encoding in the save; known issue, not yet fixed

**Known gaps:**
- No breakdown of current levy vs. current MaA (save doesn't store them separately)
- Neutral armies are omitted from the report (intentional — too noisy)

### Religion (`ck3/evaluators/religion.py`)
**Validated against murchad.txt (1087.3.24)**

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
- Orthodox landing as "nearby" (via Byzantium → Balkans → Western Europe → 2
  hops from British Isles) is arguably correct for 1087 but worth watching
- `hostile` relation type was removed; currently only "own", "same_religion",
  "other" — religious hostility would need game data files to compute

### Hierarchy (`ck3/evaluators/hierarchy.py`)
**Validated against murchad.txt (1087.3.24)**

Covers four sections:
1. **Position** — liege chain from player to the top independent ruler
2. **Vassals** — direct vassal contracts with contract type, titles, military
   contribution, and faction threat flag
3. **Alliances** — lateral alliances with bond count and mediator info
4. **Hooks** — favor hooks and house-head hooks held/held-on-player

**Key data source quirks discovered:**
- `vassal_contracts` is nested: `raw["vassal_contracts"]["database"]`
- Alliance data in `active_relations` creates **derivative entries** for the
  mediating spouses/children in addition to the main ruler-to-ruler entry.
  Filter: only count an alliance if the other party holds at least a county-
  level title.  Unlanded "allies" are mediators, not allied rulers.
- A single marriage can produce **multiple bond entries** in the same alliance
  list (seen as 2 identical entries for the Murchad–William alliance).  This
  appears to be intentional CK3 bookkeeping; we track and display the bond
  count rather than collapsing it.
- Negotiated (non-marriage) alliances are detected when both `allied_through`
  characters are the principals themselves.
- `active_hook_0` is held by `first`, `active_hook_1` by `second` in a
  relation entry.
- House-head hooks (permanent, expiry 9999.1.1) are separate from favor hooks

**Validated results (murchad.txt):**
- Independent ruler ✓
- 3 feudal vassals: Ruaidhrí (d_connacht), Muiredach (c_desmond), Ólafr (c_ormond) ✓
- 2 alliances: William of England [2 bonds, via Prince William ↔ Princess Áine],
  Murchad mac Diarmait [c_dublin, negotiated] ✓
- Robin's favor hook on player (expires 1091.2.16) ✓

**Known gaps:**
- Factions not yet validated (Murchad had none at this date)
- Sub-vassal counts and indirect vassal totals not yet surfaced
- Opinion scores not yet parsed (live in `raw["opinions"]` but structure not explored)

---

## Running the Report

```bash
python3 run_report.py sample-saves/murchad.txt
# or with an explicit character ID:
python3 run_report.py sample-saves/murchad.txt 18269
```

Output: Military → Religion → Hierarchy reports printed to stdout.
Parse/load progress goes to stderr.

---

## What To Work On Next

Suggested priorities (not binding):

- **More saves**: extract the binary `.ck3` saves (requires `ck3-melt`) to get
  a range of dates and situations to validate against
- **Character encoding**: fix garbled special characters in Irish/Norse names
- **Economy evaluator**: gold income, development, buildings — the third major
  pillar of CK3 gameplay alongside military and diplomacy
- **Opinion scores**: parse `raw["opinions"]` to surface which vassals like/
  dislike the player and why — important for predicting faction risk
- **Sub-vassals**: the current hierarchy only shows direct vassals; a "realm
  tree" view would be more complete
- **LLM advisor layer**: feed evaluator output into Claude to generate
  strategic commentary — this is the long-term goal of the whole project
