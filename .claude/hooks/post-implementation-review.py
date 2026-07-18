#!/usr/bin/env python3
"""
PostToolUse hook: Suggest Codex review after significant implementations.

Tracks file changes and suggests code review when substantial
code has been written.
"""

import hashlib
import json
import os
import sys

# Input validation constants
MAX_PATH_LENGTH = 4096
MAX_CONTENT_LENGTH = 1_000_000

# Namespacing constants for the state file path
PROJECT_HASH_LENGTH = 12
SESSION_PART_LENGTH = 8
FALLBACK_SESSION_PART = "nosession"


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


def get_state_file_path(data: dict) -> str:
    """Derive a per-project, per-session state file path.

    Namespacing prevents concurrent Claude Code sessions (same machine,
    different projects, or the same project) from clobbering each other's
    counters and the review_suggested flag.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    project_hash = hashlib.sha256(os.path.abspath(project_dir).encode()).hexdigest()[
        :PROJECT_HASH_LENGTH
    ]
    session_id = data.get("session_id", "")
    session_part = (
        session_id[:SESSION_PART_LENGTH] if session_id else FALLBACK_SESSION_PART
    )
    return f"/tmp/claude-code-impl-state-{project_hash}-{session_part}.json"


# Thresholds for suggesting review
MIN_FILES_FOR_REVIEW = 3
MIN_LINES_FOR_REVIEW = 100


def load_state(state_file: str) -> dict:
    """Load session state."""
    try:
        if os.path.exists(state_file):
            with open(state_file) as f:
                return json.load(f)
    except Exception:
        pass
    return {"files_changed": [], "total_lines": 0, "review_suggested": False}


def save_state(state: dict, state_file: str):
    """Save session state."""
    try:
        with open(state_file, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def count_lines(content: str) -> int:
    """Count meaningful lines in content."""
    lines = content.split("\n")
    # Count non-empty, non-comment lines
    meaningful = [
        line for line in lines if line.strip() and not line.strip().startswith("#")
    ]
    return len(meaningful)


def should_suggest_review(state: dict) -> tuple[bool, str]:
    """Check if we should suggest a code review."""
    if state.get("review_suggested"):
        return False, ""

    files_count = len(state.get("files_changed", []))
    total_lines = state.get("total_lines", 0)

    if files_count >= MIN_FILES_FOR_REVIEW:
        return True, f"{files_count} files modified"

    if total_lines >= MIN_LINES_FOR_REVIEW:
        return True, f"{total_lines}+ lines written"

    return False, ""


def main():
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")

        # Only process Write/Edit tools
        if tool_name not in ["Write", "Edit"]:
            sys.exit(0)

        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "") or tool_input.get("new_string", "")

        # Validate input
        if not validate_input(file_path, content):
            sys.exit(0)

        # Skip non-source files
        if not any(
            file_path.endswith(ext)
            for ext in [".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs"]
        ):
            sys.exit(0)

        # Load and update state (namespaced per project + session)
        state_file = get_state_file_path(data)
        state = load_state(state_file)
        if file_path not in state["files_changed"]:
            state["files_changed"].append(file_path)
        state["total_lines"] += count_lines(content)
        save_state(state, state_file)

        # Check if review should be suggested
        should_review, reason = should_suggest_review(state)

        if should_review:
            state["review_suggested"] = True
            save_state(state, state_file)

            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"[Code Review Suggestion] {reason} in this session. "
                        "Consider having Codex review the implementation. "
                        "**Recommended**: Use Task tool with subagent_type='general-purpose-opus' "
                        "to consult Codex with git diff and preserve main context."
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
