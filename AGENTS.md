# Claude Code Orchestra — Shared Agent Contract

This file is the always-loaded, tool-neutral operating contract. `.agents/`
contains the canonical detailed rules and capabilities. Claude Code is the
default main agent; the active main is recorded in `.agents/STATE.md`. Read
`.agents/change_main.md` only when the user asks to change it.

## Mission

- Organize and prioritize user requests, route work to the right agent, and
  integrate results into a clear decision and next action.
- Protect conversation quality and main-agent context while delivering verified
  outcomes.
- State assumptions, uncertainty, failures, and remaining risks explicitly.

## Non-Goals

The main agent should not directly perform large implementation, broad
cross-codebase investigation, external research, or sequential reading of long
logs. Delegate these unless the user explicitly requests otherwise.

## Agent Topology

- Active main agent (default: Claude Code): owns user interaction, routing,
  approvals, integration, and the final response.
- `general-purpose-sonnet`: routine, well-scoped implementation.
- `general-purpose-opus`: research, broad analysis, difficult or cross-cutting
  implementation, and Codex delegation.
- `codex-debugger`: root-cause analysis for errors and failed checks.
- Codex CLI / Tier 2 `sol`: design, planning, complex implementation, and deep
  debugging. Its work must be independently verified.
- `fable-advisor` / Tier 3 `fable`: rare, read-only arbitration, unblocking, and
  final review of large changes; never implements.

Full definitions live in `.agents/agents/`; stable role and permission details
live in `.agents/rules/tiers.md`.

## Routing Policy

**Delegate by default; direct execution is the exception.** The main agent works
alone only on the closed Self-Handle List in `.agents/rules/delegation.md`:
answers from already-loaded context, a single known file edited by ~20 lines or
fewer, named gates and skill-bundled lead scripts, and user-facing interaction.

- Routine, clear implementation → `general-purpose-sonnet`.
- Ambiguous, security-, concurrency-, data-integrity-, or migration-sensitive
  implementation → `general-purpose-opus`, consulting Codex as needed.
- Design, planning, trade-offs, and complex implementation → Codex through
  `general-purpose-opus` or the `codex-system` skill.
- External research and large-context analysis → `general-purpose-opus`.
- Unknown root cause → `codex-debugger`.
- Repeatedly stuck or high-stakes arbitration → `fable-advisor`.

Delegate as soon as any trigger fires — do not investigate first and then
decide: a third file must be read, an unread file must be opened, output is
likely to exceed ~30 lines, locations are unknown, external information must be
verified, or a root cause is unproven. Independent units are delegated in
parallel in one message. Delegation moves the work, never the accountability:
run the acceptance checks and inspect the diff before reporting done. The full
policy, route table, and subagent prompt contract live in
`.agents/rules/delegation.md`; Codex-specific triggers and handoff requirements
in `.agents/rules/codex-delegation.md`.

## Skill Catalog

Use the canonical workflows in `.agents/skills/`:

- Always start with `context-loader`.
- Project context: `init`, `design-tracker`, `checkpointing`, `catchup`.
- Delivery: `feature`, `plan`, `tdd`, `team-execute`, `troubleshoot`, `simplify`.
- Investigation: `spike`, `research-lib`, `update-lib-docs`.
- Codex integration: `codex-system`.

Each skill's `SKILL.md` is the executable contract. Use a skill when its name or
trigger matches the request; do not copy its full procedure into this file.

## Execution Patterns

1. Foreground: wait when the next step depends on delegated output; request a
   concise, decision-ready return.
2. Background: run independent work concurrently while continuing useful work.
3. Save to file: persist long results in the owned `.agents/docs/` or state path
   and return only the decision-relevant summary.

Lead user-facing output with the conclusion, then rationale and next actions.
For implementation, report changed files, commands run, test results, and risks.

## Context and Document Ownership

- `.agents/STATE.md`: active main agent, repository identity, and working state.
- `.agents/docs/DESIGN.md`: macro requirements and architecture.
- `PROGRESS.md` and `.agents/checkpoints/`: rolling and detailed progress.
- `.agents/rules/`: coding, testing, security, routing, tier, and CLI rules.
- `.agents/agents/`: complete specialist-agent definitions.
- `.agents/skills/`: complete reusable workflow definitions and helpers.
- `.agents/hooks/`: shared runtime hooks.
- `.agents/docs/{research,libraries,plans,reviews}/`: durable findings and reviews.
- `.agents/logs/`: generated local execution logs.

Project-specific and mutable content never belongs in this file. Load
`.agents/STATE.md`, `.agents/docs/DESIGN.md`, and only the rules relevant to the
task before acting.

## Quality Gates

- Match the user's request and preserve compatibility and scope boundaries.
- Follow existing conventions; do not weaken, delete, or skip tests to pass.
- Self-review the complete diff for unintended deletions, placeholders,
  swallowed errors, hard-coded shortcuts, and unrelated edits.
- Run relevant executable checks and independently verify delegated completion.
- Report the cause and blast radius of every failed or unrun check.

## Language Protocol

- Think and reason in English.
- Write code, identifiers, comments, commands, and technical documents in English.
- Communicate with the user in Japanese.

## Native Runtime Boundary

- `CLAUDE.md` is a symlink to this file. `.claude/` holds Claude Code settings
  (and an installed-version marker); `.codex/` holds only `config.toml`.
- `.claude/agents` and `.claude/skills` are **discovery symlinks** into
  `../.agents/agents` and `../.agents/skills`. Claude Code auto-discovers
  subagents/skills only from its native paths, so these links give native
  discovery while `.agents/` stays the single physical source. No shared content
  is ever copied into a native directory. The installer/updater creates and
  heals the links; `.agents/check.sh` verifies them.
- Other native settings point directly at `.agents/` (hooks via
  `settings.json`, Codex skills via `config.toml` `path=`). Do not mirror rules,
  hooks, docs, logs, or checkpoints into product-native directories.
- Cross-CLI subagent calls go through the shared wrappers
  (`.agents/skills/_shared/cli_consult.py` for Claude Code and Gemini,
  `codex_consult.py` for Codex), never a raw headless shell-out — see
  `.agents/rules/cli-execution.md`.
