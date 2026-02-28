---
name: startproject
description: |
  Start a new project/feature with multi-agent collaboration (Opus 4.6 + Agent Teams).
  Phase 1: Codebase understanding (Gemini 1M context + Claude user interaction).
  Phase 2: Parallel research & design (Agent Teams: Researcher + Architect).
  Phase 3: Plan synthesis & user approval.
  Implementation is handled separately by /team-implement.
metadata:
  short-description: Project kickoff with Agent Teams (Plan phase)
---

# Start Project

**Project kickoff skill leveraging Gemini's 1M context and Agent Teams.**

## Overview

This skill handles the planning phases (Phase 1-3). Implementation is done via `/team-implement`, and review via `/team-review`.

```
/startproject <feature>     ← This skill (planning)
    ↓ After approval
/team-implement             ← Parallel implementation
    ↓ After completion
/team-review                ← Parallel review
```

## Workflow

```
Phase 1: UNDERSTAND (Gemini 1M context + Claude Lead)
  Gemini analyzes the codebase (1M context), Claude interacts with the user
    ↓
Phase 2: RESEARCH & DESIGN (Agent Teams — Parallel)
  Researcher (Gemini) ←→ Architect (Codex) communicate bidirectionally for research and design
    ↓
Phase 3: PLAN & APPROVE (Claude Lead + User)
  Integrate research and design, create plan and get user approval
```

---

## Phase 1: UNDERSTAND (Gemini + Claude Lead)

**Analyze the codebase with Gemini's 1M context while Claude interacts with the user.**

> Claude Code's context is 200K. Large-scale codebase analysis is delegated to Gemini (1M context).

### Step 1: Analyze Codebase with Gemini

Use Gemini CLI to analyze the entire codebase:

```bash
# Via gemini-explore subagent (recommended)
Task tool:
  subagent_type: "gemini-explore"
  prompt: |
    Analyze this codebase comprehensively:
    - Directory structure and organization
    - Key modules and their responsibilities
    - Existing patterns and conventions
    - Dependencies and tech stack
    - Test structure

    gemini -p "Analyze this codebase: directory structure, key modules, architecture patterns, dependencies, conventions, and test structure" 2>/dev/null

    Save analysis to .claude/docs/research/{feature}-codebase.md
    Return concise summary (5-7 key findings).
```

To supplement Gemini's analysis, Claude can use Glob/Grep/Read to inspect specific files.

### Step 2: Requirements Gathering

Ask the user questions to clarify requirements:

1. **Purpose**: What do you want to achieve?
2. **Scope**: What to include / exclude?
3. **Technical requirements**: Specific libraries, constraints?
4. **Success criteria**: How do you determine completion?
5. **Final design**: What form should it take?

### Step 3: Create Project Brief

Combine codebase understanding + requirements into a "Project Brief":

```markdown
## Project Brief: {feature}

### Current State
- Architecture: {existing architecture summary}
- Relevant code: {key files and modules}
- Patterns: {existing patterns to follow}

### Goal
{User's desired outcome in 1-2 sentences}

### Scope
- Include: {list}
- Exclude: {list}

### Constraints
- {technical constraints}
- {library requirements}

### Success Criteria
- {measurable criteria}
```

This brief is passed to Phase 2 teammates as shared context.

---

## Phase 2: RESEARCH & DESIGN (Agent Teams — Parallel)

**Launch Researcher and Architect in parallel via Agent Teams with bidirectional communication.**

> Key difference from subagents: Teammates can communicate with each other.
> Researcher's findings change Architect's design, and Architect's requests trigger new research.

### Team Setup

```
Create an agent team for project planning: {feature}

Spawn two teammates:

1. **Researcher** — Uses Gemini CLI (1M context + Google Search grounding) for external research
   Prompt: "You are the Researcher for project: {feature}.

   Your job: Research external information needed for this project.

   Project Brief:
   {project brief from Phase 1}

   Tasks:
   1. Research libraries and tools: usage patterns, constraints, best practices
   2. Find latest documentation and API specifications
   3. Identify common pitfalls and anti-patterns
   4. Look for similar implementations and reference architectures

   How to research:
   - Use Gemini CLI for comprehensive research (1M context + Google Search grounding):
     gemini -p 'Research: {topic}. Find latest best practices, constraints, and recommendations' 2>/dev/null
   - Use WebSearch/WebFetch for targeted lookups when needed

   Save all findings to .claude/docs/research/{feature}.md
   Save library docs to .claude/docs/libraries/{library}.md

   Communicate with Architect teammate:
   - Share findings that affect design decisions
   - Respond to Architect's research requests
   - Flag constraints that limit implementation options

   IMPORTANT — Work Log:
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
   ## Key Findings
   - {finding}: {relevance to project}
   ## Communication with Teammates
   - → {recipient}: {summary of message sent}
   - ← {sender}: {summary of message received}
   ## Issues Encountered
   - {issue}: {how it was resolved}
   (If none, write 'None')
   "

2. **Architect** — Uses Codex CLI for design and planning
   Prompt: "You are the Architect for project: {feature}.

   Your job: Use Codex CLI to design the architecture and create implementation plan.

   Project Brief:
   {project brief from Phase 1}

   Tasks:
   1. Design architecture (modules, interfaces, data flow)
   2. Select patterns (considering existing codebase conventions)
   3. Create step-by-step implementation plan with dependencies
   4. Identify risks and mitigation strategies

   How to consult Codex:
   codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "{question}" 2>/dev/null

   Update .claude/docs/DESIGN.md with architecture decisions.

   Communicate with Researcher teammate:
   - Request specific library/tool research
   - Share design constraints that need validation
   - Adjust design based on Researcher's findings

   IMPORTANT — Work Log:
   When ALL your tasks are complete, write a work log file to:
     .claude/logs/agent-teams/{team-name}/architect.md

   Use this format:
   # Work Log: Architect
   ## Summary
   (1-2 sentence summary of what you designed)
   ## Tasks Completed
   - [x] {task}: {brief description of what was done}
   ## Design Decisions
   - {decision}: {rationale}
   ## Codex Consultations
   - {question asked to Codex}: {key insight from response}
   ## Communication with Teammates
   - → {recipient}: {summary of message sent}
   - ← {sender}: {summary of message received}
   ## Issues Encountered
   - {issue}: {how it was resolved}
   (If none, write 'None')
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
1. Gemini subagent finishes → returns summary
2. Claude reads summary → creates new Codex subagent prompt
3. Codex subagent finishes → returns summary
4. If Codex needs more info → another Gemini subagent round

Agent Teams collapses this into a single parallel session with real-time interaction.

---

## Phase 3: PLAN & APPROVE (Claude Lead)

**Integrate Agent Teams results, create an implementation plan, and request user approval.**

### Step 1: Synthesize Results

Read outputs from Phase 2:
- `.claude/docs/research/{feature}.md` — Researcher findings
- `.claude/docs/libraries/{library}.md` — Library documentation
- `.claude/docs/DESIGN.md` — Architecture decisions

### Step 2: Create Implementation Plan

Create task list using TodoWrite:

```python
{
    "content": "Implement {specific task}",
    "activeForm": "Implementing {specific task}",
    "status": "pending"
}
```

Task breakdown should follow `references/task-patterns.md`.

### Step 3: Update CLAUDE.md

Add project context to CLAUDE.md for cross-session persistence:

```markdown
---

## Current Project: {feature}

### Context
- Goal: {1-2 sentences}
- Key files: {list}
- Dependencies: {list}

### Architecture
- {Key architecture decisions from Architect}

### Library Constraints
- {Key constraints from Researcher}

### Decisions
- {Decision 1}: {rationale}
- {Decision 2}: {rationale}
```

### Step 4: Present to User

Present the plan to the user:

```markdown
## Project Plan: {feature}

### Codebase Analysis
{Key findings from Phase 1 — 3-5 bullet points}

### Research Findings (Researcher)
{Key findings — 3-5 bullet points}
{Library constraints and recommendations}

### Design Direction (Architect)
{Architecture overview}
{Key design decisions with rationale}

### Task List ({N} items)
{Task list with dependencies}

### Risks and Considerations
{From Architect's analysis}

### Next Steps
1. Shall we proceed with this plan?
2. After approval, you can start parallel implementation with `/team-implement`
3. After implementation, run parallel review with `/team-review`

---
Shall we proceed with this plan?
```

---

## Output Files

| File | Author | Purpose |
|------|--------|---------|
| `.claude/docs/research/{feature}.md` | Researcher | External research findings |
| `.claude/docs/libraries/{lib}.md` | Researcher | Library documentation |
| `.claude/docs/DESIGN.md` | Architect | Architecture decisions |
| `CLAUDE.md` (updated) | Lead | Cross-session project context |
| Task list (internal) | Lead | Implementation tracking |

---

## Tips

- **Phase 1**: Gemini (1M context) analyzes the codebase while Claude interacts with the user
- **Phase 2**: Agent Teams bidirectional communication allows Researcher (Gemini) and Architect (Codex) to influence each other
- **Phase 3**: After plan approval, proceed to parallel implementation with `/team-implement`
- **Ctrl+T**: Toggle task list display
- **Shift+Up/Down**: Navigate between teammates (when using Agent Teams)
