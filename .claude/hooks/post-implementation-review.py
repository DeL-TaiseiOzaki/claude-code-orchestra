#!/usr/bin/env python3
"""
PostToolUse hook: Suggest Codex review after significant implementations.

Tracks file changes and suggests code review when substantial
code has been written.
"""

import json
import sys
import os

# State file to track changes in this session
STATE_FILE = "/tmp/claude-code-implementation-state.json"

# Thresholds for suggesting review
MIN_FILES_FOR_REVIEW = 3
MIN_LINES_FOR_REVIEW = 100


def load_state() -> dict:
    """Load session state."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"files_changed": [], "total_lines": 0, "review_suggested": False}


def save_state(state: dict):
    """Save session state."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def count_lines(content: str) -> int:
    """Count meaningful lines in content."""
    lines = content.split("\n")
    # Count non-empty, non-comment lines
    meaningful = [l for l in lines if l.strip() and not l.strip().startswith("#")]
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

        # Skip non-source files
        if not any(file_path.endswith(ext) for ext in [".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs"]):
            sys.exit(0)

        # Load and update state
        state = load_state()
        if file_path not in state["files_changed"]:
            state["files_changed"].append(file_path)
        state["total_lines"] += count_lines(content)
        save_state(state)

        # Check if review should be suggested
        should_review, reason = should_suggest_review(state)

        if should_review:
            state["review_suggested"] = True
            save_state(state)

            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"[Code Review Suggestion] {reason} in this session. "
                        "Consider having Codex review the implementation. "
                        "**Recommended**: Use Task tool with subagent_type='general-purpose' "
                        "to consult Codex with git diff and preserve main context."
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
