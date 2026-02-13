---
name: gemini-system
description: |
  PROACTIVELY consult Gemini CLI for external web research and multimodal
  data processing. Gemini excels at: Google Search grounding for latest
  information, video/audio/PDF analysis, and library/API documentation lookup.
  NOTE: Codebase analysis is handled by Claude directly (1M context).
  Explicit triggers: "research", "investigate", "analyze video/audio/PDF",
  "latest docs", "library research".
metadata:
  short-description: Claude Code ↔ Gemini CLI collaboration (external research & multimodal)
---

# Gemini System — External Research & Multimodal Specialist

**Gemini CLI is your specialist for external information and multimodal processing.**

> **詳細ルール**: `.claude/rules/gemini-delegation.md`

## Role (Opus 4.6)

> **重要**: Claude 自身が 1M トークンのコンテキストを持つため、コードベース分析は Claude が直接行う。
> Gemini の役割は「外部情報の取得」と「マルチモーダル処理」に特化した。

| Task | Agent |
|------|-------|
| **コードベース分析** | **Claude 直接** (1M context) |
| **外部ライブラリ調査** | Gemini (Google Search) |
| **最新ドキュメント検索** | Gemini (Google Search) |
| **マルチモーダル (PDF/動画/音声)** | Gemini |
| **設計判断** | Codex |
| **デバッグ** | Codex |

## Context Management

| 状況 | 方法 |
|------|------|
| 短い質問・短い回答 | 直接呼び出しOK |
| ライブラリ調査 | サブエージェント経由（出力が大きい場合） |
| マルチモーダル処理 | サブエージェント経由 |
| Agent Teams 内での調査 | Teammate が直接呼び出し |

## When to Consult (MUST)

| Situation | Trigger Examples |
|-----------|------------------|
| **External research** | 「調べて」「リサーチ」 / "Research" "Investigate" |
| **Library docs** | 「ライブラリ」「ドキュメント」 / "Library" "Docs" |
| **Latest information** | 「最新の〜」「2026年の〜」 / "Latest" "Current" |
| **Multimodal** | 「PDF」「動画」「音声」 / "PDF" "Video" "Audio" |

## When NOT to Consult

- **コードベース分析** → Claude が 1M コンテキストで直接読む
- Design decisions → Codex
- Debugging → Codex
- Code implementation → Claude
- Simple file operations → Claude

## How to Consult

### In Agent Teams (Preferred for /startproject)

Researcher Teammate が Gemini を直接呼び出し、Architect Teammate と双方向通信する。

```
/startproject 内の Phase 2 で、Researcher Teammate として Gemini を活用:
- 外部情報の収集 → Gemini に調査依頼
- Architect からの追加調査依頼に対応
- 調査結果を .claude/docs/research/ に保存
```

### Subagent Pattern (Standalone research)

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true (optional, for parallel work)
- prompt: |
    Research: {topic}

    gemini -p "{research question}" 2>/dev/null

    Save full output to: .claude/docs/research/{topic}.md
    Return CONCISE summary (5-7 bullet points).
```

### Direct Call (Short Questions Only)

```bash
gemini -p "Brief question" 2>/dev/null
```

### CLI Options Reference

```bash
# External research (primary use case)
gemini -p "{question}" 2>/dev/null

# Multimodal (PDF/video/audio)
gemini -p "{prompt}" < /path/to/file.pdf 2>/dev/null

# JSON output
gemini -p "{question}" --output-format json 2>/dev/null
```

> **Note**: `--include-directories .` is no longer needed for codebase analysis — Claude handles this directly with 1M context.

## Language Protocol

1. Ask Gemini in **English**
2. Receive response in **English**
3. Synthesize and apply findings
4. Report to user in **Japanese**

## Output Location

Save Gemini research results to:
```
.claude/docs/research/{topic}.md
.claude/docs/libraries/{library}.md
```

This allows Claude and Codex to reference the research later.

## Task Templates

### Library Research

```bash
gemini -p "Research best practices for {library} in Python 2026.
Include:
- Installation and setup
- Common patterns and anti-patterns
- Known limitations and constraints
- Performance considerations
- Security concerns
- Code examples" 2>/dev/null
```

### Latest Documentation Lookup

```bash
gemini -p "Find the latest documentation for {library/API}.
Include:
- Current stable version
- Breaking changes from previous version
- New features
- Migration guide if applicable" 2>/dev/null
```

### Multimodal Analysis

```bash
# Video
gemini -p "Analyze video: main concepts, key points, timestamps" < tutorial.mp4 2>/dev/null

# PDF
gemini -p "Extract: API specs, examples, constraints" < api-docs.pdf 2>/dev/null

# Audio
gemini -p "Transcribe and summarize: decisions, action items" < meeting.mp3 2>/dev/null
```

See also: `references/lib-research-task.md`

## Integration with Codex

| Workflow | Steps |
|----------|-------|
| **New feature** | Gemini research → Codex design review |
| **Library choice** | Gemini comparison → Codex decision |
| **/startproject** | Agent Teams: Researcher (Gemini) ↔ Architect (Codex) |

## Why Gemini?

- **Google Search**: Latest information, official docs, best practices
- **Multimodal**: Native PDF/video/audio processing
- **Web grounding**: Verified facts with source URLs
- **Shared context**: Results saved for Claude/Codex to reference
