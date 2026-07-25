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

### Step 0-b: Resolve the Workspace

Resolve this feature's paths once. The title becomes file and directory names,
so give it a short English descriptor of the feature — not the user's raw
wording, which the Language Protocol keeps out of paths:

```bash
python3 .agents/skills/_shared/workspace.py \
  --skill feature --title "<short English title>" --create
```

The JSON on stdout carries `slug`, `team_name`, and `paths` (`brief`,
`codebase_scan`, `research`, `state_input`, `team_dir`). From here on, every `{slug}` /
`{team-name}` / output path in this skill — and the `/team-execute` handoff in
Route C — MUST come from this JSON verbatim, never be re-derived by hand: two
independently hand-derived slugs are exactly how cross-phase artifacts drift
out of sync.

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

    Save analysis to the `codebase_scan` path from Step 0-b (`.agents/docs/research/feature-{slug}-codebase.md`).
    Return concise summary (5-7 key findings).
```

Claude may supplement the subagent's analysis with targeted Glob/Grep/Read on specific files.

### Codex Consult Protocol

Every Codex consultation in this skill goes through the shared wrapper instead
of a raw `codex exec` call, so a crashed CLI is never silently mistaken for an
empty answer. Write the prompt body to a file under the workspace
(`.agents/logs/codex/prompt-{label}.md`, beside where the wrapper writes
the response), then invoke. The wrapper creates its log directory only *after*
it reads the prompt file, so create the directory first — otherwise the heredoc
write fails in a fresh clone and the consult reads nothing (or a stale prompt
from a previous label):

```bash
mkdir -p .agents/logs/codex
# write the prompt body to .agents/logs/codex/prompt-{label}.md, then:
python3 .agents/skills/_shared/codex_consult.py \
  --prompt-file .agents/logs/codex/prompt-{label}.md --label {label} --sandbox read-only
```

Read the answer from the JSON output's `response_file` path. Exit codes: `0`
the call succeeded — read `response_file`; `1` bad args; `2` codex CLI not on
PATH; `3` codex exited non-zero or timed out — inspect `error` and
`stderr_file` before retrying or escalating.

Sandbox: `read-only` for every analysis/design/validation consult below;
Phase 3 implementation (Route A/B) uses `--sandbox danger-full-access`
instead — called out again at that call site.

Prompts below show only the prompt body (Objective / Context / Constraints /
Output format) — that is the file content for `--prompt-file`. MODE=existing
consultations are **MANDATORY** — do not skip them. The most important input to
every Codex prompt is the existing codebase patterns from the Opus subagent
scan — always include them.

### DESIGN.md Update

In both modes, record the feature's architecture decisions in
`.agents/docs/DESIGN.md` (the macro 要件定義書) before presenting the plan —
**never by editing the file directly.** DESIGN.md is user-owned and, in
MODE=greenfield, has two writers (the Architect in Phase 2G and the lead in
Phase 3); a hand edit loses the atomic replace and the concurrent-modification
guard, and one writer silently overwrites the other. Every write goes through
the shared writer, exactly as `design-tracker` does.

Write the typed input JSON to `.agents/logs/design-input-{slug}.json` (slug from
Step 0-b, so two features cannot collide on one input file):

```json
{
  "decisions": [
    {"decision": "{design decision}", "rationale": "{why}", "alternatives": "{what was rejected}"}
  ],
  "tech_choices": [
    {"area": "{area}", "technology": "{library or tool}", "rationale": "{why}", "alternatives": "{rejected}"}
  ],
  "section_updates": [
    {"heading": "## アーキテクチャ (Architecture)", "content": "- {integration point}: {how the feature connects}"}
  ]
}
```

Table rows go through their typed key — `decisions`, `requirements`, `nfr`,
`tech_choices`, `agent_roles` — which places the row in the right table and
escapes `|` in every cell. Hand-writing a table row as `section_updates`
content is refused. Use `section_updates` only for prose sections
(Architecture overview, Constraints, TODO / Open Questions).

Run the dry-run, review the preview, then apply:

```bash
python3 .agents/skills/_shared/update_design.py \
  --input .agents/logs/design-input-{slug}.json
# Review the preview file path in the JSON output, then:
python3 .agents/skills/_shared/update_design.py \
  --input .agents/logs/design-input-{slug}.json --apply --require-change
```

Verify `"ok": true` and `"result": "applied"`. `--require-change` makes a
`no-op` result (every row a duplicate, or an empty payload) exit `2`, so this
step can never report "recorded" for a run that wrote nothing. Exit `1` is a
bad input schema; exit `2` DESIGN.md is missing or structurally invalid (run
`/init`) or the run was a no-op; exit `3` DESIGN.md changed under you
(concurrent modification) or the write failed — re-read DESIGN.md, drop what the
other writer already recorded, and re-run the dry-run before applying again.

Ordering in MODE=greenfield: the Architect teammate writes its design decisions
during Phase 2G through this same script; the lead writes only after **both**
teammates have finished (Phase 3 Step 3), and records only what the Architect
did not.

### Shared State Update

Append feature context to `.agents/STATE.md` for cross-session persistence,
following `.agents/rules/agent-state.md`. Use the shared writer script for a
deterministic, atomic update; never edit root `AGENTS.md`.

**Gather these fields** from the planning phases:

- **Context**: Goal (1-2 sentences), Key files (new/modified), Dependencies, Complexity (SIMPLE / MODERATE / COMPLEX)
- **Architecture**: Key decisions from Codex / Architect
- **Library Constraints** (greenfield) or **Codex Validation** (existing)
- **Integration Points** and **Decisions** with rationale

**Write the input JSON** to the `state_input` path from Step 0-b
(`.agents/logs/state-input-{slug}.json`):

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
  --type feature --input .agents/logs/state-input-{slug}.json
# Review the preview file path in the JSON output, then:
python3 .agents/skills/_shared/append_state_block.py \
  --type feature --input .agents/logs/state-input-{slug}.json --apply
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

Combine user requirements + codebase analysis + Codex scope assessment into a
Feature Brief following the MODE=existing template in
`references/brief-templates.md`, and **write it to the `brief` path from Step 0-b**
(`.agents/docs/research/feature-{slug}-brief.md`).

The brief is the primary cross-phase artifact: it feeds all three Phase 2E Codex
prompts, Phase 3, the Route A implementation prompt, and the `/team-execute`
handoff. Interpolating it from conversation context is how a half-filled brief
reaches three Codex prompts undetected — every downstream step reads the file.

Validate it before leaving this phase:

```bash
python3 .agents/skills/_shared/validate_doc.py \
  --contract feature-brief --file .agents/docs/research/feature-{slug}-brief.md
```

Exit `0` every required section is present (the MODE=existing / MODE=greenfield
variant is auto-detected from the headings); `1` bad args or the file is
unreadable — most often it was never written; `2` a required section is missing,
listed in `sections_missing`. Do not continue to Phase 2E on a non-zero exit.

The `### Complexity Classification (from Codex)` section is where the decided
classification is **recorded once**. Phase 3's presentation and route selection
read it from this file rather than re-typing it, so a MODERATE assessment cannot
be presented and then routed as SIMPLE. Codex decides the classification; only
its propagation is mechanical.

---

## MODE=existing — Phase 2E: DESIGN (Codex Architecture + Plan + Validation)

**Codex designs the architecture, creates an implementation plan, and validates completeness. All three consultations are MANDATORY.**

> Unlike MODE=greenfield which uses Agent Teams (Researcher + Architect) for design,
> MODE=existing uses Codex directly because the patterns and conventions are already established.

### Step 1: Codex Architecture Design (MANDATORY)

```
Objective: Design the architecture for adding this feature to the existing codebase.
Context:
- Feature Brief: contents of .agents/docs/research/feature-{slug}-brief.md (from Phase 1E)
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
- Feature Brief: contents of .agents/docs/research/feature-{slug}-brief.md (from Phase 1E)
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
- Feature Brief: contents of .agents/docs/research/feature-{slug}-brief.md
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

Combine codebase understanding + requirements into a Project Brief following the
MODE=greenfield template in `references/brief-templates.md`, and **write it to
the `brief` path from Step 0-b** (`.agents/docs/research/feature-{slug}-brief.md`).

Validate it before spawning the team — a teammate that starts from a truncated
brief researches the wrong thing, and nothing downstream would notice:

```bash
python3 .agents/skills/_shared/validate_doc.py \
  --contract feature-brief --file .agents/docs/research/feature-{slug}-brief.md
```

Exit `0` every required section is present (variant auto-detected); `1` bad args
or unreadable/never written; `2` a required section is missing, listed in
`sections_missing`.

Phase 2G teammates receive the brief **path** as shared context and read the
file, so lead and teammates work from the same bytes.

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

   Project Brief: read .agents/docs/research/feature-{slug}-brief.md

   Tasks:
   1. Research libraries and tools: usage patterns, constraints, best practices
   2. Find latest documentation and API specifications
   3. Identify common pitfalls and anti-patterns
   4. Look for similar implementations and reference architectures

   How to research:
   - Use WebSearch for comprehensive research:
     WebSearch: '{topic} best practices constraints recommendations'
   - Use WebFetch for targeted documentation lookup

   Save all findings to the `research` path from Step 0-b (.agents/docs/research/{slug}.md).
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

   Project Brief: read .agents/docs/research/feature-{slug}-brief.md

   Tasks:
   1. Design architecture (modules, interfaces, data flow)
   2. Select patterns (considering existing codebase conventions)
   3. Create step-by-step implementation plan with dependencies
   4. Identify risks and mitigation strategies

   How to consult Codex:
   Write the question to .agents/logs/codex/prompt-<topic>.md, then:
   python3 .agents/skills/_shared/codex_consult.py --prompt-file .agents/logs/codex/prompt-<topic>.md --label <topic> --sandbox read-only
   Read the answer from the JSON output's response_file.

   Record architecture decisions in .agents/docs/DESIGN.md through the shared
   writer — never by editing the file. The lead writes the same document in
   Phase 3, so a direct edit is a lost update:
   write the typed JSON to .agents/logs/design-input-{slug}-architect.json
   (keys: decisions / tech_choices / agent_roles / section_updates — table rows
   only through their typed key), then:
   python3 .agents/skills/_shared/update_design.py --input .agents/logs/design-input-{slug}-architect.json
   # review the preview path in the JSON output, then:
   python3 .agents/skills/_shared/update_design.py --input .agents/logs/design-input-{slug}-architect.json --apply --require-change
   Verify "ok": true and "result": "applied". Exit 2 = invalid structure or a
   no-op; exit 3 = DESIGN.md changed concurrently — re-read it and redo the
   dry-run before applying. Report an exit 2 or 3 in your work log.

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

### Verify the Team Run (before Phase 3)

Both teammates were told to write a work log; a teammate that died mid-task, or
wrote a log missing `Issues Encountered`, is otherwise indistinguishable from
success — and Phase 3 would then synthesize from an incomplete run:

```bash
python3 .agents/skills/_shared/validate_doc.py \
  --contract work-log --dir .agents/logs/agent-teams/{team-name}/ --expect-files 2
```

Gate on `files_failed == 0`. Exit `0` both logs exist and satisfy the contract;
`1` bad args or the team directory does not exist; `2` a required section is
missing (see `results[].sections_missing`) **or** the directory does not hold
exactly 2 logs — `--expect-files 2` is what makes "no teammate wrote a log"
distinguishable from "all logs valid". Do not proceed on a non-zero exit: find
out what the missing teammate did or did not do first.

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

- MODE=existing: the Feature Brief at `.agents/docs/research/feature-{slug}-brief.md`
  (including its recorded Complexity Classification) + Codex architecture / plan /
  validation outputs.
- MODE=greenfield: read `.agents/docs/research/{slug}.md` (Researcher findings),
  `.agents/docs/libraries/{library}.md` (library docs), `.agents/docs/DESIGN.md`
  (Architect decisions).

In MODE=greenfield, validate each library doc the Researcher's work log claims
it wrote, before its constraints are built into the plan:

```bash
python3 .agents/skills/_shared/validate_doc.py \
  --contract lib-doc --file .agents/docs/libraries/{library}.md
```

Exit `0` the doc has its sections and its `> **Last Updated**:` /
`> **Version Checked**:` metadata; `1` the file is missing — the Researcher
claimed a doc it never wrote; `2` a required section or metadata line is missing
(`sections_missing` / `metadata_missing`). Validate one file per doc: running
`--dir .agents/docs/libraries/` also checks every pre-existing doc in the
repository, which is a different question from "did this feature's research
produce usable docs". A Researcher that recorded external library constraints in
prose only, with no doc at all, is a finding — say so rather than silently
proceeding.

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

Gate Phase 3 on the artifacts this phase actually consumes, before presenting
the plan. MODE=existing:

```bash
python3 .agents/skills/_shared/workspace.py --skill feature --slug {slug} --verify
```

MODE=greenfield consumes the Researcher's `research` artifact as well, and that
key is not required by default — so name it explicitly, otherwise the gate
verifies the scan and stays blind to the file Step 1 just read:

```bash
python3 .agents/skills/_shared/workspace.py --skill feature --slug {slug} \
  --verify --require research
```

Exit 0 means every required artifact (`brief`, `codebase_scan`, plus each
`--require` key) exists and is non-empty; exit 1 is bad args or an unknown
`--require` key; exit 2 means one is missing or effectively empty — read
`verify.missing` in the JSON. Do not present a plan built on a brief or a scan
that was never written.

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
use the classification recorded in the brief's `### Complexity Classification`
section — read it from `.agents/docs/research/feature-{slug}-brief.md` rather
than re-deciding it here, so the route matches what the user approved.

#### Completion Verification (MANDATORY on every route)

Every route below hands implementation to an agent that reports on its own work.
A self-report is never completion evidence (`AGENTS.md` Guardrails), so all three
routes end with the same two executable checks — the only difference between the
routes is *who wrote the code*, not how much verification it gets.

**1. Quality gates:**

```bash
bash .agents/skills/_shared/verify.sh
```

Read the JSON: `overall` is `pass` / `fail` / `no_gates`. Exit `0` means
`overall: pass`. **Exit `2` means a gate failed, or no gate could run at all** —
inspect `log_file` and `tools`; `no_gates` is a failure by default because an
implementation must not be declarable done with zero checks executed. If the
project genuinely has no configured gates, re-run with `--allow-no-gates`,
verify manually with the project's own commands, and say so in the report.
Exit `1` bad arguments, `3` the log could not be written.

**2. Diff evidence (the other half of the Guardrails):**

```bash
python3 .agents/skills/_shared/verify_delegation.py \
  --base {ref the delegated run started from} \
  --expect-files {file the plan said would change} \
  --forbid-outside {directory the plan scoped the change to} \
  --label route-{a|b|c}
```

`--expect-files` and `--forbid-outside` each take a **repo-relative path** and
are repeatable: name the files the approved plan named, and the directories it
scoped the change to. `--base` defaults to `HEAD`, which is what a Codex run
that left the tree dirty needs.

Read `deletions`, `placeholders`, `weakened_tests`, and `out_of_scope_files`.
`verdict` is **always** `needs-review`: the script collects evidence and never
accepts a delegated run on your behalf, so read the reported hunks and decide.
Exit `0` nothing actionable and no violated expectation — deletions alone land
here, reported but not actionable on their own, and exit `0` is still not an
accept, so read the diff; `1` bad args or a `--base` that does not resolve;
`2` an actionable finding (`placeholders`, `weakened_tests`) or a violated
expectation (a missing expected file, an out-of-scope file, an empty scope);
`3` git failed or the diff could not be written.

Use `.agents/skills/_shared/gather_diff.py --base {ref}` when you want the full
patch to read: `scope_empty: true` with exit `2` means the delegated run changed
nothing at all — a failed implementation, not a clean one.

#### Route A: SIMPLE (1-3 files, <50 LOC) — Codex Direct

Codex implements directly. Write the prompt body below to
`.agents/logs/codex/prompt-route-a-implement.md`, then invoke with write access:

```bash
python3 .agents/skills/_shared/codex_consult.py \
  --prompt-file .agents/logs/codex/prompt-route-a-implement.md \
  --label route-a-implement --sandbox danger-full-access
```

```
Objective: Implement this feature following the approved plan.
Context:
- Feature Brief: contents of .agents/docs/research/feature-{slug}-brief.md
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
```

Read the implementation summary from the JSON output's `response_file` — as
input to the verification, never as its result.

Then run **Completion Verification** above (both checks).

#### Route B: MODERATE (3-5 files) — Codex + Review

1. **Implement with Codex** (same prompt and `--sandbox danger-full-access` as
   Route A, with more files)
2. **Run Completion Verification** above — both checks, same exit-code reading.
   Route B changes more files than Route A, so it gets no weaker a gate: record
   `verify.sh`'s `overall` and the `verify_delegation.py` payload before moving on
3. **Hand off to `/team-execute --review-only`** for parallel review (security,
   quality, test coverage), passing the `slug` from Step 0-b

```
After Codex implementation and Completion Verification:
/team-execute --review-only   <- Parallel review from multiple perspectives
```

#### Route C: COMPLEX (5+ files) — Team Execute

```
/team-execute   <- Phase 1: parallel implementation, Phase 2: parallel review
```

Hand `/team-execute` the brief path (`.agents/docs/research/feature-{slug}-brief.md`),
the Architecture Design and Implementation Plan from Phase 2, and the `slug`
resolved in Step 0-b — `/team-execute` reuses the slug verbatim, so its research
and design artifacts resolve to the same files this skill wrote. Its work logs
land in `.agents/logs/agent-teams/team-execute-{slug}/`, deliberately separate
from this skill's `feature-{slug}/` team directory: the slug is shared, the team
directory is per-skill. Do not look for Phase 2G logs under the team-execute
directory.

When `/team-execute` returns, run **Completion Verification** above yourself.
Its own review phase is a teammate's report on teammates' work; the gates and the
diff evidence are what close the route.

### Post-Implementation

If the `.agents/STATE.md` block was not written at plan time (existing mode), write
it now per the common protocol.

---

## Output Files

Paths below are resolved once by `workspace.py` in Step 0-b (see `paths` in
its JSON) rather than hardcoded here.

| File | Author | Purpose |
|------|--------|---------|
| `.agents/docs/research/feature-{slug}-brief.md` | Lead | Feature / Project Brief — validated with `--contract feature-brief` |
| `.agents/docs/research/feature-{slug}-codebase.md` | Opus Subagent | Codebase scan |
| `.agents/docs/research/{slug}.md` (greenfield) | Researcher | External research findings |
| `.agents/docs/libraries/{lib}.md` (greenfield) | Researcher | Library documentation |
| `.agents/docs/DESIGN.md` (updated) | Lead / Architect (Codex-informed) | Architecture decisions |
| `.agents/STATE.md` (updated) | Lead | Cross-session feature context |
| `.agents/logs/agent-teams/feature-{slug}/*.md` (greenfield) | Researcher / Architect | Work logs — validated with `--contract work-log --expect-files 2` |
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
- **Quality gates**: Every route ends with Completion Verification — `verify.sh` (gate failure or no gate at all is exit `2`) plus `verify_delegation.py` diff evidence. A Codex or teammate summary is input to that check, never a substitute for it
- **Artifacts, not transcripts**: the brief, the scan, the research file and the work logs are files with contracts. If a phase cannot point at a validated file, the phase did not happen
- **Ctrl+T**: Toggle task list display
- **Shift+Up/Down**: Navigate between teammates (when using Agent Teams)
