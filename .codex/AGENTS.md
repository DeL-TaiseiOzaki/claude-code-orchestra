# AGENTS.md -- Codex Adapter

This file is the **Codex-specific adapter**. The common CLI-subagent contract
(responsibilities, response structure, decision/quality/handoff rules,
completion-verification guardrails) lives in **`.agents/AGENTS.md`** -- read
that first.

Codex operates as **Tier 2 (`sol`)** in the agent hierarchy. See
`.agents/tiers.md` for the full tier definitions.

## Model Configuration

Source of truth: `.codex/config.toml`

| Key                       | Value            |
|---------------------------|------------------|
| `model`                   | `gpt-5.6-sol`   |
| `model_reasoning_effort`  | `xhigh`         |
| `approval_policy`         | `never`          |

## Sandbox Discipline

`approval_policy` is `"never"` -- autonomy is assumed. File writes happen
**only** when the caller explicitly passes `--sandbox workspace-write`.
Default to `--sandbox read-only` for all analysis, review, and planning
tasks.

## Enabled Codex Skills

| Skill              | Path                              |
|--------------------|-----------------------------------|
| `context-loader`   | `.codex/skills/context-loader`    |
| `design-tracker`   | `.codex/skills/design-tracker`    |

## Internal Context References

Codex may reference the following project paths as needed:

- `.claude/docs/DESIGN.md` -- macro requirements and design decisions
- `.claude/docs/research/` -- research notes and findings
- `.claude/rules/` -- coding standards and delegation rules
- `.claude/logs/cli-tools.jsonl` -- Codex call history log
