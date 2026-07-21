#!/usr/bin/env python3
"""Inspect and compose compacted .agents/STATE.md working state.

The guard never moves research notes. ``compose`` writes a draft under
``.agents/logs/``; all other modes are read-only.
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
STATE_MD = PROJECT_ROOT / ".agents" / "STATE.md"
RESEARCH_DIR = PROJECT_ROOT / ".agents" / "docs" / "research"
ARCHIVE_DIR = RESEARCH_DIR / "archive"
STATE_HEADING = "# Agent State"
PROGRESS_TRACKER_HEADING = "## Progress Tracker"
CURRENT_BLOCK_RE = re.compile(r"^## Current (Project|Feature|Bug Fix)\b")
LEGACY_HEADINGS = (
    "## Work Evolution",
    "## Archive Index",
    "## Activity Log",
    "## Session Log",
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
EXIT_STRUCTURE_INVALID = 2
EXIT_PARSE_ERROR = 3


def _block_text(lines: list[str], heading_idx: int) -> str:
    collected = [lines[heading_idx]]
    for line in lines[heading_idx + 1 :]:
        if line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected).rstrip()


def collect_work_blocks(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    for index, line in enumerate(lines):
        match = CURRENT_BLOCK_RE.match(line.strip())
        if not match:
            continue
        text = _block_text(lines, index)
        date_match = DATE_RE.search(text)
        blocks.append(
            {
                "heading": line.strip(),
                "line": index + 1,
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


def collect_research_notes(state_text: str) -> list[dict]:
    if not RESEARCH_DIR.exists():
        return []
    lowered = state_text.lower()
    notes = []
    for path in sorted(RESEARCH_DIR.glob("*.md")):
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        notes.append(
            {
                "file": path.name,
                "mtime": mtime.strftime("%Y-%m-%d"),
                "active": path.stem.lower() in lowered,
            }
        )
    return notes


def build_report(lines: list[str]) -> dict:
    state_text = "\n".join(lines)
    structure = {
        "state_heading": sum(line.strip() == STATE_HEADING for line in lines),
        "progress_tracker": sum(
            line.strip() == PROGRESS_TRACKER_HEADING for line in lines
        ),
    }
    structure["ok"] = all(value == 1 for value in structure.values())
    blocks = collect_work_blocks(lines) if structure["ok"] else []
    notes = collect_research_notes(state_text) if structure["ok"] else []
    return {
        "structure": structure,
        "state_md": {"total_lines": len(lines)},
        "work_blocks": blocks,
        "legacy_sections": [
            heading for heading in LEGACY_HEADINGS if heading in state_text
        ],
        "research_notes": notes,
        "move_plan": [
            {
                "src": str(RESEARCH_DIR / note["file"]),
                "dst": str(ARCHIVE_DIR / note["file"]),
                "mode": "append" if (ARCHIVE_DIR / note["file"]).exists() else "create",
            }
            for note in notes
            if not note["active"]
        ],
    }


def compose_state(lines: list[str], blocks: list[dict]) -> tuple[str, list[str]]:
    first_work_index = next(
        (i for i, line in enumerate(lines) if CURRENT_BLOCK_RE.match(line.strip())),
        len(lines),
    )
    base = "\n".join(lines[:first_work_index]).rstrip()
    kept = [block for block in blocks if block["keep"]]
    kept_text = [_block_text(lines, block["line"] - 1) for block in kept]
    parts = [base, *kept_text]
    return "\n\n".join(part for part in parts if part).rstrip() + "\n", [
        block["heading"] for block in blocks if not block["keep"]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard .agents/STATE.md compaction")
    parser.add_argument(
        "--mode", choices=["check", "plan", "verify", "compose"], default="check"
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    state_md = args.project_root / ".agents" / "STATE.md"
    try:
        lines = state_md.read_text(encoding="utf-8").splitlines()
        report = build_report(lines)
    except OSError as exc:
        print(json.dumps({"error": f"cannot read {state_md}: {exc}"}))
        return EXIT_PARSE_ERROR

    if not report["structure"]["ok"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return EXIT_STRUCTURE_INVALID

    if args.mode == "compose":
        composed, pruned = compose_state(lines, report["work_blocks"])
        logs_dir = args.project_root / ".agents" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        composed_path = logs_dir / "composed-state.md"
        composed_path.write_text(composed, encoding="utf-8")
        report["composed_state"] = str(composed_path)
        report["blocks_pruned"] = pruned

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
