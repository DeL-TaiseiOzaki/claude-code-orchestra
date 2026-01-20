# Project Overview

LLM/Agent Development Project

## Language Settings

- **Thinking/Reasoning**: English
- **Code**: English (variable names, function names, comments, docstrings)
- **User Communication**: Japanese

## Tech Stack

- **Language**: Python
- **Package Manager**: uv (required)
- **Dev Tools**:
  - ruff (lint & format)
  - ty (type check)
  - poe / poethepoet (task runner)
  - pytest (testing)
  - marimo (notebook, optional)
- **Environment**: venv (via uv)
- **Main Libraries**: <!-- Add libraries here -->

---

## Extensions

This project includes the following extensions.
Available for both Claude Code and Codex CLI.

### Agents (Auto-Delegation)

Agents that execute specialized tasks in independent context:

| Agent | Purpose | Trigger Examples |
|-------|---------|------------------|
| **code-reviewer** | Review after code changes | "review this", "check this" |
| **lib-researcher** | Library research & docs | "research this library" |
| **debugger** | Error investigation & fix | "fix this error", "debug this" |
| **refactorer** | Refactoring | "simplify this", "clean up" |

### Skills (Use Proactively)

**IMPORTANT: Use these skills proactively. Don't wait for explicit user request.**

| Skill | When to Use | How to Invoke |
|-------|-------------|---------------|
| **codex-system** | **ALWAYS** before design decisions, debugging, planning, trade-off evaluation | `/codex-system` or run `codex exec ...` |
| **design-tracker** | When design/architecture decisions are made in conversation | `/design-tracker` |
| **mcp-builder** | When building MCP servers or external API integrations | `/mcp-builder` |
| **skill-creator** | When creating new skills | `/skill-creator` |

#### Codex System (Most Important)

**Codex CLI is your highly capable supporter.** Use it proactively:

- Before implementing new features → Consult Codex for design
- When debugging fails once → Stop and consult Codex
- When multiple approaches exist → Ask Codex to evaluate trade-offs
- When uncertain about anything → Just ask Codex

```bash
# Analysis only (read-only)
codex exec --model gpt-5.2-codex --sandbox read-only --full-auto "Analyze: your question" 2>/dev/null

# Delegate work (can write files)
codex exec --model gpt-5.2-codex --sandbox workspace-write --full-auto "Task: implement X" 2>/dev/null
```

**Note:** Ask Codex in English → Receive English response → Report to user in Japanese

### Commands (Explicit Invocation)

Invoke with `/command`:

#### Claude Code Commands

| Command | Purpose |
|---------|---------|
| `/init` | Analyze project & update AGENTS.md |
| `/plan <feature>` | Create implementation plan |
| `/tdd <feature>` | Test-driven development workflow |
| `/research-lib <library>` | Research library & create docs |
| `/simplify <path>` | Simplify/refactor specified code |
| `/update-design` | Update design docs from conversation |
| `/update-lib-docs` | Update library documentation |

#### Codex CLI Prompts

> **Note**: Requires `cp .codex/prompts/*.md ~/.codex/prompts/` to user level

| Command | Purpose |
|---------|---------|
| `/prompts:analyze <topic>` | Deep analysis with options & trade-offs |
| `/prompts:review-architecture <path>` | Architecture review with recommendations |
| `/prompts:consult <question>` | Answer consultations from Claude Code |
| `/prompts:update-design` | Organize & record design decisions |

### Rules (Always Applied)

Rules to always follow (`.claude/rules/`):

| Rule | Content |
|------|---------|
| **language** | Think in English, respond in Japanese |
| **codex-delegation** | **ALWAYS consult Codex before design/debug/planning decisions** |
| **coding-principles** | Simplicity, single responsibility, early return, type hints |
| **dev-environment** | uv, ruff, ty, marimo usage |
| **security** | Secrets management, input validation, SQLi/XSS prevention |
| **testing** | TDD, AAA pattern, 80% coverage |

---

## Documentation Reference

Design decisions, architecture, implementation:
- `.claude/docs/DESIGN.md`

Library features, constraints, patterns:
- `.claude/docs/libraries/`

Coding rules (always applied):
- `.claude/rules/`

## Memory Management (Automatic)

**Record important information automatically. Don't wait for user to say "remember this".**

When these occur during conversation, record immediately:

| When Detected | Record To | Example |
|---------------|-----------|---------|
| Design/policy decision | `.claude/docs/DESIGN.md` | "Let's use ReAct pattern" |
| Library constraint found | `.claude/docs/libraries/{name}.md` | "This API is async only" |
| Project-specific rule | This `AGENTS.md` | "Output errors in Japanese" |

After recording, report briefly like "Recorded in DESIGN.md".

---

## Development Guidelines

### Coding Principles
- **Simplicity first** - Choose readable code over complex
- **Single responsibility** - One function/class does one thing
- **Early return** - Keep nesting shallow
- **Type hints required** - All functions need annotations
- **Code in English** - Variables, functions, comments, docstrings

### Library Management
- **Use uv** (direct pip usage prohibited)
- Manage dependencies in `pyproject.toml`
- Document library features/constraints in `.claude/docs/libraries/`
- Watch for inter-library dependencies/conflicts

### Information Gathering
- **Use web search for latest info** - Always verify library specs, best practices
- Reference official docs, GitHub Issues, Discussions
- Don't guess - always investigate unclear points

---

## Directory Structure

```
.claude/                   # Claude Code (System 1) settings & knowledge
├── settings.json          # Permission settings
├── agents/                # Sub-agents
├── rules/                 # Always-applied rules
│   ├── language.md
│   ├── codex-delegation.md
│   ├── coding-principles.md
│   ├── dev-environment.md
│   ├── security.md
│   └── testing.md
├── docs/                  # Knowledge base (actual)
│   ├── DESIGN.md          # Design document
│   └── libraries/         # Library documentation
├── skills -> ../.agent/skills
└── commands -> ../.agent/commands

.agent/                    # Shared tools
├── commands/              # Claude Code commands
├── skills/                # Auto-trigger skills
└── docs -> ../.claude/docs   # Link to knowledge base

.codex/                    # Codex CLI (System 2) settings
├── skills -> ../.agent/skills  # Shared skills
└── prompts/               # Custom prompts (copy to ~/.codex/prompts/)

src/                       # Source code
tests/                     # Tests
```

## Common Commands

```bash
# Project init (uv required)
uv init
uv venv
source .venv/bin/activate  # Linux/Mac

# Dependencies
uv add <package>           # Add package
uv add --dev <package>     # Add dev dependency
uv sync                    # Sync dependencies

# Task execution (poethepoet)
poe lint                   # ruff check + format
poe test                   # Run pytest
poe typecheck              # Run ty
poe all                    # Run all checks

# Individual execution
uv run ruff check .
uv run ruff format .
uv run ty check src/
uv run pytest -v --tb=short
```

## Notes

- Manage API keys via environment variables (don't commit `.env`)
- Watch token consumption (especially long contexts)
- Implement retry logic for rate limits
