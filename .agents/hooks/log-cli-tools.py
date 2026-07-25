#!/usr/bin/env python3
"""
PostToolUse hook: Log cross-CLI subagent calls to a JSONL file.

Triggers after Bash tool calls that invoke another CLI agent, either through
a shared wrapper (`.agents/skills/_shared/codex_consult.py`, `cli_consult.py`)
or as a bare `codex exec` command. Logs are stored in
.agents/logs/cli-tools.jsonl

All agents (Claude Code, subagents, Codex, Gemini) can read this log.
"""

import json
import re
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "cli-tools.jsonl"

# The shared wrappers are the mandated invocation path, so they are what this
# hook must recognize first. `codex_consult.py` implies the Codex callee;
# `cli_consult.py` names its callee in --cli and in its JSON result.
WRAPPER_CLI = {"codex_consult.py": "codex", "cli_consult.py": None}

# Redirections and command separators survive shlex tokenization; they are
# never the prompt.
SHELL_OPERATOR_RE = re.compile(r"[<>|;&]")


def extract_codex_prompt(command: str) -> str | None:
    """Extract the inline prompt from a bare `codex exec` command.

    Legacy path: the project mandates the wrapper, which passes the prompt via
    --prompt-file, but a hand-written `codex exec "..."` must still be logged
    rather than silently dropped.

    The prompt is the final positional argument, so the command is tokenized
    and scanned from the end. Matching the first quoted string instead would
    pick up a flag value such as `--model "gpt-5.6-sol"`.
    """
    if not re.search(r"(^|\s|/)codex\s+exec\b", command):
        return None
    try:
        tokens = shlex.split(command, comments=False)
    except ValueError:
        # Unbalanced quotes: the command line is not parseable, so there is no
        # prompt to report rather than a wrong one.
        return None
    for index in range(len(tokens) - 1, -1, -1):
        token = tokens[index]
        if token in ("codex", "exec"):
            break
        if token.startswith("-") or SHELL_OPERATOR_RE.search(token):
            continue
        # A bare value belongs to the flag in front of it, not to the prompt.
        if index > 0 and tokens[index - 1].startswith("-"):
            continue
        return token.strip() or None
    return None


def extract_model(command: str) -> str | None:
    """Extract model name from command."""
    match = re.search(r"--model[\s=]+(\S+)", command)
    return match.group(1).strip("\"'") if match else None


def _flag_value(command: str, flag: str) -> str | None:
    """Read a `--flag value` / `--flag=value` argument out of a command line."""
    match = re.search(rf"{re.escape(flag)}[\s=]+(\S+)", command)
    return match.group(1).strip("\"'") if match else None


def wrapper_callee(command: str) -> tuple[str, str | None] | None:
    """Identify a shared-wrapper invocation in *command*.

    Returns ``(wrapper_filename, cli_from_command_line)``, or None when the
    command does not run a wrapper.
    """
    for wrapper, fixed_cli in WRAPPER_CLI.items():
        if wrapper in command:
            return wrapper, fixed_cli or _flag_value(command, "--cli")
    return None


def read_prompt_file(command: str) -> str | None:
    """Best-effort recovery of the prompt a wrapper was given.

    The wrapper receives its prompt as a file (that is why the old inline-quote
    regex never matched a mandated call). The file is usually a mktemp path
    that still exists when this hook runs; when it does not, the path itself is
    still worth recording.
    """
    raw = _flag_value(command, "--prompt-file")
    if not raw:
        return None
    path = Path(raw)
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return f"[prompt file unavailable: {path}]"


def parse_wrapper_result(output: str) -> dict | None:
    """Parse the single JSON object a shared wrapper prints on stdout.

    The wrapper's own output may be preceded by unrelated shell output, so the
    last JSON object line wins.
    """
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "ok" in payload:
            return payload
    return None


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
    """Log a cross-CLI subagent call from a Bash tool invocation, if present.

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
    exit_code = tool_response.get("exit_code", 0)

    wrapper = wrapper_callee(command)
    if wrapper is None and "codex" not in command.lower():
        return None

    if wrapper is not None:
        wrapper_file, declared_cli = wrapper
        result = parse_wrapper_result(output)
        cli = declared_cli or (result or {}).get("cli") or "unknown"
        prompt = read_prompt_file(command)
        if prompt is None and "--prompt-stdin" in command:
            prompt = "[prompt supplied on stdin]"
        if prompt is None:
            # Neither prompt source is present: this is not a consult call
            # (e.g. `--help`), so there is nothing worth logging.
            return None
        entry_model = (result or {}).get("model") or extract_model(command)
        response = (result or {}).get("response_head") or output
        # The wrapper reports its own outcome; a missing result means its JSON
        # never reached stdout, which is itself a failure worth recording.
        success = bool(result and result.get("ok")) and exit_code == 0
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool": cli,
            "via": wrapper_file,
            "model": entry_model,
            "prompt": truncate_text(prompt),
            "response": truncate_text(response) if response else "",
            "response_file": (result or {}).get("response_file"),
            "success": success,
            "exit_code": exit_code,
        }
        log_entry(entry)
        return f"[LOG] {cli} call logged to .agents/logs/cli-tools.jsonl"

    prompt = extract_codex_prompt(command)
    if not prompt:
        # Could not extract prompt, skip logging
        return None

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": "codex",
        "via": "codex exec (direct; the shared wrapper is the mandated path)",
        "model": extract_model(command),
        "prompt": truncate_text(prompt),
        "response": truncate_text(output) if output else "",
        "response_file": None,
        "success": exit_code == 0 and bool(output),
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
