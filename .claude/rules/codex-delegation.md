# Codex Delegation Rule

**Codex CLI handles planning, design, and complex code implementation.**

## Two Roles of Codex

### 1. Planning & Design

- Architecture design, module structure
- Implementation planning (step decomposition, dependency ordering)
- Trade-off evaluation, technology selection
- Code review (quality and correctness analysis)

### 2. Complex Code Implementation

- Complex algorithms, optimization
- Debugging with unknown root causes
- Advanced refactoring
- Multi-step implementation tasks

## Delegation Decision

Default to Codex-first delegation for development tasks.

Consult Codex when **any** of these apply (recommended default):

- Design/architecture decisions are involved.
- Change spans 2+ files with behavior impact.
- Root cause is unclear.
- User requests comparison/trade-off analysis.
- You need a step-by-step implementation plan.
- You are unsure and want a safe implementation direction.

Skip Codex only for obvious one-file tiny edits.

## Prompt Contract (Always Include)

1. Objective (single sentence)
2. Constraints (style, limits, forbidden approaches)
3. Relevant files (explicit paths)
4. Acceptance checks (commands)
5. Output format (structured markdown sections)

Detailed templates: `@.claude/docs/CODEX_HANDOFF_PLAYBOOK.md`

## How to Consult

### Subagent Pattern (Recommended)

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true (for parallel work)
- prompt: |
    Consult Codex about: {topic}

    codex exec --model gpt-5.4 --sandbox read-only --full-auto "
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

### Direct Call (Short questions only)

```bash
codex exec --model gpt-5.4 --sandbox read-only --full-auto "Objective: {brief question}" 2>/dev/null
```

### Having Codex Implement Code

```bash
codex exec --model gpt-5.4 --sandbox workspace-write --full-auto "
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


## Codex Plugin for Claude Code (codex-plugin-cc)

The `openai/codex-plugin-cc` plugin provides structured Codex workflows directly as Claude Code slash commands.

### Plugin vs Direct CLI

| Use Case | Recommended Method | Why |
|----------|-------------------|-----|
| Code review | `/codex:review` | Structured review with background support |
| Adversarial/design review | `/codex:adversarial-review` | Steerable challenge review |
| Task delegation | `/codex:rescue` | Background jobs with status tracking |
| Job management | `/codex:status`, `/codex:result`, `/codex:cancel` | Built-in job lifecycle |
| Planning & design | `codex exec --sandbox read-only` | Ad-hoc queries with prompt control |
| Complex implementation | `codex exec --sandbox workspace-write` | Full sandbox control |

### Plugin Commands

```bash
# Code review (current changes or branch diff)
/codex:review
/codex:review --base main
/codex:review --background

# Adversarial review (challenge design decisions)
/codex:adversarial-review
/codex:adversarial-review --background look for race conditions

# Delegate a task to Codex
/codex:rescue investigate why the tests started failing
/codex:rescue --model gpt-5.4-mini --effort medium investigate the flaky test
/codex:rescue --background investigate the regression

# Job management
/codex:status
/codex:result
/codex:cancel
```

### When to Prefer Plugin

- **Code review before shipping** → `/codex:review` or `/codex:adversarial-review`
- **Delegating investigation/fix** → `/codex:rescue`
- **Background work with status tracking** → Plugin commands with `--background`

### When to Prefer Direct CLI

- **Ad-hoc design questions** → `codex exec` with custom prompt
- **Implementation with sandbox control** → `codex exec --sandbox workspace-write`
- **Subagent pattern** → `codex exec` via general-purpose subagent

## Language Protocol

1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on advice
4. Report to user in **English**
