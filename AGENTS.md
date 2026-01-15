# プロジェクト概要

LLM/エージェント開発プロジェクト

## 言語設定

- **思考・推論**: 英語で行う
- **コード**: 英語（変数名，関数名，コメント，docstring）
- **ユーザーとのやり取り**: 日本語で出力

## 技術スタック

- **言語**: Python
- **パッケージ管理**: uv（必須）
- **開発ツール**:
  - ruff（リント・フォーマット）
  - mypy（型チェック）
  - poe / poethepoet（タスクランナー）
  - pytest（テスト）
- **環境管理**: venv（uv経由で管理）
- **主要ライブラリ**: <!-- 使用ライブラリを記入 -->

---

## 拡張機能

このプロジェクトには以下の拡張機能が設定されています。
Claude Code と Codex CLI の両方で利用可能です。

### Agents（自動委譲）

独立したコンテキストで専門タスクを実行するエージェント：

| エージェント | 用途 | トリガー例 |
|-------------|------|-----------|
| **code-reviewer** | コード変更後のレビュー | 「レビューして」「チェックして」 |
| **lib-researcher** | ライブラリ調査・文書化 | 「このライブラリについて調べて」 |
| **debugger** | エラー調査・修正 | 「エラーが出た」「動かない」 |
| **refactorer** | リファクタリング | 「シンプルにして」「整理して」 |
| **codex-delegate** | [任意] 大規模タスクをCodexに自律委譲 | 10+ファイル影響、明示リクエスト |

### Skills（自動発動）

会話内容に応じて自動的に発動するスキル：

| スキル | 用途 | トリガー例 |
|--------|------|-----------|
| **design-tracker** | 設計決定の記録 | 「記録して」「アーキテクチャ」 |
| **mcp-builder** | MCPサーバー開発ガイド | 「MCPサーバーを作りたい」 |
| **skill-creator** | 新規スキル作成 | 「スキルを作りたい」 |

### Commands（明示的呼び出し）

`/command` で呼び出すコマンド：

| コマンド | 用途 |
|---------|------|
| `/research-lib` | ライブラリを調査してドキュメント化 |
| `/simplify` | 指定コードをシンプルにリファクタリング |
| `/update-design` | 会話から設計ドキュメントを更新 |
| `/update-lib-docs` | ライブラリドキュメントを最新化 |

---

## ドキュメント参照

設計決定・アーキテクチャ・実装方針:
- `.agent/docs/DESIGN.md`

各ライブラリの機能・制約・使用パターン:
- `.agent/docs/libraries/`

## 記憶の整理（自動）

**重要な情報は自動的に記録すること。ユーザーに「覚えておいて」と言われるのを待たない。**

会話中に以下が発生したら、即座に適切な場所に記録する：

| 検出したら | 記録先 | 例 |
|-----------|--------|-----|
| 設計決定・方針決定 | `.agent/docs/DESIGN.md` | 「ReActパターンでいこう」 |
| ライブラリの制約発見 | `.agent/docs/libraries/{name}.md` | 「このAPIは非同期のみ」 |
| プロジェクト固有のルール | この `AGENTS.md` に追記 | 「エラーは日本語で出力」 |

記録後は「DESIGN.mdに記録しました」のように簡潔に報告する。

---

## 開発方針

### コーディング原則
- **シンプルさを最優先** - 複雑なコードより読みやすいコードを選ぶ
- **単一責任** - 1つの関数/クラスは1つのことだけを行う
- **早期リターン** - ネストを浅く保つ
- **型ヒント必須** - すべての関数に型アノテーション
- **英語でコーディング** - 変数名，関数名，コメント，docstringはすべて英語

### ライブラリ管理
- **uvを使用**（pip直接使用は禁止）
- 依存関係は `pyproject.toml` で管理
- 各ライブラリの機能・制約を `.agent/docs/libraries/` に文書化
- ライブラリ間の依存関係・競合に注意

### 情報収集
- **最新情報はWeb検索を活用** - ライブラリの仕様変更，ベストプラクティスは常に確認
- 公式ドキュメント，GitHub Issues，Discussionsを参照
- 不明点は推測せず，必ず調査する

---

## ディレクトリ構造

```
.agent/                    # 共通設定（Claude Code / Codex CLI 共有）
├── docs/
│   ├── DESIGN.md          # 設計ドキュメント
│   └── libraries/         # ライブラリドキュメント
├── skills/                # 共通スキル
└── commands/              # 共通コマンド

.claude/                   # Claude Code 固有設定
├── settings.json          # 権限設定
├── agents/                # Claude Code エージェント
├── skills -> ../.agent/skills    # シンボリックリンク
├── commands -> ../.agent/commands
└── docs -> ../.agent/docs

.codex/                    # Codex CLI 固有設定
├── config.toml            # 設定ファイル
├── skills -> ../.agent/skills    # シンボリックリンク
└── commands -> ../.agent/commands

src/                       # ソースコード
├── agents/                # エージェント実装
├── llm/                   # LLMラッパー・クライアント
├── tools/                 # ツール定義
├── prompts/               # プロンプトテンプレート
└── utils/                 # ユーティリティ

tests/                     # テスト
```

## よく使うコマンド

```bash
# プロジェクト初期化（uv必須）
uv init
uv venv
source .venv/bin/activate  # Linux/Mac

# 依存関係
uv add <package>           # パッケージ追加
uv add --dev <package>     # 開発依存追加
uv sync                    # 依存関係同期

# タスク実行（poethepoet）
poe lint                   # ruff check + format
poe test                   # pytest実行
poe typecheck              # mypy実行
poe all                    # 全チェック実行

# 個別実行
uv run ruff check .
uv run ruff format .
uv run mypy src/
uv run pytest -v --tb=short
```

## 注意事項

- APIキーは環境変数で管理（`.env`はコミットしない）
- トークン消費に注意（特に長いコンテキスト）
- Rate limitに注意（リトライロジック実装推奨）
