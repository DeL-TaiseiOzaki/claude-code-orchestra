# Claude Code Orchestra

Multi-agent orchestration framework: Claude Code (lead) + Codex CLI (planning/complex code) + Gemini CLI (1M context analysis/research/multimodal).

## Agent Roles

| Agent | Model | Role |
|-------|-------|------|
| **Claude Code** (Lead) | Opus 4.6 | Orchestration, user interaction, simple edits |
| **Codex CLI** | gpt-5.3-codex | Planning, design, complex code, debugging |
| **Gemini CLI** | gemini-3-pro | Codebase analysis (1M ctx), research, multimodal |
| **Subagents** (Opus) | Opus 4.6 | Code implementation, Codex/Gemini delegation |
| **Agent Teams** (Opus) | Opus 4.6 | Parallel work with inter-agent communication |

## Routing

```
Task received
  ├── Multimodal file (PDF/video/audio/image)? → Gemini CLI
  ├── Large-scale codebase analysis?           → Gemini CLI (1M context)
  ├── External research / survey?              → Gemini CLI (Google Search grounding)
  ├── Planning / design / complex code?        → Codex CLI
  └── Normal implementation?                   → Claude directly or subagent
```

- Codex delegation rules: @.claude/rules/codex-delegation.md
- Gemini delegation rules: @.claude/rules/gemini-delegation.md

## Context Budget

Claude Code: **200K tokens** (effective ~140-150K). Gemini CLI: **1M tokens**.

| Output Size | Method |
|-------------|--------|
| Short (~20 lines) | Direct call |
| Medium (20-50 lines) | Prefer subagent |
| Large (50+ lines) | Subagent → save to `.claude/docs/` |
| Full codebase analysis | **Gemini** (1M context) |
| External research | **Gemini** (Google Search grounding) |

When inter-agent communication is needed (not just results), use **Agent Teams** instead of subagents.

## Workflow

```
/startproject <feature>  →  Understand → Research & Design → Plan
    ↓ approval
/team-implement          →  Parallel implementation (Agent Teams)
    ↓ completion
/team-review             →  Parallel review (Security / Quality / Test)
```

1. **Gemini** analyzes codebase (1M ctx) + **Claude** gathers requirements from user
2. **Agent Teams**: Researcher (Gemini) ↔ Architect (Codex) collaborate in parallel
3. **Claude** synthesizes findings into plan → user approval
4. `/team-implement` — module-based parallel implementation
5. `/team-review` — security / quality / test parallel review

## Tech Stack

- **Python 3.11+** / **uv** (never use pip directly)
- **ruff** (lint + format) / **ty** (type check) / **pytest**
- `poe lint` / `poe test` / `poe all`
- Details: @.claude/rules/dev-environment.md

## Key Rules

- Coding principles: @.claude/rules/coding-principles.md
- Security: @.claude/rules/security.md
- Testing: @.claude/rules/testing.md

## Documentation Map

| Location | Content |
|----------|---------|
| `.claude/rules/` | Coding standards, delegation rules, security |
| `.claude/docs/DESIGN.md` | Architecture and design decisions |
| `.claude/docs/research/` | Research results from subagents |
| `.claude/docs/libraries/` | Library constraints and docs |
| `.claude/logs/cli-tools.jsonl` | Codex/Gemini I/O logs |

## Language Protocol

- **Thinking / code / documentation**: English
- **User communication**: Japanese
