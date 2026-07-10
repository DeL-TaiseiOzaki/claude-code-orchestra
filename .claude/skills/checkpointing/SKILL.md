---
name: checkpointing
description: |
  Save full session context: git history, CLI consultations, Agent Teams activity,
  and discover reusable skill patterns — all in one run. No flags needed.
  Maintains a rolling PROGRESS.md (latest 5 checkpoint summaries) and ends with a
  compact phase that prunes stale CLAUDE.md Zone C work blocks and compacts the
  conversation (also available standalone via --compact-only, replacing the old
  /context-refresh skill).
  Run at session end, after major milestones, or when you want to capture learnings.
metadata:
  short-description: Full session checkpoint with rolling PROGRESS.md and final compact phase
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
│  5. Compact Phase (see "Compact Phase" section below)        │
│     → Prune Zone C work blocks / compact the conversation    │
│       using the just-written checkpoint                      │
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

# Compact only: skip steps 0-4/6 and run just the Compact Phase
# (replaces the old standalone /context-refresh — use when CLAUDE.md
# exceeds ~400 lines or Zone C has multiple stale work blocks)
/checkpointing --compact-only
```

When the skill runs (full mode), Claude first writes a user-facing summary file,
then passes it to the script:

```bash
# Claude writes .claude/checkpoints/.pending-summary.md first, then:
python .claude/skills/checkpointing/checkpoint.py \
  --summary-file .claude/checkpoints/.pending-summary.md
```

If `--summary-file` is omitted, the script auto-generates the summary from the
collected git/CLI/Teams data (backward compatible, but with less narrative
detail in the "どういうやり取りをユーザーと行ったのか" section).

With `--compact-only`, skip the checkpoint recording entirely and jump straight
to the **Compact Phase** at the end of this document. All of its approval gates
still apply.

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
- Follows the shared work-log format (`.claude/skills/_shared/work-log-format.md`): Summary, Tasks Completed, role-specific sections, Communication with Teammates, Issues Encountered
- Written by each Teammate upon completing all assigned tasks
- Only present when Agent Teams were used (`/feature` greenfield mode, `/team-execute`)

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
- `abc1234` feat: redesign feature skill for Opus 4.6
- `def5678` feat: add team-execute skill
...

### File Changes
**Created:**
- `.claude/skills/team-execute/SKILL.md` (+180)
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

(work log embedded verbatim — shared format: `.claude/skills/_shared/work-log-format.md`)
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

(work log embedded verbatim — shared format: `.claude/skills/_shared/work-log-format.md`)
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

**Suggested skill:** Already captured as /feature Phase 2G (greenfield).

### Pattern 2: Parallel File-Isolated Implementation (Confidence: 0.75)
**Evidence:** 3 implementers worked on separate modules with zero conflicts.
Module boundaries were defined by directory ownership.

**Suggested skill:** Already captured as /team-execute Phase 1.

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
rolling summary travels with the repo and is the first thing `/feature`
reads on the next session.

## Zone-C-safe CLAUDE.md link

The script does **not** append a growing "Session History" to CLAUDE.md anymore.
Instead it idempotently ensures a single link block exists in **Zone C** (zone
contract: `.claude/rules/claude-md-zones.md`):

```markdown
## Progress Tracker

Rolling progress summary (latest 5 checkpoints): [PROGRESS.md](./PROGRESS.md)
```

Zone A/B and the boundary marker lines are never touched.

## DESIGN.md Update Review (要件定義書)

PROGRESS.md captures *micro* work progress; `.claude/docs/DESIGN.md` is the
*macro* 要件定義書. After the checkpoint body and PROGRESS.md are written (and
**before** the Compact Phase), reflect on whether this session changed anything at
the design level:

- New or changed **機能要件 (Functional Requirements)**
- New or changed **非機能要件 (Non-Functional Requirements)**
- **アーキテクチャ (Architecture)** changes (components, agent roles, data flow)
- **技術選定 (Tech Stack & Rationale)** additions or swaps
- New **制約 (Constraints)**
- Significant **Key Decisions** made this session

If any of these changed, **invoke the design-tracker skill** to update the
corresponding DESIGN.md section(s) — the design-tracker now uses
`python3 .claude/skills/_shared/update_design.py` for mechanical appends
(decisions and section content). If nothing design-level changed, skip this
step. This keeps the macro requirements doc current without bloating PROGRESS.md.

Ordering: …→ PROGRESS.md → **DESIGN.md update review / design-tracker** →
Compact Phase.

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
/checkpointing            (--compact-only jumps straight to step 5)
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
    ├─ 5. Compact Phase (below)
    │     → Prune Zone C / compact conversation using the new checkpoint
    │
    └─ 6. Delete the temporary .pending-summary.md
```

## When to Run

| Timing | Why |
|--------|-----|
| Before session ends | Record all activity, hand off to next session |
| After `/team-execute` completes | Capture team implementation & review patterns |
| After major design decisions | Persist the decision context |
| When you notice recurring patterns | Opportunity to discover new skills |
| CLAUDE.md > ~400 lines / stale Zone C blocks | Run `--compact-only` (Compact Phase alone) |

## Notes

- Checkpoints accumulate in `.claude/checkpoints/` (already in `.gitignore`)
- `PROGRESS.md` (repo root) **is** tracked by git — it is the rolling, portable summary
- Each run also emits a `.analyze-prompt.md` sidecar next to the checkpoint for pattern discovery
- The CLAUDE.md update is a Zone-C-safe, idempotent PROGRESS.md link only — no growing Session History
- The `.pending-summary.md` temp file may be deleted after the run completes
- Log files themselves are not modified (read-only)
- Skill suggestions must always be reviewed by the user before adoption
- Agent Teams data is collected from `~/.claude/teams/` and `~/.claude/tasks/`
- The final step of every full run is the **Compact Phase** below

---

# Compact Phase

**The final phase of every `/checkpointing` run — and the whole run when invoked
as `/checkpointing --compact-only` (the replacement for the old standalone
`/context-refresh` skill). It keeps long-running working state slim: prunes stale
work blocks from CLAUDE.md Zone C, compacts the live conversation, and optionally
archives no-longer-active research notes.**

This phase is the counterweight to `/feature` and `/troubleshoot`, which append
`## Current Project|Feature|Bug Fix` blocks to Zone C over time.

## Division of Responsibility (read first)

The orchestrator's cross-session memory is split across three artifacts. The
Compact Phase only owns the first:

| Artifact | Owner | Compact Phase action |
|---|---|---|
| CLAUDE.md **Zone C** work blocks + the live conversation | Compact Phase | **Prune & compact** |
| `PROGRESS.md` (rolling latest-5 checkpoint summaries, git-tracked) | checkpoint recording (steps 0-4) | **Do not touch** — read-only reference |
| `.claude/checkpoints/*.md` (per-session detail) | checkpoint recording (steps 0-4) | **Do not touch / do not delete** |

There is **no** running activity log in Zone C anymore — the checkpoint recording
stopped appending one. Cross-session progress is carried entirely by PROGRESS.md
(which links to the full checkpoints). The Compact Phase must never recreate such
a per-session log in Zone C, regenerate PROGRESS.md, or delete checkpoint files.

## Purpose

- Retire stale `## Current Project|Feature|Bug Fix` blocks from Zone C (keep only the latest active work).
- Compact the live conversation so the next turn starts from a lean context, carrying forward only what is still needed (the just-written checkpoint already preserves the detail).
- Optionally archive `.claude/docs/research/` notes whose feature is no longer active.
- Leave PROGRESS.md, the Zone C `## Progress Tracker` link, and `.claude/checkpoints/` exactly as the checkpoint recording left them.

## When to Use `--compact-only`

- CLAUDE.md exceeds ~400 lines or Zone C scrolls off-screen with multiple stale work blocks.
- `.claude/docs/research/` accumulated multiple completed-feature notes that are no longer being edited.
- The user explicitly asks for a context compact after a project milestone.

## When NOT to Run the Compact Phase

- A session is mid-flight and the current work blocks are still being referenced — finish the work first.
- Zone B (Repository Identity) needs editing — use `/init`.
- You only want a snapshot for a returning contributor — use `/catchup`.
- Research notes are still actively edited by Researcher teammates — wait for the team to finish.

Full skill routing: CLAUDE.md §3 Routing Policy.

## Invariants

1. **Zone safety**: Touch ONLY Zone C — zone contract and markers-missing rule per `.claude/rules/claude-md-zones.md`.
2. **Progress Tracker link is sacred**: The `## Progress Tracker` block in Zone C (the link to `PROGRESS.md`) must remain intact. Do not rewrite or remove it.
3. **Checkpoints & PROGRESS.md are off-limits**: Never delete, move, or rewrite files in `.claude/checkpoints/`, and never regenerate `PROGRESS.md`. They are owned by the checkpoint recording (steps 0-4).
4. **Dry-run first**: This phase performs destructive prunes and rewrites. The default behaviour is to compute and display the plan, then request explicit approval via `AskUserQuestion`. Silent approval fallback is prohibited.
5. **Delegate scanning**: Reading every research file and every Zone C block is large-scale investigation. `refresh_guard.py` handles the mechanical inventory; if raw-file reading is ever needed, delegate to a `general-purpose` subagent (Opus 1M context). The orchestrator only consumes a structured summary.
6. **No new append-only logs**: This phase must not create its own running log of any kind in Zone C. Execution traces belong in the next `/checkpointing` run.

## Compacted Zone C Layout (Output Contract)

After this phase runs, Zone C must conform to:

```markdown
## Progress Tracker

Rolling progress summary (latest 5 checkpoints): [PROGRESS.md](./PROGRESS.md)

## Current Project: {latest only}
...

## Current Feature: {latest only}
...

## Current Bug Fix: {latest only}
...
```

Older `Current Project|Feature|Bug Fix` blocks are summarized into the relevant checkpoint/PROGRESS.md context (already captured by the checkpoint recording) and then removed from Zone C. The `## Progress Tracker` link block is preserved verbatim. No `## Work Evolution`, `## Archive Index`, or running activity-log sections are introduced — past activity is reachable through PROGRESS.md and the checkpoints it links to.

## Archive Destinations

Create directories on demand with `mkdir -p`:

- `.claude/docs/research/archive/{feature}.md` — research notes whose feature is no longer active.

(Checkpoints and project-block archives are not managed here; the checkpoint recording and PROGRESS.md retain that history.)

---

## Compact 1 — Scan (mechanical, via refresh_guard.py)

Run the bundled guard script to inventory Zone C and research notes
deterministically. It is **non-writing** (dry-run) and replaces the old
subagent scan — no raw-file reading needed:

```bash
python3 .claude/skills/checkpointing/refresh_guard.py --mode plan
```

Interpret the JSON:

- `markers.ok` — if false (exit code **2**), STOP per
  `.claude/rules/claude-md-zones.md` (user runs `./scripts/update.sh`).
- `claude_md.total_lines` / `zone_c_lines` — size accounting.
- `progress_tracker_present` — must remain true through the whole run.
- `zone_c_blocks[]` — every `## Current Project|Feature|Bug Fix` block with its
  `line`, inferred `date`, and `keep` flag (latest of each category = `keep:true`,
  older duplicates = `keep:false`).
- `legacy_sections[]` — obsolete running-history headings to remove.
- `research_notes[]` — each note with `active` (still referenced in Zone C).
- `move_plan[]` — computed archive moves (`create`/`append`); **never executed here**.

Exit codes: `0` ok · `2` markers missing (abort) · `3` CLAUDE.md unreadable.

The script owns the mechanical inventory. Your judgment is still required to write
a short gist for each retired block, decide which archive candidates are genuinely
stale, and compose the conversation compaction (Compact 4).

---

## Compact 2 — Plan (dry-run)

`refresh_guard.py --mode plan` already computed the deterministic plan (blocks to
keep vs drop via the `keep` flag, `legacy_sections`, and the research `move_plan`).
Turn that JSON into a user-facing preview — do **not** write any file yet:

1. Keep the `keep:true` blocks; list `keep:false` blocks + `legacy_sections` as removals.
2. **Compose the new Zone C body**: `## Progress Tracker` (preserved verbatim — the
   link to PROGRESS.md) followed by the kept `## Current *` blocks in order.
3. Use `move_plan[]` as-is for the research archive moves (source → destination,
   `create`/`append` mode).

### Preview Format

Present the plan to the user as:

```markdown
## Compact Phase — Dry Run

### CLAUDE.md Zone C diff
- Lines before: {n}
- Lines after (estimated): {n}
- Sections removed: <list of retired work blocks + any legacy sections>
- Sections preserved: Progress Tracker, latest Current * blocks

### Research note moves ({count})
- `.claude/docs/research/feat-x.md`
    -> `.claude/docs/research/archive/feat-x.md`

### Conversation compaction
- Summary of what will be carried forward vs dropped from the live context.
```

---

## Compact 3 — Confirm

Use `AskUserQuestion` to obtain explicit approval. Do not proceed without it; do not assume silence means approval.

Question template:

```yaml
question: "Apply this compact plan?"
multiSelect: false
options:
  - label: "proceed"
    description: "Prune Zone C, compact the conversation, and move research notes as previewed."
  - label: "adjust"
    description: "Skip / keep specific items. I will tell you which."
  - label: "cancel"
    description: "Discard the plan and make no changes."
```

If the user picks `adjust`, ask a follow-up `AskUserQuestion` listing each removal/archive candidate as a multi-select keep/move toggle, then re-run Compact 2 with the filtered set before re-confirming.

If the user picks `cancel`, exit without writing anything.

---

## Compact 4 — Execute

Only enter this step after `proceed` is selected. Operate with the `Edit` and `Write` tools; do not use `sed` or `awk`.

### 4.1 Create research archive directory (only if needed)

```bash
mkdir -p .claude/docs/research/archive
```

### 4.2 Move research notes

For each research archive candidate, move the file:

- Source: `.claude/docs/research/{feature}.md`
- Destination: `.claude/docs/research/archive/{feature}.md`

If the destination already exists (rare: re-archived feature), append the source contents under a `## Re-archived YYYY-MM-DD` heading instead of overwriting.

### 4.3 Rewrite CLAUDE.md Zone C

1. Read CLAUDE.md once.
2. Verify `@orchestra:template-boundary` and `@orchestra:repo-boundary` are both present. Abort if either is missing.
3. Locate the `@orchestra:repo-boundary` block. Everything strictly below it (after the closing ━ line) is Zone C.
4. Replace Zone C with the body composed in Compact 2 using the `Edit` tool, anchoring on the boundary box's last `━` line plus the first non-empty Zone C line. If the anchor is not unique, fall back to a single `Write` call that re-emits the file with Zone A + Zone B + boundary markers preserved verbatim.
5. The `## Progress Tracker` link block must survive verbatim. Do not touch any byte at or above the `@orchestra:repo-boundary` marker.

### 4.4 Compact the conversation

Summarize the live conversation down to what the next turn needs (current goal, active decisions, open follow-ups). The just-written checkpoint already holds the full detail, so the conversation summary can be aggressive without losing recoverable history.

---

## Compact 5 — Verify

After Compact 4 completes, re-run the guard in verify mode:

```bash
python3 .claude/skills/checkpointing/refresh_guard.py --mode verify
```

Confirm from the JSON (and exit code):

1. `markers.ok` is true and the script exits `0` (not `2`) — both boundary markers
   survived intact.
2. `progress_tracker_present` is true — the `## Progress Tracker` link block is still
   in Zone C.
3. `claude_md.total_lines` — report the new line count vs the previous one.
4. Manually confirm `.claude/docs/research/` and `.claude/docs/research/archive/`
   reflect the planned moves, and that `.claude/checkpoints/` and `PROGRESS.md` are
   unchanged (they were never touched).
5. Provide a single user-facing recap paragraph (Japanese, per `.claude/rules/language.md`) summarising: lines removed from Zone C, work blocks retired, research notes archived, and confirmation that PROGRESS.md / checkpoints were left intact.

---

## Interaction with Other Skills

| Skill | Relationship |
|---|---|
| `/catchup` | Reads PROGRESS.md and the latest checkpoints (always preserved) to reconstruct history. Compatible by design. |
| `/feature`, `/troubleshoot` | Append `## Current Project|Feature|Bug Fix` blocks to Zone C. The Compact Phase retires the older ones. |
| `/init` | Operates only on Zone B. No conflict. |
| `/design-tracker` | Operates only on `.claude/docs/DESIGN.md`. No conflict. |

---

## Compact Phase Safety Checklist

Run through this list before any write in Compact 4:

1. [ ] `@orchestra:template-boundary` present in CLAUDE.md.
2. [ ] `@orchestra:repo-boundary` present in CLAUDE.md.
3. [ ] Compact 1 guard JSON received and parsed without anomalies.
4. [ ] Compact 2 dry-run preview displayed to the user.
5. [ ] `AskUserQuestion` returned `proceed` (not silent, not assumed).
6. [ ] `## Progress Tracker` link block preserved in the new Zone C body.
7. [ ] No file in `.claude/checkpoints/` is moved or deleted; `PROGRESS.md` is not regenerated.
8. [ ] Research archive destination directory created with `mkdir -p` (only if moves are planned).
9. [ ] Zone A and Zone B byte ranges untouched (verified via marker re-grep in Compact 5).
10. [ ] Final recap reported to the user with new CLAUDE.md line count.
