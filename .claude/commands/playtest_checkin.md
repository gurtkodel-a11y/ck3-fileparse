---
description: Periodic check-in for an active CK3 playtest — runs the evaluators, follows up on open plan items, then works with the player to update existing goals and develop new ones.
argument-hint: "<playtest number, e.g. 5> — required if multiple playtests are active"
---

You are doing a periodic check-in for an active CK3 playtest.
Follow these steps in order.

## Step 1 — Identify the active playtest

If `$ARGUMENTS` is provided, use it as the playtest number (e.g. `5` → work
with `assessments/playtest5/` and `sample-saves/playtest5/`).

If no argument is provided and only one non-archived `assessments/playtestN/`
folder exists, use that one. If multiple are active, list them and ask the user
which one this check-in is for.

Read the most recent plan file in `assessments/playtestN/plans/` to understand
the open threads before running any evaluators.

## Step 2 — Load the new save

Find the most recently modified non-ironman `.ck3` file in the CK3 saves folder
(`C:\Users\kkado\Documents\Paradox Interactive\Crusader Kings III\save games\`)
whose filename matches the playtest's character/dynasty (infer from the
`assessments/playtestN/` folder name or the previous plan files if uncertain;
ask if ambiguous).

Skip files named `autosave*.ck3` and binary saves (`SAV0`, `U1\x01`, `U1\x00`).

Copy it into `sample-saves/playtestN/` and extract the gamestate to
`sample-saves/extracted/<filename>.txt` using `run_latest.py`'s extraction logic.

## Step 3 — Run the standard evaluators

```
python run_report.py sample-saves/extracted/<filename>.txt
python run_council.py sample-saves/extracted/<filename>.txt
```

Also run:
- `run_character_narrative.py --char <char_id>` — what's new in the life story
  since the last save date? (Compare against the narrative from the previous
  session to surface new events.)

## Step 4 — Follow up on open plan items

Read the current plan file carefully. For each open item (flagged with `[ ]`,
`[!]`, or listed as an "open question"), check whether the new save resolves,
advances, or changes it:

**For each open military/political thread:**
- Active wars: check `active_wars` for all wars involving the character. Note
  any new wars, finished wars, or retargeted wars (a title that changed hands
  can inherit an opponent's prior claim war — see `military.py` module docstring).
- Claims: run `gs.claims_held_by(char_id)` — any new claims? Any pressed claims
  now acted on or expired?
- Alliances: compare the new alliance count/composition to the previous report.

**For each open family/marriage thread:**
- Children: check `family_data` for any new betrothals, marriages, or births.
  Check `dead_data` for any deaths. Run `character_narrative` for recently
  deceased children (recovers the event via surviving family members' memories).
- Run `run_matchmaker.py` for any children whose betrothal is still an open plan
  item (refreshes candidate pool after ~2 years of personality development).

**For each open location/activity thread:**
- Run `run_carmen_sandiego.py --char <char_id> [<other ids>]` for any characters
  whose whereabouts matter (player, key rivals, potential war targets, etc.).

**For each open succession/development thread:**
- Check the Steward's brief for development progress and any new building
  completions. Note if the lowest-dev holding changed (a target was developed).

## Step 5 — Deliver the check-in assessment

Present findings in two parts:

**Part A — What changed**
A concise summary of what happened since the last save, organized by theme
(military, family, diplomatic, economic, narrative). Focus on changes, not
stable background. Flag anything that materially contradicts the current plan
(e.g. a war started that wasn't planned, an expected betrothal didn't happen,
a vassal died and changed the succession picture).

Note explicitly: what the save data confirms vs. what is inferred. When the
data can't explain something (e.g. why a new rival appeared), say so clearly
and ask the player rather than guessing.

**Part B — Open threads**
A short list of the plan items that are now resolved, the ones still pending,
and anything newly surfaced that doesn't fit an existing plan item yet.

Then invite the player to respond:
> "That's what I can see from the save. What are you seeing on your end —
> anything I missed or misread? And are there things you want to work through
> that the evaluators haven't surfaced?"

## Step 6 — Update the plans collaboratively

After the player responds and any back-and-forth clarification is done, write
a new plan file at `assessments/playtestN/plans/<YYYY-MM-DD>.txt` (using the
real-world date of this session, not the in-game date, since plan files are
"working documents as of this session" — but do include the in-game save date
prominently in the header).

The plan file should:
- Resolve or archive items that are confirmed complete or obsolete.
- Update items whose status changed.
- Add new items that emerged from the conversation.
- Carry forward unresolved items explicitly rather than silently dropping them.

**Important framing (same as initialize_playtest):** Your role is to help the
player develop and refine THEIR plans, not to impose your own strategic agenda.
Ask clarifying questions. Offer information and analysis when it helps them
decide. Don't write goals into the plan file that haven't been genuinely
discussed and agreed with the player in this session.
