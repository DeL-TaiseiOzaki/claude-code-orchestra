---
name: codex-system
description: |
  Delegate tasks to Codex CLI (System 2) for deep analysis, complex reasoning,
  or second opinions. Triggers on: architecture decisions, algorithm optimization,
  persistent bugs (2+ failed attempts), security review, performance analysis,
  multi-file refactoring, or explicit requests like "think deeper", "analyze this",
  "second opinion", "consult codex".
metadata:
  short-description: Claude Code ↔ Codex CLI System 2 collaboration
---

# Codex System — System 2 for Claude Code

Coordination system between Claude Code (System 1: Quick Response & Execution) and Codex CLI (System 2: Deep Thinking & Analysis).

## Delegation Conditions (Auto-Trigger)

Delegate to Codex when any of these conditions are met:

### 1. Explicit Request
- Keywords like `think deeper`, `analyze this`, `second opinion`
- Direct instructions like `consult codex`, `ask codex`

### 2. Complexity-Based
- Architecture decision required (new component design, dependency changes)
- Changes affecting 10+ files
- Complex algorithm design/optimization (O(n²) or higher)
- Deeply nested conditionals (3+ levels)

### 3. Failure-Based
- Same problem attempted 2+ times without resolution
- Tests failing repeatedly
- Root cause of error is unclear

### 4. Quality/Security
- Security-related changes (authentication, authorization, encryption)
- Performance-critical processing
- Production-impacting refactoring

## Execution Method

### Basic Format

```bash
codex exec \
  --model gpt-5-codex \
  --sandbox read-only \
  --full-auto \
  "{prompt}" 2>/dev/null
```

### Specifying Reasoning Effort

```bash
codex exec \
  --model gpt-5-codex \
  --config model_reasoning_effort="high" \
  --sandbox read-only \
  --full-auto \
  "{prompt}" 2>/dev/null
```

### Session Continuation

```bash
# Continue last session
codex exec resume --last "{follow_up_prompt}" 2>/dev/null

# Continue specific session
codex exec resume {SESSION_ID} "{follow_up_prompt}" 2>/dev/null
```

## Agent Types

Use Codex with these roles depending on task content:

| Agent | Purpose | reasoning_effort |
|-------|---------|------------------|
| Architect | Architecture design & review | high |
| Analyzer | Deep problem analysis & debugging | high |
| Optimizer | Performance & algorithm optimization | xhigh |
| Security | Security audit | xhigh |

## Prompt Construction

When delegating to Codex, include:

1. **Purpose**: What to achieve
2. **Context**: Related files, current state
3. **Constraints**: Rules to follow, available technologies
4. **Past Attempts** (for failure-based): What was tried, what failed

## Notes

- `2>/dev/null` suppresses thinking tokens (saves context)
- `--full-auto` required in CI/Claude Code environment
- `--skip-git-repo-check` only for non-Git directories
- Record session ID to enable continuation
