---
name: plan
description: Create a detailed implementation plan for a feature or task. Use when user wants to plan before coding.
disable-model-invocation: true
---

# Create Implementation Plan

Create an implementation plan for $ARGUMENTS.

**A plan is a file, not a transcript.** The plan produced here is written to a
resolved path, validated against a document contract, reviewed by Codex, and
approved by the user — in that order, and all four. A plan that lives only in
the conversation cannot be handed to `/team-execute`, cannot survive a
`/checkpointing` compaction, and cannot be re-read next session.

## Planning Process

### 0. Resolve the Workspace (always first)

Resolve this plan's slug and output path once. The title becomes the file name,
so give it a short English descriptor — not the user's raw wording, which the
Language Protocol keeps out of paths:

```bash
python3 .agents/skills/_shared/workspace.py \
  --skill plan --title "<short English title>" --create
```

The JSON on stdout carries `slug` and `paths.plan_doc`
(`.agents/docs/plans/{slug}.md`). Every `{slug}` and every output path below —
and the `/team-execute` handoff in step 6 — MUST come from this JSON verbatim,
never be re-derived by hand: two hand-derived slugs are exactly how a plan and
its executor's work logs drift apart. Exit codes: `0` resolved (and created);
`1` bad arguments.

If `.agents/docs/plans/{slug}.md` already exists, the plan is a revision of that
document — read it first and say so, rather than silently overwriting it.

### 1. Requirements Analysis

First clarify with the user:

- **Purpose**: What to achieve
- **Scope**: What to include, what to exclude
- **Constraints**: Technical, time, dependencies

Ask, do not assume. Unresolved items belong in `### Open Questions`, not in a
guessed step.

### 2. Current State Investigation

Reading the codebase for a plan is broad-context work: delegate it rather than
consuming orchestrator context.

```
Task tool:
  subagent_type: "general-purpose-opus"
  prompt: |
    Investigate this codebase for a planned change: {purpose from step 1}

    Report, with file:line evidence for every claim:
    1. Related existing code — which modules already do something similar
    2. Files that will need to change, and why each one
    3. Libraries and patterns the change should reuse (project conventions)
    4. Existing tests that cover the affected area, and gaps in that coverage
    5. Constraints or invariants the change must not break

    Use Glob, Grep, and Read. Do not implement anything.
    Return the findings; do not summarize away the file paths.
```

The returned findings are the source of `### Scope` and `### Risks &
Considerations` in the plan document. A plan whose Scope names no concrete file
paths is a plan written without reading the code — send the investigation back
rather than proceeding.

### 3. Break Down Implementation Steps

`.agents/rules/codex-delegation.md` names "you need a step-by-step
implementation plan" and "design/architecture decisions are involved" as
explicit Codex triggers, so step decomposition is a **MANDATORY** Codex
consult — the same rule `/feature` follows for the same artifact class.

Write the prompt body to a file, then invoke the shared wrapper (the directory
is not created by the wrapper before it reads the prompt, so create it first):

```bash
mkdir -p .agents/logs/codex
# write the prompt body to .agents/logs/codex/prompt-plan-{slug}-steps.md, then:
python3 .agents/skills/_shared/codex_consult.py \
  --prompt-file .agents/logs/codex/prompt-plan-{slug}-steps.md \
  --label plan-{slug}-steps --sandbox read-only
```

Prompt body:

```
Objective: Decompose this change into an ordered, independently testable implementation plan.
Context:
- Purpose: {purpose from step 1}
- Scope in / out: {from step 1}
- Constraints: {from step 1}
- Current state: {findings from step 2, with file paths}
Constraints:
- Order steps by dependency (what must exist before what)
- Each step is independently testable; name its verification
- Put high-risk and high-uncertainty steps first
- Keep steps small; do not over-detail work that will be re-decided during implementation
Output format:
## Implementation Steps (ordered by dependency)
## Verification per Step
## Risks and Mitigations
## Open Questions
```

Read the answer from the JSON output's `response_file`. Exit codes: `0` the call
succeeded — read `response_file`; `1` bad args; `2` codex CLI not on PATH; `3`
codex exited non-zero or timed out — inspect `error` and `stderr_file` before
retrying or escalating. Codex proposes the decomposition; deciding which steps
are the right steps stays yours.

### 4. Output Format

Write the plan to the `plan_doc` path from step 0 (`.agents/docs/plans/{slug}.md`)
using this shape. The five `###` sections are the `plan-doc` document contract —
renaming or dropping one is a validation failure in step 5:

```markdown
## Implementation Plan: {Title}

### Purpose
{1-2 sentences}

### Scope
- New files: {list}
- Modified files: {list}
- Dependencies: {list}

### Implementation Steps

#### Step 1: {Title}
- [ ] {Specific task}
- [ ] {Specific task}
**Verification**: {Completion criteria for this step}

#### Step 2: {Title}
...

### Risks & Considerations
- {Potential issues and mitigations}

### Open Questions
- {Items to clarify before implementation}
```

### 5. Completion Gates

A plan is done when **all four** gates below have passed. They check different
things and none of them substitutes for another: the shape gate proves the
document has its sections, never that the plan is any good.

**Gate 1 — shape.** The document contract:

```bash
python3 .agents/skills/_shared/validate_doc.py \
  --contract plan-doc --file .agents/docs/plans/{slug}.md
```

Exit `0` the required sections are present; `1` bad args or the file is
unreadable; `2` a required section is missing — read `sections_missing` in the
JSON and add the section. Exit `0` means the plan has the right *shape*. It says
nothing about whether the steps are correct, complete, or ordered sensibly.

**Gate 2 — the artifact exists and is not empty:**

```bash
python3 .agents/skills/_shared/workspace.py --skill plan --slug {slug} --verify
```

Exit `0` the plan document exists and is non-empty; exit `2` it is missing or
effectively empty — the plan was never written, so do not report a plan.

**Gate 3 — adequacy (MANDATORY Codex validation).** Same rigour `/feature`
applies to its implementation plan. Write the body below to
`.agents/logs/codex/prompt-plan-{slug}-validate.md` and consult with
`--sandbox read-only`:

```
Objective: Validate this implementation plan for completeness, correctness, and risk.
Context:
- Purpose and scope: {from step 1}
- Current state: {findings from step 2}
- Implementation plan: contents of .agents/docs/plans/{slug}.md
Constraints:
- Check for missing edge cases or error handling
- Verify the step order is actually dependency-correct
- Ensure each step's stated verification would really detect a failure
- Identify integration risks and convention violations
- Check that nothing in Open Questions is in fact a blocker disguised as a question
Output format:
## Validation Result (PASS / NEEDS_REVISION)
## Missing Coverage
## Ordering Problems
## Integration Risks
## Revised Steps (if NEEDS_REVISION)
```

On `NEEDS_REVISION`, revise the plan document and re-run gates 1 and 3 before
continuing. How to revise is judgment; re-validating is not optional.

**Gate 4 — user approval.** Present the plan (path included) and ask before any
implementation starts. No script can decide that a plan is good enough to build.

### 6. Handoff

Report the resolved path so the next skill can consume it:

```text
Plan written to .agents/docs/plans/{slug}.md (slug: {slug}) — Codex: PASS
Next: /team-execute with slug {slug}
```

`/team-execute` resolves its own workspace from that same `slug` and reads the
plan from `.agents/docs/plans/{slug}.md`. Hand over the path and the slug; do not
paste the plan back into the conversation as the source of truth, and do not
invoke another skill from here — this is a handoff the user makes.

## Notes

- Plans should be at actionable granularity
- Include verification method for each step
- Ask questions at planning stage for unclear points
- Don't over-detail (adjust during implementation)
- Deciding the steps, the risks, and what belongs in Open Questions is
  judgment and stays prose; only the artifact's path, shape, and gates are
  mechanical
