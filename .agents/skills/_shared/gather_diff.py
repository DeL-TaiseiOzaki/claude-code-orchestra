#!/usr/bin/env python3
"""Collect the review scope for a change: which files it touched, the full
patch, and the lint/coverage snapshot that goes with it.

Port of the former ``team-execute/gather_diff.sh``, moved into ``_shared/``
because ``simplify`` needs the same file list to prove it stayed inside its
declared scope, and a skill may depend on ``_shared/`` but never on another
skill's directory.

Two behaviours differ from the shell original, both deliberate:

1. **Uncommitted work is in scope.** The original compared ``base...HEAD``,
   i.e. committed history only, while the Agent Teams implement phase never
   commits. With the teammates' edits still in the working tree it therefore
   reported ``changed_files: []`` and exit 0, and the reviewers spawned next
   reviewed nothing and reported a clean review. The scope is now
   ``merge-base(base, HEAD)`` against the **working tree**, including staged,
   unstaged and untracked files. ``--no-include-uncommitted`` restores the
   committed-only view when that is what the caller actually wants.
2. **An empty scope is a failure, not a pass.** ``scope_empty: true`` and exit
   2, so "there was nothing to review" can never be read as "reviewed, clean".

``ruff`` follows ``verify.sh``'s vocabulary: an absent linter is
``status: "skipped"`` with a reason, never ``ok: false`` — a tool that is not
installed has not reported a lint failure. It lints only the changed Python
files (``scope: "changed_files"``), so pre-existing repo-wide lint debt is not
attributed to this change.

Usage:
    python3 gather_diff.py
    python3 gather_diff.py --base origin/main --out .agents/logs/review-diff.patch
    python3 gather_diff.py --no-include-uncommitted
    python3 gather_diff.py --project-root /path/to/repo --base HEAD~3

Exit codes:
    0  scope collected and non-empty
    1  bad arguments, or --project-root / --out is not usable
    2  contract violation — not a git repository, base ref not found, or the
       diff is empty (``scope_empty: true``)
    3  external failure — git failed unexpectedly, or the patch could not be
       written
"""

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DEFAULT_BASE = "main"
DEFAULT_OUT = ".agents/logs/review-diff.patch"
GIT_TIMEOUT = 120
RUFF_TIMEOUT = 180

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_CONTRACT_VIOLATION = 2
EXIT_EXTERNAL_FAILURE = 3


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as this tool's own JSON object
    on stdout with exit 1, instead of argparse's stderr text with exit 2."""

    def error(self, message: str) -> NoReturn:
        emit({"ok": False, "error": message}, EXIT_BAD_INPUT)


def emit(payload: dict, code: int) -> NoReturn:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(code)


class GitFailure(Exception):
    """A git invocation failed in a way the caller must be told about."""

    def __init__(self, message: str, code: int = EXIT_EXTERNAL_FAILURE) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def git_bytes(root: Path, *args: str, ok_codes: tuple[int, ...] = (0,)) -> bytes:
    """Run git in *root* and return stdout, raising GitFailure on an
    unexpected exit code. stderr is captured and reported, never discarded."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise GitFailure(f"git is not available: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitFailure(f"git timed out after {GIT_TIMEOUT}s: {args}") from exc
    if proc.returncode not in ok_codes:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise GitFailure(f"git {' '.join(args)} failed ({proc.returncode}): {detail}")
    return proc.stdout


def git_text(root: Path, *args: str, ok_codes: tuple[int, ...] = (0,)) -> str:
    return git_bytes(root, *args, ok_codes=ok_codes).decode("utf-8", errors="replace")


def git_lines(root: Path, *args: str) -> list[str]:
    return [line for line in git_text(root, *args).splitlines() if line.strip()]


def git_succeeds(root: Path, *args: str) -> bool:
    """True when git exits 0.

    Used only for probes whose failure is itself a reported state (no repo, no
    such ref), so the exit code is the answer rather than an error. git not
    being installed is *not* such a state and still raises GitFailure.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise GitFailure(f"git is not available: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitFailure(f"git timed out after {GIT_TIMEOUT}s: {args}") from exc
    return proc.returncode == 0


# --- scope collection --------------------------------------------------------


def collect_untracked_patch(root: Path, paths: list[str]) -> bytes:
    """Patch text for untracked files, which ``git diff`` never shows.

    ``git diff --no-index`` exits 1 when the two inputs differ, which is the
    normal case here, so 1 is an expected code rather than a failure.
    """
    chunks: list[bytes] = []
    for rel in paths:
        chunks.append(
            git_bytes(
                root,
                "diff",
                "--no-index",
                "--binary",
                "--",
                "/dev/null",
                rel,
                ok_codes=(0, 1),
            )
        )
    return b"".join(chunks)


def build_scope(root: Path, base: str, include_uncommitted: bool, exclude: str) -> dict:
    """Resolve the review scope. Raises GitFailure for every failed state.

    *exclude* is this run's own patch path: it is an output, not a change, and
    leaving it in would make the second run's scope differ from the first's.
    """
    if not git_succeeds(root, "rev-parse", "--is-inside-work-tree"):
        raise GitFailure(f"not a git repository: {root}", EXIT_CONTRACT_VIOLATION)
    if not git_succeeds(root, "rev-parse", "--verify", "--quiet", "HEAD"):
        raise GitFailure("repository has no commits", EXIT_CONTRACT_VIOLATION)
    if not git_succeeds(root, "rev-parse", "--verify", "--quiet", base):
        raise GitFailure(f"base ref not found: {base}", EXIT_CONTRACT_VIOLATION)

    if not git_succeeds(root, "merge-base", base, "HEAD"):
        raise GitFailure(
            f"no merge base between {base} and HEAD", EXIT_CONTRACT_VIOLATION
        )
    merge_base = git_text(root, "merge-base", base, "HEAD").strip()
    head = git_text(root, "rev-parse", "--short", "HEAD").strip()

    def keep(paths: list[str]) -> list[str]:
        return [p for p in paths if p != exclude]

    committed = keep(git_lines(root, "diff", "--name-only", merge_base, "HEAD"))
    commits = git_lines(root, "log", "--oneline", f"{merge_base}..HEAD")

    if include_uncommitted:
        worktree = keep(git_lines(root, "diff", "--name-only", "HEAD"))
        untracked = keep(git_lines(root, "ls-files", "--others", "--exclude-standard"))
        # A single `git diff <merge-base>` spans commits *and* the working
        # tree, which is exactly the union the reviewers must see.
        patch = git_bytes(root, "diff", merge_base)
        patch += collect_untracked_patch(root, untracked)
        shortstat = git_text(root, "diff", "--shortstat", merge_base).strip()
    else:
        worktree = []
        untracked = []
        patch = git_bytes(root, "diff", merge_base, "HEAD")
        shortstat = git_text(root, "diff", "--shortstat", merge_base, "HEAD").strip()

    changed = sorted(set(committed) | set(worktree) | set(untracked))
    diffstat = shortstat
    if untracked:
        suffix = f"{len(untracked)} untracked file(s)"
        diffstat = f"{shortstat}, {suffix}" if shortstat else suffix

    return {
        "base": base,
        "merge_base": merge_base,
        "head": head,
        "include_uncommitted": include_uncommitted,
        "changed_files": changed,
        "committed_files": committed,
        "worktree_files": worktree,
        "untracked_files": untracked,
        "scope_empty": not changed,
        "diffstat": diffstat,
        "commits": commits,
        "_patch": patch,
    }


# --- ruff snapshot -----------------------------------------------------------


def ruff_snapshot(root: Path, changed_files: list[str]) -> dict:
    """Lint the changed Python files.

    ``verify.sh`` reports an absent tool as ``status: "skipped"``; the shell
    original reported ``ok: false``, so a machine without ruff installed looked
    like a change with lint errors. This aligns on the ``verify.sh`` form.
    """
    snapshot: dict = {"scope": "changed_files"}
    if shutil.which("ruff") is None:
        return {**snapshot, "status": "skipped", "reason": "ruff not available"}

    targets = [f for f in changed_files if f.endswith(".py") and (root / f).is_file()]
    if not targets:
        return {**snapshot, "status": "skipped", "reason": "no changed Python files"}

    try:
        proc = subprocess.run(
            [
                "ruff",
                "check",
                "--output-format=json",
                "--force-exclude",
                "--",
                *targets,
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=RUFF_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {**snapshot, "status": "error", "reason": f"ruff could not run: {exc}"}

    snapshot["exit_code"] = proc.returncode
    snapshot["files_linted"] = len(targets)
    try:
        issues = json.loads(proc.stdout)
    except ValueError:
        snapshot["status"] = "error"
        snapshot["reason"] = "ruff output unparseable"
        return snapshot
    snapshot["issues"] = len(issues)
    snapshot["status"] = "pass" if not issues else "fail"
    return snapshot


# --- coverage snapshot -------------------------------------------------------


def _percent_from_json(path: Path) -> tuple[float | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"cannot read {path.name}: {exc}"
    percent = data.get("totals", {}).get("percent_covered")
    if not isinstance(percent, (int, float)):
        return None, f"{path.name} has no totals.percent_covered"
    return round(float(percent), 2), None


def _percent_from_xml(path: Path) -> tuple[float | None, str | None]:
    try:
        root_el = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return None, f"cannot read {path.name}: {exc}"
    rate = root_el.get("line-rate")
    if rate is None:
        return None, f"{path.name} has no line-rate attribute"
    try:
        return round(float(rate) * 100, 2), None
    except ValueError:
        return None, f"{path.name} line-rate is not a number: {rate!r}"


def coverage_snapshot(root: Path, scope: dict) -> tuple[dict | None, list[str]]:
    """Parse an existing coverage report, or report its absence loudly.

    ``percent`` is the parsed total, never a number an agent had to invent.
    ``stale_vs_scope`` is true when the report file is older than the newest
    thing in scope (the HEAD commit, or the newest changed file on disk), i.e.
    when it cannot describe this change.
    """
    warnings: list[str] = []
    candidates = [root / "coverage.json", root / "coverage.xml"]
    report = next((c for c in candidates if c.is_file()), None)
    if report is None:
        warnings.append(
            "no coverage.json / coverage.xml found: coverage is null, "
            "produce it before reporting a percentage"
        )
        return None, warnings

    percent, reason = (
        _percent_from_json(report)
        if report.suffix == ".json"
        else _percent_from_xml(report)
    )
    if reason:
        warnings.append(reason)

    try:
        report_mtime = report.stat().st_mtime
    except OSError as exc:
        warnings.append(f"cannot stat {report.name}: {exc}")
        report_mtime = None

    newest = 0.0
    head_time = git_text(root, "show", "-s", "--format=%ct", "HEAD").strip()
    if head_time.isdigit():
        newest = float(head_time)
    for rel in scope["changed_files"]:
        path = root / rel
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue

    stale = None if report_mtime is None else report_mtime < newest
    mtime_iso = (
        None
        if report_mtime is None
        else datetime.fromtimestamp(report_mtime, tz=UTC).isoformat()
    )
    if stale:
        warnings.append(
            f"{report.name} predates the newest file in scope: "
            "the percentage does not describe this change"
        )
    return {
        "report": report.name,
        "percent": percent,
        "mtime": mtime_iso,
        "stale_vs_scope": stale,
    }, warnings


# --- main --------------------------------------------------------------------


def resolve_out(root: Path, raw: str) -> Path:
    candidate = Path(raw)
    out = candidate if candidate.is_absolute() else root / candidate
    try:
        out = out.resolve()
        out.relative_to(root.resolve())
    except ValueError:
        emit(
            {"ok": False, "error": f"--out must be inside the project root: {raw}"},
            EXIT_BAD_INPUT,
        )
    except OSError as exc:
        emit({"ok": False, "error": f"cannot resolve --out: {exc}"}, EXIT_BAD_INPUT)
    return out


def write_patch(out: Path, patch: bytes) -> None:
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(patch)
    except OSError as exc:
        emit(
            {"ok": False, "error": f"cannot write patch file: {exc}"},
            EXIT_EXTERNAL_FAILURE,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Collect the review scope of a change")
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Base ref to compare against (default: {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--include-uncommitted",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Include staged, unstaged and untracked work in the scope "
            "(default: on). --no-include-uncommitted compares committed "
            "history only, which is what the shell original did."
        ),
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"Where to write the full patch (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Repository root to inspect",
    )
    return parser


def main() -> NoReturn:
    args = build_parser().parse_args()

    root = Path(args.project_root)
    if not root.is_dir():
        emit(
            {"ok": False, "error": f"project root is not a directory: {root}"},
            EXIT_BAD_INPUT,
        )
    out = resolve_out(root, args.out)
    diff_file = out.relative_to(root.resolve()).as_posix()

    try:
        scope = build_scope(root, args.base, args.include_uncommitted, diff_file)
    except GitFailure as exc:
        emit({"ok": False, "error": exc.message, "base": args.base}, exc.code)

    patch = scope.pop("_patch")
    write_patch(out, patch)

    try:
        coverage, warnings = coverage_snapshot(root, scope)
    except GitFailure as exc:
        coverage, warnings = None, [exc.message]

    scope_empty = scope["scope_empty"]
    if scope_empty:
        warnings.append(
            "the diff is empty: nothing was changed relative to "
            f"{args.base}. Do not spawn reviewers — an empty scope reviewed "
            "clean is indistinguishable from a reviewed clean change."
        )

    report = {
        "ok": not scope_empty,
        **scope,
        "diff_file": diff_file,
        "patch_bytes": len(patch),
        "ruff": ruff_snapshot(root, scope["changed_files"]),
        "coverage": coverage,
        "warnings": warnings,
        "artifacts": [diff_file],
    }
    emit(report, EXIT_CONTRACT_VIOLATION if scope_empty else EXIT_OK)


if __name__ == "__main__":
    main()
