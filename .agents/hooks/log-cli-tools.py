#!/usr/bin/env python3
"""
PostToolUse hook: Log Codex CLI input/output to JSONL file.

Triggers after Bash tool calls containing 'codex' commands.
Logs are stored in .agents/logs/cli-tools.jsonl

All agents (Claude Code, subagents, Codex) can read this log.
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "cli-tools.jsonl"


def extract_codex_prompt(command: str) -> str | None:
    """Extract prompt from codex exec command."""
    # Pattern: codex exec ... "prompt" or codex exec ... 'prompt'
    patterns = [
        r'codex\s+exec\s+.*?"([^"]+)"\s*2>/dev/null',
        r"codex\s+exec\s+.*?'([^']+)'\s*2>/dev/null",
    ]
    for pattern in patterns:
        match = re.search(pattern, command, re.DOTALL)
        if match:
            return match.group(1).strip()
    return None


def extract_model(command: str) -> str | None:
    """Extract model name from command."""
    match = re.search(r"--model\s+(\S+)", command)
    return match.group(1) if match else None


def truncate_text(text: str, max_length: int = 2000) -> str:
    """Truncate text if too long."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"... [truncated, {len(text)} total chars]"


def log_entry(entry: dict) -> None:
    """Append entry to JSONL log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def process_bash(data: dict) -> str | None:
    """Log a Codex CLI call from a Bash tool invocation, if present.

    Pure-ish function (its side effect is the JSONL append, which is the
    whole point of this hook) so the post-bash-check.py dispatcher can
    call it in-process. Returns a confirmation context string, or None if
    there was nothing to log. Standalone main() below still reads stdin
    directly for backwards-compatible direct invocation.
    """
    # Only process Bash tool calls
    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    # Get command and output
    tool_input = data.get("tool_input", {})
    tool_response = data.get("tool_response", {})

    command = tool_input.get("command", "")
    output = tool_response.get("stdout", "") or tool_response.get("content", "")

    # Check if this is a codex command
    if "codex" not in command.lower():
        return None

    prompt = extract_codex_prompt(command)
    model = extract_model(command) or "gpt-5.6-sol"

    if not prompt:
        # Could not extract prompt, skip logging
        return None

    # Determine success
    exit_code = tool_response.get("exit_code", 0)
    success = exit_code == 0 and bool(output)

    # Create log entry
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": "codex",
        "model": model,
        "prompt": truncate_text(prompt),
        "response": truncate_text(output) if output else "",
        "success": success,
        "exit_code": exit_code,
    }

    log_entry(entry)

    return "[LOG] Codex call logged to .agents/logs/cli-tools.jsonl"


def main() -> None:
    # Read hook input from stdin. This also handles the TaskCompleted
    # wiring: TaskCompleted payloads have no tool_name == "Bash", so
    # process_bash() returns None and this hook is a no-op for them.
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    context = process_bash(hook_input)
    if context is None:
        return

    # Output notification via hookSpecificOutput
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "additionalContext": context,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
