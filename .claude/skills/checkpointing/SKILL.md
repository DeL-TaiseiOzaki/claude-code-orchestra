---
name: checkpointing
description: |
  Save full session context: git history, CLI consultations, Agent Teams activity,
  and discover reusable skill patterns — all in one run. No flags needed.
  Maintains a rolling PROGRESS.md (latest 5 checkpoint summaries) and runs the
  context-refresh skill at the end to compact the conversation.
  Run at session end, after major milestones, or when you want to capture learnings.
metadata:
  short-description: Full session checkpoint with rolling PROGRESS.md and context-refresh
---

# Checkpointing — Full Session Recording and Pattern Discovery

**Record all session activity and discover reusable patterns. Run everything, every time.**

## What It Does (Every Time)

```
/checkpointing
    ↓
┌─────────────────────────────────────────────────────────────┐
│  0. Find previous checkpoint timestamp                       │
│     → newest file in .claude/checkpoints/                    │
│                                                              │
│  1. Claude writes the "## サマリ" block (5 subsections)       │
│     → covers everything since the previous checkpoint        │
│     → saved to .claude/checkpoints/.pending-summary.md       │
│                                                              │
│  2. Run checkpoint.py --summary-file <path>                  │
│     ├── Collect git / CLI / Agent Teams / design data        │
│     ├── Write .claude/checkpoints/YYYY-MM-DD-HHMMSS.md        │
│     │   (PROGRESS-SUMMARY block at top + collected data)     │
│     ├── Regenerate PROGRESS.md (rolling latest 5, newest 1st)│
│     ├── Ensure Zone-C PROGRESS.md link in CLAUDE.md          │
│     └── Emit .analyze-prompt.md sidecar                      │
│                                                              │
│  3. Discover Skill Patterns                                  │
│     → Subagent analyzes the .analyze-prompt.md               │
│     → Suggests reusable skills → user reviews                │
│                                                              │
│  4. Review DESIGN.md (要件定義書) update need                │
│     → Reflect on this session's design-level changes         │
│       (requirements / architecture / tech choices / decisions)│
│     → If warranted, invoke the design-tracker skill to update│
│       the relevant DESIGN.md sections                        │
│                                                              │
│  5. Run context-refresh skill (the "compact" step)           │
│     → Compact the conversation / Zone C using the checkpoint │
│                                                              │
│  6. Delete the temporary .pending-summary.md                 │
└─────────────────────────────────────────────────────────────┘
```

## Usage

```bash
# Everything. No flags needed.
/checkpointing

# Optional: only look at recent work
/checkpointing --since "2026-02-08"
```

When the skill runs, Claude first writes a user-facing summary file, then passes
it to the script:

```bash
# Claude writes .claude/checkpoints/.pending-summary.md first, then:
python .claude/skills/checkpointing/checkpoint.py \
  --summary-file .claude/checkpoints/.pending-summary.md
```

If `--summary-file` is omitted, the script auto-generates the summary from the
collected git/CLI/Teams data (backward compatible, but with less narrative
detail in the "どういうやり取りをユーザーと行ったのか" section).

## What Gets Captured

### Git Activity

- Commits (hash, message, date)
- File changes (created, modified, deleted + line counts)
- Branch information

### CLI Consultations

- Codex consultations (prompt, success/failure)

### Agent Teams Activity

- Team composition (Lead + Teammates, roles)
- Shared task list state (completed, in-progress, pending)
- File ownership per teammate
- Communication patterns (who messaged whom, about what)
- Team effectiveness signals (tasks completed vs stuck, file conflicts)

### Teammate Work Logs

- Each Teammate's work log from `.claude/logs/agent-teams/{team-name}/{teammate}.md`
- Contains: Summary, Tasks Completed, Files Modified, Key Decisions, Communication with Teammates, Issues Encountered
- Written by each Teammate upon completing all assigned tasks
- Only present when Agent Teams were used (`/start-feature`, `/team-implement`, `/team-review`)

### Design Decisions

- Changes to `.claude/docs/DESIGN.md` since last checkpoint
- New entries in Key Decisions table

## Checkpoint Format

Each checkpoint opens with a user-facing "## サマリ" block wrapped in
`<!-- PROGRESS-SUMMARY:START -->` / `<!-- PROGRESS-SUMMARY:END -->` markers.
PROGRESS.md is rebuilt from the content between those markers. The five
subsection headings are fixed and stay in Japanese (this is a user-facing
session record):

```markdown
# Checkpoint 2026-02-08-153000

<!-- PROGRESS-SUMMARY:START -->
## サマリ

### 何をしたのか
- {bullet list of what was accomplished}

### どういうやり取りをユーザーと行ったのか
- {user-centric, chronological: what the user asked, how they decided}

### どうやったのか
- {approach / means — subagents, Codex, Agent Teams usage, etc.}

### 途中でどういう課題が起こったのか
- {blockers, mistakes, direction changes}

### 将来のアクション
- {next steps}
<!-- PROGRESS-SUMMARY:END -->

## Summary
- **Commits**: 12
- **Files changed**: 15 (10 modified, 4 created, 1 deleted)
- **Codex consultations**: 3
- **Agent Teams sessions**: 1 (3 teammates)
- **Tasks completed**: 8/10

## Git History

### Commits
- `abc1234` feat: redesign start-feature for Opus 4.6
- `def5678` feat: add team-implement skill
...

### File Changes
**Created:**
- `.claude/skills/team-implement/SKILL.md` (+180)
...

**Modified:**
- `CLAUDE.md` (+40, -25)
...

## CLI Consultations

### Codex (3 consultations)
- ✓ Design: Architecture for Agent Teams integration
- ✓ Debug: Task dependency resolution
- ✗ Review: (timeout)

## Agent Teams Activity

### Team: project-planning
**Composition:**
- Lead: Claude (orchestration)
- Researcher: Opus-powered (external research)
- Architect: Codex-powered (design decisions)

**Task List:**
- [x] Research library options (Researcher)
- [x] Design module architecture (Architect)
- [x] Validate API constraints (Researcher)
- [x] Finalize implementation plan (Architect)

**Communication Patterns:**
- Researcher → Architect: 3 messages (library constraints)
- Architect → Researcher: 2 messages (additional research requests)

**Effectiveness:**
- All tasks completed
- No file conflicts
- 2 design iterations triggered by research findings

## Teammate Work Logs

### Team: project-planning

#### researcher
*Source: `.claude/logs/agent-teams/project-planning/researcher.md`*

# Work Log: Researcher
## Summary
Researched httpx library constraints and API patterns for the new API client module.
## Tasks Completed
- [x] Research libraries: httpx supports HTTP/2 via h2 dependency
- [x] Find documentation: httpx connection pool defaults to 100
## Communication with Teammates
- → Architect: httpx connection pool limit of 100, HTTP/2 requires h2
- ← Architect: Requested HTTP/2 multiplexing research

#### architect
*Source: `.claude/logs/agent-teams/project-planning/architect.md`*

# Work Log: Architect
## Summary
Designed API client module architecture with HTTP/2 support.
## Design Decisions
- Use httpx[http2] for multiplexed connections: reduces latency for parallel requests
## Codex Consultations
- Connection pool sizing strategy: Codex recommended dynamic pool based on load
## Communication with Teammates
- → Researcher: Request HTTP/2 multiplexing research
- ← Researcher: httpx supports HTTP/2 via h2

## Design Decisions (New)
- Agent Teams for Research ↔ Design (bidirectional)

## Skill Pattern Suggestions

### Pattern 1: Research-Design Iteration (Confidence: 0.85)
**Evidence:** Researcher and Architect exchanged findings 5 times, each
exchange refined the design. This back-and-forth is a repeatable pattern.

**Suggested skill:** Already captured as /start-feature Phase 2.

### Pattern 2: Parallel File-Isolated Implementation (Confidence: 0.75)
**Evidence:** 3 implementers worked on separate modules with zero conflicts.
Module boundaries were defined by directory ownership.

**Suggested skill:** Already captured as /team-implement.

---
*Generated by checkpointing skill at 2026-02-08-153000*
```

## Rolling PROGRESS.md

After writing the checkpoint, the script fully regenerates `PROGRESS.md` at the
repository root from the **latest 5** checkpoints (newest first). Each entry
links to its full checkpoint and reproduces that checkpoint's PROGRESS-SUMMARY
subsections:

```markdown
# PROGRESS

> Auto-maintained by /checkpointing. Shows the most recent 5 checkpoints (newest first).
> Full checkpoints live in `.claude/checkpoints/` (git-ignored).

## [2026-02-08-153000](.claude/checkpoints/2026-02-08-153000.md)

### 何をしたのか
- ...
### 将来のアクション
- ...

## [2026-02-07-101500](.claude/checkpoints/2026-02-07-101500.md)
...
```

`PROGRESS.md` **is** tracked by git (unlike the checkpoints directory), so the
rolling summary travels with the repo and is the first thing `/start-feature`
reads on the next session.

## Zone-C-safe CLAUDE.md link

The script does **not** append a growing "Session History" to CLAUDE.md anymore.
Instead it idempotently ensures a single link block exists in **Zone C** (below
the `@orchestra:repo-boundary` marker):

```markdown
## Progress Tracker

Rolling progress summary (latest 5 checkpoints): [PROGRESS.md](./PROGRESS.md)
```

Zone A/B and the boundary marker lines are never touched.

## DESIGN.md Update Review (要件定義書)

PROGRESS.md captures *micro* work progress; `.claude/docs/DESIGN.md` is the
*macro* 要件定義書. After the checkpoint body and PROGRESS.md are written (and
**before** context-refresh), reflect on whether this session changed anything at
the design level:

- New or changed **機能要件 (Functional Requirements)**
- New or changed **非機能要件 (Non-Functional Requirements)**
- **アーキテクチャ (Architecture)** changes (components, agent roles, data flow)
- **技術選定 (Tech Stack & Rationale)** additions or swaps
- New **制約 (Constraints)**
- Significant **Key Decisions** made this session

If any of these changed, **invoke the design-tracker skill** to update the
corresponding DESIGN.md section(s). If nothing design-level changed, skip this
step. This keeps the macro requirements doc current without bloating PROGRESS.md.

Ordering: …→ PROGRESS.md → **DESIGN.md update review / design-tracker** →
context-refresh.

## Context Refresh (the "compact" step)

After the checkpoint, PROGRESS.md, the CLAUDE.md link, and the DESIGN.md update
review are all done, run the **context-refresh** skill. It uses the just-written
checkpoint to compact the conversation and Zone C, carrying forward only what the
next session needs. This is the final step of every `/checkpointing` run.

## Skill Pattern Discovery

The checkpoint is automatically analyzed to find reusable patterns:

**What it looks for:**
- Sequences of commits forming logical workflows
- File change patterns (e.g., test + implementation together)
- CLI consultation sequences (research → design → implement)
- Agent Teams coordination patterns (team composition, task sizing)
- Multi-step operations that could be templated

**Output:** Skill suggestions with confidence scores. High-confidence patterns (>= 0.8) that don't match existing skills are presented to the user for approval.

## Execution Flow

```
/checkpointing
    │
    ├─ 0. Identify previous checkpoint
    │     → newest file in .claude/checkpoints/ (its timestamp bounds the window)
    │
    ├─ 1. Claude writes the "## サマリ" block for everything since that timestamp
    │     → 5 fixed subsections; "どういうやり取りを..." is user-centric & chronological
    │     → also fold in subagent / Codex / Agent Teams activity under "どうやったのか"
    │     → save to .claude/checkpoints/.pending-summary.md
    │
    ├─ 2. Run checkpoint.py --summary-file .claude/checkpoints/.pending-summary.md
    │     → Generates .claude/checkpoints/YYYY-MM-DD-HHMMSS.md (summary + collected data)
    │     → Regenerates PROGRESS.md (rolling latest 5, newest first)
    │     → Ensures Zone-C PROGRESS.md link in CLAUDE.md
    │     → Emits .analyze-prompt.md sidecar
    │
    ├─ 3. Spawn subagent for skill pattern analysis
    │     → Reads the .analyze-prompt.md
    │     → Identifies reusable patterns → reports → user approves
    │
    ├─ 4. Review DESIGN.md (要件定義書) update need
    │     → Reflect on design-level changes this session
    │       (requirements / architecture / tech selection / key decisions)
    │     → If warranted, invoke the design-tracker skill to update
    │       the relevant DESIGN.md sections (機能要件 / 非機能要件 /
    │       アーキテクチャ / 技術選定 / 制約 / Key Decisions)
    │
    ├─ 5. Run the context-refresh skill (the "compact" step)
    │     → Compact conversation / Zone C using the new checkpoint
    │
    └─ 6. Delete the temporary .pending-summary.md
```

## When to Run

| Timing | Why |
|--------|-----|
| Before session ends | Record all activity, hand off to next session |
| After `/team-implement` completes | Capture team activity patterns |
| After `/team-review` completes | Capture review patterns |
| After major design decisions | Persist the decision context |
| When you notice recurring patterns | Opportunity to discover new skills |

## Notes

- Checkpoints accumulate in `.claude/checkpoints/` (already in `.gitignore`)
- `PROGRESS.md` (repo root) **is** tracked by git — it is the rolling, portable summary
- Each run also emits a `.analyze-prompt.md` sidecar next to the checkpoint for pattern discovery
- The CLAUDE.md update is a Zone-C-safe, idempotent PROGRESS.md link only — no growing Session History
- The `.pending-summary.md` temp file may be deleted after the run completes
- Log files themselves are not modified (read-only)
- Skill suggestions must always be reviewed by the user before adoption
- Agent Teams data is collected from `~/.claude/teams/` and `~/.claude/tasks/`
- The final step is always the **context-refresh** skill (the "compact")
