# AGENTS.md -- CLI Executor Extension

Root `AGENTS.md` is the shared orchestration contract. Read it and
`.agents/rules/tiers.md` first. This file adds only the response, handoff, and
verification rules required of CLI executors such as Codex, Antigravity, and
Grok.

## Required Response Structure

Always respond in the following order.

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

## Cross-CLI Subagent Invocation

Any CLI agent can drive any other as a subagent by shelling out to its
non-interactive (headless) mode. All runtimes read the shared `AGENTS.md`
contract and the canonical `.agents/` capabilities, so a delegated call inherits
the same mission, routing, and guardrails regardless of which CLI runs it.

| Callee | Headless command | Machine-readable output |
|--------|------------------|-------------------------|
| Claude Code | `claude -p "<prompt>"` | `--output-format json` (includes a session id for chaining) |
| Codex | `codex exec "<prompt>" < /dev/null` | stdout; always redirect stdin to avoid the EOF hang |
| Gemini CLI | `gemini -p "<prompt>"` | `--output-format json` |

Rules:

- Pass the prompt as a single argument; prefer a timeout and capture stdout to
  `.agents/logs/` so a stall or crash stays diagnosable.
- Pin the model explicitly when the tier matters (`--model` / `CODEX_MODEL`).
- The caller MUST independently verify the callee's result per the Guardrails
  below — a delegated CLI is never trusted on its self-report.
- Prefer the project's own delegation skills (`codex-system`,
  `general-purpose-opus`) over ad-hoc shell-outs when one already covers the
  task.

## Internal Context References

Refer to the following as needed:

- `.agents/docs/DESIGN.md`
- `.agents/docs/research/`
- `.agents/rules/`
- `.agents/skills/`
- `.agents/logs/cli-tools.jsonl`

## Guardrails (Completion Verification)

Applies to any long-duration executor (Tier 2 `sol` and above). Because
`approval_policy` is `"never"`, verification replaces approval.

### (a) Independent Verification of Completion Reports

The caller MUST run the acceptance checks from the original prompt AND inspect
`git diff` for:
- Unapproved deletions (files or significant code blocks removed without
  justification in the prompt).
- Stub or placeholder completions (e.g. `pass`, `TODO`, `NotImplementedError`
  left where real logic was requested).
- Out-of-scope changes (files modified that were not mentioned in the task).

### (b) Cheating Detection

Reject completion if any of the following are detected:
- Tests were deleted, skipped (`@pytest.mark.skip`), or weakened (assertions
  removed or loosened) to make the suite pass.
- Exceptions silently swallowed (bare `except: pass` or equivalent) to hide
  failures.
- Hardcoded return values substituted for real implementation logic.

### (c) False Completion Response Protocol

When verification fails:
1. Report the specific failure(s) with evidence.
2. Re-delegate ONCE with the original prompt plus failure context appended.
3. If the second attempt also fails verification, halt and require explicit
   user approval before proceeding.
