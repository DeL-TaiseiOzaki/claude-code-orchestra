#!/usr/bin/env python3
"""Update .claude/docs/DESIGN.md with decisions, table rows, and section appends.

Appends rows to the typed DESIGN.md tables (Key Decisions, functional
requirements, non-functional requirements, tech choices, agent roles) and/or
content to named sections, from typed JSON input.  Dry-run by default;
``--apply`` writes atomically, validates the composed document before
replacing it, and refuses to write when DESIGN.md changed since it was read.

Every write is idempotent: re-applying the same input is a ``no-op``, so a
retried phase cannot duplicate content.  With ``--require-change`` a ``no-op``
is a contract violation (exit 2), so a caller can never report "recorded" for a
run that wrote nothing.

Usage:
    python3 update_design.py --input input.json
    python3 update_design.py --input input.json --apply
    python3 update_design.py --input input.json --apply --require-change
    python3 update_design.py --input input.json --apply --now 2026-07-25T09:00:00

Input JSON keys (all optional, at least one required):
    decisions      [{decision, rationale, alternatives, date}]
    requirements   [{id, requirement, priority, notes}]
    nfr            [{category, requirement, metric}]
    tech_choices   [{area, technology, rationale, alternatives}]
    agent_roles    [{agent, role, responsibilities}]
    section_updates[{heading, content}]

Exit codes:
    0  preview / applied / no-op
    1  bad args or input-schema violation
    2  marker / document-structure invalid (includes missing DESIGN.md),
       a duplicate requirement ID, or a no-op under --require-change
    3  concurrent modification / write failure
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

DECISIONS_HEADER = "| Decision | Rationale | Alternatives Considered | Date |"
SEPARATOR_RE = re.compile(r"^\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*$")
HEADING_RE = re.compile(r"^## ")
ANY_HEADING_RE = re.compile(r"^(#{1,6}) ")
TABLE_ROW_RE = re.compile(r"^\s*\|")

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_STRUCTURE_INVALID = 2
EXIT_CONFLICT = 3


@dataclass(frozen=True)
class TableTarget:
    """One typed DESIGN.md table: where it lives and how a row is built.

    ``fields`` are input keys in column order; ``required`` are the input keys
    a row cannot omit; ``identity`` names the column that must stay unique
    (only functional requirements have stable IDs, per the DESIGN.md template).
    """

    key: str
    heading: str
    header: str
    fields: tuple[str, ...]
    required: tuple[str, ...]
    identity: str | None = None


TABLE_TARGETS: tuple[TableTarget, ...] = (
    TableTarget(
        key="requirements",
        heading="## 機能要件 (Functional Requirements)",
        header="| ID | Requirement | Priority | Notes |",
        fields=("id", "requirement", "priority", "notes"),
        required=("id", "requirement"),
        identity="id",
    ),
    TableTarget(
        key="nfr",
        heading="## 非機能要件 (Non-Functional Requirements)",
        header="| Category | Requirement | Metric / Target |",
        fields=("category", "requirement", "metric"),
        required=("category", "requirement"),
    ),
    TableTarget(
        key="tech_choices",
        heading="## 技術選定 (Tech Stack & Rationale)",
        header="| Area | Technology | Rationale | Alternatives Considered |",
        fields=("area", "technology", "rationale", "alternatives"),
        required=("area", "technology"),
    ),
    TableTarget(
        key="agent_roles",
        heading="### Agent Roles",
        header="| Agent | Role | Responsibilities |",
        fields=("agent", "role", "responsibilities"),
        required=("agent", "role"),
    ),
)

TABLE_TARGETS_BY_KEY = {target.key: target for target in TABLE_TARGETS}

# Every table this script knows how to place a row in, including Key Decisions.
# validate_composition() re-checks each one after composing the document.
KNOWN_TABLE_HEADERS = (DECISIONS_HEADER,) + tuple(t.header for t in TABLE_TARGETS)


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable and never
    masquerades as this tool's exit code 2 or 3."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_INPUT)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _escape_cell(text: str) -> str:
    """Escape pipe characters and newlines for Markdown table cells.

    Without this, a rationale containing ``A|B`` silently becomes two cells and
    shifts every later column of that row.
    """
    return text.replace("|", "\\|").replace("\n", "<br>")


def _unescape_cell(text: str) -> str:
    """Inverse of :func:`_escape_cell`, for comparing an existing row."""
    return text.replace("\\|", "|").replace("<br>", "\n").strip()


def _split_row(line: str) -> list[str]:
    """Split a Markdown table row into unescaped cell values.

    Splits on unescaped ``|`` only, so ``\\|`` inside a cell stays one cell.
    """
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    return [_unescape_cell(cell) for cell in cells]


def _render_row(cells: list[str]) -> str:
    return "| " + " | ".join(_escape_cell(cell) for cell in cells) + " |"


# --- input validation --------------------------------------------------------


def _validate_row_list(key: str, rows: object, target: TableTarget) -> str | None:
    if not isinstance(rows, list):
        return f"'{key}' must be a list"
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            return f"{key}[{idx}] must be an object"
        unknown = sorted(set(row) - set(target.fields))
        if unknown:
            return (
                f"{key}[{idx}] has unknown field(s) {', '.join(unknown)}; "
                f"allowed: {', '.join(target.fields)}"
            )
        for field in target.fields:
            if not isinstance(row.get(field, ""), str):
                return f"{key}[{idx}].{field} must be a string"
        for field in target.required:
            if not row.get(field, "").strip():
                return f"{key}[{idx}].{field} is required"
    return None


def validate_input(data: dict) -> str | None:
    """Return an error message if *data* violates the input schema, else None."""
    if not isinstance(data, dict):
        return "input must be a JSON object"
    payload_keys = ("decisions", "section_updates") + tuple(TABLE_TARGETS_BY_KEY)
    if all(data.get(key) is None for key in payload_keys):
        return f"at least one of {', '.join(payload_keys)} is required"
    decisions = data.get("decisions")
    if decisions is not None:
        if not isinstance(decisions, list):
            return "'decisions' must be a list"
        for idx, dec in enumerate(decisions):
            if not isinstance(dec, dict):
                return f"decisions[{idx}] must be an object"
            for field in ("decision", "rationale", "alternatives"):
                if not isinstance(dec.get(field, ""), str):
                    return f"decisions[{idx}].{field} must be a string"
                if field == "decision" and not dec.get(field, "").strip():
                    return f"decisions[{idx}].decision is required"
            date_val = dec.get("date")
            if date_val is not None and not re.match(
                r"^\d{4}-\d{2}-\d{2}$", str(date_val)
            ):
                return f"decisions[{idx}].date must be YYYY-MM-DD"
    for key, target in TABLE_TARGETS_BY_KEY.items():
        rows = data.get(key)
        if rows is None:
            continue
        error = _validate_row_list(key, rows, target)
        if error:
            return error
    section_updates = data.get("section_updates")
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


# --- document navigation -----------------------------------------------------


def _find_table(lines: list[str], header: str) -> tuple[int, int] | None:
    """Find the table introduced by *header*.  Return (header_idx, last_row_idx).

    Returns None when the header is missing, duplicated, or not followed by a
    separator row — all of which mean "do not guess where the row goes".
    """
    header_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == header:
            if header_idx is not None:
                return None  # duplicate header — structural error
            header_idx = idx
    if header_idx is None:
        return None
    sep_idx = header_idx + 1
    if sep_idx >= len(lines) or not SEPARATOR_RE.match(lines[sep_idx]):
        return None
    last_row = sep_idx
    for idx in range(sep_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            last_row = idx
        else:
            break
    return header_idx, last_row


def _find_section_range(lines: list[str], heading: str) -> tuple[int, int] | None:
    """Find the line range for a section.  Return (heading_idx, end_idx).

    end_idx is the index of the next heading at the same or a shallower level
    (so ``### Agent Roles`` ends at the next ``### `` or ``## ``), or
    len(lines).
    """
    matches = [idx for idx, line in enumerate(lines) if line.strip() == heading.strip()]
    if len(matches) != 1:
        return None  # missing or duplicate
    heading_idx = matches[0]
    own_level = len(heading.strip()) - len(heading.strip().lstrip("#"))
    end_idx = len(lines)
    for idx in range(heading_idx + 1, len(lines)):
        match = ANY_HEADING_RE.match(lines[idx])
        if match and len(match.group(1)) <= own_level:
            end_idx = idx
            break
    return heading_idx, end_idx


def _is_placeholder(cells: list[str], skip: int = 0) -> bool:
    """True when every cell from index *skip* onward is empty."""
    return all(not cell.strip() for cell in cells[skip:])


def _place_row(
    lines: list[str],
    table_range: tuple[int, int],
    cells: list[str],
    identity_col: int | None,
) -> tuple[str, tuple[int, int]]:
    """Insert or fill *cells* in the table at *table_range*.

    Returns (outcome, new_table_range) where outcome is one of:

    ``duplicate``  an identical row already exists — nothing changed.
    ``filled``     a template row whose cells were all empty (or whose only
                   filled cell is the label this row repeats) was completed in
                   place, instead of leaving the empty row behind.
    ``appended``   a new row was inserted directly after the last row, so it
                   stays part of the table instead of being orphaned after the
                   section's trailing blank line.
    ``conflict``   *identity_col* already holds this value with different,
                   non-empty content. Only tables with a stable identity column
                   (functional requirement IDs) can report this.
    """
    header_idx, last_row = table_range
    width = len(cells)
    stripped = [cell.strip() for cell in cells]
    parsed = {
        idx: _split_row(lines[idx]) for idx in range(header_idx + 2, last_row + 1)
    }
    same_width = {
        idx: existing for idx, existing in parsed.items() if len(existing) == width
    }

    for existing in same_width.values():
        if existing == stripped:
            return "duplicate", table_range

    # A template row that carries only its label ("| Performance | | |") is an
    # unfilled placeholder, not a competing entry: complete it in place.
    for idx, existing in same_width.items():
        if existing[0] and existing[0] == stripped[0] and _is_placeholder(existing, 1):
            lines[idx] = _render_row(cells)
            return "filled", table_range

    if identity_col is not None:
        for existing in same_width.values():
            if existing[identity_col] == stripped[identity_col]:
                return "conflict", table_range

    for idx, existing in same_width.items():
        if _is_placeholder(existing):
            lines[idx] = _render_row(cells)
            return "filled", table_range

    lines.insert(last_row + 1, _render_row(cells))
    return "appended", (header_idx, last_row + 1)


def _section_contains(lines: list[str], start: int, end: int, block: list[str]) -> bool:
    """True when *block* already appears as a contiguous run inside the section."""
    body = [line.rstrip() for line in lines[start:end]]
    needle = [line.rstrip() for line in block if line.strip()]
    if not needle:
        return True
    for offset in range(len(body)):
        window = [line for line in body[offset : offset + len(block)] if line]
        if window[: len(needle)] == needle:
            return True
    return False


def _insert_section_block(
    lines: list[str], start: int, end: int, block: list[str]
) -> None:
    """Append *block* to the section body, keeping the surrounding blank lines.

    The insertion point is *before* the section's trailing blank lines, not at
    ``end``: inserting at ``end`` put the content after the blank line (so a
    table row was orphaned outside its table) and left no blank line before the
    following heading.
    """
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    payload = list(block)
    if insert_at > start and lines[insert_at - 1].strip():
        payload = [""] + payload
    if insert_at == len(lines):
        pass  # end of document: no following heading to separate from
    elif insert_at == end:
        payload = payload + [""]  # no trailing blank existed; keep one
    lines[insert_at:insert_at] = payload


# --- composition -------------------------------------------------------------


@dataclass
class ChangeReport:
    decisions_appended: int = 0
    skipped_duplicates: int = 0
    rows_appended: dict[str, int] | None = None
    sections_updated: list[str] | None = None

    def __post_init__(self) -> None:
        if self.rows_appended is None:
            self.rows_appended = {}
        if self.sections_updated is None:
            self.sections_updated = []

    @property
    def is_noop(self) -> bool:
        return (
            self.decisions_appended == 0
            and not any(self.rows_appended.values())
            and not self.sections_updated
        )


def _apply_decisions(
    lines: list[str], decisions: list[dict], today: str, report: ChangeReport
) -> str | None:
    table_range = _find_table(lines, DECISIONS_HEADER)
    if table_range is None:
        return f"cannot locate unique '{DECISIONS_HEADER}' table in DESIGN.md"
    for dec in decisions:
        cells = [
            dec["decision"].strip(),
            dec.get("rationale", "").strip(),
            dec.get("alternatives", "").strip(),
            str(dec.get("date") or today),
        ]
        # Dedup on the decision text alone, never on the date: keying dedup on
        # today's date made the same decision duplicate when re-applied on a
        # later day.
        header_idx, last_row = table_range
        for idx in range(header_idx + 2, last_row + 1):
            existing = _split_row(lines[idx])
            if len(existing) >= 1 and existing[0] and existing[0] == cells[0]:
                report.skipped_duplicates += 1
                break
        else:
            outcome, table_range = _place_row(lines, table_range, cells, None)
            if outcome == "duplicate":
                report.skipped_duplicates += 1
            else:
                report.decisions_appended += 1
    return None


def _apply_table_rows(
    lines: list[str], target: TableTarget, rows: list[dict], report: ChangeReport
) -> str | None:
    table_range = _find_table(lines, target.header)
    if table_range is None:
        return (
            f"cannot locate unique '{target.header}' table under "
            f"'{target.heading}' in DESIGN.md"
        )
    header_cells = _split_row(lines[table_range[0]])
    if len(header_cells) != len(target.fields):
        return (
            f"'{target.heading}' table has {len(header_cells)} columns, "
            f"expected {len(target.fields)}"
        )
    identity_col = (
        target.fields.index(target.identity) if target.identity is not None else None
    )
    for row in rows:
        cells = [row.get(field, "").strip() for field in target.fields]
        outcome, table_range = _place_row(lines, table_range, cells, identity_col)
        if outcome == "duplicate":
            report.skipped_duplicates += 1
        elif outcome == "conflict":
            assert identity_col is not None
            return (
                f"'{target.heading}' already has a row with "
                f"{target.identity} = '{cells[identity_col]}' and different "
                "content; revise that row manually"
            )
        else:
            report.rows_appended[target.key] = (
                report.rows_appended.get(target.key, 0) + 1
            )
    return None


def _apply_section_updates(
    lines: list[str], updates: list[dict], report: ChangeReport
) -> str | None:
    for upd in updates:
        heading = upd["heading"]
        content = upd.get("content", "")
        if not content.strip():
            continue
        sec_range = _find_section_range(lines, heading)
        if sec_range is None:
            return f"cannot locate unique section '{heading}' in DESIGN.md"
        sec_start, sec_end = sec_range
        typed_key = _typed_key_for_section(lines, sec_start, sec_end)
        if typed_key and any(TABLE_ROW_RE.match(line) for line in content.splitlines()):
            return (
                f"'{heading}' holds a typed table; pass table rows under the "
                f"'{typed_key}' input key instead of 'section_updates', so the "
                "cells are escaped and the row lands inside the table"
            )
        block = content.splitlines()
        if _section_contains(lines, sec_start, sec_end, block):
            report.skipped_duplicates += 1
            continue
        _insert_section_block(lines, sec_start, sec_end, block)
        report.sections_updated.append(heading)
    return None


def _typed_key_for_section(lines: list[str], start: int, end: int) -> str | None:
    """Return the typed input key for a table inside the given section, if any."""
    body = {line.strip() for line in lines[start:end]}
    for target in TABLE_TARGETS:
        if target.header in body:
            return target.key
    if DECISIONS_HEADER in body:
        return "decisions"
    return None


def apply_changes(
    text: str, data: dict, today: str
) -> tuple[str, ChangeReport] | tuple[None, str]:
    """Apply every requested change to *text*.

    Returns (new_text, report) on success, or (None, error_message) on a
    structural error.
    """
    lines = text.splitlines()
    report = ChangeReport()

    decisions = data.get("decisions") or []
    if decisions:
        error = _apply_decisions(lines, decisions, today, report)
        if error:
            return None, error

    for target in TABLE_TARGETS:
        rows = data.get(target.key) or []
        if not rows:
            continue
        error = _apply_table_rows(lines, target, rows, report)
        if error:
            return None, error

    error = _apply_section_updates(lines, data.get("section_updates") or [], report)
    if error:
        return None, error

    new_text = "\n".join(lines)
    if text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    return new_text, report


# --- verified success path ---------------------------------------------------


def _headings(text: str) -> list[str]:
    return [
        line.strip() for line in text.splitlines() if ANY_HEADING_RE.match(line.strip())
    ]


def validate_composition(new_text: str, original_text: str) -> str | None:
    """Return an error message if the composed document is malformed, else None.

    Checked before ``os.replace`` (the clause the previous implementation
    skipped): every original heading survives, in its original order, no known
    table was lost or duplicated, every row of a known table still has the
    header's column count, and the result never shrinks — appends and
    placeholder fills only ever grow the document, so a shorter result means
    content was dropped. A section update may legitimately introduce a *new*
    subheading, so the original headings must be a subsequence of the new ones
    rather than equal to them.
    """
    remaining = _headings(new_text)
    for heading in _headings(original_text):
        if heading not in remaining:
            return (
                f"composed document lost or reordered the heading '{heading}'; "
                "refusing to write"
            )
        remaining = remaining[remaining.index(heading) + 1 :]
    if len(new_text) < len(original_text):
        return "composed document is shorter than the original; refusing to write"
    lines = new_text.splitlines()
    original_lines = original_text.splitlines()
    for header in KNOWN_TABLE_HEADERS:
        if _find_table(original_lines, header) is None:
            continue
        table_range = _find_table(lines, header)
        if table_range is None:
            return f"composed document lost or duplicated the '{header}' table"
        header_idx, last_row = table_range
        width = len(_split_row(lines[header_idx]))
        for idx in range(header_idx + 2, last_row + 1):
            row_width = len(_split_row(lines[idx]))
            if row_width != width:
                return (
                    f"row {idx + 1} of the '{header}' table has {row_width} "
                    f"cells, expected {width}"
                )
    return None


# --- CLI ---------------------------------------------------------------------


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


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Update .claude/docs/DESIGN.md with decisions, table rows, "
        "and section appends",
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
        "--require-change",
        action="store_true",
        help="Exit 2 when the run changes nothing (duplicate or empty input)",
    )
    parser.add_argument(
        "--now",
        help="ISO 8601 timestamp to stamp instead of the real clock",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    return parser


def main() -> int:  # noqa: C901 — single-function CLI entry point
    args = _build_parser().parse_args()

    try:
        now = _parse_now(args.now)
    except ValueError as exc:
        _emit({"ok": False, "error": f"cannot parse '--now': {exc}", "artifacts": []})
        return EXIT_BAD_INPUT

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error": f"cannot read input: {exc}", "artifacts": []})
        return EXIT_BAD_INPUT

    error = validate_input(data)
    if error:
        _emit({"ok": False, "error": error, "artifacts": []})
        return EXIT_BAD_INPUT

    design_path = args.project_root / ".claude" / "docs" / "DESIGN.md"
    if not design_path.exists():
        _emit(
            {
                "ok": False,
                "error": "DESIGN.md does not exist; run /init first",
                "artifacts": [],
            }
        )
        return EXIT_STRUCTURE_INVALID

    try:
        original_text = design_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _emit({"ok": False, "error": f"cannot read DESIGN.md: {exc}", "artifacts": []})
        return EXIT_STRUCTURE_INVALID

    original_hash = _sha256(original_text)
    today = now.strftime("%Y-%m-%d")

    new_text, report = apply_changes(original_text, data, today)
    if new_text is None:
        _emit({"ok": False, "error": report, "artifacts": []})
        return EXIT_STRUCTURE_INVALID

    payload: dict[str, object] = {
        "decisions_appended": report.decisions_appended,
        "rows_appended": report.rows_appended,
        "skipped_duplicates": report.skipped_duplicates,
        "sections_updated": report.sections_updated,
    }

    if report.is_noop:
        if args.require_change:
            _emit(
                {
                    "ok": False,
                    "result": "no-op",
                    "error": (
                        "nothing to write: every entry was a duplicate or empty, "
                        "and '--require-change' was requested"
                    ),
                    "artifacts": [],
                    **payload,
                }
            )
            return EXIT_STRUCTURE_INVALID
        _emit({"ok": True, "result": "no-op", "artifacts": [], **payload})
        return EXIT_OK

    struct_error = validate_composition(new_text, original_text)
    if struct_error:
        _emit(
            {
                "ok": False,
                "error": f"composition validation failed: {struct_error}",
                "artifacts": [],
            }
        )
        return EXIT_STRUCTURE_INVALID

    logs_dir = args.project_root / ".claude" / "logs"

    if not args.apply:
        preview_path = logs_dir / f"design-preview-{now.strftime('%Y%m%d-%H%M%S')}.md"
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            preview_path.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            _emit(
                {
                    "ok": False,
                    "error": f"cannot write preview: {exc}",
                    "artifacts": [],
                }
            )
            return EXIT_CONFLICT
        _emit(
            {
                "ok": True,
                "result": "preview",
                "preview_file": str(preview_path),
                "artifacts": [_rel(preview_path, args.project_root)],
                **payload,
            }
        )
        return EXIT_OK

    try:
        current_text = design_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _emit(
            {"ok": False, "error": f"cannot re-read DESIGN.md: {exc}", "artifacts": []}
        )
        return EXIT_CONFLICT

    if _sha256(current_text) != original_hash:
        _emit(
            {
                "ok": False,
                "error": "DESIGN.md was modified concurrently; aborting",
                "artifacts": [],
            }
        )
        return EXIT_CONFLICT

    try:
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=".design-md-", suffix=".tmp", dir=str(design_path.parent)
        )
    except OSError as exc:
        _emit({"ok": False, "error": f"write failure: {exc}", "artifacts": []})
        return EXIT_CONFLICT
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_text)
        # Validate what is actually on disk, then replace.
        post_error = validate_composition(
            Path(tmp_path_str).read_text(encoding="utf-8"), original_text
        )
        if post_error:
            os.unlink(tmp_path_str)
            _emit(
                {
                    "ok": False,
                    "error": f"post-write validation failed: {post_error}",
                    "artifacts": [],
                }
            )
            return EXIT_STRUCTURE_INVALID
        os.replace(tmp_path_str, str(design_path))
    except OSError as exc:
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        _emit({"ok": False, "error": f"write failure: {exc}", "artifacts": []})
        return EXIT_CONFLICT

    _emit(
        {
            "ok": True,
            "result": "applied",
            "artifacts": [_rel(design_path, args.project_root)],
            **payload,
        }
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
