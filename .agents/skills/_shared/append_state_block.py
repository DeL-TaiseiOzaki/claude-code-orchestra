#!/usr/bin/env python3
"""Write a structured section or work block into .agents/STATE.md.

Two typed writers, one contract. ``--type feature|bug-fix|project`` renders a
``## Current Feature|Bug Fix|Project`` block from typed JSON input and appends
it to shared state; ``--type repository-identity`` replaces the body of the
``## Repository Identity`` section that ``/init`` owns (previously written by
hand with raw Edit/Write, with no validation of that section at all).

Both are dry-run by default; ``--apply`` writes atomically, validates the
composed document before replacing the original, refuses to write when
STATE.md changed since it was read, and verifies that the ``## Progress
Tracker`` section survived the write.

Usage:
    python3 append_state_block.py --type feature --input input.json
    python3 append_state_block.py --type bug-fix --input input.json --apply
    python3 append_state_block.py --type repository-identity --input id.json --apply

Input JSON:
    feature | bug-fix | project   {title, id?, sections?: [{heading, content}]}
    repository-identity           {identity}

Exit codes:
    0  preview / applied / no-op
    1  bad args or input-schema violation
    2  state document structure invalid (includes a clobbered Progress Tracker)
    3  ID conflict / concurrent modification / write failure
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

PROGRESS_TRACKER_HEADING = "## Progress Tracker"
STATE_HEADING = "# Agent State"
IDENTITY_HEADING = "## Repository Identity"

IDENTITY_TYPE = "repository-identity"
IDENTITY_MANAGED_COMMENT = "<!-- Managed by /init. Re-run /init to refresh. -->"
IDENTITY_DESIGN_POINTER = (
    "Macro requirements and design live in [docs/DESIGN.md](docs/DESIGN.md)."
)

BLOCK_ID_RE = re.compile(r"<!--\s*orchestra:block-id:\s*(.+?)\s*-->")
ANY_HEADING_RE = re.compile(r"^(#{1,6}) ")

TYPE_HEADING_MAP = {
    "feature": "Current Feature",
    "bug-fix": "Current Bug Fix",
    "project": "Current Project",
}

TYPE_CHOICES = [*TYPE_HEADING_MAP, IDENTITY_TYPE]

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_STRUCTURE_INVALID = 2
EXIT_CONFLICT = 3


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
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


def _slugify(title: str) -> str:
    """Derive a URL-safe slug from a title string."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:64] if slug else "untitled"


# --- input validation --------------------------------------------------------


def validate_input(data: dict) -> str | None:
    """Return an error message if *data* violates the block schema, else None."""
    if not isinstance(data, dict):
        return "input must be a JSON object"
    title = data.get("title")
    if not title or not isinstance(title, str):
        return "'title' is required and must be a non-empty string"
    sections = data.get("sections")
    if sections is not None:
        if not isinstance(sections, list):
            return "'sections' must be a list"
        for idx, sec in enumerate(sections):
            if not isinstance(sec, dict):
                return f"sections[{idx}] must be an object"
            if not sec.get("heading") or not isinstance(sec["heading"], str):
                return f"sections[{idx}].heading is required and must be a string"
            if not isinstance(sec.get("content", ""), str):
                return f"sections[{idx}].content must be a string"
    return None


def validate_identity_input(data: dict) -> str | None:
    """Return an error message if *data* violates the identity schema, else None.

    The section body is one identity sentence plus the fixed DESIGN.md pointer
    (``init/SKILL.md`` step 4), so anything that would introduce a heading, a
    thematic break, or a second paragraph is rejected rather than written.
    """
    if not isinstance(data, dict):
        return "input must be a JSON object"
    unknown = sorted(set(data) - {"identity"})
    if unknown:
        return f"unknown field(s) for {IDENTITY_TYPE}: {', '.join(unknown)}"
    identity = data.get("identity")
    if not identity or not isinstance(identity, str) or not identity.strip():
        return "'identity' is required and must be a non-empty string"
    if "\n\n" in identity.strip():
        return "'identity' must be a single paragraph"
    for line in identity.splitlines():
        if ANY_HEADING_RE.match(line.strip()) or line.strip() == "---":
            return "'identity' must not contain a heading or a '---' separator"
    return None


# --- document structure ------------------------------------------------------


def validate_structure(text: str, require_identity: bool = False) -> str | None:
    """Return an error message if shared state structure is invalid."""
    if text.count(STATE_HEADING) != 1:
        return f"expected exactly 1 '{STATE_HEADING}' heading"
    if text.count(PROGRESS_TRACKER_HEADING) != 1:
        return f"expected exactly 1 '{PROGRESS_TRACKER_HEADING}' heading"
    if require_identity and text.count(IDENTITY_HEADING) != 1:
        return f"expected exactly 1 '{IDENTITY_HEADING}' heading"
    return None


def _headings(text: str) -> list[str]:
    return [
        line.strip() for line in text.splitlines() if ANY_HEADING_RE.match(line.strip())
    ]


def section_body(text: str, heading: str) -> list[str] | None:
    """Return the body lines of *heading*'s section, or None if not unique.

    The section ends at the next heading of the same or a shallower level, so a
    ``### `` subsection stays part of its parent.
    """
    lines = text.splitlines()
    matches = [idx for idx, line in enumerate(lines) if line.strip() == heading]
    if len(matches) != 1:
        return None
    start = matches[0]
    own_level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        match = ANY_HEADING_RE.match(lines[idx])
        if match and len(match.group(1)) <= own_level:
            end = idx
            break
    return lines[start + 1 : end]


def progress_tracker_preserved(original_text: str, new_text: str) -> bool:
    """Whether the ``## Progress Tracker`` section survived the composition.

    A real check, not a constant: the heading must still be unique and every
    line of its original body must still be present, in order, at the start of
    the new body. A work block is appended at the end of the file, which is
    textually *inside* that trailing section, so purely-appended content is
    allowed — deleting, reordering, or rewriting any existing tracker line is
    not.
    """
    before = section_body(original_text, PROGRESS_TRACKER_HEADING)
    after = section_body(new_text, PROGRESS_TRACKER_HEADING)
    if before is None or after is None:
        return False
    return after[: len(before)] == before


def validate_composition(
    new_text: str, original_text: str, identity: bool
) -> str | None:
    """Return an error message if the composed document is malformed, else None.

    Runs against the bytes that were actually written to the temp file, before
    ``os.replace`` — the guarantee the Writer Safety Contract requires.
    """
    struct_error = validate_structure(new_text, require_identity=identity)
    if struct_error:
        return struct_error
    remaining = _headings(new_text)
    for heading in _headings(original_text):
        if heading not in remaining:
            return f"composed document lost or reordered the heading '{heading}'"
        remaining = remaining[remaining.index(heading) + 1 :]
    if not progress_tracker_preserved(original_text, new_text):
        return (
            f"composed document modified the existing '{PROGRESS_TRACKER_HEADING}' body"
        )
    return None


# --- rendering ---------------------------------------------------------------


def render_block(block_type: str, block_id: str, data: dict) -> str:
    """Render a shared-state work block from validated input data."""
    heading_prefix = TYPE_HEADING_MAP[block_type]
    title = data["title"]
    sections = data.get("sections") or []

    parts: list[str] = [
        "---",
        "",
        f"## {heading_prefix}: {title}",
        f"<!-- orchestra:block-id: {block_id} -->",
    ]

    for sec in sections:
        parts.append("")
        parts.append(f"### {sec['heading']}")
        content = sec.get("content", "")
        if content:
            parts.append("")
            parts.append(content)

    return "\n".join(parts) + "\n"


def render_identity_body(data: dict) -> list[str]:
    """Render the ``## Repository Identity`` body lines from validated input."""
    return [
        "",
        IDENTITY_MANAGED_COMMENT,
        "",
        data["identity"].strip(),
        "",
        IDENTITY_DESIGN_POINTER,
        "",
    ]


def find_existing_block(text: str, block_id: str) -> tuple[str | None, int | None]:
    """Find an existing block with *block_id* and return (block_text, start_offset)."""
    lines = text.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        match = BLOCK_ID_RE.search(line)
        if match and match.group(1) == block_id:
            # Walk backward to find the block's "---" separator
            # Continue past the "## " heading and blank lines to reach "---"
            block_start = idx
            for back in range(idx - 1, -1, -1):
                stripped = lines[back].strip()
                if stripped == "---":
                    block_start = back
                    break
                if stripped.startswith("## "):
                    block_start = back
                    continue  # keep looking for preceding ---
                if stripped == "":
                    continue
                break
            # Walk forward to find end of block (next "---" or "## " or EOF)
            block_end = len(lines)
            for fwd in range(idx + 1, len(lines)):
                stripped = lines[fwd].strip()
                if stripped == "---" or stripped.startswith("## "):
                    block_end = fwd
                    break
            block_text = "".join(lines[block_start:block_end])
            start_offset = sum(len(lines[i]) for i in range(block_start))
            return block_text, start_offset
    return None, None


# --- composition -------------------------------------------------------------


@dataclass
class Composition:
    """The outcome of composing a new STATE.md, before any write happens."""

    new_text: str | None = None
    payload: dict = field(default_factory=dict)
    noop: bool = False
    error: str | None = None
    exit_code: int = EXIT_OK


def compose_block(block_type: str, data: dict, original_text: str) -> Composition:
    """Compose STATE.md with a work block appended."""
    error = validate_input(data)
    if error:
        return Composition(error=error, exit_code=EXIT_BAD_INPUT)

    block_id = data.get("id") or _slugify(data["title"])
    rendered = render_block(block_type, block_id, data)
    heading = f"{TYPE_HEADING_MAP[block_type]}: {data['title']}"
    payload = {"heading": heading, "block_id": block_id, "structure_ok": True}

    existing_text, _ = find_existing_block(original_text, block_id)
    if existing_text is not None:
        if existing_text.strip() == rendered.strip():
            return Composition(new_text=original_text, payload=payload, noop=True)
        return Composition(
            error=(
                f"block with id '{block_id}' already exists with different content; "
                "delete or revise the existing block manually"
            ),
            exit_code=EXIT_CONFLICT,
        )

    new_text = original_text.rstrip("\n") + "\n\n" + rendered
    return Composition(new_text=new_text, payload=payload)


def compose_identity(data: dict, original_text: str) -> Composition:
    """Compose STATE.md with the ``## Repository Identity`` body replaced."""
    error = validate_identity_input(data)
    if error:
        return Composition(error=error, exit_code=EXIT_BAD_INPUT)

    body = render_identity_body(data)
    payload = {"heading": IDENTITY_HEADING, "structure_ok": True}
    lines = original_text.splitlines()

    existing = section_body(original_text, IDENTITY_HEADING)
    if existing is None:
        if original_text.count(IDENTITY_HEADING) > 1:
            return Composition(
                error=f"expected exactly 1 '{IDENTITY_HEADING}' heading",
                exit_code=EXIT_STRUCTURE_INVALID,
            )
        # Absent: create the section immediately before the Progress Tracker,
        # which validate_structure() has already proven to be unique.
        insert_at = lines.index(PROGRESS_TRACKER_HEADING)
        lines[insert_at:insert_at] = [IDENTITY_HEADING, *body]
    else:
        if [line.rstrip() for line in existing] == [line.rstrip() for line in body]:
            return Composition(new_text=original_text, payload=payload, noop=True)
        start = lines.index(IDENTITY_HEADING)
        lines[start + 1 : start + 1 + len(existing)] = body

    new_text = "\n".join(lines)
    if original_text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    return Composition(new_text=new_text, payload=payload)


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
        description="Write a structured section or work block into .agents/STATE.md",
    )
    parser.add_argument(
        "--type",
        choices=TYPE_CHOICES,
        required=True,
        help=f"Block type: {', '.join(TYPE_HEADING_MAP)}, or {IDENTITY_TYPE}",
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


def _write_preview(
    project_root: Path, new_text: str, now: datetime
) -> tuple[Path | None, str | None]:
    logs_dir = project_root / ".agents" / "logs"
    preview_path = logs_dir / f"state-preview-{now.strftime('%Y%m%d-%H%M%S')}.md"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return None, f"cannot write preview: {exc}"
    return preview_path, None


def _apply_atomically(
    state_path: Path, new_text: str, original_text: str, identity: bool
) -> tuple[str | None, int]:
    """Replace *state_path* with *new_text*.  Return (error, exit_code)."""
    try:
        current_text = state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"cannot re-read .agents/STATE.md: {exc}", EXIT_CONFLICT

    if _sha256(current_text) != _sha256(original_text):
        return ".agents/STATE.md was modified concurrently; aborting", EXIT_CONFLICT

    try:
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=".state-md-", suffix=".tmp", dir=str(state_path.parent)
        )
    except OSError as exc:
        return f"write failure: {exc}", EXIT_CONFLICT

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_text)
        written = Path(tmp_path_str).read_text(encoding="utf-8")
        post_error = validate_composition(written, original_text, identity)
        if post_error:
            os.unlink(tmp_path_str)
            return f"post-write validation failed: {post_error}", EXIT_STRUCTURE_INVALID
        os.replace(tmp_path_str, str(state_path))
    except OSError as exc:
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        return f"write failure: {exc}", EXIT_CONFLICT
    return None, EXIT_OK


def main() -> int:  # noqa: C901 — single-function CLI entry point
    args = _build_parser().parse_args()
    identity_mode = args.type == IDENTITY_TYPE

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

    state_path = args.project_root / ".agents" / "STATE.md"
    try:
        original_text = state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _emit(
            {
                "ok": False,
                "error": f"cannot read .agents/STATE.md: {exc}",
                "artifacts": [],
            }
        )
        return EXIT_STRUCTURE_INVALID

    struct_error = validate_structure(original_text)
    if struct_error:
        _emit({"ok": False, "error": struct_error, "artifacts": []})
        return EXIT_STRUCTURE_INVALID

    composed = (
        compose_identity(data, original_text)
        if identity_mode
        else compose_block(args.type, data, original_text)
    )
    if composed.error is not None:
        _emit({"ok": False, "error": composed.error, "artifacts": []})
        return composed.exit_code

    assert composed.new_text is not None
    if composed.noop:
        _emit(
            {
                "ok": True,
                "result": "no-op",
                "artifacts": [],
                "progress_tracker_preserved": True,
                **composed.payload,
            }
        )
        return EXIT_OK

    compose_error = validate_composition(
        composed.new_text, original_text, identity_mode
    )
    if compose_error:
        _emit(
            {
                "ok": False,
                "error": f"composition validation failed: {compose_error}",
                "artifacts": [],
            }
        )
        return EXIT_STRUCTURE_INVALID

    preserved = progress_tracker_preserved(original_text, composed.new_text)

    if not args.apply:
        preview_path, preview_error = _write_preview(
            args.project_root, composed.new_text, now
        )
        if preview_error or preview_path is None:
            _emit({"ok": False, "error": preview_error, "artifacts": []})
            return EXIT_CONFLICT
        _emit(
            {
                "ok": True,
                "result": "preview",
                "preview_file": str(preview_path),
                "artifacts": [_rel(preview_path, args.project_root)],
                "progress_tracker_preserved": preserved,
                **composed.payload,
            }
        )
        return EXIT_OK

    error, exit_code = _apply_atomically(
        state_path, composed.new_text, original_text, identity_mode
    )
    if error:
        _emit({"ok": False, "error": error, "artifacts": []})
        return exit_code

    _emit(
        {
            "ok": True,
            "result": "applied",
            "artifacts": [_rel(state_path, args.project_root)],
            "progress_tracker_preserved": preserved,
            **composed.payload,
        }
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
