#!/usr/bin/env python3
"""Validate a skill-produced markdown document against a named section contract.

One engine for every skill deliverable that must contain specific headings —
work logs, library docs, spike reports, bug reports — so document contracts
live in a single registry rather than as a one-off validator per document
type. Use ``--contract work-log`` for the Agent Teams teammate work log
defined in ``work-log-format.md`` (implementer/reviewer variant auto-detected).

Each contract's required headings mirror the corresponding template under a
skill's ``references/`` directory; ``tests/test_validate_doc.py`` validates
those templates against their contract so the two cannot drift apart.

Usage:
    python3 validate_doc.py --contract lib-doc --file path/to/doc.md
    python3 validate_doc.py --contract work-log --dir path/to/team-dir/

Exit codes:
    0  ok — the file(s) satisfy the contract
    1  bad args, unknown contract, or path does not exist / unreadable
    2  contract violation — one or more required sections missing
"""

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Any heading below the document title. Depth is deliberately not part of a
# contract: templates nest their required sections at whichever level reads
# best (the bug report puts them under a `## Bug Report: {issue}` title), and a
# section that moved one level deeper is still present.
HEADING_RE = re.compile(r"^#{2,6}\s+(.+)$", re.MULTILINE)

# --- work-log contract: implementer/reviewer variants (auto-detected) ---

IMPLEMENTER_SECTIONS = [
    "Summary",
    "Tasks Completed",
    "Communication with Teammates",
    "Issues Encountered",
]
REVIEWER_SECTIONS = [
    "Summary",
    "Review Scope",
    "Findings",
    "Communication with Teammates",
    "Issues Encountered",
]
# Headings unique to the reviewer variant, used for auto-detection.
REVIEWER_MARKERS = {"Review Scope", "Findings"}

Resolver = Callable[[set[str]], tuple[list[str], str | None]]


def matches(required: str, heading: str) -> bool:
    """Whether *heading* satisfies the *required* section name.

    Templates routinely carry a value or qualifier in the heading itself —
    ``## Verdict: {GO / NO-GO}``, ``### Initial Hypotheses (informed by Codex
    analysis)``. Requiring an exact string would reject documents that follow
    the template verbatim, so a heading also matches when the required name is
    a whole-token prefix of it.
    """
    return heading == required or heading.startswith((f"{required}:", f"{required} "))


def find_heading(required: str, found_headings: set[str]) -> str | None:
    """Return the found heading satisfying *required*, or None."""
    return next(
        (heading for heading in sorted(found_headings) if matches(required, heading)),
        None,
    )


def _resolve_work_log(found_headings: set[str]) -> tuple[list[str], str | None]:
    """Auto-detect implementer vs reviewer work-log variant."""
    if any(find_heading(marker, found_headings) for marker in REVIEWER_MARKERS):
        return REVIEWER_SECTIONS, "reviewer"
    return IMPLEMENTER_SECTIONS, "implementer"


def _static(headings: list[str]) -> Resolver:
    """Build a resolver for a contract with a fixed heading list (no variants)."""

    def resolve(_found_headings: set[str]) -> tuple[list[str], str | None]:
        return headings, None

    return resolve


# Contract registry: name -> resolver(found_headings) -> (required, variant).
# Adding a contract with a fixed heading list is a one-line addition here.
CONTRACTS: dict[str, Resolver] = {
    "work-log": _resolve_work_log,
    "lib-doc": _static(
        ["Overview", "Core Features", "Constraints & Notes", "References"]
    ),
    "spike-report": _static(
        [
            "Question",
            "Verdict",
            "Success Criteria Evaluation",
            "Risks",
            "Recommendation",
        ]
    ),
    "bug-report": _static(
        [
            "Error",
            "Reproduction",
            "Immediate Context",
            "Affected Area",
            "Initial Hypotheses",
        ]
    ),
}

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_CONTRACT_VIOLATION = 2


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so a mistyped ``--contract`` still fails loudly but
    without breaking the "exactly one JSON object on stdout" rule."""

    def error(self, message: str) -> NoReturn:
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2))
        sys.exit(EXIT_BAD_INPUT)


def _extract_sections(text: str) -> dict[str, str]:
    """Return a mapping of ``## `` heading text -> body text."""
    matches = list(HEADING_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[heading] = text[body_start:body_end].strip()
    return sections


def validate_file(path: Path, contract: str) -> dict:
    """Validate a single markdown file already known to exist. Never raises."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "file": str(path), "error": f"cannot read file: {exc}"}

    sections = _extract_sections(text)
    found_headings = set(sections.keys())
    required, variant = CONTRACTS[contract](found_headings)

    resolved = {name: find_heading(name, found_headings) for name in required}
    sections_found = [name for name in required if resolved[name] is not None]
    sections_missing = [name for name in required if resolved[name] is None]
    warnings = [
        f"section '{name}' is present but has an empty body"
        for name in sections_found
        if not sections[resolved[name]]
    ]

    return {
        "ok": not sections_missing,
        "file": str(path),
        "role_variant": variant,
        "sections_found": sections_found,
        "sections_missing": sections_missing,
        "warnings": warnings,
    }


def validate_dir(dir_path: Path, contract: str) -> dict:
    """Validate every top-level ``*.md`` file in an existing directory."""
    files = sorted(p for p in dir_path.glob("*.md") if p.is_file())
    results = [validate_file(p, contract) for p in files]
    files_failed = sum(1 for r in results if not r["ok"])
    return {
        "ok": files_failed == 0,
        "contract": contract,
        "results": results,
        "files_checked": len(results),
        "files_failed": files_failed,
    }


def _resolve_path(raw: Path, project_root: Path) -> Path:
    """Resolve *raw* against *project_root* unless it is already absolute."""
    return raw if raw.is_absolute() else project_root / raw


def check_file(raw_path: Path, contract: str, project_root: Path) -> tuple[dict, int]:
    """Resolve, existence-check, and validate a single file. Never raises."""
    path = _resolve_path(raw_path, project_root)
    if not path.exists():
        return {
            "ok": False,
            "file": str(path),
            "error": "file does not exist",
        }, EXIT_BAD_INPUT
    result = validate_file(path, contract)
    exit_code = EXIT_OK if result["ok"] else EXIT_CONTRACT_VIOLATION
    return result, exit_code


def check_dir(raw_path: Path, contract: str, project_root: Path) -> tuple[dict, int]:
    """Resolve, existence-check, and validate every top-level *.md in a dir."""
    path = _resolve_path(raw_path, project_root)
    if not path.exists():
        return {
            "ok": False,
            "dir": str(path),
            "error": "directory does not exist",
        }, EXIT_BAD_INPUT
    if not path.is_dir():
        return {
            "ok": False,
            "dir": str(path),
            "error": "not a directory",
        }, EXIT_BAD_INPUT
    result = validate_dir(path, contract)
    exit_code = EXIT_OK if result["ok"] else EXIT_CONTRACT_VIOLATION
    return result, exit_code


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Validate a markdown document against a named section contract",
    )
    parser.add_argument(
        "--contract",
        choices=sorted(CONTRACTS),
        required=True,
        help="Name of the section contract to validate against",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--file", type=Path, help="Validate a single markdown file")
    target.add_argument(
        "--dir",
        type=Path,
        help="Validate every top-level *.md file in DIR (non-recursive)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root, used to resolve relative --file/--dir paths",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    if args.file is not None:
        result, exit_code = check_file(args.file, args.contract, args.project_root)
    else:
        result, exit_code = check_dir(args.dir, args.contract, args.project_root)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
