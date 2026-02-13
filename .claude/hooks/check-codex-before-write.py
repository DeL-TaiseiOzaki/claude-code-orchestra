#!/usr/bin/env python3
"""
PreToolUse hook: Check if Codex consultation is recommended before Write/Edit.

This hook analyzes the file being modified and suggests Codex consultation
for design decisions, complex implementations, or architectural changes.
"""

import json
import os
import sys
from pathlib import Path

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

    # Code patterns in content
    "class ",
    "interface ",
    "abstract class",
    "def __init__",
    "from abc import",
    "Protocol",
    "@dataclass",
    "TypedDict",
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


def should_suggest_codex(file_path: str, content: str | None = None) -> tuple[bool, str]:
    """Determine if Codex consultation should be suggested."""
    path = Path(file_path)
    filename = path.name.lower()
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
        # New file with significant content
        if len(content) > 500:
            return True, "Creating new file with significant content"

        # Check for design patterns in content
        for indicator in DESIGN_INDICATORS:
            if indicator in content:
                return True, f"Content contains '{indicator}' - likely architectural code"

    # New files in src/ directory
    if "/src/" in file_path or file_path.startswith("src/"):
        if content and len(content) > 200:
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
                        "Consider consulting Codex before making this change. "
                        "**Recommended**: Use Task tool with subagent_type='general-purpose' "
                        "to preserve main context. "
                        "(Direct call OK for quick questions: "
                        "`codex exec --model gpt-5.3-codex --sandbox read-only --full-auto '...'`)"
                    )
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
