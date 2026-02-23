# Claude Code Orchestra

**マルチエージェント協調フレームワーク（Opus 4.6 + Agent Teams 対応）**

Claude Code が全体統括し、Codex CLI（計画・難実装）と Gemini CLI（1M context 活用）を使い分ける。

---

## Agent Roles — 役割分担

| Agent | Model | Role | Use For |
|-------|-------|------|---------|
| **Claude Code（メイン）** | Opus 4.6 | 全体統括 | ユーザー対話、タスク管理、簡潔なコード編集 |
| **general-purpose（サブエージェント）** | **Opus** | 実装・Codex委譲 | コード実装、Codex委譲、ファイル操作 |
| **codex-debugger（サブエージェント）** | **Opus** | エラー解析 | Codex CLI でエラーの根本原因分析・修正提案 |
| **gemini-explore（サブエージェント）** | **Opus** | 大規模分析・調査 | コードベース理解、外部リサーチ、マルチモーダル読取（1M context） |
| **Agent Teams チームメイト** | **Opus**（デフォルト） | 並列協調 | /startproject, /team-implement, /team-review |
| **Codex CLI** | gpt-5.3-codex | 計画・難しい実装 | アーキテクチャ設計、実装計画、複雑なコード実装 |
| **Gemini CLI** | gemini-3-pro | 1M context エージェント | コードベース分析、リサーチ、マルチモーダル読取 |

### 判断フロー

```
タスク受信
  ├── マルチモーダルファイル（PDF/動画/音声/画像）がある？
  │     → YES: Gemini にファイルを渡して内容抽出
  │
  ├── コードベース全体の理解・大規模分析が必要？
  │     → YES: Gemini に委譲（1M context 活用）
  │
  ├── 外部情報・リサーチ・サーベイが必要？
  │     → YES: Gemini に委譲（Google Search grounding 活用）
  │
  ├── 計画・設計・難しいコードが必要？
  │     → YES: Codex に相談 or 実装させる
  │
  └── 通常のコード実装？
        → メインが直接 or サブエージェントに委託
```

---

## Quick Reference

### Codex を使う時

- **計画・設計**（「どう実装？」「アーキテクチャ」「計画を立てて」）
- **難しいコード実装**（複雑なアルゴリズム、最適化、マルチステップ実装）
- **デバッグ**（「なぜ動かない？」「エラーの原因は？」）
- **比較検討**（「AとBどちらがいい？」「トレードオフは？」）

→ 詳細: `.claude/rules/codex-delegation.md`

### Gemini を使う時

Gemini CLI は **1M トークンのコンテキスト**を持ち、以下の3つの役割を担う:

- **マルチモーダルファイル読取（必須・自動委譲）**
  - PDF、動画、音声、画像ファイルが登場したら自動で Gemini に渡す
  ```bash
  gemini -p "{抽出したい情報}" < /path/to/file 2>/dev/null
  ```
- **コードベース・リポジトリ理解**
  - プロジェクト全体の構造分析、パターン把握、依存関係の理解
  - メインの 200K コンテキストでは収まらない大規模分析を委譲
  ```bash
  gemini -p "Analyze this codebase: structure, key modules, patterns, dependencies" 2>/dev/null
  ```
- **外部リサーチ・サーベイ**
  - 最新ドキュメント調査、ライブラリ比較、ベストプラクティス調査
  - Gemini の Google Search grounding を活用
  ```bash
  gemini -p "Research: {topic}. Find latest best practices, constraints, and recommendations" 2>/dev/null
  ```

> スクリーンショットの単純確認は Claude の Read ツールで直接可能。

→ 詳細: `.claude/rules/gemini-delegation.md`

### サブエージェントを使う時

- **コード実装**（メインのコンテキストを節約したい場合）
- **Codex 委譲**（計画・設計の相談をサブエージェント経由で）
- **調査結果の整理** → `.claude/docs/research/` に保存

---

## Context Management

Claude Code (Opus 4.6) のコンテキストは **200K トークン**（実質 **140-150K**、ツール定義等で縮小）。
> ※ API pay-as-you-go (Tier 4+) では 1M Beta が利用可能。

**Compaction 機能**により、長時間セッションでもサーバーサイドで自動要約される。

**Gemini CLI は 1M トークン**のコンテキストを持つため、大規模分析・調査は Gemini に委譲する。

### モデル選択方針

| エージェント | モデル | 理由 |
|------------|--------|------|
| general-purpose | **Opus** | 高い推論能力でコード実装・Codex委譲を高品質に実行 |
| codex-debugger | **Opus** | エラー解析には高い推論能力が必要。Codex への的確な質問生成に強い |
| gemini-explore | **Opus** | Gemini CLI（1M context）を活用した大規模分析・調査・マルチモーダル処理の統括 |
| Agent Teams | **Opus**（デフォルト） | `CLAUDE_CODE_SUBAGENT_MODEL` で設定。高い推論能力で並列作業に対応 |

### 呼び出し基準

| 出力サイズ | 方法 | 理由 |
|-----------|------|------|
| 短い（〜20行） | 直接呼び出しOK | 200Kコンテキストで吸収可能 |
| 中程度（20-50行） | サブエージェント経由を推奨 | コンテキスト効率化 |
| 大きい（50行以上） | サブエージェント → ファイル保存 | 詳細は `.claude/docs/` に永続化 |
| コードベース全体分析 | **Gemini 経由** | 1M context を活用 |
| 外部リサーチ | **Gemini 経由** | Google Search grounding 活用 |

### 並列処理の選択

| 目的 | 方法 | 適用場面 |
|------|------|----------|
| 結果を取得するだけ | サブエージェント | Codex相談、調査、実装 |
| 相互通信が必要 | **Agent Teams** | 並列実装、並列レビュー |

---

## Workflow

```
/startproject <機能名>     Phase 1-3: 理解 → 調査&設計 → 計画
    ↓ 承認後
/team-implement            Phase 4: Agent Teams で並列実装
    ↓ 完了後
/team-review               Phase 5: Agent Teams で並列レビュー
```

1. Gemini でコードベースを分析（1M context）+ Claude がユーザーと要件ヒアリング
2. Gemini で外部調査 + Codex で設計・計画（並列可）
3. Claude が調査と設計を統合し、計画をユーザーに提示
4. 承認後、`/team-implement` で並列実装
5. `/team-review` で並列レビュー

→ 詳細: `/startproject`, `/team-implement`, `/team-review` skills

---

## Tech Stack

- **Python** / **uv** (pip禁止)
- **ruff** (lint/format) / **ty** (type check) / **pytest**
- `poe lint` / `poe test` / `poe all`

→ 詳細: `.claude/rules/dev-environment.md`

---

## Documentation

| Location | Content |
|----------|---------|
| `.claude/rules/` | コーディング・セキュリティ・言語ルール |
| `.claude/docs/DESIGN.md` | 設計決定の記録 |
| `.claude/docs/research/` | 調査結果（サブエージェント / レビュー） |
| `.claude/docs/libraries/` | ライブラリ制約ドキュメント |
| `.claude/logs/cli-tools.jsonl` | Codex/Gemini入出力ログ |

---

## Language Protocol

- **思考・コード**: 英語
- **ユーザー対話**: 日本語
