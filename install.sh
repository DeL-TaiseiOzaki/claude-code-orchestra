#!/bin/bash
# Claude Code Orchestra インストールスクリプト
# 使い方: curl -fsSL https://raw.githubusercontent.com/hira22/claude-code-orchestra/main/install.sh | bash

set -e

REPO_URL="https://github.com/hira22/claude-code-orchestra"
BIN_DIR="$HOME/.local/bin"

echo "🎼 Claude Code Orchestra をインストールします..."

# Download to temp directory
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

echo "→ リポジトリをダウンロード中..."
git clone --depth 1 "$REPO_URL" "$TMP_DIR" 2>/dev/null || {
    echo "エラー: リポジトリのクローンに失敗しました"
    exit 1
}

# Install orchestra-init command
echo "→ コマンドをインストール中..."
mkdir -p "$BIN_DIR"
cp "$TMP_DIR/bin/orchestra-init" "$BIN_DIR/"
chmod +x "$BIN_DIR/orchestra-init"

# PATH check
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "⚠️  $BIN_DIR がPATHに含まれていません。"
    echo "   以下をシェル設定ファイルに追加してください："
    echo ""
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo ""
echo "✅ インストール完了！"
echo ""
echo "使い方:"
echo "  cd /path/to/your/project"
echo "  orchestra-init              # 初回セットアップ"
echo "  orchestra-init              # テンプレート更新（既存環境を検出）"
echo ""
echo "オプション:"
echo "  orchestra-init --ref v1.0   # 特定バージョンを指定"
echo "  ORCHESTRA_REPO=<url> orchestra-init  # リポジトリを指定"
echo ""
echo "前提条件:"
echo "  - Claude Code: npm install -g @anthropic-ai/claude-code"
echo "  - Codex CLI:   npm install -g @openai/codex"
echo "  - Gemini CLI:  npm install -g @google/gemini-cli"
