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
