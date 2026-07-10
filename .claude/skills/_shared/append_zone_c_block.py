#!/usr/bin/env python3
"""Append a structured work block to CLAUDE.md Zone C.

Renders a ``## Current Feature|Bug Fix|Project`` block from typed JSON input
and appends it to the end of Zone C.  Dry-run by default; ``--apply`` writes
atomically with concurrent-modification detection.

Usage:
    python3 append_zone_c_block.py --type feature --input input.json
    python3 append_zone_c_block.py --type bug-fix --input input.json --apply

Exit codes:
    0  preview / applied / no-op
    1  bad args or input-schema violation
    2  marker / document-structure invalid
    3  ID conflict / concurrent modification / write failure
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

TEMPLATE_BOUNDARY_MARKER = "@orchestra:template-boundary"
REPO_BOUNDARY_MARKER = "@orchestra:repo-boundary"
PROGRESS_TRACKER_HEADING = "## Progress Tracker"
BOUNDARY_BOX_CHAR = "━"  # heavy horizontal (━)

BLOCK_ID_RE = re.compile(r"<!--\s*orchestra:block-id:\s*(.+?)\s*-->")

TYPE_HEADING_MAP = {
    "feature": "Current Feature",
    "bug-fix": "Current Bug Fix",
    "project": "Current Project",
}

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_STRUCTURE_INVALID = 2
EXIT_CONFLICT = 3


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slugify(title: str) -> str:
    """Derive a URL-safe slug from a title string."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:64] if slug else "untitled"


def validate_input(data: dict) -> str | None:
    """Return an error message if *data* violates the input schema, else None."""
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


def validate_structure(text: str) -> str | None:
    """Return an error message if CLAUDE.md structure is invalid, else None."""
    tmpl_count = text.count(TEMPLATE_BOUNDARY_MARKER)
    repo_count = text.count(REPO_BOUNDARY_MARKER)
    if tmpl_count != 1:
        return f"expected exactly 1 {TEMPLATE_BOUNDARY_MARKER}, found {tmpl_count}"
    if repo_count != 1:
        return f"expected exactly 1 {REPO_BOUNDARY_MARKER}, found {repo_count}"
    tmpl_pos = text.index(TEMPLATE_BOUNDARY_MARKER)
    repo_pos = text.index(REPO_BOUNDARY_MARKER)
    if tmpl_pos >= repo_pos:
        return "template-boundary must appear before repo-boundary"
    zone_c_start = _zone_c_start_offset(text)
    zone_c_text = text[zone_c_start:]
    if PROGRESS_TRACKER_HEADING not in zone_c_text:
        return f"'{PROGRESS_TRACKER_HEADING}' heading missing from Zone C"
    return None


def _zone_c_start_offset(text: str) -> int:
    """Return the character offset where Zone C begins (after the repo boundary box)."""
    lines = text.splitlines(keepends=True)
    marker_idx: int | None = None
    for idx, line in enumerate(lines):
        if REPO_BOUNDARY_MARKER in line:
            marker_idx = idx
    if marker_idx is None:
        return len(text)
    for idx in range(marker_idx + 1, len(lines)):
        if BOUNDARY_BOX_CHAR in lines[idx]:
            start = sum(len(lines[i]) for i in range(idx + 1))
            return start
    start = sum(len(lines[i]) for i in range(marker_idx + 1))
    return start


def render_block(block_type: str, block_id: str, data: dict) -> str:
    """Render a Zone C markdown block from validated input data."""
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


def main() -> int:  # noqa: C901 — single-function CLI entry point
    parser = argparse.ArgumentParser(
        description="Append a structured work block to CLAUDE.md Zone C",
    )
    parser.add_argument(
        "--type",
        choices=list(TYPE_HEADING_MAP),
        required=True,
        help="Block type: feature, bug-fix, or project",
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

    # --- Load and validate CLAUDE.md ---
    claude_md_path = args.project_root / "CLAUDE.md"
    try:
        original_text = claude_md_path.read_text(encoding="utf-8")
    except OSError as exc:
        _emit({"ok": False, "error": f"cannot read CLAUDE.md: {exc}"})
        return EXIT_STRUCTURE_INVALID

    original_hash = _sha256(original_text)

    struct_error = validate_structure(original_text)
    if struct_error:
        _emit({"ok": False, "error": struct_error})
        return EXIT_STRUCTURE_INVALID

    # --- Derive block ID and render ---
    block_id = data.get("id") or _slugify(data["title"])
    rendered = render_block(args.type, block_id, data)

    # --- Idempotency check ---
    existing_text, _ = find_existing_block(original_text, block_id)
    if existing_text is not None:
        if existing_text.strip() == rendered.strip():
            _emit({
                "ok": True,
                "result": "no-op",
                "heading": f"{TYPE_HEADING_MAP[args.type]}: {data['title']}",
                "block_id": block_id,
                "markers_ok": True,
                "progress_tracker_preserved": True,
            })
            return EXIT_OK
        _emit({
            "ok": False,
            "error": (
                f"block with id '{block_id}' already exists with different content; "
                "delete or revise the existing block manually"
            ),
        })
        return EXIT_CONFLICT

    # --- Compose new file ---
    new_text = original_text.rstrip("\n") + "\n\n" + rendered

    # --- Preview or apply ---
    logs_dir = args.project_root / ".claude" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    heading = f"{TYPE_HEADING_MAP[args.type]}: {data['title']}"

    if not args.apply:
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        preview_path = logs_dir / f"zone-c-preview-{timestamp}.md"
        preview_path.write_text(new_text, encoding="utf-8")
        _emit({
            "ok": True,
            "result": "preview",
            "heading": heading,
            "block_id": block_id,
            "preview_file": str(preview_path),
            "markers_ok": True,
            "progress_tracker_preserved": True,
        })
        return EXIT_OK

    # --- Atomic apply ---
    # Re-read to detect concurrent modification
    try:
        current_text = claude_md_path.read_text(encoding="utf-8")
    except OSError as exc:
        _emit({"ok": False, "error": f"cannot re-read CLAUDE.md: {exc}"})
        return EXIT_CONFLICT

    if _sha256(current_text) != original_hash:
        _emit({
            "ok": False,
            "error": "CLAUDE.md was modified concurrently; aborting",
        })
        return EXIT_CONFLICT

    # Write to temp file in same directory, validate, then replace
    target_dir = claude_md_path.parent
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=".claude-md-", suffix=".tmp", dir=str(target_dir),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        # Validate the temp file
        tmp_text = Path(tmp_path_str).read_text(encoding="utf-8")
        post_error = validate_structure(tmp_text)
        if post_error:
            os.unlink(tmp_path_str)
            _emit({"ok": False, "error": f"post-write validation failed: {post_error}"})
            return EXIT_STRUCTURE_INVALID
        os.replace(tmp_path_str, str(claude_md_path))
    except OSError as exc:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        _emit({"ok": False, "error": f"write failure: {exc}"})
        return EXIT_CONFLICT

    _emit({
        "ok": True,
        "result": "applied",
        "heading": heading,
        "block_id": block_id,
        "markers_ok": True,
        "progress_tracker_preserved": True,
    })
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
