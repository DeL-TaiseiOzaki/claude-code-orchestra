#!/usr/bin/env python3
"""
UserPromptSubmit hook: Route to appropriate agent based on user intent.

Routing rules:
- Codebase understanding / large analysis → Opus subagent (1M context)
- External research / survey → Opus subagent
- Planning, design, complex code → Codex CLI

Multimodal files (PDF/video/audio/image) are handled directly by Claude (Opus 4.7+).
"""

import json
import sys

# Triggers for Codex (planning, design, debugging, complex implementation)
CODEX_TRIGGERS = {
    "ja": [
        "設計", "どう設計", "アーキテクチャ",
        "計画", "計画を立てて",
        "なぜ動かない", "エラー", "バグ", "デバッグ",
        "どちらがいい", "比較して", "トレードオフ",
        "実装方法", "どう実装",
        "リファクタリング", "リファクタ",
        "レビュー",
        "考えて", "分析して", "深く",
        "最適化",
    ],
    "en": [
        "design", "architecture", "architect",
        "plan", "planning",
        "debug", "error", "bug", "not working", "fails",
        "compare", "trade-off", "tradeoff", "which is better",
        "how to implement", "implementation", "complex",
        "refactor", "simplify",
        "review", "check this",
        "think", "analyze", "deeply",
        "optimize", "performance",
    ],
}

# Triggers for Opus research (codebase analysis + external research)
OPUS_RESEARCH_TRIGGERS = {
    "ja": [
        "調べて", "リサーチ", "調査", "サーベイ",
        "最新", "ドキュメント",
        "ライブラリ", "パッケージ",
        "コードベース", "リポジトリ", "全体構造",
        "理解して", "把握して",
    ],
    "en": [
        "research", "investigate", "look up", "find out", "survey",
        "latest", "documentation", "docs",
        "library", "package", "framework",
        "codebase", "repository", "project structure",
        "understand", "analyze the code",
    ],
}

# Triggers for Codex Plugin commands (review, rescue, delegation)
CODEX_PLUGIN_TRIGGERS = {
    "ja": [
        "レビューして", "コードレビュー", "レビューお願い",
        "チェックして", "出荷前",
        "codexに任せ", "codexに渡", "codexに委",
        "バグ調査", "調査して",
    ],
    "en": [
        "review this", "code review", "review my",
        "before shipping", "pre-ship",
        "delegate to codex", "hand to codex", "ask codex to",
        "codex rescue", "codex review",
    ],
}


def detect_agent(prompt: str) -> tuple[str | None, str]:
    """Detect which agent should handle this prompt.

    Returns (agent, trigger).
    """
    prompt_lower = prompt.lower()

    # Codex triggers (planning, design, debug, complex code)
    for triggers in CODEX_TRIGGERS.values():
        for trigger in triggers:
            if trigger in prompt_lower:
                return "codex", trigger

    # Codex Plugin triggers (review, rescue, delegation)
    for triggers in CODEX_PLUGIN_TRIGGERS.values():
        for trigger in triggers:
            if trigger in prompt_lower:
                return "codex-plugin", trigger

    # Opus research triggers (codebase analysis + external research)
    for triggers in OPUS_RESEARCH_TRIGGERS.values():
        for trigger in triggers:
            if trigger in prompt_lower:
                return "opus-research", trigger

    return None, ""


def main():
    try:
        data = json.load(sys.stdin)
        prompt = data.get("prompt", "")

        # Skip short prompts
        if len(prompt) < 10:
            sys.exit(0)

        agent, trigger = detect_agent(prompt)

        if agent == "codex":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Agent Routing] Detected '{trigger}' — this task may benefit from "
                        "Codex CLI for planning, design, or complex implementation. Consider: "
                        "`codex exec --model \"${CODEX_MODEL:-gpt-5.4}\" --sandbox read-only "
                        '"{task description}"` for design decisions, planning, debugging, '
                        "or complex analysis."
                    )
                }
            }
            print(json.dumps(output))

        elif agent == "codex-plugin":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Codex Plugin] Detected '{trigger}' — consider using Codex Plugin commands. "
                        "Available: `/codex:review` (code review), "
                        "`/codex:adversarial-review` (design challenge), "
                        "`/codex:rescue` (task delegation). "
                        "Add `--background` for async execution, check with `/codex:status`."
                    )
                }
            }
            print(json.dumps(output))

        elif agent == "opus-research":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Opus Research] Detected '{trigger}' — use a general-purpose subagent (Opus) "
                        "for this task. Opus subagents handle research, codebase analysis, and investigation "
                        "with 1M context and WebSearch/WebFetch. "
                        "Use via general-purpose subagent: "
                        "Agent tool with subagent_type='general-purpose'. "
                        "Save results to .claude/docs/research/."
                    )
                }
            }
            print(json.dumps(output))

        sys.exit(0)

    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
