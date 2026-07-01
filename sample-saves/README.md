# sample-saves/ — data hygiene

## Folder roles

- **`playtestN/`** — saves belonging to an in-progress playtest, numbered to
  match the corresponding `assessments/playtestN/` folder. Every playtest
  gets one of these as soon as it's initialized (see `/initialize_playtest`),
  whether or not it's the only one running — multiple playtests can be
  active in parallel (e.g. `playtest4/` and `playtest5/` run concurrently
  starting mid-2026). There is no longer a special "current playtest" root;
  the root itself only holds this README plus the shared folders below.
- **`archive/<name>/`** — saves from a playtest that has concluded or been
  superseded. Folder name matches the corresponding `assessments/archive/
  <name>/` folder (usually just `playtestN`, occasionally a descriptive name
  for pre-numbering-convention playtests) so a save and its narrative
  write-ups stay easy to cross-reference.
- **`validation/`** — fixtures used to validate evaluator/parser correctness
  (e.g. `murchad.txt`, `dunkeld.txt`) rather than narrative playtests. These
  don't belong to any `assessments/playtestN/` folder — they're referenced
  directly from CLAUDE.md's "Validated against ..." notes. Keep them here,
  not in `archive/`, so that documentation stays accurate.
- **`extracted/`** — gitignored scratch cache of plaintext-extracted saves,
  shared across all playtests (filenames already encode character/date, so
  collisions are unlikely). Fully regenerable from the `.ck3`/`.zip` files;
  safe to delete and let it repopulate. Not part of the archive/validation
  split above.

## When retiring a playtest

When a playtest ends (or is superseded — e.g. by a DLC-driven restart), move
its `playtestN/` folder to `archive/playtestN/` (or a descriptive name if it
predates the numbering convention), matching the corresponding move under
`assessments/archive/`. Don't retroactively reorganize `validation/`
fixtures — they're not tied to a playtest lifecycle.

## Legacy note: watch_autosaves.py / extract_snapshots.py

`scripts/watch_autosaves.py` and `scripts/extract_snapshots.py` still target
the old flat-root convention (saves landing directly in `sample-saves/`).
They predate the per-playtest-subfolder convention above and haven't been
updated to match — if you're using that cross-machine (gaming PC → Mac)
pipeline rather than `/initialize_playtest` / `/playtest_checkin`, saves
will land at root and need manual filing into the right `playtestN/` folder.

## Naming convention

Keep the existing pattern: `<Title>_<Name>_<Realm>_<YYYY>_<MM>_<DD>.ck3`
(e.g. `Toryo_Kiyohara_Takenori_of_the_Kiyohara_Ichizoku_1066_09_15.ck3`) —
title and name as shown in-game, underscores instead of spaces, date split
into year/month/day fields.
