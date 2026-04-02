# claude-code-orchestra

![Claude Code Orchestra](./summary.png)

Multi-Agent AI Development Environment

```
Claude Code (Orchestrator) ─┬─ Codex CLI (Planning & Complex Code)
                             ├─ Opus Subagents (Research, Analysis, Implementation)
                             └─ Gemini CLI (Multimodal: PDF/Video/Audio/Image)
```

## Quick Start

既存プロジェクトのルートで実行（事前に Codex/Gemini の起動・ログイン確認）:

```bash
codex --version && codex login && gemini --version && gemini login && git clone --depth 1 https://github.com/DeL-TaiseiOzaki/claude-code-orchestra.git .starter && cp -r .starter/.claude .starter/.codex .starter/.gemini .starter/CLAUDE.md . && rm -rf .starter && claude
```

## Prerequisites

### Claude Code

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

### Codex CLI

```bash
npm install -g @openai/codex
codex login
```

### Codex Plugin for Claude Code (Optional)

Codex を Claude Code から直接使うためのプラグインです。コードレビューやタスク委譲が簡単になります。

```bash
# Claude Code 内で実行
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

**提供されるコマンド:**
- `/codex:review` — コードレビュー
- `/codex:adversarial-review` — 設計チャレンジレビュー
- `/codex:rescue` — タスク委譲
- `/codex:status` / `/codex:result` / `/codex:cancel` — ジョブ管理

### Gemini CLI

```bash
npm install -g @google/gemini-cli
gemini login
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           Claude Code (Orchestrator — Opus 4.6, 1M context)    │
│           → コンテキスト節約が最優先                         │
│           → ユーザー対話・調整・簡潔な編集を担当             │
│                      ↓                                      │
│  ┌──────────────────────┐  ┌──────────────────────────┐    │
│  │  Subagent (Opus)      │  │  gemini-explore (Opus)    │    │
│  │  general-purpose      │  │  → Gemini CLI             │    │
│  │  → コード実装         │  │  → マルチモーダル処理     │    │
│  │  → 調査・分析         │  │  → PDF/動画/音声/画像     │    │
│  │  → Codex委譲          │  │                            │    │
│  │  ┌──────────────┐    │  │                            │    │
│  │  │  Codex CLI   │    │  │  ┌──────────────┐          │    │
│  │  │  設計・推論  │    │  │  │  Gemini CLI  │          │    │
│  │  │  デバッグ    │    │  │  │  1M context  │          │    │
│  │  └──────────────┘    │  │  └──────────────┘          │    │
│  └──────────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### コンテキスト管理（重要）

メインオーケストレーター（Opus 4.6, 1M context）のコンテキストを節約するため、大規模タスクは適切なエージェントに委譲します。

| 状況 | 推奨方法 |
|------|----------|
| コードベース全体分析 | **Opus サブエージェント**（1M context） |
| 外部リサーチ・サーベイ | **Opus サブエージェント**（WebSearch/WebFetch） |
| マルチモーダルファイル | **Gemini 経由**（PDF/動画/音声/画像） |
| コード実装 | サブエージェント（Opus）経由 |
| 設計・計画相談 | サブエージェント → Codex |
| 短い質問・短い回答 | 直接呼び出しOK |
| 詳細な分析が必要 | サブエージェント経由 → ファイル保存 |

## Directory Structure

```
.
├── CLAUDE.md                    # メインシステムドキュメント
├── README.md
├── LICENSE
├── pyproject.toml               # Python プロジェクト設定
├── uv.lock                      # 依存関係ロックファイル
├── VERSION                      # テンプレートバージョン
│
├── .claude/
│   ├── agents/
│   │   ├── general-purpose.md   # 実装・調査・Codex委譲エージェント (Opus)
│   │   ├── codex-debugger.md    # エラー分析エージェント (Opus)
│   │   └── gemini-explore.md    # マルチモーダル処理エージェント (Opus)
│   │
│   ├── skills/                  # 再利用可能なワークフロー (17個)
│   │   ├── startproject/        # マルチエージェント協調でプロジェクト開始
│   │   ├── team-implement/      # Agent Teams で並列実装
│   │   ├── team-review/         # Agent Teams で並列レビュー
│   │   ├── add-feature/         # Codex-first 機能追加（複雑度別ルーティング）
│   │   ├── spike/               # 技術調査・フィージビリティスタディ（意思決定文書）
│   │   ├── plan/                # 実装計画作成
│   │   ├── tdd/                 # テスト駆動開発
│   │   ├── simplify/            # コードリファクタリング
│   │   ├── codex-system/        # Codex CLI連携
│   │   ├── gemini-system/       # Gemini CLI連携
│   │   ├── design-tracker/      # 設計決定の自動追跡
│   │   ├── update-design/       # 設計ドキュメント明示更新
│   │   ├── research-lib/        # ライブラリ調査
│   │   ├── update-lib-docs/     # ライブラリドキュメント更新
│   │   ├── checkpointing/       # セッション永続化 + パターン発見
│   │   ├── init/                # プロジェクト初期化
│   │   └── troubleshoot/        # エラー診断・修正計画
│   │
│   ├── hooks/                   # 自動化フック (9個)
│   │   ├── agent-router.py      # エージェントルーティング
│   │   ├── lint-on-save.py      # 保存時自動lint
│   │   ├── error-to-codex.py    # エラー検出→debugger提案
│   │   └── ...
│   │
│   ├── rules/                   # 開発ガイドライン
│   │   ├── coding-principles.md
│   │   ├── testing.md
│   │   └── ...
│   │
│   ├── settings.json             # Claude Code設定（hooks/permissions/env）
│   │
│   ├── docs/
│   │   ├── DESIGN.md            # 設計決定記録
│   │   ├── CODEX_HANDOFF_PLAYBOOK.md  # Codex委譲テンプレート
│   │   ├── research/            # 調査結果（Opusサブエージェント）
│   │   └── libraries/           # ライブラリ制約
│   │
│   └── logs/                    # ランタイム生成（.gitignore対象）
│       └── cli-tools.jsonl      # Codex/Gemini入出力ログ
│
├── .codex/                      # Codex CLI設定
│   ├── AGENTS.md
│   ├── config.toml
│   └── skills/
│       ├── context-loader/      # コンテキスト読み込みスキル
│       └── design-tracker/      # 設計追跡スキル
│
├── .gemini/                     # Gemini CLI設定
│   ├── GEMINI.md
│   ├── settings.json
│   └── skills/
│       └── context-loader/      # コンテキスト読み込みスキル
│
└── scripts/
    └── update.sh               # テンプレート更新スクリプト
```

### Codex連携を安定化するための運用

- `@.claude/docs/CODEX_HANDOFF_PLAYBOOK.md` のテンプレートで Codex への依頼を統一
- `.claude/rules/codex-delegation.md` で「Codex優先で渡す」方針と例外条件を明確化
- `.codex/config.toml` は `approval_policy = "never"` を採用し、非対話フローでも止まりにくくする

## Workflow

メインのワークフローは3つのスキルを順に実行します。

```
/startproject <機能名>     Phase 1-3: コードベース理解 → 調査&設計 → 計画
    ↓ ユーザー承認後
/team-implement            Phase 4: Agent Teams で並列実装
    ↓ 実装完了後
/team-review               Phase 5: Agent Teams で並列レビュー
```

1. **Opus サブエージェント** でコードベースを分析（1M context）+ **Claude** がユーザーと要件ヒアリング
2. **Agent Teams** で Researcher（Opus）↔ Architect（Codex）が並列に調査・設計
3. **Claude** が調査と設計を統合し、計画をユーザーに提示
4. 承認後、`/team-implement` でモジュール単位の並列実装
5. `/team-review` でセキュリティ・品質・テストの並列レビュー

## Skills

### Core Workflow

#### `/startproject` — プロジェクト開始

マルチエージェント協調でプロジェクトを開始します。

```
/startproject ユーザー認証機能
```

**ワークフロー:**
1. **Opus サブエージェント** → コードベース分析・事前調査（1M context）
2. **Claude** → ユーザーと要件ヒアリング
3. **Agent Teams** → Researcher（Opus）↔ Architect（Codex）で並列調査・設計
4. **Claude** → 計画統合・ユーザー承認

#### `/team-implement` — 並列実装

Agent Teams による並列実装。`/startproject` で承認された計画に基づいて実行します。

```
/team-implement
```

**特徴:**
- モジュール/レイヤー単位で Teammate を起動し、ファイル所有権を分離
- 共有タスクリストで依存関係を管理し自律的に協調
- 各 Teammate は完了時にワークログを `.claude/logs/agent-teams/` に記録

#### `/team-review` — 並列レビュー

Agent Teams による並列コードレビュー。実装完了後に実行します。

```
/team-review
```

**レビュアー構成:**
- **Security Reviewer** — セキュリティ脆弱性の検出
- **Quality Reviewer** — コード品質・パターン準拠の確認（Codex 活用）
- **Test Reviewer** — テストカバレッジ・品質の検証

#### `/add-feature` — 機能追加

既存コードベースにCodex-firstで機能を追加します。`/startproject`（新規プロジェクト向け）より軽量で、複雑度に応じた実装ルーティングを行います。

```
/add-feature ユーザープロフィール編集機能
```

**ワークフロー:**
1. **Opus サブエージェント + Codex** → スコープ＆影響分析
2. **Codex** → アーキテクチャ設計・実装計画・バリデーション
3. **複雑度別ルーティング:**
   - SIMPLE（1-3ファイル, <50 LOC）→ Codex 直接実装
   - MODERATE（3-5ファイル）→ Codex 実装 + `/team-review`
   - COMPLEX（5+ファイル）→ `/team-implement` + `/team-review`

#### `/spike` — 技術調査・フィージビリティスタディ

Codex-firstのタイムボックス型技術調査。**意思決定文書**（go/no-go推奨）を作成します。実装計画ではなく、判断材料を提供します。

```
/spike WebSocketとSSEのどちらを採用すべきか
```

**ワークフロー:**
1. **Claude + Codex** → 調査質問のフレーミング・制約定義
2. **Agent Teams** → Researcher（Opus外部調査）↔ Feasibility Analyst（Codex深層分析）で並列調査
3. **Codex** → go/no-go推奨に統合・リサーチレポート作成

> GO決定後は `/add-feature` または `/startproject` で実装に進む

### Development

#### `/plan` — 実装計画

要件を具体的なステップに分解します。

```
/plan APIエンドポイントの追加
```

**出力:**
- 実装ステップ（ファイル・変更内容・検証方法）
- 依存関係・リスク
- 検証基準

#### `/tdd` — テスト駆動開発

Red-Green-Refactorサイクルで実装します。

```
/tdd ユーザー登録機能
```

**ワークフロー:**
1. テストケース設計
2. 失敗するテスト作成（Red）
3. 最小限の実装（Green）
4. リファクタリング（Refactor）

#### `/simplify` — コードリファクタリング

コードを簡潔化・可読性向上させます。

#### `/troubleshoot` — エラー診断・修正計画

Codexを中心としたマルチエージェント協調でエラーを診断し、修正計画を立案します。

```
/troubleshoot TypeError: cannot unpack non-iterable NoneType object
```

**ワークフロー:**
1. **Opus サブエージェント + Codex** → エラー再現・コンテキスト収集
2. **Agent Teams** → Root Cause Analyst（Codex駆動）↔ Impact Investigator（Opus + Codex）で並列診断
3. **Claude + Codex** → 修正計画統合・ユーザー承認

### Agent Delegation

#### `/codex-system` — Codex CLI連携

設計判断・デバッグ・トレードオフ分析に使用します。

**トリガー例:**
- 「どう設計すべき？」「どう実装する？」
- 「なぜ動かない？」「エラーが出る」
- 「どちらがいい？」「比較して」

#### `/gemini-system` — Gemini CLI連携

Gemini CLI を活用したマルチモーダルファイル処理（PDF/動画/音声/画像）。

**トリガー例:**
- 「このPDFを読んで」「この動画を要約して」
- 「この音声を文字起こしして」「この図を分析して」

### Documentation

#### `/design-tracker` — 設計決定追跡

アーキテクチャ・実装決定を自動記録します。会話中の設計判断を検出して `.claude/docs/DESIGN.md` に自動追記します。

#### `/update-design` — 設計ドキュメント更新

会話内容から設計決定を抽出し、`.claude/docs/DESIGN.md` を明示的に更新します。

#### `/research-lib` — ライブラリ調査

ライブラリを調査し、`.claude/docs/libraries/` に包括的なドキュメントを生成します。

```
/research-lib httpx
```

#### `/update-lib-docs` — ライブラリドキュメント更新

`.claude/docs/libraries/` の既存ドキュメントを最新情報で更新します。

### Session Management

#### `/checkpointing` — セッション永続化

セッションの全活動（git履歴・CLI相談・Agent Teams活動・設計決定）を記録し、再利用可能なスキルパターンを発見します。

```bash
/checkpointing                    # 全記録 + パターン発見
/checkpointing --since "2026-02-08"  # 特定日以降のみ
```

#### `/init` — プロジェクト初期化

プロジェクト構造を分析し、Tech Stack・コマンド・設定を自動検出して AGENTS.md を更新します。

## Development

### Template Update

テンプレートの更新をローカルプロジェクトに安全に反映できます。

```bash
# 最新版に更新
./scripts/update.sh

# 特定バージョンに更新
./scripts/update.sh v0.2.0

# 確認プロンプトをスキップ
./scripts/update.sh --yes
```

**仕組み:**
- `CLAUDE.md` の `@orchestra:local-boundary` セパレータより上（テンプレート部分）のみ更新
- skills/hooks/rules/agents は完全同期
- `.claude/docs/research/` 等のローカルデータは保護
- `.claude/settings.json` は差分表示のみ（手動マージ）

### Tech Stack

| ツール | 用途 |
|--------|------|
| **uv** | パッケージ管理（pip禁止） |
| **ruff** | リント・フォーマット |
| **ty** | 型チェック |
| **pytest** | テスト |
| **poethepoet** | タスクランナー |

### Commands

```bash
# 依存関係
uv add <package>           # パッケージ追加
uv add --dev <package>     # 開発依存追加
uv sync                    # 依存関係同期

# 品質チェック
poe lint                   # ruff check + format
poe typecheck              # ty
poe test                   # pytest
poe all                    # 全チェック実行

# 直接実行
uv run pytest -v
uv run ruff check .
```

## Hooks

自動化フックにより、適切なタイミングでエージェント連携・品質チェックを実行します。

| フック | トリガー | 動作 |
|--------|----------|------|
| `agent-router.py` | ユーザー入力 | Codex/Geminiへのルーティング提案 |
| `lint-on-save.py` | ファイル保存 | 自動lint実行 |
| `check-codex-before-write.py` | ファイル書き込み前 | Codex相談提案 |
| `check-codex-after-plan.py` | Task実行後 | 計画・設計タスク後にCodexレビュー提案 |
| `error-to-codex.py` | Bashエラー検出 | codex-debuggerサブエージェント提案 |
| `post-test-analysis.py` | テスト/ビルド失敗 | Codexによるデバッグ分析提案 |
| `post-implementation-review.py` | 大規模実装後 | Codexによるコードレビュー提案 |
| `suggest-gemini-research.py` | WebSearch/Fetch前 | 深い調査はOpusサブエージェント委譲を提案 |
| `log-cli-tools.py` | Codex/Gemini実行 | 入出力ログ記録 |

## Language Rules

- **コード・思考・推論**: 英語
- **ユーザーへの応答**: 日本語
- **技術ドキュメント**: 英語
- **README等**: 日本語可
