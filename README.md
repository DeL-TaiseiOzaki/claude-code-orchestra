# claude-code-orchestra

![Claude Code Orchestra](./summary.png)

Multi-Agent AI Development Environment

```
Claude Code (Orchestrator) ─┬─ Sonnet Subagents (Routine Implementation)
                             ├─ Opus Subagents (Research, Analysis, Difficult Implementation)
                             └─ Codex CLI (Planning & Complex Code)
```

## Quick Start

Confirm that both AI CLIs are installed and authenticated first:

```bash
claude --version && codex --version
```

### New Project

Create a repository with GitHub's **Use this template** button, clone it, then run:

```bash
claude
```

Run `/init` inside Claude Code to detect the project stack and populate the project
identity and design document.

### Existing Project

Run this from the root of an existing Git repository:

```bash
template_dir="$(mktemp -d)"
git clone --depth 1 https://github.com/DeL-TaiseiOzaki/claude-code-orchestra.git "$template_dir"
bash "$template_dir/scripts/install.sh" . && rm -rf "$template_dir"
```

The installer preserves project-owned files, including `README.md`, `VERSION`, and
existing `AGENTS.md` / `CLAUDE.md` content. It installs the merged content in
`.claude/STATE.md`, installs the concise shared `AGENTS.md` contract, and creates
`CLAUDE.md -> AGENTS.md`. Template-owned path conflicts stop the install before
changes are made. After reviewing the reported paths, `--force` can be used to back
them up under `.orchestra-backup-*/` and replace them.

An existing `.claude/settings.json` is never overwritten. When a manual merge is
needed, the installer writes `.claude/settings.orchestra.json`; merge the required
settings and delete the candidate before starting Claude Code.

Then start Claude Code and run `/init` inside it:

```bash
claude
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

### System Tools

The installer and updater require `git` and standard Unix shell tools. Template
updates additionally require `rsync`.

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

### Keeping AI CLIs Up to Date

Claude Code and Codex CLI both release frequently — model names, flags, and sandbox semantics drift between minor versions. **Update both before each working session.**

```bash
# Claude Code (built-in self-update)
claude update

# Codex CLI
npm install -g @openai/codex@latest
```

Confirm versions afterward:

```bash
claude --version && codex --version
```

The Codex model is centralized in `.claude/settings.json` (`env.CODEX_MODEL`), which every `${CODEX_MODEL:-...}` reference resolves to. `.codex/config.toml` (`model` + `model_reasoning_effort = "xhigh"`) must be kept in sync — `scripts/check.sh` verifies coherence between the two. To always use the latest model, bump that single value (currently `gpt-5.6-sol`) — no need to edit individual skill files. The `${CODEX_MODEL:-...}` fallback is just a default for when the env var is unset. Note: `update.sh` never auto-merges `.claude/settings.json` — downstream users must bump `env.CODEX_MODEL` manually after reviewing the Phase 5 diff.

Claude subagent routing is explicit in `.claude/agents/`: `general-purpose-sonnet`
and `general-purpose-opus` pin their own model aliases in frontmatter. Unspecified
subagents default to Sonnet through `.claude/settings.json`
(`env.CLAUDE_CODE_SUBAGENT_MODEL`).

Peer CLI agents are reached through `.claude/skills/_shared/cli_consult.py`,
which supports Claude Code (`--cli claude`) and Antigravity (`--cli
antigravity`, headless `agy -p`). Gemini CLI support was removed.

## Architecture

The normative orchestration policy and the complete agent/skill overview live in
`CLAUDE.md`; root `AGENTS.md` carries the CLI-agent contract every runtime
auto-loads, and `.claude/rules/tiers.md` the stable tier details.
Claude Code is the initial main agent. If the user asks to promote Codex,
Antigravity, or another runtime, follow `.claude/docs/change_main.md`. The diagram
below is a non-normative overview of the default setup.

```
┌─────────────────────────────────────────────────────────────┐
│       Claude Code (Orchestrator — Opus, 1M context)         │
│       → Context conservation is top priority                │
│       → Handles user interaction, coordination, concise edits│
│                          │                                  │
│  ┌───────────────────────┼──────────────────────────────┐   │
│  │  Tier 1 — Default     │                              │   │
│  │  ┌────────────────────┴─────────────────────────┐    │   │
│  │  │ general-purpose-sonnet: routine impl.        │    │   │
│  │  │ general-purpose-opus: research / hard impl.  │    │   │
│  │  │ codex-debugger: error analysis               │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  │                       │                              │   │
│  │  ┌────────────────────┴─────────────────────────┐    │   │
│  │  │ Tier 2 — Sol                                 │    │   │
│  │  │ Codex CLI  (gpt-5.6-sol, effort xhigh)      │    │   │
│  │  │ → Design, planning, complex code, debugging  │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  │                       │                              │   │
│  │  ┌────────────────────┴─────────────────────────┐    │   │
│  │  │ Tier 3 — Fable  (rare escalation authority)  │    │   │
│  │  │ → Arbitration, stuck problems, final review  │    │   │
│  │  │ → May land the resolution; notes to reviews/ │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Context Management (Important)

Use the routing policy and execution patterns in `CLAUDE.md`.
Product-specific delegation mechanics remain in `.claude/rules/` and the
corresponding canonical agent or skill definitions.

The posture is **delegation-first**: `.claude/rules/delegation.md` makes direct
execution by the main agent the exception, limited to a closed Self-Handle List,
and names the triggers, route table, and subagent prompt contract that every
skill follows. Delegating moves the work, not the accountability — the caller
still runs the acceptance checks and inspects the diff.

## Directory Structure

`.claude/` is the physical source for the agent runtime: rules, skills, agent
definitions, hooks, project documents, and state. `.agents/` (Antigravity) and
`.codex/` (Codex) are each a runtime's native directory and hold exactly one
thing — that runtime's entry contract. Every shared document lives under
`.claude/` and is referenced by path, never copied. Nothing in the layout is
reached through a symlink.

```
.
├── AGENTS.md                    # CLI agent contract, auto-loaded by every runtime; routes the main agent to CLAUDE.md
├── CLAUDE.md                    # Main agent contract: mission, routing, agent/skill catalog, gates
├── README.md
├── PROGRESS.md                  # Generated by the first /checkpointing run; latest 5 summaries
├── LICENSE
├── pyproject.toml               # Python project configuration
├── uv.lock                      # Dependency lock file
├── VERSION                      # Version of this template repository; downstream projects may replace it
│
├── .claude/                     # Main agent runtime (physical source)
│   ├── settings.json            # Claude Code settings; hooks point to .claude/hooks/
│   ├── orchestra-version        # Installed Orchestra version in downstream projects
│   ├── STATE.md                 # Main agent, repository identity, and working state
│   ├── agents/                  # Subagent definitions, auto-discovered by Claude Code
│   ├── skills/                  # Workflow skills and deterministic helpers
│   │   └── _shared/             # Bundled runtime: helpers every skill may depend on
│   ├── hooks/                   # Hook implementations
│   ├── rules/                   # Policy: delegation, tiers, CLI, coding, testing, security, state
│   ├── docs/                    # INDEX.md registry, change_main.md runbook, design, research, reviews
│   ├── logs/                    # Runtime logs (git-ignored)
│   └── checkpoints/             # Session checkpoints (git-ignored)
│
├── .agents/                     # Antigravity's native directory
│   └── AGENTS.md                # Antigravity adapter: headless behaviour and limits
│
├── .codex/                      # Codex's native directory
│   ├── AGENTS.md                # Codex adapter: model config, sandbox discipline, enabled skills
│   └── config.toml              # Native configuration (never overwritten); skills point to .claude/skills/
│
├── tests/                      # Contract tests for the template's own scripts and docs
│
└── scripts/
    ├── check.sh                # Contract, bootstrap, model, and tier coherence checker
    ├── install.sh              # Conflict-aware installer for existing projects
    └── update.sh               # Template update script
```

Every CLI runtime auto-loads root `AGENTS.md`, which is self-contained: response
structure, handoff rules, how to call another CLI as a subagent, and the
completion-verification guardrails are all in the file that gets loaded. From
there the main agent reads `CLAUDE.md`, and each runtime reads its own short
adapter (`.codex/AGENTS.md`, `.agents/AGENTS.md`) only for what is specific to
it. Nothing a delegated run depends on sits behind a pointer.

### Stabilizing Codex Integration

- Use templates from `@.claude/docs/CODEX_HANDOFF_PLAYBOOK.md` to standardize requests to Codex
- `.claude/rules/codex-delegation.md` defines the "Codex-first delegation" policy and exception conditions
- `.codex/config.toml` uses `approval_policy = "never"` to prevent blocking in non-interactive flows, and `sandbox_mode = "danger-full-access"` for unrestricted execution
- The shared wrappers default to the same unrestricted access rather than being quietly stricter than the CLI they wrap, so what an agent may touch does not depend on which path reached it. `--sandbox read-only` (Codex) and `--read-only` (`cli_consult.py`) remain explicit opt-ins for planning and review calls
- Since nothing confines a delegated run, every wrapper call is bracketed by `.claude/skills/_shared/edit_provenance.py` and records the files it created, changed, or deleted — with `caller` and `label` — to `.claude/logs/cli-tools.jsonl`. That log is how you answer "which subagent changed this?"

## Workflow

The main workflow executes two skills in sequence.

```
/feature <feature>   Planning: mode determination → understanding → research & design → plan
    ↓ After user approval (COMPLEX route)
/team-execute        Phase 1: Parallel implementation → Phase 2: Parallel review (Agent Teams)
```

1. **Mode determination**: existing (Codex-direct design) or greenfield (Agent Teams research & design)
2. **Opus subagent** analyzes the codebase (1M context) + **Claude** conducts requirements gathering with the user
3. Existing mode: **Codex** designs, plans, and validates. Greenfield mode: **Agent Teams** — Researcher (Opus) and Architect (Codex) work in parallel
4. **Claude** integrates research and design, then presents the plan to the user
5. After approval, `/team-execute` runs parallel implementation by module, then parallel review for security, quality, and testing (`--review-only` skips implementation)

## Skills

Each skill is a `SKILL.md` procedure that an agent follows. Steps with exactly
one correct output for a given input — deriving artifact paths, validating
document structure, invoking the Codex CLI, running quality gates — are
delegated to bundled scripts instead of being described in prose, so they cannot
drift between phases or fail silently. Judgment steps stay in markdown. The
boundary and the shared script contract (one JSON object on stdout, a common
exit-code vocabulary, errors never swallowed) are documented in
`.claude/skills/_shared/README.md`.

### Core Workflow

#### `/feature` — Feature Planning & Implementation (unified)

One entry point for feature work, with two modes (merger of the old `/add-feature` and `/start-feature`).

```
/feature user profile editing feature
```

**Modes:**
- **existing** (formerly `/add-feature`) — Codex-first addition to an established codebase: Opus subagent + Codex scope & impact analysis, then Codex architecture design, implementation plan, and validation
- **greenfield** (formerly `/start-feature`) — large/new feature requiring external research: Opus subagent codebase analysis, then Agent Teams (Researcher [Opus] + Architect [Codex]) perform parallel research & design

**Shared complexity-based routing:**
- SIMPLE (1-3 files, <50 LOC) → Direct Codex implementation
- MODERATE (3-5 files) → Codex implementation + `/team-execute --review-only`
- COMPLEX (5+ files) → `/team-execute`

#### `/team-execute` — Parallel Implementation + Review (unified)

Two-phase Agent Teams execution (merger of the old `/team-implement` and `/team-review`). Executes based on the plan approved in `/feature`.

```
/team-execute                 # Phase 1 IMPLEMENT → Phase 2 REVIEW
/team-execute --review-only   # Skip Phase 1; review existing changes
```

**Phase 1 IMPLEMENT:**
- Launches Teammates per module/layer with separated file ownership
- Manages dependencies via shared task list for autonomous coordination
- Each Teammate records a work log to `.claude/logs/agent-teams/` upon completion

**Phase 2 REVIEW (reviewer composition):**
- **Security Reviewer** — Detects security vulnerabilities
- **Quality Reviewer** — Checks code quality & pattern compliance (leveraging Codex)
- **Test Reviewer** — Validates test coverage & quality

#### `/spike` — Technical Investigation & Feasibility Study

A Codex-first, time-boxed technical investigation. Produces a **decision document** (with go/no-go recommendation). Provides decision-making material, not an implementation plan.

```
/spike Should we adopt WebSocket or SSE?
```

**Workflow:**
1. **Claude + Codex** → Frame investigation questions & define constraints
2. **Agent Teams** → Researcher (Opus external research) and Feasibility Analyst (Codex deep analysis) investigate in parallel
3. **Codex** → Synthesize into go/no-go recommendation & produce research report

> After a GO decision, proceed to implementation with `/feature`

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

### Documentation

#### `/design-tracker` — Design Decision Tracking

Detects design decisions during conversation and structurally updates the relevant section of `.claude/docs/DESIGN.md` (機能要件 / 非機能要件 / アーキテクチャ / 技術選定 / 制約 / Key Decisions). Activates proactively and also on explicit requests ("record this", "update DESIGN").

#### `/research-lib` — Library Research

Investigates a library and generates comprehensive documentation in `.claude/docs/libraries/`.

```
/research-lib httpx
```

#### `/update-lib-docs` — Update Library Documentation

Updates existing documentation in `.claude/docs/libraries/` with the latest information.

### Session Management

#### `/checkpointing` — Session Persistence

Records session activity into `.claude/checkpoints/`, regenerates the rolling
`PROGRESS.md`, and compacts stale working blocks in `.claude/STATE.md` while
preserving the main-agent selection, repository identity, and progress link.

```bash
/checkpointing                    # Full recording + pattern discovery
/checkpointing --since "2026-02-08"  # Only since a specific date
/checkpointing --compact-only    # Run only the Compact Phase (old /context-refresh)
```

#### `/init` — Project Initialization

Analyzes the project structure, auto-detects tech stack, commands, and
configuration. Populates `.claude/docs/DESIGN.md` and updates only the thin
`## Repository Identity` section in `.claude/STATE.md`.

#### `/catchup` — Onboarding Guide

Scans the repository (git history, AGENTS.md, project rules, skill catalog, DESIGN.md, research & library notes, checkpoints, agent-team logs) and writes a `GUIDE.md` at the repository root so new or returning contributors can understand past work and resume quickly.

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

When upgrading an installation that still uses an updater from v0.3.0 or earlier,
replace the updater itself before the first run. This prevents the old process from
writing its template version to a project-owned root `VERSION`:

```bash
template_dir="$(mktemp -d)"
git clone --depth 1 https://github.com/DeL-TaiseiOzaki/claude-code-orchestra.git "$template_dir"
cp "$template_dir/scripts/install.sh" "$template_dir/scripts/update.sh" scripts/
chmod +x scripts/install.sh scripts/update.sh
rm -rf "$template_dir"
./scripts/update.sh
```

**How it works:**
- `AGENTS.md` (router) and `CLAUDE.md` (main agent contract) are replaced with
  the template versions. A pre-2.0 `CLAUDE.md` symlink is retired first.
- `.claude/STATE.md`, project design/research, logs, and checkpoints are
  preserved. Legacy 2/3-zone `AGENTS.md` or `CLAUDE.md` state is migrated into
  `.claude/STATE.md` before the bootstrap is replaced.
- Only template-owned runtime subdirectories are atomically synced. Legacy
  runtime paths under `.agents/` and `.codex/` are removed.
- Real legacy `.agents/{docs,logs,checkpoints}` data and `.agents/STATE.md` are
  moved to `.claude/`; collisions are backed up before missing files are merged.
- Known legacy `.agents/hooks/` and `.agents/logs/` references in Claude
  settings are migrated to `.claude/`; other settings differences still require
  manual review.
- `.claude/settings.json` and `.codex/config.toml` are never overwritten; both only show a diff (manual merge required)
- The installed template version is stored in `.claude/orchestra-version`; a downstream project's root `VERSION` is never modified
- If the update modifies `scripts/update.sh` itself (e.g. a new version adds
  template directories such as `.claude/rules/`), **run `./scripts/update.sh` a second
  time** — the first run still uses the old script's sync list. Newer scripts
  print a reminder when this applies (updating from v0.2.0 does not, so run
  twice when upgrading to v0.3.0)

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
| `agent-router.py` | User input | Suggests routing to Codex / Opus subagent |
| `lint-on-save.py` | File save | Auto-runs lint |
| `check-codex-before-write.py` | Before file write | Suggests consulting Codex |
| `check-codex-after-plan.py` | After Task execution | Suggests Codex review after planning/design tasks |
| `post-bash-check.py` | Any Bash tool call | Dispatcher: runs error detection, test-failure analysis, and Codex I/O logging in one process (deduped) |
| `error-to-codex.py` | Bash error detected | Suggests codex-debugger subagent (invoked in-process by `post-bash-check.py`) |
| `post-test-analysis.py` | Test/build failure | Suggests debug analysis via Codex (invoked in-process by `post-bash-check.py`) |
| `post-implementation-review.py` | After large implementation | Suggests code review via Codex |
| `log-cli-tools.py` | Codex execution | Records I/O logs (invoked in-process by `post-bash-check.py`; also runs standalone on `TaskCompleted`) |

## Language Rules

- **Code, thinking, and reasoning**: English
- **Responses to users**: Japanese
- **Technical documentation**: English
- **README, etc.**: Japanese permitted
