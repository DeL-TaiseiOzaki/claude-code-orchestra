---
name: catchup
description: |
  Comprehensive onboarding for new or returning contributors.
  Scans repository artifacts (git history, .agents/STATE.md,
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
  Run the collector script -> single JSON of every dataset the template needs
    |
Phase 2: SYNTHESIZE (Claude Lead)
  Turn that JSON into per-section prose — the judgment step
    |
Phase 3: ASSEMBLE (write_guide.py)
  Stamp, order, validate, and write GUIDE.md under the Writer Safety Contract
```

---

## Phase 1: COLLECT (via collect_repo_state.py)

```bash
python3 .agents/skills/catchup/collect_repo_state.py
```

Optional flags: `--since "30 days ago"` (recent-work window, passed to git),
`--max-commits 100`, `--claude-home DIR` (Agent Teams data root),
`--project-root DIR`.

Exit codes: `0` ok · `1` bad arguments · `2` not a git repository, or a
`SKILL.md`/agent frontmatter that yields neither a name nor a description ·
`3` a git subcommand failed inside a real repository. The payload always carries
top-level `ok` and `errors`; check those rather than assuming exit `0`.

Degradation is named, never silent: an absent file is `{"present": false}`, an
unreadable one carries an `error`, and a failed git subcommand is `null` plus an
entry in `git.errors` — distinct from `[]`, which means genuinely empty.

Top-level JSON keys:

- `git` — `log`, `branches`, `status`, `stash`, `diffstat`, `recent_stat`,
  `current_branch`, `errors`.
- `identity` — `README.md`, `AGENTS.md`, `pyproject.toml` presence + first line,
  plus `identity.state` with `main_agent`, `current_project`,
  `current_feature`, `current_bug_fix` read from `.agents/STATE.md`.
- `rules` — `{present, items[{file, first_line}]}`.
- `skills` — `{present, items[{name, short_description, file}],
  frontmatter_errors}`.
- `agents` — `{present, items[{name, specialization, model, file}],
  frontmatter_errors}`.
- `docs` — `design{present, placeholder, key_decisions[]}`, `research`,
  `libraries`.
- `env` — `manifests`, `scripts` (from `pyproject.toml`), `commands`
  (each with the `source` file it was quoted from), `errors`.
- `checkpoints` — newest 5 (file + first heading).
- `agent_teams` — `sessions[{name, members, tasks_total, tasks_completed}]`
  and in-repo `work_logs`.
- `cli_tools` — recent consultations for **every** tool, each tagged with
  `tool`, plus `skipped_lines`.

Feed the emitted JSON to Phase 2 as its sole input. For very large repos hand it
to `general-purpose-opus` for the thematic grouping.

---

## Phase 2: SYNTHESIZE (Claude Lead)

Turn the collected JSON into one markdown body per section of
`references/guide-template.md`. Do not re-read the source files; the collector
now gathers every dataset the template asks for, so re-reading only costs
context.

This phase is judgment and stays here: grouping commits into 3–7 themes, ranking
the top design decisions, and deciding which optional sections are worth a
reader's time have more than one defensible answer. `write_guide.py` deliberately
takes the prose as input rather than generating it.

Omit a section entirely when its source data is absent. Never leave a
`{placeholder}` — Phase 3 rejects them.

Write the bodies to a JSON file keyed by the section ids in
`references/guide-template.md`:

```json
{
  "what_is_this_project": "- **Purpose**: ...",
  "recent_work": "- ...",
  "capabilities": "### Slash commands\n\n| Command | Purpose |\n|---|---|\n...",
  "resume_work": "- **Environment setup**: `uv sync`"
}
```

---

## Phase 3: ASSEMBLE (via write_guide.py)

```bash
python3 .agents/skills/catchup/write_guide.py --input body.json
python3 .agents/skills/catchup/write_guide.py --input body.json --apply
```

The first call previews to `.agents/logs/guide-preview-*.md`; the second writes
`GUIDE.md` atomically, refuses if `GUIDE.md` changed since it was read, and
validates the composed document (`validate_doc.py --contract guide`) before
replacing it. `--now ISO8601` injects the date stamp; `--project-root DIR`
relocates the root.

The script owns the title, the `_Generated by /catchup on YYYY-MM-DD_` line, the
section order and fixed numbering, and the `_Sources:_` footer — do not supply
them in `--input`.

Payload: `{ok, guide_path, preview_path, sections_written, sections_omitted,
line_count, residual_placeholders, applied, result, artifacts}`. Exit codes:
`0` preview/applied · `1` bad args or unreadable `--input` · `2` unknown section
id, a missing required section (`what_is_this_project`, `recent_work`,
`capabilities`, `resume_work`), a residual `{placeholder}`, or a composed
document the `guide` contract rejects · `3` write failure or concurrent
modification.

Report `guide_path`, `line_count`, `sections_written`, and `sections_omitted`
from the payload rather than restating them from memory.

---

## `GUIDE.md` Structure

`references/guide-template.md` is the contract: it maps each section id to its
numbered heading, marks which four are required, and lists the collector fields
each one draws on. Section numbers never shift when an optional section is
omitted.

---

## Tips

- **Context discipline**: Phase 1 is a single script run, not a subagent scan —
  the orchestrator never loads raw logs or long docs. Only hand the JSON to a
  subagent when the synthesis itself is large.
- **Not byte-stable**: `GUIDE.md` is regenerated from sources each run, but its
  prose is LLM-authored, so two runs over identical sources produce different
  text and a noisy diff on a tracked root file. Do not edit it by hand — update
  the underlying sources (`.agents/STATE.md`, `DESIGN.md`, rules) and re-run.
- **`.gitignore` awareness**: `.agents/checkpoints/` and `.agents/logs/` are
  gitignored. On a fresh clone they will be absent; the collector reports that
  as `present: false` rather than failing.
- **Language**: `GUIDE.md` content follows the project's user-facing language
  convention (Japanese for this repository), while code identifiers and command
  names stay in English.
