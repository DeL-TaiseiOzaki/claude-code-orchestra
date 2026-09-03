# Agent State Contract

`AGENTS.md` is an immutable, minimal bootstrap that every CLI agent may load.
`CLAUDE.md` is a relative symlink to it. Repository-specific and cross-session
state belongs in `.agents/STATE.md`, never in either bootstrap path.

## State Ownership

| Section | Owner / writers | Content |
|---------|-----------------|---------|
| `## Repository Identity` | `/init` only | Thin identity plus a pointer to `.agents/docs/DESIGN.md`. |
| `## Progress Tracker` | `/checkpointing` | Idempotent link to `PROGRESS.md`. |
| Working blocks | `/feature`, `/troubleshoot`, `/checkpointing`, and manual notes | Current project, feature, and bug-fix context. |

The installer and updater preserve `.agents/STATE.md`. They recognize legacy
`AGENTS.md` and `CLAUDE.md` boundary markers only to migrate old Zone B/C
content into this file. New bootstraps must not contain boundary markers.

## Mechanical Checks

`.agents/skills/checkpointing/refresh_guard.py` has five modes, which are
different operations rather than aliases. Read-only unless stated:

| Mode | What it does |
|------|--------------|
| `--mode check` | Structure counts (`# Agent State` and `## Progress Tracker` exactly once) plus the work-block inventory. Nothing else is collected. |
| `--mode plan` | `check` plus the compaction preview: which `## Current *` blocks would be pruned, which sections are preserved, and the *suggested* research-note `move_plan` — a heuristic that needs explicit user approval, never an action. |
| `--mode compose` | `plan` plus the candidate state written to `.agents/logs/composed-state.md`. Writes only that draft. |
| `--mode apply` | Replaces `.agents/STATE.md` under the Writer Safety Contract: dry-run by default, `--apply` to write, atomic `os.replace`, `--expect-hash <sha256>` concurrent-modification guard, and validation of the composed bytes before replacing. |
| `--mode verify` | Compares the on-disk state against the candidate and reports `compaction_applied`. |

Compaction is lossless by construction — only redundant `## Current *` blocks
are removed, every other section (manual notes included) is preserved verbatim
in document order, and any section that would still be lost is reported in
`sections_dropped` and aborts the run.

Exit codes: `0` ok or preview · `1` bad arguments · `2` structure invalid, a
non-work-block section would be dropped, or `--mode verify` found the compaction
not applied · `3` `.agents/STATE.md` unreadable, write failure, or an
`--expect-hash` mismatch. Pass `--now ISO8601` to stamp a fixed timestamp.

Structural contract for the document itself:
`.agents/skills/_shared/validate_doc.py --contract state-doc --file .agents/STATE.md`
(requires `## Main Agent` and `## Progress Tracker`; `## Repository Identity` is
inserted by its writer when missing, so it is not required). Stack and shared
state: `.agents/skills/init/detect_stack.py`.
