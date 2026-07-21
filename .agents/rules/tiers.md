# Agent Tier Definitions

Three stable tiers for multi-agent orchestration. Tier IDs are permanent
and referenced by workflows, skills, and configuration.

## Tier 1 -- `default` (Main Agent and Default Executors)

- **Scope**: User interaction and integration by the active main agent, plus
  routine direct or delegated work.
- **Selection criteria**: Default for all tasks unless escalation is needed.
- **Permission boundary**: The active runtime's native permissions; changing
  the main agent must follow `.agents/change_main.md`.
- **Inputs**: User prompt, root `AGENTS.md`, tier definitions, and relevant
  product-native rules.
- **Outputs**: Direct edits, user-facing responses, delegation calls to other tiers.
- **Default runtime**: Claude Code. The active runtime is recorded in
  `.agents/STATE.md`.
- **Default executor models**: Claude models configured through
  `.claude/settings.json`.
- **Tier-1 norm**: Implementation-work subagents run on Sonnet; research and
  large-scale analysis subagents stay on Opus (1M context window).

## Tier 2 -- `sol` (Long-Duration Executor)

- **Scope**: Design, planning, complex implementation, long-running tasks.
- **Selection criteria**: Multi-file changes with behavior impact, architecture
  decisions, complex algorithms, root-cause-unknown debugging.
- **Permission boundary**: Full filesystem and network access by default (no
  sandbox) (`sandbox_mode = "danger-full-access"` in `.codex/config.toml`);
  `approval_policy` stays `"never"`. Callers doing planning/review/analysis
  should still pass an explicit `--sandbox read-only`.
- **Inputs**: Shared orchestration context plus a structured prompt following
  the Prompt Contract
  (`.agents/rules/codex-delegation.md` section "Prompt Contract").
- **Outputs**: Structured response (TL;DR / Analysis / Plan / Patch Strategy /
  Validation / Risks); file patches; validation commands.
- **Model**: Codex CLI model (`CODEX_MODEL` env in `.claude/settings.json`,
  mirrored in `.codex/config.toml`).
- **Guardrails**: See `.agents/rules/cli-execution.md` section "Guardrails (Completion Verification)".

## Tier 3 -- `fable` (Rare Advisor / Reviewer)

- **Scope**: Design arbitration, unblocking stuck problems, final review of
  large changes. Never implements code.
- **Selection criteria**: Escalation only -- used when lower tiers are stuck,
  conflicting, or a high-stakes decision requires independent judgment.
- **Permission boundary**: Read-only access; outputs review notes to
  `.agents/docs/reviews/` only.
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
