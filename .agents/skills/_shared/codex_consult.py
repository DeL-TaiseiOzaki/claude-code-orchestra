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

The prompt that was actually sent is always persisted next to the response
(``{stem}.prompt.md``), including on the ``--prompt-stdin`` path, so a consult
stays diagnosable after the fact. With neither ``--prompt-file`` nor
``--prompt-stdin``, the prompt is read from the label's conventional path,
``.agents/logs/codex/prompt-{label}.md``.

Usage:
    python3 codex_consult.py --prompt-file prompt.txt --label design-review
    python3 codex_consult.py --label design-review   # reads prompt-design-review.md
    echo "Objective: ..." | python3 codex_consult.py --prompt-stdin
    python3 codex_consult.py --prompt-file p.txt --config model_reasoning_effort=low

Exit codes:
    0  codex exec exited 0 and its output was saved and verified
    1  bad args (both prompt sources, unreadable prompt file, bad --cwd,
       unparseable --now)
    2  codex CLI not found on PATH
    3  codex exec exited non-zero or timed out, or a log file could not be
       written, created, or verified
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

# Second-granularity timestamps collide: two consults started in the same second
# with the same --label (and `consult` is the default) used to write the same
# response file, so the second run silently destroyed the first run's answer.
# The repository now runs several agents in parallel, so the log stem is
# *reserved* with O_EXCL and a numeric suffix is appended on collision.
MAX_LOG_ATTEMPTS = 100

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


def parse_now(value: str | None) -> tuple[datetime | None, str | None]:
    """Resolve the run's single clock reading, honouring ``--now``.

    The clock is read exactly once per run so every filename and field in one
    payload agrees, and so a test can pin the log names it then inspects.
    """
    if value is None:
        return datetime.now(tz=UTC), None
    try:
        return datetime.fromisoformat(value), None
    except ValueError:
        return None, f"--now must be an ISO 8601 timestamp, got {value!r}"


def _guarded_mkdir(path: Path) -> str | None:
    """Create *path* and its parents; return an error message, never raise."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"cannot create log directory {path}: {exc}"
    return None


def _guarded_write(path: Path, text: str) -> str | None:
    """Write *text* to *path*; return an error message, never raise.

    An unwritable log directory used to surface as a bare ``OSError``
    traceback with no JSON at all, which a caller reading the exit code alone
    could not distinguish from a bad argument.
    """
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"cannot write {path}: {exc}"
    return None


def _verify_written(path: Path, expected: str) -> str | None:
    """Confirm *path* holds exactly *expected*; return an error message.

    "Codex answered" and "we saved the answer" are two different claims. This
    makes the second one checked rather than assumed before ``ok: true``.
    """
    try:
        actual = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"cannot re-read {path} after writing it: {exc}"
    if actual != expected:
        return (
            f"{path} does not match the captured output "
            f"({len(actual)} chars on disk, {len(expected)} captured)"
        )
    return None


def reserve_log_stem(
    logs_dir: Path, timestamp: str, label: str
) -> tuple[str | None, str | None]:
    """Reserve a unique ``{timestamp}-{label}`` stem inside *logs_dir*.

    The response file is created with ``O_CREAT | O_EXCL`` so a concurrent run
    that picked the same second cannot take the same stem; the loser appends
    ``-2``, ``-3``, … instead of overwriting an existing answer. Returns
    ``(stem, error)`` with exactly one of the two set.
    """
    for attempt in range(1, MAX_LOG_ATTEMPTS + 1):
        stem = (
            f"{timestamp}-{label}" if attempt == 1 else f"{timestamp}-{label}-{attempt}"
        )
        try:
            fd = os.open(logs_dir / f"{stem}.md", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        except OSError as exc:
            return None, f"cannot create response file for {stem!r}: {exc}"
        os.close(fd)
        return stem, None
    return (
        None,
        f"cannot find a free log name for {timestamp}-{label} "
        f"after {MAX_LOG_ATTEMPTS} attempts",
    )


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
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help=(
            "File containing the prompt (default: .agents/logs/codex/prompt-{label}.md)"
        ),
    )
    parser.add_argument(
        "--prompt-stdin",
        action="store_true",
        help="Read the prompt from stdin instead of a file",
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
        "--now",
        default=None,
        help="ISO 8601 timestamp to stamp instead of the real clock",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    args = parser.parse_args()
    project_root = args.project_root

    # --- Validate prompt source: at most one of --prompt-file/--prompt-stdin ---
    # Neither is allowed: the prompt then comes from the label's conventional
    # path, which is what five skills used to hand-type on every call.
    if args.prompt_file is not None and args.prompt_stdin:
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

    # --- Resolve the run's single clock reading ---
    now, now_error = parse_now(args.now)
    if now is None:
        _emit({"ok": False, "error": now_error})
        return EXIT_BAD_ARGS

    logs_dir = project_root / ".agents" / "logs" / "codex"

    # --- Load prompt ---
    prompt_source: Path | None = args.prompt_file
    if prompt_source is None and not args.prompt_stdin:
        prompt_source = logs_dir / f"prompt-{args.label}.md"
    if prompt_source is not None:
        try:
            prompt = prompt_source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            hint = (
                ""
                if args.prompt_file is not None
                else " (the default path for --label; pass --prompt-file or "
                "--prompt-stdin to use another source)"
            )
            _emit({"ok": False, "error": f"cannot read prompt file: {exc}{hint}"})
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

    # --- Reserve the log stem before spending a Codex call on it ---
    mkdir_error = _guarded_mkdir(logs_dir)
    if mkdir_error:
        _emit({"ok": False, "error": mkdir_error, "artifacts": []})
        return EXIT_FAILED
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    stem, stem_error = reserve_log_stem(logs_dir, timestamp, args.label)
    if stem is None:
        _emit({"ok": False, "error": stem_error, "artifacts": []})
        return EXIT_FAILED
    response_path = logs_dir / f"{stem}.md"
    stderr_path = logs_dir / f"{stem}.err.log"
    prompt_path = logs_dir / f"{stem}.prompt.md"

    # The prompt is persisted before the call, so a timeout or a crash still
    # leaves the exact text that was sent — including on the --prompt-stdin
    # path, where it previously existed nowhere.
    write_error = _guarded_write(prompt_path, prompt)
    if write_error:
        _emit(
            {
                "ok": False,
                "error": write_error,
                "response_file": _repo_relative(response_path, project_root),
                "artifacts": [_repo_relative(response_path, project_root)],
            }
        )
        return EXIT_FAILED

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

    artifacts = [
        _repo_relative(prompt_path, project_root),
        _repo_relative(response_path, project_root),
    ]
    write_failure = _guarded_write(response_path, stdout_text)
    stderr_file: str | None = None
    if stderr_text and write_failure is None:
        write_failure = _guarded_write(stderr_path, stderr_text)
        if write_failure is None:
            stderr_file = _repo_relative(stderr_path, project_root)
            artifacts.append(stderr_file)
    # Saving the answer is verified, not assumed: a truncated or replaced
    # response file must not be reported as a successful consult.
    response_verified = False
    if write_failure is None:
        write_failure = _verify_written(response_path, stdout_text)
        response_verified = write_failure is None

    ok = exit_code == 0 and not timed_out and write_failure is None
    if not ok and error is None:
        error = write_failure or f"codex exec exited with code {exit_code}"
    elif write_failure is not None:
        error = f"{error}; and {write_failure}"

    _emit(
        {
            "ok": ok,
            "exit_code": exit_code,
            "model": model,
            "sandbox": sandbox,
            "write_access": write_access,
            "timed_out": timed_out,
            "duration_sec": duration_sec,
            "prompt_file": _repo_relative(prompt_path, project_root),
            "response_file": _repo_relative(response_path, project_root),
            "response_verified": response_verified,
            "stderr_file": stderr_file,
            "response_chars": len(stdout_text),
            "response_head": stdout_text[:400],
            "artifacts": artifacts,
            "error": error,
        }
    )
    return EXIT_OK if ok else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
