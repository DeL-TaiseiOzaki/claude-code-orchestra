# Project Overview

LLM/Agent Development Project

---

## Multi-Agent System (CRITICAL)

```
┌─────────────────────────────────────────────────────────────┐
│           Claude Code (Orchestrator)                        │
│           → コンテキスト節約が最優先                         │
│           → 大きな出力が予想される場合はサブエージェント活用   │
│                      ↓                                      │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              Subagent (general-purpose)                │ │
│  │              → Codex/Gemini を呼び出し可能              │ │
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

| 状況 | 推奨方法 |
|------|----------|
| 大きな出力が予想される | サブエージェント経由 |
| 短い質問・短い回答 | 直接呼び出しOK |
| 複数の相談が必要 | サブエージェント経由 |
| 詳細な分析が必要 | サブエージェント経由 → ファイル保存 |

**判断基準（目安）:**
- **デフォルト**: サブエージェント経由
- **直接呼び出しOK**: 1-2文の回答で終わる質問のみ
- **必ずサブエージェント**: 出力10行以上、コード生成、分析レポート

```
# 推奨: サブエージェント経由（大きな出力の場合）
Task(subagent_type="general-purpose", prompt="Codexに設計を相談して要約を返して")

# OK: 直接呼び出し（短い質問の場合）
Bash("codex exec ... '短い質問'")  # 出力が小さければ問題なし
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
| `.claude/logs/cli-tools.jsonl` | **Codex/Gemini入出力ログ** |

### CLI Logs (Codex/Gemini)

Codex/Gemini への入出力は自動的に `.claude/logs/cli-tools.jsonl` に記録されます。

```bash
# 最近のログを確認
tail -10 .claude/logs/cli-tools.jsonl | jq '.'

# Codexのみ
jq 'select(.tool == "codex")' .claude/logs/cli-tools.jsonl

# 特定のプロンプトを検索
jq 'select(.prompt | contains("設計"))' .claude/logs/cli-tools.jsonl
```

**全エージェント（Claude, Subagent, Codex, Gemini）がこのログを参照できます。**

---

## Notes

- API keys → 環境変数で管理 (`.env`はコミット禁止)
- 設計決定 → 自動で `DESIGN.md` に記録
- 不明点 → 推測せず調査 (Gemini活用)
