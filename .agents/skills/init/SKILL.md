---
name: init
description: Analyze project structure, populate .agents/docs/DESIGN.md, and write the thin Repository Identity section in .agents/STATE.md.
disable-model-invocation: true
---

# Initialize Project Configuration

Initialize project-owned context without expanding the always-loaded root
`AGENTS.md`.

## Ownership

- `.agents/docs/DESIGN.md` owns macro requirements and design.
- `.agents/STATE.md` owns the active main agent, thin repository identity, and
  cross-session working state.
- Root `AGENTS.md` is template-owned and must not be edited by this skill.
- `PROGRESS.md` is maintained by `/checkpointing`.

## Steps

### 1. Collect stack evidence

Run:

```bash
python3 .agents/skills/init/detect_stack.py
```

The script reports **evidence, not conclusions**. It never infers a command:
`evidence.tools` names the `[tool.*]` tables declared in `pyproject.toml`,
`evidence.scripts` carries the verbatim `package.json` script strings, and
`evidence.dependencies` gives each dependency's `name`, its raw `spec`, the
`manifest` it came from, and the `key` it was declared under
(`project.dependencies`, `project.optional-dependencies.dev`,
`dependency-groups.lint`, `devDependencies.x`, …). **You** decide from that
evidence which commands and libraries are real; do not copy a command the
repository does not declare.

Read these fields before writing anything:

- `warnings` — a manifest that could not be read, decoded, or parsed. Non-empty
  means the evidence is partial, even though the exit code is `0`.
- `evidence.parsed_manifests` / `evidence.unparsed_manifests` — "parsed and
  empty" versus "present but not parsed for dependencies" (`Cargo.toml`,
  `go.mod`, `setup.py`, `Makefile`, `Dockerfile`).
- `manifests` — every checked filename with an explicit `true`/`false`, so
  "checked and absent" is never mistaken for "never checked".
- `agent_bootstrap` — `agents_md`, `claude_symlink`, `state_md`,
  `claude_agents_link`, `claude_skills_link`.

Exit codes: `0` normal · `1` bad arguments, including a `--project-root` that is
not a directory · `2` the agent bootstrap is invalid — `ok: false` and `error`
name the failed markers. Exit `2` covers the root bootstrap, the `CLAUDE.md`
symlink, shared state, **and both native discovery symlinks** (`.claude/agents`
and `.claude/skills` must be symlinks to `../.agents/…`; a dangling one silently
disables all native agent and skill discovery). Stop and repair the installation
— `bash .agents/check.sh` diagnoses the same links — before writing context.

### 2. Ask for missing context

Ask the user for the project purpose, code-language preference, and additional
conventions only when repository evidence does not already answer them.

### 3. Populate DESIGN.md

DESIGN.md is written through the typed writer, never by hand: it is a
user-owned document, and `update_design.py` supplies the dry-run preview, the
atomic replace, the concurrent-modification hash guard, per-cell `|` escaping,
and validation of the composed document before it replaces the original.

Write the input JSON to `.agents/logs/init-design-input.json` and use only the
typed keys:

| DESIGN.md target | Input key | Row fields |
|------------------|-----------|-----------|
| `## 機能要件 (Functional Requirements)` | `requirements` | `id`, `requirement`, `priority`, `notes` |
| `## 非機能要件 (Non-Functional Requirements)` | `nfr` | `category`, `requirement`, `metric` |
| `## 技術選定 (Tech Stack & Rationale)` | `tech_choices` | `area`, `technology`, `rationale`, `alternatives` |
| `## アーキテクチャ (Architecture)` Agent Roles table | `agent_roles` | `agent`, `role`, `responsibilities` |
| `## Key Decisions` | `decisions` | `decision`, `rationale`, `alternatives` (date is stamped for you) |
| Prose sections (背景・目的, スコープ, 制約, TODO / Open Questions) | `section_updates` | `heading`, `content` |

```bash
python3 .agents/skills/_shared/update_design.py --input .agents/logs/init-design-input.json
# Read the preview at preview_file, then apply:
python3 .agents/skills/_shared/update_design.py --input .agents/logs/init-design-input.json --apply --require-change
```

Completion test — `result == "applied"` **and** (`decisions_appended > 0` or any
`rows_appended` value `> 0` or `sections_updated` non-empty). `--require-change`
turns a `no-op` into exit `2`, so an all-duplicate or all-empty input can never
be reported as populated. Exit `2` also means the DESIGN.md structure is invalid;
exit `3` means DESIGN.md changed underneath the writer — re-read and retry.

Fill only claims supported by repository evidence or the user's answers, and do
not fabricate requirements. Later incremental design changes go through
`/design-tracker`, which uses the same writer.

### 4. Update Repository Identity

`## Repository Identity` is also written through its typed writer, which
replaces only that section's body and aborts if `## Main Agent`,
`## Progress Tracker`, or any working block would be lost. Write
`.agents/logs/init-identity-input.json`:

```json
{"identity": "One sentence naming what this repository is."}
```

```bash
python3 .agents/skills/_shared/append_state_block.py --type repository-identity \
  --input .agents/logs/init-identity-input.json
python3 .agents/skills/_shared/append_state_block.py --type repository-identity \
  --input .agents/logs/init-identity-input.json --apply
```

The writer emits the `<!-- Managed by /init. Re-run /init to refresh. -->`
marker and the `docs/DESIGN.md` pointer itself, so the input carries the identity
sentence only. Do not add a heading, a `---`, or a second paragraph — the writer
rejects them (exit `1`). Confirm `result: "applied"`, `structure_ok: true`, and
`progress_tracker_preserved: true` (a real check: it aborts the write with exit
`2` when an existing tracker line was deleted or rewritten).

### 5. Re-verify and report

Re-run the closing gate, and report the JSON verdicts rather than a claim:

```bash
python3 .agents/skills/init/detect_stack.py
python3 .agents/skills/_shared/validate_doc.py --contract design-doc --file .agents/docs/DESIGN.md
python3 .agents/skills/_shared/validate_doc.py --contract state-doc --file .agents/STATE.md
```

All three must exit `0` with `ok: true`. `detect_stack.py` confirms shared state
and the discovery symlinks still resolve; the two contracts confirm the documents
this skill just wrote still have the sections every other skill reads them for —
`exit 2` names the missing section. Checking the two documents directly is
stricter than inferring their health from the detector, which is why the detector
alone is no longer the gate.

Then review `.agents/rules/` for irrelevant stack-specific rules, but do
not remove them without user approval. Report the evidence you used and the
evidence you rejected, the two updated files, any `warnings`, and your
recommendations in Japanese.
