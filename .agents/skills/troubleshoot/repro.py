#!/usr/bin/env python3
"""Reproduce an error, capture its context, and optionally assert its exit code.

Runs the repro command under a deadline, records stdout/stderr/exit code (plus
an extracted CPython traceback) to a log file, gathers git context, and emits
one JSON object on stdout. The repro command's own result is reported *inside*
the JSON as ``exit_code``; the script's exit code describes the capture itself,
except when ``--expect-exit`` is given, which turns "the fix works" into an
exit code instead of prose.

Port of the former ``repro.sh``, which had no deadline (a hanging repro command
blocked the caller forever), emitted invalid JSON for arguments containing a
quote, parsed a ``--bisect-good`` flag it never used, and reported an absent git
repository as an empty history.

Usage:
    python3 repro.py "python3 -m pytest tests/test_x.py"
    python3 repro.py --command "make test" --file src/x.py --label auth-bug
    python3 repro.py "python3 -m pytest tests/test_x.py" --expect-exit 0
    python3 repro.py "make test" --timeout 600 --bisect-good v1.2.0

Exit codes:
    0  capture completed (and matched --expect-exit, when given)
    1  bad arguments, or an unusable --label / --bisect-good ref
    2  contract violation — the observed exit code differs from --expect-exit
    3  external failure — the repro command timed out, could not be started,
       or the log file could not be written
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_EXPECTATION_FAILED = 2
EXIT_EXTERNAL_FAILURE = 3

TAIL_LINES = 40
RECENT_COMMITS = 20
DEFAULT_TIMEOUT = 120

# --label keys the log file, so it is constrained to what is safe in a filename:
# same character class as workspace.py's SLUG_RE (which is the part that keeps
# "../escape" out of the log path), but longer, because callers key the log by
# workspace slug *plus* a phase suffix ("{slug}-fix-verify") and a slug may
# already be 64 characters.
LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")

# The only traceback format this script recognizes. Reported as
# ``traceback_format`` so "traceback": null is readable as "no *CPython*
# traceback found" rather than "no stack information exists" — a Node, Go, or
# pytest-assertion failure puts its stack in stderr_tail instead. Guessing at
# more formats would turn an uncertain match into an authoritative claim.
PYTHON_TRACEBACK_MARKER = "Traceback (most recent call last)"


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as this tool's own JSON +
    exit 1 contract, instead of argparse's stderr text + exit 2 (which would
    collide with the shared meaning of exit 2)."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_ARGS)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _tail(text: str, lines: int) -> str:
    return "\n".join(text.splitlines()[-lines:])


def _nonempty_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def extract_traceback(stderr_text: str) -> tuple[str | None, str | None]:
    """Return (traceback, traceback_format) for *stderr_text*."""
    index = stderr_text.find(PYTHON_TRACEBACK_MARKER)
    if index == -1:
        return None, None
    return stderr_text[index:].strip(), "python"


def _git(project_root: Path, *args: str) -> tuple[int, str, str]:
    """Run one git command in *project_root*; never raises.

    Returns (returncode, stdout, stderr). A missing git binary is reported as
    returncode 127 with the reason in stderr, so the caller can surface it
    rather than mistake it for an empty result.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return 127, "", "git executable not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"git {' '.join(args)} timed out"
    return completed.returncode, completed.stdout, completed.stderr.strip()


def git_context(
    project_root: Path, blame_file: str | None
) -> tuple[bool, str | None, list[str], str | None, str | None]:
    """Collect git history context honestly.

    Returns (git_available, git_error, recent_commits, blame, blame_error).
    Outside a work tree the caller gets ``git_available: false`` plus the
    reason, never a silent empty commit list that reads as "no relevant
    history".
    """
    code, _out, err = _git(project_root, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        reason = err or f"not a git work tree: {project_root}"
        return False, reason, [], None, None

    code, out, err = _git(project_root, "log", "--oneline", "-n", str(RECENT_COMMITS))
    if code != 0:
        return True, err or "git log failed", [], None, None
    recent = _nonempty_lines(out)

    blame: str | None = None
    blame_error: str | None = None
    if blame_file is not None:
        if not (project_root / blame_file).exists():
            blame_error = f"file not found: {blame_file}"
        else:
            code, out, err = _git(
                project_root, "log", "-1", "--oneline", "--", blame_file
            )
            lines = _nonempty_lines(out)
            if code != 0:
                blame_error = err or "git log failed for --file"
            elif not lines:
                blame_error = f"no commit touches {blame_file}"
            else:
                blame = lines[0]
    return True, None, recent, blame, blame_error


def bisect_context(
    project_root: Path, good_ref: str, blame_file: str | None
) -> dict[str, object]:
    """Report the commit range a `git bisect` would search.

    Deliberately does **not** drive a bisect: checking out commits mutates the
    working tree, and re-running an unknown repro command per commit is not
    something a capture script may do behind the caller's back. What is
    mechanical — which commits are candidates, how many there are, and the
    exact command to start the bisect — is what gets reported. This replaces
    the former ``repro.sh --bisect-good``, which was parsed and then ignored.
    """
    args = ["log", "--oneline", f"{good_ref}..HEAD"]
    if blame_file is not None:
        args += ["--", blame_file]
    code, out, err = _git(project_root, *args)
    if code != 0:
        return {
            "good_ref": good_ref,
            "error": err or f"cannot list commits since {good_ref}",
            "candidate_commits": [],
            "candidate_count": 0,
            "bisect_command": None,
        }
    commits = _nonempty_lines(out)
    return {
        "good_ref": good_ref,
        "error": None,
        "candidate_commits": commits,
        "candidate_count": len(commits),
        "path_filter": blame_file,
        "bisect_command": f"git bisect start HEAD {good_ref}",
    }


def run_repro(
    command: str, timeout: int, work_dir: Path
) -> tuple[int | None, bool, str, str, str | None]:
    """Run *command* under a deadline, capturing output to files in *work_dir*.

    Returns (exit_code, timed_out, stdout_text, stderr_text, error). ``error``
    is set only when the command could not be started at all.
    """
    out_path = work_dir / "stdout"
    err_path = work_dir / "stderr"
    exit_code: int | None = None
    timed_out = False
    try:
        with out_path.open("wb") as out_fh, err_path.open("wb") as err_fh:
            try:
                completed = subprocess.run(
                    ["bash", "-c", command],
                    stdin=subprocess.DEVNULL,
                    stdout=out_fh,
                    stderr=err_fh,
                    timeout=timeout,
                )
                exit_code = completed.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
    except FileNotFoundError as exc:
        return None, False, "", "", f"cannot run the repro command: {exc}"
    except OSError as exc:
        return None, False, "", "", f"cannot capture repro output: {exc}"
    return exit_code, timed_out, _read_text(out_path), _read_text(err_path), None


def write_log(
    log_path: Path,
    command: str,
    exit_code: int | None,
    timed_out: bool,
    timeout: int,
    stdout_text: str,
    stderr_text: str,
) -> str | None:
    """Write the full capture log; return an error message on failure."""
    status = f"timed out after {timeout}s" if timed_out else str(exit_code)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as handle:
            handle.write(f"# repro command: {command}\n")
            handle.write(f"# exit code: {status}\n")
            handle.write("# --- stdout ---\n")
            handle.write(stdout_text)
            handle.write("\n# --- stderr ---\n")
            handle.write(stderr_text)
    except OSError as exc:
        return f"cannot write log file: {exc}"
    return None


def validate_args(args: argparse.Namespace) -> str | None:
    """Return an error message if *args* violates the CLI contract, else None."""
    command = args.command if args.command is not None else args.command_positional
    if not command or not command.strip():
        return "a repro command is required (positional or --command)"
    if args.command is not None and args.command_positional is not None:
        return "pass the repro command once: positionally or via --command"
    if args.timeout <= 0:
        return "'--timeout' must be a positive number of seconds"
    if args.label is not None and not LABEL_RE.match(args.label):
        return "'--label' must match [a-z0-9][a-z0-9-]{0,95}"
    if not args.project_root.is_dir():
        return f"'--project-root' is not a directory: {args.project_root}"
    return None


def main() -> int:
    parser = JsonArgumentParser(
        description="Reproduce an error and capture its context as JSON",
    )
    parser.add_argument(
        "command_positional",
        nargs="?",
        metavar="COMMAND",
        help="The repro command to run (shell string)",
    )
    parser.add_argument(
        "--command",
        help="The repro command to run; equivalent to the positional form",
    )
    parser.add_argument(
        "--file",
        dest="blame_file",
        help="Repo-relative file from the stack trace, for last-commit context",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"Deadline for the repro command (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--expect-exit",
        type=int,
        default=None,
        metavar="N",
        help="Require this exit code from the repro command; a mismatch is exit 2",
    )
    parser.add_argument(
        "--bisect-good",
        metavar="REF",
        help="Last known-good ref; report the commits a git bisect would search",
    )
    parser.add_argument(
        "--label",
        help="Keys the log file, so a later run cannot overwrite this evidence",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    error = validate_args(args)
    if error:
        _emit({"ok": False, "error": error})
        return EXIT_BAD_ARGS

    command: str = args.command if args.command is not None else args.command_positional
    project_root: Path = args.project_root

    git_available, git_error, recent, blame, blame_error = git_context(
        project_root, args.blame_file
    )

    bisect: dict[str, object] | None = None
    if args.bisect_good is not None:
        if not git_available:
            _emit(
                {
                    "ok": False,
                    "error": f"'--bisect-good' needs a git work tree: {git_error}",
                }
            )
            return EXIT_BAD_ARGS
        code, _out, err = _git(
            project_root,
            "rev-parse",
            "--verify",
            "--quiet",
            f"{args.bisect_good}^{{commit}}",
        )
        if code != 0:
            _emit(
                {
                    "ok": False,
                    "error": (
                        f"'--bisect-good' is not a resolvable commit: "
                        f"{args.bisect_good}" + (f" ({err})" if err else "")
                    ),
                }
            )
            return EXIT_BAD_ARGS
        bisect = bisect_context(project_root, args.bisect_good, args.blame_file)

    suffix = f"-{args.label}" if args.label else ""
    log_rel = f".agents/logs/troubleshoot-repro{suffix}.log"
    log_path = project_root / log_rel

    with tempfile.TemporaryDirectory(prefix="repro-") as tmp_dir:
        exit_code, timed_out, stdout_text, stderr_text, run_error = run_repro(
            command, args.timeout, Path(tmp_dir)
        )
    if run_error:
        _emit({"ok": False, "error": run_error, "repro_command": command})
        return EXIT_EXTERNAL_FAILURE

    log_error = write_log(
        log_path,
        command,
        exit_code,
        timed_out,
        args.timeout,
        stdout_text,
        stderr_text,
    )

    traceback_text, traceback_format = extract_traceback(stderr_text)
    expectation_failed = args.expect_exit is not None and exit_code != args.expect_exit

    ok = not timed_out and log_error is None and not expectation_failed
    report: dict[str, object] = {
        "ok": ok,
        "repro_command": command,
        "label": args.label,
        "timeout": args.timeout,
        "exit_code": exit_code,
        "expected_exit": args.expect_exit,
        "timed_out": timed_out,
        "stdout_tail": _tail(stdout_text, TAIL_LINES),
        "stderr_tail": _tail(stderr_text, TAIL_LINES),
        "traceback": traceback_text,
        "traceback_format": traceback_format,
        "git_available": git_available,
        "git_error": git_error,
        "recent_commits": recent,
        "blame": blame,
        "blame_error": blame_error,
        "bisect": bisect,
        "log_file": None if log_error else log_rel,
        "artifacts": [] if log_error else [log_rel],
    }
    if timed_out:
        report["error"] = f"repro command timed out after {args.timeout}s"
    elif log_error:
        report["error"] = log_error
    elif expectation_failed:
        report["error"] = f"expected exit {args.expect_exit}, got {exit_code}"
    _emit(report)

    if timed_out or log_error:
        return EXIT_EXTERNAL_FAILURE
    if expectation_failed:
        return EXIT_EXPECTATION_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
