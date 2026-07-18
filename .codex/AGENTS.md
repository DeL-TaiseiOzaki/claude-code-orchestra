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

`approval_policy` is `"never"` -- autonomy is assumed. `sandbox_mode` in
`.codex/config.toml` defaults to `workspace-write`, so file writes are
possible without the caller passing a sandbox flag. Callers doing
analysis, review, or planning should still pass an explicit
`--sandbox read-only` to avoid accidental writes during those tasks.
Completion verification (Sol Guardrails, `.agents/AGENTS.md` section 8)
remains mandatory regardless of sandbox mode.

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
