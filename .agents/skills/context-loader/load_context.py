#!/usr/bin/env python3
"""Deterministically resolve the context-loader skill's read plan.

Enumerates the rule files actually present in ``.agents/rules/`` (with a
stable preferred-order prefix so the order never drifts from what changes on
disk), reports ``.agents/STATE.md`` / ``PROGRESS.md`` / ``.agents/docs/DESIGN.md``
status, and lists library docs -- optionally filtered to the current task -- so
"always start with context-loader" has one deterministic read order instead of a
hand-maintained list in SKILL.md.

``read_order`` is rules, then ``.agents/STATE.md``, then ``PROGRESS.md``, then
``.agents/docs/DESIGN.md``, then matched library docs. ``PROGRESS.md`` sits
directly after shared state because it carries the session-to-session
continuity that ``checkpointing/references/formats.md`` calls "the first thing
`/feature` reads on the next session"; it used to be reported and never read.

Three states, never two: a file that exists but cannot be read or decoded is
reported in ``unreadable`` rather than in ``missing``, so a permission or
encoding problem does not steer the agent to ``/init``. ``design.placeholder``
is likewise tri-state -- ``true`` (absent, or the untouched template), ``false``
(real prose), ``null`` (the Background & Purpose heading is gone, so emptiness
cannot be judged) -- because the previous boolean reported a renamed heading as
"initialised".

Usage:
    python3 load_context.py
    python3 load_context.py --task-libraries duckdb,fastapi

Exit codes:
    0  ok (rules dir and STATE.md are present and readable; design/progress/
       libraries may legitimately be absent -- that is reported, not an error)
    1  bad args
    2  a canonical file is missing entirely or is unreadable
       (.agents/STATE.md or the .agents/rules/ directory)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Stable prefix order; any rule file not listed here is appended alphabetically.
PREFERRED_RULE_ORDER = [
    "coding-principles",
    "dev-environment",
    "language",
    "security",
    "testing",
    "tiers",
    "cli-execution",
    "codex-delegation",
]

# English parenthetical in the "## 背景・目的 (Background & Purpose)" heading --
# stable regardless of Japanese rendering/encoding, and the first section
# `/init` fills in, so its emptiness is the most direct placeholder signal.
DESIGN_PLACEHOLDER_HEADING_MARKER = "Background & Purpose"

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# A rolling PROGRESS.md entry: `## [2026-07-25-100000](.agents/checkpoints/...)`,
# the shape checkpointing/references/formats.md declares.
PROGRESS_ENTRY_RE = re.compile(
    r"^## \[\d{4}-\d{2}-\d{2}-\d{6}\]\(\.agents/checkpoints/", re.MULTILINE
)

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_CONTRACT_VIOLATION = 2


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so an argparse-level failure never masquerades as this
    tool's exit code 2, which means "a canonical file is missing"."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_ARGS)


def _rel_posix(path: Path, root: Path) -> str:
    """Render *path* as a POSIX-style string relative to *root*."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_read(path: Path) -> tuple[str | None, str | None]:
    """Read a text file, returning ``(text, error)``.

    ``(None, None)`` means the file does not exist; ``(None, "...")`` means it
    exists but could not be read or decoded. Collapsing those two into one
    ``None`` made a permission-denied STATE.md indistinguishable from an
    un-bootstrapped repository.
    """
    if not path.exists():
        return None, None
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _normalize(name: str) -> str:
    """Normalize a library name for loose matching against filenames."""
    return name.strip().lower().replace("_", "-")


def order_rule_files(rules_dir: Path) -> list[Path]:
    """Order rule files: the stable preferred prefix, then unknowns alphabetically."""
    by_stem = {path.stem: path for path in sorted(rules_dir.glob("*.md"))}
    ordered: list[Path] = []
    for stem in PREFERRED_RULE_ORDER:
        found = by_stem.pop(stem, None)
        if found is not None:
            ordered.append(found)
    ordered.extend(sorted(by_stem.values()))
    return ordered


def _extract_heading_value(text: str, heading: str) -> str | None:
    """Return the first non-blank line under an exact ``## {heading}`` line."""
    lines = text.splitlines()
    target = f"## {heading}"
    for idx, line in enumerate(lines):
        if line.strip() != target:
            continue
        for candidate in lines[idx + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            return None if stripped.startswith("#") else stripped
        return None
    return None


def _extract_section_body(text: str, heading_marker: str) -> str | None:
    """Return the body between a ``## `` heading containing *heading_marker*
    and the next ``## `` heading (or EOF); None if no such heading exists."""
    lines = text.splitlines()
    start: int | None = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and heading_marker in stripped:
            start = idx + 1
            break
    if start is None:
        return None

    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].strip().startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end])


def _is_design_placeholder(text: str) -> bool | None:
    """Whether DESIGN.md is still the fresh /init template.

    ``True`` when the Background & Purpose section holds only its instructional
    HTML comment, ``False`` when real prose was added, and ``None`` when the
    marker heading is absent altogether — emptiness cannot be judged then, and
    reporting ``False`` (the old behaviour) claimed the document was initialised.
    """
    body = _extract_section_body(text, DESIGN_PLACEHOLDER_HEADING_MARKER)
    if body is None:
        return None
    return HTML_COMMENT_RE.sub("", body).strip() == ""


def build_state_info(root: Path) -> dict:
    """Report STATE.md presence and its ``## Main Agent`` value."""
    path = root / ".agents" / "STATE.md"
    text, error = _safe_read(path)
    return {
        "present": text is not None,
        "path": _rel_posix(path, root),
        "error": error,
        "main_agent": _extract_heading_value(text, "Main Agent") if text else None,
    }


def build_design_info(root: Path) -> dict:
    """Report DESIGN.md presence and whether it is still the /init placeholder."""
    path = root / ".agents" / "docs" / "DESIGN.md"
    text, error = _safe_read(path)
    return {
        "present": text is not None,
        "path": _rel_posix(path, root),
        "error": error,
        # Absent means definitively uninitialised; unreadable means unknowable.
        "placeholder": _is_design_placeholder(text)
        if text is not None
        else (None if error else True),
    }


def build_progress_info(root: Path) -> dict:
    """Report PROGRESS.md presence and how many checkpoint entries it holds."""
    path = root / "PROGRESS.md"
    text, error = _safe_read(path)
    entries = len(PROGRESS_ENTRY_RE.findall(text)) if text is not None else 0
    return {
        "present": text is not None,
        "path": _rel_posix(path, root),
        "error": error,
        "entries": entries,
    }


def build_libraries_info(root: Path, task_libraries: list[str]) -> dict:
    """List library docs, optionally filtered to names relevant to the task."""
    libraries_dir = root / ".agents" / "docs" / "libraries"
    present = libraries_dir.is_dir()
    files = sorted(p.name for p in libraries_dir.glob("*.md")) if present else []

    matched: list[str] = []
    if task_libraries:
        wanted = [_normalize(name) for name in task_libraries]
        for filename in files:
            stem = _normalize(filename[: -len(".md")])
            if any(w in stem or stem in w for w in wanted):
                matched.append(filename)

    return {
        "dir": _rel_posix(libraries_dir, root),
        "present": present,
        "files": files,
        "matched": matched,
    }


def build_report(root: Path, task_libraries: list[str]) -> tuple[dict, int]:
    """Assemble the full load_context.py JSON report; return (report, exit_code)."""
    rules_dir = root / ".agents" / "rules"
    rules_present = rules_dir.is_dir()
    rule_paths = order_rule_files(rules_dir) if rules_present else []
    rule_rel_paths = [_rel_posix(p, root) for p in rule_paths]

    state = build_state_info(root)
    design = build_design_info(root)
    progress = build_progress_info(root)
    libraries = build_libraries_info(root, task_libraries)

    read_order = list(rule_rel_paths)
    if state["present"]:
        read_order.append(state["path"])
    if progress["present"]:
        read_order.append(progress["path"])
    if design["present"]:
        read_order.append(design["path"])
    libraries_dir = root / ".agents" / "docs" / "libraries"
    read_order.extend(
        _rel_posix(libraries_dir / name, root) for name in libraries["matched"]
    )

    missing: list[str] = []
    unreadable: list[str] = []
    if not rules_present:
        missing.append(_rel_posix(rules_dir, root))
    for info in (state, progress, design):
        if info["present"]:
            continue
        (unreadable if info["error"] else missing).append(info["path"])

    warnings: list[str] = []
    for info in (state, progress, design):
        if info["error"]:
            warnings.append(f"{info['path']} exists but is unreadable: {info['error']}")
    if design["placeholder"] is True:
        warnings.append(
            "DESIGN.md is still the uninitialised /init template; run /init to populate it"
        )
    elif design["present"] and design["placeholder"] is None:
        warnings.append(
            "DESIGN.md has no heading containing "
            f"'{DESIGN_PLACEHOLDER_HEADING_MARKER}', so whether it is still a "
            "placeholder cannot be determined"
        )
    if progress["present"] and progress["entries"] == 0:
        warnings.append(
            "PROGRESS.md holds no checkpoint entries; run /checkpointing to populate it"
        )

    ok = rules_present and state["present"]
    report = {
        "ok": ok,
        "read_order": read_order,
        "rules": {
            "dir": _rel_posix(rules_dir, root),
            "present": rules_present,
            "files": rule_rel_paths,
        },
        "state": state,
        "design": design,
        "progress": progress,
        "libraries": libraries,
        "missing": missing,
        "unreadable": unreadable,
        "warnings": warnings,
    }
    return report, (EXIT_OK if ok else EXIT_CONTRACT_VIOLATION)


def main() -> int:
    parser = JsonArgumentParser(
        description="Resolve the context-loader skill's read plan (JSON to stdout)",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--task-libraries",
        default=None,
        help="Comma-separated library names to match against docs/libraries/",
    )
    args = parser.parse_args()

    task_libraries = (
        [name.strip() for name in args.task_libraries.split(",") if name.strip()]
        if args.task_libraries
        else []
    )

    report, exit_code = build_report(args.project_root, task_libraries)
    _emit(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
