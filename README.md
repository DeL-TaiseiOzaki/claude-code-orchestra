# fastslow-claude-code

Claude Code (Fast/System 1) と Codex CLI (Slow/System 2) の設定を既存プロジェクトに導入するスターターキット。

## 導入方法

```bash
# 1. 既存プロジェクトのルートで実行
git clone --depth 1 https://github.com/DeL-TaiseiOzaki/fastslow-claude-code.git .starter

# 2. 必要なファイルをコピー
cp -r .starter/.agent .starter/.claude .starter/.codex .starter/AGENTS.md .
cp -P .starter/CLAUDE.md .

# 3. クリーンアップ
rm -rf .starter

# 4. プロジェクトを初期化
claude  # Claude Code を起動
/init   # AGENTS.md を自動生成
```

**ワンライナー:**
```bash
git clone --depth 1 https://github.com/DeL-TaiseiOzaki/fastslow-claude-code.git .starter && cp -r .starter/.agent .starter/.claude .starter/.codex .starter/AGENTS.md . && cp -P .starter/CLAUDE.md . && rm -rf .starter
```

## Codex CLI プロンプトの設定（任意）

Codex CLI のカスタムコマンドはユーザーレベルで設定が必要:

```bash
# Codex 用プロンプトをコピー
cp .codex/prompts/*.md ~/.codex/prompts/
```

## 構成

```
.claude/          # Claude Code 設定
├── agents/       # サブエージェント（自動委譲）
├── rules/        # 常時適用ルール
├── docs/         # 知識ベース
└── settings.json # 権限設定

.agent/           # 共通ツール
├── commands/     # コマンド（/init, /plan, /tdd 等）
└── skills/       # スキル（自動発動）

.codex/           # Codex CLI 設定
├── skills/       # スキル（自動発動）
└── prompts/      # プロンプト（~/.codex/prompts/ へコピー）

AGENTS.md         # プロジェクト設定（両ツール共通）
CLAUDE.md         # AGENTS.md へのシンボリックリンク
```

## ライセンス

MIT
