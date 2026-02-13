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

# Codex System — Deep Reasoning Partner

**Codex CLI (gpt-5.3-codex) is your highly capable supporter for deep reasoning tasks.**

> **詳細ルール**: `.claude/rules/codex-delegation.md`

## Context Management (Opus 4.6)

Claude の 1M コンテキストにより、直接呼び出しの許容範囲が拡大した。ただし大きな出力はサブエージェント経由を推奨。

| 状況 | 方法 |
|------|------|
| 短い質問（〜50行回答） | 直接呼び出しOK |
| 詳細な設計相談 | サブエージェント経由（推奨） |
| デバッグ分析 | サブエージェント経由（推奨） |
| Agent Teams 内での相談 | Teammate が直接呼び出し |

## When to Consult (MUST)

| Situation | Trigger Examples |
|-----------|------------------|
| **Design decisions** | 「どう設計？」「アーキテクチャ」 / "How to design?" |
| **Debugging** | 「なぜ動かない？」「エラー」 / "Debug" "Error" |
| **Trade-off analysis** | 「どちらがいい？」「比較して」 / "Compare" "Which?" |
| **Complex implementation** | 「実装方法」「どう作る？」 / "How to implement?" |
| **Refactoring** | 「リファクタ」「シンプルに」 / "Refactor" "Simplify" |
| **Code review** | 「レビューして」「確認して」 / "Review" "Check" |

## When NOT to Consult

- Simple file edits, typo fixes
- Following explicit user instructions
- git commit, running tests, linting
- Tasks with obvious single solutions
- **Codebase analysis** → Claude does this directly (1M context)

## How to Consult

### In Agent Teams (Preferred for /startproject)

Architect Teammate が Codex を直接呼び出し、Researcher Teammate と双方向通信する。

```
/startproject 内の Phase 2 で、Architect Teammate として Codex を活用:
- 設計検討 → Codex に相談
- Researcher からの調査結果を受けて設計を修正
- 設計決定を .claude/docs/DESIGN.md に記録
```

### Subagent Pattern (Standalone consultation)

**Use Task tool with `subagent_type='general-purpose'` for larger outputs.**

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true (optional, for parallel work)
- prompt: |
    Consult Codex about: {topic}

    codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
    {question for Codex}
    " 2>/dev/null

    Return CONCISE summary (key recommendation + rationale).
```

### Direct Call (Up to ~50 lines response)

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "Brief question" 2>/dev/null
```

### Sandbox Modes

| Mode | Use Case |
|------|----------|
| `read-only` | Analysis, review, debugging advice |
| `workspace-write` | Implementation, refactoring, fixes |

## Language Protocol

1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on advice (or let Codex execute)
4. Report to user in **Japanese**

## Task Templates

### Design Review

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
Review this design approach for: {feature}

Context:
{relevant code or architecture}

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

### Code Review

See: `references/code-review-task.md`

### Refactoring

See: `references/refactoring-task.md`

## Integration with Gemini

| Task | Use |
|------|-----|
| Need external research first | Gemini → then Codex |
| Design decision | Codex directly |
| Library comparison | Gemini research → Codex decision |
| /startproject | Agent Teams: Researcher (Gemini) ↔ Architect (Codex) |

## Why Codex?

- **Deep reasoning**: Complex analysis and problem-solving
- **Code expertise**: Implementation strategies and patterns
- **Consistency**: Same project context via `context-loader` skill
- **Parallel work**: Background execution or Agent Teams teammate
