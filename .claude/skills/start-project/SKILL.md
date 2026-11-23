---
name: start-project
description: Set up a project after installing Orchestra - convert root AGENTS.md into the project's own instructions, populate .claude/docs/DESIGN.md, and point STATE.md's Repository Identity at AGENTS.md. User-triggered only.
disable-model-invocation: true
---

# Start Project

Turn a fresh Orchestra install into this project's own setup. This is the
repository skill, invoked as `/start-project`; it is deliberately not named
`init`, because Claude Code's built-in `/init` creates `CLAUDE.md`, and any
`CLAUDE.md` stops Claude Code from loading `AGENTS.md`. Never run the built-in.

## Ownership

- Root `AGENTS.md` is the project's own document and the single source of the
  project identity, commands, and conventions. This skill converts the shipped
  skeleton once through `write_agents_md.py`; template updates never rewrite
  the converted file. Re-running the skill re-converts it from new facts.
- `.claude/docs/DESIGN.md` owns macro requirements and design.
- `.claude/STATE.md` owns the active main agent, a pointer to the project
  identity, and cross-session working state.
- `PROGRESS.md` is maintained by `/checkpointing`.

## Steps

### 1. Collect stack evidence

Run:

```bash
python3 .claude/skills/start-project/detect_stack.py
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
- `agent_bootstrap` — `agents_md`, `state_md`, `claude_agents_dir`,
  `claude_skills_dir`, `cli_subagent_contract`, `no_owned_instruction_shadowing`.
- `agents_md_state` — `skeleton` (not converted yet), `converted`,
  `unrecognized` (no `## Agent Roles` / `## Orchestra References` to carry
  forward: reinstall the skeleton), or `missing`.
- `instruction_shadowing` — `owned` / `shim` / `ancestor` lists, plus
  `bootstrap_warnings` for ancestor files the project cannot remove. Tell the
  user about every ancestor entry: Claude Code skips `AGENTS.md` while it exists.

Exit codes: `0` normal · `1` bad arguments, including a `--project-root` that is
not a directory · `2` the agent bootstrap is invalid — `ok: false` and `error`
name the failed markers. Exit `2` covers the root `AGENTS.md`, shared state, the
CLI-subagent contract, an owned `CLAUDE.md` / `CLAUDE.local.md` /
`.claude/CLAUDE.md` that shadows `AGENTS.md`, **and both native runtime
directories** (`.claude/agents` and `.claude/skills` must be real directories; a
missing one silently disables all native agent and skill discovery). Stop and
repair the installation — `bash scripts/update.sh` backs up and removes owned
shadowing files, and `bash scripts/check.sh` diagnoses the same layout — before
writing context.

### 2. Ask for missing context

Ask the user for the project purpose, the user and code languages, and
additional conventions only when repository evidence does not already answer
them.

Read the `## Pending Instruction Merge` section of `.claude/STATE.md`, if any.
`scripts/install.sh` and `scripts/update.sh` list there every `CLAUDE.md`,
`CLAUDE.local.md`, `.claude/CLAUDE.md`, or replaced `AGENTS.md` they backed up
and removed, with the backup path. Read each backup, propose which project rules
belong in `AGENTS.md` `## Conventions` (template copies of the old Orchestra
contract need no merge: that policy now lives in `.claude/rules/`), and ask the
user to approve the merge before writing anything.

### 3. Populate DESIGN.md

DESIGN.md is written through the typed writer, never by hand: it is a
user-owned document, and `update_design.py` supplies the dry-run preview, the
atomic replace, the concurrent-modification hash guard, per-cell `|` escaping,
and validation of the composed document before it replaces the original.

Write the input JSON to `.claude/logs/start-project-design-input.json` and use only the
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
python3 .claude/skills/_shared/update_design.py --input .claude/logs/start-project-design-input.json
# Read the preview at preview_file, then apply:
python3 .claude/skills/_shared/update_design.py --input .claude/logs/start-project-design-input.json --apply --require-change
```

Completion test — `result == "applied"` **and** (`decisions_appended > 0` or any
`rows_appended` value `> 0` or `sections_updated` non-empty). `--require-change`
turns a `no-op` into exit `2`, so an all-duplicate or all-empty input can never
be reported as populated. Exit `2` also means the DESIGN.md structure is invalid;
exit `3` means DESIGN.md changed underneath the writer — re-read and retry.

Fill only claims supported by repository evidence or the user's answers, and do
not fabricate requirements. Later incremental design changes go through
`/design-tracker`, which uses the same writer.

### 4. Convert AGENTS.md

Root `AGENTS.md` is written through its typed writer, never by hand. Write
`.claude/logs/start-project-agents-input.json` with facts supported by the
evidence or the user's answers only (commands the repository declares, approved
merged conventions):

```json
{"project_name": "Acme API",
 "identity": "One paragraph: what this repository is and who it serves.",
 "layout": ["`src/` - application code", "`tests/` - pytest suite"],
 "commands": [{"purpose": "Test", "command": "uv run pytest"}],
 "conventions": ["Keep public APIs backwards compatible."],
 "languages": {"user": "Japanese", "code": "English"}}
```

```bash
python3 .claude/skills/start-project/write_agents_md.py \
  --input .claude/logs/start-project-agents-input.json
# Show the user preview_file, then apply with the reviewed hash:
python3 .claude/skills/start-project/write_agents_md.py \
  --input .claude/logs/start-project-agents-input.json \
  --apply --expect-hash <sha256_before> \
  [--resolve-pending-merge <pending_merge_sha256>]
```

The writer carries `## Agent Roles` and `## Orchestra References` forward from
the current file, validates the result (required headings once each, at most
150 lines, under 32 KiB, no skeleton placeholder, executor-contract and rule
references intact), and replaces atomically. Pass `--resolve-pending-merge`
with the preview's `pending_merge_sha256` only after the user decided on every
entry in `pending_merge`; it removes that STATE.md section in the same run, and
exit `3` means the section changed since the preview (a new backup arrived):
re-run the preview and review again. Confirm `result: "applied"` (or `"no-op"`) and
`agents_md_state_after: "converted"`. Exit `2` names a contract violation (no
skeleton sections to carry, an owned `CLAUDE.md`, or a composed file that fails
validation); exit `3` means a file changed under the writer — re-read and retry.

### 5. Point Repository Identity at AGENTS.md

`AGENTS.md` `## Project` is the single source of the project identity, so
`## Repository Identity` in STATE.md carries only a pointer. Its typed writer
replaces only that section's body and aborts if `## Main Agent`,
`## Progress Tracker`, or any working block would be lost. Write
`.claude/logs/start-project-identity-input.json`:

```json
{"identity": "Project identity, commands, and conventions: see the Project section of root AGENTS.md."}
```

```bash
python3 .claude/skills/_shared/append_state_block.py --type repository-identity \
  --input .claude/logs/start-project-identity-input.json
python3 .claude/skills/_shared/append_state_block.py --type repository-identity \
  --input .claude/logs/start-project-identity-input.json --apply
```

The writer emits the `<!-- Managed by /start-project. Re-run /start-project to refresh. -->`
marker and the `docs/DESIGN.md` pointer itself, so the input carries the pointer
sentence only. Do not add a heading, a `---`, or a second paragraph — the writer
rejects them (exit `1`). Confirm `result: "applied"`, `structure_ok: true`, and
`progress_tracker_preserved: true` (a real check: it aborts the write with exit
`2` when an existing tracker line was deleted or rewritten).

### 6. Re-verify and report

Re-run the closing gate, and report the JSON verdicts rather than a claim:

```bash
python3 .claude/skills/start-project/detect_stack.py
python3 .claude/skills/_shared/validate_doc.py --contract agents-md --file AGENTS.md
python3 .claude/skills/_shared/validate_doc.py --contract design-doc --file .claude/docs/DESIGN.md
python3 .claude/skills/_shared/validate_doc.py --contract state-doc --file .claude/STATE.md
bash scripts/check.sh
```

All must exit `0` with `ok: true`, and `detect_stack.py` must report
`agents_md_state: "converted"`. `detect_stack.py` confirms shared state, the
native runtime directories, and the absence of shadowing files; the contracts
confirm the documents this skill just wrote still have the sections every other
skill reads them for — `exit 2` names the missing section. Checking the
documents directly is stricter than inferring their health from the detector,
which is why the detector alone is no longer the gate.

Then review `.claude/rules/` for irrelevant stack-specific rules, but do
not remove them without user approval. Report the evidence you used and the
evidence you rejected, the updated files (`AGENTS.md`, DESIGN.md, STATE.md),
any `warnings`, and your recommendations in the user language from `AGENTS.md`
`## Conventions`.
