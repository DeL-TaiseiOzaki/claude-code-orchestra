---
name: codex-system
description: |
  Codex CLI handles planning, design, and complex code implementation.
  Use for: architecture design, implementation planning, complex algorithms,
  debugging (root cause analysis), trade-off evaluation, code review.
  External research is NOT Codex's job — use Gemini CLI (Google Search grounding) instead.
  Explicit triggers: "plan", "design", "architecture", "think deeper",
  "analyze", "debug", "complex", "optimize".
metadata:
  short-description: Codex CLI — planning, design, and complex implementation
---

# Codex System — Planning, Design & Complex Implementation

**Codex CLI handles planning, design, and complex code implementation.**

> **Detailed rules**: `.claude/rules/codex-delegation.md`

## Two Roles of Codex

### 1. Planning & Design

- Architecture design, module composition
- Implementation plan creation (step breakdown, dependency ordering)
- Trade-off evaluation, technology selection
- Code review (quality and correctness analysis)

### 2. Complex Implementation

- Complex algorithms, optimization
- Debugging with unknown root causes
- Advanced refactoring
- Multi-step implementation tasks

## When to Consult (MUST)

| Situation | Trigger Examples |
|-----------|------------------|
| **Planning** | "Create a plan" "Architecture" |
| **Design decisions** | "How to design?" |
| **Complex implementation** | "How to implement?" "How to build?" |
| **Debugging** | "Why doesn't this work?" "Error" "Debug" |
| **Trade-off analysis** | "Which is better?" "Compare" |
| **Refactoring** | "Refactor" "Simplify" |
| **Code review** | "Review" "Check" |

## When NOT to Consult

- Simple file edits, typo fixes
- Tasks that simply follow explicit user instructions
- git commit, test execution, lint
- **Codebase analysis** → Gemini CLI (1M context for large-scale analysis)
- **External information retrieval** → Gemini CLI (Google Search grounding)
- **Multimodal processing** → Gemini CLI (PDF/video/audio/images)

## How to Consult

### Subagent Pattern (Recommended)

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true (optional)
- prompt: |
    Consult Codex about: {topic}

    codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
    {question for Codex}
    " 2>/dev/null

    Return CONCISE summary (key recommendation + rationale).
```

### Direct Call (responses up to ~50 lines)

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "Brief question" 2>/dev/null
```

### Having Codex Implement Code

```bash
codex exec --model gpt-5.3-codex --sandbox workspace-write --full-auto "
Implement: {task description}
Requirements: {requirements}
Files: {file paths}
" 2>/dev/null
```

### Sandbox Modes

| Mode | Use Case |
|------|----------|
| `read-only` | Design, review, debug analysis |
| `workspace-write` | Implementation, fixes, refactoring |

## Task Templates

### Implementation Planning

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
Create an implementation plan for: {feature}

Context: {relevant architecture/code}

Provide:
1. Step-by-step plan with dependencies
2. Files to create/modify
3. Key design decisions
4. Risks and mitigations
" 2>/dev/null
```

### Design Review

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
Review this design approach for: {feature}

Context: {relevant code or architecture}

Evaluate:
1. Is this approach sound?
2. Alternative approaches?
3. Potential issues?
4. Recommendations?
" 2>/dev/null
```

### Debug Analysis

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
Debug this issue:

Error: {error message}
Code: {relevant code}
Context: {what was happening}

Analyze root cause and suggest fixes.
" 2>/dev/null
```

## Language Protocol

1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on advice
4. Report to user in **the user's language**

## Why Codex?

- **Deep reasoning**: Complex analysis and problem-solving
- **Planning expertise**: Architecture and implementation strategies
- **Code mastery**: Complex algorithms, optimization, debugging
- **Consistency**: Same project context via `context-loader` skill
