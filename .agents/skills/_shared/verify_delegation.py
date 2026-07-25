#!/usr/bin/env python3
"""Collect Guardrail evidence about a delegated run's diff. Never auto-accepts.

`.agents/rules/cli-execution.md` Guardrails require the *caller* to inspect a
delegated run's diff for unapproved deletions, stub/placeholder completions,
out-of-scope changes, and cheating patterns (deleted, skipped, or weakened
tests, swallowed exceptions, hard-coded returns).  That was prose in two rule
files, so it was skipped at exactly the moments it mattered.  This script makes
the *evidence collection* deterministic.

It deliberately does **not** decide.  ``verdict`` is always ``needs-review``:
the pattern list is heuristic, a legitimate test deletion exists, and only the
agent that wrote the prompt knows what the task authorised.  There is no
``clean`` verdict, because an automated accept is exactly the judgment the
Guardrails exist to force.  ``ok`` reports whether collection succeeded — it is
not an accept.

The diff includes uncommitted work (a delegated CLI run usually leaves the tree
dirty) and untracked files, whose lines are scanned as additions.

Usage:
    python3 verify_delegation.py
    python3 verify_delegation.py --base HEAD~1
    python3 verify_delegation.py --expect-files src/a.py --expect-files tests/test_a.py
    python3 verify_delegation.py --forbid-outside src --forbid-outside tests
    python3 verify_delegation.py --label implement --now 2026-07-25T09:00:00

Exit codes:
    0  evidence collected, no finding and no violated expectation
       (still ``needs-review``: read the diff)
    1  bad arguments, or a --base that does not resolve
    2  a finding was collected, or an expectation was violated
       (missing expected file, out-of-scope file, empty scope)
    3  git failed or timed out, or the diff could not be written
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_FINDINGS = 2
EXIT_EXTERNAL = 3

VERDICT = "needs-review"
LABEL_RE = re.compile(r"^[a-z0-9-]+$")
LOG_DIR = Path(".agents") / "logs" / "delegation"

# Only an agent reading the diff can judge this one, so it is named rather than
# faked with a detector that would be either silent or unusably noisy.
NOT_AUTOMATED = (
    "hard-coded return values substituted for real implementation logic "
    "(Guardrail b3) — read the diff",
)

MAX_SAMPLES = 3

TEST_PATH_RE = re.compile(
    r"(^|/)tests?/|(^|/)test_[^/]+\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$"
)

PLACEHOLDER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("todo-marker", re.compile(r"\b(TODO|FIXME|XXX)\b")),
    ("not-implemented", re.compile(r"NotImplementedError|TODO\(\)|unimplemented!")),
    ("pass-stub", re.compile(r"^\s*pass\s*(#.*)?$")),
    ("ellipsis-stub", re.compile(r"^\s*\.\.\.\s*$")),
    (
        "placeholder-text",
        re.compile(r"\b(placeholder|stub for now|for now, return)\b", re.I),
    ),
    ("swallowed-exception", re.compile(r"except\b[^:]*:\s*pass\b")),
    ("swallowed-exception", re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")),
)

WEAKENED_ADDED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("skip-marker", re.compile(r"@(pytest\.mark\.(skip|xfail)|unittest\.skip)")),
    ("skip-call", re.compile(r"\b(pytest\.skip|self\.skipTest)\(")),
    ("skip-marker", re.compile(r"\b(it|test|describe)\.skip\(|\bxit\(|\bxdescribe\(")),
    ("tautological-assertion", re.compile(r"^\s*assert\s+(True|1)\s*(,|$)")),
)

ASSERTION_RE = re.compile(r"\b(assert|expect\()")


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as this tool's own JSON /
    exit-1 contract instead of argparse's stderr text + exit 2, so an
    argparse-level failure never masquerades as exit 2 ("a finding was
    collected")."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "verdict": VERDICT, "error": message, "artifacts": []})
        sys.exit(EXIT_BAD_ARGS)


@dataclass
class FileChange:
    """Per-file accumulation of removed lines and their most telling samples."""

    path: str
    deleted_lines: int = 0
    file_deleted: bool = False
    removed_assertions: int = 0
    samples: list[str] = field(default_factory=list)

    def record_removed(self, line: str) -> None:
        self.deleted_lines += 1
        if ASSERTION_RE.search(line):
            self.removed_assertions += 1
        if len(self.samples) < MAX_SAMPLES:
            self.samples.append(line.strip())


def _fail(error: str, code: int) -> int:
    _emit({"ok": False, "verdict": VERDICT, "error": error, "artifacts": []})
    return code


def _git(root: Path, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run git with an explicit repository root, captured output, and a deadline."""
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def is_test_path(path: str) -> bool:
    """True when *path* looks like a test file, by directory or filename."""
    return bool(TEST_PATH_RE.search(path))


def parse_diff(diff_text: str) -> dict[str, FileChange]:
    """Group a unified diff's removals per file.

    Blank removals are ignored: the Guardrail is about *significant* removed
    code, and counting whitespace churn would bury the signal.
    """
    changes: dict[str, FileChange] = {}
    current: FileChange | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[-1].strip() if " b/" in line else line
            current = changes.setdefault(path, FileChange(path=path))
            continue
        if current is None:
            continue
        if line.startswith("deleted file mode"):
            current.file_deleted = True
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-") and line[1:].strip():
            current.record_removed(line[1:])
    return changes


def added_lines(diff_text: str) -> list[tuple[str, str]]:
    """Return (file, added line) pairs from a unified diff."""
    added: list[tuple[str, str]] = []
    path = ""
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[-1].strip() if " b/" in line else line
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added.append((path, line[1:]))
    return added


def scan_placeholders(pairs: list[tuple[str, str]]) -> list[dict]:
    """Report added lines that look like a stub, a marker, or a swallowed error."""
    found: list[dict] = []
    for path, line in pairs:
        for name, pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(line):
                found.append(
                    {"file": path, "pattern": name, "line": line.strip()[:200]}
                )
                break
    return found


def scan_weakened_tests(
    pairs: list[tuple[str, str]], changes: dict[str, FileChange]
) -> list[dict]:
    """Report skip markers, tautological assertions, and lost test assertions."""
    found: list[dict] = []
    for path, line in pairs:
        if not is_test_path(path):
            continue
        for name, pattern in WEAKENED_ADDED_PATTERNS:
            if pattern.search(line):
                found.append(
                    {"file": path, "pattern": name, "line": line.strip()[:200]}
                )
                break
    for path, change in sorted(changes.items()):
        if not is_test_path(path):
            continue
        if change.file_deleted:
            found.append(
                {
                    "file": path,
                    "pattern": "test-file-deleted",
                    "removed_lines": change.deleted_lines,
                }
            )
        elif change.removed_assertions:
            found.append(
                {
                    "file": path,
                    "pattern": "assertions-removed",
                    "removed_assertions": change.removed_assertions,
                    "samples": change.samples,
                }
            )
    return found


def deletion_report(changes: dict[str, FileChange]) -> list[dict]:
    """Summarise removals per file, bounded to a few samples each."""
    report: list[dict] = []
    for path, change in sorted(changes.items()):
        if not change.deleted_lines and not change.file_deleted:
            continue
        report.append(
            {
                "file": path,
                "file_deleted": change.file_deleted,
                "deleted_lines": change.deleted_lines,
                "samples": change.samples,
            }
        )
    return report


def out_of_scope(files: list[str], allowed: list[str]) -> list[str]:
    """Return the changed files that lie outside every allowed path prefix."""
    if not allowed:
        return []
    prefixes = [a.strip("/") for a in allowed if a.strip("/")]
    outside: list[str] = []
    for path in files:
        if not any(path == p or path.startswith(f"{p}/") for p in prefixes):
            outside.append(path)
    return outside


def _read_untracked(
    root: Path, paths: list[str]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Read untracked files as added lines; return (pairs, unreadable paths)."""
    pairs: list[tuple[str, str]] = []
    unreadable: list[str] = []
    for rel in paths:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable.append(rel)
            continue
        pairs.extend((rel, line) for line in text.splitlines())
    return pairs, unreadable


def _parse_now(raw: str | None) -> datetime:
    """Parse --now, or read the clock exactly once."""
    if raw is None:
        return datetime.now(tz=UTC)
    return datetime.fromisoformat(raw)


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Collect Guardrail evidence about a delegated run (never accepts)",
    )
    parser.add_argument(
        "--base",
        default="HEAD",
        help="Git ref the delegated work started from (default HEAD, i.e. uncommitted work)",
    )
    parser.add_argument(
        "--expect-files",
        action="append",
        default=[],
        metavar="PATH",
        help="Repo-relative path the task was supposed to change (repeatable); "
        "a missing one is exit 2",
    )
    parser.add_argument(
        "--forbid-outside",
        action="append",
        default=[],
        metavar="PATH",
        help="Restrict the change to these paths (repeatable); anything else is "
        "reported as out_of_scope_files and is exit 2",
    )
    parser.add_argument(
        "--label",
        default="delegation",
        help="[a-z0-9-]+ slug used in the captured diff filename (default delegation)",
    )
    parser.add_argument(
        "--timeout", type=int, default=120, help="Per-git-command timeout in seconds"
    )
    parser.add_argument(
        "--now", help="ISO 8601 timestamp to stamp instead of the real clock"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    return parser


def collect(
    root: Path, base: str, timeout: int
) -> tuple[str, list[str], list[str]] | str:
    """Return (diff text, changed files, untracked files), or an error message."""
    diff = _git(root, ["diff", "--no-color", base], timeout)
    if diff.returncode != 0:
        return f"git diff failed: {diff.stderr.strip() or diff.returncode}"
    names = _git(root, ["diff", "--name-only", base], timeout)
    if names.returncode != 0:
        return f"git diff --name-only failed: {names.stderr.strip()}"
    untracked = _git(root, ["ls-files", "--others", "--exclude-standard"], timeout)
    if untracked.returncode != 0:
        return f"git ls-files failed: {untracked.stderr.strip()}"
    changed = [line for line in names.stdout.splitlines() if line]
    new_files = [line for line in untracked.stdout.splitlines() if line]
    return diff.stdout, changed, new_files


def main() -> int:  # noqa: C901 — single-function CLI entry point
    args = _build_parser().parse_args()

    if not LABEL_RE.match(args.label):
        return _fail("'--label' must match [a-z0-9-]+", EXIT_BAD_ARGS)
    if args.timeout <= 0:
        return _fail("'--timeout' must be a positive number of seconds", EXIT_BAD_ARGS)
    try:
        now = _parse_now(args.now)
    except ValueError as exc:
        return _fail(f"cannot parse '--now': {exc}", EXIT_BAD_ARGS)
    root: Path = args.project_root
    if not root.is_dir():
        return _fail(f"'--project-root' is not a directory: {root}", EXIT_BAD_ARGS)

    try:
        inside = _git(root, ["rev-parse", "--is-inside-work-tree"], args.timeout)
        if inside.returncode != 0:
            return _fail(f"not a git repository: {root}", EXIT_EXTERNAL)
        resolved = _git(root, ["rev-parse", "--verify", args.base], args.timeout)
        if resolved.returncode != 0:
            return _fail(f"'--base' does not resolve: {args.base}", EXIT_BAD_ARGS)
        collected = collect(root, args.base, args.timeout)
    except FileNotFoundError:
        return _fail("git is not on PATH", EXIT_EXTERNAL)
    except subprocess.TimeoutExpired:
        return _fail(f"git timed out after {args.timeout}s", EXIT_EXTERNAL)
    if isinstance(collected, str):
        return _fail(collected, EXIT_EXTERNAL)
    diff_text, changed, new_files = collected

    changes = parse_diff(diff_text)
    pairs = added_lines(diff_text)
    untracked_pairs, unreadable = _read_untracked(root, new_files)
    pairs.extend(untracked_pairs)

    all_files = sorted(set(changed) | set(new_files))
    deletions = deletion_report(changes)
    placeholders = scan_placeholders(pairs)
    weakened = scan_weakened_tests(pairs, changes)
    outside = out_of_scope(all_files, args.forbid_outside)
    missing = [path for path in args.expect_files if path not in all_files]
    scope_empty = not all_files

    stamp = now.strftime("%Y%m%d-%H%M%S")
    diff_path = root / LOG_DIR / f"{args.label}-{stamp}.diff"
    body = diff_text
    if new_files:
        body += "\n# untracked files (scanned as additions)\n"
        body += "".join(f"# {path}\n" for path in new_files)
    try:
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        return _fail(f"cannot write the captured diff: {exc}", EXIT_EXTERNAL)

    findings = len(deletions) + len(placeholders) + len(weakened)
    violations = bool(outside or missing or scope_empty)
    rel_diff = os.path.relpath(diff_path, root)
    payload = {
        "ok": not (findings or violations),
        "verdict": VERDICT,
        "base": args.base,
        "changed_files": all_files,
        "untracked_files": new_files,
        "unreadable_files": unreadable,
        "scope_empty": scope_empty,
        "deletions": deletions,
        "placeholders": placeholders,
        "weakened_tests": weakened,
        "out_of_scope_files": outside,
        "missing_expected_files": missing,
        "findings_total": findings,
        "not_automated": list(NOT_AUTOMATED),
        "diff_file": rel_diff,
        "artifacts": [rel_diff],
    }
    if findings or violations:
        payload["error"] = (
            f"{findings} finding(s) and "
            f"{len(outside) + len(missing) + int(scope_empty)} violated expectation(s); "
            "read the diff and decide — this script never accepts a delegated change"
        )
    _emit(payload)
    return EXIT_OK if payload["ok"] else EXIT_FINDINGS


if __name__ == "__main__":
    sys.exit(main())
