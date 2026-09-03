#!/usr/bin/env python3
"""
PreToolUse hook: Check if Codex consultation is recommended before Write/Edit.

This hook analyzes the file being modified and suggests Codex consultation
for design decisions, complex implementations, or architectural changes.
"""

import json
import sys

# Input validation constants
MAX_PATH_LENGTH = 4096
MAX_CONTENT_LENGTH = 1_000_000


def validate_input(file_path: str, content: str) -> bool:
    """Validate input for security."""
    if not file_path or len(file_path) > MAX_PATH_LENGTH:
        return False
    if len(content) > MAX_CONTENT_LENGTH:
        return False
    # Check for path traversal
    if ".." in file_path:
        return False
    return True


# Patterns that suggest design/architecture decisions
DESIGN_INDICATORS = [
    # File patterns
    "DESIGN.md",
    "ARCHITECTURE.md",
    "architecture",
    "design",
    "schema",
    "model",
    "interface",
    "abstract",
    "base_",
    "core/",
    "/core/",
    "config",
    "settings",
    # Structural / architectural roles: a file named for one of these is
    # almost always a seam other code depends on.
    "middleware",
    "router",
    "handler",
    "service",
    "repository",
    "factory",
    "strategy",
    "adapter",
    "decorator",
    "observer",
    "manager",
    "controller",
    "provider",
    "registry",
    "pipeline",
    # Code patterns in content
    "class ",
    "interface ",
    "abstract class",
    "def __init__",
    "from abc import",
    "Protocol",
    "@dataclass",
    "TypedDict",
    # Concurrency, process boundaries, and resilience: the places where a
    # second opinion is worth the most because the bugs are non-local.
    "async def",
    "asyncio",
    "threading",
    "multiprocessing",
    "subprocess",
    "signal",
    "retry",
    "cache",
    "singleton",
]

# Number of function/class definitions in one payload that makes it
# structural rather than a local edit.
MIN_DEFINITIONS_FOR_REVIEW = 2

# Content-size thresholds (characters) above which a write is worth a look.
NEW_FILE_CONTENT_THRESHOLD = 200
SRC_FILE_CONTENT_THRESHOLD = 50

# Files that are typically simple edits (skip suggestion)
SIMPLE_EDIT_PATTERNS = [
    ".gitignore",
    "README.md",
    "CHANGELOG.md",
    "requirements.txt",
    "package.json",
    "pyproject.toml",
    ".env.example",
]


def should_suggest_codex(
    file_path: str, content: str | None = None
) -> tuple[bool, str]:
    """Determine if Codex consultation should be suggested."""
    filepath_lower = file_path.lower()

    # Skip simple edits
    for pattern in SIMPLE_EDIT_PATTERNS:
        if pattern.lower() in filepath_lower:
            return False, ""

    # Check file path for design indicators
    for indicator in DESIGN_INDICATORS:
        if indicator.lower() in filepath_lower:
            return True, f"File path contains '{indicator}' - likely a design decision"

    # Check content if available
    if content:
        # New file with meaningful content
        if len(content) > NEW_FILE_CONTENT_THRESHOLD:
            return True, "Creating new file with meaningful content"

        # Check for design patterns in content
        for indicator in DESIGN_INDICATORS:
            if indicator in content:
                return (
                    True,
                    f"Content contains '{indicator}' - likely architectural code",
                )

        # Several definitions in one payload means structure is being decided,
        # not a single line being fixed.
        definition_count = content.count("class ") + content.count("def ")
        if definition_count >= MIN_DEFINITIONS_FOR_REVIEW:
            return (
                True,
                f"{definition_count} definitions in one write - structural change",
            )

    # New files in src/ directory
    if "/src/" in file_path or file_path.startswith("src/"):
        if content and len(content) > SRC_FILE_CONTENT_THRESHOLD:
            return True, "New source file - consider design review"

    return False, ""


def main():
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "") or tool_input.get("new_string", "")

        # Validate input
        if not validate_input(file_path, content):
            sys.exit(0)

        should_suggest, reason = should_suggest_codex(file_path, content)

        if should_suggest:
            # Return additional context to Claude
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": (
                        f"[Codex Consultation Reminder] {reason}. "
                        "You SHOULD consult Codex before finalizing this change — it "
                        "catches design problems, better patterns, and hidden coupling "
                        "while they are still cheap to fix. "
                        "**Recommended**: Use Task tool with subagent_type='general-purpose-opus' "
                        "to preserve main context. "
                        "(Direct call OK for quick questions: write the prompt to a file, then "
                        "`python3 .agents/skills/_shared/codex_consult.py --prompt-file <path> "
                        "--sandbox read-only`)"
                    ),
                }
            }
            print(json.dumps(output))

        sys.exit(0)  # Always allow, just add context

    except Exception as e:
        # Don't block on errors
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
