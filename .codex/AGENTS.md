# AGENTS.md -- Codex Adapter (reference only)

**Reference only: Codex does not auto-load this file** (it reads the project's
root `AGENTS.md`). It documents Codex-specific configuration for humans and for
agents that follow a pointer here. When Codex runs as a delegated executor,
`codex_consult.py` places `.claude/skills/_shared/executor_contract.md` (role,
response structure, handoff rules) before the task and sets
`ORCHESTRA_ROLE=executor`; caller-side rules and guardrails are
`.claude/rules/cli-contract.md`.

Codex operates as **Tier 2 (`sol`)** in the agent hierarchy. See
`.claude/rules/tiers.md` for the full tier definitions.

## Model Configuration

Source of truth: `.codex/config.toml`

| Key                      | Value          |
|--------------------------|----------------|
| `model`                  | `gpt-5.6-sol`  |
| `model_reasoning_effort` | `xhigh`        |
| `approval_policy`        | `never`        |
| `sandbox_mode`           | `danger-full-access` |

## Sandbox Discipline

`approval_policy` is `"never"` and `sandbox_mode` is `"danger-full-access"`, so
Codex runs unattended with unrestricted filesystem and network access and no
confirmation prompts. Callers doing analysis, review, or planning should still
pass an explicit `--sandbox read-only` to avoid accidental writes during those
tasks. Completion verification (Sol Guardrails, `.claude/rules/cli-contract.md`
section "Guardrails (Completion Verification)") remains mandatory regardless of
sandbox mode.

## Enabled Codex Skills

Skills are enabled by `[[skills.config]]` entries in `.codex/config.toml` that
point directly at the canonical implementations under `.claude/skills/`.
Nothing is copied into `.codex/`.

| Skill            | Path                            |
|------------------|---------------------------------|
| `context-loader` | `.claude/skills/context-loader` |
| `design-tracker` | `.claude/skills/design-tracker` |

## Internal Context References

Codex may reference the following project paths as needed:

- `.claude/docs/DESIGN.md` -- macro requirements and design decisions
- `.claude/docs/research/` -- research notes and findings
- `.claude/rules/` -- coding standards and delegation rules
- `.claude/STATE.md` -- active main agent and cross-session working state
- `.claude/logs/cli-tools.jsonl` -- Codex call history log
