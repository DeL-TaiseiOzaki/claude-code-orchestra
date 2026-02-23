# Codex Delegation Rule

**Codex CLI は計画・設計と難しいコード実装を担当する。**

## Codex の2つの役割

### 1. 計画・設計（Plan & Design）

- アーキテクチャ設計、モジュール構成
- 実装計画の策定（ステップ分解、依存関係整理）
- トレードオフ評価、技術選定
- コードレビュー（品質・正確性分析）

### 2. 難しいコード実装（Complex Implementation）

- 複雑なアルゴリズム、最適化
- 根本原因が不明なデバッグ
- 高度なリファクタリング
- マルチステップの実装タスク

## When to Consult Codex

| 状況 | 例 |
|------|------|
| **計画が必要** | 「どう設計？」「計画を立てて」「アーキテクチャ」 |
| **難しい実装** | 複雑なロジック、最適化、パフォーマンス改善 |
| **デバッグ** | 「なぜ動かない？」「エラーの原因は？」（初回失敗後） |
| **比較検討** | 「AとBどちらがいい？」「トレードオフは？」 |
| **コードレビュー** | 「レビューして」「品質チェック」 |

### Trigger Phrases (User Input)

| Japanese | English |
|----------|---------|
| 「どう設計すべき？」「どう実装する？」 | "How should I design/implement?" |
| 「計画を立てて」「アーキテクチャ」 | "Create a plan" "Architecture" |
| 「なぜ動かない？」「原因は？」「エラーが出る」 | "Why doesn't this work?" "Error" |
| 「どちらがいい？」「比較して」「トレードオフは？」 | "Which is better?" "Compare" |
| 「考えて」「分析して」「深く考えて」 | "Think" "Analyze" "Think deeper" |

## When NOT to Consult

- 単純なファイル編集（typo修正、小さな変更）
- 明示的なユーザー指示に従うだけの作業
- 標準操作（git commit、テスト実行）
- 明確な単一解があるタスク
- ファイル検索・読み取り
- **コードベース分析** → Claude が直接行う（1M context）
- **外部情報取得** → サブエージェント（WebSearch/WebFetch）が行う
- **マルチモーダル処理** → Gemini が行う

## Context Management

| 状況 | 推奨方法 |
|------|----------|
| 短い質問・短い回答（〜50行） | 直接呼び出しOK |
| 詳細な設計・計画 | サブエージェント経由 |
| デバッグ分析 | サブエージェント経由 |
| 複雑なコード実装 | サブエージェント経由（workspace-write） |

## How to Consult

### Subagent Pattern（推奨）

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

### Direct Call (短い質問、〜50行の回答)

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "Brief question" 2>/dev/null
```

### Codex に実装させる場合

```bash
codex exec --model gpt-5.3-codex --sandbox workspace-write --full-auto "
Implement: {detailed implementation task}

Requirements:
- {requirement 1}
- {requirement 2}

Files to create/modify:
- {file paths}
" 2>/dev/null
```

### Sandbox Modes

| Mode | Sandbox | Use Case |
|------|---------|----------|
| Analysis | `read-only` | 設計レビュー、デバッグ、トレードオフ |
| Implementation | `workspace-write` | 実装、修正、リファクタリング |

## Language Protocol

1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on advice
4. Report to user in **Japanese**
