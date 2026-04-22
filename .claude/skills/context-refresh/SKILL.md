---
name: context-refresh
description: |
  User-invoked maintenance skill that compresses long-running working state.
  Archives older entries from CLAUDE.md Zone C, `.claude/checkpoints/`, and
  `.claude/docs/research/`, then regenerates a Work Evolution narrative and
  Archive Index in Zone C so future sessions stay context-light.
  Run when Zone C, checkpoint count, or research notes have grown large
  (typical trigger: CLAUDE.md > ~400 lines, checkpoints > 10 files, or
  visible duplication in Session History).
metadata:
  short-description: Compress CLAUDE.md Zone C and archive old checkpoints/research
disable-model-invocation: true
---

# Context Refresh

**Maintenance skill that keeps long-running working state slim by archiving older entries and regenerating a compact Work Evolution + Archive Index inside CLAUDE.md Zone C.**

This skill is the counterweight to `/checkpointing`, `/start-feature`, `/add-feature`, and `/troubleshoot`, all of which append to Zone C and to `.claude/checkpoints/` / `.claude/docs/research/` over time. Without periodic compression, those areas crowd the orchestrator's context budget.

## Purpose

- Move stale checkpoints, research notes, and old `Current Project|Feature|Bug Fix` blocks into archive directories.
- Rewrite Zone C in-place so it contains only the latest active work plus a structured **Work Evolution** narrative and an **Archive Index** that points at archived material.
- Preserve everything that `/catchup` and other downstream skills depend on (latest 5 checkpoints, archive pointers, current work blocks).

## When to Use

- CLAUDE.md exceeds ~400 lines or Zone C scrolls off-screen.
- `.claude/checkpoints/` contains more than ~10 files.
- `.claude/docs/research/` accumulated multiple completed-feature notes that are no longer being edited.
- The user explicitly invokes `/context-refresh` after a project milestone.

## When Not to Use

- A session is mid-flight and the latest checkpoints are still being referenced — let `/checkpointing` finish first.
- Zone B (Repository Identity) needs editing — use `/init`.
- You only want a snapshot for a returning contributor — use `/catchup`.
- Research notes are still actively edited by Researcher teammates — wait for the team to finish.

## Invariants

1. **Zone safety**: Touch ONLY Zone C (below `@orchestra:repo-boundary`). Never modify Zone A (above `@orchestra:template-boundary`) or Zone B (between the two markers). If either marker is missing, stop and ask the user to run `./scripts/update.sh`; do not hand-insert markers.
2. **Latest 5 checkpoints are sacred**: `/catchup` reads them. They must remain in `.claude/checkpoints/` (not archived) regardless of age.
3. **Dry-run first**: This skill performs destructive moves and rewrites. The default behaviour is to compute and display the plan, then request explicit approval via `AskUserQuestion`. Silent approval fallback is prohibited.
4. **Delegate scanning**: Reading every checkpoint and every research file is large-scale investigation. Delegate to a `general-purpose` subagent (Opus 1M context). The orchestrator only consumes a structured summary.
5. **No new append-only logs**: This skill must not create its own running log. Execution traces belong in the next `/checkpointing` run.

## Compressed Zone C Layout (Output Contract)

After this skill runs, Zone C must conform to:

```markdown
## Work Evolution
- 2026-01..02: <topic summary>
- 2026-03: <topic summary>
- 2026-04 (latest): <topic summary>

## Archive Index
| Path | Period | Contents |
|---|---|---|
| `.claude/checkpoints/archive/2026-01.md` | 2026-01 | N sessions, key topics |
| `.claude/docs/archive/projects-2026-Q1.md` | 2026-Q1 | feat-x, feat-y |
| `.claude/docs/research/archive/{feature}.md` | ... | ... |

## Current Project: {latest only}
...

## Current Feature: {latest only}
...

## Current Bug Fix: {latest only}
...

## Session History
### YYYY-MM (latest month only)
- entry
- entry
```

Older `Current Project|Feature|Bug Fix` blocks and older `Session History` months are folded into Work Evolution + Archive Index, then the source rows are removed from Zone C.

## Archive Destinations

Create directories on demand with `mkdir -p`:

- `.claude/checkpoints/archive/YYYY-MM.md` — month-aggregated checkpoint summaries.
- `.claude/docs/archive/projects-YYYY-Qn.md` — quarter-aggregated `Current Project|Feature|Bug Fix` blocks.
- `.claude/docs/research/archive/{feature}.md` — research notes whose feature is no longer active.

---

## Phase 1 — Scan (Opus Subagent)

Delegate inventory to a `general-purpose` subagent. The orchestrator must not read raw checkpoints or full research files itself.

### Subagent Brief

```
You are preparing an inventory for the /context-refresh skill. Do NOT
modify or move any file. Return a structured summary only.

## Sources to scan

### CLAUDE.md Zone C (only the area below `@orchestra:repo-boundary`)
- List every section heading currently present
- For each `## Current Project|Feature|Bug Fix` block: title, last update date
  (infer from git log on CLAUDE.md if no inline date), 3-line gist
- For `## Session History`: list each `### YYYY-MM-DD` entry with one-line gist
- For any existing `## Work Evolution` / `## Archive Index`: capture verbatim

### Checkpoints
- Path: `.claude/checkpoints/*.md` (NOT including `archive/`)
- Sort by filename (timestamped). Mark the newest 5 as PROTECTED.
- For older files: filename, date, 1-line summary (from the `## Summary` block).

### Research notes
- Path: `.claude/docs/research/*.md` (NOT including `archive/`)
- For each file: filename, last-modified date, 1-line topic summary,
  and whether the feature still appears in Zone C `Current ...` blocks.

### Existing archives
- Path: `.claude/checkpoints/archive/`, `.claude/docs/archive/`,
  `.claude/docs/research/archive/`
- List filenames and 1-line description of contents (so we can append
  rather than overwrite).

## Return format

```markdown
### Zone C Inventory
- Sections present: ...
- Current blocks: <table: title | date | gist>
- Session History entries: <table: date | gist>
- Existing Work Evolution: <verbatim or "none">
- Existing Archive Index: <verbatim or "none">

### Checkpoints
- Protected (latest 5): <list of filenames>
- Archive candidates: <table: filename | date | summary>

### Research notes
- Active (still referenced): <list>
- Archive candidates: <table: filename | last-modified | topic | reason>

### Existing archives
- <table: path | period | contents>

### Anomalies
- Missing markers, malformed sections, or unparseable files.
```

If a path does not exist, write "not present" instead of fabricating data.
```

Run the subagent in the foreground. The returned summary is the sole input to Phase 2.

---

## Phase 2 — Plan (dry-run)

Compute the rewrite plan from the Phase 1 summary. Do not write any file yet.

1. **Bucket archive candidates** by month (checkpoints), quarter (Current blocks), and feature (research notes).
2. **Compose new Work Evolution** by merging:
   - Any existing `## Work Evolution` bullets (kept verbatim, deduplicated).
   - One new bullet per archive bucket, formatted `- YYYY-MM: <topic summary>` (or `- YYYY-Qn: <topic summary>` for project blocks).
   - Mark the latest period with `(latest)`.
3. **Compose new Archive Index** as a markdown table with one row per archive file that will exist after the run (existing archives + new ones being created).
4. **Compose new Zone C body** in this order:
   - `## Work Evolution`
   - `## Archive Index`
   - The single most-recent `## Current Project`, `## Current Feature`, `## Current Bug Fix` block (drop older instances).
   - `## Session History` containing only the latest month's entries.
5. **Compose file-move plan** as a list of `(source, destination, append-or-create)` tuples. For month-aggregated checkpoints, the operation is "merge into a single archive file".

### Preview Format

Present the plan to the user as:

```markdown
## /context-refresh — Dry Run

### CLAUDE.md Zone C diff
- Lines before: {n}
- Lines after (estimated): {n}
- Sections removed: <list>
- Sections rewritten: Work Evolution, Archive Index
- Sections preserved: <list>

### File moves ({count})
- `.claude/checkpoints/2026-01-12-*.md` (3 files)
    -> merge into `.claude/checkpoints/archive/2026-01.md`
- `.claude/docs/research/feat-x.md`
    -> `.claude/docs/research/archive/feat-x.md`
- `## Current Project: feat-x` (from CLAUDE.md)
    -> append to `.claude/docs/archive/projects-2026-Q1.md`

### New Work Evolution
- 2026-01..02: ...
- 2026-03: ...
- 2026-04 (latest): ...

### New Archive Index
| Path | Period | Contents |
|---|---|---|
| ... | ... | ... |
```

---

## Phase 3 — Confirm

Use `AskUserQuestion` to obtain explicit approval. Do not proceed without it; do not assume silence means approval.

Question template:

```yaml
question: "Apply this context-refresh plan?"
multiSelect: false
options:
  - label: "proceed"
    description: "Execute the moves and rewrite CLAUDE.md Zone C as previewed."
  - label: "adjust"
    description: "Skip / keep specific items. I will tell you which."
  - label: "cancel"
    description: "Discard the plan and make no changes."
```

If the user picks `adjust`, ask a follow-up `AskUserQuestion` listing each archive candidate as a multi-select keep/move toggle, then re-run Phase 2 with the filtered set before re-confirming.

If the user picks `cancel`, exit without writing anything.

---

## Phase 4 — Execute

Only enter this phase after `proceed` is selected. Operate with the `Edit` and `Write` tools; do not use `sed` or `awk`.

### 4.1 Create archive directories

```bash
mkdir -p .claude/checkpoints/archive
mkdir -p .claude/docs/archive
mkdir -p .claude/docs/research/archive
```

### 4.2 Aggregate checkpoint archives (per month)

For each month bucket, write or append to `.claude/checkpoints/archive/YYYY-MM.md`:

```markdown
# Archived Checkpoints — YYYY-MM

## YYYY-MM-DD-HHMMSS
{verbatim contents of original checkpoint, or its `## Summary` section if the file is large}

## YYYY-MM-DD-HHMMSS
...
```

Idempotency rule: before appending, scan the existing archive file for the source timestamp header. Skip any timestamp already present (this guarantees re-runs are safe).

After successful aggregation, delete the original checkpoint files. The latest 5 (PROTECTED list from Phase 1) must remain untouched.

### 4.3 Move research notes

For each research archive candidate, move the file:

- Source: `.claude/docs/research/{feature}.md`
- Destination: `.claude/docs/research/archive/{feature}.md`

If the destination already exists (rare: re-archived feature), append the source contents under a `## Re-archived YYYY-MM-DD` heading instead of overwriting.

### 4.4 Quarterly project archive

Append removed `## Current Project|Feature|Bug Fix` blocks to `.claude/docs/archive/projects-YYYY-Qn.md`:

```markdown
# Archived Project Blocks — YYYY-Qn

## YYYY-MM-DD — {original heading}
{original block contents}
```

Use the same idempotency rule (check for the dated heading before appending).

### 4.5 Rewrite CLAUDE.md Zone C

1. Read CLAUDE.md once.
2. Verify `@orchestra:template-boundary` and `@orchestra:repo-boundary` are both present. Abort if either is missing.
3. Locate the `@orchestra:repo-boundary` block. Everything strictly below it (after the closing ━ line) is Zone C.
4. Replace Zone C with the body composed in Phase 2 using the `Edit` tool, anchoring on the boundary box's last `━` line plus the first non-empty Zone C line. If the anchor is not unique, fall back to a single `Write` call that re-emits the file with Zone A + Zone B + boundary markers preserved verbatim.
5. Do not touch any byte at or above the `@orchestra:repo-boundary` marker.

---

## Phase 5 — Verify

After Phase 4 completes:

1. Run `wc -l CLAUDE.md` and report new line count vs previous.
2. List the contents of `.claude/checkpoints/`, `.claude/checkpoints/archive/`, `.claude/docs/research/`, `.claude/docs/research/archive/`, `.claude/docs/archive/`.
3. Re-grep for both boundary markers to confirm they survived intact:

   ```bash
   grep -c "@orchestra:template-boundary" CLAUDE.md
   grep -c "@orchestra:repo-boundary" CLAUDE.md
   ```

   Both must return `1`.
4. Provide a single user-facing recap paragraph (Japanese, per `.claude/rules/language.md`) summarising: lines removed, files archived, latest checkpoints preserved, and where the archives live.

---

## Interaction with Other Skills

| Skill | Relationship |
|---|---|
| `/checkpointing` | Continues to append to Zone C `Session History` and `.claude/checkpoints/`. `/context-refresh` cleans these up later. No coordination needed. |
| `/catchup` | Reads the latest 5 checkpoints (always preserved) and the new `Archive Index` to find older material. Compatible by design. |
| `/start-feature`, `/add-feature`, `/troubleshoot` | Continue to append `## Current Project|Feature|Bug Fix` blocks to Zone C. `/context-refresh` retires older blocks into `.claude/docs/archive/`. |
| `/init` | Operates only on Zone B. No conflict. |
| `/design-tracker` | Operates only on `.claude/docs/DESIGN.md`. No conflict. |

---

## Safety Checklist

Run through this list before any write in Phase 4:

1. [ ] `@orchestra:template-boundary` present in CLAUDE.md.
2. [ ] `@orchestra:repo-boundary` present in CLAUDE.md.
3. [ ] Phase 1 subagent summary received and parsed without anomalies.
4. [ ] Phase 2 dry-run preview displayed to the user.
5. [ ] `AskUserQuestion` returned `proceed` (not silent, not assumed).
6. [ ] PROTECTED list (latest 5 checkpoints) excluded from every move/delete.
7. [ ] Archive destination directories created with `mkdir -p`.
8. [ ] Idempotency check applied to every archive append (no duplicate timestamp headers).
9. [ ] Zone A and Zone B byte ranges untouched (verified via marker re-grep in Phase 5).
10. [ ] Final recap reported to the user with new CLAUDE.md line count.
