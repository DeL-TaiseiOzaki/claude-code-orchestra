# Codex Handoff Playbook

This document standardizes how Claude Code hands tasks to Codex so planning/implementation loops stay short and predictable.

## Goals

- Reduce retries caused by ambiguous Codex prompts.
- Keep Claude context small by returning concise summaries.
- Make Codex responses immediately actionable in Claude workflows.

## 1) Delegation Decision Matrix

Use Codex when **at least one** is true:

- Architecture or module boundary decisions are involved.
- The implementation requires multiple dependent steps.
- The error root cause is unknown.
- Trade-off comparison is required.
- The change affects 2+ files with behavioral impact.

Skip Codex when all are true:

- Single-file, obvious edit.
- <10 LOC change.
- No design decision or risk.

## 2) Prompt Contract (Required Fields)

Every Codex prompt should include:

1. **Objective**: one-sentence outcome.
2. **Constraints**: language, style, forbidden approaches.
3. **Relevant files**: explicit paths.
4. **Acceptance checks**: commands to run.
5. **Output format**: concise markdown sections.

## 3) Recommended Prompt Templates

### A. Planning / Design (read-only)

```bash
codex exec --model gpt-5.4 --sandbox read-only --full-auto "
Objective: Create an implementation plan for {feature}.
Constraints:
- Keep existing architecture unless explicitly justified.
- Prefer minimal diff.
Relevant files:
- {file1}
- {file2}
Acceptance checks:
- {test or lint commands}
Output format:
## Analysis
## Recommendation
## Implementation Plan
## Risks
## Next Steps
"
```

### B. Complex Implementation (workspace-write)

```bash
codex exec --model gpt-5.4 --sandbox workspace-write --full-auto "
Objective: Implement {feature/fix}.
Constraints:
- Follow project lint/type/test rules.
- Do not modify unrelated files.
Relevant files:
- {file1}
- {file2}
Acceptance checks:
- {test or lint commands}
Output format:
## Changes Made
## Validation
## Remaining Risks
"
```

## 4) Claude-side Compression Rules

When Codex finishes, Claude should keep only:

- Top recommendation.
- 3-5 implementation steps.
- Risks requiring user decision.

Store long analysis in `.claude/docs/research/` and reference the path in user-facing updates.

## 5) Failure Recovery

If Codex output is not actionable:

1. Re-run with explicit file list and acceptance checks.
2. Split into two calls: `read-only` plan → `workspace-write` implementation.
3. Ask Codex to compare exactly two options and choose one.
