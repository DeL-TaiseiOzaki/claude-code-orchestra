---
name: troubleshoot
description: |
  Diagnose and plan fixes for errors/bugs with multi-agent collaboration (Opus 4.6 + Agent Teams).
  Phase 1: Error reproduction & context gathering (Opus subagent 1M context + Claude user interaction).
  Phase 2: Parallel diagnosis (Agent Teams: Root Cause Analyst + Impact Investigator).
  Phase 3: Fix plan synthesis & user approval.
  Fix implementation is handled separately by /team-implement.
metadata:
  short-description: Error/bug diagnosis with Agent Teams (Diagnosis phase)
---

# Troubleshoot

**Error/bug diagnosis skill leveraging Opus 1M context and Agent Teams.**

## Overview

This skill handles the diagnosis phases (Phase 1-3). Fix implementation is done via `/team-implement`, and review via `/team-review`.

```
/troubleshoot <error description>   ← This skill (diagnosis & fix planning)
    ↓ After approval
/team-implement                     ← Parallel fix implementation
    ↓ After completion
/team-review                        ← Parallel review (regression check)
```

## Workflow

```
Phase 1: REPRODUCE & UNDERSTAND (Opus 1M context + Claude Lead)
  Opus subagent analyzes the error context, Claude gathers details from the user
    ↓
Phase 2: DIAGNOSE (Agent Teams — Parallel)
  Root Cause Analyst (Codex) ←→ Impact Investigator (Opus) communicate bidirectionally
    ↓
Phase 3: FIX PLAN & APPROVE (Claude Lead + User)
  Integrate diagnosis results, create fix plan and get user approval
```

---

## Phase 1: REPRODUCE & UNDERSTAND (Opus Subagent + Claude Lead)

**Reproduce the error and gather full context with Opus subagent's 1M context while Claude interacts with the user.**

> Main orchestrator context is precious. Large-scale error context analysis is delegated to Opus subagent (1M context).

### Step 1: Gather Error Details from User

Ask the user to provide:

1. **Error message / stack trace**: Full error output
2. **Reproduction steps**: How to trigger the error
3. **Expected vs actual behavior**: What should happen vs what happens
4. **Environment**: OS, Python version, dependency versions
5. **Recent changes**: What changed before the error appeared (if known)

### Step 2: Reproduce & Analyze with Opus Subagent

Use a general-purpose subagent (Opus) to reproduce and analyze:

```
Task tool:
  subagent_type: "general-purpose"
  prompt: |
    Investigate this error in the codebase:

    Error: {error message / stack trace}
    Reproduction: {steps from user}

    Tasks:
    1. Try to reproduce the error:
       - Run the failing command/test
       - Capture full error output with stack trace
    2. Analyze the error context:
       - Read all files mentioned in the stack trace
       - Trace the execution flow leading to the error
       - Identify the immediate cause (what line throws/fails)
    3. Gather surrounding context:
       - Check recent git history for related changes: git log --oneline -20
       - Look for related tests and whether they pass/fail
       - Check if similar patterns exist elsewhere in the codebase

    Use Bash, Glob, Grep, and Read tools to investigate thoroughly.

    Save analysis to .claude/docs/research/troubleshoot-{issue}-context.md
    Return concise summary (5-7 key findings).
```

### Step 3: Create Bug Report

Combine error details + codebase analysis into a "Bug Report":

```markdown
## Bug Report: {issue}

### Error
- Message: {error message}
- Location: {file:line}
- Stack trace: {key frames}

### Reproduction
- Steps: {numbered list}
- Reproducibility: {always / intermittent / environment-specific}

### Immediate Context
- Failing code: {file:line and surrounding logic}
- Call chain: {caller → ... → failing function}
- Recent changes: {relevant git commits}

### Affected Area
- Files involved: {list}
- Related tests: {list with pass/fail status}

### Initial Hypotheses
1. {Hypothesis A}: {brief reasoning}
2. {Hypothesis B}: {brief reasoning}
3. {Hypothesis C}: {brief reasoning}
```

This bug report is passed to Phase 2 teammates as shared context.

---

## Phase 2: DIAGNOSE (Agent Teams — Parallel)

**Launch Root Cause Analyst and Impact Investigator in parallel via Agent Teams with bidirectional communication.**

> Key difference from subagents: Teammates can communicate with each other.
> Root Cause Analyst's findings change Impact Investigator's scope, and Impact Investigator's context informs root cause analysis.

### Team Setup

```
Create an agent team for troubleshooting: {issue}

Spawn two teammates:

1. **Root Cause Analyst** — Uses Codex CLI for deep code analysis and reasoning
   Prompt: "You are the Root Cause Analyst for bug: {issue}.

   Your job: Identify the definitive root cause of this error through deep code analysis.

   Bug Report:
   {bug report from Phase 1}

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

   How to consult Codex:
   codex exec --model gpt-5.4 --sandbox read-only --full-auto "{question}" 2>/dev/null

   Use Codex for:
   - Complex control flow analysis
   - Reasoning about race conditions / state mutations
   - Evaluating fix approaches and their trade-offs

   Save analysis to .claude/docs/research/troubleshoot-{issue}-root-cause.md

   Communicate with Impact Investigator teammate:
   - Share root cause findings that expand the affected scope
   - Request context about specific code paths or history
   - Confirm or refute hypotheses based on shared evidence

   IMPORTANT — Work Log:
   When ALL your tasks are complete, write a work log file to:
     .claude/logs/agent-teams/{team-name}/root-cause-analyst.md

   Use this format:
   # Work Log: Root Cause Analyst
   ## Summary
   (1-2 sentence summary of root cause finding)
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
   ## Communication with Teammates
   - → {recipient}: {summary of message sent}
   - ← {sender}: {summary of message received}
   ## Issues Encountered
   - {issue}: {how it was resolved}
   (If none, write 'None')
   "

2. **Impact Investigator** — Uses Opus with Git history, codebase search, and WebSearch
   Prompt: "You are the Impact Investigator for bug: {issue}.

   Your job: Determine the full scope and impact of this bug, and gather context for the fix.

   Bug Report:
   {bug report from Phase 1}

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

   Save findings to .claude/docs/research/troubleshoot-{issue}-impact.md

   Communicate with Root Cause Analyst teammate:
   - Share git history context that informs root cause
   - Share external findings (known issues, upstream fixes)
   - Request clarification on which code paths to investigate

   IMPORTANT — Work Log:
   When ALL your tasks are complete, write a work log file to:
     .claude/logs/agent-teams/{team-name}/impact-investigator.md

   Use this format:
   # Work Log: Impact Investigator
   ## Summary
   (1-2 sentence summary of impact assessment)
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
   ## Communication with Teammates
   - → {recipient}: {summary of message sent}
   - ← {sender}: {summary of message received}
   ## Issues Encountered
   - {issue}: {how it was resolved}
   (If none, write 'None')
   "

Wait for both teammates to complete their tasks.
```

### Why Bidirectional Communication Matters for Debugging

```
Example interaction flow:

Root Cause Analyst: "The error occurs because parse_config() returns None when key is missing"
    → Impact Investigator: "Checking git blame — this was changed in commit abc123"
    → Impact Investigator: "Found 5 other callers of parse_config() that don't handle None"
    → Root Cause Analyst: "Expanding fix scope — need to either fix callers or fix parse_config()"
    → Root Cause Analyst: "Codex recommends: fix parse_config() to raise KeyError instead of returning None"
    → Impact Investigator: "Confirmed: all 5 callers already have try/except for KeyError"
    → Root Cause Analyst: "Root cause confirmed. Fix approach: restore KeyError in parse_config()"
```

Without Agent Teams, this discovery loop would require multiple sequential subagent rounds.

---

## Phase 3: FIX PLAN & APPROVE (Claude Lead)

**Integrate Agent Teams diagnosis results, create a fix plan, and request user approval.**

### Step 1: Synthesize Diagnosis

Read outputs from Phase 2:
- `.claude/docs/research/troubleshoot-{issue}-root-cause.md` — Root cause analysis
- `.claude/docs/research/troubleshoot-{issue}-impact.md` — Impact assessment

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
1. **Write failing test** — Reproduce the bug as a test case
2. **Apply fix** — Implement the root cause fix
3. **Verify fix** — Confirm the failing test now passes
4. **Check regressions** — Run full test suite
5. **Fix collateral damage** — Address blast radius items (if any)

### Step 3: Update CLAUDE.md

Add bug context to CLAUDE.md for cross-session persistence:

```markdown
---

## Current Bug Fix: {issue}

### Context
- Error: {1-2 sentence summary}
- Root cause: {description}
- Affected files: {list}

### Fix Approach
- {Recommended approach from Root Cause Analyst}

### Regression Risks
- {Key risks from Impact Investigator}

### Decisions
- {Decision 1}: {rationale}
- {Decision 2}: {rationale}
```

### Step 4: Present to User

Present the diagnosis and fix plan to the user:

```markdown
## Diagnosis Report: {issue}

### Error Reproduction
{Reproduction result — confirmed / partially confirmed / could not reproduce}

### Root Cause (Root Cause Analyst)
- **Defect**: {description of the underlying defect}
- **Location**: `{file}:{line}`
- **Trigger**: {conditions under which the error occurs}
- **Evidence**: {key evidence supporting this conclusion}

### Impact Assessment (Impact Investigator)
- **Blast radius**: {affected code paths and features}
- **Introducing commit**: {hash and description, if identified}
- **External context**: {known issues, upstream fixes if any}
- **Regression risk**: {what could break during fix}

### Fix Plan ({N} tasks)
1. Write failing test to reproduce the bug
2. {Fix task — the core fix}
3. {Additional fix tasks from blast radius}
4. Run full test suite for regression check

### Alternative Approaches Considered
- **Approach A**: {description} — {why chosen / not chosen}
- **Approach B**: {description} — {why chosen / not chosen}

### Next Steps
1. Shall we proceed with this fix plan?
2. After approval, start fix implementation with `/team-implement`
3. After implementation, run regression review with `/team-review`

---
Shall we proceed with this fix plan?
```

---

## Output Files

| File | Author | Purpose |
|------|--------|---------|
| `.claude/docs/research/troubleshoot-{issue}-context.md` | Opus Subagent | Initial error context analysis |
| `.claude/docs/research/troubleshoot-{issue}-root-cause.md` | Root Cause Analyst | Root cause analysis |
| `.claude/docs/research/troubleshoot-{issue}-impact.md` | Impact Investigator | Impact assessment |
| `CLAUDE.md` (updated) | Lead | Cross-session bug fix context |
| Task list (internal) | Lead | Fix implementation tracking |

---

## Tips

- **Phase 1**: Opus subagent (1M context) reproduces the error and gathers full context while Claude collects details from the user
- **Phase 2**: Agent Teams bidirectional communication allows Root Cause Analyst (Codex) and Impact Investigator (Opus) to converge on the true root cause
- **Phase 3**: After fix plan approval, proceed to implementation with `/team-implement`
- **Competing Hypotheses**: If Phase 2 yields inconclusive results, consider spawning additional teammates with adversarial hypotheses (see `/team-review` competing hypotheses pattern)
- **Quick bugs**: For obvious single-file bugs, skip this skill and fix directly — use this skill for non-trivial bugs where root cause is unclear
- **Ctrl+T**: Toggle task list display
- **Shift+Up/Down**: Navigate between teammates (when using Agent Teams)
