# Japan: Ritsuryō / Sōryō governments, Noble Family titles, and Domiciles

Load this file when working with a Japanese-government save (or any save using
the Noble Family / Domicile mechanics this DLC content introduced) — it's
intentionally kept out of CLAUDE.md's always-loaded context since it's
specific to this region/mechanic and not relevant most of the time.

Source playtest: Playtest 4, Takenori Kiyohara, Duke of Mutsu (`japan_feudal_government`).

## Government types

Defined in `game/common/governments/01_japan_government_types.txt`:

- **`japan_administrative_government`** — code-commented `# Ritsuryo`. The
  more centralized/bureaucratic of the two; `main_administrative_tier = county`,
  `domain_limit_max = 1`. Blocks several subject-court types.
- **`japan_feudal_government`** — code-commented `# Soryo`. The more
  militaristic variant; `domain_limit_max = 2`, knight/MaA cost bonuses
  (`archer_cavalry_recruitment_cost_mult = -0.25`, etc.), `knight_limit = 2`.
  Vassal contract group: `japan_feudal_vassal` (this is why
  `ck3/evaluators/base.py`'s `_contract_label()` rendered it as the generic
  title-cased fallback "Japan Feudal Vassal" rather than a hardcoded label —
  see CLAUDE.md's DLC Coverage section).
- Both governments set `noble_families = yes` and `domicile_type = japanese_manor`
  in their rules — these two mechanics (below) are tied directly to having
  one of these two government types.
- `can_get_government` for both is gated on `has_tgp_dlc_trigger` — `tgp` is
  the internal codename for this Japan content (also shows up as an infix on
  tradition keys; see CLAUDE.md's "Fixed during the playtest 4 shakeout" note).

## Noble Family titles

A landless, honorary title representing headship of an extended dynasty/clan,
distinct from a character's real landed titles. In this save, Takenori holds
`c_nf_kiyohara` ("the Kiyohara Family") alongside his real duchy/counties —
it has a county-tier key prefix but carries no barony and isn't counted among
his actual holdings (`ck3/evaluators/terrain.py` correctly excludes it; it has
no province to profile).  It does indicate possession of that family's Manor,
which can be held as a physical location even if a character has no landed 
holdings whatsoever.

**Save-data fingerprint** — a title record like this looks different from an
ordinary landed title:
```python
gs.titles["13595"]
# {'key': 'c_nf_kiyohara', 'holder': 28352, 'heir': [30898],
#  'laws': ['noble_family_succession_law'], 'domicile': 16777524, ...}
```
- `laws: ['noble_family_succession_law']` — overrides the realm's normal
  succession law (Takenori's `landed_data.laws` includes
  `partition_succession_law`, which governs his real titles) for this title
  specifically.
- `heir` is a **single character ID**, not the usual multi-candidate
  succession queue list his other titles carry — Noble Family succession
  names one heir directly (in this case Takesada, id 30898, who is also his
  player-visible heir).
- `domicile` points into the separate `raw["domiciles"]["database"]` table
  (see below) — not every landed title has one; ordinary counties/duchies in
  this save have `domicile: None`.
- Game-data confirmation: `game/common/domiciles/types/10_tgp_japan_domicile_types.txt`'s
  `japanese_manor` domicile type is gated on
  `allowed_for_character: any_held_title: is_noble_family_title = yes`.

## Domiciles

A separate top-level save section, **not** specific to Japan — `raw["domiciles"]["database"]`
had 851 entries in this save, with domicile types like `estate` and
`east_asian_estate` appearing for non-Japanese characters too. It looks like
base content (possibly tied to Roads to Power, which we don't currently own)
that the Japan content reuses via its own `japanese_manor` domicile type.

Structure of one entry:
```python
{'domicile_type': 'japanese_manor', 'owner_title': 13595, 'province': 10699,
 'buildings': ['japanese_manor_main_02', 'japanese_horse_pastures_01',
               'japanese_tea_plantation_01', 'japanese_stables_01',
               'japanese_main_carpenter_01'],
 'domicile_building_slots': [...], 'move_cooldown': '1067.3.14'}
```
- `owner_title` is the title ID (not character ID) that owns the domicile —
  cross-reference against `gs.titles[tid]["key"]` to find which title (in
  this case the Noble Family title), not via the holding character directly.
- It's a real micro-holding: a province, a building list, building slots
  (external/main, with internal sub-slots) — structurally closer to a
  barony's building list than anything else currently modeled.
- `move_cooldown` confirms domiciles are literally relocatable (there's a
  gold cost to move one, scaled by current manor tier — see the
  `japanese_manor` type definition).

## Tool coverage gap (not yet built)

None of this is currently surfaced by any evaluator:
- Noble Family titles are silently included in `domain_title_keys`/
  `domain_title_labels` (character.py) with a generic "Count of X" label
  (fixed to at least show the *correct* name during the playtest 4 shakeout,
  but the label still says "Count of Kiyohara Family" rather than something
  that reflects it isn't a real county).
- `noble_family_succession_law` and the single named `heir` aren't read by
  any evaluator — a player relying on the tool for succession planning would
  currently see no signal that this title follows different inheritance
  rules than the rest of the realm.
- The domicile (manor buildings, province, development) isn't read at all —
  `raw["domiciles"]` has zero index/lookup anywhere in `ck3/gamestate.py`.

If/when this becomes worth building: a `gs.domicile_for_title(title_key)`
lookup (mirroring `gs.title_by_key()`) would be the natural entry point,
paired with a small addition to `character_profile()` that flags
Noble Family titles distinctly from real landholdings and surfaces their
succession law + named heir.
