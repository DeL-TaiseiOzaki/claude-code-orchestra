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

> **Full details:** See "Codex CLI Integration" section in AGENTS.md

## Quick Reference

### When to Consult

| Situation | Action |
|-----------|--------|
| Design decisions | **MUST** consult |
| Debugging (cause unclear) | **MUST** consult |
| Multiple approaches | **MUST** consult |
| Complex implementation | **MUST** consult |
| Simple edits, explicit instructions | Skip |

### How to Consult (Background Execution)

**Always use `run_in_background: true`:**

```bash
# Analysis
codex exec --model gpt-5.2-codex --sandbox read-only --full-auto "Analyze: {question}" 2>/dev/null

# Work delegation
codex exec --model gpt-5.2-codex --sandbox workspace-write --full-auto "Task: {description}" 2>/dev/null
```

### Workflow

1. **Start Codex** (background) → Get task_id
2. **Continue your work** → Don't wait
3. **Retrieve results** → Use `TaskOutput` tool

### Language Protocol

1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on advice
4. Report to user in **Japanese**
