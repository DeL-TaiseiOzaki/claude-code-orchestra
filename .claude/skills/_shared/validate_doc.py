#!/usr/bin/env python3
"""Validate a skill-produced markdown document against a named section contract.

One engine for every skill deliverable that must contain specific headings —
work logs, library docs, plans, briefs, reports, checkpoint summaries, guides —
so document contracts live in a single registry rather than as a one-off
validator per document type. Use ``--contract work-log`` for the Agent Teams
teammate work log defined in ``work-log-format.md`` (implementer/reviewer
variant auto-detected); ``--contract feature-brief`` likewise auto-detects the
MODE=existing / MODE=greenfield variant.

Each contract's required headings are taken verbatim from the template (or, for
``plan-doc``, the SKILL.md output format) that declares them;
``tests/test_validate_doc.py`` validates those templates against their contract
so the two cannot drift apart. ``design-doc`` and ``state-doc`` have no separate
template: their reference document *is* the seed
``.claude/docs/DESIGN.md`` / ``.claude/STATE.md`` that ``scripts/install.sh``
copies into a project, and both are project-owned and mutable afterwards, so
each requires only the sections their writers (``update_design.py``,
``append_state_block.py``, ``refresh_guard.py``) depend on rather than every
heading the seed happens to contain. A contract may additionally require
machine-readable metadata lines (``lib-doc`` requires the
``> **Last Updated**:`` / ``> **Version Checked**:`` blockquote that
``update-lib-docs/lib_inventory.py`` parses); those are reported in
``metadata_missing``.

Usage:
    python3 validate_doc.py --contract lib-doc --file path/to/doc.md
    python3 validate_doc.py --contract work-log --dir path/to/team-dir/
    python3 validate_doc.py --contract work-log --dir path/to/team-dir/ \
        --expect-files 3

``--expect-files N`` states how many ``*.md`` files the caller requires in
``--dir``. Without it, an empty directory is reported as
``files_checked: 0`` with a warning and stays exit 0 — "no teammate wrote a
log" would otherwise be indistinguishable from "every log is valid".
``--expect-files`` is only meaningful with ``--dir``; combining it with
``--file`` is a bad-argument error (exit 1) rather than a silently ignored flag.

Exit codes:
    0  ok — the file(s) satisfy the contract
    1  bad args, unknown contract, or path does not exist / unreadable
    2  contract violation — a required section or metadata line is missing, or
       --expect-files was not satisfied
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

# --- feature-brief contract: MODE=existing / MODE=greenfield variants ---
# Both are declared by feature/references/brief-templates.md, which marks each
# section REQUIRED "when the corresponding mode is active".

FEATURE_BRIEF_EXISTING_SECTIONS = [
    "Current State",
    "Feature Goal",
    "Scope",
    "Complexity Classification",
    "Integration Points",
    "Risks",
    "Success Criteria",
]
FEATURE_BRIEF_GREENFIELD_SECTIONS = [
    "Current State",
    "Goal",
    "Scope",
    "Constraints",
    "Success Criteria",
]
# Headings unique to the MODE=existing brief, used for auto-detection.
FEATURE_BRIEF_EXISTING_MARKERS = {
    "Feature Goal",
    "Complexity Classification",
    "Integration Points",
}

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


def _resolve_feature_brief(found_headings: set[str]) -> tuple[list[str], str | None]:
    """Auto-detect MODE=existing (Feature Brief) vs MODE=greenfield (Project
    Brief). Detection mirrors the work-log resolver: a single heading unique to
    the existing-mode brief selects it, otherwise the greenfield set applies."""
    if any(
        find_heading(marker, found_headings)
        for marker in FEATURE_BRIEF_EXISTING_MARKERS
    ):
        return FEATURE_BRIEF_EXISTING_SECTIONS, "existing"
    return FEATURE_BRIEF_GREENFIELD_SECTIONS, "greenfield"


def _static(headings: list[str]) -> Resolver:
    """Build a resolver for a contract with a fixed heading list (no variants)."""

    def resolve(_found_headings: set[str]) -> tuple[list[str], str | None]:
        return headings, None

    return resolve


# Contract registry: name -> resolver(found_headings) -> (required, variant).
# Adding a contract with a fixed heading list is a one-line addition here.
# Every entry's heading list is taken verbatim from the template or SKILL.md
# named in the comment, and pinned to it by tests/test_validate_doc.py.
CONTRACTS: dict[str, Resolver] = {
    # _shared/work-log-format.md
    "work-log": _resolve_work_log,
    # research-lib/SKILL.md "## Documentation Template"
    "lib-doc": _static(
        ["Overview", "Core Features", "Constraints & Notes", "References"]
    ),
    # spike/references/report-template.md
    "spike-report": _static(
        [
            "Question",
            "Verdict",
            "Success Criteria Evaluation",
            "Risks",
            "Recommendation",
        ]
    ),
    # troubleshoot/references/bug-report-template.md
    "bug-report": _static(
        [
            "Error",
            "Reproduction",
            "Immediate Context",
            "Affected Area",
            "Initial Hypotheses",
        ]
    ),
    # plan/SKILL.md "### 4. Output Format"
    "plan-doc": _static(
        [
            "Purpose",
            "Scope",
            "Implementation Steps",
            "Risks & Considerations",
            "Open Questions",
        ]
    ),
    # feature/references/brief-templates.md (both modes)
    "feature-brief": _resolve_feature_brief,
    # spike/references/brief-template.md
    "spike-brief": _static(
        [
            "Question",
            "Parameters",
            "Success Criteria",
            "Sub-questions",
            "Critical Path",
            "Investigation Plan",
        ]
    ),
    # troubleshoot/references/diagnosis-template.md
    "diagnosis": _static(
        [
            "Error Reproduction",
            "Root Cause",
            "Impact Assessment",
            "Fix Plan",
            "Alternative Approaches Considered",
            "Next Steps",
        ]
    ),
    # checkpointing/references/formats.md, PROGRESS-SUMMARY block — the same
    # five subsections checkpoint.py declares as SUMMARY_SUBSECTIONS.
    "checkpoint-summary": _static(
        [
            "何をしたのか",
            "どういうやり取りをユーザーと行ったのか",
            "どうやったのか",
            "途中でどういう課題が起こったのか",
            "将来のアクション",
        ]
    ),
    # checkpointing/references/formats.md "## Rolling PROGRESS.md Format".
    # Entry headings are `## [{timestamp}](link)` — not a fixed name, so the
    # contract pins the two subsections the declared shape spells out. Their
    # presence is what proves PROGRESS.md holds at least one real entry.
    "progress": _static(["何をしたのか", "将来のアクション"]),
    # catchup/references/guide-template.md. The template marks every section
    # OPTIONAL, then names sections 2, 4, 6 and 8 as the ones omitted when
    # their sources are empty; the remaining four are always present.
    "guide": _static(
        [
            "1. What is this project?",
            "3. Recent Work",
            "5. Capabilities",
            "7. How to Resume Work",
        ]
    ),
    # .claude/docs/DESIGN.md — the document install.sh seeds into every project
    # and the structure update_design.py's typed targets locate by heading, so
    # a DESIGN.md missing one of these makes /init or /design-tracker exit 2.
    # Only the `##` sections are required: the `### Agent Roles` table is
    # meaningful for an agent-orchestration project and absent from an ordinary
    # one, and `### In Scope` / `### Out of Scope` are a rendering choice inside
    # `## スコープ` that no writer depends on. Each name is the Japanese heading
    # prefix, so a document that dropped the English gloss still passes.
    "design-doc": _static(
        [
            "背景・目的",
            "スコープ",
            "機能要件",
            "非機能要件",
            "アーキテクチャ",
            "技術選定",
            "制約",
            "Key Decisions",
            "TODO / Open Questions",
        ]
    ),
    # .claude/STATE.md — project-owned and mutable, so this contract requires
    # only what must always be there: `## Progress Tracker`, whose presence
    # append_state_block.py and refresh_guard.py both hard-enforce (exactly one
    # occurrence, or exit 2), and `## Main Agent`, the one fact the file exists
    # to carry (load_context.py and collect_repo_state.py read it by heading).
    # `## Repository Identity` is deliberately *not* required: it is /init-owned
    # and append_state_block.py inserts it when absent, so a state file that has
    # not been through /init is legitimately without it. Working blocks
    # (`## Current Feature`, …) come and go and are never required.
    "state-doc": _static(["Main Agent", "Progress Tracker"]),
}

# Required machine-readable metadata lines, per contract: contract -> field
# labels expected as a `> **Label**: value` blockquote line with a non-empty
# value. This is the format lib_inventory.py:38-41 parses, and the single
# canonical location for a library doc's version metadata.
REQUIRED_METADATA: dict[str, list[str]] = {
    "lib-doc": ["Last Updated", "Version Checked"],
}


def _metadata_re(label: str) -> re.Pattern[str]:
    """Blockquote metadata line matcher, e.g. `> **Version Checked**: 1.4.0`."""
    # Horizontal whitespace only: `\s*` would let the value be satisfied by
    # text on a following line, so an empty `> **Version Checked**:` would pass.
    return re.compile(
        rf"^>[ \t]*\*\*{re.escape(label)}\*\*:[ \t]*(\S.*?)[ \t]*$",
        re.MULTILINE,
    )


EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_CONTRACT_VIOLATION = 2


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so a mistyped ``--contract`` still fails loudly but
    without breaking the "exactly one JSON object on stdout" rule."""

    def error(self, message: str) -> NoReturn:
        print(
            json.dumps(
                {"ok": False, "error": message, "artifacts": []},
                ensure_ascii=False,
                indent=2,
            )
        )
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
        return {
            "ok": False,
            "file": str(path),
            "error": f"cannot read file: {exc}",
            "role_variant": None,
            "sections_found": [],
            "sections_missing": [],
            "metadata_missing": [],
            "warnings": [],
        }

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
    metadata_missing = [
        label
        for label in REQUIRED_METADATA.get(contract, [])
        if not _metadata_re(label).search(text)
    ]

    return {
        "ok": not sections_missing and not metadata_missing,
        "file": str(path),
        "role_variant": variant,
        "sections_found": sections_found,
        "sections_missing": sections_missing,
        "metadata_missing": metadata_missing,
        "warnings": warnings,
    }


def validate_dir(dir_path: Path, contract: str, expect_files: int | None) -> dict:
    """Validate every top-level ``*.md`` file in an existing directory.

    *expect_files* is the number of documents the caller requires. A count
    mismatch is a contract violation in its own right: without it, an empty
    directory would pass, so "nobody produced a document" and "every document
    is valid" would be the same result.
    """
    files = sorted(p for p in dir_path.glob("*.md") if p.is_file())
    results = [validate_file(p, contract) for p in files]
    files_failed = sum(1 for r in results if not r["ok"])
    warnings: list[str] = []
    error: str | None = None

    if expect_files is not None and len(results) != expect_files:
        error = f"expected {expect_files} files, found {len(results)}"
    elif expect_files is None and not results:
        # Named, visible state instead of a silent "all clear" on nothing.
        warnings.append(
            "no *.md files found: pass --expect-files N to make this a failure"
        )

    payload = {
        "ok": files_failed == 0 and error is None,
        "contract": contract,
        "results": results,
        "files_checked": len(results),
        "files_failed": files_failed,
        "expect_files": expect_files,
        "warnings": warnings,
    }
    if error is not None:
        payload["error"] = error
    return payload


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


def check_dir(
    raw_path: Path,
    contract: str,
    project_root: Path,
    expect_files: int | None = None,
) -> tuple[dict, int]:
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
    result = validate_dir(path, contract, expect_files)
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
        "--expect-files",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Number of *.md files --dir must contain; a mismatch is exit 2. "
            "Only valid with --dir"
        ),
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root, used to resolve relative --file/--dir paths",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.expect_files is not None and args.expect_files < 0:
        parser.error("--expect-files must be >= 0")

    if args.file is not None:
        if args.expect_files is not None:
            # Ignoring the flag would let a caller believe an expectation was
            # checked when it was not.
            parser.error("--expect-files is only valid with --dir")
        result, exit_code = check_file(args.file, args.contract, args.project_root)
    else:
        result, exit_code = check_dir(
            args.dir, args.contract, args.project_root, args.expect_files
        )

    # This tool is read-only: it never creates or modifies a file, so the
    # shared contract's touch list is always empty. It is still reported, so a
    # caller can parse `artifacts` uniformly across every bundled script
    # instead of special-casing the validators.
    result["artifacts"] = []

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
