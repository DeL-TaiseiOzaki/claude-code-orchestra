# Claude Code Orchestra — Root Agent Contract (Claude Code-only edition)

Claude Code loads this file automatically from the repository root **because
no `CLAUDE.md` sits beside it**. It is the single root contract: mission,
routing policy, agent and skill catalogs, quality gates, response structure,
handoff rules, and the completion-verification guardrails that bind every
delegation to a subagent. Follow it as written -- nothing here depends on
opening another file first.

This is the **Claude Code-only** edition: every agent is a Claude Code main
agent or a Claude subagent invoked through the native Agent tool. No external
CLI is part of the orchestration.

**Do not add a `CLAUDE.md`, a `.claude/CLAUDE.md`, or a `CLAUDE.local.md` at or
above the repository root.** Claude Code reads the first one it finds instead of
this file and silently stops loading `AGENTS.md` -- no warning, no error, just a
main agent operating without its contract.

Where to go next, only as the task needs it:

| You need | Read |
|----------|------|
| Tier details | [`.claude/rules/tiers.md`](.claude/rules/tiers.md) |
| Shared standards | [`.claude/rules/`](.claude/rules/) -- coding, testing, security, delegation |
| Full document registry | [`.claude/docs/INDEX.md`](.claude/docs/INDEX.md) |

`.claude/` contains the canonical detailed rules and capabilities. Working
state lives in [`.claude/STATE.md`](.claude/STATE.md).

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

- Claude Code main agent: owns user interaction, routing, approvals,
  integration, and the final response.
- `general-purpose-sonnet` (Tier 1 `default`): routine, well-scoped
  implementation.
- `general-purpose-opus` (Tier 2 `deep`): planning, design, trade-offs, code
  review, research, broad analysis, and difficult or cross-cutting
  implementation. Claude Code's built-in `Plan` agent covers a read-only plan.
- `debugger` (Tier 2 `deep`): root-cause analysis for errors and failed checks.
- `fable-advisor` (Tier 3 `fable`): rare arbitration, unblocking, and final
  review of large changes; may land the resolution when handing it back down
  would repeat the failure that escalated to it.

Every delegated result must be independently verified (see `## Guardrails
(Completion Verification)` below). Full definitions live in `.claude/agents/`;
stable role and permission details live in `.claude/rules/tiers.md`.

## Routing Policy

**Delegate by default; direct execution is the exception.** The main agent works
alone only on the closed Self-Handle List in `.claude/rules/delegation.md`:
answers from already-loaded context, a single known file edited by ~20 lines or
fewer, named gates and skill-bundled lead scripts, and user-facing interaction.

- Routine, clear implementation → `general-purpose-sonnet`.
- Ambiguous, security-, concurrency-, data-integrity-, or migration-sensitive
  implementation → `general-purpose-opus`.
- Design, planning, trade-offs, code review, and complex implementation →
  `general-purpose-opus` (or the built-in `Plan` agent for a read-only plan).
- External research and large-context analysis → `general-purpose-opus`.
- Unknown root cause → `debugger`.
- Repeatedly stuck or high-stakes arbitration → `fable-advisor`.

Delegate as soon as any trigger fires — do not investigate first and then
decide: a third file must be read, an unread file must be opened, output is
likely to exceed ~30 lines, locations are unknown, external information must be
verified, or a root cause is unproven. Independent units are delegated in
parallel in one message. Delegation moves the work, never the accountability:
run the acceptance checks and inspect the diff before reporting done. The full
policy, route table, deep-reasoning triggers, and subagent prompt contract
live in `.claude/rules/delegation.md`.

## Skill Catalog

Use the canonical workflows in `.claude/skills/`:

- Always start with `context-loader`.
- Project context: `init`, `design-tracker`, `checkpointing`, `catchup`.
- Delivery: `feature`, `plan`, `tdd`, `team-execute`, `troubleshoot`, `simplify`.
- Investigation: `spike`, `research-lib`, `update-lib-docs`.

Each skill's `SKILL.md` is the executable contract. Use a skill when its name or
trigger matches the request; do not copy its full procedure into this file.

## Execution Patterns

1. Foreground: wait when the next step depends on delegated output; request a
   concise, decision-ready return.
2. Background: run independent work concurrently while continuing useful work.
3. Save to file: persist long results in the owned `.claude/docs/` or state path
   and return only the decision-relevant summary.

Lead user-facing output with the conclusion, then rationale and next actions.
For implementation, report changed files, commands run, test results, and risks.

## Context and Document Ownership

- `.claude/STATE.md`: repository identity and working state.
- `.claude/docs/DESIGN.md`: macro requirements and architecture.
- `PROGRESS.md` and `.claude/checkpoints/`: rolling and detailed progress.
- `.claude/rules/`: coding, testing, security, routing, and tier rules.
- `.claude/agents/`: complete specialist-agent definitions.
- `.claude/skills/`: complete reusable workflow definitions and helpers.
- `.claude/hooks/`: runtime hooks.
- `.claude/docs/{research,libraries,plans,reviews}/`: durable findings and reviews.
- `.claude/logs/`: generated local execution logs.

Project-specific and mutable content never belongs in this file. Load
`.claude/STATE.md`, `.claude/docs/DESIGN.md`, and only the rules relevant to the
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
- Subagent prompts and subagent returns are in English.
- Response style (natural Japanese, concise but complete): `.claude/rules/language.md`.

## Native Runtime Boundary

- `.claude/` is the **only physical runtime**: `agents/`, `skills/`, `rules/`,
  `hooks/`, `docs/`, `checkpoints/`, `logs/`, `STATE.md`, and `settings.json`.
  `.claude/agents` and `.claude/skills` are real directories, never symlinks,
  so Claude Code's native auto-discovery works without an indirection layer.
- `AGENTS.md` at the repository root is the single contract Claude Code
  auto-loads. It is self-contained and a real file, never a symlink. No
  `CLAUDE.md` may sit beside it, because Claude Code would load that instead
  and never read this contract.
- Subagents are invoked only through Claude Code's native Agent tool, with the
  agent name as `subagent_type`. There are no peer-CLI adapter directories and
  no headless shell-outs to another agent CLI; `scripts/check.sh` verifies the
  boundary.

## Required Response Structure

Subagents doing planning, design, review, or analysis respond in the following
order.

```markdown
## TL;DR
- Conclusion in 3 lines or fewer

## Analysis
- Problem decomposition, assumptions, constraints

## Plan
1. Implementation step
2. Implementation step

## Patch Strategy
- Which files to change and what to change in each

## Validation
- Tests/verification commands to run

## Risks
- Impact of failure and mitigation strategies
```

## Handoff Rules

- Return procedures that are directly executable as-is
- Compress key points needed for decision-making, not lengthy raw data
- Separate unverified items as TODOs
- State assumptions before implementing ambiguous requirements
- Prefer incremental, minimal diffs for large changes
- Include a migration plan whenever compatibility may break

## Internal Context References

Refer to the following as needed:

- `.claude/docs/DESIGN.md`
- `.claude/docs/research/`
- `.claude/rules/`
- `.claude/skills/`
- `.claude/logs/delegation/`

## Guardrails (Completion Verification)

Applies to every delegated subagent run, and most strictly to Tier 2 `deep`
and above. A subagent's completion report is its own claim about its own work:
it is never trusted on its self-report. Implementation subagents have write
access, so verification is the control on a delegated run — nothing stops the
edit, so everything depends on catching it afterwards.

### (a) Independent Verification of Completion Reports

The caller MUST run the acceptance checks from the original prompt AND inspect
the delegated run's diff for:
- Unapproved deletions (files or significant code blocks removed without
  justification in the prompt).
- Stub or placeholder completions (e.g. `pass`, `TODO`, `NotImplementedError`
  left where real logic was requested).
- Out-of-scope changes (files modified that were not mentioned in the task).

Collecting that evidence is mechanical, so it is scripted — reading these three
paragraphs and doing it by hand is exactly what gets skipped when the run looks
successful. To know exactly which files a subagent touched, bracket the
delegation with `.claude/skills/_shared/edit_provenance.py` (`--snapshot`
before, `--compare <snapshot>` after; pre-existing uncommitted work is
excluded), then collect the diff evidence:

```bash
python3 .claude/skills/_shared/verify_delegation.py \
  --base HEAD --expect-files src/a.py --forbid-outside src --forbid-outside tests \
  --label implement
```

`--base` is the ref the delegated work started from (default `HEAD`, i.e.
uncommitted work); `--expect-files PATH` (repeatable) names a path the task was
supposed to change; `--forbid-outside PATH` (repeatable) restricts the change to
those paths. The full diff — uncommitted and untracked work included — is written
under `.claude/logs/delegation/` and named by `diff_file`.

The payload reports `deletions`, `placeholders`, `weakened_tests`,
`out_of_scope_files` and `missing_expected_files`, plus `changed_files`,
`untracked_files`, `unreadable_files`, `scope_empty`, `findings_total`,
`actionable_total` and `expectations_violated`. Exit codes: `0` nothing
actionable and no violated expectation · `1` bad arguments or an unresolvable
`--base` · `2` an actionable finding (`placeholders`, `weakened_tests`) or a
violated expectation · `3` git failed or the diff could not be written.

**Deletions do not drive the exit code.** Any removed non-blank line counts as
one, so a real diff almost always has some; letting them decide the exit status
made `2` the routine outcome, and a check that fails routinely teaches callers
that its failure is noise — a worse state than the unverified delegation it
replaced. Deletions are reported in full in every payload and are covered by
`verdict`, not by the exit code.

**Exit `0` is not an accept.** `verdict` is `needs-review` on every path and
there is deliberately no `clean` branch: the pattern list is heuristic, a
legitimate test deletion exists, and only the agent that wrote the prompt knows
what the task authorised. `ok` reports whether *collection* succeeded. The
`not_automated` field names what no heuristic detects — hard-coded return values
substituted for real logic (b3 below) — instead of pretending full coverage. Read
the diff and decide.

### (b) Cheating Detection

Reject completion if any of the following are detected:
- b1: Tests were deleted, skipped (`@pytest.mark.skip`), or weakened (assertions
  removed or loosened) to make the suite pass. → `weakened_tests`
- b2: Exceptions silently swallowed (bare `except: pass` or equivalent) to hide
  failures. → `placeholders`
- b3: Hardcoded return values substituted for real implementation logic. → not
  detected by any script; the reviewer's own judgment on the diff, which is why
  the script never accepts.

### (c) False Completion Response Protocol

When verification fails:
1. Report the specific failure(s) with evidence.
2. Re-delegate ONCE with the original prompt plus failure context appended.
3. If the second attempt also fails verification, halt and require explicit
   user approval before proceeding.
