# Claude Code Orchestra テンプレート概要

## 1. 設計思想

- Claude Code を **オーケストレーター** として使い、直接実装ではなく委譲に徹する。
- 「会話品質」と「コンテキスト節約」が最優先。Opus 1M context を主 Claude で温存する。
- **三層委譲モデル**: Codex（設計・計画・複雑実装）/ Opus subagent（研究・コード実装・コードベース解析）/ Gemini（マルチモーダル PDF/動画/音声/画像）。
- 大規模タスク（10 LOC 超、3 ファイル以上読む、2 ファイル以上編集、設計判断を含む）は必ず委譲するのがコントラクト。
- Python 側は `uv` + `ruff` + `ty` + `pytest` + `poethepoet` の Astral 系ツールチェーンで統一。

## 2. ディレクトリ構造（tree 風）

```
claude-code-orchestra/
├── CLAUDE.md                    # Orchestrator Contract（3ゾーン: Zone A=template / Zone B=init / Zone C=working）
├── README.md / LICENSE / VERSION / summary.png
├── pyproject.toml / uv.lock     # uv + ruff + ty + pytest + poe
├── scripts/
│   └── update.sh                # テンプレート更新スクリプト
├── .claude/
│   ├── settings.json            # hooks/permissions/env 設定
│   ├── agents/                  # 3 個のサブエージェント定義
│   ├── skills/                  # 17 個のスキル (SKILL.md + references/)
│   ├── hooks/                   # 9 個の Python 自動化フック
│   ├── rules/                   # 7 個の運用ルール
│   └── docs/                    # DESIGN.md / CODEX_HANDOFF_PLAYBOOK.md / research/ / libraries/
├── .codex/                      # Codex CLI 側設定
│   ├── AGENTS.md / config.toml
│   └── skills/{context-loader,design-tracker}/
└── .gemini/                     # Gemini CLI 側設定
    ├── GEMINI.md / settings.json
    └── skills/context-loader/
```

## 3. ルール一覧（`.claude/rules/`）

- `coding-principles.md`: Simplicity First / Single Responsibility / Early Return / Type Hints 必須 / 不変性 / 命名規約。
- `testing.md`: TDD 推奨、AAA パターン、`test_{対象}_{条件}_{結果}` 命名、カバレッジ 80% 目標、`uv run pytest` コマンド集。
- `dev-environment.md`: `uv`（pip 禁止）/ `ruff` / `ty` / `marimo` / `poe` タスク定義、プリコミットチェックリスト。
- `security.md`: 秘匿情報管理、Pydantic 入力検証、SQL インジェクション・XSS 防止、エラーメッセージ粒度。
- `language.md`: 思考・コードは英語、ユーザー応答は日本語、ドキュメントは英語。
- `codex-delegation.md`: Codex-first ポリシー、プロンプト契約（Objective/Constraints/Files/Checks/Format）、plugin（`/codex:review` 等）vs 直接 CLI の使い分け。
- `gemini-delegation.md`: Gemini はマルチモーダル専用、対応拡張子一覧、研究用途では使わない。

## 4. スキル一覧（`.claude/skills/`）

> 全 18 個。システムリマインダーで列挙された `update-config / keybindings-help / less-permission-prompts / loop / claude-api / session-start-hook / security-review / review` は本テンプレートには **存在しない**（注意点 §9 参照）。

### コアワークフロー（プロジェクト開始〜レビュー）
- `start-feature` — 明示 `/start-feature` — Phase1-3 の新機能キックオフ（Opus codebase 解析 → Agent Teams 並列リサーチ＆設計 → 統合承認）。
- `team-implement` — 明示 `/team-implement` — モジュール別 Teammate による並列実装、ファイル所有分離とタスクリスト共有で自律協調。
- `team-review` — 明示 `/team-review` — Security/Quality/Test の 3 Reviewer 並列レビュー（Codex 活用）。
- `add-feature` — 明示 `/add-feature` — 既存コードベースへの軽量追加。複雑度で SIMPLE/MODERATE/COMPLEX にルーティング。
- `spike` — 明示 `/spike` — Time-boxed 技術調査、go/no-go 判断ドキュメントを生成（実装計画ではない）。

### 実装補助
- `plan` — `disable-model-invocation: true`（ユーザー明示呼び出しのみ） — 要件分解から実装ステップ・依存・リスクを文書化。
- `tdd` — 明示呼び出し専用 — Red-Green-Refactor サイクル実施。
- `simplify` — 明示呼び出し専用 — 関数 20 行以下・ネスト 2 以下を目指すリファクタ。
- `troubleshoot` — 明示 `/troubleshoot` — Codex-first 3-Phase 原因分析（再現→Agent Teams 並列診断→修正計画）。

### 委譲システム
- `codex-system` — トリガー語「plan / design / architecture / debug / complex / optimize」— Codex CLI 連携の二役（計画・設計／複雑実装）を説明。
- `gemini-system` — `.pdf / .mp4 / .mov / .mp3 / .wav / .m4a` 検知で自動起動 — Gemini によるマルチモーダル抽出。

### 調査・ドキュメント
- `research-lib` — 明示 `/research-lib <lib>` — Opus subagent が WebSearch でライブラリを調査し `docs/libraries/` へ出力。
- `update-lib-docs` — 明示呼び出し専用 — 既存 `docs/libraries/` を最新情報で更新。
- `design-tracker` — **PROACTIVE**（アーキテクチャ議論検知で自動起動） — `DESIGN.md` へ設計判断を追記。
- `update-design` — 明示呼び出し専用 — design-tracker と同ワークフローを手動強制起動。

### セッション・設定
- `checkpointing` — 明示 `/checkpointing` — git 履歴・CLI consult・Agent Teams 活動を全記録し再利用可能スキルパターンを発見。
- `catchup` — 明示 `/catchup` — リポジトリ全体（git・CLAUDE/AGENTS・rules・skills・DESIGN/research/libraries・checkpoints・agent-teams ログ）を Opus subagent で包括スキャンし、ルート直下に `GUIDE.md` を生成（新規/復帰コントリビューター向け）。
- `init` — 明示 `/init` 専用 — プロジェクト構造解析、技術スタック自動検出、AGENTS.md のプロジェクト固有セクションを更新。

## 5. サブエージェント一覧（`.claude/agents/`）

- `general-purpose` (tools: Read/Edit/Write/Bash/Grep/Glob/WebFetch/WebSearch, model: opus) — 実装・研究・コードベース解析・Codex 委譲のメイン実行役。
- `codex-debugger` (tools: Read/Edit/Write/Bash/Grep/Glob, model: opus) — エラー・テスト失敗・ビルド失敗時の Codex CLI 深掘り分析専門。hooks から自動提案される。
- `gemini-explore` (tools: Read/Bash/Grep/Glob/WebFetch/WebSearch, model: opus) — Gemini CLI 経由で PDF/動画/音声/画像を抽出するマルチモーダル専用。

## 6. スラッシュコマンド一覧

`.claude/commands/` ディレクトリは **存在しない**。スラッシュコマンドはすべて `.claude/skills/*/SKILL.md` の frontmatter を介して提供される（`/start-feature`, `/team-implement`, `/team-review`, `/add-feature`, `/spike`, `/plan`, `/tdd`, `/simplify`, `/troubleshoot`, `/codex-system`, `/gemini-system`, `/research-lib`, `/update-lib-docs`, `/design-tracker`, `/update-design`, `/checkpointing`, `/catchup`, `/init` の 18 個）。
外部の Codex プラグイン `/codex:review`, `/codex:adversarial-review`, `/codex:rescue`, `/codex:status|result|cancel` は別途 `/plugin install codex@openai-codex` で導入。

## 7. 開発環境（`pyproject.toml`）

- Python >=3.11、ビルドバックエンド `hatchling`、ランタイム依存なし。
- Dev: `ruff>=0.8` / `ty>=0.1` / `pytest>=8.0` / `poethepoet>=0.31`。
- ruff: line-length=88, select=E/W/F/I/B/UP, quote-style=double。
- pytest: `testpaths=tests`, `pythonpath=src`, `-v --tb=short`。
- poe tasks: `lint` / `format` / `typecheck` / `test` / `all`。
- パッケージ管理は `uv` 必須（`pip` 直接利用禁止）。

## 8. 使い方の典型フロー

### 新機能キックオフ（大規模）
```
/start-feature <feature>    # Phase 1-3: Opus 解析 → Agent Teams 研究＆設計 → 承認
  ↓
/team-implement             # Phase 4: モジュール並列実装
  ↓
/team-review                # Phase 5: Security / Quality / Test 並列レビュー
  ↓
/checkpointing              # セッション保存 + パターン抽出
```

### 既存コードベースへの追加
```
/add-feature <feature>      # 複雑度判定 → Codex 直接 or /team-* ルート
  ↓ (COMPLEX 判定時)
/team-implement → /team-review
```

### 技術調査〜導入
```
/spike <question>           # go/no-go 判断ドキュメント
  ↓ (GO 時)
/add-feature or /start-feature
```

### エラー対応
```
/troubleshoot <error>       # Codex-first で原因分析 → 修正計画
  ↓
/team-implement             # 修正実装
```

### 補助ループ
- アーキテクチャ議論時 → `design-tracker` が自動で `DESIGN.md` に追記。
- PDF/動画/音声混入 → `gemini-system` が自動起動。
- Bash エラー検知 → hook が `codex-debugger` 起用を提案。

## 9. 注意点・未整備な点

- **`/.claude/commands/` ディレクトリは未作成**。slash command はすべて `skills/` 配下で定義されている。
- **`docs/research/` と `docs/libraries/` は `.gitkeep` のみ**（テンプレート配布時は空）。ユーザーはここに Opus subagent の調査結果を蓄積する前提。
- **システムリマインダー記載の以下スキルは本テンプレートに存在しない**: `update-config`, `keybindings-help`, `less-permission-prompts`, `loop`, `claude-api`, `session-start-hook`, `review`, `security-review`。これらは Anthropic 標準スキル（Claude Code 本体同梱）であり、本プロジェクトはそれらを上書きせず、プロジェクト固有の 17 個を追加する構成。
- `CLAUDE.md` は **3 ゾーン構造**: Zone A（`@orchestra:template-boundary` の上、テンプレ所有、update.sh で差し替え）/ Zone B（2 マーカー間、`/init` が書く Repository Identity、保持）/ Zone C（`@orchestra:repo-boundary` の下、`/start-feature` 等が追記、保持）。旧 `@orchestra:local-boundary` 方式は `update.sh` が自動移行する（legacy 以下 → Zone C、Zone B はプレースホルダにリセットして `/init` 再実行を促す）。
- `.claude/settings.json` は update 時に diff 表示のみで **自動マージされない**（手動マージ必須）。
- Codex プラグイン（`/codex:review` 等）は別途 `/plugin install` が必要。
- `.codex/config.toml` は `approval_policy = "never"` で非対話フローのブロッキング回避を図る（実行時は承認が出ない点に注意）。
- Python 依存は空 (`dependencies = []`)。LLM/Agent プロジェクト想定だが、ライブラリは利用者が追加する前提。
