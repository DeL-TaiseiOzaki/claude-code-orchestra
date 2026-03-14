# Claude Code Orchestra — Comprehensive Template Features Analysis

> Generated: 2026-03-14
> Repository: https://github.com/DeL-TaiseiOzaki/claude-code-orchestra
> License: MIT (Copyright 2026 Taisei Ozaki)

---

## 1. Core Architecture

### 1.1 Orchestrator Pattern (CLAUDE.md)

The central design principle: **Claude Code acts as an orchestrator, not an implementer.** The 200K context window is preserved by delegating heavy work to specialized agents.

**Mission:**
- Organize, prioritize, and build consensus on user requirements
- Delegate to appropriate agents (Codex / Gemini / Subagents)
- Integrate results, make decisions, present next actions

**Non-Goals (Claude does NOT do directly):**
- Large-scale implementation (>10 LOC)
- Large-scale investigation (cross-codebase analysis, web research)
- Sequential reading of long logs / many files

**Delegation Triggers (any one = delegate):**
1. Output exceeds ~10 lines
2. Editing 2+ files
3. Reading 3+ files
4. Design decisions or trade-off comparisons needed
5. External/latest information needed

**Execution Patterns:**
- **Foreground**: Wait for result when next step depends on it (3-5 bullet summary)
- **Background**: Continue user interaction while processing
- **Save-to-file**: Results >20 lines saved to `.claude/docs/`, only summary returned

**Output Contract:**
- Conclusion first, rationale second, next action last
- Uncertainty explicitly marked (speculation / unverified / needs confirmation)
- Always show commands, changed files, test results

**Quality Gates (before final response):**
- Change intent matches user request
- Diff self-reviewed
- At least one test/check executed
- Failures include cause and impact analysis

### 1.2 Settings Configuration (.claude/settings.json)

**Key settings:**
- `language`: Japanese (user-facing)
- `effortLevel`: high
- `alwaysThinkingEnabled`: true
- `fastMode`: false

**Environment variables:**
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`: 1 (enables Agent Teams)
- `CLAUDE_CODE_SUBAGENT_MODEL`: claude-opus-4-6

**Permissions:**
- Comprehensive allow-list for common CLI tools (git, uv, ruff, ty, pytest, node, npm, docker, codex, gemini, etc.)
- Explicit deny-list for sensitive files (.env, .pem, .key, credentials, secrets, ~/.ssh, ~/.aws, ~/.config/gcloud)
- Destructive commands denied (rm -rf /, rm -rf ~)

### 1.3 Routing Policy

| Task Type | Route |
|-----------|-------|
| Design, planning, complex implementation | `general-purpose` subagent → Codex CLI |
| External research, large-scale analysis, multimodal | `gemini-explore` subagent → Gemini CLI |
| Error analysis | `codex-debugger` subagent |
| Minor fixes (single file, small change) | Claude directly |

---

## 2. Agent System (.claude/agents/)

### 2.1 general-purpose (Opus)

**Role**: Execution arm of the main orchestrator.

**Responsibilities:**
1. **Code implementation** — features, fixes, refactoring, tests, file operations
2. **Codex delegation** — planning, design decisions, debugging, complex implementation
3. **Research organization** — synthesize and structure findings

**Codex call patterns:**
- Analysis (read-only): `codex exec --model gpt-5.4 --sandbox read-only --full-auto "{question}"`
- Implementation (write): `codex exec --model gpt-5.4 --sandbox workspace-write --full-auto "{task}"`

**Tools available**: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch

**Working principles**: Independence (no clarifying questions), efficiency (parallel tool calls), concise output, context awareness (.claude/docs/).

### 2.2 codex-debugger (Opus)

**Role**: Error analysis specialist powered by Codex CLI.

**Workflow:**
1. **Gather context** — read error files, check recent git changes, find related tests
2. **Call Codex CLI** — pass full error output + relevant code + context
3. **Apply and verify fix** — directly if clear, or return recommendation

**Trigger conditions:**
- Test failures (pytest, npm test, cargo test)
- Build errors (tsc, ruff, mypy)
- Runtime errors (Traceback, Exception, panic)
- Lint errors (non-auto-fixable)
- Unexpected command failures

**Output format**: Diagnosis (1-2 sentence root cause), Details (what/where/why), Recommended Fix (code), Prevention.

**Tools available**: Read, Edit, Write, Bash, Grep, Glob

### 2.3 gemini-explore (Opus)

**Role**: Analysis and research agent using Gemini CLI's 1M context.

**Three roles:**
1. **Codebase & Repository Understanding** — full project analysis, cross-module dependencies, patterns
2. **External Research & Survey** — library investigation, best practices, technology comparison (Google Search grounding)
3. **Multimodal File Processing** — PDF, video, audio, image content extraction

**Supported file types:**
- PDF: `.pdf`
- Video: `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`
- Audio: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`
- Image: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg`

**Tools available**: Read, Bash, Grep, Glob, WebFetch, WebSearch

**Result persistence**: Research → `.claude/docs/research/`, Library docs → `.claude/docs/libraries/`

---

## 3. Skills System (.claude/skills/) — 14 Skills

### 3.1 Core Workflow Skills (3)

#### /startproject — Project Kickoff with Agent Teams

**Purpose**: Multi-agent collaborative project start (planning phases only).

**Phases:**
1. **UNDERSTAND** (Gemini + Claude Lead): Gemini analyzes codebase (1M context), Claude gathers requirements from user. Creates "Project Brief" with current state, goal, scope, constraints, success criteria.
2. **RESEARCH & DESIGN** (Agent Teams — Parallel): Researcher (Gemini) and Architect (Codex) communicate bidirectionally. Researcher finds libraries/constraints, Architect creates design. Real-time interaction replaces sequential subagent rounds.
3. **PLAN & APPROVE** (Claude Lead + User): Synthesize results, create task list (TodoWrite), update CLAUDE.md with project context, present plan to user for approval.

**Output files**: Research findings, library docs, DESIGN.md updates, CLAUDE.md updates, task list.

#### /team-implement — Parallel Implementation with Agent Teams

**Prerequisites**: /startproject complete and plan approved.

**Workflow:**
1. **Analyze Plan & Design Team** — identify parallelizable workstreams, assign file ownership
2. **Spawn Agent Team** — launch Implementer per module + optional Tester
3. **Monitor & Coordinate** — Lead monitors, does not implement directly
4. **Integration & Verification** — run full quality check suite

**Team patterns:**
- **Module-Based** (recommended): each teammate owns a module
- **Layer-Based**: data layer, business logic, interface layer
- **Feature-Based**: each teammate owns a full feature

**Anti-patterns**: two teammates editing same file, too many tasks per teammate, overly complex dependencies.

**Work logs**: each teammate writes `.claude/logs/agent-teams/{team-name}/{teammate}.md` upon completion.

#### /team-review — Parallel Code Review with Agent Teams

**Prerequisites**: Implementation complete, all tests passing.

**Reviewers:**
1. **Security Reviewer** — hardcoded secrets, injection, input validation, auth issues, data exposure
2. **Quality Reviewer** — coding principles adherence, uses Codex for deep analysis
3. **Test Reviewer** — runs coverage, checks happy/error/boundary/edge cases, AAA pattern

**Prioritization**: Critical (must fix) → High (should fix) → Medium (if time allows) → Low (track for later).

**Optional**: Competing hypotheses mode for bug investigation (3-5 adversarial teammates).

### 3.2 Development Skills (3)

#### /plan — Implementation Planning

**Purpose**: Break requirements into detailed, actionable steps.

**Output**: Purpose, scope (new/modified files, dependencies), implementation steps with verification criteria, risks/considerations, open questions.

**Flag**: `disable-model-invocation: true` (does not trigger model calls itself).

#### /tdd — Test-Driven Development

**Cycle**: Red → Green → Refactor (repeat)

**Phases:**
1. **Test Design** — confirm requirements, list test cases (happy path, boundary, error, edge)
2. **Red-Green-Refactor** — write failing test, minimal implementation, refactor
3. **Completion Check** — all tests pass, coverage ≥80%

#### /simplify — Code Refactoring

**Principles**: Single responsibility, <20 line functions, shallow nesting (depth ≤ 2), clear naming, type hints required.

**Patterns**: Early return, extract function.

**Safety**: Check library constraints in `.claude/docs/libraries/`, run tests after each change.

### 3.3 Agent Delegation Skills (2)

#### /codex-system — Codex CLI Integration

**Roles**: Planning & design, complex implementation.

**When to use**: Planning, design decisions, complex implementation, debugging, trade-off analysis, refactoring, code review.

**When NOT to use**: Simple edits, git/test/lint commands, codebase analysis (→ Gemini), external research (→ Gemini), multimodal (→ Gemini).

**Reference files**: 5 reference templates (agent-prompts.md, code-review-task.md, delegation-patterns.md, refactoring-task.md, troubleshooting.md).

#### /gemini-system — Gemini CLI Integration

**Roles**: Codebase understanding (1M context), external research (Google Search grounding), multimodal file reading.

**Auto-triggers**: When multimodal file extensions appear in task.

### 3.4 Documentation Skills (4)

#### /design-tracker — Automatic Design Decision Tracking

**Purpose**: PROACTIVELY record design decisions without being asked. Detects architecture discussions, implementation decisions, pattern choices, library selections.

**Target sections**: Overview, Architecture, Implementation Plan (Patterns, Libraries, Key Decisions), TODO, Open Questions.

#### /update-design — Explicit Design Document Update

**Purpose**: Force update `.claude/docs/DESIGN.md` with conversation content. Uses same workflow as design-tracker but triggered explicitly.

#### /research-lib — Library Research

**Primary tool**: Gemini CLI (Google Search grounding).

**Output**: Saves comprehensive documentation to `.claude/docs/libraries/{library}.md` using standardized template (Basic Info, Core Features, Constraints, Usage Patterns, Troubleshooting).

#### /update-lib-docs — Library Documentation Update

**Purpose**: Update existing library docs with latest information (version, breaking changes, deprecated features, security updates).

**Impact check**: After update, verify if codebase uses deprecated APIs or is affected by breaking changes.

### 3.5 Session Management Skills (2)

#### /checkpointing — Full Session Recording + Pattern Discovery

**Captures**: Git history (commits, file changes, line stats), CLI logs (Codex/Gemini), Agent Teams activity (tasks, teammates, messages, effectiveness), Teammate work logs, Design decision diffs.

**Outputs:**
1. Checkpoint file → `.claude/checkpoints/YYYY-MM-DD-HHMMSS.md`
2. Session summary → appended to `CLAUDE.md` (cross-session persistence)
3. Skill pattern analysis prompt → for subagent pattern discovery

**Pattern discovery**: Identifies reusable workflows in checkpoint data (commit sequences, file change patterns, CLI consultation sequences, Agent Teams coordination patterns). Suggests new skills with confidence scores.

**Implementation**: `checkpoint.py` (645 lines) — Python script that collects data from git, CLI logs, Agent Teams directories, and design docs.

#### /init — Project Initialization

**Purpose**: Analyze project structure and update AGENTS.md.

**Detection**: package.json (Node.js), pyproject.toml (Python), Cargo.toml (Rust), go.mod (Go), Makefile/Dockerfile, CI/CD configs.

**User questions**: Project overview, code language preference, additional rules.

---

## 4. Hooks System (.claude/hooks/) — 9 Hooks

### 4.1 UserPromptSubmit Hooks

#### agent-router.py

**Trigger**: Every user prompt submission (>10 chars).

**Logic (priority order):**
1. **Multimodal file detection** (HIGHEST PRIORITY) — regex matches file paths with PDF/video/audio/image extensions → suggests Gemini
2. **Codex triggers** — Japanese + English keywords for design, planning, debugging, comparison, implementation → suggests Codex
3. **Gemini research triggers** — keywords for research, survey, documentation, codebase understanding → suggests Gemini

### 4.2 PreToolUse Hooks

#### check-codex-before-write.py

**Matcher**: Edit|Write

**Logic**: Analyzes file path and content for design indicators (DESIGN.md, architecture, schema, model, interface, abstract, base_, core/, config, class definitions, Protocol, dataclass). Skips simple edits (.gitignore, README, pyproject.toml). Suggests Codex for files >500 lines or new source files in src/.

#### suggest-gemini-research.py

**Matcher**: WebSearch|WebFetch

**Logic**: Detects research indicators (documentation, best practice, comparison, library, framework, architecture, migration, API reference). Skips simple lookups (error messages, version checks, changelogs). Long queries (>100 chars) also trigger suggestion.

### 4.3 PostToolUse Hooks

#### check-codex-after-plan.py

**Matcher**: Task

**Logic**: After Task tool executes, checks if the task involved planning/design keywords. Suggests Codex review for plan tasks.

#### error-to-codex.py

**Matcher**: Bash

**Logic**: Detects error patterns in command output (Traceback, Exception, panic, FAILED, npm ERR!, etc.). Ignores trivial commands (git status, ls) and simple errors (command not found, no such file). Skips Codex/Gemini commands to avoid recursive suggestions. Directs to `codex-debugger` subagent.

#### post-test-analysis.py

**Matcher**: Bash

**Logic**: Specifically targets test/build commands (pytest, npm test, ruff check, ty check, tsc, cargo test, go test). Detects complex failures (3+ error patterns, or tracebacks with assertions). Filters out simple errors (ModuleNotFoundError, command not found).

#### lint-on-save.py

**Matcher**: Edit|Write

**Logic**: For Python files, automatically runs:
1. `uv run ruff format {file}` (auto-format)
2. `uv run ruff check --fix {file}` (auto-fix lint)
3. `uv run ty check {file}` (type check)

Reports remaining unfixable issues.

#### post-implementation-review.py

**Matcher**: Edit|Write

**Logic**: Tracks cumulative file changes across session (via `/tmp/claude-code-implementation-state.json`). When 3+ source files modified OR 100+ meaningful lines written, suggests Codex code review. Only triggers once per session.

#### log-cli-tools.py

**Matcher**: Bash (PostToolUse) + TaskCompleted

**Logic**: Detects Codex/Gemini CLI calls in Bash commands. Extracts prompts and responses. Logs to `.claude/logs/cli-tools.jsonl` with timestamp, tool, model, prompt, response (truncated at 2000 chars), success/failure, exit code.

### 4.4 TeammateIdle Hook

**Logic**: Inline echo command that instructs idle teammates to:
1. Check shared task list for pending tasks
2. Write work log to `.claude/logs/agent-teams/{team-name}/{teammate}.md`
3. Report to team lead

### 4.5 PreCompact Hook

**Matcher**: auto (automatic context compaction)

**Logic**: Injects additional context about key files to preserve during compaction: CLAUDE.md, DESIGN.md, .claude/rules/.

---

## 5. Rules System (.claude/rules/) — 7 Rules

### 5.1 coding-principles.md

Core rules: simplicity first, single responsibility, early return, type hints required, immutability (create new objects vs mutate), meaningful naming (snake_case, PascalCase, UPPER_SNAKE_CASE), no magic numbers. Target 200-400 lines/file (max 800).

### 5.2 dev-environment.md

Toolchain: uv (package management, NO pip), ruff (lint + format), ty (type check by Astral), marimo (reactive notebooks), poethepoet (task runner). pyproject.toml configuration for ruff (target py311, line-length 88, select E/W/F/I/B/UP), pytest, poe tasks.

### 5.3 testing.md

TDD recommended, 80%+ coverage target, <100ms per unit test. AAA pattern (Arrange-Act-Assert). Naming: `test_{target}_{condition}_{expected_result}`. Coverage: happy path, boundary values, error cases, edge cases. Mock external dependencies. Fixtures in conftest.py.

### 5.4 security.md

No hardcoded secrets (use env vars), input validation (Pydantic), parameterized SQL queries, XSS prevention (template auto-escaping), minimal error messages (details to logs only), regular dependency audits (pip-audit, safety), pin versions.

### 5.5 language.md

Thinking/reasoning: English. User communication: Japanese. All code in English (variables, functions, comments, docstrings). Technical documentation: English.

### 5.6 codex-delegation.md

Default Codex-first for development tasks. Decision criteria: design/architecture involved, 2+ files with behavior impact, unclear root cause, comparison/trade-off needed, step-by-step plan needed. Prompt contract: Objective + Constraints + Relevant files + Acceptance checks + Output format. Two sandbox modes: read-only (analysis) and workspace-write (implementation).

### 5.7 gemini-delegation.md

Three roles: codebase analysis (1M context), external research (Google Search grounding), multimodal reading (PDF/video/audio/image). Trigger phrases documented in Japanese and English. Auto-trigger for multimodal file extensions. NOT for planning/design (→ Codex), debugging (→ Codex), or implementation (→ Claude/subagent).

---

## 6. Codex CLI Integration (.codex/)

### 6.1 Configuration (config.toml)

- Model: gpt-5.4
- Reasoning: effort=high, summary=detailed
- Web search: live
- Approval policy: never (non-interactive, never blocks)
- Skills: enabled (context-loader)
- Verbosity: medium

### 6.2 Agent Contract (AGENTS.md)

**Responsibilities**: Implementation plan decomposition, design comparison, complex code changes / root cause analysis, test strategy proposals.

**Non-responsibilities**: External web research (→ Gemini), multimodal analysis (→ Gemini), user communication (→ Claude).

**Required response structure**: TL;DR → Analysis → Plan → Patch Strategy → Validation → Risks.

**Code quality rules**: Follow existing style, avoid unnecessary abstraction, observable error handling, maintain testability.

**Handoff rules**: Return "immediately executable" procedures, compress to essential points, separate unverified items as TODO.

### 6.3 Context Loader Skill

**Purpose**: Load project context at the start of EVERY Codex task.

**Loads**: `.claude/rules/*` (coding principles, dev environment, language, security, testing), `.claude/docs/DESIGN.md`, `.claude/docs/libraries/*` (as needed).

Ensures Codex operates with the same knowledge as Claude Code.

---

## 7. Gemini CLI Integration (.gemini/)

### 7.1 Configuration (settings.json)

- Model: gemini-3.1-pro
- Context: reads GEMINI.md and AGENTS.md, max 200 directories for discovery
- File filtering: respects .gitignore and .geminiignore
- Tools: sandbox=false, autoAccept=false
- Experimental: skills=true, enableAgents=true

### 7.2 Research Contract (GEMINI.md)

**Responsibilities**: Cross-codebase analysis (1M context), official documentation-centered research, multimodal content extraction, separation of facts vs recommendations.

**Research quality standard**: Official primary sources first, check publication/update dates, cross-reference multiple sources, explicitly mark unverified information.

**Required output format**: Executive Summary → Verified Facts → Implications for This Repo → Recommended Changes → Open Questions.

**Multimodal policy**: Separate observations from interpretations, note OCR/speech recognition error potential, recommend re-verification of important numbers.

**Output size control**: Save long content to files, return summaries to conversation, compress tables to "minimum granularity needed for decisions."

### 7.3 Context Loader Skill

Same purpose as Codex context-loader: loads `.claude/rules/`, `.claude/docs/DESIGN.md`, `.claude/docs/libraries/` at the start of every task.

---

## 8. Documentation System (.claude/docs/)

### 8.1 DESIGN.md

Architecture decisions, implementation patterns, library choices, key decisions with rationale and dates, TODO items, open questions, changelog. Updated by design-tracker skill (automatic) and update-design skill (explicit).

### 8.2 CODEX_HANDOFF_PLAYBOOK.md

Standardized templates for delegating to Codex. Decision matrix (when to delegate vs skip). Prompt contract (5 required fields). Two prompt templates: Planning/Design (read-only) and Complex Implementation (workspace-write). Claude-side compression rules (keep only top recommendation, 3-5 steps, risks requiring user decision). Failure recovery: re-run with explicit files, split into plan + implement, ask Codex to compare exactly two options.

### 8.3 libraries/_TEMPLATE.md

Standardized template for library documentation: Basic Information (version, license, docs, GitHub, PyPI), Core Features (with code examples), Constraints and Notes (limitations, conflicts, performance), Usage Patterns (recommended + avoid), Troubleshooting (common errors), Related Files, Reference Links.

### 8.4 research/

Directory for storing research findings from Gemini/subagents. Kept empty in template (`.gitkeep`).

---

## 9. Development Environment (pyproject.toml)

**Project**: Python ≥3.11, uses hatchling build system.

**Dependencies**: None in production.

**Dev dependencies**: ruff ≥0.8, ty ≥0.1, pytest ≥8.0, poethepoet ≥0.31.

**Ruff config**: target py311, line-length 88, rules E/W/F/I/B/UP, ignore E501, double-quote format.

**Pytest config**: testpaths=tests, pythonpath=src, addopts="-v --tb=short".

**Poe tasks**: lint (ruff check + format check), format (ruff fix + format), typecheck (ty check src/), test (pytest -v), all (lint + typecheck + test).

---

## 10. Core Workflow Pipeline

The main development workflow is a 3-skill pipeline:

```
/startproject <feature>     Phase 1-3: Codebase understanding → Research & Design → Plan
    ↓ User approval
/team-implement             Phase 4: Parallel implementation with Agent Teams
    ↓ Implementation complete
/team-review                Phase 5: Parallel review (Security + Quality + Test)
```

Between sessions: `/checkpointing` records all activity and discovers reusable patterns.
For any new project: `/init` detects tech stack and configures agents.

---

## 11. Context Management Strategy

| Situation | Method |
|-----------|--------|
| Full codebase analysis | Gemini (1M context) |
| External research/survey | Gemini (Google Search grounding) |
| Multimodal files | Gemini |
| Code implementation | Subagent (Opus) |
| Design/planning consultation | Subagent → Codex |
| Short question/answer | Direct call OK |
| Detailed analysis needed | Subagent → save to file |
| Results >20 lines | Save to `.claude/docs/`, return summary |

---

## 12. Language Protocol Summary

| Context | Language |
|---------|----------|
| User-facing communication | Japanese |
| Code, identifiers, commands | English |
| Thinking/reasoning (internal) | English |
| Codex queries and responses | English |
| Gemini queries and responses | English |
| Technical documentation | English |

---

## 13. Security Model

**File access control:**
- Deny: .env, .env.*, *.pem, *.key, credentials*, *secret*, ~/.ssh/**, ~/.aws/**, ~/.config/gcloud/**
- Deny: rm -rf /, rm -rf ~

**Code security rules:**
- Environment variables for secrets (never hardcode)
- Pydantic for input validation
- Parameterized SQL queries
- Auto-escaped template output
- Minimal error messages to users (details in logs)
- Regular dependency vulnerability scanning

**Hook security:**
- Input validation in hooks (MAX_PATH_LENGTH, MAX_CONTENT_LENGTH, path traversal checks)
- All hooks fail open (sys.exit(0) on error — never block the user)

---

## 14. File Inventory

| Category | Count | Files |
|----------|-------|-------|
| Core config | 4 | CLAUDE.md, .claude/settings.json, pyproject.toml, .gitignore |
| Agents | 3 | general-purpose.md, codex-debugger.md, gemini-explore.md |
| Skills | 14 | startproject, team-implement, team-review, plan, tdd, simplify, codex-system, gemini-system, design-tracker, update-design, research-lib, update-lib-docs, checkpointing, init |
| Skill references | 8 | task-patterns.md, agent-prompts.md, code-review-task.md, delegation-patterns.md, refactoring-task.md, troubleshooting.md, lib-research-task.md, use-cases.md |
| Hooks | 9 | agent-router.py, check-codex-before-write.py, check-codex-after-plan.py, error-to-codex.py, lint-on-save.py, log-cli-tools.py, post-implementation-review.py, post-test-analysis.py, suggest-gemini-research.py |
| Rules | 7 | coding-principles.md, dev-environment.md, testing.md, security.md, language.md, codex-delegation.md, gemini-delegation.md |
| Docs | 4 | DESIGN.md, CODEX_HANDOFF_PLAYBOOK.md, libraries/_TEMPLATE.md, research/.gitkeep |
| Codex integration | 3 | AGENTS.md, config.toml, context-loader/SKILL.md |
| Gemini integration | 3 | GEMINI.md, settings.json, context-loader/SKILL.md |
| Other | 3 | README.md, LICENSE, summary.png |
| **Total** | **58** | (excluding uv.lock and .git) |

---

*Analysis completed by reading every file in the repository.*
