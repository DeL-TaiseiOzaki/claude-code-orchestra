---
name: spike
description: |
  Time-boxed technical investigation/feasibility study with Codex-first multi-agent collaboration (Codex + Opus 4.6 + Agent Teams).
  Codex CLI is consulted in EVERY phase for question framing, feasibility analysis, and final evaluation.
  Phase 1: Frame the investigation question & constraints (Claude user interaction + Codex question decomposition).
  Phase 2: Parallel investigation (Agent Teams: Researcher [Opus external research] + Feasibility Analyst [Codex deep analysis] + optional prototype).
  Phase 3: Codex synthesis into go/no-go recommendation & research report.
  Produces a DECISION DOCUMENT, NOT an implementation plan. Use /add-feature or /startproject after a GO decision.
metadata:
  short-description: Codex-first time-boxed technical investigation with Agent Teams (Decision phase)
---

# Spike

**Codex-first time-boxed technical investigation skill leveraging Codex deep reasoning, Opus 1M context, and Agent Teams.**

## Overview

This skill handles time-boxed feasibility studies and technical investigations. It produces a **decision document** (go/no-go recommendation), NOT an implementation plan. After a GO decision, the user proceeds to `/add-feature` or `/startproject` for actual implementation.

```
/spike <question or hypothesis>    <- This skill (investigation & decision)
    | After GO decision
/add-feature or /startproject      <- Implementation planning
    | After approval
/team-implement                    <- Parallel implementation
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

| Situation | Use Instead |
|-----------|-------------|
| Bug diagnosis | `/troubleshoot` |
| Known feature to implement | `/add-feature` or `/startproject` |
| Simple library lookup | Direct research (Opus subagent) |
| Code review | `/team-review` |

### Investigation Modes

| Mode | Description | When to Use |
|------|-------------|-------------|
| **RESEARCH-ONLY** | No code written. Pure analysis from docs, examples, and Codex reasoning. | Library evaluation, architecture questions, migration risk |
| **PROTOTYPE** | Small throwaway code to validate a specific technical question. Code is NOT production-quality. | Performance hypothesis, API integration feasibility, compatibility testing |

## Workflow

```
Phase 1: FRAME (Claude Lead + Codex Question Decomposition)
  Claude clarifies the spike question with the user, Codex decomposes into
  sub-questions and defines success criteria
    |
Phase 2: INVESTIGATE (Agent Teams -- Parallel, Codex-driven)
  Researcher (Opus) <-> Feasibility Analyst (Codex) communicate bidirectionally
  Optional: Codex prototype (workspace-write) for hands-on validation
    |
Phase 3: SYNTHESIZE (Codex Evaluation + Claude Lead + User)
  Codex evaluates all evidence against success criteria,
  produces go/no-go recommendation, Claude presents to user
```

---

## Phase 1: FRAME (Claude Lead + Codex Question Decomposition)

**Clarify the spike question with the user, then consult Codex to decompose it into a structured investigation plan.**

> A well-framed question is half the answer. Phase 1 ensures we investigate the right thing within the right constraints.

### Step 1: Gather Spike Parameters from User

Ask the user to provide:

1. **Question / Hypothesis**: What are we trying to find out? (e.g., "Can we use SQLite for multi-tenant data isolation?")
2. **Time budget**: How long should this investigation take? (e.g., 30 min, 1 hour, 2 hours)
3. **Investigation mode**: RESEARCH-ONLY or PROTOTYPE?
4. **Success criteria**: What evidence would make this a GO? (e.g., "Library supports X, performance meets Y threshold")
5. **Context**: Why is this question important now? What decision depends on it?

### Step 2: Codex Question Decomposition (MANDATORY)

Consult Codex to decompose the spike question into a structured investigation plan:

```bash
codex exec --model gpt-5.4 --sandbox read-only --full-auto "
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
" 2>/dev/null
```

### Step 3: Create Spike Brief

Combine user parameters + Codex decomposition into a "Spike Brief":

```markdown
## Spike Brief: {topic}

### Question
{The core question or hypothesis in one sentence}

### Parameters
- Time budget: {duration}
- Investigation mode: {RESEARCH-ONLY / PROTOTYPE}
- Started: {timestamp}
- Deadline: {timestamp}

### Success Criteria
- GO if: {conditions that make this a GO}
- NO-GO if: {conditions that make this a NO-GO}
- INCONCLUSIVE if: {what would leave us uncertain}

### Sub-questions (from Codex decomposition)
1. {Sub-question A}: Evidence needed: {description}
2. {Sub-question B}: Evidence needed: {description}
3. {Sub-question C}: Evidence needed: {description}

### Critical Path
{Which sub-question is most decisive -- investigate this first}

### Investigation Plan
- Researcher (Opus): {what to research externally}
- Feasibility Analyst (Codex): {what to analyze technically}
- Prototype (if applicable): {what to build and test}
```

This brief is passed to Phase 2 teammates as shared context.

---

## Phase 2: INVESTIGATE (Agent Teams -- Parallel)

**Launch Researcher and Feasibility Analyst in parallel via Agent Teams with bidirectional communication. Feasibility Analyst MUST consult Codex for all technical analysis.**

> Key difference from subagents: Teammates can communicate with each other.
> Researcher's external findings change Feasibility Analyst's analysis scope, and Analyst's technical questions trigger new research.

### Team Setup

```
Create an agent team for spike investigation: {topic}

Spawn two teammates:

1. **Researcher** -- Uses WebSearch/WebFetch for external research (Opus 1M context)
   Prompt: "You are the Researcher for spike: {topic}.

   Your job: Gather external evidence to answer the spike's sub-questions.

   Spike Brief:
   {spike brief from Phase 1}

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
     WebSearch: '{topic} {sub-question keywords} best practices limitations benchmarks'
   - Use WebFetch for targeted documentation lookup:
     WebFetch: '{official docs URL}' with prompt to extract specific information
   - For library evaluation, check:
     - Official docs: features, constraints, API surface
     - GitHub: stars, issues, release frequency, last commit
     - Benchmarks: performance characteristics
     - Migration guides: complexity of adoption

   Save all findings to .claude/docs/research/spike-{topic}-research.md

   Communicate with Feasibility Analyst teammate:
   - Share findings that affect technical feasibility
   - Respond to Analyst's requests for specific external data
   - Flag constraints or limitations that change the analysis

   IMPORTANT -- Work Log:
   When ALL your tasks are complete, write a work log file to:
     .claude/logs/agent-teams/{team-name}/researcher.md

   Use this format:
   # Work Log: Researcher
   ## Summary
   (1-2 sentence summary of what you researched)
   ## Tasks Completed
   - [x] {task}: {brief description of findings}
   ## Sources Consulted
   - {URL or source}: {what was found}
   ## Evidence Collected (per sub-question)
   - {sub-question}: FOR: {evidence} / AGAINST: {evidence}
   ## Key Findings
   - {finding}: {relevance to spike question}
   ## Communication with Teammates
   - -> {recipient}: {summary of message sent}
   - <- {sender}: {summary of message received}
   ## Issues Encountered
   - {issue}: {how it was resolved}
   (If none, write 'None')
   "

2. **Feasibility Analyst** -- Uses Codex CLI as PRIMARY analysis engine for technical feasibility
   Prompt: "You are the Feasibility Analyst for spike: {topic}.

   Your job: Evaluate the technical feasibility of the spike question through deep analysis.
   Codex CLI is your PRIMARY tool for reasoning about technical trade-offs and feasibility.

   Spike Brief:
   {spike brief from Phase 1}

   Tasks:
   1. Analyze technical feasibility of each sub-question
   2. Evaluate compatibility with the existing codebase and architecture
   3. Assess complexity and effort for implementation (if GO)
   4. Identify technical risks and unknowns
   5. If PROTOTYPE mode: build a minimal throwaway prototype to validate

   ## Codex Analysis Protocol (MANDATORY)

   You MUST consult Codex for EACH of the following analysis tasks.
   Do NOT skip Codex consultation -- it is the primary reasoning engine for this role.

   ### 1. Technical Feasibility Assessment
   For each sub-question, consult Codex:
   codex exec --model gpt-5.4 --sandbox read-only --full-auto '
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
   ' 2>/dev/null

   ### 2. Architecture Compatibility Analysis
   Consult Codex to evaluate fit with existing architecture:
   codex exec --model gpt-5.4 --sandbox read-only --full-auto '
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
   ' 2>/dev/null

   ### 3. Risk and Trade-off Analysis
   Consult Codex to evaluate risks:
   codex exec --model gpt-5.4 --sandbox read-only --full-auto '
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
   ' 2>/dev/null

   ### 4. Prototype Validation (PROTOTYPE mode only)
   If the investigation mode is PROTOTYPE, build a minimal throwaway prototype:
   codex exec --model gpt-5.4 --sandbox workspace-write --full-auto '
   Objective: Build a minimal prototype to validate {specific technical question}.
   Context:
   - Question to validate: {what the prototype tests}
   - Expected behavior: {what success looks like}
   - Scope: THROWAWAY code -- minimal, not production quality
   Constraints:
   - Keep it under 100 lines
   - Test ONE specific thing
   - Document what was validated and the result
   - Place prototype in .claude/spikes/{topic}/ directory
   Output format:
   ## What Was Tested
   ## Prototype Code (with inline comments)
   ## Result (VALIDATED / INVALIDATED / INCONCLUSIVE)
   ## Evidence
   ' 2>/dev/null

   Save analysis to .claude/docs/research/spike-{topic}-feasibility.md

   Communicate with Researcher teammate:
   - Share technical constraints that need external validation
   - Request specific data (benchmarks, API specs, compatibility info)
   - Update feasibility assessment based on Researcher's findings

   IMPORTANT -- Work Log:
   When ALL your tasks are complete, write a work log file to:
     .claude/logs/agent-teams/{team-name}/feasibility-analyst.md

   Use this format:
   # Work Log: Feasibility Analyst
   ## Summary
   (1-2 sentence summary of feasibility assessment)
   ## Sub-question Assessments
   - {sub-question}: {FEASIBLE / NOT_FEASIBLE / UNKNOWN} -- {key reasoning}
   ## Codex Consultations
   - {question asked to Codex}: {key insight from response}
   ## Architecture Compatibility
   - {COMPATIBLE / REQUIRES_CHANGES / INCOMPATIBLE}: {reasoning}
   ## Risks Identified
   - {risk}: {likelihood} x {impact} -- {mitigation}
   ## Prototype Results (if applicable)
   - Tested: {what}
   - Result: {VALIDATED / INVALIDATED / INCONCLUSIVE}
   ## Communication with Teammates
   - -> {recipient}: {summary of message sent}
   - <- {sender}: {summary of message received}
   ## Issues Encountered
   - {issue}: {how it was resolved}
   (If none, write 'None')
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
    -> Feasibility Analyst: "Codex analysis: WAL + write queue is feasible but adds complexity"
    -> Feasibility Analyst: "Updated assessment: PARTIALLY_FEASIBLE with medium effort"
    -> Researcher: "Found alternative: SQLite with litestream -- simpler write model"
    -> Feasibility Analyst: "Codex comparison: SQLite+litestream wins on simplicity, DuckDB wins on analytics"
```

Without Agent Teams, this discovery loop would require multiple sequential subagent rounds.

---

## Phase 3: SYNTHESIZE (Codex Evaluation + Claude Lead)

**Integrate Agent Teams investigation results, have Codex evaluate evidence against success criteria, and produce a go/no-go recommendation.**

### Step 1: Gather Investigation Results

Read outputs from Phase 2:
- `.claude/docs/research/spike-{topic}-research.md` -- Researcher findings
- `.claude/docs/research/spike-{topic}-feasibility.md` -- Feasibility analysis (Codex-driven)
- `.claude/spikes/{topic}/` -- Prototype code and results (if PROTOTYPE mode)

### Step 2: Codex Final Evaluation (MANDATORY)

Consult Codex to synthesize all findings into a go/no-go recommendation:

```bash
codex exec --model gpt-5.4 --sandbox read-only --full-auto "
Objective: Synthesize spike investigation findings and produce a go/no-go recommendation.
Context:
- Spike question: {original question}
- Success criteria: {from Spike Brief}
- Researcher findings: {summary of key findings}
- Feasibility assessment: {summary of Codex feasibility analysis per sub-question}
- Risks identified: {summary of risks}
- Prototype result (if any): {VALIDATED / INVALIDATED / INCONCLUSIVE}
Constraints:
- Evaluate each success criterion against the collected evidence
- Be explicit about confidence level (HIGH / MEDIUM / LOW)
- If GO, specify key constraints and risks to carry forward
- If NO-GO, explain the decisive blocker and suggest alternatives
- If INCONCLUSIVE, specify what additional investigation is needed
Output format:
## Evidence Summary (per success criterion)
## Verdict: GO / NO-GO / INCONCLUSIVE
## Confidence Level: HIGH / MEDIUM / LOW
## Decisive Factor
## If GO: Constraints and Risks to Carry Forward
## If GO: Recommended Next Skill (/add-feature or /startproject)
## If NO-GO: Decisive Blocker and Alternatives
## If INCONCLUSIVE: What Additional Investigation Is Needed
" 2>/dev/null
```

### Step 3: Save Research Report

Save the complete spike report to `.claude/docs/research/spike-{topic}.md`:

```markdown
# Spike Report: {topic}

## Question
{The original spike question}

## Verdict: {GO / NO-GO / INCONCLUSIVE}
**Confidence**: {HIGH / MEDIUM / LOW}
**Decisive factor**: {one-sentence summary of why}

## Investigation Parameters
- Time budget: {duration}
- Mode: {RESEARCH-ONLY / PROTOTYPE}
- Date: {date}

## Success Criteria Evaluation
| Criterion | Evidence | Met? |
|-----------|----------|------|
| {criterion 1} | {evidence summary} | {YES / NO / PARTIAL} |
| {criterion 2} | {evidence summary} | {YES / NO / PARTIAL} |

## Sub-question Findings
### {Sub-question 1}
- Finding: {description}
- Evidence: {sources and data}
- Assessment: {FEASIBLE / NOT_FEASIBLE / UNKNOWN}

### {Sub-question 2}
- Finding: {description}
- Evidence: {sources and data}
- Assessment: {FEASIBLE / NOT_FEASIBLE / UNKNOWN}

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| {risk 1} | {H/M/L} | {H/M/L} | {strategy} |

## Prototype Results (if applicable)
- Tested: {what was tested}
- Result: {VALIDATED / INVALIDATED / INCONCLUSIVE}
- Evidence: {observations}

## Architecture Compatibility
- Assessment: {COMPATIBLE / REQUIRES_CHANGES / INCOMPATIBLE}
- Required changes: {list, if any}

## Alternatives Considered
| Alternative | Pros | Cons | Verdict |
|-------------|------|------|---------|
| {alt 1} | {pros} | {cons} | {recommendation} |

## Recommendation
{GO / NO-GO / INCONCLUSIVE with detailed reasoning}

### If GO
- Next step: {/add-feature or /startproject}
- Key constraints to carry forward: {list}
- Risks to monitor: {list}

### If NO-GO
- Decisive blocker: {description}
- Suggested alternatives: {list}

### If INCONCLUSIVE
- Missing evidence: {what we still need}
- Suggested follow-up: {description}
```

### Step 4: Present to User

Present the spike result to the user:

```markdown
## Spike Result: {topic}

### Verdict: {GO / NO-GO / INCONCLUSIVE}
**Confidence**: {HIGH / MEDIUM / LOW}

### Question
{The original spike question}

### Evidence Summary
{3-5 bullet points of key findings from Researcher}

### Feasibility Assessment (Codex)
{3-5 bullet points of key analysis from Feasibility Analyst}

### Risks
{Top 2-3 risks with likelihood and impact}

### Prototype Result (if applicable)
{What was tested and what the result was}

### Success Criteria Check
| Criterion | Met? | Evidence |
|-----------|------|----------|
| {criterion} | {YES/NO/PARTIAL} | {brief evidence} |

### Codex Evaluation
{Codex's synthesized reasoning for the verdict}
{Confidence level and decisive factor}

### Next Steps
**If GO:**
1. Proceed with `/add-feature` or `/startproject` for implementation
2. Key constraints to carry forward: {list}
3. Risks to monitor during implementation: {list}

**If NO-GO:**
1. Decisive blocker: {description}
2. Alternatives to consider: {list}

**If INCONCLUSIVE:**
1. Missing evidence: {what we still need}
2. Consider a follow-up spike with narrower scope

---
Full report saved to: `.claude/docs/research/spike-{topic}.md`

Shall we proceed with the recommended next step?
```

---

## Output Files

| File | Author | Purpose |
|------|--------|---------|
| `.claude/docs/research/spike-{topic}-research.md` | Researcher | External research findings |
| `.claude/docs/research/spike-{topic}-feasibility.md` | Feasibility Analyst | Technical feasibility analysis (Codex-driven) |
| `.claude/docs/research/spike-{topic}.md` | Lead | Final spike report (decision document) |
| `.claude/spikes/{topic}/` | Feasibility Analyst | Prototype code (PROTOTYPE mode only) |

---

## Tips

- **Codex-first**: Every phase consults Codex. This is intentional -- Codex excels at structured reasoning about feasibility and trade-offs that complements Opus's broad research capabilities
- **Time budget discipline**: Respect the time budget. If investigation is taking too long, Codex can evaluate with partial evidence and mark the verdict as INCONCLUSIVE
- **Phase 1 is critical**: A well-decomposed question makes Phase 2 much more efficient. Invest time in framing the right sub-questions with Codex
- **Phase 2**: Agent Teams bidirectional communication allows Researcher (Opus) and Feasibility Analyst (Codex-driven) to converge on evidence-based assessment
- **Phase 3**: Codex synthesizes all findings into a decision. After a GO decision, proceed to `/add-feature` or `/startproject` -- do NOT start implementation within the spike
- **PROTOTYPE mode**: Prototype code is throwaway. It lives in `.claude/spikes/` and is NOT production code. Its only purpose is to generate evidence for the decision
- **Short-circuit**: If Phase 2 discovers a hard blocker early, short-circuit to Phase 3 immediately. No need to complete all sub-questions if the answer is already clear
- **Inconclusive is OK**: Not every spike produces a clear answer. An INCONCLUSIVE result with documented unknowns is more valuable than a false GO
- **Reuse research**: Spike reports in `.claude/docs/research/` persist across sessions. Reference prior spikes before starting new ones on similar topics
- **Ctrl+T**: Toggle task list display
- **Shift+Up/Down**: Navigate between teammates (when using Agent Teams)
