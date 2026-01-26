# Project Overview

LLM/Agent Development Project

---

## Multi-Agent System (CRITICAL)

```
┌─────────────────────────────────────────────────────────────┐
│           Claude Code (Orchestrator)                        │
│           → コンテキスト節約が最優先                         │
│           → Codex/Gemini は直接呼ばない                      │
│                      ↓                                      │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              Subagent (general-purpose)                │ │
│  │              → Codex/Gemini を代わりに呼び出す          │ │
│  │              → 結果を要約してメインに返す               │ │
│  │                                                        │ │
│  │   ┌──────────────┐        ┌──────────────┐            │ │
│  │   │  Codex CLI   │        │  Gemini CLI  │            │ │
│  │   │  設計・推論  │        │  リサーチ    │            │ │
│  │   └──────────────┘        └──────────────┘            │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Context Management (CRITICAL)

**メインオーケストレーターのコンテキストを節約する。**

| やること | やらないこと |
|----------|--------------|
| サブエージェント経由でCodex呼び出し | メインから直接Codex呼び出し |
| サブエージェント経由でGemini呼び出し | メインから直接Gemini呼び出し |
| 要約を受け取る | 生の出力をメインに読み込む |
| 詳細はファイルに保存 | 大量のテキストをコンテキストに保持 |

```
# Good: サブエージェント経由
Task(subagent_type="general-purpose", prompt="Codexに設計を相談して要約を返して")

# Bad: 直接呼び出し
Bash("codex exec ...")  # メインのコンテキストを消費
```

### Codex CLI — 設計・デバッグ・深い推論 (via Subagent)

**MUST consult before**: 設計判断、デバッグ、トレードオフ分析、リファクタリング

| Trigger (日本語) | Trigger (English) |
|------------------|-------------------|
| 「どう設計？」「実装方法は？」 | "How to design/implement?" |
| 「なぜ動かない？」「エラー」 | "Debug" "Error" "Not working" |
| 「どちらがいい？」「比較して」 | "Compare" "Which is better?" |
| 「考えて」「深く分析」 | "Think" "Analyze deeply" |

```
# サブエージェント経由で呼び出し
Task(subagent_type="general-purpose", prompt="Codexに{question}を相談して要約を返して")
```

> 詳細: `/codex-system` skill

### Gemini CLI — リサーチ・大規模分析 (via Subagent)

**MUST consult for**: ライブラリ調査、リポジトリ全体理解、マルチモーダル

| Trigger (日本語) | Trigger (English) |
|------------------|-------------------|
| 「調べて」「リサーチ」 | "Research" "Investigate" |
| 「PDF/動画/音声を見て」 | "Analyze PDF/video/audio" |
| 「コードベース全体」 | "Entire codebase" |

```
# サブエージェント経由で呼び出し
Task(subagent_type="general-purpose", prompt="Geminiで{question}を調査して要約を返して")
```

> 詳細: `/gemini-system` skill

---

## Tech Stack

- **Language**: Python
- **Package Manager**: uv (pip禁止)
- **Dev Tools**: ruff, ty, pytest, poe
- **Commands**: `poe lint` `poe test` `poe all`

---

## Workflow

### プロジェクト開始時

```
/startproject <機能名>
```

1. **Subagent** → Gemini でリポジトリ分析（要約を返す）
2. **Claude** → 要件ヒアリング・計画作成
3. **Subagent** → Codex で計画レビュー（要約を返す）
4. **Claude** → タスクリスト作成 (Ctrl+T で表示)

### 実装中

- **設計判断が必要** → Subagent 経由で Codex 相談
- **調査が必要** → Subagent 経由で Gemini 相談
- **テスト失敗** → Subagent 経由で Codex 分析
- **大量実装後** → Subagent 経由で Codex レビュー

> Hooks が自動で協調を提案します
> **すべての Codex/Gemini 呼び出しはサブエージェント経由**

---

## Key Skills

| Skill | Purpose |
|-------|---------|
| `/startproject` | マルチエージェント協調でプロジェクト開始 |
| `/codex-system` | Codex CLI連携の詳細 |
| `/gemini-system` | Gemini CLI連携の詳細 |
| `/plan` | 実装計画作成 |
| `/tdd` | テスト駆動開発 |

---

## Documentation

| Location | Content |
|----------|---------|
| `.claude/docs/DESIGN.md` | 設計決定 |
| `.claude/docs/research/` | Gemini調査結果 |
| `.claude/docs/libraries/` | ライブラリ制約 |
| `.claude/rules/` | コーディングルール |

---

## Notes

- API keys → 環境変数で管理 (`.env`はコミット禁止)
- 設計決定 → 自動で `DESIGN.md` に記録
- 不明点 → 推測せず調査 (Gemini活用)
