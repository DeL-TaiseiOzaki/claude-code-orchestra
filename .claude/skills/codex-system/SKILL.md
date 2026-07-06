---
name: codex-system
description: |
  Codex CLI handles planning, design, and complex code implementation.
  Use for: architecture design, implementation planning, complex algorithms,
  debugging (root cause analysis), trade-off evaluation, code review.
  External research is NOT Codex's job — use general-purpose subagent (Opus) instead.
  Explicit triggers: "plan", "design", "architecture", "think deeper",
  "analyze", "debug", "complex", "optimize".
metadata:
  short-description: Codex CLI — planning, design, and complex implementation
---

# Codex System — Planning, Design & Complex Implementation

**Codex CLI handles planning, design, and complex code implementation.**

> **Preflight (SSOT):** Update CLIs before each session — `claude update && npm install -g @openai/codex@latest`. Releases drift frequently (model names, flags, sandbox semantics). Other skills reference this line instead of repeating it.
> **Delegation policy (when to delegate)**: `.claude/rules/codex-delegation.md`

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

## When to Delegate

Delegation policy — when to consult, when NOT to, and trigger criteria — lives in `.claude/rules/codex-delegation.md` (SSOT). This skill covers *how* to consult.

## How to Consult

### Subagent Pattern (Recommended)

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true (optional)
- prompt: |
    Consult Codex about: {topic}

    codex exec --model "${CODEX_MODEL:-gpt-5.5}" --sandbox read-only "
    Objective: {single-sentence objective}
    Constraints:
    - {constraint 1}
    Relevant files:
    - {file paths}
    Acceptance checks:
    - {commands}
    Output format:
    ## Analysis
    ## Recommendation
    ## Implementation Plan
    ## Risks
    ## Next Steps
    " 2>/dev/null

    Return CONCISE summary (key recommendation + rationale).
```

### Direct Call (short questions, responses up to ~50 lines)

```bash
codex exec --model "${CODEX_MODEL:-gpt-5.5}" --sandbox read-only "Objective: {brief question}" 2>/dev/null
```

### Having Codex Implement Code

```bash
codex exec --model "${CODEX_MODEL:-gpt-5.5}" --sandbox workspace-write "
Objective: Implement {detailed implementation task}
Constraints:
- Follow existing project conventions
- Keep diffs minimal
Relevant files:
- {file paths}
Acceptance checks:
- {commands}
Output format:
## Changes Made
## Validation
## Remaining Risks
" 2>/dev/null
```

### Sandbox Modes

| Mode | Sandbox | Use Case |
|------|---------|----------|
| Analysis | `read-only` | Design review, debugging, trade-off analysis |
| Implementation | `workspace-write` | Implementation, fixes, refactoring |

## Task Templates

### Implementation Planning

```bash
codex exec --model "${CODEX_MODEL:-gpt-5.5}" --sandbox read-only "
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
codex exec --model "${CODEX_MODEL:-gpt-5.5}" --sandbox read-only "
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
codex exec --model "${CODEX_MODEL:-gpt-5.5}" --sandbox read-only "
Debug this issue:

Error: {error message}
Code: {relevant code}
Context: {what was happening}

Analyze root cause and suggest fixes.
" 2>/dev/null
```

## Language Protocol

See `.claude/rules/language.md` (SSOT): ask Codex in English, receive in English, report to the user per that rule.

## Codex Plugin Commands (codex-plugin-cc)

When the `openai/codex-plugin-cc` plugin is installed, these slash commands are available:

> Plugin source: https://github.com/openai/codex-plugin-cc

### Code Review

```bash
/codex:review                    # Review current uncommitted changes
/codex:review --base main        # Review branch diff against main
/codex:review --background       # Run review in background
/codex:review --wait             # Synchronous: block until review finishes
```

### Adversarial Review

```bash
/codex:adversarial-review                           # Challenge design decisions
/codex:adversarial-review --base main               # Branch-level adversarial review
/codex:adversarial-review --background look for race conditions
```

### Task Delegation (Rescue)

```bash
/codex:rescue investigate why the tests started failing
/codex:rescue fix the failing test with the smallest safe patch
/codex:rescue --resume apply the top fix from the last run
/codex:rescue --model gpt-5.5-mini --effort medium investigate flaky test
/codex:rescue --background investigate the regression
```

### Job Management

```bash
/codex:status                    # Check progress of background jobs
/codex:result                    # Show finished job output
/codex:cancel                    # Cancel active background job
```

### Setup

```bash
/codex:setup                     # Check if Codex is installed and authenticated
/codex:setup --enable-review-gate   # Enable auto-review gate (use with caution)
/codex:setup --disable-review-gate  # Disable review gate
```

### When to Use Plugin vs Direct CLI

| Scenario | Use |
|----------|-----|
| Pre-ship code review | `/codex:review` |
| Challenge design | `/codex:adversarial-review` |
| Delegate investigation/fix | `/codex:rescue` |
| Background work + tracking | Plugin `--background` |
| Ad-hoc design question | `codex exec` (direct) |
| Implementation in sandbox | `codex exec --sandbox workspace-write` |
| Subagent delegation | `codex exec` via general-purpose |

## Why Codex?

- **Deep reasoning**: Complex analysis and problem-solving
- **Planning expertise**: Architecture and implementation strategies
- **Code mastery**: Complex algorithms, optimization, debugging

## References

Detailed templates and patterns in `references/`:

- [agent-prompts.md](references/agent-prompts.md) — Prompt templates for specialized review agents (Architect, etc.)
- [code-review-task.md](references/code-review-task.md) — Prompt template for delegating code review to Codex
- [delegation-patterns.md](references/delegation-patterns.md) — Delegation decision flowchart and detailed patterns
- [refactoring-task.md](references/refactoring-task.md) — Prompt template for delegating refactoring to Codex
- [troubleshooting.md](references/troubleshooting.md) — Codex CLI troubleshooting (installation, auth, common errors)
