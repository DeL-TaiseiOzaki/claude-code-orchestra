---
name: checkpointing
description: Save session activity, rebuild rolling PROGRESS.md, and compact stale working blocks in .agents/STATE.md.
metadata:
  short-description: Full session checkpoint and shared-state compaction
---

# Checkpointing

Capture durable session context without growing the always-loaded root
`AGENTS.md`. Canonical state and artifacts live under `.agents/`.

## Owned Paths

- `.agents/checkpoints/`: full timestamped checkpoints; never deleted by the
  compact phase.
- `PROGRESS.md`: latest five checkpoint summaries.
- `.agents/STATE.md`: one Progress Tracker link and current working blocks.
- `.agents/logs/`: drafts, work logs, and CLI activity.
- `.agents/docs/research/`: research notes; inactive notes may be archived only
  after user approval.

## Full Checkpoint

1. Determine the time window from the newest checkpoint, or use all available
   history when none exists.
2. Gather the user requests and decisions from the current conversation, git
   changes, CLI logs, team work logs, and relevant design changes.
3. Write a Japanese five-part summary containing:
   `何をしたのか`, `どういうやり取りをユーザーと行ったのか`, `どうやったのか`,
   `途中でどういう課題が起こったのか`, and `将来のアクション`.
4. Save the summary to `.agents/checkpoints/.pending-summary.md`, then run:

   ```bash
   python3 .agents/skills/checkpointing/checkpoint.py \
     --summary-file .agents/checkpoints/.pending-summary.md
   ```

5. Confirm that a timestamped checkpoint and `PROGRESS.md` were updated and
   that `.agents/STATE.md` still contains exactly one Progress Tracker block.
6. Review whether durable architecture decisions belong in
   `.agents/docs/DESIGN.md`; use `/design-tracker` when warranted.
7. Run the Compact Phase below.

## Compact Phase

The compact phase keeps only the newest `## Current Project`,
`## Current Feature`, and `## Current Bug Fix` block of each category. It must
preserve `## Main Agent`, `## Repository Identity`, and `## Progress Tracker`.

1. Inspect the state and dry-run archive plan:

   ```bash
   python3 .agents/skills/checkpointing/refresh_guard.py --mode plan
   ```

2. Compose the candidate state:

   ```bash
   python3 .agents/skills/checkpointing/refresh_guard.py --mode compose
   ```

3. Review `.agents/logs/composed-state.md` and the reported research move plan.
4. Ask for approval before replacing `.agents/STATE.md` or moving research
   notes. Never delete checkpoint files or regenerate `PROGRESS.md` here.
5. After approved edits, run:

   ```bash
   python3 .agents/skills/checkpointing/refresh_guard.py --mode verify
   ```

## Safety Gates

- Root `AGENTS.md` and `CLAUDE.md` are never modified.
- State structure must contain exactly one `# Agent State` heading and one
  `## Progress Tracker` heading.
- Archive destinations use `.agents/docs/research/archive/`; append when a
  destination already exists.
- All destructive moves require an explicit preview and user approval.
- Report the checkpoint path, state blocks pruned, research notes archived,
  validation result, and remaining risks in Japanese.
