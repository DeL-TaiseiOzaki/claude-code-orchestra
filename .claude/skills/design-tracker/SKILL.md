---
name: design-tracker
description: Record a project design decision into .claude/docs/DESIGN.md through the shared typed writer. Use when the user says "record this", "add to design", "document this", "記録して", or asks what has been decided so far — and when a design decision has just been made and should not be lost.
---

# Design Tracker Skill

## Purpose

This skill keeps the project's 要件定義書 (`.claude/docs/DESIGN.md`) current.
DESIGN.md is the **macro** requirements & design document (*what* the project builds
and *why*); micro work progress lives in `PROGRESS.md`. It covers:
- Background & purpose, scope
- Functional & non-functional requirements
- Architecture (including agent roles)
- Tech stack choices and their rationale
- Constraints, key decisions, and open questions

## How This Skill Is Reached

Read this before relying on it: **nothing in the repository activates this skill
automatically.** The description above is the entire trigger surface, and it works
only through the runtime's own description-based skill selection.

- **Explicit request** — "record this", "add to design", "update DESIGN",
  "記録して", `/design-tracker`. This is the reliable path.
- **Model invocation** from the description, at the runtime's discretion.
  Claude Code discovers the skill through `.claude/skills` → `.claude/skills`;
  Codex through `.codex/config.toml`'s `path = ".claude/skills/design-tracker"`.
- **No hook mechanism.** `.claude/hooks/` contains no design-tracker branch, and
  the words a design conversation actually uses (設計 / design / architecture)
  are claimed by `CODEX_TRIGGERS` in `agent-router.py`, which injects a *Codex*
  consultation nudge instead. `check-codex-before-write.py` also nudges when
  `DESIGN.md` is edited, but it blocks nothing — a freehand edit still lands.

So an agent in a design conversation must decide to record the decision; no
automation will decide for it. If a decision was made and this skill was not
reached, record it at the next checkpoint — `/checkpointing` describes recording
decisions via `update_design.py` for exactly that reason.

> Previous versions of this file promised proactive, automatic activation
> ("Do NOT wait for user to ask"). That promise was enforced by nothing, so it
> has been removed rather than left as a false statement in a normative
> document.

## Workflow

### Recording Decisions

1. Decide whether this *is* a design decision, and whether it is already
   recorded. Grep the target table (e.g. `grep -n "^| " .claude/docs/DESIGN.md`)
   instead of reading the whole document — the writer locates the table and
   heading itself.
2. Extract the decision from the conversation.
3. Map it to a section and to that section's **typed input key** (table below).
4. Write a per-invocation input JSON and run the shared writer (see Mechanical
   Update).

### Sections to Update

DESIGN.md uses these fixed sections (Japanese + English headings). Every target
has a typed input key, so no markdown row is ever hand-written:

| Conversation Topic | Target Section | Input key | Fields |
|-------------------|----------------|-----------|--------|
| Project goals, problem, stakeholders | `## 背景・目的 (Background & Purpose)` | `section_updates` | `heading`, `content` (prose) |
| What is / isn't covered | `## スコープ (Scope)` — In / Out of Scope | `section_updates` | `heading`, `content` (bullets) |
| A feature the system must provide | `## 機能要件 (Functional Requirements)` | `requirements` | `id`, `requirement`, `priority`, `notes` |
| Performance, security, availability, maintainability targets | `## 非機能要件 (Non-Functional Requirements)` | `nfr` | `category`, `requirement`, `metric` |
| System structure, components, agent roles | `## アーキテクチャ (Architecture)` — overview + Agent Roles table | `section_updates` for the overview prose, `agent_roles` for the table | `agent`, `role`, `responsibilities` |
| Library / framework / infra choice + why | `## 技術選定 (Tech Stack & Rationale)` | `tech_choices` | `area`, `technology`, `rationale`, `alternatives` |
| Hard limits (technical, org, compatibility) | `## 制約 (Constraints)` bullets | `section_updates` | `heading`, `content` (bullets) |
| Why we chose X over Y (significant) | `## Key Decisions` | `decisions` | `decision`, `rationale`, `alternatives` (the date is stamped by the writer) |
| Things to do later, unresolved questions | `## TODO / Open Questions` | `section_updates` | `heading`, `content` (checklist) |

The four prose sections have no typed key **because they have no fixed shape** —
their content is a sentence or a bullet an agent writes, and there is no correct
rendering for a script to own. Every section that *does* have a fixed shape (a
table) has a typed key, and the writer refuses table rows passed through
`section_updates`: it exits `2` naming the key you should have used, so the
unescaped-cell and orphaned-row corruptions are now unreachable from this skill.

Choosing the section stays judgment. Rendering the row does not.

### Mechanical Update

Use a **per-invocation** input path, never a shared one: this skill can run
concurrently with other work (and inside a subagent), and two recordings sharing
one input file overwrite each other. Resolve the path from the shared workspace
registry rather than deriving it by hand, so the slug rule is the same one every
other skill uses:

```bash
python3 .claude/skills/_shared/workspace.py \
  --skill design-tracker --title "{decision topic}" --create
```

That prints one JSON object whose `paths.design_input` is
`.claude/logs/design-input-{slug}.json`. Use it verbatim as `${input}` below.
Exit 0 resolved/created · 1 bad args · 3 `.claude/logs/` could not be created.

Example input (use only the keys you need):

```json
{
  "decisions": [
    {"decision": "Use ReAct pattern", "rationale": "Better tool-use control", "alternatives": "Function calling only"}
  ],
  "tech_choices": [
    {"area": "Agent loop", "technology": "ReAct", "rationale": "Tool-use control", "alternatives": "Function calling only"}
  ],
  "section_updates": [
    {"heading": "## TODO / Open Questions", "content": "- [ ] Evaluate streaming support"}
  ]
}
```

Run dry-run, read the preview, then apply:

```bash
python3 .claude/skills/_shared/update_design.py --input "${input}"
# Read the file named by preview_file in the JSON output, then:
python3 .claude/skills/_shared/update_design.py --input "${input}" --apply --require-change
```

**Completion test.** `"ok": true` alone is not it — a duplicate or empty entry
used to return `ok: true` with `result: "no-op"` and exit `0` while nothing was
written. Require all of:

- `result == "applied"`, and
- `decisions_appended > 0` **or** some `rows_appended` value `> 0` **or**
  `sections_updated` non-empty.

Always report `skipped_duplicates` when it is non-zero — that is the honest
"already recorded" answer. `--require-change` makes the writer enforce the same
thing: a no-op becomes `ok: false` and exit `2`, so "recorded" can never be
reported for a run that wrote nothing.

Other exit codes: `1` bad arguments or input-schema violation · `2` DESIGN.md
structure invalid or missing (run `/init` first), a duplicate requirement ID, a
table row passed through `section_updates`, or a no-op under `--require-change` ·
`3` DESIGN.md changed while the writer held it, or the write failed — re-read and
retry.

## Output Format

When recording, report concisely:
- What was recorded, and into which DESIGN.md section
- The writer's `result`, the appended counts, and `skipped_duplicates`
- Anything you decided *not* to record, and why

## Language Rules

- **Reasoning / code examples**: English
- **Document content**: English (technical terms); Japanese descriptions are
  acceptable to match the existing 要件定義書 headings
- **Report**: follow the surrounding session's language
