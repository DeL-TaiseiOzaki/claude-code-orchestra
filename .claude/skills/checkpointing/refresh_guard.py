#!/usr/bin/env python3
"""Inspect, compose, apply, and verify compacted ``.claude/STATE.md`` state.

The five modes are genuinely different operations, not aliases:

``check``
    Structure counts plus the work-block inventory — the mechanical check
    ``.claude/rules/agent-state.md`` names. Read-only, nothing else collected.
``plan``
    ``check`` plus the compaction preview (which blocks would be pruned, which
    sections would be preserved) and the *suggested* research-note archive
    moves. Read-only.
``compose``
    ``plan`` plus the candidate state written to
    ``.claude/logs/composed-state.md``. Writes only that draft.
``apply``
    Replace ``.claude/STATE.md`` with the candidate under the Writer Safety
    Contract: dry-run by default, ``--apply`` to write, atomic ``os.replace``,
    content-hash guard, and validation of the composed bytes before replacing.
``verify``
    Compare the on-disk state against the candidate and report whether the
    compaction has actually landed (``compaction_applied``).

Compaction is lossless by construction: only redundant ``## Current *`` work
blocks are removed. Every other section — including manual notes, which
``.claude/rules/agent-state.md`` explicitly sanctions — is preserved verbatim in
document order, and any section that would still be lost is reported in
``sections_dropped`` and aborts the run with exit 2.

The guard never moves research notes; ``move_plan`` is a suggestion that
requires explicit user approval.

Usage:
    python3 refresh_guard.py --mode check
    python3 refresh_guard.py --mode plan --project-root /path/to/repo
    python3 refresh_guard.py --mode compose
    python3 refresh_guard.py --mode apply           # dry-run preview
    python3 refresh_guard.py --mode apply --apply
    python3 refresh_guard.py --mode verify

Exit codes:
    0  ok / preview
    1  bad arguments
    2  .claude/STATE.md structure invalid, a non-work-block section would be
       dropped, or --mode verify found the compaction not applied
    3  .claude/STATE.md cannot be read, write failure, concurrent modification
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

STATE_HEADING = "# Agent State"
PROGRESS_TRACKER_HEADING = "## Progress Tracker"
CURRENT_BLOCK_RE = re.compile(r"^## Current (Project|Feature|Bug Fix)\b")
TOP_HEADING_RE = re.compile(r"^## ")
LEGACY_HEADINGS = (
    "## Work Evolution",
    "## Archive Index",
    "## Activity Log",
    "## Session Log",
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

MOVE_PLAN_CAVEAT = (
    "move_plan is a suggestion from a stem-mention heuristic, not a decision: "
    "archiving a research note requires explicit user approval"
)

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_STRUCTURE_INVALID = 2
EXIT_WRITE_FAILURE = 3

MODES = ["check", "plan", "compose", "apply", "verify"]


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable and never
    masquerades as this tool's own exit code 2 (STATE.md structure
    invalid)."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message, "artifacts": []})
        sys.exit(EXIT_BAD_INPUT)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_now(raw: str | None) -> datetime:
    """Read the clock exactly once, or parse the injected ``--now`` value."""
    if raw is None:
        return datetime.now(tz=UTC)
    return datetime.fromisoformat(raw)


def _rel(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# --- document model ----------------------------------------------------------


@dataclass
class Section:
    """A top-level ``## `` section, or the preamble when ``heading`` is empty."""

    heading: str
    start: int
    end: int  # exclusive


def split_sections(lines: list[str]) -> list[Section]:
    """Split *lines* into the preamble plus one Section per top-level heading.

    Every line of the document belongs to exactly one Section, so dropping a
    Section removes exactly its own text and nothing else — that is what makes
    compaction lossless for the sections that are kept.
    """
    starts = [i for i, line in enumerate(lines) if TOP_HEADING_RE.match(line)]
    sections: list[Section] = []
    if not starts:
        return [Section("", 0, len(lines))] if lines else []
    if starts[0] > 0:
        sections.append(Section("", 0, starts[0]))
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        sections.append(Section(lines[start].strip(), start, end))
    return sections


def top_headings(lines: list[str]) -> list[str]:
    """Every top-level ``## `` heading, in document order."""
    return [line.strip() for line in lines if TOP_HEADING_RE.match(line)]


def collect_work_blocks(lines: list[str]) -> list[dict]:
    """Inventory the ``## Current *`` blocks, marking the newest of each kind."""
    blocks: list[dict] = []
    for section in split_sections(lines):
        match = CURRENT_BLOCK_RE.match(section.heading)
        if not match:
            continue
        text = "\n".join(lines[section.start : section.end])
        date_match = DATE_RE.search(text)
        blocks.append(
            {
                "heading": section.heading,
                "line": section.start + 1,
                "date": date_match.group(0) if date_match else None,
                "category": match.group(1),
                "keep": True,
            }
        )
    last_by_category = {block["category"]: i for i, block in enumerate(blocks)}
    for i, block in enumerate(blocks):
        block["keep"] = last_by_category[block["category"]] == i
        del block["category"]
    return blocks


@dataclass
class Compaction:
    """The outcome of composing a compacted state, before anything is written."""

    text: str
    blocks_pruned: list[str]
    sections_preserved: list[str]
    sections_dropped: list[str]


def compose_state(lines: list[str]) -> Compaction:
    """Compose the compacted state by deleting only redundant work blocks.

    Earlier revisions rebuilt the document from ``lines[:first_work_index]``
    plus the kept blocks, which silently deleted every section that happened to
    follow a work block — including the ``## Progress Tracker`` link and any
    manual notes. This walks the section list instead and keeps everything it
    does not explicitly prune.
    """
    sections = split_sections(lines)
    work_positions = [
        i
        for i, section in enumerate(sections)
        if CURRENT_BLOCK_RE.match(section.heading)
    ]
    last_by_category: dict[str, int] = {}
    for i in work_positions:
        match = CURRENT_BLOCK_RE.match(sections[i].heading)
        assert match is not None
        last_by_category[match.group(1)] = i

    dropped_lines: set[int] = set()
    blocks_pruned: list[str] = []
    preserved: list[str] = []
    for i, section in enumerate(sections):
        match = CURRENT_BLOCK_RE.match(section.heading)
        if match is not None and last_by_category[match.group(1)] != i:
            blocks_pruned.append(section.heading)
            dropped_lines.update(range(section.start, section.end))
            continue
        if section.heading:
            preserved.append(section.heading)

    kept = [line for i, line in enumerate(lines) if i not in dropped_lines]
    text = "\n".join(kept).rstrip("\n") + "\n"

    # Honest recomputation rather than a restatement of the loop above: any
    # heading that was neither preserved nor deliberately pruned is a defect.
    surviving = top_headings(text.splitlines())
    expected = [h for h in top_headings(lines) if h not in blocks_pruned]
    sections_dropped = [h for h in expected if h not in surviving]
    return Compaction(text, blocks_pruned, preserved, sections_dropped)


def validate_composition(new_text: str, original_lines: list[str]) -> str | None:
    """Return an error message if the composed state is malformed, else None."""
    lines = new_text.splitlines()
    if sum(1 for line in lines if line.strip() == STATE_HEADING) != 1:
        return f"expected exactly 1 '{STATE_HEADING}' heading"
    if sum(1 for line in lines if line.strip() == PROGRESS_TRACKER_HEADING) != 1:
        return f"expected exactly 1 '{PROGRESS_TRACKER_HEADING}' heading"
    compaction = compose_state(original_lines)
    surviving = top_headings(lines)
    expected = [
        h for h in top_headings(original_lines) if h not in compaction.blocks_pruned
    ]
    if surviving != expected:
        return (
            "composed document lost or reordered a section: "
            f"expected {expected}, found {surviving}"
        )
    return None


# --- collection --------------------------------------------------------------


def collect_research_notes(state_text: str, research_dir: Path) -> list[dict]:
    """List research notes, hinting which ones STATE.md still mentions."""
    if not research_dir.is_dir():
        return []
    lowered = state_text.lower()
    notes = []
    for path in sorted(research_dir.glob("*.md")):
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        notes.append(
            {
                "file": path.name,
                "mtime": mtime.strftime("%Y-%m-%d"),
                "active": path.stem.lower() in lowered,
            }
        )
    return notes


def build_report(lines: list[str], root: Path, mode: str) -> dict:
    """Assemble the mode-appropriate report. ``root`` reaches every path used."""
    state_text = "\n".join(lines)
    structure = {
        "state_heading": sum(line.strip() == STATE_HEADING for line in lines),
        "progress_tracker": sum(
            line.strip() == PROGRESS_TRACKER_HEADING for line in lines
        ),
    }
    structure["ok"] = all(value == 1 for value in structure.values())
    report: dict = {
        "ok": structure["ok"],
        "mode": mode,
        "structure": structure,
        "state_md": {"total_lines": len(lines)},
        "work_blocks": collect_work_blocks(lines) if structure["ok"] else [],
        "legacy_sections": [
            heading for heading in LEGACY_HEADINGS if heading in state_text
        ],
        "warnings": [],
        "artifacts": [],
    }
    if mode == "check" or not structure["ok"]:
        return report

    research_dir = root / ".claude" / "docs" / "research"
    archive_dir = research_dir / "archive"
    notes = collect_research_notes(state_text, research_dir)
    compaction = compose_state(lines)
    report["research_notes"] = notes
    report["move_plan"] = [
        {
            "src": _rel(research_dir / note["file"], root),
            "dst": _rel(archive_dir / note["file"], root),
            "mode": "append" if (archive_dir / note["file"]).exists() else "create",
            "suggested": True,
        }
        for note in notes
        if not note["active"]
    ]
    if report["move_plan"]:
        report["warnings"].append(MOVE_PLAN_CAVEAT)
    report["blocks_pruned"] = compaction.blocks_pruned
    report["sections_preserved"] = compaction.sections_preserved
    report["sections_dropped"] = compaction.sections_dropped
    if compaction.sections_dropped:
        report["ok"] = False
        report["error"] = (
            "compaction would drop non-work-block section(s): "
            f"{', '.join(compaction.sections_dropped)}"
        )
    return report


# --- writing -----------------------------------------------------------------


def _write_file(path: Path, text: str) -> str | None:
    """Write *text* to *path*, returning an error message on failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"cannot write {path}: {exc}"
    return None


def apply_atomically(
    state_path: Path, new_text: str, original_text: str, expect_hash: str | None
) -> tuple[str | None, int]:
    """Replace *state_path* with *new_text*. Return (error, exit_code)."""
    original_lines = original_text.splitlines()
    try:
        current_text = state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"cannot re-read {state_path}: {exc}", EXIT_WRITE_FAILURE

    current_hash = _sha256(current_text)
    if expect_hash is not None and current_hash != expect_hash:
        return (
            f"--expect-hash {expect_hash} does not match on-disk {current_hash}",
            EXIT_WRITE_FAILURE,
        )
    if current_hash != _sha256(original_text):
        return (
            ".claude/STATE.md was modified concurrently; aborting",
            EXIT_WRITE_FAILURE,
        )

    try:
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=".state-md-", suffix=".tmp", dir=str(state_path.parent)
        )
    except OSError as exc:
        return f"write failure: {exc}", EXIT_WRITE_FAILURE

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_text)
        written = Path(tmp_path_str).read_text(encoding="utf-8")
        post_error = validate_composition(written, original_lines)
        if post_error:
            os.unlink(tmp_path_str)
            return (
                f"post-write validation failed: {post_error}",
                EXIT_STRUCTURE_INVALID,
            )
        os.replace(tmp_path_str, str(state_path))
    except OSError as exc:
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        return f"write failure: {exc}", EXIT_WRITE_FAILURE
    return None, EXIT_OK


# --- CLI ---------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(description="Guard .claude/STATE.md compaction")
    parser.add_argument("--mode", choices=MODES, default="check")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="With --mode apply, actually replace .claude/STATE.md",
    )
    parser.add_argument(
        "--expect-hash",
        help="SHA-256 of the .claude/STATE.md the caller inspected; a mismatch is exit 3",
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


def _run_compose(report: dict, root: Path, lines: list[str]) -> tuple[dict, int]:
    composed = compose_state(lines)
    composed_path = root / ".claude" / "logs" / "composed-state.md"
    error = _write_file(composed_path, composed.text)
    if error:
        report["ok"] = False
        report["error"] = error
        return report, EXIT_WRITE_FAILURE
    report["composed_state"] = _rel(composed_path, root)
    report["artifacts"] = [_rel(composed_path, root)]
    return report, EXIT_OK


def _run_apply(
    report: dict,
    root: Path,
    state_path: Path,
    original_text: str,
    args: argparse.Namespace,
) -> tuple[dict, int]:
    lines = original_text.splitlines()
    composed = compose_state(lines)
    pre_error = validate_composition(composed.text, lines)
    if pre_error:
        report["ok"] = False
        report["error"] = f"composition validation failed: {pre_error}"
        return report, EXIT_STRUCTURE_INVALID

    report["state_hash_before"] = _sha256(original_text)
    if not args.apply:
        try:
            now = _parse_now(args.now)
        except ValueError as exc:
            report["ok"] = False
            report["error"] = f"cannot parse '--now': {exc}"
            return report, EXIT_BAD_INPUT
        stamp = now.strftime("%Y%m%d-%H%M%S")
        preview = root / ".claude" / "logs" / f"state-compaction-preview-{stamp}.md"
        error = _write_file(preview, composed.text)
        if error:
            report["ok"] = False
            report["error"] = error
            return report, EXIT_WRITE_FAILURE
        report["result"] = "preview"
        report["applied"] = False
        report["preview_file"] = _rel(preview, root)
        report["artifacts"] = [_rel(preview, root)]
        return report, EXIT_OK

    error, exit_code = apply_atomically(
        state_path, composed.text, original_text, args.expect_hash
    )
    if error:
        report["ok"] = False
        report["applied"] = False
        report["error"] = error
        return report, exit_code
    report["result"] = "applied"
    report["applied"] = True
    report["state_hash_after"] = _sha256(composed.text)
    report["artifacts"] = [_rel(state_path, root)]
    return report, EXIT_OK


def _run_verify(report: dict, original_text: str) -> tuple[dict, int]:
    lines = original_text.splitlines()
    composed = compose_state(lines)
    applied = composed.text == (original_text.rstrip("\n") + "\n")
    report["compaction_applied"] = applied
    report["state_hash"] = _sha256(original_text)
    if not applied:
        report["ok"] = False
        report["error"] = (
            "compaction not applied: "
            f"{len(composed.blocks_pruned)} redundant work block(s) remain"
        )
        return report, EXIT_STRUCTURE_INVALID
    return report, EXIT_OK


def main() -> int:
    args = _build_parser().parse_args()
    root = args.project_root
    state_path = root / ".claude" / "STATE.md"

    try:
        original_text = state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _emit(
            {
                "ok": False,
                "mode": args.mode,
                "error": f"cannot read {state_path}: {exc}",
                "artifacts": [],
            }
        )
        return EXIT_WRITE_FAILURE

    lines = original_text.splitlines()
    report = build_report(lines, root, args.mode)
    if not report["ok"]:
        _emit(report)
        return EXIT_STRUCTURE_INVALID

    if args.mode == "compose":
        report, code = _run_compose(report, root, lines)
    elif args.mode == "apply":
        report, code = _run_apply(report, root, state_path, original_text, args)
    elif args.mode == "verify":
        report, code = _run_verify(report, original_text)
    else:
        code = EXIT_OK

    _emit(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
