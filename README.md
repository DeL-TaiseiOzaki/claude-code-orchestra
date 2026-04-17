# claude-code-orchestra

![Claude Code Orchestra](./summary.png)

Multi-Agent AI Development Environment

```
Claude Code (Orchestrator) ─┬─ Codex CLI (Planning & Complex Code)
                             ├─ Opus Subagents (Research, Analysis, Implementation)
                             └─ Gemini CLI (Multimodal: PDF/Video/Audio/Image)
```

## Quick Start

Run in the root of your existing project (ensure Codex/Gemini are installed and logged in first):

```bash
codex --version && codex login && gemini --version && gemini login && git clone --depth 1 https://github.com/DeL-TaiseiOzaki/claude-code-orchestra.git .starter && cp -r .starter/.claude .starter/.codex .starter/.gemini .starter/CLAUDE.md . && rm -rf .starter && claude
```

## Prerequisites

### Claude Code

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

### Codex CLI

```bash
npm install -g @openai/codex
codex login
```

### Codex Plugin for Claude Code (Optional)

A plugin that lets you use Codex directly from Claude Code. Simplifies code review and task delegation.

```bash
# Run inside Claude Code
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

**Available commands:**
- `/codex:review` — Code review
- `/codex:adversarial-review` — Design challenge review
- `/codex:rescue` — Task delegation
- `/codex:status` / `/codex:result` / `/codex:cancel` — Job management

### Gemini CLI

```bash
npm install -g @google/gemini-cli
gemini login
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           Claude Code (Orchestrator — Opus 4.6, 1M context)    │
│           → Context conservation is top priority             │
│           → Handles user interaction, coordination, concise edits │
│                      ↓                                      │
│  ┌──────────────────────┐  ┌──────────────────────────┐    │
│  │  Subagent (Opus)      │  │  gemini-explore (Opus)    │    │
│  │  general-purpose      │  │  → Gemini CLI             │    │
│  │  → Code implementation│  │  → Multimodal processing  │    │
│  │  → Research & analysis│  │  → PDF/Video/Audio/Image  │    │
│  │  → Codex delegation   │  │                            │    │
│  │  ┌──────────────┐    │  │                            │    │
│  │  │  Codex CLI   │    │  │  ┌──────────────┐          │    │
│  │  │  Design &    │    │  │  │  Gemini CLI  │          │    │
│  │  │  Reasoning   │    │  │  │  1M context  │          │    │
│  │  │  Debugging   │    │  │  └──────────────┘          │    │
│  │  └──────────────┘    │  │                            │    │
│  └──────────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Context Management (Important)

To conserve the main orchestrator's (Opus 4.6, 1M context) context, large-scale tasks are delegated to the appropriate agents.

| Situation | Recommended Method |
|-----------|-------------------|
| Full codebase analysis | **Opus subagent** (1M context) |
| External research & surveys | **Opus subagent** (WebSearch/WebFetch) |
| Multimodal files | **Via Gemini** (PDF/Video/Audio/Image) |
| Code implementation | Via subagent (Opus) |
| Design & planning consultation | Subagent → Codex |
| Short questions & answers | Direct call OK |
| Detailed analysis needed | Via subagent → save to file |

## Directory Structure

```
.
├── CLAUDE.md                    # Main system document
├── README.md
├── LICENSE
├── pyproject.toml               # Python project configuration
├── uv.lock                      # Dependency lock file
├── VERSION                      # Template version
│
├── .claude/
│   ├── agents/
│   │   ├── general-purpose.md   # Implementation, research & Codex delegation agent (Opus)
│   │   ├── codex-debugger.md    # Error analysis agent (Opus)
│   │   └── gemini-explore.md    # Multimodal processing agent (Opus)
│   │
│   ├── skills/                  # Reusable workflows (18 total)
│   │   ├── start-feature/       # Start feature with multi-agent coordination
│   │   ├── team-implement/      # Parallel implementation with Agent Teams
│   │   ├── team-review/         # Parallel review with Agent Teams
│   │   ├── add-feature/         # Codex-first feature addition (complexity-based routing)
│   │   ├── spike/               # Technical investigation & feasibility study (decision document)
│   │   ├── plan/                # Implementation plan creation
│   │   ├── tdd/                 # Test-driven development
│   │   ├── simplify/            # Code refactoring
│   │   ├── codex-system/        # Codex CLI integration
│   │   ├── gemini-system/       # Gemini CLI integration
│   │   ├── design-tracker/      # Automatic design decision tracking
│   │   ├── update-design/       # Explicit design document updates
│   │   ├── research-lib/        # Library research
│   │   ├── update-lib-docs/     # Library documentation updates
│   │   ├── checkpointing/       # Session persistence + pattern discovery
│   │   ├── catchup/             # Generate GUIDE.md for onboarding/re-onboarding
│   │   ├── init/                # Project initialization
│   │   └── troubleshoot/        # Error diagnosis & fix planning
│   │
│   ├── hooks/                   # Automation hooks (9 total)
│   │   ├── agent-router.py      # Agent routing
│   │   ├── lint-on-save.py      # Auto-lint on save
│   │   ├── error-to-codex.py    # Error detection → debugger suggestion
│   │   └── ...
│   │
│   ├── rules/                   # Development guidelines
│   │   ├── coding-principles.md
│   │   ├── testing.md
│   │   └── ...
│   │
│   ├── settings.json             # Claude Code settings (hooks/permissions/env)
│   │
│   ├── docs/
│   │   ├── DESIGN.md            # Design decision records
│   │   ├── CODEX_HANDOFF_PLAYBOOK.md  # Codex delegation templates
│   │   ├── research/            # Research results (Opus subagents)
│   │   └── libraries/           # Library constraints
│   │
│   └── logs/                    # Runtime generated (.gitignore target)
│       └── cli-tools.jsonl      # Codex/Gemini I/O logs
│
├── .codex/                      # Codex CLI configuration
│   ├── AGENTS.md
│   ├── config.toml
│   └── skills/
│       ├── context-loader/      # Context loading skill
│       └── design-tracker/      # Design tracking skill
│
├── .gemini/                     # Gemini CLI configuration
│   ├── GEMINI.md
│   ├── settings.json
│   └── skills/
│       └── context-loader/      # Context loading skill
│
└── scripts/
    └── update.sh               # Template update script
```

### Stabilizing Codex Integration

- Use templates from `@.claude/docs/CODEX_HANDOFF_PLAYBOOK.md` to standardize requests to Codex
- `.claude/rules/codex-delegation.md` defines the "Codex-first delegation" policy and exception conditions
- `.codex/config.toml` uses `approval_policy = "never"` to prevent blocking in non-interactive flows

## Workflow

The main workflow executes three skills in sequence.

```
/start-feature <feature>   Phase 1-3: Codebase understanding → Research & design → Planning
    ↓ After user approval
/team-implement            Phase 4: Parallel implementation with Agent Teams
    ↓ After implementation
/team-review               Phase 5: Parallel review with Agent Teams
```

1. **Opus subagent** analyzes the codebase (1M context) + **Claude** conducts requirements gathering with the user
2. **Agent Teams**: Researcher (Opus) and Architect (Codex) perform research and design in parallel
3. **Claude** integrates research and design, then presents the plan to the user
4. After approval, `/team-implement` runs parallel implementation by module
5. `/team-review` runs parallel review for security, quality, and testing

## Skills

### Core Workflow

#### `/start-feature` — Start Feature

Starts a feature with multi-agent coordination.

```
/start-feature user authentication feature
```

**Workflow:**
1. **Opus subagent** → Codebase analysis & preliminary research (1M context)
2. **Claude** → Requirements gathering with the user
3. **Agent Teams** → Researcher (Opus) and Architect (Codex) perform parallel research & design
4. **Claude** → Plan integration & user approval

#### `/team-implement` — Parallel Implementation

Parallel implementation with Agent Teams. Executes based on the plan approved in `/start-feature`.

```
/team-implement
```

**Features:**
- Launches Teammates per module/layer with separated file ownership
- Manages dependencies via shared task list for autonomous coordination
- Each Teammate records a work log to `.claude/logs/agent-teams/` upon completion

#### `/team-review` — Parallel Review

Parallel code review with Agent Teams. Run after implementation is complete.

```
/team-review
```

**Reviewer composition:**
- **Security Reviewer** — Detects security vulnerabilities
- **Quality Reviewer** — Checks code quality & pattern compliance (leveraging Codex)
- **Test Reviewer** — Validates test coverage & quality

#### `/add-feature` — Add Feature

Adds a feature to an existing codebase using a Codex-first approach. Lighter-weight than `/start-feature` (which targets large new features requiring research), with complexity-based implementation routing.

```
/add-feature user profile editing feature
```

**Workflow:**
1. **Opus subagent + Codex** → Scope & impact analysis
2. **Codex** → Architecture design, implementation plan, validation
3. **Complexity-based routing:**
   - SIMPLE (1-3 files, <50 LOC) → Direct Codex implementation
   - MODERATE (3-5 files) → Codex implementation + `/team-review`
   - COMPLEX (5+ files) → `/team-implement` + `/team-review`

#### `/spike` — Technical Investigation & Feasibility Study

A Codex-first, time-boxed technical investigation. Produces a **decision document** (with go/no-go recommendation). Provides decision-making material, not an implementation plan.

```
/spike Should we adopt WebSocket or SSE?
```

**Workflow:**
1. **Claude + Codex** → Frame investigation questions & define constraints
2. **Agent Teams** → Researcher (Opus external research) and Feasibility Analyst (Codex deep analysis) investigate in parallel
3. **Codex** → Synthesize into go/no-go recommendation & produce research report

> After a GO decision, proceed to implementation with `/add-feature` or `/start-feature`

### Development

#### `/plan` — Implementation Plan

Breaks down requirements into concrete steps.

```
/plan Add API endpoint
```

**Output:**
- Implementation steps (files, changes, verification methods)
- Dependencies & risks
- Validation criteria

#### `/tdd` — Test-Driven Development

Implements using the Red-Green-Refactor cycle.

```
/tdd user registration feature
```

**Workflow:**
1. Design test cases
2. Write failing tests (Red)
3. Minimal implementation (Green)
4. Refactoring (Refactor)

#### `/simplify` — Code Refactoring

Simplifies code and improves readability.

#### `/troubleshoot` — Error Diagnosis & Fix Planning

Diagnoses errors and creates fix plans through multi-agent coordination centered on Codex.

```
/troubleshoot TypeError: cannot unpack non-iterable NoneType object
```

**Workflow:**
1. **Opus subagent + Codex** → Error reproduction & context collection
2. **Agent Teams** → Root Cause Analyst (Codex-driven) and Impact Investigator (Opus + Codex) diagnose in parallel
3. **Claude + Codex** → Fix plan integration & user approval

### Agent Delegation

#### `/codex-system` — Codex CLI Integration

Used for design decisions, debugging, and trade-off analysis.

**Trigger examples:**
- "How should this be designed?" "How should I implement this?"
- "Why isn't this working?" "I'm getting an error"
- "Which is better?" "Compare these options"

#### `/gemini-system` — Gemini CLI Integration

Multimodal file processing (PDF/video/audio/image) powered by Gemini CLI.

**Trigger examples:**
- "Read this PDF" "Summarize this video"
- "Transcribe this audio" "Analyze this diagram"

### Documentation

#### `/design-tracker` — Design Decision Tracking

Automatically records architecture and implementation decisions. Detects design decisions during conversation and appends them to `.claude/docs/DESIGN.md`.

#### `/update-design` — Update Design Document

Extracts design decisions from conversation content and explicitly updates `.claude/docs/DESIGN.md`.

#### `/research-lib` — Library Research

Investigates a library and generates comprehensive documentation in `.claude/docs/libraries/`.

```
/research-lib httpx
```

#### `/update-lib-docs` — Update Library Documentation

Updates existing documentation in `.claude/docs/libraries/` with the latest information.

### Session Management

#### `/checkpointing` — Session Persistence

Records all session activity (git history, CLI consultations, Agent Teams activity, design decisions) and discovers reusable skill patterns.

```bash
/checkpointing                    # Full recording + pattern discovery
/checkpointing --since "2026-02-08"  # Only since a specific date
```

#### `/init` — Project Initialization

Analyzes the project structure, auto-detects tech stack, commands, and configuration, and updates AGENTS.md.

#### `/catchup` — Onboarding Guide

Scans the repository (git history, CLAUDE.md/AGENTS.md, project rules, skill catalog, DESIGN.md, research & library notes, checkpoints, agent-team logs) and writes a `GUIDE.md` at the repository root so new or returning contributors can understand past work and resume quickly.

```bash
/catchup
```

## Development

### Template Update

Safely applies template updates to your local project.

```bash
# Update to the latest version
./scripts/update.sh

# Update to a specific version
./scripts/update.sh v0.2.0

# Skip confirmation prompt
./scripts/update.sh --yes
```

**How it works:**
- `CLAUDE.md` uses a 3-zone layout separated by two markers:
  - **Zone A** (above `@orchestra:template-boundary`) — orchestra concept & template base; fully replaced by the update
  - **Zone B** (between the two markers) — repository identity, managed by `/init`; preserved across updates
  - **Zone C** (below `@orchestra:repo-boundary`) — working state (features, session notes); preserved across updates
- Projects still using the legacy `@orchestra:local-boundary` layout are auto-migrated on first run: their content below the legacy marker becomes Zone C, and Zone B is reset to the placeholder so `/init` can repopulate it
- skills/hooks/rules/agents are fully synced
- Local data such as `.claude/docs/research/` is preserved
- `.claude/settings.json` only shows a diff (manual merge required)

### Tech Stack

| Tool | Purpose |
|--------|------|
| **uv** | Package management (pip is prohibited) |
| **ruff** | Linting & formatting |
| **ty** | Type checking |
| **pytest** | Testing |
| **poethepoet** | Task runner |

### Commands

```bash
# Dependencies
uv add <package>           # Add package
uv add --dev <package>     # Add dev dependency
uv sync                    # Sync dependencies

# Quality checks
poe lint                   # ruff check + format
poe typecheck              # ty
poe test                   # pytest
poe all                    # Run all checks

# Direct execution
uv run pytest -v
uv run ruff check .
```

## Hooks

Automation hooks execute agent coordination and quality checks at the appropriate timing.

| Hook | Trigger | Action |
|--------|----------|------|
| `agent-router.py` | User input | Suggests routing to Codex/Gemini |
| `lint-on-save.py` | File save | Auto-runs lint |
| `check-codex-before-write.py` | Before file write | Suggests consulting Codex |
| `check-codex-after-plan.py` | After Task execution | Suggests Codex review after planning/design tasks |
| `error-to-codex.py` | Bash error detected | Suggests codex-debugger subagent |
| `post-test-analysis.py` | Test/build failure | Suggests debug analysis via Codex |
| `post-implementation-review.py` | After large implementation | Suggests code review via Codex |
| `suggest-gemini-research.py` | Before WebSearch/Fetch | Suggests delegating deep research to Opus subagent |
| `log-cli-tools.py` | Codex/Gemini execution | Records I/O logs |

## Language Rules

- **Code, thinking, and reasoning**: English
- **Responses to users**: Japanese
- **Technical documentation**: English
- **README, etc.**: Japanese permitted
