---
description: Initialize tracking for a new CK3 playthrough — creates the assessments/playtestN/ folder, copies the most recent save, runs the full evaluator suite, and opens a conversation about the player's goals.
argument-hint: "[optional: character name or realm hint to disambiguate if multiple recent saves exist]"
---

You are initializing a new playtest tracking session for the CK3 fileparse project.
Follow these steps in order. Be transparent about what you're doing at each stage.

## Step 1 — Determine the next playtest number

Scan `assessments/` for existing `playtestN/` folders (including those under
`assessments/archive/`) and pick the next unused integer. Print what you found
and which number you're assigning.

## Step 2 — Locate the save file

Find the most recently modified non-ironman `.ck3` file in the CK3 saves folder
(`C:\Users\kkado\Documents\Paradox Interactive\Crusader Kings III\save games\`).
Skip files named `autosave*.ck3` and any whose embedded gamestate starts with
binary magic bytes (`SAV0`, `U1\x01`, `U1\x00`).

If `$ARGUMENTS` was provided, prefer files whose name contains that string. If
multiple candidates exist and none is clearly newest or labeled, list them and
ask the user which one to use.

## Step 3 — File the save

Check `sample-saves/` root. If a non-archived save file is already sitting there
(indicating an active playtest), ask the user how to handle it before proceeding:
- Archive it into `sample-saves/archive/<playtest-name>/` (matching the
  corresponding `assessments/archive/` folder if one exists)
- Leave it in place and run parallel playtests
- Other

Once resolved, copy the chosen `.ck3` into `sample-saves/playtestN/` (using the
new number from Step 1). Extract the embedded gamestate to
`sample-saves/extracted/<filename>.txt` using the same extraction logic as
`run_latest.py` (skip the `SAV0` header, find the embedded ZIP, read `gamestate`).

## Step 4 — Run the standard evaluators

Run all five against the extracted text file:
```
python run_report.py sample-saves/extracted/<filename>.txt
python run_council.py sample-saves/extracted/<filename>.txt
```

Also run these targeted queries for the played character:
- `gs.claims_held_by(char_id)` — any existing title claims (opportunities)
- `run_character_narrative.py --char <char_id>` — life story so far

Capture all output. Parse the played character's ID from the output header.

## Step 5 — Create the folder structure

```
assessments/playtestN/
assessments/playtestN/plans/
```

## Step 6 — Deliver the opening assessment

Write a structured first assessment covering **all** of the following, drawing
on the evaluator output:

**Identity & Position**
- Who is the player character? Name, title, age, dynasty, realm size.
- What is their position in the political hierarchy (liege chain up)?

**Family & Dynasty**
- Spouse(s), children (ages, personalities, education focus if known).
- Dynasty prestige, house head, notable relatives at other courts.

**Internal Political Situation**
- Direct vassals: who is loyal, neutral, or at risk?
- Active factions (if any).
- Hooks held / held on player.
- Alliances (if any) and what they cover.

**External Political Situation**
- Liege relationship: how does the player stand with their overlord?
- Key neighboring rulers: power ratios, faith, proximity zones.
- Active wars (if any) — CB, current score, allied/enemy pool.

**Existing Claims & Opportunities**
- Any title claims held (pressed or not)? Surfaces via `claims_held_by`.
- Faith-related opportunities (pagan neighbors, fervor, crusade eligibility)?
- Any obvious expansion windows or strategic openings?

**Strategic Threats**
- Rivals and personal enemies.
- Any strong negative opinions that could drive scheming?
- Military posture: outnumbered, matched, or strong advantage?

**Character Narrative** (if memories exist)
- Anything already interesting in the life-story output — formative events,
  relationships, losses. Don't invent; only report what the save actually
  records.

Keep the assessment factual and grounded in the evaluator data. Note explicitly
when something is inference vs. direct evidence. Use the same epistemic-humility
conventions established in this project's assessments (see `assessments/` folder
for tone examples).

## Step 7 — Open the goals conversation

After delivering the assessment, say something like:

> "That's where things stand at the start. Before I file anything in the plans
> folder, I'd like to hear your own read — what are you hoping to accomplish in
> this playthrough? Big picture and near-term both welcome. I'll ask follow-up
> questions to help articulate them clearly, then we can decide what goes in the
> plan file and at what level of detail."

**Important framing:** Your role here is NOT to develop the plans yourself.
Your job is to provide useful information and ask useful questions that help the
player articulate and refine THEIR own goals. Don't front-load a full strategic
plan — surface information, ask what matters to them, and work collaboratively
toward a plan file that reflects their actual intentions.

Gradually build out `assessments/playtestN/plans/<date>.txt` as the conversation
develops, writing only what has been genuinely decided through dialogue, not what
you think they *should* do.
