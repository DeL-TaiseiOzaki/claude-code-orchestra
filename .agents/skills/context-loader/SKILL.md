---
name: context-loader
description: ALWAYS activate this skill at the start of every task. Load shared rules from .agents/ and project design context before executing any task.
---

# Context Loader Skill

## Purpose

Load canonical shared context from `.agents/` plus project-owned design
documentation so every agent runtime uses the same source files.

## When to Activate

**ALWAYS** - This skill must run at the beginning of every task to load project context.

## Workflow

### Step 1: Resolve the Read Plan

Run `load_context.py` to get a deterministic read order instead of a
hand-maintained file list, so the plan never drifts from what actually exists
on disk:

```bash
python3 .agents/skills/context-loader/load_context.py [--task-libraries name,name]
```

Pass `--task-libraries` (comma-separated) when the task names specific
libraries; the script matches them against `.agents/docs/libraries/` and folds
any hits into the read order.

The JSON reports `{ok, read_order, rules, state, design, progress, libraries,
missing, warnings}`. `read_order` is the exact ordered list of repo-relative
paths to read — it covers the rule files in `.agents/rules/` (coding
principles, dev environment, language, security, testing, tiers, CLI
execution, Codex delegation, and any newly added rule file), `.agents/STATE.md`
for the active main agent and current work, `.agents/docs/DESIGN.md` for
architecture decisions and constraints, and any matched library docs.

### Step 2: Read Everything in `read_order`, Then Surface Gaps

Read each path in `read_order`. Then check the rest of the report:

- **`missing`** — canonical files that do not exist at all (e.g.
  `.agents/docs/DESIGN.md`, `PROGRESS.md`). Report these; do not silently
  proceed as if they were empty.
- **`warnings`** — most notably, `design.placeholder: true` means
  `.agents/docs/DESIGN.md` is either absent or still the uninitialised `/init`
  template (its "Background & Purpose" section is empty). Either state signals
  that `/init` has not been run — surface it rather than treating the project
  as if it had real design context.
- **`libraries.matched`** vs **`libraries.files`** — `matched` is what
  `read_order` included for the current task; `files` is every doc that
  exists. If a library relevant to the task isn't in `files` at all, its
  documentation simply doesn't exist yet.

Exit code 2 means a canonical file is missing entirely (`.agents/rules/` or
`.agents/STATE.md`) — treat this as a hard stop, not a warning.

### Step 3: Execute Task

With the loaded context, execute the requested task following:
- Coding principles from rules
- Design decisions from DESIGN.md
- Library constraints from docs

## Key Rules to Remember

After loading, always follow these principles:

1. **Simplicity first** - Choose readable code over complex
2. **Single responsibility** - One function/class does one thing
3. **Type hints required** - All functions need annotations
4. **Use uv** - Never use pip directly
5. **Security** - No hardcoded secrets, validate input, parameterize SQL

## Language Protocol

- **Thinking/Reasoning**: English
- **Code**: English (variables, functions, comments)
- **User communication**: Japanese (when reporting back through Claude Code)

## Output

After loading context, briefly confirm:
- Rules loaded
- Design document status
- Ready to execute task
