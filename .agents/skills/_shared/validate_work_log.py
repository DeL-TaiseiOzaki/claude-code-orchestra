#!/usr/bin/env python3
"""Validate an Agent Teams teammate work log against the shared format contract.

Checks that the log file conforms to the canonical template defined in
``.agents/skills/_shared/work-log-format.md``: required ``## `` headings are
present and section bodies are non-empty.

Usage:
    python3 validate_work_log.py --file <path/to/log.md>

Exit codes:
    0  valid (warnings allowed — e.g. empty section bodies)
    1  bad args or file missing / unreadable
    3  required sections missing
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Required sections for each role variant (in expected order, though order is
# not enforced — only presence matters).
IMPLEMENTER_SECTIONS = [
    "Summary",
    "Tasks Completed",
    "Communication with Teammates",
    "Issues Encountered",
]

# Reviewer roles replace "Tasks Completed" with "Review Scope" + "Findings".
REVIEWER_SECTIONS = [
    "Summary",
    "Review Scope",
    "Findings",
    "Communication with Teammates",
    "Issues Encountered",
]

# Headings unique to the reviewer variant, used for auto-detection.
REVIEWER_MARKERS = {"Review Scope", "Findings"}

HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_SECTIONS_MISSING = 3


def _extract_sections(text: str) -> dict[str, str]:
    """Return a mapping of ``## `` heading text -> body text."""
    matches = list(HEADING_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections[heading] = body
    return sections


def _detect_variant(found_headings: set[str]) -> str:
    """Detect whether the log uses the reviewer variant or the implementer variant."""
    if found_headings & REVIEWER_MARKERS:
        return "reviewer"
    return "implementer"


def validate(file_path: Path) -> tuple[dict, int]:
    """Validate the work log at *file_path* and return (result_dict, exit_code)."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "ok": False,
            "file": str(file_path),
            "error": f"cannot read file: {exc}",
        }, EXIT_BAD_INPUT

    sections = _extract_sections(text)
    found_headings = set(sections.keys())

    variant = _detect_variant(found_headings)
    required = REVIEWER_SECTIONS if variant == "reviewer" else IMPLEMENTER_SECTIONS

    sections_found = [s for s in required if s in found_headings]
    sections_missing = [s for s in required if s not in found_headings]

    # Warn on empty bodies (present heading but blank/whitespace body).
    warnings: list[str] = []
    for heading, body in sections.items():
        if heading in {s for s in required} and not body:
            warnings.append(f"section '{heading}' is present but has an empty body")

    ok = len(sections_missing) == 0
    exit_code = EXIT_OK if ok else EXIT_SECTIONS_MISSING

    return {
        "ok": ok,
        "file": str(file_path),
        "role_variant": variant,
        "sections_found": sections_found,
        "sections_missing": sections_missing,
        "warnings": warnings,
    }, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an Agent Teams teammate work log against the shared format contract",
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the work log markdown file",
    )
    args = parser.parse_args()

    if not args.file.exists():
        result = {
            "ok": False,
            "file": str(args.file),
            "error": "file does not exist",
        }
        print(json.dumps(result, ensure_ascii=False))
        return EXIT_BAD_INPUT

    result, exit_code = validate(args.file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
