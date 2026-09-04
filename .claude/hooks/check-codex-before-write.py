#!/usr/bin/env python3
"""
PreToolUse hook: Check if Codex consultation is recommended before Write/Edit.

This hook analyzes the file being modified and suggests Codex consultation
for design decisions, complex implementations, or architectural changes.
"""

import json
import re
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


# Structural roles that make a *file* a seam other code depends on. Matched
# against the name tokens of the file and of its immediate directory, never as
# substrings of the whole path: "cache" as a substring made every
# __pycache__/ artefact "a design decision".
PATH_ROLE_INDICATORS = {
    "architecture",
    "design",
    "schema",
    "model",
    "models",
    "interface",
    "abstract",
    "base",
    "core",
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
}

# Patterns in the written *content* that suggest design/architecture decisions.
# Concept words ("cache", "signal", "retry") belong here and not in the path
# list: they describe what the code does, not what the file is named.
DESIGN_INDICATORS = [
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

# A real function/class definition, as opposed to the substring "def " inside
# "typedef", "#ifdef", or English prose — all three of which the previous
# content.count("def ") counted as definitions.
DEFINITION_RE = re.compile(r"(?m)^\s*(?:async\s+)?def\s+\w|^\s*class\s+\w")

# Word-ish tokens of a path component.
TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")

# Number of function/class definitions in one payload that makes it
# structural rather than a local edit.
MIN_DEFINITIONS_FOR_REVIEW = 2

# Content-size thresholds (characters) above which a write is worth a look.
# The new-file threshold applies only to Write (an actual creation); 200
# characters of an Edit is roughly three lines of prose, and announcing that
# as "creating a new file" was both wrong and the hook's dominant firing path.
NEW_FILE_CONTENT_THRESHOLD = 500
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


def path_role_tokens(file_path: str) -> set[str]:
    """Name tokens of the file and of the directory that contains it."""
    path = Path(file_path)
    tokens: set[str] = set()
    for part in (path.name, path.parent.name):
        tokens.update(t for t in TOKEN_SPLIT_RE.split(part.lower()) if t)
    return tokens


def should_suggest_codex(
    file_path: str, content: str | None = None, is_new_file: bool = False
) -> tuple[bool, str]:
    """Determine if Codex consultation should be suggested.

    ``is_new_file`` must be True only for a Write (a whole-file creation or
    replacement); an Edit patches an existing file, however long the patch.
    """
    filepath_lower = file_path.lower()

    # Skip simple edits
    for pattern in SIMPLE_EDIT_PATTERNS:
        if pattern.lower() in filepath_lower:
            return False, ""

    # Check file path for design indicators
    role_matches = sorted(path_role_tokens(file_path) & PATH_ROLE_INDICATORS)
    if role_matches:
        return (
            True,
            f"File is named for the role '{role_matches[0]}' - likely a design decision",
        )

    # Check content if available
    if content:
        # A whole new file of substantial size.
        if is_new_file and len(content) > NEW_FILE_CONTENT_THRESHOLD:
            return True, "Creating new file with substantial content"

        # Check for design patterns in content
        for indicator in DESIGN_INDICATORS:
            if indicator in content:
                return (
                    True,
                    f"Content contains '{indicator}' - likely architectural code",
                )

        # Several definitions in one payload means structure is being decided,
        # not a single line being fixed.
        definition_count = len(DEFINITION_RE.findall(content))
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

        # Only a Write creates or replaces a whole file; an Edit is a patch.
        is_new_file = data.get("tool_name") == "Write"
        should_suggest, reason = should_suggest_codex(file_path, content, is_new_file)

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
                        "`python3 .claude/skills/_shared/codex_consult.py --prompt-file <path> "
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
