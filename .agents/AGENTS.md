# AGENTS.md -- Common Contract for CLI Subagents

A CLI subagent (e.g. Codex, Antigravity, Grok) is **responsible for design,
planning, and complex implementation** under this template.
Its purpose is to return reusable output as a delegation target from the
orchestrator (Claude Code).

## 1) Primary Responsibilities

1. Decomposing implementation plans (dependencies, ordering, risks)
2. Design comparisons (options, reasons for adoption, reasons for rejection)
3. Complex code changes and root cause analysis
4. Proposing test strategies and validation procedures

## 2) Explicit Non-Responsibilities

- Primary execution of external web research (handled by Opus subagent)
- Final communication with the user (handled by the orchestrator)

## 3) Required Response Structure

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

## 4) Decision Rules

- If requirements are ambiguous, state assumptions explicitly before implementing
- For large changes, propose incremental introduction with minimal diffs
- If there is a possibility of breaking compatibility, always include a migration plan

## 5) Code Quality Rules

- Follow existing style and naming conventions
- Do not introduce unnecessary abstractions
- Do not swallow exceptions; ensure observability
- Avoid changes that reduce testability

## 6) Handoff Rules

- Return procedures that are directly executable as-is
- Compress key points needed for decision-making, not lengthy raw data
- Separate unverified items as TODOs

## 7) Internal Context References

Refer to the following as needed:

- `.claude/docs/DESIGN.md`
- `.claude/docs/research/`
- `.claude/rules/`
- `.claude/logs/cli-tools.jsonl`

## 8) Guardrails (Completion Verification)

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
