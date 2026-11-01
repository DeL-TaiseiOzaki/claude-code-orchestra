---
name: spike
description: |
  Time-boxed technical investigation/feasibility study with deep-reasoning multi-agent collaboration (Opus subagents + Agent Teams).
  A deep-reasoning pass runs in EVERY phase for question framing, feasibility analysis, and final evaluation.
  Phase 1: Frame the investigation question & constraints (Claude user interaction + Opus question decomposition).
  Phase 2: Parallel investigation (Agent Teams: Researcher [external research] + Feasibility Analyst [structured feasibility analysis] + optional prototype).
  Phase 3: Independent Opus synthesis into go/no-go recommendation & research report.
  Produces a DECISION DOCUMENT, NOT an implementation plan. Use /feature after a GO decision.
metadata:
  short-description: Deep-reasoning time-boxed technical investigation with Agent Teams (Decision phase)
---

# Spike

**Deep-reasoning time-boxed technical investigation skill leveraging `general-purpose-opus` consults, Opus 1M context, and Agent Teams.**

## Overview

This skill handles time-boxed feasibility studies and technical investigations. It produces a **decision document** (go/no-go recommendation), NOT an implementation plan. After a GO decision, the user proceeds to `/feature` (existing or greenfield mode) for actual implementation.

```
/spike <question or hypothesis>    <- This skill (investigation & decision)
    | After GO decision
/feature                            <- Implementation planning
    | After approval
/team-execute                      <- Parallel implementation + review
```

### When to Use

| Situation | Example |
|-----------|---------|
| **Technology feasibility** | "Can we use WebSocket for real-time sync?" |
| **Library evaluation** | "Is DuckDB suitable for our analytics pipeline?" |
| **Architecture question** | "Should we use event sourcing for the order system?" |
| **Performance hypothesis** | "Can we serve 10k concurrent requests with this stack?" |
| **Migration risk** | "What would it take to migrate from REST to gRPC?" |
| **Integration question** | "Can we integrate with the Stripe Connect API for our use case?" |

### When NOT to Use

- Bug diagnosis → `/troubleshoot`
- Known feature to implement → `/feature`
- Simple library lookup → direct research (Opus subagent)
- Code review → `/team-execute --review-only`

Full skill routing: `AGENTS.md` section "Routing Policy".

### Investigation Modes

| Mode | Description | When to Use |
|------|-------------|-------------|
| **RESEARCH-ONLY** | No code written. Pure analysis from docs, examples, and structured reasoning. | Library evaluation, architecture questions, migration risk |
| **PROTOTYPE** | Small throwaway code to validate a specific technical question. Code is NOT production-quality. | Performance hypothesis, API integration feasibility, compatibility testing |

## Workflow

```
Phase 1: FRAME (Claude Lead + Opus Question Decomposition)
  Claude clarifies the spike question with the user, an Opus consult decomposes
  it into sub-questions and defines success criteria
    |
Phase 2: INVESTIGATE (Agent Teams -- Parallel)
  Researcher <-> Feasibility Analyst communicate bidirectionally
  Optional: throwaway prototype (written only under the prototype directory)
    |
Phase 3: SYNTHESIZE (Opus Evaluation + Claude Lead + User)
  A fresh Opus subagent evaluates all evidence against success criteria,
  produces go/no-go recommendation, Claude presents to user
```

---

## Phase 1: FRAME (Claude Lead + Opus Question Decomposition)

**Clarify the spike question with the user, then run an Opus consult to decompose it into a structured investigation plan.**

> A well-framed question is half the answer. Phase 1 ensures we investigate the right thing within the right constraints.

### Step 0: Resolve Workspace

Resolve this spike's deterministic workspace once. The title becomes file and directory names, so give it a short English descriptor of the question -- not the user's raw wording, which the Language Protocol keeps out of paths:

```bash
python3 .claude/skills/_shared/workspace.py --skill spike --title "{short English title}" --create
```

This prints one JSON object: `slug`, `team_name`, and `paths` (`brief`, `research`, `feasibility`, `report`, `prototype_dir`, `team_dir`). Exit 0 resolved/created; 1 bad args; 2 applies only to `--verify` (used later in Phase 3); 3 the workspace directories could not be created. Use `{slug}`, `{team_name}`, and every `paths.*` value from this JSON verbatim for the rest of this skill -- do not re-derive them by hand in a later phase.

### Step 1: Gather Spike Parameters from User

Ask the user to provide:

1. **Question / Hypothesis**: What are we trying to find out? (e.g., "Can we use SQLite for multi-tenant data isolation?")
2. **Time budget**: How long should this investigation take? (e.g., 30 min, 1 hour, 2 hours)
3. **Investigation mode**: RESEARCH-ONLY or PROTOTYPE?
4. **Success criteria**: What evidence would make this a GO? (e.g., "Library supports X, performance meets Y threshold")
5. **Context**: Why is this question important now? What decision depends on it?

### Step 2: Opus Question Decomposition (MANDATORY)

Delegate the decomposition to a `general-purpose-opus` subagent (Agent tool) with the prompt below, plus: "Read-only consult -- do not edit any file. Write your full answer to `.claude/logs/spike-{slug}-decomposition.md` and return a short summary plus that path." Read the full answer from the file; a run that wrote no file is a failed consult -- re-run it once with the gap named:

```text
Objective: Decompose this spike question into a structured investigation plan.
Context:
- Spike question: {question/hypothesis from user}
- Investigation mode: {RESEARCH-ONLY or PROTOTYPE}
- Time budget: {time budget}
- Success criteria: {user's success criteria}
- Project context: {why this matters, what decision depends on it}
Constraints:
- Break the question into 3-5 concrete sub-questions that can be independently investigated
- For each sub-question, specify what evidence would confirm or deny it
- Identify the critical path (which sub-question is most decisive)
- Suggest the investigation approach for each sub-question
- Keep the plan achievable within the time budget
Output format:
## Question Decomposition
## Sub-questions (ranked by decisiveness)
## Evidence Needed (per sub-question)
## Investigation Approach
## Critical Path (which finding would short-circuit the spike)
## Risk of Inconclusive Result
```

### Step 3: Create Spike Brief

Combine user parameters + the Opus decomposition into a Spike Brief following the template contract in `references/brief-template.md`. Write it to `{paths.brief}` (from Step 0) -- not only into this conversation -- then validate it:

```bash
python3 .claude/skills/_shared/validate_doc.py --contract spike-brief --file {paths.brief}
```

`references/brief-template.md` is the single source of truth for the required
sections; the `spike-brief` contract is pinned to that template by
`tests/test_validate_doc.py`. Exit 0 means every required section is present;
exit 2 means one is missing and the JSON `sections_missing` names it; exit 1
means the file does not exist. Fill the gap before spawning the team.

The brief carries the success criteria and sub-questions that Phase 3 scores the
evidence against, and `{paths.brief}` is in `REQUIRED_KEYS`, so the Phase 3
`--verify` gate fails without it. A brief that lives only in the Lead's context
does not survive compaction or a session break -- which is why it is a file
here, and why both teammates are pointed at the path instead of a pasted copy.

---

## Phase 2: INVESTIGATE (Agent Teams -- Parallel)

**Launch Researcher and Feasibility Analyst in parallel via Agent Teams with bidirectional communication. Feasibility Analyst MUST follow its structured analysis protocol for all technical analysis.**

> Key difference from subagents: Teammates can communicate with each other.
> Researcher's external findings change Feasibility Analyst's analysis scope, and Analyst's technical questions trigger new research.

### Team Setup

```
Create an agent team named `{team_name}` for spike investigation: {slug}

Spawn two teammates:

1. **Researcher** -- Uses WebSearch/WebFetch for external research (Opus 1M context)
   Prompt: "You are the Researcher for spike: {slug}.

   Your job: Gather external evidence to answer the spike's sub-questions.

   Spike Brief: read `{paths.brief}` (written and validated in Phase 1 Step 3).

   Tasks:
   1. Research each sub-question from the Spike Brief:
      - Find official documentation, API specs, feature matrices
      - Look for benchmarks, performance data, known limitations
      - Find real-world usage examples and case studies
   2. Identify risks and gotchas:
      - Known issues, bugs, breaking changes
      - Community sentiment (is the technology mature? well-maintained?)
      - License compatibility
   3. Find comparable implementations:
      - How have others solved similar problems?
      - What alternatives exist and how do they compare?
   4. Gather evidence for each sub-question:
      - Document evidence FOR and AGAINST each sub-question
      - Rate evidence quality (official docs > blog posts > forum answers)

   How to research:
   - Use WebSearch for comprehensive research:
     WebSearch: '{spike question} {sub-question keywords} best practices limitations benchmarks'
   - Use WebFetch for targeted documentation lookup:
     WebFetch: '{official docs URL}' with prompt to extract specific information
   - For library evaluation, check:
     - Official docs: features, constraints, API surface
     - GitHub: stars, issues, release frequency, last commit
     - Benchmarks: performance characteristics
     - Migration guides: complexity of adoption

   Save all findings to `{paths.research}` (from Phase 1 Step 0).

   Communicate with Feasibility Analyst teammate:
   - Share findings that affect technical feasibility
   - Respond to Analyst's requests for specific external data
   - Flag constraints or limitations that change the analysis

   IMPORTANT -- Work Log:
   When ALL your tasks are complete, write your work log to
   {paths.team_dir}researcher.md per the shared format:
   .claude/skills/_shared/work-log-format.md
   Role-specific sections (between Tasks Completed and Communication):
   ## Sources Consulted
   - {URL or source}: {what was found}
   ## Evidence Collected (per sub-question)
   - {sub-question}: FOR: {evidence} / AGAINST: {evidence}
   ## Key Findings
   - {finding}: {relevance to spike question}
   "

2. **Feasibility Analyst** -- Opus teammate; technical feasibility through a mandatory analysis protocol
   Prompt: "You are the Feasibility Analyst for spike: {slug}.

   Your job: Evaluate the technical feasibility of the spike question through deep analysis.
   Reason explicitly about technical trade-offs, and back every verdict with evidence.

   Spike Brief: read `{paths.brief}` (written and validated in Phase 1 Step 3).

   Tasks:
   1. Analyze technical feasibility of each sub-question
   2. Evaluate compatibility with the existing codebase and architecture
   3. Assess complexity and effort for implementation (if GO)
   4. Identify technical risks and unknowns
   5. If PROTOTYPE mode: build a minimal throwaway prototype to validate

   ## Analysis Protocol (MANDATORY)

   You MUST work through EACH of the following analysis tasks explicitly.
   Do NOT skip one -- each is a separate reasoning pass with its own
   Objective / Context / Constraints, and its answer is written under the
   stated output headings in your output file.

   ### 1. Technical Feasibility Assessment
   For each sub-question, work through:

   Objective: Assess technical feasibility of {sub-question}.
   Context:
   - Spike question: {main question}
   - Sub-question: {specific sub-question}
   - Known constraints: {from Researcher findings and project context}
   - Current architecture: {relevant architecture details}
   Constraints:
   - Evaluate against the success criteria defined in the Spike Brief
   - Consider both theoretical feasibility and practical implementation
   - Identify hard blockers vs soft challenges
   Output format:
   ## Feasibility Verdict (FEASIBLE / PARTIALLY_FEASIBLE / NOT_FEASIBLE / UNKNOWN)
   ## Evidence and Reasoning
   ## Hard Blockers (if any)
   ## Soft Challenges
   ## Effort Estimate (if feasible)

   ### 2. Architecture Compatibility Analysis
   Evaluate the fit with the existing architecture:

   Objective: Evaluate how {proposed approach} fits with the existing architecture.
   Context:
   - Proposed approach: {description}
   - Current architecture: {relevant patterns, modules, conventions}
   - Integration points: {where the new approach would connect}
   Constraints:
   - Assess alignment with existing patterns and conventions
   - Identify necessary architectural changes
   - Evaluate migration complexity
   Output format:
   ## Compatibility Assessment (COMPATIBLE / REQUIRES_CHANGES / INCOMPATIBLE)
   ## Alignment with Existing Patterns
   ## Required Architectural Changes
   ## Migration Complexity (LOW / MEDIUM / HIGH)

   ### 3. Risk and Trade-off Analysis
   Evaluate the risks:

   Objective: Identify and evaluate risks of adopting {proposed approach}.
   Context:
   - Proposed approach: {description}
   - Benefits identified: {list}
   - Constraints identified: {list}
   - Alternative approaches: {list}
   Constraints:
   - Categorize risks: technical, operational, maintenance, performance, security
   - Assess likelihood and impact for each risk
   - Compare against alternatives
   Output format:
   ## Risks (categorized)
   ## Risk Matrix (likelihood x impact)
   ## Comparison with Alternatives
   ## Mitigation Strategies

   ### 4. Prototype Validation (PROTOTYPE mode only)
   If the investigation mode is PROTOTYPE, build a minimal throwaway prototype yourself to the brief below. This is the only step in this skill that writes code, and it writes ONLY under `{paths.prototype_dir}`; every other step is read-only:

   Objective: Build a minimal prototype to validate {specific technical question}.
   Context:
   - Question to validate: {what the prototype tests}
   - Expected behavior: {what success looks like}
   - Scope: THROWAWAY code -- minimal, not production quality
   Constraints:
   - Keep it under 100 lines
   - Test ONE specific thing
   - Document what was validated and the result
   - Place prototype in {paths.prototype_dir} (from Phase 1 Step 0)
   Output format:
   ## What Was Tested
   ## Prototype Code (with inline comments)
   ## Result (VALIDATED / INVALIDATED / INCONCLUSIVE)
   ## Evidence

   ### 5. Post-Prototype Acceptance Checks (MANDATORY after building it)
   "The prototype works" is a self-report. Per the Guardrails in root
   `AGENTS.md`, run the acceptance checks -- the Lead re-runs the first one in
   Phase 3. Run both, in this order:

   python3 .claude/skills/_shared/workspace.py --skill spike --slug {slug} --verify --require prototype_dir
   python3 .claude/skills/_shared/verify_delegation.py --base HEAD --forbid-outside {paths.prototype_dir}

   The first exits 2 when `{paths.prototype_dir}` holds no non-trivial file --
   i.e. the prototype was reported and never written. Read `verify.missing` /
   `verify.empty` to see which key failed.
   The second collects the diff evidence: `deletions`, `placeholders`,
   `weakened_tests`, `out_of_scope_files`. Its `verdict` is always
   `needs-review` -- it reports evidence and never accepts on your behalf. Read
   the payload yourself: any path in `out_of_scope_files` means a throwaway
   prototype wrote outside its directory, and must be reverted before the
   evidence is used. Stub or placeholder code invalidates a VALIDATED result.

   Record the outcome of both checks in your work log under
   `## Prototype Results`, and treat the prototype as INCONCLUSIVE if either
   check failed.

   Save analysis to `{paths.feasibility}` (from Phase 1 Step 0).

   Communicate with Researcher teammate:
   - Share technical constraints that need external validation
   - Request specific data (benchmarks, API specs, compatibility info)
   - Update feasibility assessment based on Researcher's findings

   IMPORTANT -- Work Log:
   When ALL your tasks are complete, write your work log to
   {paths.team_dir}feasibility-analyst.md per the shared
   format: .claude/skills/_shared/work-log-format.md
   Keep all five core sections, `## Tasks Completed` included -- the Lead
   validates this log with `validate_doc.py --contract work-log`, which
   rejects a log that drops it.
   Role-specific sections (between Tasks Completed and Communication with
   Teammates) for this role:
   ## Sub-question Assessments
   - {sub-question}: {FEASIBLE / NOT_FEASIBLE / UNKNOWN} -- {key reasoning}
   ## Analysis Protocol Results
   - {protocol step}: {verdict and key insight}
   ## Architecture Compatibility
   - {COMPATIBLE / REQUIRES_CHANGES / INCOMPATIBLE}: {reasoning}
   ## Risks Identified
   - {risk}: {likelihood} x {impact} -- {mitigation}
   ## Prototype Results (if applicable)
   - Tested: {what}
   - Result: {VALIDATED / INVALIDATED / INCONCLUSIVE}
   - Acceptance checks: workspace --require prototype_dir: {exit code} /
     verify_delegation out_of_scope_files: {list or none}
   "

Wait for both teammates to complete their tasks.
```

### Why Bidirectional Communication Matters for Spikes

```
Example interaction flow:

Researcher: "DuckDB supports concurrent reads but only single-writer"
    -> Feasibility Analyst: "Single-writer is a hard blocker for our multi-tenant writes"
    -> Feasibility Analyst: "Research: does DuckDB support WAL mode or write queuing?"
    -> Researcher: "WAL mode available since v0.9. Also found a connection pooling pattern."
    -> Feasibility Analyst: "Feasibility analysis: WAL + write queue is feasible but adds complexity"
    -> Feasibility Analyst: "Updated assessment: PARTIALLY_FEASIBLE with medium effort"
    -> Researcher: "Found alternative: SQLite with litestream -- simpler write model"
    -> Feasibility Analyst: "Trade-off analysis: SQLite+litestream wins on simplicity, DuckDB wins on analytics"
```

Without Agent Teams, this discovery loop would require multiple sequential subagent rounds.

---

## Phase 3: SYNTHESIZE (Opus Evaluation + Claude Lead)

**Integrate Agent Teams investigation results, have a fresh Opus subagent evaluate evidence against success criteria, and produce a go/no-go recommendation.**

### Step 1: Gather Investigation Results

Confirm both teammates actually finished **before** reading anything -- "wait for
both teammates to complete" is a self-report, and a half-finished investigation
read as complete produces a confident verdict on partial evidence:

```bash
python3 .claude/skills/_shared/validate_doc.py --contract work-log \
  --dir {paths.team_dir} --expect-files 2
```

Exit 0 means both logs exist and satisfy the work-log contract. Exit 2 means
either a log is missing (`error: "expected 2 files, found N"` -- without
`--expect-files` an empty directory would pass) or a log is malformed
(`files_failed > 0`, with `sections_missing` per file). Resolve it before
continuing.

Then read outputs from Phase 2 (paths resolved in Phase 1 Step 0):
- `{paths.brief}` -- Spike Brief: the success criteria to score against
- `{paths.research}` -- Researcher findings
- `{paths.feasibility}` -- Feasibility analysis (analysis protocol results)
- `{paths.prototype_dir}` -- Prototype code and results (if PROTOTYPE mode)

### Step 2: Opus Final Evaluation (MANDATORY)

Delegate the synthesis to a **fresh** `general-purpose-opus` subagent (Agent tool) -- not a teammate, which would be grading its own investigation. Add to the prompt below: "Read-only evaluation -- do not edit any file. Write your full answer to `.claude/logs/spike-{slug}-evaluation.md` and return a short summary plus that path." Pass the Phase 2 output paths rather than pasting their contents:

```text
Objective: Synthesize spike investigation findings and produce a go/no-go recommendation.
Context:
- Spike question: {original question}
- Success criteria: {quoted verbatim from the `Success Criteria` section of {paths.brief}}
- Researcher findings: {summary of key findings}
- Feasibility assessment: {summary of the feasibility analysis per sub-question}
- Risks identified: {summary of risks}
- Prototype result (if any): {VALIDATED / INVALIDATED / INCONCLUSIVE}
Constraints:
- Evaluate each success criterion against the collected evidence
- Be explicit about confidence level (HIGH / MEDIUM / LOW)
- If GO, specify key constraints and risks to carry forward
- If NO-GO, explain the decisive blocker and suggest alternatives
- If INCONCLUSIVE, specify what additional investigation is needed
Output format (headings chosen to drop straight into `references/report-template.md`):
## Success Criteria Evaluation (per criterion, quoting the criterion verbatim)
## Verdict: GO / NO-GO / INCONCLUSIVE
## Confidence Level: HIGH / MEDIUM / LOW
## Decisive Factor
## If GO: Constraints and Risks to Carry Forward
## If GO: Recommended Next Skill (/feature — existing or greenfield mode)
## If NO-GO: Decisive Blocker and Alternatives
## If INCONCLUSIVE: What Additional Investigation Is Needed
```

### Step 3: Save Research Report

Save the complete spike report to `{paths.report}` (from Phase 1 Step 0) following the template contract in `references/report-template.md`. Then validate it and gate Phase 3 before presenting to the user:

```bash
python3 .claude/skills/_shared/validate_doc.py --contract spike-report --file {paths.report}
python3 .claude/skills/_shared/workspace.py --skill spike --slug {slug} --verify
# PROTOTYPE mode only -- make the prototype itself a required artifact:
python3 .claude/skills/_shared/workspace.py --skill spike --slug {slug} --verify --require prototype_dir
```

`references/report-template.md` is the single source of truth for the report's
required sections; the `spike-report` contract is pinned to that template by
`tests/test_validate_doc.py`. Do not work from a section list retyped here.
Exit 0 means every required section is present; exit 2 means one is missing and
the JSON `sections_missing` names it -- the usual casualty is the section that
ties the verdict back to the Phase 1 success criteria, and a report without it
has an unsupported verdict.

The `--verify` call confirms `brief`, `research`, `feasibility`, and `report`
all exist and are non-trivial; exit 2 means one is missing or empty (read
`verify.missing` / `verify.empty`). In PROTOTYPE mode add
`--require prototype_dir`: `prototype_dir` is not required by default, so
without it a PROTOTYPE spike passes this gate with no prototype on disk. An
empty directory does not satisfy it. Resolve any gap before Step 4.

### Step 4: Present to User

Present the spike result to the user:

```markdown
## Spike Result: {slug}

### Verdict: {GO / NO-GO / INCONCLUSIVE}
**Confidence**: {HIGH / MEDIUM / LOW}

### Question
{The original spike question}

### Evidence Summary
{3-5 bullet points of key findings from Researcher}

### Feasibility Assessment
{3-5 bullet points of key analysis from Feasibility Analyst}

### Risks
{Top 2-3 risks with likelihood and impact}

### Prototype Result (if applicable)
{What was tested and what the result was}

### Success Criteria Check
| Criterion | Met? | Evidence |
|-----------|------|----------|
| {criterion} | {YES/NO/PARTIAL} | {brief evidence} |

### Opus Evaluation
{the evaluator's synthesized reasoning for the verdict}
{Confidence level and decisive factor}

### Next Steps
**If GO:**
1. Proceed with `/feature` (existing or greenfield mode) for implementation
2. Key constraints to carry forward: {list}
3. Risks to monitor during implementation: {list}

**If NO-GO:**
1. Decisive blocker: {description}
2. Alternatives to consider: {list}

**If INCONCLUSIVE:**
1. Missing evidence: {what we still need}
2. Consider a follow-up spike with narrower scope

---
Full report saved to: `{paths.report}`

Shall we proceed with the recommended next step?
```

---

## Output Files

Paths resolved once in Phase 1 Step 0 (`.claude/skills/_shared/workspace.py --skill spike`):

| File | Author | Purpose |
|------|--------|---------|
| `{paths.brief}` | Lead | Spike Brief: success criteria, sub-questions, time budget (Phase 1) |
| `{paths.research}` | Researcher | External research findings |
| `{paths.feasibility}` | Feasibility Analyst | Technical feasibility analysis |
| `{paths.report}` | Lead | Final spike report (decision document) |
| `{paths.prototype_dir}` | Feasibility Analyst | Prototype code (PROTOTYPE mode only) |

---

## Tips

- **Deep-reasoning first**: Every phase has an explicit reasoning pass. This is intentional -- structured reasoning about feasibility and trade-offs complements broad research
- **Time budget discipline**: Respect the time budget. If investigation is taking too long, the Phase 3 evaluator can work with partial evidence and mark the verdict as INCONCLUSIVE
- **Phase 1 is critical**: A well-decomposed question makes Phase 2 much more efficient. Invest time in framing the right sub-questions
- **Phase 2**: Agent Teams bidirectional communication allows Researcher and Feasibility Analyst to converge on evidence-based assessment
- **Phase 3**: A fresh Opus subagent synthesizes all findings into a decision. After a GO decision, proceed to `/feature` -- do NOT start implementation within the spike
- **PROTOTYPE mode**: Prototype code is throwaway. It lives in `{paths.prototype_dir}` and is NOT production code. Its only purpose is to generate evidence for the decision -- and because it is the skill's only code-writing step, the acceptance checks after it (`--require prototype_dir` plus `verify_delegation.py`) are not optional
- **Short-circuit**: If Phase 2 discovers a hard blocker early, short-circuit to Phase 3 immediately. No need to complete all sub-questions if the answer is already clear
- **Inconclusive is OK**: Not every spike produces a clear answer. An INCONCLUSIVE result with documented unknowns is more valuable than a false GO
- **Reuse research**: Spike reports in `.claude/docs/research/` persist across sessions. Reference prior spikes before starting new ones on similar topics
- **Ctrl+T**: Toggle task list display
- **Shift+Up/Down**: Navigate between teammates (when using Agent Teams)
