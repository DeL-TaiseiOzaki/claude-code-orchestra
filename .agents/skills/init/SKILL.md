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

### 1. Detect the project

Run:

```bash
python3 .agents/skills/init/detect_stack.py
```

Use its languages, package managers, manifests, commands, libraries, and CI
fields. Exit `2` means the root bootstrap, Claude discovery symlink, or shared
state is invalid; stop and repair the installation before writing context.

### 2. Ask for missing context

Ask the user for the project purpose, code-language preference, and additional
conventions only when repository evidence does not already answer them.

### 3. Populate DESIGN.md

Read `.agents/docs/DESIGN.md`, preserve its fixed headings and document map, and
fill only claims supported by repository evidence or the user's answers:

- background and purpose;
- in-scope and out-of-scope behavior;
- functional and non-functional requirements;
- architecture and agent roles;
- technology choices and rationale;
- constraints, key decisions, and open questions.

Do not fabricate requirements. Later incremental design changes use
`.agents/skills/_shared/update_design.py`.

### 4. Update Repository Identity

Edit only the body of `## Repository Identity` in `.agents/STATE.md`. Preserve
`## Main Agent`, `## Progress Tracker`, and every working block. Keep the body
to one identity sentence plus this pointer:

```markdown
Macro requirements and design live in [docs/DESIGN.md](docs/DESIGN.md).
```

### 5. Review rules and report

Review `.agents/rules/` for irrelevant stack-specific rules, but do not remove
them without user approval. Report the detected stack, the two updated files,
and any recommendations in Japanese.
