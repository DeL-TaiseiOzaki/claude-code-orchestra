# Gemini Delegation Rule

**Gemini CLI は 1M context を活かし、大規模分析・リサーチ・マルチモーダル読取を担当する。**

## Gemini の3つの役割

### 1. コードベース・リポジトリ理解（Codebase Analysis）

- プロジェクト全体の構造分析
- 主要モジュール・責務の把握
- 既存パターン・規約の理解
- 依存関係の分析

> Claude Code のコンテキストは **200K トークン**（実質 140-150K）。
> 大規模コードベースの全体分析は Gemini の **1M context** に委譲する。

### 2. 外部リサーチ・サーベイ（Research & Survey）

- 最新ドキュメント・API仕様の調査
- ライブラリの比較検討・ベストプラクティス
- 技術的なサーベイ・トレンド調査
- 既知の問題・制約の調査

> Gemini CLI は Google Search grounding を内蔵しており、外部情報の取得に最適。

### 3. マルチモーダルファイル読取（Multimodal Reading）

- PDF、動画、音声、画像ファイルの内容抽出
- 図表・ダイアグラムの詳細分析
- 動画の要約・タイムスタンプ抽出
- 音声の文字起こし・要約

## When to Use Gemini

| 状況 | 例 |
|------|------|
| **コードベース分析** | 「プロジェクト全体を理解して」「構造を分析して」 |
| **外部リサーチ** | 「調べて」「リサーチして」「最新のドキュメント」 |
| **ライブラリ調査** | 「ライブラリを比較して」「ベストプラクティスは？」 |
| **マルチモーダル** | PDF/動画/音声/画像ファイルが登場した場合（自動委譲） |

### Trigger Phrases (User Input)

| Japanese | English |
|----------|---------|
| 「コードベースを理解して」「全体構造を見て」 | "Understand the codebase" "Analyze structure" |
| 「調べて」「リサーチして」「サーベイして」 | "Research" "Investigate" "Survey" |
| 「ライブラリを比較」「ベストプラクティス」 | "Compare libraries" "Best practices" |
| 「このPDF/動画/画像を見て」 | "Read this PDF/video/image" |

## When NOT to Use Gemini

- 単純なファイル読み取り（Claude の Read ツールで十分）
- スクリーンショットの単純確認（Claude の Read ツールで直接可能）
- 計画・設計・アーキテクチャ → **Codex** が担当
- デバッグ・エラー解析 → **Codex** が担当
- コード実装 → **Claude / サブエージェント** が担当

## 対象ファイル拡張子（マルチモーダル）

| カテゴリ | 拡張子 |
|----------|--------|
| PDF | `.pdf` |
| 動画 | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| 音声 | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg` |
| 画像（高度な分析） | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg` |

## How to Use

### コードベース分析

```bash
# プロジェクト構造の分析（Gemini がワークスペースを読む）
gemini -p "Analyze this codebase: directory structure, key modules, patterns, dependencies, and architecture" 2>/dev/null

# 特定ファイルの詳細分析
gemini -p "Analyze this code: purpose, patterns, dependencies" < /path/to/file 2>/dev/null
```

### 外部リサーチ

```bash
# ライブラリ調査
gemini -p "Research: {library name}. Find latest version, key features, constraints, best practices, and common pitfalls" 2>/dev/null

# ベストプラクティス調査
gemini -p "Research best practices for {topic}. Include latest recommendations, common patterns, and anti-patterns" 2>/dev/null

# 技術比較
gemini -p "Compare {A} vs {B} for {use case}. Include pros, cons, performance, and community support" 2>/dev/null
```

### マルチモーダルファイル読取

```bash
# PDF — 構造・内容の抽出
gemini -p "Extract: {what information to extract}" < /path/to/file.pdf 2>/dev/null

# 動画 — 要約・キーポイント・タイムスタンプ
gemini -p "Summarize: key concepts, decisions, timestamps" < /path/to/video.mp4 2>/dev/null

# 音声 — 文字起こし・要約
gemini -p "Transcribe and summarize: decisions, action items" < /path/to/audio.mp3 2>/dev/null

# 画像 — 図表・ダイアグラムの詳細分析
gemini -p "Analyze this diagram: components, relationships, data flow" < /path/to/diagram.png 2>/dev/null
```

## Context Management

| 状況 | 推奨方法 |
|------|----------|
| 短い抽出・回答（〜30行） | 直接呼び出しOK |
| 詳細な分析レポート | サブエージェント経由 |
| リサーチ結果 | サブエージェント経由 → ファイル保存 |

### Subagent Pattern（出力が大きい場合）

```
Task tool parameters:
- subagent_type: "gemini-explore"
- run_in_background: true (for parallel work)
- prompt: |
    {task description}

    gemini -p "{prompt}" 2>/dev/null

    Save results to .claude/docs/research/{topic}.md
    Return CONCISE summary (key findings + recommendations).
```

### Direct Call（短い質問・回答）

```bash
gemini -p "Brief question about {topic}" 2>/dev/null
```

## Auto-Trigger（ユーザー指示なしで自動発動）

- タスク内で PDF/動画/音声ファイルが参照されている
- ユーザーがファイルパスを提示し、拡張子がマルチモーダル対象

## Language Protocol

1. Ask Gemini in **English**
2. Receive response in **English**
3. Execute based on findings
4. Report to user in **Japanese**
