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
    "orchestrat",
    # Code patterns in content
    "class ",
    "interface ",
    "abstract class",
    "def __init__",
    "from abc import",
    "Protocol",
    "@dataclass",
    "TypedDict",
    "async def",
    "asyncio",
    "threading",
    "multiprocessing",
    "subprocess",
    "signal",
    "except Exception",
    "raise ",
    "retry",
    "cache",
    "singleton",
]

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
        # New file with meaningful content (lowered from 500)
        if len(content) > 200:
            return (
                True,
                "Creating new file with meaningful content — Codex should review",
            )

        # Check for design patterns in content
        for indicator in DESIGN_INDICATORS:
            if indicator in content:
                return (
                    True,
                    f"Content contains '{indicator}' — Codex should review design",
                )

        # Multiple function/class definitions suggest architectural decisions
        class_count = content.count("class ") + content.count("def ")
        if class_count >= 2:
            return (
                True,
                f"Multiple definitions ({class_count}) — Codex should review structure",
            )

    # New files in src/ directory (lowered from 200)
    if "/src/" in file_path or file_path.startswith("src/"):
        if content and len(content) > 50:
            return True, "New source file — Codex should review design"

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
                        f"[Codex Review Required] {reason}. "
                        "You SHOULD consult Codex before finalizing this change. "
                        "Codex can catch design issues, suggest better patterns, and prevent bugs. "
                        "Use Task(subagent_type='general-purpose') for design review, or "
                        "direct call for quick validation: "
                        "`codex exec --model gpt-5.3-codex --sandbox read-only --full-auto '...'`"
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
