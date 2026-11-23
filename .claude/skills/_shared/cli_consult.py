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
CLI's native mechanism so the granted access is visible in the call: Claude
``--permission-mode bypassPermissions`` / ``plan``; Antigravity
``--dangerously-skip-permissions`` / session-only ``--settings`` deny rules for
``write_file(*)``, ``command(*)``, ``mcp(*)``, ``read_url(*)``, and
``execute_url(*)`` (deny outranks the user's own allow rules; ``--mode plan`` is
not read-only and is never used).
``--add-dir DIR`` (repeatable) adds a directory outside the repository, such as
media, to the callee's workspace for one run, as an absolute path.

Antigravity runs with ``--output-format json`` and the prompt attached as the
final argv element (``-p=<prompt>``). agy exits 0 with ``SUCCESS`` even after
refusing work, so a non-``SUCCESS`` status, an empty ``response``, or a
non-JSON envelope fails the run (raw stdout kept in the response file), and
``denied_actions``, soft-deny stderr, and deny-rule messages become
``warnings``. ``--resume`` is refused: agy restores no history in print mode.
A prompt over Linux's single-argument limit (``MAX_ARG_STRLEN``, 128 KiB) is
refused before anything is spawned; pass long inputs by absolute path.

Because the default is unrestricted, every run is bracketed by an
``edit_provenance`` snapshot and the resulting ``edits`` object names the
files the callee actually created, changed, or deleted, including files it
committed. With ``caller`` and ``label`` alongside it, a change in the tree
can be traced back to the subagent that asked for it. ``executor_contract.py``
prefixes every prompt with the executor contract and sets
``ORCHESTRA_ROLE=executor``; the composed prompt actually sent (which the argv
limit applies to) is persisted as ``{stem}.prompt.md``, ``--prompt-stdin`` too.

Usage:
    python3 cli_consult.py --cli claude --prompt-file p.txt --label design-review
    echo "Objective: ..." | python3 cli_consult.py --cli antigravity --prompt-stdin
    python3 cli_consult.py --cli antigravity --prompt-file p.txt --read-only \
        --add-dir /abs/path/to/media
    python3 cli_consult.py --cli claude --prompt-file p.txt --caller feature-lead
    python3 cli_consult.py --cli claude --prompt-file p.txt \
        --cli-arg=--max-turns --cli-arg 8

Exit codes:
    0  the callee CLI exited 0, did not report an error, and its output was
       saved and verified
    1  bad args (missing/both prompt sources, unreadable prompt file, bad --cwd
       or --add-dir, unparseable --now, rejected passthrough argument, flag
       unsupported by the chosen CLI, prompt over the single-argv limit)
    2  the callee CLI is not on PATH
    3  the callee CLI could not be started, failed, reported an error (for
       Antigravity: a non-SUCCESS status, an empty response, or an
       unparseable envelope), or timed out, a log file could not be
       written, created, or verified, or the executor contract is unreadable
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

import edit_provenance
import executor_contract
from agy_envelope import antigravity_warnings, extract_antigravity_result

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DEFAULT_TIMEOUT = 900
LABEL_RE = re.compile(r"^[a-z0-9-]+$")


# Session-only deny rules for a read-only Antigravity run (`--settings` is
# never saved). `command(*)` also blocks read-only shell use, so the callee
# must read with its file-view tools. Reads are not confined to the workspace,
# so URL fetch and browser actions are denied too (defence in depth: agy 1.5.14
# print mode offers neither). `search_web` has no deny action and stays usable.
ANTIGRAVITY_READ_ONLY_DENY_RULES = tuple(
    "write_file(*) command(*) mcp(*) read_url(*) execute_url(*)".split()
)
ANTIGRAVITY_READ_ONLY_SETTINGS = json.dumps(
    {"permissions": {"deny": list(ANTIGRAVITY_READ_ONLY_DENY_RULES)}},
    separators=(",", ":"),
)

# Per-callee headless contract. `read_only` / `write` are the native permission
# flags this wrapper maps its access choice onto; `output_flags` and
# `prompt_flag` place the prompt; `install_hint` is what a caller sees when the
# CLI is missing.
CLI_SPECS: dict[str, dict] = {
    "claude": {
        "base": ["claude", "-p", "--output-format", "json"],
        "read_only": ["--permission-mode", "plan"],
        "write": ["--permission-mode", "bypassPermissions"],
        "model_flag": "--model",
        "resume_flag": "--resume",
        "resume_refusal": None,
        "add_dir_flag": "--add-dir",
        "output_flags": [],
        # Positional: the prompt is the bare final argv element.
        "prompt_flag": None,
        "install_hint": "install with `npm install -g @anthropic-ai/claude-code`",
    },
    "antigravity": {
        "base": ["agy"],
        "read_only": ["--settings", ANTIGRAVITY_READ_ONLY_SETTINGS],
        # Matches Claude's bypassPermissions and Codex's danger-full-access.
        # agy's own default (`auto`) lets an LLM risk judge soft-deny steps
        # while the run still exits 0, which is not "unrestricted".
        "write": ["--dangerously-skip-permissions"],
        "model_flag": "--model",
        "resume_flag": None,
        "resume_refusal": (
            "agy accepts --conversation but does not restore history in print mode"
        ),
        "add_dir_flag": "--add-dir",
        "output_flags": ["--output-format", "json"],
        # `-p` takes the prompt as its value, so it must come last; the
        # attached form keeps flag and prompt in one argv element.
        "prompt_flag": "-p",
        "install_hint": "install the Antigravity CLI so that `agy` is on PATH",
    },
}

# Passthrough flags that decide what the callee may touch are refused: the
# wrapper's own access flag stays the single visible statement of access, in
# either direction. Substring match: any spelling names an access decision.
CLI_ARG_ACCESS_SUBSTRINGS = (
    "permission-mode",
    "allowedtools",
    "allowed-tools",
    "disallowedtools",
    "disallowed-tools",
    "sandbox",
    "dangerously",
)
# Exact match only: `mode` is a substring of `--model` and `--fallback-model`.
CLI_ARG_ACCESS_EXACT = frozenset({"mode", "settings"})
# Flags the wrapper sets itself (or deliberately does not offer), also exact.
CLI_ARG_WRAPPER_EXACT = frozenset(
    "add-dir conversation continue c resume r output-format input-format "
    "print prompt p prompt-interactive i remote-agent remote-control".split()
)
# Flags that make the callee process itself write a file (agy's own CLI log) to
# a caller-chosen path; no deny rule covers that, so --read-only could not.
CLI_ARG_SIDE_EFFECT_EXACT = frozenset({"log-file"})

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_NOT_FOUND = 2
EXIT_FAILED = 3

# Same-second consults with the same --label used to overwrite each other's
# response file, so the log stem is reserved with O_EXCL (numeric suffix on
# collision).
MAX_LOG_ATTEMPTS = 100


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """Report usage errors as one JSON object with exit 1, never argparse's
    stderr text + exit 2 (which would read as "CLI not on PATH")."""

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
        return datetime.now(tz=timezone.utc), None
    # Python 3.10's fromisoformat rejects the "Z" designator that 3.11 accepts.
    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        return datetime.fromisoformat(normalized), None
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


def validate_cli_args(cli_args: list[str | list]) -> str | None:
    """Return an error message if any ``--cli-arg`` passthrough is unusable.

    Non-flag entries are flag *values* (``--cli-arg --max-turns --cli-arg 8``)
    and pass through untouched: each is its own argv element, never shell-
    expanded. Only flags are screened: access flags against the access
    denylist, and the flags the wrapper itself owns by exact name.
    """
    for entry in cli_args:
        # Python 3.10's argparse strips a lone "--" from an option value and
        # stores an empty list in its place.
        raw = entry if isinstance(entry, str) else "--"
        if not raw.startswith("-"):
            continue
        name = raw.lstrip("-").split("=", 1)[0].lower()
        if not name:
            return (
                f"--cli-arg {raw!r} is refused: it would end option parsing "
                "before the flags and prompt the wrapper appends"
            )
        if name in CLI_ARG_ACCESS_EXACT or any(
            denied in name for denied in CLI_ARG_ACCESS_SUBSTRINGS
        ):
            return (
                f"--cli-arg {raw!r} is refused: use --read-only (or its "
                "absence) so the granted access stays visible in the call"
            )
        if name in CLI_ARG_WRAPPER_EXACT:
            return (
                f"--cli-arg {raw!r} is refused: the wrapper sets this flag "
                "itself; use its own option where one exists (--add-dir, "
                "--resume)"
            )
        if name in CLI_ARG_SIDE_EFFECT_EXACT:
            return (
                f"--cli-arg {raw!r} is refused: it makes the callee write its "
                "own log to a caller-chosen path, which --read-only cannot block"
            )
    return None


def build_argv(
    spec: dict,
    *,
    write_access: bool,
    model: str | None,
    add_dirs: list[str],
    resume: str | None,
    cli_args: list[str],
    prompt: str,
) -> list[str]:
    """Assemble the callee argv; the prompt is always the final element."""
    argv = [*spec["base"], *(spec["write"] if write_access else spec["read_only"])]
    if model is not None:
        argv.extend([spec["model_flag"], model])
    # Attached form: Claude's --add-dir is variadic and would otherwise
    # swallow the positional prompt as one more directory.
    argv.extend(f"{spec['add_dir_flag']}={directory}" for directory in add_dirs)
    if resume is not None:
        argv.extend([spec["resume_flag"], resume])
    argv.extend(cli_args)
    argv.extend(spec["output_flags"])
    # Never shell-expanded. agy's -p consumes its value, so it is attached
    # (-p=<prompt>) and last. agy still checks that value against its own flag
    # names: a prompt that is exactly a flag token (`--model`, `--model=x`,
    # `-c`) exits 2 in either form, reported as exit 3 with stderr saved.
    prompt_flag = spec["prompt_flag"]
    argv.append(prompt if prompt_flag is None else f"{prompt_flag}={prompt}")
    return argv


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


def build_parser() -> JsonArgumentParser:
    """Define the command line."""
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
            "Deny the callee write access (default: unrestricted). claude: "
            "--permission-mode plan. antigravity: session deny rules for "
            "write_file, command, mcp, read_url, and execute_url (writes, "
            "shell, MCP, and URL fetches are blocked; web search is not; reads "
            "use file-view tools)."
        ),
    )
    parser.add_argument(
        "--add-dir",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help=(
            "Add an existing directory to the callee's workspace for this run "
            "(repeatable), e.g. media outside the repository. Sent as an "
            "absolute path."
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
        help=(
            "Continue a prior session by id (claude only; antigravity does "
            "not restore history in print mode)"
        ),
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
            "read: --cli-arg=--max-turns --cli-arg 8. Permission, sandbox, "
            "mode, and settings flags are refused (use --read-only), and so "
            "are flags the wrapper sets itself (prompt, output format, "
            "add-dir, resume/continue) and agy's --log-file."
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
    return parser


def main() -> int:  # noqa: C901 — single-function CLI entry point
    args = build_parser().parse_args()
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

    # --- Validate --add-dir; absolute, so the callee's cwd cannot reinterpret it ---
    for directory in args.add_dir:
        if not directory.is_dir():
            _emit({"ok": False, "error": f"--add-dir is not a directory: {directory}"})
            return EXIT_BAD_ARGS
    add_dirs = [str(directory.resolve()) for directory in args.add_dir]

    # --- Reject flags the chosen callee has no equivalent for ---
    if args.resume is not None and spec["resume_flag"] is None:
        _emit(
            {
                "ok": False,
                "error": (
                    f"--resume is not supported for --cli {args.cli}: "
                    f"{spec['resume_refusal']}"
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

    try:  # The callee must know it is a delegated executor, not the main agent.
        prompt, contract_sha = executor_contract.prepare_prompt(prompt)
    except executor_contract.ContractError as exc:
        _emit({"ok": False, "cli": args.cli, "error": str(exc), "artifacts": []})
        return EXIT_FAILED

    write_access = not args.read_only
    caller = args.caller or os.environ.get("ORCHESTRA_CALLER") or None
    model = args.model
    argv = build_argv(
        spec,
        write_access=write_access,
        model=model,
        add_dirs=add_dirs,
        resume=args.resume,
        cli_args=args.cli_arg,
        prompt=prompt,
    )

    # --- Refuse an argv exec would reject, before spending anything on it ---
    oversized_error = executor_contract.oversized_argv_error(argv)
    if oversized_error:
        _emit({"ok": False, "cli": args.cli, "error": oversized_error})
        return EXIT_BAD_ARGS

    # --- the callee must be resolvable on PATH before we attempt to run it ---
    # The resolved path is what runs: exec's own PATH walk would skip an
    # entry it cannot execute and silently start a later same-named binary.
    executable = shutil.which(spec["base"][0])
    if executable is None:
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
            executable=executable,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            cwd=cwd,
            env=executor_contract.executor_env(),
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
        # Defensive fallback: the resolved callee vanished between the
        # shutil.which check above and this call.
        _emit(_not_found_report(args.cli, model, write_access))
        return EXIT_NOT_FOUND
    except OSError as exc:
        # exec itself failed (not executable, exec format error, E2BIG from
        # the total argv + environment size): a JSON error, never a traceback.
        error = f"cannot start {args.cli}: {exc}"
    duration_sec = round(time.monotonic() - start, 3)
    edits = edit_provenance.edits_since(project_root, before_snapshot)

    session_id: str | None = None
    reported_error = False
    response_text = stdout_text
    # Every callee and every failure path reports `denied_actions` as a list.
    envelope: dict = {
        "conversation_id": None,
        "status": None,
        "denied_actions": [],
        "error": None,
    }
    warnings: list[str] = []
    if args.cli == "claude" and not timed_out:
        response_text, session_id, reported_error = extract_claude_result(stdout_text)
    if args.cli == "antigravity" and not timed_out and error is None:
        envelope = extract_antigravity_result(stdout_text)
        response_text = envelope["response"]
        warnings.extend(
            antigravity_warnings(envelope["denied_actions"], stderr_text, response_text)
        )
    if args.read_only and edits.get("files_total"):
        warnings.append(
            f"{edits['files_total']} file(s) recorded as edited under --read-only "
            "(possibly a concurrent writer); inspect `edits`"
        )

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

    if error is None:
        if reported_error:
            error = f"{args.cli} reported an error in its result envelope"
        elif exit_code != 0:
            error = f"{args.cli} exited with code {exit_code}"
        elif envelope["error"] is not None:
            error = envelope["error"]
    if write_failure is not None:
        error = write_failure if error is None else f"{error}; and {write_failure}"
    ok = error is None

    _emit(
        {
            "ok": ok,
            "exit_code": exit_code,
            "cli": args.cli,
            "model": model,
            "caller": caller,
            "label": args.label,
            "write_access": write_access,
            "executor_contract_sha": contract_sha,
            "add_dirs": add_dirs,
            "edits": edits,
            "session_id": session_id,
            "conversation_id": envelope["conversation_id"],
            "envelope_status": envelope["status"],
            "denied_actions": envelope["denied_actions"],
            "warnings": warnings,
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
