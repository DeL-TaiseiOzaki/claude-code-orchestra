#!/usr/bin/env python3
"""Safely invoke the Codex CLI and capture its output deterministically.

Skills consult Codex through this wrapper instead of shelling out to
``codex exec`` directly. A hand-written invocation has three failure modes
this removes: redirecting stderr away makes a crashed CLI indistinguishable
from an empty answer, prompts containing nested quotes break the shell
command, and an open stdin makes ``codex exec`` wait for EOF forever. Here
the prompt is a single argv element (no shell), stdin is closed, stdout and
stderr are captured to timestamped files under ``.agents/logs/codex/``, and
every outcome is reported as a single JSON object.

Usage:
    python3 codex_consult.py --prompt-file prompt.txt --label design-review
    echo "Objective: ..." | python3 codex_consult.py --prompt-stdin
    python3 codex_consult.py --prompt-file p.txt --config model_reasoning_effort=low

Exit codes:
    0  codex exec exited 0
    1  bad args (missing/both prompt sources, unreadable prompt file, bad --cwd)
    2  codex CLI not found on PATH
    3  codex exec exited non-zero, or timed out
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_TIMEOUT = 600
SANDBOX_CHOICES = ["read-only", "workspace-write", "danger-full-access"]
LABEL_RE = re.compile(r"^[a-z0-9-]+$")
INSTALL_HINT = "install with `npm install -g @openai/codex@latest`"

# --config KEY=VALUE overrides forwarded to codex. Keys are constrained to the
# dotted-identifier shape codex itself uses, and the two keys that decide what
# Codex is allowed to touch are refused: the caller's --sandbox must stay the
# single visible statement of write access, not something a config override can
# quietly contradict.
CONFIG_KEY_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
CONFIG_KEY_DENYLIST = ("sandbox", "approval")

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
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable and never
    masquerades as this tool's exit code 2."""

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


def validate_config_overrides(overrides: list[str]) -> str | None:
    """Return an error message if any ``--config`` override is unusable."""
    for override in overrides:
        key, separator, value = override.partition("=")
        if not separator or not key or not value:
            return f"--config must be KEY=VALUE, got {override!r}"
        if not CONFIG_KEY_RE.match(key):
            return f"--config key must be a dotted identifier, got {key!r}"
        if any(denied in key for denied in CONFIG_KEY_DENYLIST):
            return (
                f"--config {key!r} is refused: pass --sandbox explicitly instead "
                "so the granted access stays visible in the call"
            )
    return None


def _not_found_report(
    model: str, sandbox: str, write_access: bool, detail: str
) -> dict:
    """Build the JSON payload for the two ways codex-missing can surface."""
    return {
        "ok": False,
        "error": f"{detail}; {INSTALL_HINT}",
        "model": model,
        "sandbox": sandbox,
        "write_access": write_access,
    }


def main() -> int:  # noqa: C901 — single-function CLI entry point
    parser = JsonArgumentParser(
        description="Safely invoke the Codex CLI and capture its output.",
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
        "--sandbox",
        choices=SANDBOX_CHOICES,
        default="read-only",
        help="Codex sandbox mode (default: read-only)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Defaults to $CODEX_MODEL, else gpt-5.6-sol",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Working directory for codex exec (default: --project-root)",
    )
    parser.add_argument(
        "--skip-git-repo-check",
        action="store_true",
        help="Forward codex exec's --skip-git-repo-check (non-git working dir)",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Forward a codex --config override (repeatable), e.g. "
            "model_reasoning_effort=low. Sandbox and approval keys are refused."
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

    # --- Validate --cwd up front so a bad path is never misread as "codex missing" ---
    if args.cwd is not None and not args.cwd.is_dir():
        _emit({"ok": False, "error": f"--cwd is not a directory: {args.cwd}"})
        return EXIT_BAD_ARGS

    # --- Validate --config overrides ---
    config_error = validate_config_overrides(args.config)
    if config_error:
        _emit({"ok": False, "error": config_error})
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

    # An empty CODEX_MODEL is treated as unset: codex rejects an empty --model,
    # and an exported-but-blank variable is a common shell accident.
    env_model = os.environ.get("CODEX_MODEL") or DEFAULT_MODEL
    model = args.model if args.model is not None else env_model
    sandbox = args.sandbox
    write_access = sandbox != "read-only"

    # --- codex must be resolvable on PATH before we attempt to run it ---
    if shutil.which("codex") is None:
        _emit(
            _not_found_report(
                model, sandbox, write_access, "codex CLI not found on PATH"
            )
        )
        return EXIT_NOT_FOUND

    logs_dir = project_root / ".agents" / "logs" / "codex"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    response_path = logs_dir / f"{timestamp}-{args.label}.md"
    stderr_path = logs_dir / f"{timestamp}-{args.label}.err.log"

    cwd = args.cwd if args.cwd is not None else project_root
    argv = ["codex", "exec", "--model", model, "--sandbox", sandbox]
    if args.skip_git_repo_check:
        argv.append("--skip-git-repo-check")
    for override in args.config:
        argv.extend(["--config", override])
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
        error = f"codex exec timed out after {args.timeout}s"
    except FileNotFoundError as exc:
        # Defensive fallback: PATH changed between the shutil.which check
        # above and this call, or the resolved entry was not executable.
        _emit(
            _not_found_report(
                model, sandbox, write_access, f"codex CLI not found: {exc}"
            )
        )
        return EXIT_NOT_FOUND
    duration_sec = round(time.monotonic() - start, 3)

    response_path.write_text(stdout_text, encoding="utf-8")
    stderr_file: str | None = None
    if stderr_text:
        stderr_path.write_text(stderr_text, encoding="utf-8")
        stderr_file = _repo_relative(stderr_path, project_root)

    ok = exit_code == 0 and not timed_out
    if not ok and error is None:
        error = f"codex exec exited with code {exit_code}"

    _emit(
        {
            "ok": ok,
            "exit_code": exit_code,
            "model": model,
            "sandbox": sandbox,
            "write_access": write_access,
            "timed_out": timed_out,
            "duration_sec": duration_sec,
            "response_file": _repo_relative(response_path, project_root),
            "stderr_file": stderr_file,
            "response_chars": len(stdout_text),
            "response_head": stdout_text[:400],
            "error": error,
        }
    )
    return EXIT_OK if ok else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
