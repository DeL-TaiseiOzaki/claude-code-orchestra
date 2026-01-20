---
name: codex-system
description: |
  PROACTIVELY consult Codex CLI, your highly capable supporter with exceptional
  reasoning and task completion abilities. Codex is a trusted expert you should
  ALWAYS consult BEFORE making decisions on: design choices, implementation
  approaches, debugging strategies, refactoring plans, or any non-trivial problem.
  When uncertain, consult Codex. Don't hesitate - Codex provides better analysis.
  Explicit triggers: "think deeper", "analyze", "second opinion", "consult codex".
metadata:
  short-description: Claude Code ↔ Codex CLI collaboration
---

# Codex System — Your Trusted Supporter

**Codex CLI is your highly capable supporter with exceptional reasoning abilities.**

Codex CLI is an AI that excels at:
- Deep analysis and complex reasoning
- Thorough investigation and problem-solving
- Providing well-considered recommendations

**Think of Codex as a trusted senior expert you can always consult.**

## MUST Consult (Required)

Always consult Codex in these situations:

### 1. Before Any Design Decision
- "How should I structure this?"
- "Which approach is better?"
- "What's the best way to implement X?"
- Any architectural choice → **ASK CODEX FIRST**

### 2. Before Complex Implementation
- New feature design
- Multi-file changes (3+ files)
- Algorithm design
- API design
- Database schema changes

### 3. When Debugging
- Error cause is not immediately obvious
- First fix attempt didn't work → **STOP and consult Codex**
- Unexpected behavior

### 4. When Planning
- Task requires multiple steps
- Multiple approaches are possible
- Trade-offs need to be evaluated

### 5. Explicit Triggers
- User says: "think deeper", "analyze", "second opinion", "consult codex"
- User says: "考えて", "分析して", "深く考えて", "codexに聞いて"

## SHOULD Consult (Recommended)

Strongly consider consulting for:

- Security-related code
- Performance optimization
- Refactoring existing code
- Code review / quality check
- Library selection
- Error handling strategy

## NO Need to Consult

Skip Codex for simple, straightforward tasks:

- Simple file edits (typo fixes, small changes)
- Following explicit user instructions
- Standard operations (git commit, running tests, linting)
- Tasks with clear, single solutions
- Reading/searching files
- Trivial code changes where the solution is obvious

## Quick Rule

**If you pause to think "hmm, how should I do this?" → CONSULT CODEX**

Codex will provide better analysis than you can do alone. Don't hesitate to ask.

## Execution Method

Choose the appropriate mode based on what you need from Codex:

### Analysis Only (Read-Only)

Use when you need Codex to analyze, review, or advise:

```bash
codex exec \
  --model gpt-5.2-codex \
  --sandbox read-only \
  --full-auto \
  "Analyze: {question in English}" 2>/dev/null
```

**Use cases:** Design review, debugging analysis, trade-off evaluation, architecture advice

### Delegate Work (Can Write Files)

Use when you want Codex to actually implement or fix something:

```bash
codex exec \
  --model gpt-5.2-codex \
  --sandbox workspace-write \
  --full-auto \
  "Task: {task description in English}" 2>/dev/null
```

**Use cases:** Implement feature, fix bug, refactor code, write tests

### Decision Guide

| Need | Mode | Sandbox |
|------|------|---------|
| "How should I design this?" | Analysis | read-only |
| "What's causing this bug?" | Analysis | read-only |
| "Implement this feature" | Work | workspace-write |
| "Fix this bug" | Work | workspace-write |
| "Refactor this code" | Work | workspace-write |

### Language Protocol

1. **Ask Codex in English** - Write prompts in English
2. **Receive response in English** - Codex replies in English
3. **Execute or verify** - Work based on Codex's advice, or verify Codex's work
4. **Report to user in Japanese** - Summarize results for the user

### Session Continuation

```bash
# Continue last session
codex exec resume --last "{follow_up_prompt}" 2>/dev/null

# Continue specific session
codex exec resume {SESSION_ID} "{follow_up_prompt}" 2>/dev/null
```

## Prompt Construction

When consulting Codex, include:

1. **Purpose**: What to achieve
2. **Context**: Related files, current state
3. **Constraints**: Rules to follow, available technologies
4. **Past Attempts** (for debugging): What was tried, what failed

## Notes

- `2>/dev/null` suppresses thinking tokens (saves context)
- `--full-auto` required in CI/Claude Code environment
- `--skip-git-repo-check` only for non-Git directories
- Record session ID to enable continuation
