---
name: init
description: Analyze project structure, write the thick requirements doc (.claude/docs/DESIGN.md), populate the thin "Repository Identity" pointer in CLAUDE.md (Zone B), and mirror identity into AGENTS.md.
disable-model-invocation: true
---

# Initialize Project Configuration

Analyze this project and:

1. Generate the **thick** 要件定義書 at `.claude/docs/DESIGN.md` (macro requirements & design — *what* this project builds and *why*).
2. Populate the **thin** **Repository Identity (Zone B)** pointer in `CLAUDE.md` (a brief identity line + a pointer to DESIGN.md — no thick content here).
3. Mirror the identity into the project-specific sections of `AGENTS.md`.

## Document hierarchy (where content lives)

- `CLAUDE.md` = orchestrator contract. Zone B holds only a **thin identity + pointer**.
- `.claude/docs/DESIGN.md` = 要件定義書 (thick macro requirements/design). This is where rich project content belongs.
- `PROGRESS.md` = micro work progress (maintained by `/checkpointing`).

## CLAUDE.md 3-zone layout (recap)

```
Zone A — Orchestra concept & template base (template-owned)
# @orchestra:template-boundary
Zone B — Repository Identity (thin pointer)  ← this skill writes here
# @orchestra:repo-boundary
Zone C — Working state (sessions, features, design pointers)
```

## Important

- Touch ONLY Zone B of `CLAUDE.md`. Never modify Zone A (above `@orchestra:template-boundary`) or Zone C (below `@orchestra:repo-boundary`).
- For `AGENTS.md`, do NOT modify the "Extensions" section and below — only update the top project-specific sections.
- If `CLAUDE.md` lacks the 3-zone markers (legacy layout), ask the user to run `./scripts/update.sh` first. Do not hand-insert markers.

## Steps

### 1. Project Analysis

Find these files to identify the tech stack:

- `package.json` → Node.js/TypeScript project
- `pyproject.toml` / `setup.py` / `requirements.txt` → Python project
- `Cargo.toml` → Rust project
- `go.mod` → Go project
- `Makefile` / `Dockerfile` → Build/deploy config
- `.github/workflows/` → CI/CD config

Also detect:

- npm scripts / poe tasks / make targets → Common commands
- Major libraries/frameworks

### 2. Ask User

Use AskUserQuestion tool to ask:

1. **Project overview**: What does this project do? (1-2 sentences)
2. **Code language**: English or Japanese for comments/variable names?
3. **Additional rules**: Any other coding conventions to follow?

### 3. Generate the thick DESIGN.md (要件定義書)

`.claude/docs/DESIGN.md` is the **macro requirements & design** document. This is where
the rich project content goes (not CLAUDE.md). Read the existing template first, then
fill each section **as far as the project evidence allows**, using the analysis from
step 1 and the user's answers from step 2. Leave a section as its placeholder only when
there is genuinely no basis to fill it.

Map your findings onto the fixed section structure (keep the Japanese+English headings
and the leading document-map links intact):

| Section | What to fill in |
|---------|-----------------|
| `## 背景・目的 (Background & Purpose)` | The user's project overview answer; the problem it solves and for whom. |
| `## スコープ (Scope)` | In Scope / Out of Scope bullets inferred from the overview and codebase. |
| `## 機能要件 (Functional Requirements)` | Table rows (ID / 要件 / 優先度 / 備考) for features evident in the code or stated by the user. |
| `## 非機能要件 (Non-Functional Requirements)` | Table rows (カテゴリ / 要件 / 指標) for performance, security, maintainability, etc. |
| `## アーキテクチャ (Architecture)` | Overview narrative + the Agent Roles table (orchestrator / delegated agents). |
| `## 技術選定 (Tech Stack & Rationale)` | Table rows (領域 / 採用技術 / 理由 / 代替案) from the detected stack. |
| `## 制約 (Constraints)` | Bullets for technical / org / compatibility constraints. |
| `## Key Decisions` | Seed any decisions already made (with today's date). |
| `## TODO / Open Questions` | Items needing follow-up. |

Do **not** fabricate requirements for a distribution-template repo: when initializing a
real project, prefer concrete evidence; when nothing is known, leave the placeholder.

### 4. Update CLAUDE.md Zone B (thin pointer only)

First verify the 3-zone markers exist:

```bash
grep -q "@orchestra:template-boundary" CLAUDE.md && grep -q "@orchestra:repo-boundary" CLAUDE.md
```

If either marker is missing, stop and ask the user to run `./scripts/update.sh` to migrate the file; the updater auto-migrates legacy single-boundary layouts.

Replace the content **between** the two markers with a **thin** identity + pointer (keep
the marker lines and their ━ separators intact). The thick content lives in DESIGN.md —
do **not** duplicate tech stack / requirements here. Use the Edit tool by anchoring on
the full block between the two boundary box lines.

```markdown
## Repository Identity

<!-- Managed by /init. Re-run /init to refresh. -->

{One-line identity: what this project is, in a single sentence}

Macro requirements & design live in **[.claude/docs/DESIGN.md](.claude/docs/DESIGN.md)** (要件定義書).
Keep this section thin — a brief identity line + pointer. Thick content belongs in DESIGN.md.
```

### 5. Partial Update of AGENTS.md

Mirror the same information into `AGENTS.md` so Codex sees it. Update only the top section (up to the first `---`) with this format:

```markdown
# Project Overview

{User's answer}

## Language Settings

- **Thinking/Reasoning**: English
- **Code**: {Based on analysis - English or Japanese}
- **User Communication**: Japanese

## Tech Stack

- **Language**: {Detected language}
- **Package Manager**: {Detected tools}
- **Dev Tools**: {Detected tools}
- **Main Libraries**: {Detected libraries}

## Common Commands

```bash
{Detected commands}
```
```

### 6. Check Unnecessary Rules

Check rules in `.claude/rules/` and suggest removing unnecessary ones:

- Non-Python project → `dev-environment.md` (uv/ruff/ty) may not be needed
- No-test project → `testing.md` may not be needed

### 7. Report Completion

Report to user (in Japanese):

- Detected tech stack
- Files updated (`.claude/docs/DESIGN.md`, `CLAUDE.md` Zone B, `AGENTS.md`)
- Recommended rules to remove (if any)
