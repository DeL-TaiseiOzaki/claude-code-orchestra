#!/usr/bin/env python3
"""
UserPromptSubmit hook: Route to appropriate agent based on user intent.

Routing rules:
- Multimodal files (PDF/video/audio/image) → Gemini CLI (HIGHEST PRIORITY)
- Codebase understanding / large analysis → Gemini CLI (1M context)
- External research / survey → Gemini CLI (Google Search grounding)
- Planning, design, complex code → Codex CLI
"""

import json
import re
import sys

# Multimodal file extensions that MUST be processed by Gemini
MULTIMODAL_EXTENSIONS = [
    # PDF
    ".pdf",
    # Video
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    # Audio
    ".mp3", ".wav", ".m4a", ".flac", ".ogg",
    # Image (for detailed analysis — screenshots can be read by Claude directly)
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
]

# Pattern to detect file paths with multimodal extensions
MULTIMODAL_PATTERN = re.compile(
    r'[\w./\\~-]+\.(?:' +
    '|'.join(ext.lstrip('.') for ext in MULTIMODAL_EXTENSIONS) +
    r')(?:\s|$|["\']|,)',
    re.IGNORECASE,
)

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

# Triggers for Gemini research (codebase analysis + external research)
GEMINI_RESEARCH_TRIGGERS = {
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


def detect_multimodal_files(prompt: str) -> str | None:
    """Detect multimodal file references in the prompt. Returns matched file path or None."""
    match = MULTIMODAL_PATTERN.search(prompt)
    if match:
        return match.group(0).strip().rstrip('"\',')
    return None


def detect_agent(prompt: str) -> tuple[str | None, str, bool]:
    """Detect which agent should handle this prompt.

    Returns (agent, trigger, is_multimodal).
    """
    prompt_lower = prompt.lower()

    # HIGHEST PRIORITY: Multimodal file detection → Gemini
    multimodal_file = detect_multimodal_files(prompt)
    if multimodal_file:
        return "gemini-multimodal", multimodal_file, True

    # Codex triggers (planning, design, debug, complex code)
    for triggers in CODEX_TRIGGERS.values():
        for trigger in triggers:
            if trigger in prompt_lower:
                return "codex", trigger, False

    # Gemini research triggers (codebase analysis + external research)
    for triggers in GEMINI_RESEARCH_TRIGGERS.values():
        for trigger in triggers:
            if trigger in prompt_lower:
                return "gemini-research", trigger, False

    return None, "", False


def main():
    try:
        data = json.load(sys.stdin)
        prompt = data.get("prompt", "")

        # Skip short prompts
        if len(prompt) < 10:
            sys.exit(0)

        agent, trigger, is_multimodal = detect_agent(prompt)

        if is_multimodal:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Multimodal File Detected] Found '{trigger}' in prompt. "
                        "**MUST** use Gemini CLI to process this file. "
                        "Pass the file to Gemini with specific extraction instructions: "
                        f'`gemini -p "Extract: {{what to extract}}" < {trigger} 2>/dev/null` '
                        "Do NOT attempt to read this file directly — use Gemini for content extraction."
                    )
                }
            }
            print(json.dumps(output))

        elif agent == "codex":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Agent Routing] Detected '{trigger}' — this task may benefit from "
                        "Codex CLI for planning, design, or complex implementation. Consider: "
                        "`codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
                        '"{task description}"` for design decisions, planning, debugging, '
                        "or complex analysis."
                    )
                }
            }
            print(json.dumps(output))

        elif agent == "gemini-research":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Gemini Research] Detected '{trigger}' — use Gemini CLI (1M context) "
                        "for this task. Gemini handles codebase analysis and external research "
                        "with its native 1M context and Google Search grounding. "
                        "Use via gemini-explore subagent or direct call: "
                        '`gemini -p "{research/analysis prompt}" 2>/dev/null` '
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
