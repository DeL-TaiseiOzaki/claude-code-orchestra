---
name: team-execute
description: |
  Two-phase Agent Teams execution — replaces the old /team-implement and /team-review skills.
  Phase 1 IMPLEMENT (formerly /team-implement): parallel implementation with teammates per
  module/layer, file-ownership separation, and a shared task list with dependencies.
  Run after /feature plan approval.
  Phase 2 REVIEW (formerly /team-review): specialized reviewers (security, quality,
  test coverage) review the changes from different perspectives in parallel.
  Pass --review-only to skip Phase 1 and review existing changes
  (after manual or Codex implementation).
metadata:
  short-description: Parallel implementation + parallel review with Agent Teams
---

# Team Execute

**Parallel implementation followed by parallel review, both via Agent Teams. Executes the plan approved in `/feature`.**

> Preflight: ensure codex CLI is current (see codex-system skill).

## Arguments

- (no arguments) — run Phase 1 IMPLEMENT, then Phase 2 REVIEW.
- `--review-only` — skip Phase 1 and go straight to Phase 2 REVIEW. Use after
  manual implementation or a Codex direct/MODERATE implementation from `/feature`.

## Prerequisites

- Phase 1: `/feature` is complete and the plan has been approved by the user;
  architecture is documented in `.claude/docs/DESIGN.md`; task list has been created.
- Phase 2 (or `--review-only`): implementation is complete and all tests are passing.

### Inputs

Read these before designing the team so execution stays aligned with the plan
produced by `/feature`:

- **CLAUDE.md Zone C** (below `@orchestra:repo-boundary`) — current project context and decisions
- **`.claude/docs/DESIGN.md`** — architecture and design decisions from the Architect
- **`.claude/docs/research/`** — Researcher findings and library constraints
- **`PROGRESS.md`** (repo root) — rolling summary of recent sessions and next actions

Use the **same `{feature}` / `{team-name}` naming as `/feature`** so work logs
(`.claude/logs/agent-teams/{team-name}/`) and research/design files line up
across phases.

## Workflow

```
Phase 1: IMPLEMENT                        (skipped with --review-only)
  Step 1-1: Analyze Plan & Design Team
  Step 1-2: Spawn Agent Team (implementers per module + tester)
  Step 1-3: Monitor & Coordinate
  Step 1-4: Integration & Verification
    ↓
Phase 2: REVIEW
  Step 2-1: Gather Diff (gather_diff.sh)
  Step 2-2: Spawn Review Team (security / quality / test reviewers)
  Step 2-3: Synthesize Findings
  Step 2-4: Report to User
```

---

# Phase 1: IMPLEMENT

## Step 1-1: Analyze Plan & Design Team

**Identify parallelizable workstreams from the task list.**

### Team Design Principles

1. **File ownership separation**: Each Teammate owns a different set of files
2. **Respect dependencies**: Dependent tasks go to the same Teammate or execute in dependency order
3. **Appropriate granularity**: Target 5-6 tasks per Teammate

### Common Team Patterns

**Pattern A: Module-Based (Recommended)**
```
Teammate 1: Module A (models, core logic)
Teammate 2: Module B (API, endpoints)
Teammate 3: Tests (unit + integration)
```

**Pattern B: Layer-Based**
```
Teammate 1: Data layer (models, DB)
Teammate 2: Business logic (services)
Teammate 3: Interface layer (API/CLI)
```

**Pattern C: Feature-Based**
```
Teammate 1: Feature X (all layers)
Teammate 2: Feature Y (all layers)
Teammate 3: Shared infrastructure
```

### Anti-patterns

- Two Teammates editing the same file → overwrite risk
- Too many tasks per Teammate → risk of prolonged idle time
- Overly complex dependencies → coordination costs outweigh benefits

---

## Step 1-2: Spawn Agent Team

**Launch the team based on the plan.**

```
Create an agent team for implementing: {feature}

Each teammate receives:
- Project Brief from CLAUDE.md
- Architecture from .claude/docs/DESIGN.md
- Library constraints from .claude/docs/libraries/
- Their specific task assignments

Spawn teammates:

1. **Implementer-{module}** for each module/workstream
   Prompt: "You are implementing {module} for project: {feature}.

   Read these files for context:
   - CLAUDE.md (project context)
   - .claude/docs/DESIGN.md (architecture)
   - .claude/docs/libraries/ (library constraints)

   Your assigned tasks:
   {task list for this teammate}

   Your file ownership:
   {list of files this teammate owns}

   Rules:
   - ONLY edit files in your ownership set
   - Follow existing codebase patterns
   - Write type hints on all functions
   - Run ruff check after each file change
   - Communicate with other teammates if you need interface changes

   When done with each task, mark it completed in the task list.

   IMPORTANT — Work Log:
   When ALL your assigned tasks are complete, write your work log to
   .claude/logs/agent-teams/{team-name}/{your-teammate-name}.md per the shared
   format: .claude/skills/_shared/work-log-format.md
   Role-specific sections (between Tasks Completed and Communication):
   ## Files Modified
   - `{file path}`: {what was changed and why}
   ## Key Decisions
   - {decision made during implementation and rationale}
   "

2. **Tester** (optional but recommended)
   Prompt: "You are the Tester for project: {feature}.

   Read:
   - CLAUDE.md, .claude/docs/DESIGN.md
   - Existing test patterns in tests/

   Your tasks:
   - Write tests for each module as implementers complete them
   - Follow TDD where possible (write test stubs first)
   - Run uv run pytest after each test file
   - Report failing tests to the relevant implementer

   Test coverage target: 80%+

   IMPORTANT — Work Log:
   When ALL your assigned tasks are complete, write your work log to
   .claude/logs/agent-teams/{team-name}/{your-teammate-name}.md per the shared
   format: .claude/skills/_shared/work-log-format.md
   Role-specific sections (between Tasks Completed and Communication):
   ## Files Modified
   - `{file path}`: {what was changed and why}
   ## Key Decisions
   - {decision made during implementation and rationale}
   "

Use delegate mode (Shift+Tab) to prevent Lead from implementing directly.
Wait for all teammates to complete their tasks.
```

---

## Step 1-3: Monitor & Coordinate

**Lead focuses on monitoring and integration, not implementing.**

### Monitoring Checklist

- [ ] Check task list progress (Ctrl+T)
- [ ] Review each Teammate's output (Shift+Up/Down)
- [ ] Verify no file conflicts
- [ ] Check if any Teammate is stuck

### Intervention Triggers

| Situation | Response |
|-----------|----------|
| Teammate not making progress for a long time | Send a message to check, re-instruct if needed |
| File conflict detected | Reassign file ownership |
| Tests keep failing | Send message to the relevant Implementer |
| Unexpected technical issue | Consult Codex (via subagent) |

### Quality Gates (via Hooks)

`TeammateIdle` hook and `TaskCompleted` hook automatically run quality checks:

- Lint check (ruff)
- Test execution (pytest)
- Type check (ty)

---

## Step 1-4: Integration & Verification

**After all tasks are complete, run integration verification.**

Run the quality gates per `.claude/rules/dev-environment.md` (ruff check / ruff format --check / ty / pytest, or `poe all`).

### Integration Report

```markdown
## Implementation Complete: {feature}

### Completed Tasks
- [x] {task 1}
- [x] {task 2}
...

### Quality Checks
- ruff: PASS / FAIL
- ty: PASS / FAIL
- pytest: PASS ({N} tests passed)
- coverage: {N}%

### Next Steps
Proceed to Phase 2: REVIEW
```

### Cleanup

```
Clean up the implementation team
```

Then continue to Phase 2.

---

# Phase 2: REVIEW

**Parallel review from multiple perspectives. Entry point when `--review-only` is passed.**

Read the Inputs listed above (DESIGN.md, PROGRESS.md) so the review is grounded
in the original intent, not just the raw diff. Carry the same `{feature}` name
forward so the review references the matching design and work-log files.

## Step 2-1: Gather Diff

**Identify the scope of changes to review** with the bundled script:

```bash
bash .claude/skills/team-execute/gather_diff.sh [base-ref]   # base-ref defaults to main
```

It writes the full diff to `.claude/logs/review-diff.patch` (kept out of context)
and prints a lightweight JSON summary on stdout:

- `changed_files[]`, `diffstat`, `commits[]` — the review scope.
- `diff_file` — path to the full patch for reviewers to read as needed.
- `ruff` — `{ok, issues}` lint snapshot (recorded, never fatal).
- `coverage` — existing coverage report if present, else `null`.

Exit codes: `0` normal · `1` not a git repo or base ref missing. Pass the
`changed_files` list and `diff_file` path to the reviewers in Step 2-2.

---

## Step 2-2: Spawn Review Team

**Launch reviewers with specialized perspectives in parallel.**

```
Create an agent team to review implementation of: {feature}

The following files were changed:
{changed files list}

Spawn reviewers:

1. **Security Reviewer**
   Prompt: "You are a Security Reviewer for: {feature}.

   Review all changed files for security vulnerabilities:
   - Hardcoded secrets or credentials
   - SQL injection, XSS, command injection
   - Input validation gaps
   - Authentication/authorization issues
   - Sensitive data exposure in logs/errors
   - Dependency vulnerabilities

   Changed files: {list}

   Reference: .claude/rules/security.md

   For each finding:
   - Severity: Critical / High / Medium / Low
   - File and line number
   - Description of the issue
   - Recommended fix

   Save report to .claude/docs/research/review-security-{feature}.md

   IMPORTANT — Work Log:
   When your review is complete, write your work log to
   .claude/logs/agent-teams/{team-name}/security-reviewer.md per the shared
   format: .claude/skills/_shared/work-log-format.md (reviewer variant:
   Review Scope + Findings instead of Tasks Completed).
   "

2. **Quality Reviewer**
   Prompt: "You are a Quality Reviewer for: {feature}.

   Review all changed files for code quality:
   - Adherence to coding principles (.claude/rules/coding-principles.md)
   - Single responsibility violations
   - Deep nesting (should use early return)
   - Missing type hints
   - Magic numbers
   - Naming clarity
   - Function length (target < 20 lines)
   - Library constraint violations (.claude/docs/libraries/)

   Use Codex CLI for deep analysis of complex logic:
   codex exec --model "${CODEX_MODEL:-gpt-5.5}" --sandbox read-only "{question}" 2>/dev/null

   Changed files: {list}

   For each finding:
   - Severity: High / Medium / Low
   - File and line number
   - Current code
   - Suggested improvement

   Save report to .claude/docs/research/review-quality-{feature}.md

   IMPORTANT — Work Log:
   When your review is complete, write your work log to
   .claude/logs/agent-teams/{team-name}/quality-reviewer.md per the shared
   format: .claude/skills/_shared/work-log-format.md (reviewer variant:
   Review Scope + Findings instead of Tasks Completed).
   Extra role-specific section after Findings:
   ## Codex Consultations
   - {question asked to Codex}: {key insight from response}
   "

3. **Test Reviewer**
   Prompt: "You are a Test Reviewer for: {feature}.

   Review test coverage and quality:
   - Coverage: use the `coverage` field from Step 2-1's gather_diff.sh JSON;
     if it is null, produce it with the pytest coverage command from
     .claude/rules/testing.md (quality-gate commands: .claude/rules/dev-environment.md).
   - Check: Are all happy paths tested?
   - Check: Are error cases covered?
   - Check: Are boundary values tested?
   - Check: Are edge cases handled?
   - Check: Are external deps properly mocked?
   - Check: Do tests follow AAA pattern?
   - Check: Are tests independent (no order dependency)?

   Reference: .claude/rules/testing.md

   For each gap:
   - File/function missing coverage
   - What test cases are needed
   - Priority: High / Medium / Low

   Save report to .claude/docs/research/review-tests-{feature}.md

   IMPORTANT — Work Log:
   When your review is complete, write your work log to
   .claude/logs/agent-teams/{team-name}/test-reviewer.md per the shared
   format: .claude/skills/_shared/work-log-format.md (reviewer variant:
   Review Scope + Findings instead of Tasks Completed).
   Role-specific notes: in Review Scope report Coverage: {percentage};
   Findings use [{priority}] {file/function}: {missing test case description}.
   Extra role-specific section after Findings:
   ## Test Execution Results
   - Total: {N} tests, Passed: {N}, Failed: {N}
   - Coverage: {percentage}
   "

Wait for all reviewers to complete.
```

### Optional: Competing Hypotheses (for debugging)

For bug investigation, add adversarial reviewers:

```
Spawn 3-5 teammates with different hypotheses about the bug.
Have them actively try to disprove each other's theories.
```

---

## Step 2-3: Synthesize Findings

**Integrate results from all reviewers and assign priorities.**

Read review reports:
- `.claude/docs/research/review-security-{feature}.md`
- `.claude/docs/research/review-quality-{feature}.md`
- `.claude/docs/research/review-tests-{feature}.md`

### Prioritization

| Priority | Criteria | Action |
|----------|----------|--------|
| **Critical** | Security vulnerabilities, data loss risk | Must fix before merge |
| **High** | Bugs, missing critical tests, type errors | Should fix before merge |
| **Medium** | Code quality, naming, patterns | Fix if time allows |
| **Low** | Style, minor improvements | Track for later |

---

## Step 2-4: Report to User

**Present the integrated review results to the user.**

```markdown
## Review Results: {feature}

### Summary
- Security: {N} findings (Critical: {n}, High: {n}, Medium: {n})
- Code Quality: {N} findings (High: {n}, Medium: {n}, Low: {n})
- Test Coverage: {N}% ({above/below} the 80% target)

### Critical / High Findings

#### [{Severity}] {Issue Title}
- **File**: `{file}:{line}`
- **Issue**: {description}
- **Recommended Fix**: {recommended fix}

...

### Recommended Actions
1. {Action 1 — Critical fix}
2. {Action 2 — High priority fix}
3. {Action 3 — Test gap to fill}

### Medium / Low Findings
{Brief list — details in review reports}

---
Shall we proceed with fixes?
```

### Cleanup

```
Clean up the team
```

---

## Tips

- **Delegate mode**: Use Shift+Tab to prevent Lead from implementing directly
- **Task granularity**: 5-6 tasks per Teammate is optimal
- **File conflict prevention**: Module-level ownership separation is the most important factor
- **Separate Tester**: Having a dedicated Tester separate from Implementers enables a TDD-like workflow
- **Reviewer specialization**: Each reviewer focuses on a different perspective to prevent blind spots
- **Codex utilization**: Quality Reviewer delegates complex logic analysis to Codex
- **Report persistence**: Save review results in `.claude/docs/research/` for reference during fixes
- **Competing hypotheses mode**: Adversarial review pattern is effective for bug investigation
- **Cost awareness**: Each Teammate is an independent Claude instance (high token consumption). 3 reviewers = 3x tokens; for small changes, a subagent-based review is sufficient
