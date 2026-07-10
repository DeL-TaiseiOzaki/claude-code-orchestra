---
name: design-tracker
description: PROACTIVELY track and document project design decisions without being asked. Activate automatically when detecting architecture discussions, implementation decisions, pattern choices, library selections, or any technical decisions. Also use when user explicitly says "record this", "what's our design status", or equivalent. Do NOT wait for user to ask - record important decisions immediately.
---

# Design Tracker Skill

## Purpose

This skill keeps the project's 要件定義書 (`.claude/docs/DESIGN.md`) current.
DESIGN.md is the **macro** requirements & design document (*what* the project builds
and *why*); micro work progress lives in `PROGRESS.md`. This skill automatically tracks:
- Background & purpose, scope
- Functional & non-functional requirements
- Architecture (including agent roles)
- Tech stack choices and their rationale
- Constraints, key decisions, and open questions

## When to Activate

- User discusses architecture or design patterns
- User makes implementation decisions (e.g., "let's use ReAct pattern")
- User says "record this", "add to design", "document this"
- User asks "what's our current design?" or "what have we decided?"
- Important technical decisions are made during conversation

This skill also handles **explicit, manual update requests** — e.g. "update DESIGN",
"force a design update", "記録して" — in addition to its proactive auto-activation.
Whether triggered automatically or on request, it runs the same workflow below.

## Workflow

### Recording Decisions

1. Read existing `.claude/docs/DESIGN.md`
2. Extract the decision/information from conversation
3. Map to the appropriate section (use the topic table below)
4. Write the input JSON and run the shared writer script (see Mechanical Update below)

### Sections to Update

DESIGN.md uses these fixed sections (Japanese + English headings). Map each
conversation topic to its section:

| Conversation Topic | Target Section |
|-------------------|----------------|
| Project goals, problem, stakeholders | `## 背景・目的 (Background & Purpose)` |
| What is / isn't covered | `## スコープ (Scope)` — In / Out of Scope |
| A feature the system must provide | `## 機能要件 (Functional Requirements)` table (ID / 要件 / 優先度 / 備考) |
| Performance, security, availability, maintainability targets | `## 非機能要件 (Non-Functional Requirements)` table (カテゴリ / 要件 / 指標) |
| System structure, components, agent roles | `## アーキテクチャ (Architecture)` — overview + Agent Roles table |
| Library / framework / infra choice + why | `## 技術選定 (Tech Stack & Rationale)` table (領域 / 採用技術 / 理由 / 代替案) |
| Hard limits (technical, org, compatibility) | `## 制約 (Constraints)` bullets |
| Why we chose X over Y (significant) | `## Key Decisions` table (Decision / Rationale / Alternatives / Date) |
| Things to do later, unresolved questions | `## TODO / Open Questions` |

### Mechanical Update

Use the shared writer script for all DESIGN.md appends. Write the input JSON
to `.claude/logs/design-input.json`:

```json
{
  "decisions": [
    {"decision": "Use ReAct pattern", "rationale": "Better tool-use control", "alternatives": "Function calling only"}
  ],
  "section_updates": [
    {"heading": "## TODO / Open Questions", "content": "- [ ] Evaluate streaming support"}
  ]
}
```

Run dry-run, review the preview, then apply:

```bash
python3 .claude/skills/_shared/update_design.py --input .claude/logs/design-input.json
# Review the preview file path in the JSON output, then:
python3 .claude/skills/_shared/update_design.py --input .claude/logs/design-input.json --apply
```

Verify `"ok": true` in the output. Duplicate decision rows (same text + date)
are automatically skipped. Exit code 2 means DESIGN.md structure is invalid or
missing — run `/init` first.

## Output Format

When recording, report concisely:
- What was recorded
- Which DESIGN.md section was updated
- Brief summary of the change

## Language Rules

- **Reasoning / code examples**: English
- **Document content**: English (technical terms); Japanese descriptions are
  acceptable to match the existing 要件定義書 headings
- **Report**: follow the surrounding session's language
