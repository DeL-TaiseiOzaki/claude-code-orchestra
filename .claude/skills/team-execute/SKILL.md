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

- Phase 1: `/feature` **or `/plan`** is complete and the plan has been approved
  by the user;
  architecture is documented in `.claude/docs/DESIGN.md`; task list has been created.
- Phase 2 (or `--review-only`): implementation is complete. "All tests pass" is
  **not** taken on trust here: Step 2-1 runs `verify.sh` and collects diff
  evidence before any reviewer is spawned. On the `--review-only` path the
  implementer was an external agent, which is exactly when the Guardrails in
  root `AGENTS.md` apply.

### Inputs

Read these before designing the team so execution stays aligned with the plan
produced by `/feature` or `/plan`:

- **`.claude/STATE.md`** — current project context and decisions
- **`.claude/docs/DESIGN.md`** — architecture and design decisions from the Architect
- **`.claude/docs/research/`** — Researcher findings and library constraints
- **`PROGRESS.md`** (repo root) — rolling summary of recent sessions and next actions
- **`.claude/docs/plans/{slug}.md`** — the approved implementation plan, when the
  plan came from `/plan` (validated there with `validate_doc.py --contract
  plan-doc`; `/plan` hands over the slug as `Next: /team-execute with slug {slug}`)

Use the **same `slug` `/feature` or `/plan` resolved** so work logs
(`.claude/logs/agent-teams/{team-name}/`) and research/design files line up
across phases. Step 1-1 resolves the workspace for a full run; Step 2-1
re-resolves it for a `--review-only` entry.

## Workflow

```
Phase 1: IMPLEMENT                        (skipped with --review-only)
  Step 1-1: Analyze Plan & Design Team (check_ownership.py --mode preflight)
  Step 1-2: Spawn Agent Team (implementers per module + tester)
  Step 1-3: Monitor & Coordinate
  Step 1-4: Integration & Verification (validate_doc.py, verify.sh,
            check_ownership.py --mode reconcile)
    ↓
Phase 2: REVIEW
  Step 2-1: Verify & Gather Diff (verify.sh, gather_diff.py)
  Step 2-2: Spawn Review Team (security / quality / test reviewers)
  Step 2-3: Synthesize Findings
  Step 2-4: Report to User
```

---

# Phase 1: IMPLEMENT

## Step 1-1: Analyze Plan & Design Team

**Identify parallelizable workstreams from the task list.**

### Resolve the Workspace

Resolve this run's paths once, reusing the same `slug` `/feature` or `/plan`
resolved:

```bash
python3 .claude/skills/_shared/workspace.py \
  --skill team-execute --slug {slug} --create
```

The JSON carries `team_name` and `paths` (`review_security`, `review_quality`,
`review_tests`, `diff_file`, `team_dir`). Adding `--teammate NAME` returns a
`work_log` path inside `team_dir` for that teammate. Every `{team-name}` /
output path below MUST come from this JSON verbatim, never be re-derived by
hand.

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

### Ownership Preflight (mandatory before spawning)

Which decomposition fits this plan is judgment and stays above. Whether the
resulting ownership sets **overlap** has exactly one correct answer, so it is
checked, not asserted. Write the map the teammates will actually receive to
`.claude/logs/ownership-{team_name}.json` (gitignored, so it is not itself a
change to reconcile later):

```json
{
  "owners": {
    "implementer-api": ["src/api/**"],
    "implementer-core": ["src/core/**"],
    "tester": ["tests/**"]
  }
}
```

```bash
python3 .claude/skills/team-execute/check_ownership.py \
  --assignment .claude/logs/ownership-{team_name}.json --mode preflight
```

Patterns: `**` crosses directories, `*` and `?` do not, and a bare directory
covers its subtree. A pattern with no glob character is also matched as an exact
path, so two teammates told to create the *same new file* are caught before
either exists.

Exit codes: `0` disjoint · `1` bad arguments or a malformed assignment ·
`2` overlap. On `2`, `overlaps[]` names the exact path and the owners claiming
it — reassign before spawning. `patterns_matching_nothing` and `warnings` list
globs that match no existing file; confirm each is a file the plan creates
rather than a typo. Feed the same JSON into the per-teammate `Your file
ownership` block in Step 1-2 so the map that was checked is the map that was
handed out.

### Model Routing

- Use `general-purpose-sonnet` for implementers and the tester by default.
- Assign `general-purpose-opus` before spawning when a workstream has ambiguous
  architecture, broad cross-system invariants, subtle security/concurrency/data
  integrity/performance risk, or a history of failed implementation attempts.
- Do not route by file count alone. Mechanical multi-file work stays on Sonnet when
  the plan and acceptance criteria are clear.
- If a Sonnet teammate discovers an escalation condition, have it report concrete
  evidence, stop that workstream, and reassign the remaining work to Opus.

---

## Step 1-2: Spawn Agent Team

**Launch the team based on the plan.**

```
Create an agent team for implementing: {feature}

Each teammate receives:
- Project Brief from AGENTS.md
- Architecture from .claude/docs/DESIGN.md
- Library constraints from .claude/docs/libraries/
- Their specific task assignments

Spawn teammates:

1. **Implementer-{module}** for each module/workstream
   Agent: `general-purpose-sonnet` by default; `general-purpose-opus` only when the
   Model Routing criteria above are already met.

   Prompt: "You are implementing {module} for project: {feature}.

   Read these files for context:
   - AGENTS.md (project context)
   - .claude/docs/DESIGN.md (architecture)
   - .claude/docs/libraries/ (library constraints)

   Your assigned tasks:
   {task list for this teammate}

   Your file ownership:
   {the owners entry for this teammate from the preflighted assignment JSON}

   Rules:
   - ONLY edit files in your ownership set — it is reconciled against git in
     Step 1-4, so an edit outside it will surface as unowned
   - Follow existing codebase patterns
   - Write type hints on all functions
   - Run ruff check after each file change
   - Before reporting a task complete, run
     bash .claude/skills/_shared/verify.sh and quote overall; exit 2 means a
     gate failed or no gate ran. No hook does this for you.
   - Communicate with other teammates if you need interface changes
   - If the task reveals an Opus escalation condition, stop and report the evidence

   When done with each task, mark it completed in the task list.

   IMPORTANT — Work Log:
   When ALL your assigned tasks are complete, write your work log to
   {paths.work_log} — resolve it with
   python3 .claude/skills/_shared/workspace.py --skill team-execute
     --slug {slug} --teammate {your-teammate-name}
   and use the returned path verbatim — per the shared
   format: .claude/skills/_shared/work-log-format.md
   Role-specific sections (between Tasks Completed and Communication):
   ## Files Modified
   - `{file path}`: {what was changed and why}
   ## Key Decisions
   - {decision made during implementation and rationale}
   "

2. **Tester** (optional but recommended)
   Agent: `general-purpose-sonnet` by default.

   Prompt: "You are the Tester for project: {feature}.

   Read:
   - AGENTS.md, .claude/docs/DESIGN.md
   - Existing test patterns in tests/

   Your tasks:
   - Write tests for each module as implementers complete them
   - Follow TDD where possible (write test stubs first)
   - Run uv run pytest after each test file
   - Report failing tests to the relevant implementer

   Test coverage target: 80%+ measured, never estimated. If the project has no
   coverage tooling configured, say so instead of reporting a number.

   IMPORTANT — Work Log:
   When ALL your assigned tasks are complete, write your work log to
   {paths.work_log} — resolve it with
   python3 .claude/skills/_shared/workspace.py --skill team-execute
     --slug {slug} --teammate {your-teammate-name}
   and use the returned path verbatim — per the shared
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
- [ ] Verify no file conflicts — `check_ownership.py --mode reconcile` (below)
      rather than by eye
- [ ] Run `bash .claude/skills/_shared/verify.sh` yourself at least once
      mid-run; do not wait for Step 1-4 to discover a broken tree
- [ ] Check if any Teammate is stuck

### Intervention Triggers

| Situation | Response |
|-----------|----------|
| Teammate not making progress for a long time | Send a message to check, re-instruct if needed |
| File conflict detected | Reassign file ownership |
| Tests keep failing | Send message to the relevant Implementer |
| Sonnet exposes ambiguous or high-risk complexity | Stop that workstream and reassign it to `general-purpose-opus` with the evidence collected so far |
| Unexpected technical issue | Consult Codex via `general-purpose-opus` |

### Quality Gates — who actually runs them

**No hook runs a quality gate.** The configured hooks are a `TeammateIdle`
work-log reminder and a `TaskCompleted` CLI-call logger; neither executes ruff,
pytest or ty. Treat the gates as entirely agent-driven:

- Each teammate runs `bash .claude/skills/_shared/verify.sh` itself before
  reporting a task complete, and quotes `overall` in its report.
- The lead re-runs it in Step 1-4 and does not accept a teammate's self-report
  in its place (root `AGENTS.md` Guardrails).
- Gate failure is exit `2`, so a `verify.sh` call whose exit code was never
  checked is an unverified task.

---

## Step 1-4: Integration & Verification

**After all tasks are complete, validate work logs and run integration verification.**

### Work Log Validation

Validate every teammate's work log in the team directory with a single call.
`{N}` is the number of teammates you actually dispatched:

```bash
python3 .claude/skills/_shared/validate_doc.py --contract work-log \
  --dir {paths.team_dir} --expect-files {N}
```

`--expect-files` is what makes "no teammate wrote a log at all" visible: Step
1-1's `--create` already made the directory, so without it an **empty** team
directory returns `ok: true, files_checked: 0, files_failed: 0` and exit 0 —
indistinguishable from every log being valid.

Exit codes: `0` every log satisfies the contract · `1` bad arguments or the
directory does not exist · `2` a required section is missing **or** the file
count differs from `--expect-files` (`error: "expected N files, found M"`).
On `2`, inspect `results` for the failing file and `error` for a shortfall, and
have that teammate fix its log before proceeding. Use `{paths.team_dir}` from
Step 1-1 — do not re-derive the path by hand.

### Ownership Reconcile

Compare the assignment against what git says actually changed:

```bash
python3 .claude/skills/team-execute/check_ownership.py \
  --assignment .claude/logs/ownership-{team_name}.json \
  --mode reconcile --base main
```

It derives the changed-file list through `_shared/gather_diff.py`, so
uncommitted teammate work counts. Exit `0` clean · `1` bad arguments ·
`2` a changed file that two owners claim (`overlaps[]`) or that nobody was
assigned (`unowned_changes[]`) · `3` git could not report the scope. Add
`--allow-path PATTERN` for files the lead legitimately maintains outside the
map (`PROGRESS.md`, a task list). `idle_owners[]` names teammates that changed
nothing — a workstream that silently did not run.

### Quality Gates

Run the quality gates:

```bash
bash .claude/skills/_shared/verify.sh
```

Exit codes: `0` `overall: "pass"` · `1` bad arguments · **`2` a gate failed, or
no gate could run at all** · `3` the log file could not be written. On `2` read
`overall`: `fail` means inspect `log_file`; `no_gates` means nothing was
verified — supply the project's own commands, run them, and record each command
with its exit code in the report below. Only then re-run with
`--allow-no-gates` to record the state deliberately.

### Integration Report

Quote the `tools` object from the `verify.sh` JSON verbatim. Do not re-type gate
statuses: the payload distinguishes `pass` / `fail` / `skipped`, and a
hand-written `PASS` erases the difference between a gate that passed and a gate
that never ran.

```markdown
## Implementation Complete: {feature}

### Completed Tasks
- [x] {task 1}
- [x] {task 2}
...

### Quality Checks
overall: {overall}
{the tools object, pasted from the verify.sh JSON}

### Ownership Reconcile
- overlaps: {overlaps} · unowned: {unowned_changes} · idle: {idle_owners}

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

## Step 2-1: Verify & Gather Diff

**Confirm the tree is green, then identify the scope of changes to review.**

If Phase 1 already ran, Step 1-1 resolved the workspace already — repeat the
identical call here (idempotent) when entering directly via `--review-only`:

```bash
python3 .claude/skills/_shared/workspace.py \
  --skill team-execute --slug {slug} --create
```

### 1. Run the gates before spending three reviewers on a red tree

```bash
bash .claude/skills/_shared/verify.sh
```

Exit `0` pass · `1` bad arguments · **`2` a gate failed or no gate ran** ·
`3` write failure. On `2` do **not** spawn reviewers: report `overall`, the
failing tools and `log_file` to the user and stop, unless the user explicitly
chooses to review a red tree. This is the only executable check on the
`--review-only` path, where the implementer was a Codex run or a human and
"all tests pass" is otherwise an unverified claim.

### 2. Collect the Guardrail evidence for a delegated implementation

On the `--review-only` path, also run:

```bash
python3 .claude/skills/_shared/verify_delegation.py --base main
```

It reports `deletions`, `placeholders`, `weakened_tests` and
`out_of_scope_files`, and its `verdict` is always `needs-review` — it collects
evidence, it never accepts a delegated change on your behalf. Hand the findings
to the reviewers as known risk areas.

### 3. Gather the diff

```bash
python3 .claude/skills/_shared/gather_diff.py --base main --out {paths.diff_file}
```

Always pass `--out {paths.diff_file}`. The script's own default is a single
fixed path, so two reviews running at once would overwrite each other's patch —
the resolved `diff_file` is slug-keyed and cannot collide.

Uncommitted work is **in scope by default**: Phase 1 never commits, and the
predecessor of this script compared committed history only — with the teammates'
edits still in the working tree it reported `changed_files: []` and exit 0, and
the three reviewers below then reviewed nothing and reported a clean review.

It writes the full patch to the resolved `diff_file`
(`.claude/logs/review-diff-{slug}.patch`, kept out of context) and prints one
JSON object:

- `changed_files[]` — the review scope: committed, staged, unstaged and
  untracked, deduplicated. `committed_files[]`, `worktree_files[]` and
  `untracked_files[]` break it down; `diffstat` and `commits[]` summarise it.
- `scope_empty` — **gate on this.** `true` means nothing changed relative to
  `--base`; do not spawn reviewers.
- `diff_file`, `patch_bytes` — the full patch for reviewers to read as needed.
- `ruff` — `{status, reason?, exit_code?, issues?, files_linted?, scope}` over
  the changed `.py` files only. `status` is `pass` / `fail` / `skipped` /
  `error`, following `verify.sh`: an absent linter is `skipped`, never a lint
  failure.
- `coverage` — `{report, percent, mtime, stale_vs_scope}` parsed from an
  existing `coverage.json` / `coverage.xml`, else `null` with a warning.
  `stale_vs_scope: true` means the report predates the newest file in scope, so
  the percentage does not describe this change.
- `warnings[]`, `artifacts[]`.

Exit codes: `0` scope collected and non-empty · `1` bad arguments or `--out`
outside the project root · `2` not a git repository, base ref not found, or
`scope_empty` · `3` git failed or the patch could not be written.
`--no-include-uncommitted` restores the committed-only view;
`--base`/`--out` override the defaults (`main`, and a single fixed patch path
that this skill always overrides with the slug-keyed `diff_file`).

Pass the `changed_files` list and `diff_file` path to the reviewers in Step 2-2.

---

## Step 2-2: Spawn Review Team

**Launch reviewers with specialized perspectives in parallel.**

Entry condition, checked before spending three agents: Step 2-1's `verify.sh`
did not exit `2` (or the user overrode it), and `gather_diff.py` reported
`scope_empty: false`. Reviewers spawned against an empty `changed_files` list
produce a clean review of nothing.

Reviewers use `general-purpose-sonnet` by default. Use `general-purpose-opus` for a
review whose dominant risk is subtle security, concurrency, data integrity,
performance, or cross-system behavior; Quality Reviewer may also consult Codex as
specified below.

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

   Save report to .claude/docs/research/review-security-{slug}.md

   IMPORTANT — Work Log:
   When your review is complete, write your work log to
   {paths.work_log} — resolve it with
   python3 .claude/skills/_shared/workspace.py --skill team-execute
     --slug {slug} --teammate security-reviewer
   and use the returned path verbatim — per the shared
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

   Use Codex CLI for deep analysis of complex logic. Write the question to
   .claude/logs/codex/prompt-quality-review.md, then:
   python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-quality-review.md --label quality-review --sandbox read-only
   Read the answer from the JSON output's response_file. Exit codes: 0 ok
   (read response_file); 1 bad args; 2 codex CLI missing; 3 codex failed or
   timed out (inspect error/stderr_file).

   Changed files: {list}

   For each finding:
   - Severity: High / Medium / Low
   - File and line number
   - Current code
   - Suggested improvement

   Save report to .claude/docs/research/review-quality-{slug}.md

   IMPORTANT — Work Log:
   When your review is complete, write your work log to
   {paths.work_log} — resolve it with
   python3 .claude/skills/_shared/workspace.py --skill team-execute
     --slug {slug} --teammate quality-reviewer
   and use the returned path verbatim — per the shared
   format: .claude/skills/_shared/work-log-format.md (reviewer variant:
   Review Scope + Findings instead of Tasks Completed).
   Extra role-specific section after Findings:
   ## Codex Consultations
   - {question asked to Codex}: {key insight from response}
   "

3. **Test Reviewer**
   Prompt: "You are a Test Reviewer for: {feature}.

   Review test coverage and quality:
   - Coverage: use `coverage.percent` from Step 2-1's gather_diff.py JSON. If
     `coverage` is null, or `stale_vs_scope` is true, the number does not
     describe this change: produce a fresh report with the pytest coverage
     command from .claude/rules/testing.md (quality-gate commands:
     .claude/rules/dev-environment.md), or report "coverage not measured".
     Never estimate a percentage.
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

   Save report to .claude/docs/research/review-tests-{slug}.md

   IMPORTANT — Work Log:
   When your review is complete, write your work log to
   {paths.work_log} — resolve it with
   python3 .claude/skills/_shared/workspace.py --skill team-execute
     --slug {slug} --teammate test-reviewer
   and use the returned path verbatim — per the shared
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

**Validate reviewer work logs, then integrate results and assign priorities.**

### Reviewer Work Log Validation

Validate every reviewer's work log in the team directory with a single call.
`{N}` is the number of reviewers you dispatched (3 for the standard team, plus
any Phase 1 logs still in the directory — count what should be there):

```bash
python3 .claude/skills/_shared/validate_doc.py --contract work-log \
  --dir {paths.team_dir} --expect-files {N}
```

Exit `0` all valid · `1` bad arguments or missing directory · `2` a required
section is missing or the count differs from `--expect-files`. On `2`, inspect
`results` and `error`, and ask that reviewer to fix its log before proceeding —
a reviewer that produced no log has not demonstrably reviewed anything.

### Workspace Artifact Check

```bash
python3 .claude/skills/_shared/workspace.py --skill team-execute --slug {slug} --verify
```

`ok: true` means all three review reports exist and are non-empty — read them
next. On `ok: false`, check `missing` / `empty` before synthesizing.

### Review Reports

Read review reports:
- `.claude/docs/research/review-security-{slug}.md`
- `.claude/docs/research/review-quality-{slug}.md`
- `.claude/docs/research/review-tests-{slug}.md`

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
- Test Coverage: {coverage.percent from Step 2-1, or "not measured"}
  ({above/below} the 80% target — omit the comparison when not measured)

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
- **File conflict prevention**: Module-level ownership separation is the most important factor — and the one part of team design that is checked rather than trusted (`check_ownership.py`, preflight before spawning and reconcile after)
- **Separate Tester**: Having a dedicated Tester separate from Implementers enables a TDD-like workflow
- **Reviewer specialization**: Each reviewer focuses on a different perspective to prevent blind spots
- **Codex utilization**: Quality Reviewer delegates complex logic analysis to Codex
- **Model routing**: Sonnet is the default; use Opus only when ambiguity, risk, or failed attempts justify the additional capability
- **Report persistence**: Save review results in `.claude/docs/research/` for reference during fixes
- **Competing hypotheses mode**: Adversarial review pattern is effective for bug investigation
- **Cost awareness**: Each Teammate is an independent Claude instance (high token consumption). 3 reviewers = 3x tokens; for small changes, a subagent-based review is sufficient
