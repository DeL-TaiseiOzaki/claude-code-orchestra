#!/usr/bin/env python3
"""
PostToolUse hook: Detect errors from Bash commands and suggest codex-debugger.

Broader than post-test-analysis.py — catches ANY Bash error,
not just test/build commands. Directs to the codex-debugger subagent.
"""

import json
import re
import sys

# Error patterns indicating something went wrong
ERROR_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"(?:Error|Exception):\s+\S",
    r"error\[\w+\]",
    r"panic:",
    r"FAIL[ED:\s]",
    r"fatal:",
    r"segmentation fault",
    r"core dumped",
    r"(?:Cannot|Could not|Unable to)\s",
    r"(?:TypeError|ValueError|AttributeError|ImportError|KeyError|IndexError|RuntimeError)",
    r"(?:SyntaxError|NameError|FileNotFoundError|PermissionError|OSError)",
    r"npm ERR!",
    r"cargo error",
]

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

# Skip if the command itself is a Codex/Gemini call (avoid recursive suggestions)
SKIP_COMMANDS = [
    "codex ",
    "gemini ",
]

MIN_OUTPUT_LENGTH = 20


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
    """Detect error patterns in the output."""
    found = []
    for pattern in ERROR_PATTERNS:
        if re.search(pattern, output, re.IGNORECASE):
            found.append(pattern)
    return found


def main() -> None:
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")

        if tool_name != "Bash":
            sys.exit(0)

        tool_input = data.get("tool_input", {})
        tool_response = data.get("tool_response", {})
        command = tool_input.get("command", "")
        tool_output = tool_response.get("stdout", "") or tool_response.get("content", "")

        if not command or not tool_output:
            sys.exit(0)

        if len(tool_output) < MIN_OUTPUT_LENGTH:
            sys.exit(0)

        if should_ignore_command(command):
            sys.exit(0)

        if should_ignore_output(tool_output):
            sys.exit(0)

        errors = detect_errors(tool_output)

        if errors:
            error_count = len(errors)
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"[Error Detected] {error_count} error pattern(s) found in command output. "
                        "**Action**: Use the `codex-debugger` subagent to analyze this error. "
                        "Pass the full command and error output to the subagent for Codex-powered diagnosis. "
                        "Example: Task(subagent_type='codex-debugger', prompt='Analyze this error: ...')"
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
