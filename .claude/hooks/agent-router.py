#!/usr/bin/env python3
"""
UserPromptSubmit hook: Route to appropriate agent based on user intent.

Routing rules (checked in order, most specific first):
- Design arbitration / stuck problems / final review → Fable advisor (rare)
- Explicit review/rescue/delegation phrases → Codex Plugin commands
- Human-facing report drafts, video reading, Japanese polishing → Antigravity
  (`antigravity-delegate`); suppressed whenever a code-context word is present
- Planning, design, complex code → Codex CLI
- Codebase understanding / large analysis / external research → Opus subagent

Images and PDFs are handled directly by Claude; video goes to `antigravity-delegate`.
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

# Triggers for Codex (planning, design, debugging, complex implementation)
CODEX_TRIGGERS = {
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
        # where a Codex consult is cheaper than the rework it prevents.
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

# Triggers for Codex Plugin commands (review, rescue, delegation)
CODEX_PLUGIN_TRIGGERS = {
    "ja": [
        "レビューして",
        "コードレビュー",
        "レビューお願い",
        "チェックして",
        "出荷前",
        "codexに任せ",
        "codexに渡",
        "codexに委",
        "バグ調査",
        "調査して",
    ],
    "en": [
        "review this",
        "code review",
        "review my",
        "before shipping",
        "pre-ship",
        "delegate to codex",
        "hand to codex",
        "ask codex to",
        "codex rescue",
        "codex review",
    ],
}

# Triggers for Antigravity (`antigravity-delegate`): exactly three uses --
# human-facing report drafts, careful video reading, Japanese prose polishing.
# Only high-precision phrases are listed, and the Japanese ones are anchored on
# the request form ("...を書いて", "...を確認して"): a bare "report" or "動画", or
# a stem such as "レポートを書" (which also matches "書き出す" / "書き込む"),
# would steal report-generator and video-processing *code* requests from Codex.
ANTIGRAVITY_TRIGGERS = {
    "ja": [
        "推敲",
        "校正して",
        "文章を整え",
        "日本語を自然に",
        "動画の内容",
        "動画を見て",
        "動画を確認して",
        "動画を精査",
        "動画を分析",
        "動画を書き起こ",
        "報告書を書いて",
        "報告書を作成して",
        "報告書にまとめて",
        "レポートを書いて",
        "レポートを作成して",
        "レポートにまとめて",
    ],
    "en": [
        "proofread the japanese",
        "proofread this japanese",
        "proofread japanese",
        "polish the japanese",
        "polish this japanese",
        "polish japanese",
        "japanese prose",
        "watch the video",
        "transcribe the video",
        "what happens in the video",
        "write a report",
        "draft a report",
    ],
}

# A code-context word anywhere in the prompt suppresses the Antigravity route,
# so "報告書生成スクリプトを実装して" falls through to Codex or Opus. English
# entries use ASCII-only boundaries, so they also match inside a Japanese
# sentence ("CIジョブ", "APIを").
CODE_CONTEXT_EXCLUSIONS = {
    "ja": [
        "実装",
        "追加",
        "処理",
        "コード",
        "関数",
        "スクリプト",
        "機能",
        "設計",
        "テスト",
        "エンドポイント",
        "パイプライン",
        "バグ",
    ],
    "en": [
        "implement",
        "add",
        "code",
        "function",
        "script",
        "component",
        "pipeline",
        "generator",
        "design",
        "bug",
        "test",
        "api",
        "cli",
        "ci",
        "endpoint",
    ],
}

# Polishing prose *about* a design, a feature, or code is still polishing:
# these triggers ignore the soft exclusions below, so "設計書を推敲して",
# "機能紹介の文章を校正して", and "polish the japanese in the design doc" route
# to Antigravity. Hard exclusions (実装, 追加, テスト, "api", ...) still apply.
POLISH_EXEMPT_TRIGGERS = (
    "推敲",
    "校正して",
    "文章を整え",
    "日本語を自然に",
    "proofread the japanese",
    "proofread this japanese",
    "proofread japanese",
    "polish the japanese",
    "polish this japanese",
    "polish japanese",
    "japanese prose",
)
POLISH_EXEMPT_EXCLUSIONS = ("設計", "機能", "design", "code")


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


def matches_exclusion(exclusion: str, prompt_lower: str, lang: str) -> bool:
    """Check one code-context exclusion against the lowercased prompt.

    Japanese exclusions are substrings. English ones use ASCII-only
    boundaries (with an optional plural "s"), because ``\\b`` treats an
    adjacent Japanese character as a word character and would miss "CIジョブ".
    """
    if lang != "en":
        return exclusion in prompt_lower
    pattern = rf"(?<![a-z0-9]){re.escape(exclusion)}s?(?![a-z0-9])"
    return re.search(pattern, prompt_lower) is not None


def detect_antigravity(prompt_lower: str) -> str | None:
    """Return the matched Antigravity trigger, or None.

    Returns None when no routed-use phrase matches, or when a code-context
    exclusion is present (so the prompt falls through to Codex or Opus).
    """
    matched: str | None = None
    for lang, triggers in ANTIGRAVITY_TRIGGERS.items():
        for trigger in triggers:
            if matches_trigger(trigger, prompt_lower, lang):
                matched = trigger
                break
        if matched is not None:
            break
    if matched is None:
        return None

    is_polish = matched in POLISH_EXEMPT_TRIGGERS
    for lang, exclusions in CODE_CONTEXT_EXCLUSIONS.items():
        for exclusion in exclusions:
            if is_polish and exclusion in POLISH_EXEMPT_EXCLUSIONS:
                continue
            if matches_exclusion(exclusion, prompt_lower, lang):
                return None
    return matched


def detect_agent(prompt: str) -> tuple[str | None, str]:
    """Detect which agent should handle this prompt.

    Returns (agent, trigger).
    """
    prompt_lower = prompt.lower()

    # Fable triggers (rare escalation: arbitration, stuck, final review)
    # Checked FIRST — narrow, high-specificity triggers that must not be
    # swallowed by the broader Codex keywords.
    for lang, triggers in FABLE_TRIGGERS.items():
        for trigger in triggers:
            if matches_trigger(trigger, prompt_lower, lang):
                return "fable", trigger

    # Codex Plugin triggers (review, rescue, delegation)
    # Checked BEFORE the broad Codex triggers: these are more specific
    # phrases (e.g. "コードレビュー", "review this") that the bare
    # CODEX_TRIGGERS substrings (e.g. "レビュー", "review") would
    # otherwise shadow.
    for lang, triggers in CODEX_PLUGIN_TRIGGERS.items():
        for trigger in triggers:
            if matches_trigger(trigger, prompt_lower, lang):
                return "codex-plugin", trigger

    # Antigravity triggers (report drafts, video reading, Japanese polishing).
    # Checked BEFORE the broad Codex keywords so "この文章を推敲して" is not
    # swallowed by them, but only on high-precision phrases and never when a
    # code-context word is present.
    antigravity_trigger = detect_antigravity(prompt_lower)
    if antigravity_trigger is not None:
        return "antigravity", antigravity_trigger

    # Codex triggers (planning, design, debug, complex code)
    for lang, triggers in CODEX_TRIGGERS.items():
        for trigger in triggers:
            if matches_trigger(trigger, prompt_lower, lang):
                return "codex", trigger

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
                        "stuck problems / final review of large changes; may land the "
                        "resolution; notes saved to .claude/docs/reviews/). For routine "
                        "review or implementation, use the normal Codex/team-execute "
                        "routes instead."
                    ),
                }
            }
            print(json.dumps(output))

        elif agent == "antigravity":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Antigravity] Detected '{trigger}'. If the task is "
                        "drafting a human-facing report from supplied sources, "
                        "reading a video's content, or polishing Japanese prose, "
                        "delegate to `antigravity-delegate` (Agent tool). Code, "
                        "design, or review aspects go to Codex, and the final "
                        "Japanese reply stays with you."
                    ),
                }
            }
            print(json.dumps(output))

        elif agent == "codex":
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[Agent Routing] Detected '{trigger}' — consult Codex before "
                        "committing to an approach. Planning, design, trade-offs and "
                        "complex implementation MUST go through Codex unless the whole "
                        "task is on the Self-Handle List in .claude/rules/delegation.md. "
                        "Write the prompt to a file, then `python3 .claude/skills/_shared/"
                        "codex_consult.py --prompt-file <path> --sandbox read-only`, or "
                        "delegate via general-purpose-opus to preserve main context."
                    ),
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
