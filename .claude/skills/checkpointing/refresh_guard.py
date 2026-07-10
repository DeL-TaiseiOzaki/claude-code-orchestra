#!/usr/bin/env python3
"""Refresh guard: mechanical verification for the checkpointing Compact Phase.

Non-writing (dry-run only, except ``--mode compose`` which writes a draft file
under ``.claude/logs/``). Computes the deterministic parts of the compact:
boundary-marker verification, CLAUDE.md line accounting, Zone C work-block
inventory, legacy-section detection, research-note staleness, and an archive
move plan (computed, never executed). All LLM judgment (summarization, archive
decisions, approval gates) stays in SKILL.md.

Usage:
    python3 refresh_guard.py --mode check    # markers + line counts (abort gate)
    python3 refresh_guard.py --mode plan     # full inventory + dry-run move plan
    python3 refresh_guard.py --mode verify   # post-run marker/line re-check
    python3 refresh_guard.py --mode compose  # compose new Zone C body → draft file

Exit codes:
    0  normal
    2  boundary marker(s) missing (abort; caller must run ./scripts/update.sh)
    3  parse/IO failure (CLAUDE.md unreadable or unparseable)
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"
RESEARCH_DIR = PROJECT_ROOT / ".claude" / "docs" / "research"
ARCHIVE_DIR = RESEARCH_DIR / "archive"

TEMPLATE_BOUNDARY_MARKER = "@orchestra:template-boundary"
REPO_BOUNDARY_MARKER = "@orchestra:repo-boundary"
PROGRESS_TRACKER_HEADING = "## Progress Tracker"
BOUNDARY_BOX_CHAR = "━"  # heavy horizontal (━) used in marker boxes

# Zone C work blocks that the Compact Phase manages (keep only the latest each).
CURRENT_BLOCK_RE = re.compile(r"^## Current (Project|Feature|Bug Fix)\b")
# Obsolete running-history sections that should be removed if present.
LEGACY_HEADINGS = (
    "## Work Evolution",
    "## Archive Index",
    "## Activity Log",
    "## Session Log",
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
EXIT_MARKERS_MISSING = 2
EXIT_PARSE_ERROR = 3


def find_zone_c_start(lines: list[str]) -> int:
    """Return 0-based index of the first Zone C line (after the repo boundary box).

    Zone C begins after the closing box rule that follows the last
    @orchestra:repo-boundary marker line. Returns len(lines) if none found.
    """
    marker_idx = None
    for idx, line in enumerate(lines):
        if REPO_BOUNDARY_MARKER in line:
            marker_idx = idx
    if marker_idx is None:
        return len(lines)
    # Skip forward past the box's closing rule line (the ━ line after marker).
    for idx in range(marker_idx + 1, len(lines)):
        if BOUNDARY_BOX_CHAR in lines[idx]:
            return idx + 1
    return marker_idx + 1


def collect_zone_c_blocks(lines: list[str], zone_c_start: int) -> list[dict]:
    """Inventory `## Current Project|Feature|Bug Fix` blocks in Zone C.

    keep=True marks the latest (last in file order) block of each category;
    older instances of the same category get keep=False.
    """
    blocks: list[dict] = []
    for offset, line in enumerate(lines[zone_c_start:]):
        match = CURRENT_BLOCK_RE.match(line.strip())
        if not match:
            continue
        line_no = zone_c_start + offset + 1  # 1-based
        block_text = _block_text(lines, zone_c_start + offset)
        date_match = DATE_RE.search(block_text)
        blocks.append(
            {
                "heading": line.strip(),
                "line": line_no,
                "date": date_match.group(0) if date_match else None,
                "category": match.group(1),
                "keep": True,  # provisional; demoted below for older duplicates
            }
        )

    # Demote all but the last block of each category.
    last_of_category: dict[str, int] = {}
    for i, block in enumerate(blocks):
        last_of_category[block["category"]] = i
    keep_indices = set(last_of_category.values())
    for i, block in enumerate(blocks):
        block["keep"] = i in keep_indices
        del block["category"]
    return blocks


def _block_text(lines: list[str], heading_idx: int) -> str:
    """Return the text of a `## ` block starting at heading_idx up to the next `## `."""
    collected = [lines[heading_idx]]
    for line in lines[heading_idx + 1 :]:
        if line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected)


def collect_legacy_sections(lines: list[str], zone_c_start: int) -> list[str]:
    """Return legacy running-history headings present in Zone C."""
    zone_c = {line.strip() for line in lines[zone_c_start:]}
    return [heading for heading in LEGACY_HEADINGS if heading in zone_c]


def collect_research_notes(zone_c_text: str) -> list[dict]:
    """Inventory research notes; active=True when the note is still referenced.

    A note is considered active when its filename stem appears anywhere in the
    Zone C text (i.e. its feature still has a live work block).
    """
    if not RESEARCH_DIR.exists():
        return []
    notes: list[dict] = []
    zone_c_lower = zone_c_text.lower()
    for path in sorted(RESEARCH_DIR.glob("*.md")):
        stem = path.stem
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        notes.append(
            {
                "file": path.name,
                "mtime": mtime.strftime("%Y-%m-%d"),
                "active": stem.lower() in zone_c_lower,
            }
        )
    return notes


def build_move_plan(research_notes: list[dict]) -> list[dict]:
    """Compute (never execute) the archive move plan for inactive notes."""
    plan: list[dict] = []
    for note in research_notes:
        if note["active"]:
            continue
        src = RESEARCH_DIR / note["file"]
        dst = ARCHIVE_DIR / note["file"]
        plan.append(
            {
                "src": str(src),
                "dst": str(dst),
                "mode": "append" if dst.exists() else "create",
            }
        )
    return plan


def extract_progress_tracker_block(lines: list[str], zone_c_start: int) -> str:
    """Return the full text of the ``## Progress Tracker`` block in Zone C.

    Includes the heading line and all body lines up to (but not including) the
    next ``## `` heading or end of file.
    """
    for idx in range(zone_c_start, len(lines)):
        if lines[idx].strip() == PROGRESS_TRACKER_HEADING:
            return _block_text(lines, idx)
    return ""


def extract_kept_block_texts(
    lines: list[str],
    zone_c_blocks: list[dict],
) -> list[str]:
    """Return the full markdown text for each ``keep:true`` block, in file order.

    Each text spans from the ``## Current ...`` heading through to (but not
    including) the next ``## `` heading or EOF.
    """
    kept: list[str] = []
    for block in zone_c_blocks:
        if not block["keep"]:
            continue
        # block["line"] is 1-based
        heading_idx = block["line"] - 1
        kept.append(_block_text(lines, heading_idx))
    return kept


def compose_zone_c(
    lines: list[str],
    zone_c_start: int,
    zone_c_blocks: list[dict],
) -> tuple[str, list[str], list[str]]:
    """Compose a new Zone C body from the Progress Tracker block and kept blocks.

    Returns (composed_body, blocks_kept_headings, blocks_pruned_headings).
    """
    progress_block = extract_progress_tracker_block(lines, zone_c_start)
    kept_texts = extract_kept_block_texts(lines, zone_c_blocks)

    parts: list[str] = []
    if progress_block:
        parts.append(progress_block)
    for text in kept_texts:
        parts.append(text)

    composed = "\n\n".join(parts) + "\n" if parts else ""

    blocks_kept = [b["heading"] for b in zone_c_blocks if b["keep"]]
    blocks_pruned = [b["heading"] for b in zone_c_blocks if not b["keep"]]
    return composed, blocks_kept, blocks_pruned


def build_report(lines: list[str]) -> dict:
    """Assemble the full JSON report from CLAUDE.md lines."""
    template_count = sum(1 for line in lines if TEMPLATE_BOUNDARY_MARKER in line)
    repo_count = sum(1 for line in lines if REPO_BOUNDARY_MARKER in line)
    markers = {
        "template_boundary": template_count,
        "repo_boundary": repo_count,
        "ok": template_count >= 1 and repo_count >= 1,
    }

    zone_c_start = find_zone_c_start(lines)
    zone_c_lines_list = lines[zone_c_start:]
    zone_c_text = "\n".join(zone_c_lines_list)

    claude_md = {
        "total_lines": len(lines),
        "zone_c_start": zone_c_start + 1 if markers["ok"] else None,
        "zone_c_lines": len(zone_c_lines_list) if markers["ok"] else 0,
    }
    progress_present = PROGRESS_TRACKER_HEADING in zone_c_text

    if not markers["ok"]:
        return {
            "markers": markers,
            "claude_md": claude_md,
            "progress_tracker_present": progress_present,
            "zone_c_blocks": [],
            "legacy_sections": [],
            "research_notes": [],
            "move_plan": [],
        }

    zone_c_blocks = collect_zone_c_blocks(lines, zone_c_start)
    legacy_sections = collect_legacy_sections(lines, zone_c_start)
    research_notes = collect_research_notes(zone_c_text)
    move_plan = build_move_plan(research_notes)
    return {
        "markers": markers,
        "claude_md": claude_md,
        "progress_tracker_present": progress_present,
        "zone_c_blocks": zone_c_blocks,
        "legacy_sections": legacy_sections,
        "research_notes": research_notes,
        "move_plan": move_plan,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mechanical guard for the checkpointing Compact Phase (dry-run, non-writing)",
    )
    parser.add_argument(
        "--mode",
        choices=["check", "plan", "verify", "compose"],
        default="check",
        help="check: abort gate; plan: full move plan; verify: post-run re-check; compose: draft new Zone C body",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    args = parser.parse_args()

    claude_md = args.project_root / "CLAUDE.md"
    try:
        text = claude_md.read_text(encoding="utf-8")
    except OSError:
        json.dump({"error": f"cannot read {claude_md}"}, sys.stdout)
        print()
        return EXIT_PARSE_ERROR

    try:
        lines = text.splitlines()
        report = build_report(lines)
    except (ValueError, OSError) as exc:
        json.dump({"error": f"parse failure: {exc}"}, sys.stdout)
        print()
        return EXIT_PARSE_ERROR

    if not report["markers"]["ok"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return EXIT_MARKERS_MISSING

    if args.mode == "compose":
        zone_c_start = find_zone_c_start(lines)
        composed_body, blocks_kept, blocks_pruned = compose_zone_c(
            lines,
            zone_c_start,
            report["zone_c_blocks"],
        )
        logs_dir = args.project_root / ".claude" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        composed_path = logs_dir / "composed-zone-c.md"
        composed_path.write_text(composed_body, encoding="utf-8")

        compose_report = {
            **report,
            "composed_zone_c": str(composed_path),
            "blocks_kept": blocks_kept,
            "blocks_pruned": blocks_pruned,
        }
        print(json.dumps(compose_report, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
