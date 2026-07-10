#!/usr/bin/env python3
"""Update .claude/docs/DESIGN.md with decisions and section appends.

Appends rows to the Key Decisions table and/or content to named sections,
from typed JSON input.  Dry-run by default; ``--apply`` writes atomically
with concurrent-modification detection.

Usage:
    python3 update_design.py --input input.json
    python3 update_design.py --input input.json --apply

Exit codes:
    0  preview / applied / no-op
    1  bad args or input-schema violation
    2  marker / document-structure invalid (includes missing DESIGN.md)
    3  concurrent modification / write failure
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DECISIONS_HEADER = "| Decision | Rationale | Alternatives Considered | Date |"
DECISIONS_SEPARATOR_RE = re.compile(
    r"^\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|"
)
HEADING_RE = re.compile(r"^## ")

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_STRUCTURE_INVALID = 2
EXIT_CONFLICT = 3


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _escape_cell(text: str) -> str:
    """Escape pipe characters and newlines for Markdown table cells."""
    return text.replace("|", "\\|").replace("\n", "<br>")


def validate_input(data: dict) -> str | None:
    """Return an error message if *data* violates the input schema, else None."""
    if not isinstance(data, dict):
        return "input must be a JSON object"
    decisions = data.get("decisions")
    section_updates = data.get("section_updates")
    if decisions is None and section_updates is None:
        return "at least one of 'decisions' or 'section_updates' is required"
    if decisions is not None:
        if not isinstance(decisions, list):
            return "'decisions' must be a list"
        for idx, dec in enumerate(decisions):
            if not isinstance(dec, dict):
                return f"decisions[{idx}] must be an object"
            for field in ("decision", "rationale", "alternatives"):
                if not isinstance(dec.get(field, ""), str):
                    return f"decisions[{idx}].{field} must be a string"
                if field == "decision" and not dec.get(field):
                    return f"decisions[{idx}].decision is required"
            date_val = dec.get("date")
            if date_val is not None:
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date_val)):
                    return f"decisions[{idx}].date must be YYYY-MM-DD"
    if section_updates is not None:
        if not isinstance(section_updates, list):
            return "'section_updates' must be a list"
        for idx, upd in enumerate(section_updates):
            if not isinstance(upd, dict):
                return f"section_updates[{idx}] must be an object"
            if not upd.get("heading") or not isinstance(upd["heading"], str):
                return f"section_updates[{idx}].heading is required"
            if not isinstance(upd.get("content", ""), str):
                return f"section_updates[{idx}].content must be a string"
    return None


def _find_decisions_table(lines: list[str]) -> tuple[int, int] | None:
    """Find the Key Decisions table.  Return (header_line_idx, last_row_idx)."""
    header_idx: int | None = None
    for idx, line in enumerate(lines):
        if DECISIONS_HEADER in line:
            if header_idx is not None:
                return None  # duplicate header — structural error
            header_idx = idx
    if header_idx is None:
        return None
    # Find the separator line after header
    sep_idx = header_idx + 1
    if sep_idx >= len(lines) or not DECISIONS_SEPARATOR_RE.match(lines[sep_idx]):
        return None
    # Walk forward through table rows
    last_row = sep_idx
    for idx in range(sep_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            last_row = idx
        else:
            break
    return header_idx, last_row


def _row_matches(line: str, decision: str, date: str) -> bool:
    """Check whether a table row has the same decision text and date."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 4:
        return False
    row_decision = cells[0].replace("\\|", "|").replace("<br>", "\n").strip()
    row_date = cells[3].strip()
    return row_decision == decision and row_date == date


def _find_section_range(lines: list[str], heading: str) -> tuple[int, int] | None:
    """Find the line range for a section.  Return (heading_idx, end_idx).

    end_idx is the line index of the next ``## `` heading, or len(lines).
    """
    matches: list[int] = []
    for idx, line in enumerate(lines):
        if line.strip() == heading.strip():
            matches.append(idx)
    if len(matches) != 1:
        return None  # missing or duplicate
    heading_idx = matches[0]
    end_idx = len(lines)
    for idx in range(heading_idx + 1, len(lines)):
        if HEADING_RE.match(lines[idx]):
            end_idx = idx
            break
    return heading_idx, end_idx


def apply_changes(  # noqa: C901
    text: str, data: dict, today: str,
) -> tuple[str, int, int, list[str]] | tuple[None, None, None, str]:
    """Apply decisions + section_updates to *text*.

    Returns (new_text, decisions_appended, skipped_duplicates, sections_updated)
    on success, or (None, None, None, error_message) on structural error.
    """
    lines = text.splitlines()
    decisions_appended = 0
    skipped_duplicates = 0
    sections_updated: list[str] = []
    new_rows: list[str] = []

    # --- Decisions ---
    decisions = data.get("decisions") or []
    if decisions:
        table_range = _find_decisions_table(lines)
        if table_range is None:
            return None, None, None, (
                f"cannot locate unique '{DECISIONS_HEADER}' table in DESIGN.md"
            )
        _header_idx, last_row = table_range
        existing_rows = lines[_header_idx:last_row + 1]
        for dec in decisions:
            date = dec.get("date") or today
            decision_text = dec["decision"]
            # Dedup check
            is_dup = any(
                _row_matches(row, decision_text, date) for row in existing_rows
            )
            if is_dup:
                skipped_duplicates += 1
                continue
            rationale = _escape_cell(dec.get("rationale", ""))
            alternatives = _escape_cell(dec.get("alternatives", ""))
            row = f"| {_escape_cell(decision_text)} | {rationale} | {alternatives} | {date} |"
            new_rows.append(row)
            decisions_appended += 1

        if new_rows:
            insert_pos = last_row + 1
            for row in reversed(new_rows):
                lines.insert(insert_pos, row)

    # --- Section updates ---
    section_updates = data.get("section_updates") or []
    for upd in section_updates:
        heading = upd["heading"]
        content = upd.get("content", "")
        if not content:
            continue
        sec_range = _find_section_range(lines, heading)
        if sec_range is None:
            return None, None, None, (
                f"cannot locate unique section '{heading}' in DESIGN.md"
            )
        _sec_start, sec_end = sec_range
        # Insert content lines before sec_end
        content_lines = content.splitlines()
        # Ensure a blank line before appended content
        if sec_end > 0 and lines[sec_end - 1].strip():
            content_lines = [""] + content_lines
        for line in reversed(content_lines):
            lines.insert(sec_end, line)
        sections_updated.append(heading)

    new_text = "\n".join(lines)
    # Preserve trailing newline
    if text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    return new_text, decisions_appended, skipped_duplicates, sections_updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update .claude/docs/DESIGN.md with decisions and section appends",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to JSON input file",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write; without this flag the script only previews",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    args = parser.parse_args()

    # --- Load and validate input JSON ---
    try:
        input_text = args.input.read_text(encoding="utf-8")
        data = json.loads(input_text)
    except (OSError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error": f"cannot read input: {exc}"})
        return EXIT_BAD_INPUT

    error = validate_input(data)
    if error:
        _emit({"ok": False, "error": error})
        return EXIT_BAD_INPUT

    # --- Load DESIGN.md ---
    design_path = args.project_root / ".claude" / "docs" / "DESIGN.md"
    if not design_path.exists():
        _emit({
            "ok": False,
            "error": "DESIGN.md does not exist; run /init first",
        })
        return EXIT_STRUCTURE_INVALID

    try:
        original_text = design_path.read_text(encoding="utf-8")
    except OSError as exc:
        _emit({"ok": False, "error": f"cannot read DESIGN.md: {exc}"})
        return EXIT_STRUCTURE_INVALID

    original_hash = _sha256(original_text)
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # --- Apply changes ---
    result = apply_changes(original_text, data, today)
    new_text, decisions_appended, skipped_duplicates, sections_updated = result
    if new_text is None:
        # sections_updated holds the error message in the error branch
        _emit({"ok": False, "error": sections_updated})
        return EXIT_STRUCTURE_INVALID

    # --- No-op check ---
    is_noop = (decisions_appended == 0 and not sections_updated)
    if is_noop:
        _emit({
            "ok": True,
            "result": "no-op",
            "decisions_appended": 0,
            "skipped_duplicates": skipped_duplicates,
            "sections_updated": [],
        })
        return EXIT_OK

    # --- Preview or apply ---
    logs_dir = args.project_root / ".claude" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not args.apply:
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        preview_path = logs_dir / f"design-preview-{timestamp}.md"
        preview_path.write_text(new_text, encoding="utf-8")
        _emit({
            "ok": True,
            "result": "preview",
            "decisions_appended": decisions_appended,
            "skipped_duplicates": skipped_duplicates,
            "sections_updated": sections_updated,
            "preview_file": str(preview_path),
        })
        return EXIT_OK

    # --- Atomic apply ---
    try:
        current_text = design_path.read_text(encoding="utf-8")
    except OSError as exc:
        _emit({"ok": False, "error": f"cannot re-read DESIGN.md: {exc}"})
        return EXIT_CONFLICT

    if _sha256(current_text) != original_hash:
        _emit({
            "ok": False,
            "error": "DESIGN.md was modified concurrently; aborting",
        })
        return EXIT_CONFLICT

    target_dir = design_path.parent
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=".design-md-", suffix=".tmp", dir=str(target_dir),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.replace(tmp_path_str, str(design_path))
    except OSError as exc:
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        _emit({"ok": False, "error": f"write failure: {exc}"})
        return EXIT_CONFLICT

    _emit({
        "ok": True,
        "result": "applied",
        "decisions_appended": decisions_appended,
        "skipped_duplicates": skipped_duplicates,
        "sections_updated": sections_updated,
    })
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
