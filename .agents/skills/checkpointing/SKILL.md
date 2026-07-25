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
- `.agents/logs/`: drafts, previews, work logs, and CLI activity.
- `.agents/docs/research/`: research notes; inactive notes may be archived only
  after user approval.

Both scripts write nothing without `--apply`. Every default run produces preview
files under `.agents/logs/` and leaves `PROGRESS.md` and `.agents/STATE.md`
untouched.

## Full Checkpoint

1. Determine the time window from the newest checkpoint, or use all available
   history when none exists.
2. Gather the user requests and decisions from the current conversation, git
   changes, CLI logs, team work logs, and relevant design changes.
3. Write a Japanese five-part summary containing:
   `何をしたのか`, `どういうやり取りをユーザーと行ったのか`, `どうやったのか`,
   `途中でどういう課題が起こったのか`, and `将来のアクション`.
   This is the irreducible judgment in the skill and is never generated: a
   missing, empty, stale, or incomplete summary aborts the run with exit `2`.
4. Save the summary to `.agents/logs/pending-summary.md`, then preview:

   ```bash
   python3 .agents/skills/checkpointing/checkpoint.py \
     --summary-file .agents/logs/pending-summary.md
   ```

   Exit `0` reports `result: preview` and three preview files
   (`checkpoint-preview-*`, `progress-preview-*`, `state-preview-*` under
   `.agents/logs/`). Exit `1` is a bad `--since` / `--now`; exit `2` is a
   summary or shared-state contract violation; exit `3` is a timestamp
   collision, a concurrent modification, or a write failure.
5. Review the three previews, then write for real:

   ```bash
   python3 .agents/skills/checkpointing/checkpoint.py \
     --summary-file .agents/logs/pending-summary.md \
     --apply --consume-summary --json
   ```

   `--consume-summary` deletes the draft on success, so the next session cannot
   silently embed this session's summary. `--json` emits the single payload
   `{ok, result, checkpoint_path, prompt_path, progress_path, progress_entries,
   state_path, state_updated, summary_validated, summary_consumed, commits,
   files_changed, cli_consultations, agent_teams, work_logs, collector_errors,
   skipped_records, warnings, artifacts}`; without it the same facts are printed
   as prose. Quote `collector_errors` and `warnings` verbatim when reporting —
   a failed collector is not an empty session.
6. Confirm the shared-state invariant mechanically rather than by reading:

   ```bash
   python3 .agents/skills/checkpointing/refresh_guard.py --mode check
   ```

   Exit `0` means exactly one `# Agent State` and one `## Progress Tracker`
   heading; exit `2` means the structure is invalid.
7. Review whether durable architecture decisions belong in
   `.agents/docs/DESIGN.md`; use `/design-tracker` when warranted.
8. Run the Compact Phase below.

## Compact Phase

The compact phase keeps only the newest `## Current Project`,
`## Current Feature`, and `## Current Bug Fix` block of each category. **Every
other section is preserved verbatim in document order** — `## Main Agent`,
`## Repository Identity`, `## Progress Tracker`, and any manual notes, which
`.agents/rules/agent-state.md` explicitly sanctions. A section that would still
be lost is reported in `sections_dropped` and aborts the run with exit `2`.

1. Inspect the state, the compaction preview, and the suggested archive moves:

   ```bash
   python3 .agents/skills/checkpointing/refresh_guard.py --mode plan
   ```

   Reports `blocks_pruned`, `sections_preserved`, `sections_dropped`,
   `research_notes`, and `move_plan`. `move_plan` entries carry
   `suggested: true`: they come from a stem-mention heuristic and are never a
   decision.

2. Write the candidate state to a draft:

   ```bash
   python3 .agents/skills/checkpointing/refresh_guard.py --mode compose
   ```

3. Review `.agents/logs/composed-state.md` and the reported move plan.
4. Ask for approval before replacing `.agents/STATE.md` or moving research
   notes. Never delete checkpoint files or regenerate `PROGRESS.md` here.
5. After approval, apply the compaction with the script — never by hand:

   ```bash
   python3 .agents/skills/checkpointing/refresh_guard.py --mode apply
   python3 .agents/skills/checkpointing/refresh_guard.py --mode apply --apply
   ```

   The first call previews to `.agents/logs/state-compaction-preview-*.md` and
   reports `state_hash_before`. The second writes atomically, refuses if
   `.agents/STATE.md` changed since it was read, and validates the composed
   bytes before replacing. Pass `--expect-hash <state_hash_before>` to pin the
   exact revision that was approved.

6. Confirm the compaction landed:

   ```bash
   python3 .agents/skills/checkpointing/refresh_guard.py --mode verify
   ```

   `verify` compares the on-disk state against a freshly composed candidate and
   reports `compaction_applied`. Exit `2` means redundant work blocks remain.

## Safety Gates

- Root `AGENTS.md` and `CLAUDE.md` are never modified.
- State structure must contain exactly one `# Agent State` heading and one
  `## Progress Tracker` heading.
- Archive destinations use `.agents/docs/research/archive/`; append when a
  destination already exists.
- All destructive moves require an explicit preview and user approval.
- Report the checkpoint path, state blocks pruned, sections preserved, research
  notes archived, validation result, and remaining risks in Japanese.
