# Project Overview

LLM/Agent Development Project

## Language Settings

- **Thinking/Reasoning**: English
- **Code**: English (variable names, function names, comments, docstrings)
- **User Communication**: Japanese

---

## Codex CLI Integration (CRITICAL)

**Codex CLI is your highly capable supporter. Consult it proactively.**

### When You MUST Consult Codex

Run `codex exec` when you encounter these situations:

| User Says (Japanese) | User Says (English) | Action |
|---------------------|---------------------|--------|
| 「どう設計すべき？」「どう実装する？」 | "How should I design/implement this?" | Consult Codex |
| 「なぜ動かない？」「原因は？」 | "Why doesn't this work?" | Consult Codex |
| 「どちらがいい？」「比較して」 | "Which is better?" "Compare these" | Consult Codex |
| 「〜を作りたい」「〜を実装して」 | "I want to build X" "Implement X" | Consult Codex for design first |
| 「考えて」「分析して」「深く考えて」 | "Think about this" "Analyze" | Consult Codex |

### How to Consult (Background Execution)

**Always run Codex in background for parallel work:**

```bash
# Analysis (read-only) - run with run_in_background: true
codex exec --model gpt-5.2-codex --sandbox read-only --full-auto "Analyze: {question}" 2>/dev/null

# Work delegation (can write) - run with run_in_background: true
codex exec --model gpt-5.2-codex --sandbox workspace-write --full-auto "Task: {description}" 2>/dev/null
```

**Workflow:**
1. Start Codex in background → Get task_id
2. Continue your own work → Don't wait
3. Retrieve results with `TaskOutput` when needed

**Language protocol:**
1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on Codex's advice (or let Codex execute)
4. Report to user in **Japanese**

### When NOT to Consult

- Simple file edits, typo fixes
- Following explicit user instructions
- git commit, running tests, linting
- Tasks with obvious single solutions

---

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
| **refactorer** | Refactoring | "simplify this", "clean up" |

### Skills (Use Proactively)

**IMPORTANT: Use these skills proactively. Don't wait for explicit user request.**

| Skill | When to Use | How to Invoke |
|-------|-------------|---------------|
| **codex-system** | **ALWAYS** before design decisions, debugging, planning, trade-off evaluation | `/codex-system` or run `codex exec ...` |
| **design-tracker** | When design/architecture decisions are made in conversation | `/design-tracker` |

> **Note:** Codex System details are in the "Codex CLI Integration" section above.

### Commands (Explicit Invocation)

Invoke with `/command`:

| Command | Purpose |
|---------|---------|
| `/init` | Analyze project & update AGENTS.md |
| `/plan <feature>` | Create implementation plan |
| `/tdd <feature>` | Test-driven development workflow |
| `/research-lib <library>` | Research library & create docs |
| `/simplify <path>` | Simplify/refactor specified code |
| `/update-design` | Update design docs from conversation |
| `/update-lib-docs` | Update library documentation |

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
.claude/                   # Claude Code settings & knowledge
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

.codex/                    # Codex CLI settings
└── skills -> ../.agent/skills  # Shared skills

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
