# Claude Code Orchestra

**マルチエージェント協調フレームワーク（Opus 4.6 + Agent Teams 対応）**

Claude Code が Codex CLI（深い推論）と Gemini CLI（外部情報・マルチモーダル）を統合し、Agent Teams で並列開発を加速する。

---

## Why This Exists

| Agent | Strength | Use For |
|-------|----------|---------|
| **Claude Code** | 1Mコンテキスト、オーケストレーション、Agent Teams | 全体統括、コードベース分析、並列チーム管理 |
| **Codex CLI** | 深い推論、設計判断、デバッグ | 設計相談、エラー分析、トレードオフ評価 |
| **Gemini CLI** | Google Search、マルチモーダル | 外部情報取得、ライブラリ調査、PDF/動画/音声処理 |

> **Opus 4.6 での変化**: Claude 自身が 1M トークンのコンテキストを持つようになったため、コードベース分析は Claude が直接行う。Gemini の役割は「外部情報の取得」と「マルチモーダル処理」に特化した。

---

## Context Management

Claude Code (Opus 4.6) のコンテキストは **1M トークン**（実質 **350-500k**、ツール定義等で縮小）。

**Compaction 機能**により、長時間セッションでもサーバーサイドで自動要約される。

### Codex/Gemini 呼び出し基準

| 出力サイズ | 方法 | 理由 |
|-----------|------|------|
| 短い（〜50行） | 直接呼び出しOK | 1Mコンテキストで十分吸収可能 |
| 大きい（50行以上） | サブエージェント経由を推奨 | コンテキスト効率化 |
| 分析レポート | サブエージェント → ファイル保存 | 詳細は `.claude/docs/` に永続化 |

### 並列処理の選択

| 目的 | 方法 | 適用場面 |
|------|------|----------|
| 結果を取得するだけ | サブエージェント | Codex設計相談、Gemini調査 |
| 相互通信が必要 | **Agent Teams** | Research↔Design、並列実装、並列レビュー |

---

## Quick Reference

### Codex を使う時

- 設計判断（「どう実装？」「どのパターン？」）
- デバッグ（「なぜ動かない？」「エラーの原因は？」）
- 比較検討（「AとBどちらがいい？」）

→ 詳細: `.claude/rules/codex-delegation.md`

### Gemini を使う時

- 外部リサーチ（「最新のドキュメントは？」「ライブラリを調べて」）
- マルチモーダル（「このPDF/動画/音声を見て」）

> **注意**: コードベース分析は Claude が直接行う。Gemini への委託は不要。

→ 詳細: `.claude/rules/gemini-delegation.md`

---

## Workflow

```
/startproject <機能名>     Phase 1-3: 理解 → 調査&設計 → 計画
    ↓ 承認後
/team-implement            Phase 4: Agent Teams で並列実装
    ↓ 完了後
/team-review               Phase 5: Agent Teams で並列レビュー
```

1. Claude がコードベースを直接読み（1Mコンテキスト）、ユーザーと要件ヒアリング
2. Agent Teams で Researcher（Gemini）+ Architect（Codex）を並列起動
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
| `.claude/docs/research/` | 調査結果（Gemini / レビュー） |
| `.claude/docs/libraries/` | ライブラリ制約ドキュメント |
| `.claude/logs/cli-tools.jsonl` | Codex/Gemini入出力ログ |

---

## Language Protocol

- **思考・コード**: 英語
- **ユーザー対話**: 日本語
