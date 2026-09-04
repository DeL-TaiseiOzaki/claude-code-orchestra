#!/usr/bin/env python3
"""
PostToolUse hook: Detect errors from Bash commands and suggest codex-debugger.

Broader than post-test-analysis.py — catches ANY Bash error,
not just test/build commands. Directs to the codex-debugger subagent.
"""

import json
import re
import sys

# Strong signals: specific enough on their own to trigger a hint alone.
STRONG_ERROR_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"^error\[\w+\]",
    r"npm ERR!",
    r"panic:",
    r"segmentation fault",
    r"core dumped",
    r"^\s*(?:TypeError|ValueError|AttributeError|ImportError|KeyError|IndexError|"
    r"RuntimeError|SyntaxError|NameError|FileNotFoundError|PermissionError|OSError|"
    r"ConnectionError|ConnectionRefusedError|ConnectionResetError|TimeoutError|"
    r"MemoryError):\s",
    # Network failures named by errno: unambiguous, never benign prose.
    r"\b(?:ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENOTFOUND)\b",
    # Resource exhaustion.
    r"OutOfMemoryError",
    r"too many open files",
    # Build / link / module resolution failures.
    r"undefined reference to",
    r"unresolved external symbol",
    r"(?:compilation|build) failed",
    r"(?:cannot find module|module not found)",
]

# Weak signals: individually too generic (or prone to matching benign prose);
# require at least MIN_WEAK_SIGNALS matches before triggering a hint.
WEAK_ERROR_PATTERNS = [
    r"(?:Error|Exception):\s+\S",
    r"FAIL[ED:\s]",
    r"fatal:",
    r"(?:Cannot|Could not|Unable to)\s",
    r"cargo error",
    # Individually ambiguous: a passing run may legitimately print "timed out
    # (retrying)". Only further signals make them a reason to stop and diagnose.
    # Deprecation notices are deliberately absent: a warning is by definition
    # not an error, and pip/curl output pairs them with "Could not"/"Unable to"
    # often enough that two-of-a-kind fired on healthy builds.
    r"(?:timeout|timed out)",
    r"(?:DNS|name) resolution",
    r"resource temporarily unavailable",
    r"returned non-zero",
    r"exit (?:code|status)\s*[1-9]",
]

# Minimum number of weak signals required when no strong signal is present.
# Ten weak patterns co-occur too easily for a threshold of two: a successful
# `git show` of this repository scored eight.
MIN_WEAK_SIGNALS = 3

# Commands to ignore (not useful to debug)
IGNORE_COMMANDS = [
    "git status",
    "git log",
    "git diff",
    "git branch",
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "echo",
    "which",
    "type",
    "true",
]

# Outputs to ignore (trivial / expected errors)
IGNORE_OUTPUTS = [
    "command not found",
    "No such file or directory",
    "already exists",
    "nothing to commit",
    "Already up to date",
    "Everything up-to-date",
]

# Skip if the command itself is a Codex call (avoid recursive suggestions)
SKIP_COMMANDS = [
    "codex ",
]

# Terse failures ("Error: failed") are still failures, so the floor only has
# to exclude effectively empty output.
MIN_OUTPUT_LENGTH = 5


def should_ignore_command(command: str) -> bool:
    """Check if the command should be ignored."""
    command_stripped = command.strip()
    for ignore in IGNORE_COMMANDS:
        if command_stripped.startswith(ignore):
            return True
    for skip in SKIP_COMMANDS:
        if skip in command_stripped:
            return True
    return False


def should_ignore_output(output: str) -> bool:
    """Check if the output contains only trivial errors."""
    for ignore in IGNORE_OUTPUTS:
        if ignore in output and output.count("\n") < 5:
            return True
    return False


def detect_errors(output: str) -> list[str]:
    """Detect error patterns in the output.

    Returns the matched patterns only if the evidence is strong enough to
    warrant a hint: either one strong signal, or at least MIN_WEAK_SIGNALS
    weak signals. This avoids false positives on benign output that merely
    mentions error-adjacent phrases in passing.
    """
    flags = re.IGNORECASE | re.MULTILINE
    strong_matches = [
        pattern
        for pattern in STRONG_ERROR_PATTERNS
        if re.search(pattern, output, flags)
    ]
    if strong_matches:
        return strong_matches

    weak_matches = [
        pattern for pattern in WEAK_ERROR_PATTERNS if re.search(pattern, output, flags)
    ]
    if len(weak_matches) >= MIN_WEAK_SIGNALS:
        return weak_matches

    return []


def build_context(data: dict) -> str | None:
    """Return the additionalContext hint for this hook, or None.

    Pure function (no stdin/stdout/exit) so the post-bash-check.py
    dispatcher can call it in-process. Standalone main() below still
    reads stdin directly for backwards-compatible direct invocation.
    """
    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    tool_input = data.get("tool_input", {})
    tool_response = data.get("tool_response", {})
    command = tool_input.get("command", "")
    tool_output = tool_response.get("stdout", "") or tool_response.get("content", "")

    if not command or not tool_output:
        return None

    if len(tool_output) < MIN_OUTPUT_LENGTH:
        return None

    if should_ignore_command(command):
        return None

    if should_ignore_output(tool_output):
        return None

    errors = detect_errors(tool_output)
    if not errors:
        return None

    reason = f"{len(errors)} error pattern(s) found in command output"

    return (
        f"[Error Detected] {reason}. "
        "**Action**: You MUST use the `codex-debugger` subagent to analyze this "
        "error rather than guessing at a fix. "
        "Pass the full command and error output to the subagent for Codex-powered diagnosis. "
        "Example: Task(subagent_type='codex-debugger', prompt='Analyze this error: ...')"
    )


def main() -> None:
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
