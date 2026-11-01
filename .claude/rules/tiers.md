# Agent Tier Definitions

Three stable tiers for multi-agent orchestration. Tier IDs are stable and
referenced by skills, rules, and configuration. In this Claude Code-only
edition every tier runs on Claude; Tier 2 is `deep` (an Opus executor) rather
than the multi-CLI flavour's externally hosted tier.

## Tier 1 -- `default` (Main Agent and Default Executors)

- **Scope**: User interaction and integration by the Claude Code main agent,
  plus routine direct or delegated work.
- **Selection criteria**: Default for all tasks unless escalation is needed.
- **Permission boundary**: Claude Code's native permissions
  (`.claude/settings.json`).
- **Inputs**: User prompt, `AGENTS.md`, tier definitions, and relevant rules.
- **Outputs**: Direct edits, user-facing responses, delegation calls to other tiers.
- **Runtime**: Claude Code (the only supported runtime in this edition).
- **Default executor models**: Claude models configured through
  `.claude/settings.json`; unspecified subagents default to
  `CLAUDE_CODE_SUBAGENT_MODEL` (Sonnet).
- **Tier-1 norm**: Implementation-work subagents run on Sonnet
  (`general-purpose-sonnet`).

## Tier 2 -- `deep` (Deep Reasoning Executor)

- **Scope**: Design, planning, code review, complex implementation,
  root-cause debugging, research, and large-context analysis.
- **Selection criteria**: Multi-file changes with behavior impact,
  architecture decisions, complex algorithms, root-cause-unknown debugging,
  and any of the deep-reasoning triggers in `.claude/rules/delegation.md`.
- **Agents**: `general-purpose-opus` (planning, design, review, difficult
  implementation, research), `debugger` (root-cause analysis), and Claude
  Code's built-in `Plan` agent when a read-only plan is all that is wanted.
- **Permission boundary**: Claude Code's native permissions; a planning or
  review request is read-only by instruction, and the caller verifies every
  diff it produces.
- **Inputs**: A structured prompt following the Subagent Prompt Contract
  (`.claude/rules/delegation.md`).
- **Outputs**: Structured response (TL;DR / Analysis / Plan / Patch Strategy /
  Validation / Risks); file patches; validation commands.
- **Model**: Claude Opus (`model: opus` in the agent frontmatter, 1M context).
- **Guardrails**: See root `AGENTS.md` section "Guardrails (Completion Verification)".

## Tier 3 -- `fable` (Rare Escalation / Final Authority)

- **Scope**: Design arbitration, unblocking stuck problems, final review of
  large changes -- and implementing the resolution when it is faster and safer
  to land the fix than to hand it back down a tier that already failed twice.
- **Selection criteria**: Escalation only -- used when lower tiers are stuck,
  conflicting, or a high-stakes decision requires independent judgment.
  Scarcity is what keeps the signal high; the widened permission does not
  widen the scope.
- **Permission boundary**: Full filesystem access, same as Tier 2. Review
  notes still belong in `.claude/docs/reviews/`, but that is now a convention
  about where judgment is recorded, not a restriction on what can be written.
  A read-only advisor could only ever describe a fix, which meant every
  escalation ended by delegating the resolution back to the tier that had
  already failed at it.
- **Inputs**: Context summary, competing proposals or stuck-state description.
- **Outputs**: Judgment, arbitration decision, review notes, and -- when it
  implements -- a diff subject to the same completion verification as any
  other tier.
- **Model**: Claude `fable-advisor` agent
  (`.claude/agents/fable-advisor.md`).
- **Guardrails**: See root `AGENTS.md` section "Guardrails
  (Completion Verification)". Fable's judgment is not self-certifying: a
  change it lands is verified like any other.

## Fable Differentiation

Multiple review mechanisms exist. Their scopes are distinct:

| Mechanism                        | Scope                                          | Trigger                          |
|----------------------------------|-------------------------------------------------|----------------------------------|
| team-execute Phase 2 reviewers   | Per-change ship gate (security, quality, tests) | Every team-execute change        |
| `general-purpose-opus` review    | Code-level design challenge and code review     | On-demand, or hook-suggested     |
| **Fable (Tier 3)**               | RARE escalation: arbitration, unblocking, large-change final judgment, and landing the resolution | Manual escalation when stuck or high-stakes |
