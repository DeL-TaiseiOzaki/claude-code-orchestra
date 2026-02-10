# Codex Delegation Rule

**Codex CLI is your indispensable partner. Consult proactively and frequently.**

> **原則**: 迷ったらCodexに聞く。聞かずに失敗するより、聞いて正しく進む方がはるかに良い。
> Codexへの相談コストは低い。相談しないことによる手戻りコストは高い。

## Context Management (Opus 4.6)

Claude の 1M コンテキストにより、以前より直接呼び出しの許容範囲が拡大した。ただし大きな出力の場合はサブエージェント経由を推奨。

| 状況 | 推奨方法 |
|------|----------|
| 短い質問・短い回答（〜50行） | 直接呼び出しOK |
| 詳細な設計相談 | サブエージェント経由 |
| デバッグ分析 | サブエージェント経由 |
| Agent Teams 内での相談 | Teammate が直接呼び出し |

## About Codex

Codex CLI is an AI with exceptional reasoning and task completion abilities.
Think of it as a trusted senior expert whose opinion you should ALWAYS seek.

**Default behavior: Consult Codex. Skip ONLY when explicitly unnecessary.**

## When to Consult Codex

ALWAYS consult Codex BEFORE:

1. **Design decisions** - How to structure code, which pattern to use
2. **Debugging** - ANY error, not just complex ones. Codex catches root causes faster
3. **Implementation planning** - Multi-step tasks, multiple approaches
4. **Trade-off evaluation** - Choosing between options
5. **Code review** - Quality and correctness analysis
6. **New file creation** - Codex validates structure before you write
7. **Refactoring** - Codex identifies better patterns and hidden dependencies
8. **Performance concerns** - Codex spots bottlenecks and suggests optimizations
9. **Security-sensitive code** - Auth, input validation, crypto, permissions
10. **Uncertainty** - If you're not 100% confident, ask Codex

### Automatic Triggers (Hooks detect these)

| Situation | Hook | Action |
|-----------|------|--------|
| User prompt with design/debug keywords | `agent-router.py` | Codex Required |
| Write/Edit to design-related file | `check-codex-before-write.py` | Codex Review Required |
| Test/build failure | `post-test-analysis.py` | Codex Debug Required |
| Any Bash error | `error-to-codex.py` | codex-debugger Required |
| Plan created | `check-codex-after-plan.py` | Codex Validation |
| 2+ files / 50+ lines modified | `post-implementation-review.py` | Codex Review Required |

### Proactive Triggers (Consult WITHOUT being asked)

| Situation | Why |
|-----------|-----|
| About to create a new module/class | Codex validates architecture |
| About to modify shared/core code | Codex checks for ripple effects |
| Writing error handling / retry logic | Codex reviews edge cases |
| Choosing between 2+ approaches | Codex evaluates trade-offs |
| Implementing async / concurrent code | Codex catches race conditions |
| After 2+ failed attempts at fixing something | Codex finds what you're missing |

### Trigger Phrases (User Input)

| Japanese | English |
|----------|---------|
| 「どう設計すべき？」「どう実装する？」 | "How should I design/implement?" |
| 「なぜ動かない？」「原因は？」「エラーが出る」 | "Why doesn't this work?" "Error" |
| 「どちらがいい？」「比較して」「トレードオフは？」 | "Which is better?" "Compare" |
| 「考えて」「分析して」「深く考えて」 | "Think" "Analyze" "Think deeper" |
| 「どうすべき？」「ベストプラクティス」「パターン」 | "What should I?" "Best practice" "Pattern" |
| 「不安」「自信がない」「わからない」 | "Not sure" "Uncertain" "Unsure" |

## When NOT to Consult

**ONLY** skip Codex for these truly trivial cases:

- Single-line typo fixes
- Adding/removing a single import
- Updating a version number
- Running git status/log/diff
- Reading/searching files
- **Codebase analysis** → Claude does this directly (1M context)

> If the task takes more than 30 seconds of thought, consult Codex.

## How to Consult

### In Agent Teams (Preferred for /startproject)

Architect Teammate が Codex を直接呼び出し、Researcher Teammate と双方向通信する。

### Subagent Pattern

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true (for parallel work)
- prompt: |
    Consult Codex about: {topic}

    codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
    {question for Codex}
    " 2>/dev/null

    Return CONCISE summary (key recommendation + rationale).
```

### Direct Call (Short Questions, up to ~50 lines response)

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "Brief question" 2>/dev/null
```

### Sandbox Modes

| Mode | Sandbox | Use Case |
|------|---------|----------|
| Analysis | `read-only` | Design review, debugging, trade-offs |
| Work | `workspace-write` | Implement, fix, refactor |

## Language Protocol

1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on advice
4. Report to user in **Japanese**
