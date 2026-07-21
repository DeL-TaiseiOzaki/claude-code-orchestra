---
name: feature
description: |
  Unified feature planning & implementation skill — replaces the old /add-feature and
  /start-feature skills (both trigger phrases still apply here).
  MODE=existing (formerly /add-feature): add a feature to an established codebase with
  Codex-first collaboration — Codex is consulted in every phase for scope analysis,
  architecture design, implementation planning, and validation.
  MODE=greenfield (formerly /start-feature): start a large or new feature that requires
  external research — Agent Teams (Researcher + Architect) do parallel research & design.
  Both modes share Phase 3 complexity routing (SIMPLE: Codex direct, MODERATE: Codex +
  /team-execute --review-only, COMPLEX: /team-execute).
metadata:
  short-description: Feature planning with existing/greenfield modes and complexity routing
---

# Feature

**One entry point for feature work, two modes:**

- **MODE=existing** (old `/add-feature` path): the feature goes into an **established** codebase whose conventions are already known. No external research needed → Codex-direct scope → design → plan.
- **MODE=greenfield** (old `/start-feature` path): a **large or new** feature that needs external research and parallel design → Agent Teams (Researcher + Architect) with bidirectional communication.

Both modes converge on a shared Phase 3: user approval + complexity-routed implementation.

> Preflight: ensure codex CLI is current (see codex-system skill).

```
/feature <feature description>
    | MODE determination (AskUserQuestion when ambiguous)
    ├─ MODE=existing   : Phase 1E SCOPE  -> Phase 2E DESIGN (Codex direct)
    └─ MODE=greenfield : Phase 1G UNDERSTAND -> Phase 2G RESEARCH & DESIGN (Agent Teams)
    | Phase 3 (shared): PLAN, APPROVE & IMPLEMENT
    SIMPLE   (1-3 files, <50 LOC) -> Codex danger-full-access direct
    MODERATE (3-5 files)          -> Codex danger-full-access + /team-execute --review-only
    COMPLEX  (5+ files)           -> /team-execute (implement + review)
```

---

## Mode Determination (always first)

Decide the MODE before anything else. Signals:

| Signal | MODE=existing | MODE=greenfield |
|--------|---------------|-----------------|
| Codebase state | Established, conventions known | New area, or conventions absent |
| External research needed | No — Codex reasons about existing patterns directly | Yes — libraries/tools/reference architectures must be researched |
| Feature size | Localized addition | Large, multi-module, or project kickoff |
| Design source | Codex (read-only consults) | Agent Teams (Researcher + Architect) |

If the signals are mixed or unclear, ask via `AskUserQuestion` — do NOT guess:

```yaml
question: "Which feature mode applies?"
multiSelect: false
options:
  - label: "existing"
    description: "Add to an established codebase; conventions known; no external research (old /add-feature)."
  - label: "greenfield"
    description: "Large/new feature; needs external research and parallel design via Agent Teams (old /start-feature)."
```

## When NOT to Use

- Bug diagnosis where root cause is unclear → `/troubleshoot`
- Executing an already-approved implementation plan → `/team-execute`
- Feasibility unknown / go-no-go decision needed first → `/spike`
- Truly trivial changes (single function, <10 LOC) → edit directly, skip this skill

Full skill routing: root `AGENTS.md` section "Routing Policy".

---

## Common Protocols (both modes)

### Step 0: Read PROGRESS.md (always first)

Before anything else, if `PROGRESS.md` exists at the repository root, **read it**.
It is the rolling summary of the latest 5 checkpoints (maintained by
`/checkpointing`) and carries the most recent session context, in-progress work,
and the "将来のアクション" (next actions) from prior sessions. Use it to ground
the new feature in what already happened and to avoid re-deciding settled
questions. If it is absent (fresh repo), skip this step.

### Requirements Gathering

Ask the user to clarify:

1. **Purpose / feature description**: What should the feature do? What do you want to achieve?
2. **Expected behavior**: How should it work from the user's perspective?
3. **Scope boundaries**: What to include / exclude?
4. **Technical preferences / constraints**: Specific libraries, patterns, or constraints?
5. **Success criteria**: How do you determine the feature is complete?
6. **Final design** (greenfield): What form should the result take?

### Opus Subagent Codebase Scan

Main orchestrator context is precious — large-scale codebase scanning is always
delegated to `general-purpose-opus` (Opus, 1M context):

```
Task tool:
  subagent_type: "general-purpose-opus"
  prompt: |
    Analyze this codebase for feature: {feature description}

    Tasks (MODE=existing — affected-area scan):
    1. Identify the areas relevant to this feature:
       - Which modules/files will be affected?
       - What are the existing patterns in those areas?
       - What interfaces/contracts exist that the feature must conform to?
    2. Analyze existing conventions:
       - Code patterns (naming, structure, error handling)
       - Test patterns (test location, fixture usage, assertion style)
       - Import and dependency patterns
    3. Map dependencies:
       - What does the affected code depend on?
       - What depends on the affected code? (downstream consumers)
       - Are there shared utilities or base classes to leverage?

    Tasks (MODE=greenfield — comprehensive scan):
    - Directory structure and organization
    - Key modules and their responsibilities
    - Existing patterns and conventions
    - Dependencies and tech stack
    - Test structure

    Use Glob, Grep, and Read tools to investigate thoroughly.

    Save analysis to .agents/docs/research/feature-{feature}-codebase.md
    Return concise summary (5-7 key findings).
```

Claude may supplement the subagent's analysis with targeted Glob/Grep/Read on specific files.

### Codex Consult Protocol

Every Codex consultation in this skill uses the same wrapper (read-only for
analysis/design; danger-full-access only for implementation in Phase 3):

```bash
codex exec --model "${CODEX_MODEL:-gpt-5.6-sol}" --sandbox read-only "{prompt}" < /dev/null 2>/dev/null
```

Prompts below show only the prompt body (Objective / Context / Constraints /
Output format). MODE=existing consultations are **MANDATORY** — do not skip them.
The most important input to every Codex prompt is the existing codebase patterns
from the Opus subagent scan — always include them.

### DESIGN.md Update

In both modes, record the feature's architecture decisions in
`.agents/docs/DESIGN.md` (the macro 要件定義書) before presenting the plan:

```markdown
## Feature: {feature}

### Architecture
- {Key architecture decisions from Codex / Architect}

### Integration Points
- {How the feature connects to existing code}

### Design Decisions
- {Decision 1}: {rationale}
- {Decision 2}: {rationale}
```

(In MODE=greenfield the Architect teammate updates DESIGN.md directly during Phase 2G.)

### Shared State Update

Append feature context to `.agents/STATE.md` for cross-session persistence,
following `.agents/rules/agent-state.md`. Use the shared writer script for a
deterministic, atomic update; never edit root `AGENTS.md`.

**Gather these fields** from the planning phases:

- **Context**: Goal (1-2 sentences), Key files (new/modified), Dependencies, Complexity (SIMPLE / MODERATE / COMPLEX)
- **Architecture**: Key decisions from Codex / Architect
- **Library Constraints** (greenfield) or **Codex Validation** (existing)
- **Integration Points** and **Decisions** with rationale

**Write the input JSON** to `.agents/logs/zone-c-input.json`:

```json
{
  "title": "{feature name}",
  "sections": [
    {"heading": "Context", "content": "- Goal: ...\n- Key files: ...\n- Dependencies: ...\n- Complexity: MODERATE"},
    {"heading": "Architecture", "content": "- {decisions}"},
    {"heading": "Decisions", "content": "- {Decision 1}: {rationale}"}
  ]
}
```

**Run dry-run**, review the preview, then apply:

```bash
python3 .agents/skills/_shared/append_state_block.py \
  --type feature --input .agents/logs/zone-c-input.json
# Review the preview file path in the JSON output, then:
python3 .agents/skills/_shared/append_state_block.py \
  --type feature --input .agents/logs/zone-c-input.json --apply
```

Verify `"ok": true` and `"progress_tracker_preserved": true` in the output.
Exit code 2 means the state structure is invalid; stop before writing.

Timing: MODE=greenfield writes this at plan time (Phase 3); MODE=existing may
defer it to post-implementation. Either way it is written exactly once per feature.

### Work Logs (Agent Teams roles)

All teammates spawned in MODE=greenfield write their work log to
`.agents/logs/agent-teams/{team-name}/{teammate}.md` per the shared format:
`.agents/skills/_shared/work-log-format.md`.

---

## MODE=existing — Phase 1E: SCOPE (Opus Subagent + Codex + Claude Lead)

**Understand the feature's scope and impact on the existing codebase: run the Opus subagent scan (common protocol, existing task list) and consult Codex for scope and impact analysis, while Claude clarifies requirements with the user (common protocol).**

### Codex Scope & Impact Analysis (MANDATORY)

Via the Codex consult protocol:

```
Objective: Analyze the scope and impact of adding this feature to the existing codebase.
Context:
- Feature: {feature description}
- Affected modules: {from Opus subagent analysis}
- Existing patterns: {from Opus subagent analysis}
- Dependencies: {from Opus subagent analysis}
Constraints:
- Assess how many files need to change and estimate LOC
- Classify complexity: SIMPLE (1-3 files, <50 LOC), MODERATE (3-5 files), COMPLEX (5+ files)
- Identify integration points where the feature connects to existing code
- Flag risks: breaking changes, performance concerns, test coverage gaps
Output format:
## Scope Assessment
## Complexity Classification (SIMPLE / MODERATE / COMPLEX)
## Integration Points
## Affected Files (with change type: new / modify)
## Risks and Concerns
## Recommended Approach
```

Use Codex's complexity classification to determine the implementation route in Phase 3.

### Create Feature Brief

Combine user requirements + codebase analysis + Codex scope assessment into a Feature Brief following the MODE=existing template in `references/brief-templates.md`.

This brief is passed to Phase 2E for design.

---

## MODE=existing — Phase 2E: DESIGN (Codex Architecture + Plan + Validation)

**Codex designs the architecture, creates an implementation plan, and validates completeness. All three consultations are MANDATORY.**

> Unlike MODE=greenfield which uses Agent Teams (Researcher + Architect) for design,
> MODE=existing uses Codex directly because the patterns and conventions are already established.

### Step 1: Codex Architecture Design (MANDATORY)

```
Objective: Design the architecture for adding this feature to the existing codebase.
Context:
- Feature Brief: {feature brief from Phase 1E}
- Existing patterns: {conventions from codebase scan}
- Integration points: {from Codex scope analysis}
Constraints:
- Follow existing codebase conventions exactly (naming, structure, patterns)
- Minimize changes to existing code (prefer extension over modification)
- Maintain backward compatibility
- Design for testability
Output format:
## Architecture Design
## Module Structure (new files and modifications)
## Interface Design (function signatures, class APIs)
## Data Flow
## Error Handling Strategy
## Test Strategy
```

### Step 2: Codex Implementation Plan (MANDATORY)

```
Objective: Create a step-by-step implementation plan for this feature.
Context:
- Feature Brief: {feature brief from Phase 1E}
- Architecture Design: {from Step 1}
- Complexity: {SIMPLE / MODERATE / COMPLEX}
Constraints:
- Order steps by dependency (what must be built first)
- Each step should be independently testable
- Include test writing as explicit steps (TDD where possible)
- Keep individual steps small and focused
Output format:
## Implementation Steps (ordered by dependency)
## File Changes (per step: file path, change type, description)
## Test Plan (per step: what to test)
## Dependencies Between Steps
## Estimated Effort per Step
```

### Step 3: Codex Validation (MANDATORY)

```
Objective: Validate this implementation plan for completeness, correctness, and risk.
Context:
- Feature Brief: {feature brief}
- Architecture Design: {from Step 1}
- Implementation Plan: {from Step 2}
- Existing codebase patterns: {from Phase 1E}
Constraints:
- Check for missing edge cases or error handling
- Verify the plan maintains backward compatibility
- Ensure test coverage is adequate
- Identify potential integration issues
- Check that the plan follows existing conventions
Output format:
## Validation Result (PASS / NEEDS_REVISION)
## Missing Coverage
## Backward Compatibility Check
## Convention Compliance
## Integration Risks
## Additional Test Cases Recommended
## Revised Steps (if NEEDS_REVISION)
```

If Codex returns NEEDS_REVISION, update the plan and re-validate before proceeding.

Then update DESIGN.md (common protocol) and continue to Phase 3.

---

## MODE=greenfield — Phase 1G: UNDERSTAND (Opus Subagent + Claude Lead)

**Analyze the codebase with the Opus subagent scan (common protocol, greenfield task list) while Claude gathers requirements from the user (common protocol).**

### Create Project Brief

Combine codebase understanding + requirements into a Project Brief following the MODE=greenfield template in `references/brief-templates.md`.

This brief is passed to Phase 2G teammates as shared context.

---

## MODE=greenfield — Phase 2G: RESEARCH & DESIGN (Agent Teams — Parallel)

**Launch Researcher and Architect in parallel via Agent Teams with bidirectional communication.**

> Key difference from subagents: Teammates can communicate with each other.
> Researcher's findings change Architect's design, and Architect's requests trigger new research.

### Team Setup

```
Create an agent team for project planning: {feature}

Spawn two teammates:

1. **Researcher** — Uses WebSearch/WebFetch for external research (Opus 1M context)
   Prompt: "You are the Researcher for project: {feature}.

   Your job: Research external information needed for this project.

   Project Brief:
   {project brief from Phase 1G}

   Tasks:
   1. Research libraries and tools: usage patterns, constraints, best practices
   2. Find latest documentation and API specifications
   3. Identify common pitfalls and anti-patterns
   4. Look for similar implementations and reference architectures

   How to research:
   - Use WebSearch for comprehensive research:
     WebSearch: '{topic} best practices constraints recommendations'
   - Use WebFetch for targeted documentation lookup

   Save all findings to .agents/docs/research/{feature}.md
   Save library docs to .agents/docs/libraries/{library}.md

   Communicate with Architect teammate:
   - Share findings that affect design decisions
   - Respond to Architect's research requests
   - Flag constraints that limit implementation options

   IMPORTANT — Work Log:
   When ALL your tasks are complete, write your work log to
   .agents/logs/agent-teams/{team-name}/researcher.md per the shared format:
   .agents/skills/_shared/work-log-format.md
   Role-specific sections (between Tasks Completed and Communication):
   ## Sources Consulted
   - {URL or source}: {what was found}
   ## Key Findings
   - {finding}: {relevance to project}
   "

2. **Architect** — Uses Codex CLI for design and planning
   Prompt: "You are the Architect for project: {feature}.

   Your job: Use Codex CLI to design the architecture and create implementation plan.

   Project Brief:
   {project brief from Phase 1G}

   Tasks:
   1. Design architecture (modules, interfaces, data flow)
   2. Select patterns (considering existing codebase conventions)
   3. Create step-by-step implementation plan with dependencies
   4. Identify risks and mitigation strategies

   How to consult Codex:
   codex exec --model "${CODEX_MODEL:-gpt-5.6-sol}" --sandbox read-only "{question}" < /dev/null 2>/dev/null

   Update .agents/docs/DESIGN.md with architecture decisions.

   Communicate with Researcher teammate:
   - Request specific library/tool research
   - Share design constraints that need validation
   - Adjust design based on Researcher's findings

   IMPORTANT — Work Log:
   When ALL your tasks are complete, write your work log to
   .agents/logs/agent-teams/{team-name}/architect.md per the shared format:
   .agents/skills/_shared/work-log-format.md
   Role-specific sections (between Tasks Completed and Communication):
   ## Design Decisions
   - {decision}: {rationale}
   ## Codex Consultations
   - {question asked to Codex}: {key insight from response}
   "

Wait for both teammates to complete their tasks.
```

### Why Bidirectional Communication Matters

```
Example interaction flow:

Researcher: "httpx has a connection pool limit of 100 by default"
    → Architect: "Need to add connection pool config to design"
    → Architect: "Also research: does httpx support HTTP/2 multiplexing?"
    → Researcher: "Yes, via httpx[http2]. Requires h2 dependency."
    → Architect: "Updated design to use HTTP/2 for the API client module"
```

Without Agent Teams (old subagent approach), this would require:
1. Researcher subagent finishes → returns summary
2. Claude reads summary → creates new Codex subagent prompt
3. Codex subagent finishes → returns summary
4. If Codex needs more info → another researcher subagent round

Agent Teams collapses this into a single parallel session with real-time interaction.

---

## Phase 3 (shared): PLAN, APPROVE & IMPLEMENT

**Both modes converge here: synthesize, get user approval, then route implementation by complexity.**

### Step 1: Synthesize Results

- MODE=existing: Feature Brief + Codex architecture / plan / validation outputs.
- MODE=greenfield: read `.agents/docs/research/{feature}.md` (Researcher findings),
  `.agents/docs/libraries/{library}.md` (library docs), `.agents/docs/DESIGN.md`
  (Architect decisions).

### Step 2: Create Task List

Create the task list using TodoWrite:

```python
{
    "content": "Implement {specific task}",
    "activeForm": "Implementing {specific task}",
    "status": "pending"
}
```

Task breakdown should follow `references/task-patterns.md`.

### Step 3: Update DESIGN.md and Shared State

Per the common protocols above (DESIGN.md Update / Shared State Update).

### Step 4: Present to User (approval gate)

```markdown
## Feature Plan: {feature}

### Mode
{existing / greenfield} — {1-line rationale}

### Codebase / Scope Analysis
{Key findings from Phase 1 — 3-5 bullet points}

### Research Findings (greenfield: Researcher)
{Key findings — 3-5 bullet points; library constraints and recommendations}

### Complexity
- Classification: {SIMPLE / MODERATE / COMPLEX}
- Implementation route: {Codex direct / Codex + review / team-execute}

### Architecture Design (Codex / Architect)
{Architecture overview}
{Key design decisions with rationale}

### Implementation Plan ({N} steps) — Codex Validated: {PASS} (existing mode)
1. {Step 1}: {description}
2. {Step 2}: {description}
...

### File Changes Summary
| File | Change Type | Description |
|------|------------|-------------|
| {file} | {new/modify} | {what changes} |

### Test Plan
- {Test 1}: {what it verifies}

### Risks and Mitigations
- {Risk}: {mitigation}

---
Shall we proceed with this plan?
```

Do not implement until the user approves the plan.

### Step 5: Complexity Routing

Greenfield features usually classify as COMPLEX (Route C); existing-mode features
use the classification from the Codex scope analysis.

#### Route A: SIMPLE (1-3 files, <50 LOC) — Codex Direct

Codex implements directly (danger-full-access):

```bash
codex exec --model "${CODEX_MODEL:-gpt-5.6-sol}" --sandbox danger-full-access "
Objective: Implement this feature following the approved plan.
Context:
- Feature Brief: {feature brief}
- Architecture Design: {from Phase 2}
- Implementation Plan: {from Phase 2}
- Existing conventions: {from Phase 1 codebase scan}
Constraints:
- Follow the implementation plan steps exactly
- Follow existing codebase conventions (naming, structure, patterns)
- Write tests for all new functionality
- Keep changes minimal and focused
Relevant files:
- {list of files to create/modify}
Acceptance checks:
- All new tests pass
- Existing tests still pass
- Code follows existing conventions
Output format:
## Changes Made
## Tests Written
## Validation Results
## Remaining Risks
" < /dev/null 2>/dev/null
```

After Codex implementation, run the quality gates:

```bash
bash .agents/skills/_shared/verify.sh
```

Read the JSON: `overall` is `pass` / `fail` / `no_gates`. On `fail`, inspect the `log_file`. On `no_gates` (project has no configured gates), fall back to the project's own verification commands and confirm manually.

#### Route B: MODERATE (3-5 files) — Codex + Review

1. **Implement with Codex** (same as Route A, but with more files)
2. **Run basic verification** (tests, linting)
3. **Invoke `/team-execute --review-only`** for parallel review (security, quality, test coverage)

```
After Codex implementation:
/team-execute --review-only   <- Parallel review from multiple perspectives
```

#### Route C: COMPLEX (5+ files) — Team Execute

```
/team-execute   <- Phase 1: parallel implementation, Phase 2: parallel review
```

Pass the Feature Brief / Project Brief, Architecture Design, and Implementation
Plan from Phase 2 as input to `/team-execute`. Use the same `{feature}` /
`{team-name}` naming so work logs and research/design files line up across phases.

### Post-Implementation

If the `.agents/STATE.md` block was not written at plan time (existing mode), write
it now per the common protocol.

---

## Output Files

| File | Author | Purpose |
|------|--------|---------|
| `.agents/docs/research/feature-{feature}-codebase.md` | Opus Subagent | Codebase scan |
| `.agents/docs/research/{feature}.md` (greenfield) | Researcher | External research findings |
| `.agents/docs/libraries/{lib}.md` (greenfield) | Researcher | Library documentation |
| `.agents/docs/DESIGN.md` (updated) | Lead / Architect (Codex-informed) | Architecture decisions |
| `.agents/STATE.md` (updated) | Lead | Cross-session feature context |
| Task list (internal) | Lead | Implementation tracking |
| Implementation files | Codex / Agent Teams | The feature itself |
| Test files | Codex / Agent Teams | Tests for the feature |

---

## Tips

- **Mode first**: The biggest failure mode is picking the wrong path. When ambiguous, always AskUserQuestion — never guess
- **Codex-first (existing mode)**: Every phase consults Codex. Codex excels at understanding how new code fits into existing patterns and identifying integration risks; early scope classification picks the right implementation route from the start; validation catches missing edge cases and convention violations before implementation begins
- **Existing patterns**: The most important input to Codex is the existing codebase patterns from the Opus subagent scan — include them in every Codex prompt
- **Agent Teams (greenfield mode)**: Bidirectional communication lets Researcher (Opus) and Architect (Codex) influence each other in real time
- **Complexity routing**: Do not over-engineer simple features. 1-3 file changes should use Codex direct implementation, not Agent Teams
- **Quality gates**: After implementation, always run the quality gates per `.agents/rules/dev-environment.md` regardless of complexity route
- **Ctrl+T**: Toggle task list display
- **Shift+Up/Down**: Navigate between teammates (when using Agent Teams)
