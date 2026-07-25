#!/usr/bin/env python3
"""Check an Agent Teams file-ownership assignment: no two teammates own the
same path (``--mode preflight``), and the files that actually changed match the
assignment (``--mode reconcile``).

``team-execute/SKILL.md`` calls file-ownership separation "the most important
factor" in preventing lost edits, and enforced it with three sentences. Whether
N sets of paths overlap, and whether a changed file was assigned to somebody,
each have exactly one correct answer for a given input, so per the Automation
Boundary (``_shared/README.md``) they belong in a script. *Designing* the team —
which decomposition fits the plan, and which teammate runs on which model —
stays prose: this script validates a map it never authors.

Assignment file (``--assignment``), typed JSON, never markdown::

    {
      "owners": {
        "implementer-api": ["src/api/**", "src/api/routes.py"],
        "implementer-core": ["src/core/**"],
        "tester": ["tests/**"]
      }
    }

Pattern syntax: ``**`` crosses directory separators, ``*`` and ``?`` do not,
``dir/`` and a bare ``dir`` both mean everything under that directory. A
pattern with no glob character also matches as an exact path, so a file that
does not exist yet (the normal case in preflight) is still checked.

Overlap is reported with evidence, never guessed: a concrete path claimed by
two or more owners. The candidate paths are the repository's tracked and
untracked files plus every literal pattern in the assignment, so both
"two teammates own the same existing file" and "two teammates were told to
create the same new file" are caught.

``--mode reconcile`` derives the real changed-file list by calling
``_shared/gather_diff.py`` (the single source of truth for "what changed",
including uncommitted work) and reports files nobody owned, files owned by two
teammates, and owners that touched nothing.

Usage:
    python3 check_ownership.py --assignment owners.json --mode preflight
    python3 check_ownership.py --assignment owners.json --mode reconcile \
        --base main --allow-path PROGRESS.md

Exit codes:
    0  clean — no overlap, and in reconcile mode every change is owned
    1  bad arguments, or the assignment file is missing / unreadable / malformed
    2  contract violation — overlapping ownership, or a changed file that no
       owner claims and no --allow-path permits
    3  external failure — git or gather_diff.py could not report the scope
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
GATHER_DIFF = Path(__file__).parent.parent / "_shared" / "gather_diff.py"
SCOPE_PATCH = ".agents/logs/ownership-scope.patch"
GATHER_TIMEOUT = 240
GIT_TIMEOUT = 120

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_CONTRACT_VIOLATION = 2
EXIT_EXTERNAL_FAILURE = 3

MAGIC = ("*", "?", "[")


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as this tool's own JSON object
    on stdout with exit 1, instead of argparse's stderr text with exit 2."""

    def error(self, message: str) -> NoReturn:
        emit({"ok": False, "error": message}, EXIT_BAD_INPUT)


def emit(payload: dict, code: int) -> NoReturn:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(code)


# --- pattern matching --------------------------------------------------------


def normalize(path: str) -> str:
    # removeprefix, not lstrip: lstrip("./") would strip the leading dot of
    # `.agents/logs` and silently own a different tree.
    return path.strip().removeprefix("./").rstrip("/")


def pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a path pattern to an anchored regex.

    Written out rather than delegated to ``fnmatch`` because ``fnmatch``'s
    ``*`` crosses ``/``, which would make ``src/*`` silently own the entire
    subtree and turn a real overlap into a false clean result.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*" and pattern[i + 1 : i + 2] == "*":
            if pattern[i + 2 : i + 3] == "/":
                out.append("(?:.*/)?")
                i += 3
            else:
                out.append(".*")
                i += 2
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class Pattern:
    """One ownership pattern, plus the literal-prefix behaviour a bare
    directory name is expected to have."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.normalized = normalize(raw)
        self.is_literal = not any(char in self.normalized for char in MAGIC)
        self.regex = pattern_to_regex(self.normalized)

    def matches(self, path: str) -> bool:
        if self.regex.match(path):
            return True
        # `src/api` owns `src/api/routes.py`; the `/` boundary keeps it from
        # also owning `src/api_v2/routes.py`.
        return path.startswith(self.normalized + "/")


def load_owners(path: Path) -> dict[str, list[Pattern]]:
    """Read and validate the assignment file. Every rejection is specific
    enough to fix without reading this source."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        emit({"ok": False, "error": f"cannot read assignment: {exc}"}, EXIT_BAD_INPUT)
    except ValueError as exc:
        emit(
            {"ok": False, "error": f"assignment is not valid JSON: {exc}"},
            EXIT_BAD_INPUT,
        )

    if not isinstance(raw, dict) or not isinstance(raw.get("owners"), dict):
        emit(
            {
                "ok": False,
                "error": 'assignment must be {"owners": {"<name>": ["<pattern>", ...]}}',
            },
            EXIT_BAD_INPUT,
        )
    owners_raw: dict = raw["owners"]
    if not owners_raw:
        emit(
            {"ok": False, "error": "assignment lists no owners"},
            EXIT_BAD_INPUT,
        )

    owners: dict[str, list[Pattern]] = {}
    for name, patterns in owners_raw.items():
        if not isinstance(patterns, list) or not patterns:
            emit(
                {
                    "ok": False,
                    "error": f"owner {name!r} must map to a non-empty list of patterns",
                },
                EXIT_BAD_INPUT,
            )
        cleaned = []
        for pattern in patterns:
            if not isinstance(pattern, str) or not normalize(pattern):
                emit(
                    {
                        "ok": False,
                        "error": f"owner {name!r} has an empty or non-string pattern",
                    },
                    EXIT_BAD_INPUT,
                )
            cleaned.append(Pattern(pattern))
        owners[name] = cleaned
    return owners


# --- repository facts --------------------------------------------------------


def git_lines(root: Path, *args: str) -> tuple[list[str], str | None]:
    """Return git's stdout lines, or an error message. Never raises."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError as exc:
        return [], f"git is not available: {exc}"
    except subprocess.TimeoutExpired:
        return [], f"git timed out after {GIT_TIMEOUT}s"
    if proc.returncode != 0:
        return [], f"git {' '.join(args)} failed: {proc.stderr.strip()}"
    return [line for line in proc.stdout.splitlines() if line.strip()], None


def repository_files(root: Path) -> tuple[list[str], list[str]]:
    """Tracked + untracked paths, and any warnings about why the list is thin."""
    warnings: list[str] = []
    tracked, error = git_lines(root, "ls-files")
    if error:
        warnings.append(f"could not list tracked files: {error}")
    untracked, error = git_lines(root, "ls-files", "--others", "--exclude-standard")
    if error:
        warnings.append(f"could not list untracked files: {error}")
    return sorted(set(tracked) | set(untracked)), warnings


def changed_files(root: Path, base: str) -> tuple[list[str], list[str]]:
    """Delegate to gather_diff.py. Exit 2 there means an empty scope, which is
    a legitimate reconcile input (nothing changed) rather than a failure."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(GATHER_DIFF),
                "--project-root",
                str(root),
                "--base",
                base,
                "--out",
                SCOPE_PATCH,
            ],
            capture_output=True,
            text=True,
            timeout=GATHER_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        emit(
            {"ok": False, "error": f"could not run gather_diff.py: {exc}"},
            EXIT_EXTERNAL_FAILURE,
        )
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        emit(
            {
                "ok": False,
                "error": "gather_diff.py produced no JSON",
                "gather_diff_exit": proc.returncode,
                "stderr": proc.stderr.strip(),
            },
            EXIT_EXTERNAL_FAILURE,
        )
    if proc.returncode not in (0, EXIT_CONTRACT_VIOLATION):
        emit(
            {
                "ok": False,
                "error": payload.get("error", "gather_diff.py failed"),
                "gather_diff_exit": proc.returncode,
            },
            EXIT_EXTERNAL_FAILURE,
        )
    warnings = [f"gather_diff: {w}" for w in payload.get("warnings", [])]
    return payload.get("changed_files", []), warnings


# --- the checks --------------------------------------------------------------


def owners_of(owners: dict[str, list[Pattern]], path: str) -> list[str]:
    return sorted(
        name
        for name, patterns in owners.items()
        if any(pattern.matches(path) for pattern in patterns)
    )


def find_overlaps(
    owners: dict[str, list[Pattern]], candidates: list[str]
) -> list[dict]:
    overlaps = []
    for path in sorted(set(candidates)):
        claiming = owners_of(owners, path)
        if len(claiming) > 1:
            overlaps.append({"path": path, "owners": claiming})
    return overlaps


def preflight(root: Path, owners: dict[str, list[Pattern]]) -> dict:
    existing, warnings = repository_files(root)
    literals = [
        p.normalized for patterns in owners.values() for p in patterns if p.is_literal
    ]
    overlaps = find_overlaps(owners, existing + literals)

    unmatched = {}
    for name, patterns in owners.items():
        dead = [
            p.raw
            for p in patterns
            if not p.is_literal and not any(p.matches(path) for path in existing)
        ]
        if dead:
            unmatched[name] = dead
    if unmatched:
        listed = "; ".join(
            f"{name}: {', '.join(patterns)}" for name, patterns in unmatched.items()
        )
        warnings.append(
            "these glob patterns match no existing file — confirm they are for "
            f"files that will be created ({listed})"
        )

    return {
        "ok": not overlaps,
        "mode": "preflight",
        "owners": {name: [p.raw for p in ps] for name, ps in owners.items()},
        "candidates_checked": len(set(existing + literals)),
        "overlaps": overlaps,
        "patterns_matching_nothing": unmatched,
        "warnings": warnings,
        "artifacts": [],
    }


def reconcile(
    root: Path, owners: dict[str, list[Pattern]], base: str, allowed: list[Pattern]
) -> dict:
    changed, warnings = changed_files(root, base)
    overlaps = find_overlaps(owners, changed)

    per_owner: dict[str, list[str]] = {name: [] for name in owners}
    unowned: list[str] = []
    for path in changed:
        claiming = owners_of(owners, path)
        for name in claiming:
            per_owner[name].append(path)
        if not claiming and not any(pattern.matches(path) for pattern in allowed):
            unowned.append(path)

    idle = sorted(name for name, paths in per_owner.items() if not paths)
    if idle:
        warnings.append(
            f"these owners changed nothing: {idle} — confirm the workstream ran"
        )
    if not changed:
        warnings.append(
            "no file changed at all: the implement phase produced nothing to reconcile"
        )

    return {
        "ok": not overlaps and not unowned,
        "mode": "reconcile",
        "base": base,
        "owners": {name: [p.raw for p in ps] for name, ps in owners.items()},
        "changed_files": changed,
        "changed_by_owner": per_owner,
        "overlaps": overlaps,
        "unowned_changes": unowned,
        "idle_owners": idle,
        "allowed_paths": [p.raw for p in allowed],
        "warnings": warnings,
        "artifacts": [SCOPE_PATCH],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Validate an Agent Teams file-ownership assignment"
    )
    parser.add_argument(
        "--assignment",
        required=True,
        help="Path to the typed JSON assignment file",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["preflight", "reconcile"],
        help="preflight: overlap check before spawning. "
        "reconcile: compare the assignment against what actually changed",
    )
    parser.add_argument(
        "--base",
        default="main",
        help="Base ref for --mode reconcile (default: main)",
    )
    parser.add_argument(
        "--allow-path",
        action="append",
        default=[],
        help="Pattern that may change without an owner (repeatable), for "
        "shared files the lead maintains such as PROGRESS.md",
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

    assignment = Path(args.assignment)
    if not assignment.is_absolute():
        assignment = root / assignment
    if not assignment.is_file():
        emit(
            {"ok": False, "error": f"assignment file not found: {args.assignment}"},
            EXIT_BAD_INPUT,
        )
    owners = load_owners(assignment)

    if args.mode == "preflight":
        report = preflight(root, owners)
    else:
        report = reconcile(
            root, owners, args.base, [Pattern(p) for p in args.allow_path]
        )

    emit(report, EXIT_OK if report["ok"] else EXIT_CONTRACT_VIOLATION)


if __name__ == "__main__":
    main()
