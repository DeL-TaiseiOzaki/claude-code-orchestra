---
name: context-loader
description: ALWAYS activate this skill at the start of every task. Load shared rules from .agents/ and project design context before executing any task.
---

# Context Loader Skill

## Purpose

Load canonical shared context from `.agents/` plus project-owned design
documentation so every agent runtime uses the same source files.

## When to Activate

**ALWAYS** - This skill must run at the beginning of every task to load project context.

## Workflow

### Step 1: Resolve the Read Plan

Run `load_context.py` to get a deterministic read order instead of a
hand-maintained file list, so the plan never drifts from what actually exists
on disk:

```bash
python3 .agents/skills/context-loader/load_context.py [--task-libraries name,name]
```

Pass `--task-libraries` (comma-separated) when the task names specific
libraries; the script matches them against `.agents/docs/libraries/` and folds
any hits into the read order.

The JSON reports `{ok, read_order, rules, state, design, progress, libraries,
missing, unreadable, warnings}`. `read_order` is the exact ordered list of
repo-relative paths to read, in this order:

1. the rule files in `.agents/rules/` (coding principles, dev environment,
   language, security, testing, tiers, CLI execution, Codex delegation, and any
   newly added rule file);
2. `.agents/STATE.md` — the active main agent and current working blocks;
3. `PROGRESS.md` — the rolling record of the latest five checkpoints, and the
   session-to-session continuity `/feature` reads first;
4. `.agents/docs/DESIGN.md` — architecture decisions and constraints;
5. any matched library docs.

### Step 2: Read Everything in `read_order`, Then Surface Gaps

Read each path in `read_order`. Then check the rest of the report:

- **`missing`** — canonical files that do not exist at all (e.g.
  `.agents/docs/DESIGN.md`, `PROGRESS.md`). Report these; do not silently
  proceed as if they were empty.
- **`unreadable`** — files that *do* exist but could not be read or decoded.
  This is a filesystem or encoding problem, not an un-bootstrapped repository:
  do not respond by suggesting `/init`.
- **`warnings`** — `design.placeholder` is tri-state: `true` means
  `.agents/docs/DESIGN.md` is absent or still the uninitialised `/init`
  template (its "Background & Purpose" section is empty), `false` means real
  prose, and `null` means the marker heading is gone so the question cannot be
  answered. `progress.entries: 0` means `PROGRESS.md` exists but holds no
  checkpoint entry.
- **`libraries.matched`** vs **`libraries.files`** — `matched` is what
  `read_order` included for the current task; `files` is every doc that
  exists. If a library relevant to the task isn't in `files` at all, its
  documentation simply doesn't exist yet.

Exit code 2 means `.agents/rules/` or `.agents/STATE.md` is missing entirely or
unreadable — treat this as a hard stop, not a warning.

### Step 3: Execute Task

With the loaded context, execute the requested task following:
- Coding principles from rules
- Design decisions from DESIGN.md
- Library constraints from docs

## Key Rules

The rules themselves live in the files `read_order` enumerates — restating them
here would be a hand-maintained duplicate of authoritative content, which is the
drift this script exists to prevent. Apply what you read in
`.agents/rules/coding-principles.md`, `dev-environment.md`, `language.md`,
`security.md`, and `testing.md`.

## Output

After loading context, briefly confirm in Japanese:

- how many rule files were read, and that `.agents/STATE.md` was read;
- the `missing`, `unreadable`, and `warnings` arrays **quoted verbatim** from the
  JSON — not paraphrased, not summarised as "no issues";
- `design.placeholder` and `progress.entries` as reported;
- ready to execute the task.
