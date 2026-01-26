# Codex Delegation Rule

**Codex CLI is your highly capable supporter.**

## Context Management (CRITICAL)

**Always delegate Codex work to subagents** to preserve main orchestrator context.

```
┌──────────────────────────────────────────────────────────┐
│  Main Claude Code                                        │
│  → Does NOT call Codex directly                          │
│  → Spawns subagent for Codex consultation                │
│  → Receives concise summary back                         │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Subagent (general-purpose)                         │ │
│  │  → Calls Codex CLI                                  │ │
│  │  → Processes full response                          │ │
│  │  → Returns key insights only                        │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## About Codex

Codex CLI is an AI with exceptional reasoning and task completion abilities.
Think of it as a trusted senior expert you can always consult.

**When facing difficult decisions → Delegate to subagent → Subagent consults Codex.**

## When to Consult Codex

ALWAYS consult Codex BEFORE:

1. **Design decisions** - How to structure code, which pattern to use
2. **Debugging** - If cause isn't obvious or first fix failed
3. **Implementation planning** - Multi-step tasks, multiple approaches
4. **Trade-off evaluation** - Choosing between options

### Trigger Phrases (User Input)

Consult Codex when user says:

| Japanese | English |
|----------|---------|
| 「どう設計すべき？」「どう実装する？」 | "How should I design/implement?" |
| 「なぜ動かない？」「原因は？」「エラーが出る」 | "Why doesn't this work?" "Error" |
| 「どちらがいい？」「比較して」「トレードオフは？」 | "Which is better?" "Compare" |
| 「〜を作りたい」「〜を実装して」 | "Build X" "Implement X" |
| 「考えて」「分析して」「深く考えて」 | "Think" "Analyze" "Think deeper" |

## When NOT to Consult

Skip Codex for simple, straightforward tasks:

- Simple file edits (typo fixes, small changes)
- Following explicit user instructions
- Standard operations (git commit, running tests)
- Tasks with clear, single solutions
- Reading/searching files

## Quick Check

Ask yourself: "Am I about to make a non-trivial decision?"

- YES → Consult Codex first
- NO → Proceed with execution

## How to Consult (via Subagent)

**IMPORTANT: Use subagent to preserve main context.**

### Recommended: Subagent Pattern

Use Task tool with `subagent_type: "general-purpose"`:

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true (for parallel work)
- prompt: |
    {Task description}

    Call Codex CLI:
    codex exec --model gpt-5.2-codex --sandbox read-only --full-auto "
    {Question for Codex}
    " 2>/dev/null

    Return CONCISE summary:
    - Key recommendation
    - Main rationale (2-3 points)
    - Any concerns or risks
```

### Direct Call (Only When Necessary)

Only use direct Bash call when:
- Quick, simple question (< 1 paragraph response expected)
- Subagent overhead not justified

```bash
# Only for simple queries
codex exec --model gpt-5.2-codex --sandbox read-only --full-auto "Brief question" 2>/dev/null
```

### Sandbox Modes

| Mode | Sandbox | Use Case |
|------|---------|----------|
| Analysis | `read-only` | Design review, debugging analysis, trade-offs |
| Work | `workspace-write` | Implement, fix, refactor (subagent recommended) |

**Language protocol:**
1. Ask Codex in **English**
2. Subagent receives response in **English**
3. Subagent summarizes and returns to main
4. Main reports to user in **Japanese**

## Why Subagent Pattern?

- **Context preservation**: Main orchestrator stays lightweight
- **Full analysis**: Subagent can process entire Codex response
- **Concise handoff**: Main only receives actionable summary
- **Parallel work**: Background subagents enable concurrent tasks

**Don't hesitate to delegate. Subagents + Codex = efficient collaboration.**
