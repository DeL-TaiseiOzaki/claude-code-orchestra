---
name: troubleshoot
description: |
  Diagnose and plan fixes for errors/bugs with Codex-first multi-agent collaboration (Codex + Opus 4.6 + Agent Teams).
  Codex CLI is consulted in EVERY phase for deep code reasoning, hypothesis evaluation, and fix validation.
  Phase 1: Error reproduction & context gathering (Opus subagent 1M context + Codex initial analysis + Claude user interaction).
  Phase 2: Parallel diagnosis (Agent Teams: Root Cause Analyst [Codex-driven] + Impact Investigator [Opus + Codex risk analysis]).
  Phase 3: Fix plan synthesis, Codex validation & user approval.
  Fix implementation is handled separately by /team-execute.
metadata:
  short-description: Codex-first error/bug diagnosis with Agent Teams (Diagnosis phase)
---

# Troubleshoot

**Codex-first error/bug diagnosis skill leveraging Codex deep reasoning, Opus 1M context, and Agent Teams.**

> Preflight: ensure codex CLI is current (see codex-system skill).

## Overview

This skill handles the diagnosis phases (Phase 1-3) with a **Codex-first approach**: Codex CLI is consulted proactively in every phase for pattern recognition, hypothesis evaluation, root cause reasoning, and fix validation. Fix implementation and review are done via `/team-execute`.

```
/troubleshoot <error description>   <- This skill (diagnosis & fix planning)
    | After approval
/team-execute                       <- Parallel fix implementation (Phase 1)
    | After completion
    Phase 2 REVIEW                  <- Parallel review (regression check)
```

## Workflow

```
Phase 1: REPRODUCE & UNDERSTAND (Opus 1M context + Codex Initial Analysis + Claude Lead)
  Opus subagent analyzes the error context, Codex generates initial hypotheses,
  Claude gathers details from the user
    |
Phase 2: DIAGNOSE (Agent Teams -- Parallel, Codex-driven)
  Root Cause Analyst (Codex mandatory) <-> Impact Investigator (Opus + Codex) communicate bidirectionally
  Both teammates consult Codex for deep reasoning throughout analysis
    |
Phase 3: FIX PLAN & APPROVE (Codex Validation + Claude Lead + User)
  Integrate diagnosis results, validate fix plan with Codex, get user approval
```

---

## Phase 1: REPRODUCE & UNDERSTAND (Opus Subagent + Codex + Claude Lead)

**Reproduce the error and gather full context with Opus subagent's 1M context, then consult Codex for initial hypothesis generation, while Claude interacts with the user.**

> Main orchestrator context is precious. Large-scale error context analysis is delegated to Opus subagent (1M context).
> Codex is consulted early for pattern recognition and hypothesis generation.

### Step 0: Resolve Workspace

Resolve this bug's deterministic workspace once. The title becomes file and directory names, so give it a short English descriptor of the bug -- not the user's raw wording, which the Language Protocol keeps out of paths:

```bash
python3 .claude/skills/_shared/workspace.py --skill troubleshoot --title "{short English title}" --create
```

This prints one JSON object: `slug`, `team_name`, and `paths` (`bug_report`, `context`, `root_cause`, `impact`, `diagnosis`, `state_input`, `team_dir`). Exit 0 resolved/created; 1 bad args; 2 applies only to `--verify` (used later in Phase 3); 3 the workspace directories could not be created. Use `{slug}`, `{team_name}`, and every `paths.*` value from this JSON verbatim for the rest of this skill -- do not re-derive them by hand in a later phase.

### Step 1: Gather Error Details from User

Ask the user to provide:

1. **Error message / stack trace**: Full error output
2. **Reproduction steps**: How to trigger the error
3. **Expected vs actual behavior**: What should happen vs what happens
4. **Environment**: OS, Python version, dependency versions
5. **Recent changes**: What changed before the error appeared (if known)

### Step 2: Reproduce & Capture Context (repro.py)

First run the bundled script for the **mechanical** capture — it runs the failing
command under a deadline, records stdout/stderr/exit code + extracted traceback
to a log file keyed by `--label`, and gathers recent git history (plus optional
last-commit context for a stack-trace file):

```bash
python3 .claude/skills/troubleshoot/repro.py "<repro-command>" \
  --label {slug}-initial [--file <path-from-stack-trace>] [--timeout 120]
```

Always pass `--label {slug}-initial` here: the log path is
`.claude/logs/troubleshoot-repro-{label}.log` and an unlabelled run reuses one
shared file, so the Phase 3 fix-verification run (Step 2 task 3) would otherwise
overwrite the original failure evidence this whole diagnosis rests on.

Exit codes: `0` capture completed; `1` bad arguments (including an unusable
`--label` or `--bisect-good` ref, checked *before* the command runs); `2` the
observed exit code differs from `--expect-exit` (not used in Phase 1); `3` the
repro command timed out or the log could not be written. A failing repro command
is the expected case and is still exit `0` — its result is the JSON `exit_code`.

Read the JSON fields: `exit_code`, `timed_out`, `stdout_tail`, `stderr_tail`,
`traceback`, `traceback_format`, `git_available`, `git_error`, `recent_commits`,
`blame`, `blame_error`, `bisect`, `log_file`, `artifacts`. Two fields exist to
stop a null being over-read: `traceback` is only extracted for CPython
tracebacks (`traceback_format: "python"`), so `null` there means "no *Python*
traceback" — a Node/Go/pytest-assertion stack is in `stderr_tail`. And
`git_available: false` with a `git_error` means history could not be read at
all; that is not the same as "no relevant recent history".

On `timed_out: true` (exit 3) the command has no usable result: raise the
`--timeout`, narrow the repro command, or treat the hang itself as the bug —
do not proceed as if the capture succeeded.

To scope a regression, add `--bisect-good <last-known-good-ref>`. It reports the
`bisect` object (`candidate_commits`, `candidate_count`, `path_filter`,
`bisect_command`) — the commits an actual `git bisect` would search, plus the
command to start it. The script never checks out a commit itself, so driving the
bisect stays the Impact Investigator's call in Phase 2.

Then hand that captured context to `general-purpose-opus` for the
**judgment** part — do NOT re-run the command or re-fetch git history:

```
Task tool:
  subagent_type: "general-purpose-opus"
  prompt: |
    Analyze this reproduced error (already captured by repro.py):

    Error: {error message / stack trace}
    repro.py JSON: {exit_code, traceback, recent_commits, log_file}

    Tasks:
    1. Read all files mentioned in the traceback; trace the execution flow
       leading to the error and identify the immediate cause (what line fails).
    2. Look for related tests and whether they pass/fail.
    3. Check if similar patterns exist elsewhere in the codebase.

    Use Glob, Grep, and Read tools to investigate thoroughly.

    Save analysis to `{paths.context}` (from Phase 1 Step 0).
    Return concise summary (5-7 key findings).
```

### Step 2.5: Codex Initial Error Pattern Analysis

Consult Codex for initial hypothesis generation before creating the Bug Report. Write the prompt to a file, then invoke the wrapper:

```text
Objective: Analyze this error and generate initial hypotheses for root cause.
Context:
- Error: {error message / stack trace}
- Failing location: {file:line from Opus subagent analysis}
- Execution flow: {call chain from Opus subagent analysis}
Constraints:
- Focus on root cause categories (state mutation, boundary, concurrency, dependency, type/contract)
- Rank hypotheses by likelihood
- Suggest specific code areas to investigate for each hypothesis
Output format:
## Error Pattern Recognition
## Hypotheses (ranked by likelihood)
## Investigation Plan (per hypothesis)
## Known Similar Patterns
```

```bash
python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-troubleshoot-initial.md --label troubleshoot-initial
```

`.claude/skills/_shared/codex_consult.py` exits 0 when Codex answered normally, 2 if the Codex CLI is not installed, 3 if Codex failed or timed out -- check the JSON `ok` field and read `response_file` for the answer (`error`/`stderr_file` explain a failure). Every later Codex consultation in this skill follows this same write-prompt-then-invoke pattern without repeating these exit codes.

Use Codex's analysis to strengthen the Initial Hypotheses section of the Bug Report.

### Step 3: Create Bug Report

Combine error details + codebase analysis + Codex initial hypotheses into a Bug Report following the template contract in `references/bug-report-template.md`. Save it to `{paths.bug_report}` (from Step 0), then validate it:

```bash
python3 .claude/skills/_shared/validate_doc.py --contract bug-report --file {paths.bug_report}
```

`references/bug-report-template.md` is the single source of truth for the
required sections; the `bug-report` contract is pinned to that template by
`tests/test_validate_doc.py`. Do not work from a section list retyped here --
that drift is exactly what this fix removed. Exit 0 means every required section
is present; exit 2 means one is missing, and the JSON `sections_missing` names
it. Fill the gap before proceeding; exit 1 means the file does not exist.

Both Phase 2 teammates read this file, and Phase 3's `--verify` gate requires
it, so it must exist on disk -- not only in this conversation.

---

## Phase 2: DIAGNOSE (Agent Teams — Parallel)

**Launch Root Cause Analyst and Impact Investigator in parallel via Agent Teams with bidirectional communication. Both teammates MUST consult Codex for deep reasoning tasks.**

> Key difference from subagents: Teammates can communicate with each other.
> Root Cause Analyst's findings change Impact Investigator's scope, and Impact Investigator's context informs root cause analysis.

### Team Setup

```
Create an agent team named `{team_name}` for troubleshooting: {slug}

Spawn two teammates:

1. **Root Cause Analyst** — Uses Codex CLI as PRIMARY analysis engine for deep code reasoning
   Prompt: "You are the Root Cause Analyst for bug: {slug}.

   Your job: Identify the definitive root cause of this error through deep code analysis.
   Codex CLI is your PRIMARY tool for reasoning about code behavior.

   Bug Report: read `{paths.bug_report}` (written and validated in Phase 1 Step 3).

   Tasks:
   1. Trace the execution flow step by step from entry point to error
   2. Evaluate each hypothesis from the Bug Report:
      - Gather evidence FOR and AGAINST each hypothesis
      - Eliminate hypotheses that contradict the evidence
   3. Identify the root cause (not just the symptom):
      - What is the underlying defect?
      - Why does it manifest as this specific error?
      - Under what conditions does it trigger?
   4. Propose fix approaches (at least 2 alternatives):
      - Approach A: {description, pros, cons}
      - Approach B: {description, pros, cons}
      - Recommended approach with rationale

   ## Codex Analysis Protocol (MANDATORY)

   You MUST consult Codex for EACH of the following analysis tasks.
   Do NOT skip Codex consultation — it is the primary reasoning engine for this role.
   Each consultation below follows the same shape: write the prompt to a file,
   then run `python3 .claude/skills/_shared/codex_consult.py --prompt-file <path> --label <label>`
   and read the JSON `response_file`.

   ### 1. Execution Flow Tracing
   For complex control flow, write the prompt below to a file, then consult Codex:

   Objective: Trace the execution flow from {entry point} to {error location}.
   Context:
   - Entry point: {file:function}
   - Error location: {file:line}
   - Key intermediate functions: {list}
   Constraints:
   - Track state transformations at each step
   - Identify where assumptions are violated
   Output format:
   ## Execution Flow (step by step)
   ## State Transformations
   ## Assumption Violations
   ## Critical Decision Points

   python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-troubleshoot-flow.md --label troubleshoot-flow

   ### 2. Hypothesis Evaluation
   For each hypothesis, write the prompt below to a file, then consult Codex to evaluate evidence:

   Objective: Evaluate hypothesis "{hypothesis}" against collected evidence.
   Context:
   - Hypothesis: {description}
   - Evidence FOR: {list}
   - Evidence AGAINST: {list}
   - Code context: {relevant code snippets}
   Constraints:
   - Apply logical reasoning, not pattern matching
   - Consider alternative explanations for the evidence
   Output format:
   ## Verdict (CONFIRMED / ELIMINATED / INCONCLUSIVE)
   ## Reasoning
   ## Remaining Unknowns

   python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-troubleshoot-hypothesis.md --label troubleshoot-hypothesis

   ### 3. Fix Approach Design
   Write the prompt below to a file, then consult Codex for trade-off analysis of fix alternatives:

   Objective: Design and compare fix approaches for root cause: {root cause description}.
   Context:
   - Root cause: {description}
   - Affected code: {file:line}
   - Current behavior: {description}
   - Desired behavior: {description}
   Constraints:
   - Propose at least 2 approaches
   - Evaluate: correctness, minimal invasiveness, maintainability, performance
   - Consider backward compatibility
   Output format:
   ## Approach A: {name}
   ## Approach B: {name}
   ## Comparison Matrix
   ## Recommendation with Rationale

   python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-troubleshoot-fix-design.md --label troubleshoot-fix-design

   ### 4. Fix Correctness Verification
   Before finalizing, write the prompt below to a file, then consult Codex to verify the proposed fix:

   Objective: Verify that the proposed fix correctly resolves the root cause.
   Context:
   - Root cause: {description}
   - Proposed fix: {description}
   - Edge cases identified: {list}
   Constraints:
   - Check that the fix addresses the root cause, not just symptoms
   - Verify behavior under all identified trigger conditions
   - Check for new failure modes introduced by the fix
   Output format:
   ## Correctness Assessment (CORRECT / INCOMPLETE / INCORRECT)
   ## Edge Case Coverage
   ## New Failure Modes (if any)
   ## Confidence Level

   python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-troubleshoot-fix-verify.md --label troubleshoot-fix-verify

   Save analysis to `{paths.root_cause}` (from Phase 1 Step 0).

   Communicate with Impact Investigator teammate:
   - Share root cause findings that expand the affected scope
   - Request context about specific code paths or history
   - Confirm or refute hypotheses based on shared evidence

   IMPORTANT — Work Log:
   When ALL your tasks are complete, write your work log to
   {paths.team_dir}root-cause-analyst.md per the shared
   format: .claude/skills/_shared/work-log-format.md
   Keep all five core sections, `## Tasks Completed` included -- the Lead
   validates this log with `validate_doc.py --contract work-log`, which
   rejects a log that drops it.
   Role-specific sections (between Tasks Completed and Communication with
   Teammates) for this role:
   ## Hypotheses Evaluated
   - [confirmed/eliminated] {hypothesis}: {evidence}
   ## Root Cause
   - Defect: {description}
   - Location: {file:line}
   - Trigger condition: {when it occurs}
   ## Proposed Fixes
   - Approach A: {description} — {pros/cons}
   - Approach B: {description} — {pros/cons}
   - Recommended: {which and why}
   ## Codex Consultations
   - {question asked to Codex}: {key insight from response}
   "

2. **Impact Investigator** — Uses Opus with Git history, codebase search, WebSearch, and Codex for risk analysis
   Prompt: "You are the Impact Investigator for bug: {slug}.

   Your job: Determine the full scope and impact of this bug, and gather context for the fix.
   Consult Codex for regression risk reasoning and fix safety analysis.

   Bug Report: read `{paths.bug_report}` (written and validated in Phase 1 Step 3).

   Tasks:
   1. Trace the bug's origin in git history:
      - git log / git bisect to find the introducing commit
      - What change caused this? Was it intentional?
   2. Assess blast radius:
      - What other code paths call the affected function?
      - What features/users are impacted?
      - Are there related bugs or similar patterns elsewhere?
   3. Research external context:
      - Is this a known issue in a dependency? (WebSearch)
      - Are there upstream fixes or workarounds?
      - Check issue trackers, changelogs, migration guides
   4. Evaluate regression risk:
      - What tests cover the affected area?
      - What could break if we change this code?
      - Are there downstream consumers to consider?

   How to research:
   - Use Git commands (git log, git blame, git bisect) for history
   - Use Grep/Glob for codebase impact analysis
   - Use WebSearch for external known issues:
     WebSearch: '{library} {error message} issue fix'

   ## Codex Risk Analysis Protocol (MANDATORY)

   You MUST consult Codex for regression risk reasoning and fix safety analysis.
   Each consultation below follows the same shape: write the prompt to a file,
   then run `python3 .claude/skills/_shared/codex_consult.py --prompt-file <path> --label <label>`
   and read the JSON `response_file`.

   ### Regression Risk Reasoning
   Write the prompt below to a file, then consult Codex to evaluate what could break if the proposed change is applied:

   Objective: Evaluate regression risk if {proposed change} is applied to {file:line}.
   Context:
   - Current behavior: {description}
   - Proposed change: {description}
   - Callers of affected function: {list}
   - Existing test coverage: {description}
   Constraints:
   - Consider all callers and downstream consumers
   - Identify implicit contracts that may be violated
   - Assess backward compatibility impact
   Output format:
   ## Risk Assessment (HIGH / MEDIUM / LOW)
   ## Affected Code Paths
   ## Implicit Contracts at Risk
   ## Recommended Safeguards

   python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-troubleshoot-regression.md --label troubleshoot-regression

   ### Fix Safety Analysis
   Write the prompt below to a file, then consult Codex to verify the proposed fix does not introduce new issues:

   Objective: Analyze whether the proposed fix introduces new issues or side effects.
   Context:
   - Root cause: {from Root Cause Analyst}
   - Proposed fix: {description}
   - Blast radius: {affected code paths}
   - Dependencies: {upstream/downstream}
   Constraints:
   - Check for new edge cases created by the fix
   - Verify thread safety if applicable
   - Check for performance implications
   Output format:
   ## Safety Assessment (SAFE / CAUTION / UNSAFE)
   ## New Issues Identified
   ## Side Effects
   ## Mitigation Recommendations

   python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-troubleshoot-fix-safety.md --label troubleshoot-fix-safety

   Save findings to `{paths.impact}` (from Phase 1 Step 0).

   Communicate with Root Cause Analyst teammate:
   - Share git history context that informs root cause
   - Share external findings (known issues, upstream fixes)
   - Request clarification on which code paths to investigate

   IMPORTANT — Work Log:
   When ALL your tasks are complete, write your work log to
   {paths.team_dir}impact-investigator.md per the shared
   format: .claude/skills/_shared/work-log-format.md
   Keep all five core sections, `## Tasks Completed` included -- the Lead
   validates this log with `validate_doc.py --contract work-log`, which
   rejects a log that drops it.
   Role-specific sections (between Tasks Completed and Communication with
   Teammates) for this role:
   ## Git History
   - Introducing commit: {hash} — {description}
   - Related commits: {list}
   ## Blast Radius
   - Affected code paths: {list}
   - Affected features/users: {list}
   ## External Research
   - {source}: {finding and relevance}
   ## Regression Risk
   - Existing test coverage: {description}
   - Risk areas: {what could break}
   ## Codex Risk Analysis
   - Regression risk assessment: {Codex's verdict and reasoning}
   - Fix safety assessment: {Codex's verdict and reasoning}
   "

Wait for both teammates to complete their tasks.
```

### Why Bidirectional Communication Matters for Debugging

```
Example interaction flow:

Root Cause Analyst: "The error occurs because parse_config() returns None when key is missing"
    -> Impact Investigator: "Checking git blame -- this was changed in commit abc123"
    -> Impact Investigator: "Found 5 other callers of parse_config() that don't handle None"
    -> Root Cause Analyst: "Expanding fix scope -- need to either fix callers or fix parse_config()"
    -> Root Cause Analyst: "Codex recommends: fix parse_config() to raise KeyError instead of returning None"
    -> Impact Investigator: "Codex risk analysis confirms: all 5 callers already have try/except for KeyError"
    -> Root Cause Analyst: "Root cause confirmed. Codex verified fix correctness. Fix approach: restore KeyError in parse_config()"
```

Without Agent Teams, this discovery loop would require multiple sequential subagent rounds.

---

## Phase 3: FIX PLAN & APPROVE (Codex Validation + Claude Lead)

**Integrate Agent Teams diagnosis results, validate the fix plan with Codex, and request user approval.**

### Step 1: Synthesize Diagnosis

Gate Phase 3 on the Phase 1/2 artifacts **before** reading anything, so a
teammate that stopped early cannot be mistaken for one that finished:

```bash
python3 .claude/skills/_shared/workspace.py --skill troubleshoot --slug {slug} --verify
python3 .claude/skills/_shared/validate_doc.py --contract work-log \
  --dir {paths.team_dir} --expect-files 2
```

The first call exits 0 when `bug_report`, `context`, `root_cause`, and `impact` are all present and non-trivial; exit 2 means one is missing or empty (read `verify.missing` / `verify.empty`). The second exits 0 only when both teammate logs exist and satisfy the work-log contract; exit 2 means a log is missing (`error: "expected 2 files, found N"`) or malformed (`files_failed > 0`, with `sections_missing` per file). "Wait for both teammates to complete" is a self-report; these two commands are the check. Resolve every gap before continuing.

Read outputs from Phase 2:
- `{paths.root_cause}` -- Root cause analysis
- `{paths.impact}` -- Impact assessment

### Step 1.5: Codex Fix Plan Validation

Before presenting to the user, validate the fix plan with Codex. Write the prompt to a file, then invoke the wrapper:

```text
Objective: Validate this fix plan for completeness and correctness.
Context:
- Root cause: {from Root Cause Analyst}
- Proposed fix: {recommended approach}
- Blast radius: {from Impact Investigator}
- Fix tasks: {task list}
Constraints:
- Check for missing edge cases
- Verify the fix addresses the root cause (not just symptoms)
- Identify potential new issues the fix could introduce
- Suggest additional test cases if needed
Output format:
## Validation Result (PASS / NEEDS_REVISION)
## Missing Coverage
## Potential New Issues
## Additional Test Cases Recommended
## Revised Task List (if needed)
```

```bash
python3 .claude/skills/_shared/codex_consult.py --prompt-file .claude/logs/codex/prompt-troubleshoot-plan-validation.md --label troubleshoot-plan-validation
```

If Codex returns NEEDS_REVISION, update the fix plan before presenting to user.

### Step 2: Create Fix Plan

Create task list using TodoWrite:

```python
{
    "content": "Fix {specific task}",
    "activeForm": "Fixing {specific task}",
    "status": "pending"
}
```

Task breakdown should follow `references/debug-patterns.md`.

Typical fix task structure:
1. **Write failing test** -- Reproduce the bug as a test case
2. **Apply fix** -- Implement the root cause fix
3. **Verify fix** -- Re-run the original repro command with the expectation
   asserted by the script rather than read by eye, and with its own label so the
   Phase 1 failure log survives:

   ```bash
   python3 .claude/skills/troubleshoot/repro.py "<repro-command>" \
     --label {slug}-fix-verify --expect-exit 0
   ```

   Exit `0` is the verification. Exit `2` means the fix is **not** verified
   (`error: "expected exit 0, got N"`); exit `3` means it timed out and nothing
   was verified at all. Do not report a verified fix on any exit code but `0`.
4. **Check regressions** -- Run the quality gates:

   ```bash
   bash .claude/skills/_shared/verify.sh
   ```

   Read the JSON: `overall` is `pass` / `fail` / `no_gates`. Exit `0` is a pass; exit **`2`** is a gate failure *or* `no_gates` -- inspect `log_file` and the per-tool `tools` object. `no_gates` means zero gates actually ran, which is a contract violation, not a pass: fall back to the project's own verification commands and confirm manually, and pass `--allow-no-gates` only when you have done so deliberately. Quote the `tools` object rather than re-typing each status, so a `skipped` gate is never reported as a pass.
5. **Fix collateral damage** -- Address blast radius items (if any)

### Step 3: Update Shared State

Add bug context to `.claude/STATE.md` for cross-session persistence using the
shared writer script and `.claude/rules/agent-state.md`.

**Gather these fields** from the diagnosis:

- **Context**: Error summary, Root cause, Affected files
- **Fix Approach**: Recommended approach from Root Cause Analyst
- **Codex Validation**: Result + additional test cases
- **Regression Risks**: Key risks from Impact Investigator + Codex assessment
- **Decisions** with rationale

**Write the input JSON** to `{paths.state_input}` (from Phase 1 Step 0):

```json
{
  "title": "{slug}",
  "sections": [
    {"heading": "Context", "content": "- Error: ...\n- Root cause: ...\n- Affected files: ..."},
    {"heading": "Fix Approach", "content": "- {approach}"},
    {"heading": "Regression Risks", "content": "- {risks}"},
    {"heading": "Decisions", "content": "- {Decision 1}: {rationale}"}
  ]
}
```

**Run dry-run**, review the preview, then apply:

```bash
python3 .claude/skills/_shared/append_state_block.py \
  --type bug-fix --input {paths.state_input}
# Review the preview file path in the JSON output, then:
python3 .claude/skills/_shared/append_state_block.py \
  --type bug-fix --input {paths.state_input} --apply
```

Verify `"ok": true` and `"progress_tracker_preserved": true` in the output.
Exit code 2 means the state structure is invalid; stop before writing.

### Step 4: Present to User

Compose the diagnosis and fix plan following the template contract in
`references/diagnosis-template.md`. Write the composed presentation to
`{paths.diagnosis}` (resolved in Phase 1 Step 0, never hand-built) and validate
its structure before presenting it:

```bash
python3 .claude/skills/_shared/validate_doc.py --contract diagnosis \
  --file {paths.diagnosis}
python3 .claude/skills/_shared/workspace.py --skill troubleshoot \
  --slug {slug} --verify --require diagnosis
```

`references/diagnosis-template.md` is the section source of truth (the
`diagnosis` contract is pinned to it by `tests/test_validate_doc.py`). Exit 0
means every required section is present; exit 2 means one is missing and
`sections_missing` names it -- most often `Alternative Approaches Considered`,
the section a rushed presentation drops. Then present the validated document to
the user. Structure is all this gate checks: whether the diagnosis is *correct*
remains the Codex validation in Step 1.5 plus the user's approval.

---

## Output Files

Paths resolved once in Phase 1 Step 0 (`.claude/skills/_shared/workspace.py --skill troubleshoot`):

| File | Author | Purpose |
|------|--------|---------|
| `{paths.bug_report}` | Lead | Bug Report (Phase 1 synthesis) |
| `{paths.context}` | Opus Subagent | Initial error context analysis |
| `{paths.root_cause}` | Root Cause Analyst | Root cause analysis (Codex-driven) |
| `{paths.impact}` | Impact Investigator | Impact assessment (with Codex risk analysis) |
| `.claude/STATE.md` (updated) | Lead | Cross-session bug fix context |
| Task list (internal) | Lead | Fix implementation tracking |

Run artifacts under `.claude/logs/`, keyed by `{slug}` so successive runs do not
overwrite each other. The repro logs are not part of `--verify`; the diagnosis is
checkable on demand with `--require diagnosis` (it is not a default required key,
because in Phases 1-2 it does not exist yet):

| File | Author | Purpose |
|------|--------|---------|
| `.claude/logs/troubleshoot-repro-{slug}-initial.log` | `repro.py` | Phase 1 failure capture |
| `.claude/logs/troubleshoot-repro-{slug}-fix-verify.log` | `repro.py` | Phase 3 fix-verification capture |
| `{paths.diagnosis}` | Lead | Phase 3 presentation, validated with `--contract diagnosis` and `--require diagnosis` |

---

## Tips

- **Codex-first**: Every phase consults Codex. This is intentional -- Codex excels at deep code reasoning and pattern recognition that complements Opus's broad context analysis
- **Codex for hypothesis testing**: When hypotheses conflict, ask Codex to evaluate evidence for each. Codex is better at logical reasoning about code behavior than pattern matching
- **Phase 1**: Opus subagent (1M context) reproduces the error and gathers full context, then Codex generates initial hypotheses, while Claude collects details from the user
- **Phase 2**: Agent Teams bidirectional communication allows Root Cause Analyst (Codex-driven) and Impact Investigator (Opus + Codex) to converge on the true root cause
- **Phase 3**: Codex validates the fix plan before presenting to user. After approval, proceed to implementation with `/team-execute`
- **Competing Hypotheses**: If Phase 2 yields inconclusive results, consider spawning additional teammates with adversarial hypotheses (see the `/team-execute` Phase 2 competing hypotheses pattern)
- **Quick bugs**: For obvious single-file bugs, skip this skill and fix directly -- use this skill for non-trivial bugs where root cause is unclear
- **Ctrl+T**: Toggle task list display
- **Shift+Up/Down**: Navigate between teammates (when using Agent Teams)
