---
name: context-refresh
description: |
  Maintenance skill that compacts long-running working state so future sessions
  stay context-light. Prunes stale `Current Project|Feature|Bug Fix` work blocks
  from CLAUDE.md Zone C, compresses the live conversation, and (optionally)
  archives old research notes. Cross-session progress lives in PROGRESS.md and the
  per-session detail in `.claude/checkpoints/` — both are owned by /checkpointing
  and are NOT regenerated here. Run when Zone C has grown (typical trigger:
  CLAUDE.md > ~400 lines or multiple stale work blocks) or as the final step of a
  /checkpointing run.
metadata:
  short-description: Compact CLAUDE.md Zone C work blocks and the live conversation
disable-model-invocation: true
---

# Context Refresh

**Maintenance skill that keeps long-running working state slim: it prunes stale work blocks from CLAUDE.md Zone C, compacts the live conversation, and optionally archives no-longer-active research notes.**

This skill is the counterweight to `/start-feature`, `/add-feature`, and `/troubleshoot`, all of which append `## Current Project|Feature|Bug Fix` blocks to Zone C over time. It is normally run as the **final step of `/checkpointing`** (the "compact" step), but can also be invoked directly when Zone C has grown large.

## Division of Responsibility (read first)

The orchestrator's cross-session memory is split across three artifacts. context-refresh only owns the first:

| Artifact | Owner | context-refresh action |
|---|---|---|
| CLAUDE.md **Zone C** work blocks + the live conversation | context-refresh | **Prune & compact** |
| `PROGRESS.md` (rolling latest-5 checkpoint summaries, git-tracked) | `/checkpointing` | **Do not touch** — read-only reference |
| `.claude/checkpoints/*.md` (per-session detail) | `/checkpointing` | **Do not touch / do not delete** |

There is **no** running activity log in Zone C anymore — `/checkpointing` stopped appending one. Cross-session progress is carried entirely by PROGRESS.md (which links to the full checkpoints). context-refresh must never recreate such a per-session log in Zone C, regenerate PROGRESS.md, or delete checkpoint files.

## Purpose

- Retire stale `## Current Project|Feature|Bug Fix` blocks from Zone C (keep only the latest active work).
- Compact the live conversation so the next turn starts from a lean context, carrying forward only what is still needed (the just-written checkpoint already preserves the detail).
- Optionally archive `.claude/docs/research/` notes whose feature is no longer active.
- Leave PROGRESS.md, the Zone C `## Progress Tracker` link, and `.claude/checkpoints/` exactly as `/checkpointing` left them.

## When to Use

- As the final step of a `/checkpointing` run (the conversation/Zone C "compact" step).
- CLAUDE.md exceeds ~400 lines or Zone C scrolls off-screen with multiple stale work blocks.
- `.claude/docs/research/` accumulated multiple completed-feature notes that are no longer being edited.
- The user explicitly invokes `/context-refresh` after a project milestone.

## When Not to Use

- A session is mid-flight and the current work blocks are still being referenced — finish the work first.
- Zone B (Repository Identity) needs editing — use `/init`.
- You only want a snapshot for a returning contributor — use `/catchup`.
- You want to persist this session's activity — that is `/checkpointing` (context-refresh runs *after* it, not instead of it).
- Research notes are still actively edited by Researcher teammates — wait for the team to finish.

## Invariants

1. **Zone safety**: Touch ONLY Zone C (below `@orchestra:repo-boundary`). Never modify Zone A (above `@orchestra:template-boundary`) or Zone B (between the two markers). If either marker is missing, stop and ask the user to run `./scripts/update.sh`; do not hand-insert markers.
2. **Progress Tracker link is sacred**: The `## Progress Tracker` block in Zone C (the link to `PROGRESS.md`) must remain intact. Do not rewrite or remove it.
3. **Checkpoints & PROGRESS.md are off-limits**: Never delete, move, or rewrite files in `.claude/checkpoints/`, and never regenerate `PROGRESS.md`. They are owned by `/checkpointing`.
4. **Dry-run first**: This skill performs destructive prunes and rewrites. The default behaviour is to compute and display the plan, then request explicit approval via `AskUserQuestion`. Silent approval fallback is prohibited.
5. **Delegate scanning**: Reading every research file and every Zone C block is large-scale investigation. Delegate to a `general-purpose` subagent (Opus 1M context). The orchestrator only consumes a structured summary.
6. **No new append-only logs**: This skill must not create its own running log of any kind in Zone C. Execution traces belong in the next `/checkpointing` run.

## Compacted Zone C Layout (Output Contract)

After this skill runs, Zone C must conform to:

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

Older `Current Project|Feature|Bug Fix` blocks are summarized into the relevant checkpoint/PROGRESS.md context (already captured by `/checkpointing`) and then removed from Zone C. The `## Progress Tracker` link block is preserved verbatim. No `## Work Evolution`, `## Archive Index`, or running activity-log sections are introduced — past activity is reachable through PROGRESS.md and the checkpoints it links to.

## Archive Destinations

Create directories on demand with `mkdir -p`:

- `.claude/docs/research/archive/{feature}.md` — research notes whose feature is no longer active.

(Checkpoints and project-block archives are not managed here; `/checkpointing` and PROGRESS.md retain that history.)

---

## Phase 1 — Scan (Opus Subagent)

Delegate inventory to a `general-purpose` subagent. The orchestrator must not read raw research files or every Zone C block itself.

### Subagent Brief

```
You are preparing an inventory for the /context-refresh skill. Do NOT
modify, move, or delete any file. Return a structured summary only.

## Sources to scan

### CLAUDE.md Zone C (only the area below `@orchestra:repo-boundary`)
- List every section heading currently present.
- Confirm the `## Progress Tracker` link block is present (it must be preserved).
- For each `## Current Project|Feature|Bug Fix` block: title, last update date
  (infer from git log on CLAUDE.md if no inline date), 3-line gist.
- Flag any leftover legacy running-history sections — `## Work Evolution`,
  `## Archive Index`, or any per-session activity-log heading (these are
  obsolete and should be removed).

### Research notes
- Path: `.claude/docs/research/*.md` (NOT including `archive/`)
- For each file: filename, last-modified date, 1-line topic summary,
  and whether the feature still appears in a Zone C `Current ...` block.

### Existing research archives
- Path: `.claude/docs/research/archive/`
- List filenames and 1-line description of contents (so we can append
  rather than overwrite).

## Return format

```markdown
### Zone C Inventory
- Sections present: ...
- Progress Tracker link present: yes/no
- Current blocks: <table: title | date | gist>
- Legacy sections to remove: <list or "none">

### Research notes
- Active (still referenced): <list>
- Archive candidates: <table: filename | last-modified | topic | reason>

### Existing research archives
- <table: filename | contents>

### Anomalies
- Missing markers, malformed sections, or unparseable files.
```

If a path does not exist, write "not present" instead of fabricating data.
```

Run the subagent in the foreground. The returned summary is the sole input to Phase 2.

---

## Phase 2 — Plan (dry-run)

Compute the rewrite plan from the Phase 1 summary. Do not write any file yet.

1. **Identify the single most-recent** `## Current Project`, `## Current Feature`, and `## Current Bug Fix` block to keep; mark older instances for removal.
2. **Mark obsolete sections** (`## Work Evolution`, `## Archive Index`, or any legacy per-session activity-log heading) for removal if present.
3. **Bucket research archive candidates** (features no longer in any Zone C `Current ...` block).
4. **Compose new Zone C body** in this order:
   - `## Progress Tracker` (preserved verbatim — the link to PROGRESS.md).
   - The single most-recent `## Current Project`, `## Current Feature`, `## Current Bug Fix` block (drop older instances).
5. **Compose research-move plan** as a list of `(source, destination, append-or-create)` tuples.

### Preview Format

Present the plan to the user as:

```markdown
## /context-refresh — Dry Run

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

## Phase 3 — Confirm

Use `AskUserQuestion` to obtain explicit approval. Do not proceed without it; do not assume silence means approval.

Question template:

```yaml
question: "Apply this context-refresh plan?"
multiSelect: false
options:
  - label: "proceed"
    description: "Prune Zone C, compact the conversation, and move research notes as previewed."
  - label: "adjust"
    description: "Skip / keep specific items. I will tell you which."
  - label: "cancel"
    description: "Discard the plan and make no changes."
```

If the user picks `adjust`, ask a follow-up `AskUserQuestion` listing each removal/archive candidate as a multi-select keep/move toggle, then re-run Phase 2 with the filtered set before re-confirming.

If the user picks `cancel`, exit without writing anything.

---

## Phase 4 — Execute

Only enter this phase after `proceed` is selected. Operate with the `Edit` and `Write` tools; do not use `sed` or `awk`.

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
4. Replace Zone C with the body composed in Phase 2 using the `Edit` tool, anchoring on the boundary box's last `━` line plus the first non-empty Zone C line. If the anchor is not unique, fall back to a single `Write` call that re-emits the file with Zone A + Zone B + boundary markers preserved verbatim.
5. The `## Progress Tracker` link block must survive verbatim. Do not touch any byte at or above the `@orchestra:repo-boundary` marker.

### 4.4 Compact the conversation

Summarize the live conversation down to what the next turn needs (current goal, active decisions, open follow-ups). The just-written checkpoint already holds the full detail, so the conversation summary can be aggressive without losing recoverable history.

---

## Phase 5 — Verify

After Phase 4 completes:

1. Run `wc -l CLAUDE.md` and report new line count vs previous.
2. Confirm the `## Progress Tracker` link block is still present in Zone C.
3. List the contents of `.claude/docs/research/` and `.claude/docs/research/archive/`.
4. Confirm `.claude/checkpoints/` and `PROGRESS.md` are unchanged (they were never touched).
5. Re-grep for both boundary markers to confirm they survived intact:

   ```bash
   grep -c "@orchestra:template-boundary" CLAUDE.md
   grep -c "@orchestra:repo-boundary" CLAUDE.md
   ```

   Both must return `1`.
6. Provide a single user-facing recap paragraph (Japanese, per `.claude/rules/language.md`) summarising: lines removed from Zone C, work blocks retired, research notes archived, and confirmation that PROGRESS.md / checkpoints were left intact.

---

## Interaction with Other Skills

| Skill | Relationship |
|---|---|
| `/checkpointing` | Owns PROGRESS.md and `.claude/checkpoints/`. Calls `/context-refresh` as its final "compact" step. context-refresh reads, but never rewrites, those artifacts. |
| `/catchup` | Reads PROGRESS.md and the latest checkpoints (always preserved) to reconstruct history. Compatible by design. |
| `/start-feature`, `/add-feature`, `/troubleshoot` | Append `## Current Project|Feature|Bug Fix` blocks to Zone C. `/context-refresh` retires the older ones. |
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
6. [ ] `## Progress Tracker` link block preserved in the new Zone C body.
7. [ ] No file in `.claude/checkpoints/` is moved or deleted; `PROGRESS.md` is not regenerated.
8. [ ] Research archive destination directory created with `mkdir -p` (only if moves are planned).
9. [ ] Zone A and Zone B byte ranges untouched (verified via marker re-grep in Phase 5).
10. [ ] Final recap reported to the user with new CLAUDE.md line count.
