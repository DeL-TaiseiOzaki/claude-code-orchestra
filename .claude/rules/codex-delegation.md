# Codex Delegation Rule

**Codex CLI is your highly capable supporter.**

## About Codex

Codex CLI is an AI with exceptional reasoning and task completion abilities.
Think of it as a trusted senior expert you can always consult.

**When facing difficult decisions → Consult Codex first, then execute.**

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

## How to Consult

**IMPORTANT: Always run Codex in background to enable parallel work.**

### Step 1: Start Codex (Background)

Use Bash tool with `run_in_background: true`:

```bash
# Analysis (read-only)
codex exec --model gpt-5.2-codex --sandbox read-only --full-auto "Analyze: {question}" 2>/dev/null

# Work delegation (can write)
codex exec --model gpt-5.2-codex --sandbox workspace-write --full-auto "Task: {description}" 2>/dev/null
```

### Step 2: Continue Your Work

While Codex is processing, you can:
- Work on other files
- Run tests
- Do independent tasks

### Step 3: Check Results

Use `TaskOutput` tool to retrieve Codex's response when needed.

### When to Use Which Mode

| Mode | Sandbox | Use Case |
|------|---------|----------|
| Analysis | `read-only` | Design review, debugging analysis, trade-offs |
| Work | `workspace-write` | Implement, fix, refactor |

**Language protocol:**
1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on Codex's advice (or let Codex execute)
4. Report to user in **Japanese**

## Why Consult Codex?

- Codex excels at deep analysis and complex reasoning
- Codex provides well-considered recommendations
- Consulting Codex leads to better outcomes than deciding alone

**Don't hesitate to ask. Codex is your reliable partner.**
