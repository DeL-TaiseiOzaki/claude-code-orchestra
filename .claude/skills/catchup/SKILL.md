---
name: catchup
description: |
  Comprehensive onboarding for new or returning contributors.
  Scans repository artifacts (git history, CLAUDE.md / AGENTS.md,
  project rules, skill catalog, DESIGN.md, research & library notes,
  checkpoints, agent-team logs) and synthesizes a GUIDE.md at the
  repository root summarizing what has been worked on, why, and how
  to resume work.
metadata:
  short-description: Produce GUIDE.md summarizing past work for new/returning contributors
---

# Catchup

**Onboarding skill that produces a `GUIDE.md` at the repository root so a new or returning contributor can understand the project's history, current state, and how to resume work.**

## When to Use

- A contributor joins the repository for the first time
- A contributor returns after a long absence
- You want a single human-readable snapshot of "what has been happening here"

## When NOT to Use

- You need a single focused answer (use `/start-feature` planning phases or direct research instead)
- You want to capture the current session for later (use `/checkpointing`)
- You want running design history (use `/design-tracker` or read `DESIGN.md` directly)

## Workflow

```
Phase 1: COLLECT (Opus subagent — 1M context)
  Scan repo artifacts in parallel and save raw findings
    |
Phase 2: SYNTHESIZE (Claude Lead)
  Integrate findings into the GUIDE.md structure
    |
Phase 3: WRITE GUIDE.md
  Write to repository root, show diff summary to the user
```

---

## Phase 1: COLLECT (Opus Subagent)

**Delegate the scan to a `general-purpose` subagent with Opus 1M context.** The orchestrator context must stay light — the subagent reads many files and returns a structured summary.

### Subagent Brief

Spawn a `general-purpose` subagent with the following prompt skeleton:

```
You are preparing a GUIDE.md for new or returning contributors of this
repository. Scan the following sources and return a structured summary.
DO NOT write GUIDE.md yourself — only return findings.

## Sources to scan

### Git state
- `git log --oneline -n 100` (recent commit topics)
- `git log --since="30 days ago" --stat` (recent change footprint)
- `git branch -a` (active branches, including remote)
- `git status` (uncommitted work)
- `git diff HEAD --stat` (work-in-progress files)
- `git stash list` (shelved experiments)

### Project identity & rules
- README.md
- CLAUDE.md
- AGENTS.md (if present)
- .codex/AGENTS.md (if present)
- pyproject.toml (tech stack, scripts)
- .claude/rules/*.md (every rule file, summarize each in 1–2 lines)

### Capabilities catalog
- .claude/skills/*/SKILL.md — read only the YAML frontmatter (name,
  description, metadata.short-description). Build a list of available
  slash commands and their one-line purposes.
- .claude/agents/*.md — list subagent types and their specializations
  (frontmatter only).

### Design & research context
- .claude/docs/DESIGN.md (architecture decisions, key choices)
- .claude/docs/research/*.md (each research note, 1–2 line summary)
- .claude/docs/libraries/*.md (library constraints, 1–2 line summary)

### Local history (scan ONLY if the path exists)
- .claude/checkpoints/*.md (newest 5, summarize each in 1–2 lines)
- .claude/logs/agent-teams/*/*.md (teammate work logs, group by team)
- .claude/logs/cli-tools.jsonl (last ~50 entries; extract distinct
  Codex consultation topics)

## Return format

Return a single markdown block with these sections. Keep each bullet
tight — this feeds into GUIDE.md synthesis, not GUIDE.md itself.

### Project identity
- Purpose (1 sentence)
- Tech stack (language, package manager, key libs)
- Conventions (language for comments/communication, lint/test stack)

### Current state
- Active branch + any "Current Project" section from CLAUDE.md
- WIP files (from git status / diff)
- Stashed experiments (from git stash list)

### Recent work (last 30 days)
- Thematic grouping of recent commits (3–7 themes with commit counts)
- Notable features merged

### Architecture & decisions
- Top 5 design decisions from DESIGN.md with rationale
- Active research threads (from .claude/docs/research/)
- Library constraints worth knowing (from .claude/docs/libraries/)

### Capabilities
- Slash commands available (from skills/) — name + one-line purpose
- Subagents available (from agents/) — name + specialization

### Local history (if available)
- Latest checkpoint summaries
- Agent Teams sessions (team name, teammates, outcome)
- Frequent CLI consultation topics

### Rules summary
- One-line summary per .claude/rules/*.md file

If any source is missing, note it as "not present" instead of fabricating.
```

### Execution Pattern

Use the `general-purpose` subagent in the foreground and wait for its structured summary. The summary is the sole input to Phase 2 — the subagent must NOT create `GUIDE.md` itself.

---

## Phase 2: SYNTHESIZE (Claude Lead)

Integrate the subagent's structured findings into the `GUIDE.md` layout below. Do not re-read the source files; rely on the subagent's summary to preserve orchestrator context.

If an expected section is missing from the subagent output (e.g. no checkpoints exist), omit the corresponding section in `GUIDE.md` rather than leaving a placeholder.

---

## Phase 3: WRITE GUIDE.md

Write the final document to `GUIDE.md` at the repository root (overwrite if it exists). After writing:

1. Report the file path and line count to the user
2. List the top-level sections that were included
3. Note sections that were skipped because the source was absent

---

## `GUIDE.md` Structure

Use this layout. Keep the tone factual and skimmable.

```markdown
# Project Guide

_Generated by `/catchup` on {YYYY-MM-DD}_

## 1. What is this project?

- **Purpose**: {one sentence from README/CLAUDE.md}
- **Tech stack**: {language, package manager, key libraries}
- **Conventions**: {language for code / communication, lint / test tools}

## 2. Current State

- **Active branch**: {branch name}
- **Current focus** (from CLAUDE.md): {Current Project section, if present}
- **Work in progress**: {uncommitted files; omit section if none}
- **Stashed experiments**: {stash entries; omit if none}

## 3. Recent Work (last 30 days)

{3–7 thematic bullets grouping recent commits, with commit counts}

## 4. Architecture & Key Decisions

{Top 5 design decisions from DESIGN.md with rationale}

### Active research threads
{List from .claude/docs/research/ with 1-line summaries}

### Library constraints
{List from .claude/docs/libraries/ with 1-line summaries}

## 5. Capabilities

### Slash commands
{Table: command — purpose, from skills/ frontmatter}

### Subagents
{Table: name — specialization, from agents/ frontmatter}

## 6. Project Rules

{One-line summary per .claude/rules/*.md file}

## 7. How to Resume Work

- **Environment setup**: {commands from pyproject.toml / README}
- **Common commands**: {lint / test / run / build}
- **Suggested next skills**:
  - New feature (large, needs research) → `/start-feature`
  - Feature on existing codebase → `/add-feature`
  - Technical investigation → `/spike`
  - Bug / error diagnosis → `/troubleshoot`

## 8. Recent Sessions (if available)

### Checkpoints
{Latest 5 checkpoint summaries}

### Agent Teams sessions
{Group by team-name, show teammates + outcome}

### Frequent CLI consultations
{Codex topics from cli-tools.jsonl}

---

_Sources: git log, CLAUDE.md, AGENTS.md, .claude/rules/, .claude/skills/,
.claude/docs/, .claude/checkpoints/, .claude/logs/._
```

Sections 2 (WIP / stash), 4 (research / libraries), 6, 8 are omitted when their sources are empty. Do not leave placeholder text.

---

## Tips

- **Context discipline**: Phase 1 runs in a subagent so the orchestrator never loads raw logs or long docs. Only the structured summary comes back.
- **Idempotent**: `GUIDE.md` is regenerated from sources each run. Do not edit it by hand — update the underlying sources (CLAUDE.md, DESIGN.md, etc.) and re-run.
- **`.gitignore` awareness**: `.claude/checkpoints/` and `.claude/logs/` are gitignored. On a fresh clone they will be absent; the skill handles this gracefully.
- **Language**: `GUIDE.md` content itself follows the project's user-facing language convention (Japanese for this repository), while code identifiers and command names stay in English.
