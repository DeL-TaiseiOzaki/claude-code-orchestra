#!/usr/bin/env python3
"""
UserPromptSubmit hook: Route to appropriate agent based on user intent.

Routing rules (checked in order, most specific first):
- Design arbitration / stuck problems / final review → Fable advisor (rare)
- Explicit code-review phrases → general-purpose-opus review
- Planning, design, debugging, complex code → general-purpose-opus / Plan / debugger
- Codebase understanding / large analysis / external research → Opus subagent

Multimodal files (PDF/video/audio/image) are handled directly by Claude (Opus 4.7+).
"""

import json
import re
import sys

# Triggers for Fable advisor (rare escalation: arbitration, stuck, final review)
FABLE_TRIGGERS = {
    "ja": [
        "設計判断に迷",
        "設計の裁定",
        "裁定して",
        "行き詰ま",
        "詰まった",
        "打開",
        "最終レビュー",
        "最終判断",
        "方針を決めて",
        "方針決定",
        "fableに聞",
        "fableに相談",
        "アドバイザー",
    ],
    "en": [
        "design arbitration",
        "arbitrate",
        "settle this",
        "stuck",
        "deadlocked",
        "blocked on design",
        "final review",
        "final judgment",
        "second opinion",
        "ask fable",
        "fable advisor",
        "advisor",
    ],
}

# Triggers for deep reasoning (planning, design, debugging, complex
# implementation): routed to general-purpose-opus, the built-in Plan agent, or
# the debugger subagent.
DEEP_REASONING_TRIGGERS = {
    "ja": [
        "設計",
        "どう設計",
        "アーキテクチャ",
        "計画",
        "計画を立てて",
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
        "考えて",
        "分析して",
        "深く",
        "最適化",
        # Proactive triggers: uncertainty and quality questions are exactly
        # where a deep-reasoning consult is cheaper than the rework it prevents.
        # Single words that name a topic rather than a request for judgement
        # ("パターン", "改善", "セキュリティ", "依存関係", "相談", "意見",
        # "複雑") are deliberately absent: they fired on ordinary asks such as
        # "セキュリティヘッダーを追加して" and even "相談なんだけど昼食は?".
        "どうすべき",
        "良い方法",
        "ベストプラクティス",
        "パフォーマンス",
        "テスト戦略",
        "テスト設計",
        "循環",
        "わからない",
        "迷って",
        "不安",
        "自信がない",
        "アドバイス",
    ],
    "en": [
        "design",
        "architecture",
        "architect",
        "plan",
        "planning",
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
        "complex",
        "refactor",
        "simplify",
        "review",
        "check this",
        "think",
        "analyze",
        "deeply",
        "optimize",
        "performance",
        # Proactive triggers (mirror of the Japanese list above). Only
        # multi-word phrases and unambiguous words survive: bare "option",
        # "pattern", "approach", "improve", "alternative", "dependency",
        # "security" and "advice" routed 44% of non-design prompts, including
        # "add a --dry-run option" and "improve the wording of this sentence".
        "best practice",
        "test strategy",
        "test design",
        "circular",
        "not sure",
        "unsure",
        "uncertain",
        "should i",
        "should we",
        "what if",
        "why does",
        "why is",
        "how come",
        "better way",
    ],
}

# Triggers for Opus research (codebase analysis + external research)
OPUS_RESEARCH_TRIGGERS = {
    "ja": [
        "調べて",
        "リサーチ",
        "調査",
        "サーベイ",
        "最新",
        "ドキュメント",
        "ライブラリ",
        "パッケージ",
        "コードベース",
        "リポジトリ",
        "全体構造",
        "理解して",
        "把握して",
    ],
    "en": [
        "research",
        "investigate",
        "look up",
        "find out",
        "survey",
        "latest",
        "documentation",
        "docs",
        "library",
        "package",
        "framework",
        "codebase",
        "repository",
        "project structure",
        "understand",
        "analyze the code",
    ],
}

# Triggers for an explicit code review request
REVIEW_TRIGGERS = {
    "ja": [
        "レビューして",
        "コードレビュー",
        "レビューお願い",
        "チェックして",
        "出荷前",
    ],
    "en": [
        "review this",
        "code review",
        "review my",
        "before shipping",
        "pre-ship",
    ],
}


def matches_trigger(trigger: str, prompt_lower: str, lang: str) -> bool:
    """Check one trigger against the lowercased prompt.

    English triggers are matched on word boundaries (with an optional plural
    "s"), so "option" can no longer match "optional" and "docs" can no longer
    match "docstring". Japanese has no word boundaries, so those triggers stay
    substring matches — which is why the ambiguous single words were removed
    from the Japanese lists instead.
    """
    if lang != "en":
        return trigger in prompt_lower
    return re.search(rf"\b{re.escape(trigger)}s?\b", prompt_lower) is not None


def detect_agent(prompt: str) -> tuple[str | None, str]:
    """Detect which agent should handle this prompt.

    Returns (agent, trigger).
    """
    prompt_lower = prompt.lower()

    # Fable triggers (rare escalation: arbitration, stuck, final review)
    # Checked FIRST — narrow, high-specificity triggers that must not be
    # swallowed by the broader deep-reasoning keywords.
    for lang, triggers in FABLE_TRIGGERS.items():
        for trigger in triggers:
            if matches_trigger(trigger, prompt_lower, lang):
                return "fable", trigger

    # Review triggers. Checked BEFORE the broad deep-reasoning triggers:
    # these are more specific phrases (e.g. "コードレビュー", "review this")
    # that the bare DEEP_REASONING_TRIGGERS substrings (e.g. "レビュー",
    # "review") would otherwise shadow.
    for lang, triggers in REVIEW_TRIGGERS.items():
        for trigger in triggers:
            if matches_trigger(trigger, prompt_lower, lang):
                return "review", trigger

    # Deep-reasoning triggers (planning, design, debug, complex code)
    for lang, triggers in DEEP_REASONING_TRIGGERS.items():
        for trigger in triggers:
            if matches_trigger(trigger, prompt_lower, lang):
                return "deep", trigger

    # Opus research triggers (codebase analysis + external research)
    for lang, triggers in OPUS_RESEARCH_TRIGGERS.items():
        for trigger in triggers:
            if matches_trigger(trigger, prompt_lower, lang):
                return "opus-research", trigger

    return None, ""


def main():
    try:
        data = json.load(sys.stdin)
        prompt = data.get("prompt", "")

        # No length gate: it was character-based, so it skipped "設計" (two
        # characters) — the exact terse-but-loaded ask it claimed to rescue —
        # while admitting every three-character noise prompt. detect_agent
        # matches nothing on an empty or one-character prompt anyway.
        agent, trigger = detect_agent(prompt)

        if agent == "fable":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Fable Advisor] Detected '{trigger}' — this may warrant the "
                        "fable-advisor subagent (rare escalation: design arbitration / "
                        "stuck problems / final review of large changes; notes saved to "
                        ".claude/docs/reviews/). For routine review or implementation, "
                        "use the normal general-purpose-opus/team-execute routes instead."
                    ),
                }
            }
            print(json.dumps(output))

        elif agent == "deep":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Agent Routing] Detected '{trigger}' — get a deep-reasoning "
                        "pass before committing to an approach. Planning, design, "
                        "trade-offs and complex implementation go to the "
                        "general-purpose-opus subagent (or the built-in Plan agent for "
                        "a read-only plan) unless the whole task is on the Self-Handle "
                        "List in .claude/rules/delegation.md. An error or failure with "
                        "an unproven root cause goes to the debugger subagent."
                    ),
                }
            }
            print(json.dumps(output))

        elif agent == "review":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Code Review] Detected '{trigger}' — delegate the review to "
                        "the general-purpose-opus subagent with the diff range and the "
                        "review dimensions (correctness, security, tests). For a "
                        "multi-dimension ship gate, use the team-execute review phase."
                    ),
                }
            }
            print(json.dumps(output))

        elif agent == "opus-research":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Opus Research] Detected '{trigger}' — use general-purpose-opus "
                        "for this task. Opus subagents handle research, codebase analysis, and investigation "
                        "with 1M context and WebSearch/WebFetch. "
                        "Use via Agent tool with subagent_type='general-purpose-opus'. "
                        "Save results to .claude/docs/research/."
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
