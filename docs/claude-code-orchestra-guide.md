# Claude Code Orchestra 完全ガイド

**マルチエージェント協調フレームワーク（Opus 4.6 + Codex CLI + Gemini CLI + Agent Teams）**

Claude Code が全体統括し、Codex CLI（計画・難実装）と Gemini CLI（マルチモーダル読取）を使い分けるオーケストラ型テンプレート。

```
┌─────────────────────────────────────────────────────────────┐
│          Claude Code (Opus 4.6 / 1M context)                │
│              全体統括・指揮者                                 │
├────────┬──────────┬──────────────┬──────────────────────────┤
│ Codex  │ Gemini   │ サブエージェント │ Agent Teams             │
│ CLI    │ CLI      │ (general-    │ (チームメイト)            │
│ 計画   │ PDF/動画 │  purpose等)  │ 並列実装                 │
│ 設計   │ 音声/画像│ 調査・実装    │ 並列レビュー             │
│ デバッグ│ 読取専用 │ 外部検索      │ 相互通信あり             │
└────────┴──────────┴──────────────┴──────────────────────────┘
```

---

## 目次

1. [CLI Agentをうまく使いこなすキモは結局コンテキスト処理](#1-cli-agentをうまく使いこなすキモは結局コンテキスト処理)
2. [Claude Code・Codex・Geminiのそれぞれ強いユースケースを見つける](#2-claude-codecodexgeminiのそれぞれ強いユースケースを見つける)
3. [認知負荷を下げる意識を忘れない](#3-認知負荷を下げる意識を忘れない)
4. [カスタマイズを楽しんで！](#4-カスタマイズを楽しんで)

---

## 1. CLI Agentをうまく使いこなすキモは結局コンテキスト処理

### なぜコンテキスト処理が最重要なのか

Claude Code（Opus 4.6）は **1M トークンのコンテキストウィンドウ** を持つ。しかし、ツール定義やシステムプロンプトで実質 **350-500k** に縮小される。このテンプレートの設計思想は **「いかにこの有限なコンテキストを効率的に使うか」** に集約される。

### このテンプレートのコンテキスト戦略

#### 戦略1: 出力サイズによる振り分け

すべてのタスクを Claude が直接処理するのではなく、**出力の大きさによって処理方法を変える**。

| 出力サイズ | 処理方法 | 理由 |
|-----------|----------|------|
| **短い（〜50行）** | Claude が直接処理 | 1M コンテキストで十分吸収可能 |
| **大きい（50行以上）** | サブエージェント経由 | メインのコンテキストを節約 |
| **分析レポート** | サブエージェント → ファイル保存 | `.claude/docs/` に永続化して再利用 |

#### 戦略2: サブエージェントによるコンテキスト隔離

サブエージェントは **独立したコンテキストウィンドウ** を持つ。つまり、大量の調査結果やCodexの詳細な分析は、サブエージェントのコンテキスト内で処理され、**要約だけがメインに返る**。

```
メイン（1Mコンテキスト）
  ├── 「ライブラリXを調べて」→ サブエージェント（独立コンテキスト）
  │                              ├── WebSearch → 大量の検索結果
  │                              ├── WebFetch → ドキュメント全文
  │                              └── 要約して返す（〜20行）← これだけがメインに入る
  │
  └── 「設計を考えて」→ サブエージェント（独立コンテキスト）
                          ├── Codex CLI → 詳細な設計文書
                          └── 要約して返す（〜30行）← これだけがメインに入る
```

**サブエージェント定義（`.claude/agents/`）**:

| エージェント | モデル | ツール | 役割 |
|---|---|---|---|
| **general-purpose** | Sonnet (1M) | Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch | 外部調査、コード実装、Codex委譲 |
| **codex-debugger** | Opus | Read, Bash, Grep, Glob | エラーの根本原因分析（Codex CLIで深い推論） |
| **gemini-explore** | Opus | Read, Bash, Grep, Glob, WebFetch, WebSearch | PDF/動画/音声/画像の内容抽出 |

#### 戦略3: Agent Teams vs サブエージェントの使い分け

並列処理に2つの方法があり、**相互通信の要否** で使い分ける。

| 目的 | 方法 | 特徴 |
|------|------|------|
| 結果を取得するだけ | **サブエージェント** | 独立コンテキスト、結果のみ返す |
| 相互に通信が必要 | **Agent Teams** | チームメイト間で双方向通信が可能 |

**Agent Teams の核心**: `/startproject` の Phase 2 では、Researcher と Architect が **リアルタイムで双方向通信** する。Researcher の調査結果が Architect の設計を更新し、Architect の新たな要件が Researcher に新しい調査を依頼する。これにより、従来の「調査→設計」の逐次プロセスが **一つの並列セッション** に圧縮される。

#### 戦略4: ファイルによる永続化

コンテキストは消えるが、**ファイルは残る**。このテンプレートは情報をファイルに永続化して、セッションをまたいで再利用する。

| 場所 | 内容 | 誰が書く |
|------|------|---------|
| `.claude/docs/DESIGN.md` | 設計決定の記録 | `/design-tracker`（自動） |
| `.claude/docs/research/` | 調査結果 | サブエージェント |
| `.claude/docs/libraries/` | ライブラリ制約 | `/research-lib` |
| `.claude/logs/cli-tools.jsonl` | Codex/Gemini 呼び出しログ | `log-cli-tools.py`（自動） |
| `.claude/checkpoints/` | セッション全体の記録 | `/checkpointing` |
| `.claude/logs/agent-teams/` | チームメイトのワークログ | 各チームメイト |

#### 戦略5: Compaction への対策

長時間セッションでは **サーバーサイドの自動圧縮（Compaction）** が発動する。このテンプレートには `PreCompact` フックがあり、圧縮前に「CLAUDE.md、DESIGN.md、rulesを忘れないで」とリマインドする。

また、`/checkpointing` スキルでセッション全体をファイルに保存できるため、圧縮や新セッション開始後にも情報を復元できる。

---

## 2. Claude Code・Codex・Geminiのそれぞれ強いユースケースを見つける

### 全体像: 誰が何をするのか

```
タスク受信
  ├── マルチモーダルファイル（PDF/動画/音声/画像）がある？
  │     → Gemini CLI にファイルを渡して内容抽出
  │
  ├── 計画・設計・デバッグ・複雑な実装が必要？
  │     → Codex CLI に相談 or 実装させる
  │
  ├── 外部情報・リサーチが必要？
  │     → サブエージェント（WebSearch/WebFetch）
  │
  ├── 並列実装・並列レビューが必要？
  │     → Agent Teams（チームメイト）
  │
  └── 通常のコード実装・分析？
        → Claude Code が直接処理
```

### Claude Code（Opus 4.6）— 全体統括・指揮者

**何が強いのか**: 1M コンテキストによるコードベース全体の把握、ユーザーとの対話、タスクの振り分け

| 得意なこと | 説明 |
|-----------|------|
| コードベース分析 | 1M コンテキストで数千ファイルを直接読める。Gemini やCodexに委譲する必要なし |
| ユーザー対話 | 日本語での質問・回答・確認 |
| タスク管理 | TodoWrite でタスクを分解し、サブエージェントに振り分け |
| 単純なコード変更 | typo修正、小さなリファクタ、設定変更など |
| Git操作 | コミット、ブランチ管理、PR作成 |

**Claude がやらないこと**:
- PDF/動画/音声の読取 → Gemini
- 深い設計・計画 → Codex
- 外部リサーチ（コンテキスト節約のためサブエージェントに委託）

### Codex CLI（gpt-5.3-codex）— 計画・設計・難しい実装

**何が強いのか**: 深い推論による設計、計画策定、複雑なアルゴリズム、根本原因分析

**設定ファイル**: `.codex/config.toml`

```toml
model = "gpt-5.3-codex"
model_reasoning_effort = "xhigh"     # 最大の推論リソース
model_reasoning_summary = "detailed" # 詳細なサマリー
web_search = "enabled"               # Web検索有効
```

**ペルソナ定義**: `.codex/AGENTS.md` — Claude Code に呼ばれる専門家として定義

#### Codex の2つの役割

**1. 計画・設計（Plan & Design）**
- アーキテクチャ設計、モジュール構成
- 実装計画の策定（ステップ分解、依存関係整理）
- トレードオフ評価、技術選定
- コードレビュー（品質・正確性分析）

**2. 難しいコード実装（Complex Implementation）**
- 複雑なアルゴリズム、最適化
- 根本原因が不明なデバッグ
- 高度なリファクタリング

#### 呼び出し方法

```bash
# 分析・設計（読み取り専用サンドボックス）
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "質問" 2>/dev/null

# 実装（書き込み可能サンドボックス）
codex exec --model gpt-5.3-codex --sandbox workspace-write --full-auto "実装タスク" 2>/dev/null
```

#### トリガーフレーズ（これらが出たら Codex に相談）

| 日本語 | 英語 |
|--------|------|
| 「どう設計すべき？」「どう実装する？」 | "How should I design/implement?" |
| 「計画を立てて」「アーキテクチャ」 | "Create a plan" "Architecture" |
| 「なぜ動かない？」「原因は？」「エラーが出る」 | "Why doesn't this work?" "Error" |
| 「どちらがいい？」「比較して」「トレードオフは？」 | "Which is better?" "Compare" |
| 「考えて」「分析して」「深く考えて」 | "Think" "Analyze" "Think deeper" |

#### Codex 用リファレンス資料（5種）

このテンプレートには Codex を効果的に使うためのテンプレート集が同梱されている。

| ファイル | 内容 |
|---------|------|
| `agent-prompts.md` | Architect、Analyzer、Optimizer、Security の4つのエージェントプロンプトテンプレート |
| `code-review-task.md` | コードレビュー用プロンプトテンプレート（チェックリスト付き） |
| `delegation-patterns.md` | 判断フローチャートと4つのパターン例（アーキテクチャ、障害、最適化、セキュリティ） |
| `refactoring-task.md` | リファクタリング用プロンプトテンプレート |
| `troubleshooting.md` | Codex CLI のトラブルシューティング |

### Gemini CLI（gemini-3-pro）— マルチモーダル読取専用

**何が強いのか**: PDF、動画、音声、画像の内容理解

**設定ファイル**: `.gemini/settings.json`

```json
{
  "model": { "name": "gemini-3-pro-preview" }
}
```

**ペルソナ定義**: `.gemini/GEMINI.md` — マルチモーダルファイル読取専用と明記

#### 対象ファイル

| カテゴリ | 拡張子 |
|----------|--------|
| PDF | `.pdf` |
| 動画 | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| 音声 | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg` |
| 画像（詳細分析） | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg` |

#### 呼び出し方法

```bash
# PDF — 構造・内容の抽出
gemini -p "Extract: API endpoints, schemas, auth methods" < /path/to/api-docs.pdf 2>/dev/null

# 動画 — 要約・キーポイント
gemini -p "Summarize: key concepts, decisions, timestamps" < /path/to/meeting.mp4 2>/dev/null

# 音声 — 文字起こし・要約
gemini -p "Transcribe and summarize: decisions, action items" < /path/to/audio.mp3 2>/dev/null

# 画像 — 図表・ダイアグラムの分析
gemini -p "Analyze: components, relationships, data flow" < /path/to/diagram.png 2>/dev/null
```

#### 重要な制約: Gemini が「やらない」こと

| やらないこと | 代わりに誰がやるか |
|---|---|
| 外部リサーチ | サブエージェント（WebSearch/WebFetch） |
| ライブラリ調査 | サブエージェント（WebSearch/WebFetch） |
| コードベース分析 | Claude Code（1M context で直接） |
| 設計・計画 | Codex CLI |
| デバッグ | Codex CLI |

### コンテキストローダー — 共有知識の同期

Codex と Gemini はそれぞれ **コンテキストローダースキル** を持つ（`.codex/skills/context-loader/`、`.gemini/skills/context-loader/`）。タスク開始時に `.claude/rules/`、`.claude/docs/DESIGN.md`、`.claude/docs/libraries/` を読み込み、Claude Code と同じプロジェクト知識を共有する。

---

## 3. 認知負荷を下げる意識を忘れない

### 自動化フック — 「考えなくていい」仕組み

このテンプレートの9つのフックは、**ユーザーが何も指示しなくても適切なエージェントへのルーティングや品質チェックを行う**。

#### ルーティング系フック（入力時）

**`agent-router.py`** — ユーザー入力の自動分析

| 検出対象 | 優先度 | 提案 |
|---------|--------|------|
| マルチモーダルファイル（.pdf/.mp4/.mp3等） | **最高** | Gemini CLI に自動委譲 |
| Codexキーワード（設計/計画/デバッグ/最適化） | 高 | Codex CLI に相談 |
| リサーチキーワード（調べて/研究/調査） | 中 | サブエージェント（WebSearch） |

#### 品質保証系フック（ツール実行後）

**`lint-on-save.py`** — Python ファイル保存時に自動実行

```
Edit/Write でPythonファイルを変更
  → ruff format（フォーマット）
  → ruff check --fix（リント＆自動修正）
  → ty check（型チェック）
```

**`error-to-codex.py`** — エラー検出時の自動ルーティング

```
Bash でコマンド実行 → エラーパターンを検出（28種類の正規表現）
  → codex-debugger サブエージェントへのルーティングを提案
```

検出するエラーパターン: Traceback、Exception、TypeError、ValueError、SyntaxError、ImportError、RuntimeError、npm ERR!、cargo error、git errors 等

**`post-test-analysis.py`** — テスト/ビルド失敗の分析提案

```
pytest/npm test/cargo test 等の実行後
  → 3件以上の失敗パターン or トレースバック+アサーションエラー
  → Codex による深い分析を提案
```

#### コンテキスト保護系フック（ツール実行前）

**`check-codex-before-write.py`** — 設計関連ファイル編集前のチェック

```
DESIGN.md、architecture、schema、model、interface 等を含むファイルへの書き込み前
  → Codex に設計レビューを相談することを提案
```

**`suggest-gemini-research.py`** — 大規模リサーチの委譲提案

```
WebSearch/WebFetch の使用前に、クエリが100文字以上 or 包括的リサーチを検出
  → サブエージェントへの委譲を提案（メインのコンテキスト節約）
```

#### 監査系フック

**`log-cli-tools.py`** — 全CLI呼び出しの記録

```
codex/gemini コマンドの実行を検出
  → .claude/logs/cli-tools.jsonl にJSONL形式でログ
  → タイムスタンプ、ツール名、モデル、プロンプト、レスポンス、成功/失敗
```

**`post-implementation-review.py`** — 実装レビューのタイミング提案

```
3ファイル以上 or 100行以上の変更が蓄積
  → Codex によるコードレビューを提案
```

**`check-codex-after-plan.py`** — 計画完了後のレビュー提案

```
Task（plan タイプ）完了後
  → Codex による計画のレビューを提案
```

#### Agent Teams 用フック

**`TeammateIdle`** — ワークログ書き忘れ防止

```
Agent Teams のチームメイトがアイドル状態になった時
  → 「タスクリストを確認」「ワークログを書いて」とリマインド
```

### スラッシュコマンド — ワンコマンドで複雑なワークフローを実行

15個のスキルが定義されており、複雑なマルチステップのワークフローをスラッシュコマンド一つで起動できる。

#### メインワークフロー（3コマンド）

```
/startproject <機能名>     → Phase 1-3: 理解 → 調査&設計 → 計画
    ↓ 承認後
/team-implement            → Phase 4: Agent Teams で並列実装
    ↓ 完了後
/team-review               → Phase 5: Agent Teams で並列レビュー
```

**`/startproject`** — プロジェクト開始（3フェーズ）

| Phase | 担当 | 内容 |
|-------|------|------|
| 1. UNDERSTAND | Claude Lead | コードベース直読（1M context）、要件ヒアリング、ブリーフ作成 |
| 2. RESEARCH & DESIGN | Agent Teams | Researcher（WebSearch/WebFetch）+ Architect（Codex CLI）を並列スポーン。**双方向通信**で相互フィードバック |
| 3. PLAN & APPROVE | Claude Lead | 調査と設計を統合、実装計画作成、ユーザー承認 |

**`/team-implement`** — 並列実装

| Step | 内容 |
|------|------|
| 1. チーム設計 | 計画を分析し、モジュール別/レイヤー別/機能別にチームメイトを配置 |
| 2. スポーン | Implementer（モジュール別）+ Tester（任意）を並列スポーン。**ファイル所有権を分離**して衝突ゼロ |
| 3. 監視・調整 | リード（Claude）は監視のみ。Ctrl+T でタスク確認、Shift+Up/Down でチームメイト切替 |
| 4. 統合・検証 | lint、型チェック、テストのクオリティゲート |

**`/team-review`** — 並列レビュー（3専門レビュアー）

| レビュアー | 観点 |
|---|---|
| **Security Reviewer** | ハードコードされた秘密情報、インジェクション、入力検証、認証認可、データ露出、依存関係の脆弱性 |
| **Quality Reviewer** | コーディング原則遵守、単一責任、ネスト深度、型ヒント、マジックナンバー、命名、関数長、ライブラリ制約（Codex CLIで深い分析） |
| **Test Reviewer** | カバレッジ、Happy path、エラーケース、境界値、エッジケース、モック、AAAパターン、テスト独立性 |

#### エージェント連携コマンド（2コマンド）

**`/codex-system`** — Codex CLI の明示的呼び出し
- 計画・設計・デバッグ・リファクタリング・コードレビューをCodexに委譲
- トリガー: 「設計して」「計画を立てて」「なぜ動かない？」「AとBどちらがいい？」

**`/gemini-system`** — Gemini CLI の明示的呼び出し
- マルチモーダルファイルの内容抽出
- 対象拡張子が登場した時点で**自動発動**（ユーザー指示不要）

#### 開発支援コマンド（5コマンド）

| コマンド | 用途 | 詳細 |
|---------|------|------|
| `/plan` | 実装計画 | `/startproject` より軽量。要件→調査→ステップ分解→検証基準を出力 |
| `/tdd` | テスト駆動開発 | Red（失敗テスト）→ Green（最小実装）→ Refactor のサイクル。カバレッジ目標80%以上 |
| `/simplify` | コード簡素化 | 5原則（単一責任、短い関数、浅いネスト、明確な命名、型ヒント）に基づくリファクタ |
| `/research-lib` | ライブラリ調査 | WebSearch で調査 → `.claude/docs/libraries/{ライブラリ名}.md` に包括的ドキュメント生成 |
| `/init` | プロジェクト初期化 | 技術スタック自動検出 → AGENTS.md 更新 |

#### ドキュメント管理コマンド（3コマンド）

| コマンド | 用途 | 特徴 |
|---------|------|------|
| `/design-tracker` | 設計決定の自動記録 | **プロアクティブ発動**（設計の議論を検出すると自動で DESIGN.md を更新） |
| `/update-design` | 設計文書の明示的更新 | ユーザーが意図的に更新したい時 |
| `/update-lib-docs` | ライブラリ文書更新 | 最新バージョン、破壊的変更、セキュリティアップデートをチェック |

#### セッション管理コマンド（1コマンド）

**`/checkpointing`** — セッション全体の記録

| 記録内容 | 詳細 |
|---------|------|
| Git履歴 | コミットハッシュ、メッセージ、日付、ファイル変更（行数統計付き） |
| CLI呼び出し | Codex/Gemini のプロンプトと結果、成功/失敗ステータス |
| Agent Teams | チーム構成、タスクリスト状態、ファイル所有権、通信パターン |
| ワークログ | 各チームメイトのサマリー、タスク、ファイル、判断、問題 |
| 設計決定 | DESIGN.md の変更差分 |

**出力先**: `.claude/checkpoints/YYYY-MM-DD-HHMMSS.md`
**ボーナス機能**: 再利用可能なスキルパターンの自動発見（信頼度スコア付き）

### ルール — 「毎回考えなくていい」規約集

7つのルールファイル（`.claude/rules/`）が開発規約を定義。Claude は常にこれらに従うため、ユーザーが都度指示する必要がない。

| ルール | 内容 |
|--------|------|
| `coding-principles.md` | シンプルさ優先、単一責任、早期リターン、型ヒント必須、不変性、命名規則、マジックナンバー禁止 |
| `testing.md` | TDD推奨、カバレッジ80%以上、AAAパターン、テスト命名規則、フィクスチャ活用 |
| `dev-environment.md` | uv（pip禁止）、ruff（lint/format）、ty（型チェック）、marimo（ノートブック）、poe（タスクランナー） |
| `security.md` | 秘密情報管理、入力検証（Pydantic）、SQLパラメータ化、XSS防止、エラーメッセージ最小化 |
| `language.md` | 思考・コード→英語、ユーザー対話→日本語 |
| `codex-delegation.md` | Codex への委譲ルール（いつ使う、いつ使わない、呼び出し方法） |
| `gemini-delegation.md` | Gemini への委譲ルール（マルチモーダル専用、自動トリガー条件） |

---

## 4. カスタマイズを楽しんで！

このテンプレートは **すべてがファイルベース** で構成されているため、自由にカスタマイズできる。

### ディレクトリ構成 — 何がどこにあるか

```
claude-code-orchestra/
├── CLAUDE.md                         # メイン設定ドキュメント
├── pyproject.toml                    # Python 設定（uv/ruff/ty/pytest/poe）
│
├── .claude/                          # ★ Claude Code 設定の中心
│   ├── settings.json                 # 全体設定（フック、権限、環境変数）
│   │
│   ├── agents/                       # サブエージェント定義
│   │   ├── general-purpose.md        #   汎用（調査・実装・Codex委譲）
│   │   ├── codex-debugger.md         #   エラー分析（Codex CLI駆動）
│   │   └── gemini-explore.md         #   マルチモーダル読取
│   │
│   ├── skills/                       # スラッシュコマンド（14スキル）
│   │   ├── startproject/SKILL.md     #   /startproject
│   │   ├── team-implement/SKILL.md   #   /team-implement
│   │   ├── team-review/SKILL.md      #   /team-review
│   │   ├── codex-system/SKILL.md     #   /codex-system （+ 5リファレンス）
│   │   ├── gemini-system/SKILL.md    #   /gemini-system （+ 2リファレンス）
│   │   ├── plan/SKILL.md             #   /plan
│   │   ├── tdd/SKILL.md              #   /tdd
│   │   ├── simplify/SKILL.md         #   /simplify
│   │   ├── research-lib/SKILL.md     #   /research-lib
│   │   ├── init/SKILL.md             #   /init
│   │   ├── design-tracker/SKILL.md   #   /design-tracker
│   │   ├── update-design/SKILL.md    #   /update-design
│   │   ├── update-lib-docs/SKILL.md  #   /update-lib-docs
│   │   └── checkpointing/SKILL.md    #   /checkpointing
│   │
│   ├── hooks/                        # 自動化フック（9スクリプト）
│   │   ├── agent-router.py           #   入力ルーティング
│   │   ├── check-codex-before-write.py  #  設計レビュー提案
│   │   ├── check-codex-after-plan.py #   計画レビュー提案
│   │   ├── error-to-codex.py         #   エラー → codex-debugger
│   │   ├── post-test-analysis.py     #   テスト失敗分析
│   │   ├── lint-on-save.py           #   自動lint（ruff + ty）
│   │   ├── post-implementation-review.py  # 実装レビュータイミング
│   │   ├── suggest-gemini-research.py #  リサーチ委譲提案
│   │   └── log-cli-tools.py          #   CLI呼び出しログ
│   │
│   ├── rules/                        # 開発規約（7ファイル）
│   │   ├── coding-principles.md
│   │   ├── testing.md
│   │   ├── dev-environment.md
│   │   ├── security.md
│   │   ├── language.md
│   │   ├── codex-delegation.md
│   │   └── gemini-delegation.md
│   │
│   ├── docs/                         # ドキュメント永続化
│   │   ├── DESIGN.md                 #   設計決定記録
│   │   ├── research/                 #   調査結果
│   │   └── libraries/                #   ライブラリ制約
│   │
│   ├── logs/                         # ログ
│   │   ├── cli-tools.jsonl           #   Codex/Gemini 呼び出しログ
│   │   └── agent-teams/              #   チームメイトワークログ
│   │
│   └── checkpoints/                  # セッションチェックポイント
│
├── .codex/                           # Codex CLI 設定
│   ├── AGENTS.md                     #   ペルソナ定義
│   ├── config.toml                   #   モデル設定
│   └── skills/context-loader/        #   コンテキストローダー
│
└── .gemini/                          # Gemini CLI 設定
    ├── GEMINI.md                     #   ペルソナ定義
    ├── settings.json                 #   モデル設定
    └── skills/context-loader/        #   コンテキストローダー
```

### カスタマイズポイント

#### 1. CLAUDE.md — プロジェクトの「憲法」

`CLAUDE.md` はプロジェクトのルートにある最重要ファイル。Claude Code が最初に読む設定文書であり、エージェントの役割分担、判断フロー、ワークフロー、技術スタックがすべて記載されている。

**カスタマイズ例**:
- 技術スタックの変更（Python → TypeScript など）
- エージェント役割の調整
- ワークフローの変更

#### 2. `.claude/rules/` — 開発規約の追加・変更

ルールファイルは Markdown で記述されており、自由に追加・変更できる。

**カスタマイズ例**:
- `coding-principles.md` にプロジェクト固有のルールを追加
- 新しいルールファイル（例: `api-design.md`、`database.md`）を作成
- 不要なルールの削除

#### 3. `.claude/skills/` — 独自スラッシュコマンドの作成

スキルは `SKILL.md` ファイル一つで定義できる。

**カスタマイズ例**:
- `/deploy` — デプロイワークフローを自動化
- `/migration` — DBマイグレーションの手順化
- `/api-design` — API設計のテンプレート化

#### 4. `.claude/hooks/` — 自動化の追加

フックは Python スクリプトで記述し、`settings.json` で登録する。

**カスタマイズ例**:
- 特定ファイル（`*.sql`）編集時にセキュリティチェックを追加
- テスト成功時に自動コミットを提案
- 特定のライブラリ使用時に制約ドキュメントを表示

#### 5. `.claude/agents/` — サブエージェントの追加

サブエージェント定義は Markdown の YAML フロントマター + 本文で構成される。

```markdown
---
name: my-custom-agent
description: "カスタムエージェントの説明"
tools: Read, Bash, Grep, Glob
model: sonnet
---

エージェントの指示をここに記述...
```

#### 6. `.codex/` / `.gemini/` — 外部CLIのペルソナ調整

`AGENTS.md`（Codex）や `GEMINI.md`（Gemini）を編集して、ペルソナや出力フォーマットをカスタマイズできる。

#### 7. `settings.json` — 権限・環境変数

```json
{
  "permissions": {
    "allow": ["Read", "Edit", "Write", ...],
    "deny": [".env files", "*.pem", "credentials.*"]
  },
  "env": {
    "CLAUDE_CODE_ENABLE_AGENT_TEAMS": "1",
    "CLAUDE_CODE_SUBAGENT_MODEL": "claude-sonnet-4-5"
  }
}
```

### クイックスタート

既存プロジェクトに適用する場合:

```bash
git clone --depth 1 https://github.com/DeL-TaiseiOzaki/claude-code-orchestra.git .starter \
  && cp -r .starter/.claude .starter/.codex .starter/.gemini .starter/CLAUDE.md . \
  && rm -rf .starter \
  && claude
```

その後 `/init` を実行して、プロジェクト固有の設定を自動検出させる。

### 前提条件

```bash
# Claude Code
npm install -g @anthropic-ai/claude-code && claude login

# Codex CLI
npm install -g @openai/codex && codex login

# Gemini CLI
npm install -g @google/gemini-cli && gemini login
```

---

## まとめ

| 観点 | このテンプレートのアプローチ |
|------|---------------------------|
| **コンテキスト処理** | サブエージェントによる隔離、ファイル永続化、Agent Teams での双方向通信、Compaction 対策 |
| **適材適所** | Claude（全体統括・コード分析）、Codex（計画・設計・難実装）、Gemini（マルチモーダル読取専用） |
| **認知負荷軽減** | 9つの自動フック、15のスラッシュコマンド、7つのルールファイル |
| **カスタマイズ性** | すべてファイルベース（Markdown + Python + JSON/TOML）で自由に拡張可能 |
