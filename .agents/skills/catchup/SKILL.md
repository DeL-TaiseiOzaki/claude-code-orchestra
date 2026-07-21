---
name: catchup
description: |
  Comprehensive onboarding for new or returning contributors.
  Scans repository artifacts (git history, AGENTS.md,
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

- You need a single focused answer (use `/feature` planning phases or direct research instead)
- You want to capture the current session for later (use `/checkpointing`)
- You want running design history (use `/design-tracker` or read `DESIGN.md` directly)

Full skill routing: root `AGENTS.md` section "Routing Policy".

## Workflow

```
Phase 1: COLLECT (collect_repo_state.py)
  Run the collector script -> single JSON of repo artifacts
    |
Phase 2: SYNTHESIZE (Claude Lead)
  Integrate findings into the GUIDE.md structure
    |
Phase 3: WRITE GUIDE.md
  Write to repository root, show diff summary to the user
```

---

## Phase 1: COLLECT (via collect_repo_state.py)

Run the bundled collector script. It aggregates git state, project identity,
rules/skills/agents frontmatter, design & research docs, checkpoints, and
CLI-log topics into one JSON document — replacing the old subagent scan and
keeping the orchestrator context light:

```bash
python3 .agents/skills/catchup/collect_repo_state.py
```

Optional flags: `--since "30 days ago"` (recent-work window), `--max-commits 100`.

The script degrades gracefully — any missing path becomes `null` / `"not present"`
and it still exits `0` (exit `1` only signals a non-git directory, with `git:null`).
Feed the emitted JSON to Phase 2 synthesis as its sole input.

Top-level JSON keys:

- `git` — log (oneline), branches, status, stash, diffstat.
- `identity` — README / AGENTS.md / pyproject.toml presence + first line.
- `rules` — rule files + first line each.
- `skills` — name + short-description (available slash commands).
- `agents` — name + specialization.
- `docs` — DESIGN.md presence, research & library listings (file + first line).
- `checkpoints` — newest 5 (file + first heading).
- `cli_tools` — recent Codex consultation topics.

For very large repos you may still hand this JSON to `general-purpose-opus`
for thematic grouping, but the mechanical collection is already done.

---

## Phase 2: SYNTHESIZE (Claude Lead)

Integrate the structured findings into the `GUIDE.md` layout below, applying
the shared routing policy loaded at session start. Do not re-read the source
files; rely on the collector output to preserve orchestrator context.

If an expected section is missing from the subagent output (e.g. no checkpoints exist), omit the corresponding section in `GUIDE.md` rather than leaving a placeholder.

---

## Phase 3: WRITE GUIDE.md

Write the final document to `GUIDE.md` at the repository root (overwrite if it exists). After writing:

1. Report the file path and line count to the user
2. List the top-level sections that were included
3. Note sections that were skipped because the source was absent

---

## `GUIDE.md` Structure

Write GUIDE.md following the template contract in `references/guide-template.md`; omit empty sections as the template's rules describe.

---

## Tips

- **Context discipline**: Phase 1 runs in a subagent so the orchestrator never loads raw logs or long docs. Only the structured summary comes back.
- **Idempotent**: `GUIDE.md` is regenerated from sources each run. Do not edit it by hand — update the underlying sources (AGENTS.md, DESIGN.md, etc.) and re-run.
- **`.gitignore` awareness**: `.agents/checkpoints/` and `.agents/logs/` are gitignored. On a fresh clone they will be absent; the skill handles this gracefully.
- **Language**: `GUIDE.md` content itself follows the project's user-facing language convention (Japanese for this repository), while code identifiers and command names stay in English.
