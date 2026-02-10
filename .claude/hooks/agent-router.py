#!/usr/bin/env python3
"""
UserPromptSubmit hook: Route to appropriate agent based on user intent.

Analyzes user prompts and suggests the most appropriate agent
(Codex for design/debug, Gemini for research/multimodal).
"""

import json
import sys

# Triggers for Codex (design, debugging, deep reasoning)
CODEX_TRIGGERS = {
    "ja": [
        "設計",
        "どう設計",
        "アーキテクチャ",
        "なぜ動かない",
        "エラー",
        "バグ",
        "デバッグ",
        "どちらがいい",
        "比較して",
        "トレードオフ",
        "実装方法",
        "どう実装",
        "リファクタリング",
        "リファクタ",
        "レビュー",
        "見て",
        "考えて",
        "分析して",
        "深く",
        # Additional proactive triggers
        "どうすべき",
        "良い方法",
        "ベストプラクティス",
        "パターン",
        "改善",
        "最適化",
        "パフォーマンス",
        "セキュリティ",
        "テスト戦略",
        "テスト設計",
        "依存関係",
        "循環",
        "複雑",
        "わからない",
        "迷って",
        "不安",
        "自信がない",
        "相談",
        "意見",
        "アドバイス",
    ],
    "en": [
        "design",
        "architecture",
        "architect",
        "debug",
        "error",
        "bug",
        "not working",
        "fails",
        "compare",
        "trade-off",
        "tradeoff",
        "which is better",
        "how to implement",
        "implementation",
        "refactor",
        "simplify",
        "review",
        "check this",
        "think",
        "analyze",
        "deeply",
        # Additional proactive triggers
        "best practice",
        "pattern",
        "approach",
        "improve",
        "optimize",
        "performance",
        "security",
        "test strategy",
        "test design",
        "dependency",
        "circular",
        "complex",
        "not sure",
        "unsure",
        "uncertain",
        "advice",
        "should i",
        "should we",
        "what if",
        "why does",
        "why is",
        "how come",
        "alternative",
        "option",
        "better way",
    ],
}

# Triggers for Gemini (research, multimodal, large context)
GEMINI_TRIGGERS = {
    "ja": [
        "調べて",
        "リサーチ",
        "調査",
        "PDF",
        "動画",
        "音声",
        "画像",
        "コードベース全体",
        "リポジトリ全体",
        "最新",
        "ドキュメント",
        "ライブラリ",
        "パッケージ",
    ],
    "en": [
        "research",
        "investigate",
        "look up",
        "find out",
        "pdf",
        "video",
        "audio",
        "image",
        "entire codebase",
        "whole repository",
        "latest",
        "documentation",
        "docs",
        "library",
        "package",
        "framework",
    ],
}


def detect_agent(prompt: str) -> tuple[str | None, str]:
    """Detect which agent should handle this prompt."""
    prompt_lower = prompt.lower()

    # Check Codex triggers
    for triggers in CODEX_TRIGGERS.values():
        for trigger in triggers:
            if trigger in prompt_lower:
                return "codex", trigger

    # Check Gemini triggers
    for triggers in GEMINI_TRIGGERS.values():
        for trigger in triggers:
            if trigger in prompt_lower:
                return "gemini", trigger

    return None, ""


def main():
    try:
        data = json.load(sys.stdin)
        prompt = data.get("prompt", "")

        # Skip very short prompts (lowered to catch brief commands like "debug this")
        if len(prompt) < 3:
            sys.exit(0)

        agent, trigger = detect_agent(prompt)

        if agent == "codex":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Codex Required] Detected '{trigger}' — you MUST consult Codex before proceeding. "
                        "Codex excels at this type of task. Use codex-debugger subagent for errors, "
                        "or general-purpose subagent for design/analysis: "
                        "`codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
                        '"{task description}"`. Do NOT skip this step.'
                    ),
                }
            }
            print(json.dumps(output))

        elif agent == "gemini":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Agent Routing] Detected '{trigger}' - this task may benefit from "
                        "Gemini CLI's research capabilities. Consider: "
                        '`gemini -p "Research: {topic}" 2>/dev/null` '
                        "for documentation, library research, or multimodal content."
                    ),
                }
            }
            print(json.dumps(output))

        sys.exit(0)

    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
