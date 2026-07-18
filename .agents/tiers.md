# Agent Tier Definitions

Three stable tiers for multi-agent orchestration. Tier IDs are permanent
and referenced by workflows, skills, and configuration.

## Tier 1 -- `default` (Default Executor)

- **Scope**: Orchestrator-direct work (<=10 LOC) plus Claude subagent tasks.
- **Selection criteria**: Default for all tasks unless escalation is needed.
- **Permission boundary**: Full orchestrator permissions as defined in `.claude/settings.json`.
- **Inputs**: User prompt, context from CLAUDE.md and rules.
- **Outputs**: Direct edits, user-facing responses, delegation calls to other tiers.
- **Model**: Claude (configured via `CLAUDE_CODE_SUBAGENT_MODEL` in `.claude/settings.json`).
- **Tier-1 norm**: Implementation-work subagents run on Sonnet; research and
  large-scale analysis subagents stay on Opus (1M context window).

## Tier 2 -- `sol` (Long-Duration Executor)

- **Scope**: Design, planning, complex implementation, long-running tasks.
- **Selection criteria**: Multi-file changes with behavior impact, architecture
  decisions, complex algorithms, root-cause-unknown debugging.
- **Permission boundary**: Write access by default (`sandbox_mode =
  "workspace-write"` in `.codex/config.toml`); `approval_policy` stays
  `"never"`. Callers doing planning/review/analysis should still pass an
  explicit `--sandbox read-only`.
- **Inputs**: Structured prompt following the Prompt Contract
  (`.claude/rules/codex-delegation.md` section "Prompt Contract").
- **Outputs**: Structured response (TL;DR / Analysis / Plan / Patch Strategy /
  Validation / Risks); file patches; validation commands.
- **Model**: Codex CLI model (`CODEX_MODEL` env in `.claude/settings.json`,
  mirrored in `.codex/config.toml`).
- **Guardrails**: See `.agents/AGENTS.md` section "Guardrails (Completion Verification)".

## Tier 3 -- `fable` (Rare Advisor / Reviewer)

- **Scope**: Design arbitration, unblocking stuck problems, final review of
  large changes. Never implements code.
- **Selection criteria**: Escalation only -- used when lower tiers are stuck,
  conflicting, or a high-stakes decision requires independent judgment.
- **Permission boundary**: Read-only access; outputs review notes to
  `.claude/docs/reviews/` only.
- **Inputs**: Context summary, competing proposals or stuck-state description.
- **Outputs**: Judgment, arbitration decision, review notes.
- **Model**: Claude `fable-advisor` agent (created in a later commit;
  configuration TBD).

## Fable Differentiation

Multiple review mechanisms exist. Their scopes are distinct:

| Mechanism                        | Scope                                          | Trigger                          |
|----------------------------------|-------------------------------------------------|----------------------------------|
| team-execute Phase 2 reviewers   | Per-change ship gate (security, quality, tests) | Every team-execute change        |
| `/codex:adversarial-review`      | Code-level design challenge (external plugin)   | On-demand via codex-plugin-cc    |
| **Fable (Tier 3)**               | RARE escalation: arbitration, unblocking, large-change final judgment | Manual escalation when stuck or high-stakes |
