# Agent State Contract

Root `AGENTS.md` is the single always-loaded bootstrap and belongs to the
project: `/start-project` converts the shipped skeleton once, and the project
owns it afterwards (`scripts/update.sh` replaces it only while it is
byte-identical to a known shipped skeleton). The main agent's contract is
`.claude/rules/orchestration.md`. There is no `CLAUDE.md`: Claude Code skips
`AGENTS.md` while any `CLAUDE.md`, `CLAUDE.local.md`, or `.claude/CLAUDE.md`
exists in the working directory or a parent, so install and update back such
files up, remove them, and record the backups for `/start-project` to offer
merging. Never run Claude Code's built-in `/init`, which creates `CLAUDE.md`.
Cross-session state belongs in `.claude/STATE.md`.

## State Ownership

| Section | Owner / writers | Content |
|---------|-----------------|---------|
| `## Repository Identity` | `/start-project` only | Thin identity plus a pointer to `.claude/docs/DESIGN.md`. |
| `## Pending Instruction Merge` | `scripts/install.sh` / `scripts/update.sh` write; `/start-project` resolves | Backups of removed `CLAUDE.md`-family files and replaced `AGENTS.md` content awaiting a merge decision. |
| `## Progress Tracker` | `/checkpointing` | Idempotent link to `PROGRESS.md`. |
| Working blocks | `/feature`, `/troubleshoot`, `/checkpointing`, and manual notes | Current project, feature, and bug-fix context. |

The installer and updater preserve `.claude/STATE.md`. They recognize legacy
`AGENTS.md` and `CLAUDE.md` boundary markers only to migrate old Zone B/C
content into this file. New bootstraps must not contain boundary markers.

## Mechanical Checks

`.claude/skills/checkpointing/refresh_guard.py` has five modes, which are
different operations rather than aliases. Read-only unless stated:

| Mode | What it does |
|------|--------------|
| `--mode check` | Structure counts (`# Agent State` and `## Progress Tracker` exactly once) plus the work-block inventory. Nothing else is collected. |
| `--mode plan` | `check` plus the compaction preview: which `## Current *` blocks would be pruned, which sections are preserved, and the *suggested* research-note `move_plan` — a heuristic that needs explicit user approval, never an action. |
| `--mode compose` | `plan` plus the candidate state written to `.claude/logs/composed-state.md`. Writes only that draft. |
| `--mode apply` | Replaces `.claude/STATE.md` under the Writer Safety Contract: dry-run by default, `--apply` to write, atomic `os.replace`, `--expect-hash <sha256>` concurrent-modification guard, and validation of the composed bytes before replacing. |
| `--mode verify` | Compares the on-disk state against the candidate and reports `compaction_applied`. |

Compaction is lossless by construction — only redundant `## Current *` blocks
are removed, every other section (manual notes included) is preserved verbatim
in document order, and any section that would still be lost is reported in
`sections_dropped` and aborts the run.

Exit codes: `0` ok or preview · `1` bad arguments · `2` structure invalid, a
non-work-block section would be dropped, or `--mode verify` found the compaction
not applied · `3` `.claude/STATE.md` unreadable, write failure, or an
`--expect-hash` mismatch. Pass `--now ISO8601` to stamp a fixed timestamp.

Structural contract for the document itself:
`.claude/skills/_shared/validate_doc.py --contract state-doc --file .claude/STATE.md`
(requires `## Main Agent` and `## Progress Tracker`; `## Repository Identity` is
inserted by its writer when missing, so it is not required). Stack and shared
state: `.claude/skills/start-project/detect_stack.py`, which also reports the
`AGENTS.md` state and any instruction file that would shadow it.
