#!/usr/bin/env python3
"""Invoke a peer CLI agent (Claude Code, Gemini CLI) as a subagent.

This is the cross-CLI counterpart of ``codex_consult.py``: whichever runtime is
the active main agent, it drives the others through their headless mode with
one hardened contract instead of a hand-written shell-out. A raw
``claude -p`` / ``gemini -p`` call has the same four failure modes the Codex
wrapper removes: an open stdin can block on EOF in a non-TTY shell, stderr
redirected away makes a crashed CLI indistinguishable from an empty answer, a
prompt with nested quotes breaks the shell command, and a stalled call has no
deadline. Here the prompt is a single argv element (no shell), stdin is closed,
stdout and stderr are captured to timestamped files under
``.agents/logs/<cli>/``, and every outcome is reported as a single JSON object.

Codex is deliberately NOT accepted here: its sandbox modes and ``--config``
overrides need dedicated validation, so it keeps its own wrapper and there is
exactly one implementation per callee CLI.

Access is read-only unless ``--write-access`` is passed, mapped onto each CLI's
native permission flag, so the granted access is always visible in the call.

Usage:
    python3 cli_consult.py --cli claude --prompt-file p.txt --label design-review
    echo "Objective: ..." | python3 cli_consult.py --cli gemini --prompt-stdin
    python3 cli_consult.py --cli claude --prompt-file p.txt --write-access
    python3 cli_consult.py --cli claude --prompt-file p.txt \
        --cli-arg=--max-turns --cli-arg 8

Exit codes:
    0  the callee CLI exited 0 and did not report an error
    1  bad args (missing/both prompt sources, unreadable prompt file, bad --cwd,
       rejected passthrough argument, flag unsupported by the chosen CLI)
    2  the callee CLI is not on PATH
    3  the callee CLI failed, reported an error, or timed out
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DEFAULT_TIMEOUT = 900
LABEL_RE = re.compile(r"^[a-z0-9-]+$")

# Per-callee headless contract. `read_only` / `write` are the native permission
# flags this wrapper maps --write-access onto; `install_hint` is what a caller
# sees when the CLI is missing.
CLI_SPECS: dict[str, dict] = {
    "claude": {
        "base": ["claude", "-p", "--output-format", "json"],
        "read_only": ["--permission-mode", "plan"],
        "write": ["--permission-mode", "acceptEdits"],
        "model_flag": "--model",
        "resume_flag": "--resume",
        "install_hint": "install with `npm install -g @anthropic-ai/claude-code`",
    },
    "gemini": {
        # Gemini's own JSON output has known gaps (google-gemini/gemini-cli
        # #9009, #9281), so its text output is captured verbatim instead and
        # the exit code is the success signal.
        "base": ["gemini", "-p"],
        # `default` is the read-only setting: a tool call that would need
        # confirmation errors out instead of being auto-approved.
        "read_only": ["--approval-mode", "default"],
        "write": ["--approval-mode", "yolo"],
        "model_flag": "--model",
        "resume_flag": None,
        "install_hint": "install with `npm install -g @google/gemini-cli`",
    },
}

# Passthrough arguments are forwarded verbatim, so the flags that decide what
# the callee may touch are refused: --write-access must stay the single visible
# statement of access, not something a passthrough can quietly contradict.
CLI_ARG_DENYLIST = (
    "permission-mode",
    "approval-mode",
    "allowedtools",
    "allowed-tools",
    "disallowedtools",
    "disallowed-tools",
    "yolo",
    "sandbox",
    "dangerously",
)

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_NOT_FOUND = 2
EXIT_FAILED = 3


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure stays machine-readable
    and never masquerades as this tool's exit code 2."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_ARGS)


def _repo_relative(path: Path, project_root: Path) -> str:
    """Render *path* as a repo-relative POSIX string when possible."""
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _as_text(value: bytes | str | None) -> str:
    """Normalize subprocess-captured output that may be str, bytes, or None.

    ``subprocess.TimeoutExpired.stdout``/``.stderr`` hold whatever was
    captured before the timeout fired; they are not guaranteed to already be
    decoded even though the call requested ``text=True``.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def validate_cli_args(cli_args: list[str]) -> str | None:
    """Return an error message if any ``--cli-arg`` passthrough is unusable.

    Non-flag entries are flag *values* (``--cli-arg --max-turns --cli-arg 8``)
    and pass through untouched: each is its own argv element, never shell-
    expanded. Only flags are screened, against the access denylist.
    """
    for raw in cli_args:
        if not raw.startswith("-"):
            continue
        stripped = raw.lstrip("-").split("=", 1)[0].lower()
        if any(denied in stripped for denied in CLI_ARG_DENYLIST):
            return (
                f"--cli-arg {raw!r} is refused: pass --write-access instead so "
                "the granted access stays visible in the call"
            )
    return None


def extract_claude_result(stdout_text: str) -> tuple[str, str | None, bool]:
    """Split ``claude -p --output-format json`` stdout into usable parts.

    Returns ``(response_text, session_id, reported_error)``. The envelope's
    ``result`` field is the answer itself, so callers get the clean response
    instead of a transport wrapper. Unparseable stdout is returned verbatim —
    a CLI that changed its output shape must not be reported as an empty
    answer.
    """
    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError:
        return stdout_text, None, False
    if not isinstance(payload, dict):
        return stdout_text, None, False
    result = payload.get("result")
    text = result if isinstance(result, str) else stdout_text
    session_id = payload.get("session_id")
    return (
        text,
        session_id if isinstance(session_id, str) else None,
        bool(payload.get("is_error")),
    )


def _not_found_report(cli: str, model: str | None, write_access: bool) -> dict:
    """Build the JSON payload for the two ways a missing callee can surface."""
    return {
        "ok": False,
        "error": (f"{cli} CLI not found on PATH; {CLI_SPECS[cli]['install_hint']}"),
        "cli": cli,
        "model": model,
        "write_access": write_access,
    }


def main() -> int:  # noqa: C901 — single-function CLI entry point
    parser = JsonArgumentParser(
        description="Invoke a peer CLI agent as a subagent and capture its output.",
    )
    parser.add_argument(
        "--cli",
        choices=sorted(CLI_SPECS),
        required=True,
        help="Callee CLI. Codex has its own wrapper: codex_consult.py",
    )
    parser.add_argument("--prompt-file", type=Path, help="File containing the prompt")
    parser.add_argument(
        "--prompt-stdin",
        action="store_true",
        help="Read the prompt from stdin",
    )
    parser.add_argument(
        "--label",
        default="consult",
        help="[a-z0-9-] slug used in log filenames (default: consult)",
    )
    parser.add_argument(
        "--write-access",
        action="store_true",
        help="Allow the callee to modify files (default: read-only)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Pin the callee's model (default: the callee's own default)",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="Continue a prior session by id (claude only)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Timeout in seconds (default: 900)",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Working directory for the callee (default: --project-root)",
    )
    parser.add_argument(
        "--cli-arg",
        action="append",
        default=[],
        metavar="ARG",
        help=(
            "Forward one extra argument to the callee (repeatable). A value "
            "starting with '-' must use the '=' form, which argparse can "
            "read: --cli-arg=--max-turns --cli-arg 8. Permission and sandbox "
            "flags are refused; use --write-access."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    args = parser.parse_args()
    project_root = args.project_root
    spec = CLI_SPECS[args.cli]

    # --- Validate prompt source: exactly one of --prompt-file/--prompt-stdin ---
    if bool(args.prompt_file) == bool(args.prompt_stdin):
        _emit(
            {
                "ok": False,
                "error": "exactly one of --prompt-file or --prompt-stdin is required",
            }
        )
        return EXIT_BAD_ARGS

    # --- Validate label (used verbatim in log filenames) ---
    if not LABEL_RE.match(args.label):
        _emit(
            {"ok": False, "error": f"--label must match [a-z0-9-]+, got {args.label!r}"}
        )
        return EXIT_BAD_ARGS

    # --- Validate --cwd up front so a bad path is never misread as "CLI missing" ---
    if args.cwd is not None and not args.cwd.is_dir():
        _emit({"ok": False, "error": f"--cwd is not a directory: {args.cwd}"})
        return EXIT_BAD_ARGS

    # --- Reject flags the chosen callee has no equivalent for ---
    if args.resume is not None and spec["resume_flag"] is None:
        _emit(
            {
                "ok": False,
                "error": f"--resume is not supported for --cli {args.cli}",
            }
        )
        return EXIT_BAD_ARGS

    # --- Validate passthrough arguments ---
    cli_arg_error = validate_cli_args(args.cli_arg)
    if cli_arg_error:
        _emit({"ok": False, "error": cli_arg_error})
        return EXIT_BAD_ARGS

    # --- Load prompt ---
    if args.prompt_file is not None:
        try:
            prompt = args.prompt_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _emit({"ok": False, "error": f"cannot read prompt file: {exc}"})
            return EXIT_BAD_ARGS
    else:
        prompt = sys.stdin.read()

    write_access = args.write_access
    model = args.model

    # --- the callee must be resolvable on PATH before we attempt to run it ---
    if shutil.which(spec["base"][0]) is None:
        _emit(_not_found_report(args.cli, model, write_access))
        return EXIT_NOT_FOUND

    logs_dir = project_root / ".agents" / "logs" / args.cli
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    response_path = logs_dir / f"{timestamp}-{args.label}.md"
    stderr_path = logs_dir / f"{timestamp}-{args.label}.err.log"

    cwd = args.cwd if args.cwd is not None else project_root
    argv = list(spec["base"])
    argv.extend(spec["write"] if write_access else spec["read_only"])
    if model is not None:
        argv.extend([spec["model_flag"], model])
    if args.resume is not None:
        argv.extend([spec["resume_flag"], args.resume])
    argv.extend(args.cli_arg)
    # The prompt is always the final argv element and is never shell-expanded.
    argv.append(prompt)

    timed_out = False
    error: str | None = None
    stdout_text = ""
    stderr_text = ""
    exit_code: int | None = None

    start = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            cwd=cwd,
        )
        stdout_text = result.stdout
        stderr_text = result.stderr
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout_text = _as_text(exc.stdout)
        stderr_text = _as_text(exc.stderr)
        error = f"{args.cli} timed out after {args.timeout}s"
    except FileNotFoundError:
        # Defensive fallback: PATH changed between the shutil.which check
        # above and this call, or the resolved entry was not executable.
        _emit(_not_found_report(args.cli, model, write_access))
        return EXIT_NOT_FOUND
    duration_sec = round(time.monotonic() - start, 3)

    session_id: str | None = None
    reported_error = False
    response_text = stdout_text
    if args.cli == "claude" and not timed_out:
        response_text, session_id, reported_error = extract_claude_result(stdout_text)

    response_path.write_text(response_text, encoding="utf-8")
    stderr_file: str | None = None
    if stderr_text:
        stderr_path.write_text(stderr_text, encoding="utf-8")
        stderr_file = _repo_relative(stderr_path, project_root)

    ok = exit_code == 0 and not timed_out and not reported_error
    if not ok and error is None:
        error = (
            f"{args.cli} reported an error in its result envelope"
            if reported_error
            else f"{args.cli} exited with code {exit_code}"
        )

    _emit(
        {
            "ok": ok,
            "exit_code": exit_code,
            "cli": args.cli,
            "model": model,
            "write_access": write_access,
            "session_id": session_id,
            "timed_out": timed_out,
            "duration_sec": duration_sec,
            "response_file": _repo_relative(response_path, project_root),
            "stderr_file": stderr_file,
            "response_chars": len(response_text),
            "response_head": response_text[:400],
            "error": error,
        }
    )
    return EXIT_OK if ok else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
