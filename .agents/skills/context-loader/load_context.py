#!/usr/bin/env python3
"""Deterministically resolve the context-loader skill's read plan.

Enumerates the rule files actually present in ``.agents/rules/`` (with a
stable preferred-order prefix so the order never drifts from what changes on
disk), reports ``.agents/STATE.md`` / ``.agents/docs/DESIGN.md`` /
``PROGRESS.md`` status, and lists library docs -- optionally filtered to the
current task -- so "always start with context-loader" has one deterministic
read order instead of a hand-maintained list in SKILL.md.

Usage:
    python3 load_context.py
    python3 load_context.py --task-libraries duckdb,fastapi

Exit codes:
    0  ok (rules dir and STATE.md are present; design/progress/libraries may
       legitimately be absent -- that is reported, not an error)
    1  bad args
    2  a canonical file is missing entirely (.agents/STATE.md or the
       .agents/rules/ directory)
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


def _safe_read(path: Path) -> str | None:
    """Read a text file; return None when missing/unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


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


def _is_design_placeholder(text: str) -> bool:
    """Detect the fresh /init template: the Background & Purpose section holds
    only its instructional HTML comment, with no real prose added yet."""
    body = _extract_section_body(text, DESIGN_PLACEHOLDER_HEADING_MARKER)
    if body is None:
        return False
    return HTML_COMMENT_RE.sub("", body).strip() == ""


def build_state_info(root: Path) -> dict:
    """Report STATE.md presence and its ``## Main Agent`` value."""
    path = root / ".agents" / "STATE.md"
    text = _safe_read(path)
    present = text is not None
    return {
        "present": present,
        "path": _rel_posix(path, root),
        "main_agent": _extract_heading_value(text, "Main Agent") if present else None,
    }


def build_design_info(root: Path) -> dict:
    """Report DESIGN.md presence and whether it is still the /init placeholder."""
    path = root / ".agents" / "docs" / "DESIGN.md"
    text = _safe_read(path)
    present = text is not None
    return {
        "present": present,
        "path": _rel_posix(path, root),
        "placeholder": True if text is None else _is_design_placeholder(text),
    }


def build_progress_info(root: Path) -> dict:
    """Report PROGRESS.md presence."""
    path = root / "PROGRESS.md"
    return {"present": path.is_file(), "path": _rel_posix(path, root)}


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
    if design["present"]:
        read_order.append(design["path"])
    libraries_dir = root / ".agents" / "docs" / "libraries"
    read_order.extend(
        _rel_posix(libraries_dir / name, root) for name in libraries["matched"]
    )

    missing: list[str] = []
    if not rules_present:
        missing.append(_rel_posix(rules_dir, root))
    if not state["present"]:
        missing.append(state["path"])
    if not design["present"]:
        missing.append(design["path"])
    if not progress["present"]:
        missing.append(progress["path"])

    warnings: list[str] = []
    if design["placeholder"]:
        warnings.append(
            "DESIGN.md is still the uninitialised /init template; run /init to populate it"
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
