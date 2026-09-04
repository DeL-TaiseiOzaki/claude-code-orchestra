#!/usr/bin/env python3
"""Invoke a peer CLI agent (Claude Code, Antigravity) as a subagent.

This is the cross-CLI counterpart of ``codex_consult.py``: whichever runtime is
the active main agent, it drives the others through their headless mode with
one hardened contract instead of a hand-written shell-out. A raw
``claude -p`` / ``agy -p`` call has the same four failure modes the Codex
wrapper removes: an open stdin can block on EOF in a non-TTY shell, stderr
redirected away makes a crashed CLI indistinguishable from an empty answer, a
prompt with nested quotes breaks the shell command, and a stalled call has no
deadline. Here the prompt is a single argv element (no shell), stdin is closed,
stdout and stderr are captured to timestamped files under
``.claude/logs/<cli>/``, and every outcome is reported as a single JSON object.

Codex is deliberately NOT accepted here: its sandbox modes and ``--config``
overrides need dedicated validation, so it keeps its own wrapper and there is
exactly one implementation per callee CLI.

Access is unrestricted unless ``--read-only`` is passed, mapped onto each
CLI's native permission flag, so the granted access is always visible in the
call rather than inherited from whatever the callee's own configuration
happens to say. A callee whose headless mode cannot be confined — Antigravity
auto-approves every tool call — refuses ``--read-only`` instead of accepting
it and running unrestricted anyway.

Because the default is unrestricted, every run is bracketed by an
``edit_provenance`` snapshot and the resulting ``edits`` object names the
files the callee actually created, changed, or deleted, including files it
committed. With ``caller`` and ``label`` alongside it, a change in the tree
can be traced back to the subagent that asked for it.

The prompt that was actually sent is always persisted next to the response
(``{stem}.prompt.md``), including on the ``--prompt-stdin`` path, so a consult
stays diagnosable after the fact.

Usage:
    python3 cli_consult.py --cli claude --prompt-file p.txt --label design-review
    echo "Objective: ..." | python3 cli_consult.py --cli antigravity --prompt-stdin
    python3 cli_consult.py --cli claude --prompt-file p.txt --read-only
    python3 cli_consult.py --cli claude --prompt-file p.txt --caller feature-lead
    python3 cli_consult.py --cli claude --prompt-file p.txt \
        --cli-arg=--max-turns --cli-arg 8

Exit codes:
    0  the callee CLI exited 0, did not report an error, and its output was
       saved and verified
    1  bad args (missing/both prompt sources, unreadable prompt file, bad --cwd,
       unparseable --now, rejected passthrough argument, flag unsupported by
       the chosen CLI)
    2  the callee CLI is not on PATH
    3  the callee CLI failed, reported an error, or timed out, or a log file
       could not be written, created, or verified
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

import edit_provenance

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DEFAULT_TIMEOUT = 900
LABEL_RE = re.compile(r"^[a-z0-9-]+$")

# Per-callee headless contract. `read_only` / `write` are the native permission
# flags this wrapper maps its access choice onto; `install_hint` is what a caller
# sees when the CLI is missing.
CLI_SPECS: dict[str, dict] = {
    "claude": {
        "base": ["claude", "-p", "--output-format", "json"],
        "read_only": ["--permission-mode", "plan"],
        "write": ["--permission-mode", "bypassPermissions"],
        "model_flag": "--model",
        "resume_flag": "--resume",
        "install_hint": "install with `npm install -g @anthropic-ai/claude-code`",
    },
    "antigravity": {
        # Antigravity's headless mode auto-approves every tool call, including
        # `write_file` (google-antigravity/antigravity-cli#45). That made it
        # unusable while the wrappers were read-only by default; under an
        # unrestricted default it simply means `read_only` has no
        # implementation to map onto, which `--read-only` reports as an error
        # rather than granting write access under a read-only-looking flag.
        "base": ["agy", "-p"],
        "read_only": None,
        "write": [],
        "model_flag": "--model",
        "resume_flag": None,
        "install_hint": "install the Antigravity CLI so that `agy` is on PATH",
    },
}

# Passthrough arguments are forwarded verbatim, so the flags that decide what
# the callee may touch are refused: the wrapper's own access flag must stay the
# single visible statement of access, not something a passthrough can quietly
# contradict. This still matters now that the default is unrestricted — the
# denylist is about where access is *declared*, not about which way it points.
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

# Second-granularity timestamps collide: two consults started in the same second
# with the same --label (and `consult` is the default) used to write the same
# response file, so the second run silently destroyed the first run's answer.
# The repository now runs several agents in parallel, so the log stem is
# *reserved* with O_EXCL and a numeric suffix is appended on collision.
MAX_LOG_ATTEMPTS = 100


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

    "The callee answered" and "we saved the answer" are two different claims.
    This makes the second one checked rather than assumed before ``ok: true``.
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
                f"--cli-arg {raw!r} is refused: use --read-only (or its "
                "absence) so the granted access stays visible in the call"
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
        "--read-only",
        action="store_true",
        help=(
            "Deny the callee write access (default: unrestricted). Not every "
            "callee can enforce this; one that cannot refuses the flag."
        ),
    )
    parser.add_argument(
        "--caller",
        default=None,
        help=(
            "Name of the agent making this call (default: $ORCHESTRA_CALLER). "
            "Recorded with the edit set so a change can be traced back to the "
            "subagent that asked for it."
        ),
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
            "flags are refused; use --read-only."
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

    # Refusing is the honest answer: silently running unrestricted under a
    # flag that says read-only would make the call itself a lie about the
    # access it granted.
    if args.read_only and spec["read_only"] is None:
        _emit(
            {
                "ok": False,
                "error": (
                    f"--read-only is not supported for --cli {args.cli}: its "
                    "headless mode auto-approves every tool call, so the "
                    "restriction cannot be enforced from the caller"
                ),
            }
        )
        return EXIT_BAD_ARGS

    # --- Validate passthrough arguments ---
    cli_arg_error = validate_cli_args(args.cli_arg)
    if cli_arg_error:
        _emit({"ok": False, "error": cli_arg_error})
        return EXIT_BAD_ARGS

    # --- Resolve the run's single clock reading ---
    now, now_error = parse_now(args.now)
    if now is None:
        _emit({"ok": False, "error": now_error})
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

    write_access = not args.read_only
    caller = args.caller or os.environ.get("ORCHESTRA_CALLER") or None
    model = args.model

    # --- the callee must be resolvable on PATH before we attempt to run it ---
    if shutil.which(spec["base"][0]) is None:
        _emit(_not_found_report(args.cli, model, write_access))
        return EXIT_NOT_FOUND

    # --- Reserve the log stem before spending a subagent call on it ---
    logs_dir = project_root / ".claude" / "logs" / args.cli
    mkdir_error = _guarded_mkdir(logs_dir)
    if mkdir_error:
        _emit({"ok": False, "cli": args.cli, "error": mkdir_error, "artifacts": []})
        return EXIT_FAILED
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    stem, stem_error = reserve_log_stem(logs_dir, timestamp, args.label)
    if stem is None:
        _emit({"ok": False, "cli": args.cli, "error": stem_error, "artifacts": []})
        return EXIT_FAILED
    response_path = logs_dir / f"{stem}.md"
    stderr_path = logs_dir / f"{stem}.err.log"
    prompt_path = logs_dir / f"{stem}.prompt.md"

    # The prompt is persisted before the call, so a timeout or a crash still
    # leaves the exact text that was sent — including on the --prompt-stdin
    # path, where it previously existed nowhere.
    prompt_write_error = _guarded_write(prompt_path, prompt)
    if prompt_write_error:
        _emit(
            {
                "ok": False,
                "cli": args.cli,
                "error": prompt_write_error,
                "response_file": _repo_relative(response_path, project_root),
                "artifacts": [_repo_relative(response_path, project_root)],
            }
        )
        return EXIT_FAILED

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

    # Provenance brackets the call as tightly as possible: work already in the
    # tree when the snapshot is taken hashes identically afterwards and is not
    # attributed to this run.
    before_snapshot, _ = edit_provenance.take_snapshot(project_root)

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
    edits = edit_provenance.edits_since(project_root, before_snapshot)

    session_id: str | None = None
    reported_error = False
    response_text = stdout_text
    if args.cli == "claude" and not timed_out:
        response_text, session_id, reported_error = extract_claude_result(stdout_text)

    artifacts = [
        _repo_relative(prompt_path, project_root),
        _repo_relative(response_path, project_root),
    ]
    write_failure = _guarded_write(response_path, response_text)
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
        write_failure = _verify_written(response_path, response_text)
        response_verified = write_failure is None

    ok = exit_code == 0 and not timed_out and not reported_error
    if not ok and error is None:
        error = (
            f"{args.cli} reported an error in its result envelope"
            if reported_error
            else f"{args.cli} exited with code {exit_code}"
        )
    if write_failure is not None:
        error = write_failure if error is None else f"{error}; and {write_failure}"
        ok = False

    _emit(
        {
            "ok": ok,
            "exit_code": exit_code,
            "cli": args.cli,
            "model": model,
            "caller": caller,
            "label": args.label,
            "write_access": write_access,
            "edits": edits,
            "session_id": session_id,
            "timed_out": timed_out,
            "duration_sec": duration_sec,
            "prompt_file": _repo_relative(prompt_path, project_root),
            "response_file": _repo_relative(response_path, project_root),
            "response_verified": response_verified,
            "stderr_file": stderr_file,
            "response_chars": len(response_text),
            "response_head": response_text[:400],
            "artifacts": artifacts,
            "error": error,
        }
    )
    return EXIT_OK if ok else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
