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

Mechanical checks: `.agents/skills/checkpointing/refresh_guard.py --mode check`
and `.agents/skills/init/detect_stack.py`.
