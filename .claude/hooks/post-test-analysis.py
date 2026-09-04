#!/usr/bin/env python3
"""
PostToolUse hook: Suggest Codex analysis after test/build failures.

Analyzes test and build output and suggests Codex consultation
for debugging complex failures.
"""

import json
import re
import sys

# Commands that run tests or builds
TEST_BUILD_COMMANDS = [
    "pytest",
    "npm test",
    "npm run test",
    "npm run build",
    "uv run pytest",
    "ruff check",
    "ty check",
    "mypy",
    "tsc",
    "cargo test",
    "go test",
    "make test",
    "make build",
]

# Patterns indicating failures that need debugging.
#
# Every pattern is anchored or quantified so that it can only match a runner's
# *verdict*, never a test name, a file name, or prose. Bare tokens ("ERROR",
# "failed", "Error:") matched a green `pytest -v` run whose test names merely
# contained the word "error", so the hint fired on 8 passed, 0 failed.
# Matched case-sensitively for the same reason: "error" in an identifier is not
# an error, "ERROR" at the start of a line is.
FAILURE_PATTERNS = [
    # Runner verdict lines: pytest "FAILED test_x", "ERROR test_x".
    r"(?m)^(?:FAILED|ERROR)\b",
    # pytest's failure-detail prefix ("E   assert 1 == 2").
    r"(?m)^E\s",
    # Summary counts: "1 failed, 2 passed".
    r"\b\d+\s+failed\b",
    # An exception header at the start of a line, qualified or not:
    # "AssertionError: ...", "django.db.Error: ...", "Exception: ...".
    r"(?m)^\s*(?:\w+\.)*\w*(?:Error|Exception):\s",
    # rustc / cargo diagnostics.
    r"(?m)^error\[\w+\]",
    # Go panics and gotest/ctest verdict lines.
    r"(?m)^panic:",
    r"(?m)^FAIL\b",
    # Python traceback header (parenthesised, so it cannot match a test name).
    r"Traceback \(most recent call last\):",
    # Named exception types as whole words; case-sensitive, so the lowercase
    # forms that appear inside identifiers do not match.
    r"\b(?:AssertionError|TypeError|ValueError|AttributeError|ImportError|"
    r"ModuleNotFoundError|SyntaxError)\b",
]

# Failure count at which the output is reported as a multi-failure run.
MIN_FAILURES_FOR_MULTIPLE = 3

# Simple errors that don't need Codex
SIMPLE_ERRORS = [
    "ModuleNotFoundError",  # Usually just need to install
    "command not found",
    "No such file or directory",
]


def is_test_or_build_command(command: str) -> bool:
    """Check if the command runs tests or builds."""
    command_lower = command.lower()
    return any(cmd in command_lower for cmd in TEST_BUILD_COMMANDS)


def has_complex_failure(output: str) -> tuple[bool, str]:
    """Check if output contains complex failures that need debugging."""
    # Skip if it's a simple error
    for simple in SIMPLE_ERRORS:
        if simple in output:
            return False, ""

    # Count failure patterns
    failure_count = 0
    matched_patterns = []
    for pattern in FAILURE_PATTERNS:
        matches = re.findall(pattern, output)
        if matches:
            failure_count += len(matches)
            matched_patterns.append(pattern)

    # Any failure in a test or build command is worth a Codex look: a red
    # suite is the cheapest possible moment to find the root cause, and a
    # single failure is not evidence that the cause is simple.
    if failure_count >= MIN_FAILURES_FOR_MULTIPLE:
        return True, f"Multiple failures detected ({failure_count} issues)"

    if failure_count >= 1:
        plural = "" if failure_count == 1 else "s"
        if any(
            p in output.lower()
            for p in ["traceback", "assertion", "error", "exception"]
        ):
            return (
                True,
                f"Test failure with error details ({failure_count} issue{plural})",
            )
        return True, f"Test/build failure detected ({failure_count} issue{plural})"

    return False, ""


def build_context(data: dict) -> str | None:
    """Return the additionalContext hint for this hook, or None.

    Pure function (no stdin/stdout/exit) so the post-bash-check.py
    dispatcher can call it in-process. Standalone main() below still
    reads stdin directly for backwards-compatible direct invocation.
    """
    tool_name = data.get("tool_name", "")
    # Only process Bash tool
    if tool_name != "Bash":
        return None

    tool_input = data.get("tool_input", {})
    tool_response = data.get("tool_response", {})
    command = tool_input.get("command", "")
    tool_output = tool_response.get("stdout", "") or tool_response.get("content", "")

    # Check if it's a test/build command
    if not is_test_or_build_command(command):
        return None

    # Check for complex failures
    has_failure, reason = has_complex_failure(tool_output)
    if not has_failure:
        return None

    return (
        f"[Codex Debug Suggestion] {reason}. "
        "Use the `codex-debugger` subagent before attempting a manual fix — "
        "deep reasoning finds root causes that surface-level fixes miss. "
        "**Recommended**: Task(subagent_type='codex-debugger') with the full "
        "command and test output, which also preserves main context."
    )


def main():
    try:
        data = json.load(sys.stdin)
        context = build_context(data)

        if context:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": context,
                }
            }
            print(json.dumps(output))

        sys.exit(0)

    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
