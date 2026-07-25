#!/usr/bin/env python3
"""Assemble, stamp, and validate root ``GUIDE.md`` from agent-written prose.

This script owns the *mechanics* of `/catchup` Phase 3 — the date stamp, the
section order and fixed numbering, the omit-don't-placeholder rule, the line
count, and the guarded write — and none of the judgment. It **never generates
narrative**: the thematic grouping of commits, the ranking of design decisions,
and the choice of what a returning contributor needs are Phase 2 synthesis and
arrive here as markdown bodies in ``--input``.

``GUIDE.md`` is a tracked file at the repository root, so the write follows the
Writer Safety Contract: dry-run by default, ``--apply`` to write, atomic
``os.replace``, a content-hash concurrent-modification guard, and validation of
the composed document (``validate_doc.py --contract guide``) before replacing.

Section numbers are part of the section names, exactly as
``references/guide-template.md`` declares them and ``validate_doc.py``'s
``guide`` contract requires them. Omitting an optional section never renumbers
the rest: section 5 is "5. Capabilities" whether or not section 4 is present.

Input JSON: ``{"<section_id>": "<markdown body>"}``. Ids and their headings:

    what_is_this_project  1. What is this project?          (required)
    current_state         2. Current State                  (optional)
    recent_work           3. Recent Work (last 30 days)     (required)
    architecture          4. Architecture & Key Decisions   (optional)
    capabilities          5. Capabilities                   (required)
    project_rules         6. Project Rules                  (optional)
    resume_work           7. How to Resume Work             (required)
    recent_sessions       8. Recent Sessions                (optional)

Usage:
    python3 write_guide.py --input body.json
    python3 write_guide.py --input body.json --apply
    python3 write_guide.py --input body.json --apply --now 2026-07-25T09:00:00+00:00

Exit codes:
    0  preview written, or GUIDE.md applied
    1  bad args, unreadable/malformed --input, or an unparseable --now
    2  unknown section id, a missing required section, a residual
       ``{placeholder}`` token, or a composed document the ``guide`` contract
       rejects
    3  write failure or concurrent modification of GUIDE.md
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
VALIDATE_DOC = (
    PROJECT_ROOT / ".agents" / "skills" / "_shared" / "validate_doc.py"
).resolve()

TITLE = "# Project Guide"
SOURCES_FOOTER = (
    "_Sources: git log, .agents/STATE.md, .agents/rules/, .agents/skills/, "
    ".agents/docs/, .agents/checkpoints/, .agents/logs/._"
)
VALIDATOR_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class GuideSection:
    """One template section: its input id, its numbered heading, and necessity."""

    key: str
    heading: str
    required: bool


# Order and numbering come verbatim from references/guide-template.md. The four
# required sections are exactly validate_doc.py's `guide` contract.
SECTIONS: tuple[GuideSection, ...] = (
    GuideSection("what_is_this_project", "1. What is this project?", True),
    GuideSection("current_state", "2. Current State", False),
    GuideSection("recent_work", "3. Recent Work (last 30 days)", True),
    GuideSection("architecture", "4. Architecture & Key Decisions", False),
    GuideSection("capabilities", "5. Capabilities", True),
    GuideSection("project_rules", "6. Project Rules", False),
    GuideSection("resume_work", "7. How to Resume Work", True),
    GuideSection("recent_sessions", "8. Recent Sessions", False),
)
SECTION_KEYS = tuple(section.key for section in SECTIONS)

# A residual template token such as `{branch name}` or `{one sentence from
# README}`. Only ASCII-letter-initial single-line braces count, and fenced code
# blocks are exempt, so a JSON or f-string example in the prose is not a
# false positive.
PLACEHOLDER_RE = re.compile(r"\{[A-Za-z][^{}\n]{0,79}\}")
FENCE_RE = re.compile(r"^```")

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_CONTRACT_VIOLATION = 2
EXIT_WRITE_FAILURE = 3


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so an argparse-level failure never masquerades as this
    tool's exit code 2, which means the assembled GUIDE.md is unusable."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message, "artifacts": []})
        sys.exit(EXIT_BAD_INPUT)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# --- composition -------------------------------------------------------------


def validate_input(data: object) -> str | None:
    """Return an error message if *data* violates the input schema, else None."""
    if not isinstance(data, dict):
        return "input must be a JSON object of {section_id: markdown}"
    unknown = sorted(set(data) - set(SECTION_KEYS))
    if unknown:
        return (
            f"unknown section id(s): {', '.join(unknown)}; "
            f"known ids: {', '.join(SECTION_KEYS)}"
        )
    for key, value in data.items():
        if not isinstance(value, str):
            return f"section '{key}' must be a markdown string"
    missing = [
        section.key
        for section in SECTIONS
        if section.required and not (data.get(section.key) or "").strip()
    ]
    if missing:
        return (
            f"required section(s) missing or empty: {', '.join(missing)}; "
            "the guide contract requires all four"
        )
    return None


def find_placeholders(text: str) -> list[str]:
    """Residual ``{placeholder}`` tokens outside fenced code blocks."""
    found: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        found.extend(PLACEHOLDER_RE.findall(line))
    return found


def compose_guide(data: dict, now: datetime) -> tuple[str, list[str], list[str]]:
    """Return (guide_text, sections_written, sections_omitted)."""
    lines: list[str] = [
        TITLE,
        "",
        f"_Generated by `/catchup` on {now.strftime('%Y-%m-%d')}_",
    ]
    written: list[str] = []
    omitted: list[str] = []
    for section in SECTIONS:
        body = (data.get(section.key) or "").strip()
        if not body:
            omitted.append(section.key)
            continue
        lines.extend(["", f"## {section.heading}", "", body])
        written.append(section.key)
    lines.extend(["", "---", "", SOURCES_FOOTER])
    return "\n".join(lines).rstrip("\n") + "\n", written, omitted


def validate_guide_document(text: str, project_root: Path) -> str | None:
    """Validate the composed document against validate_doc.py's ``guide``."""
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", encoding="utf-8", delete=False
        ) as handle:
            handle.write(text)
            probe = Path(handle.name)
    except OSError as exc:
        return f"cannot stage GUIDE.md for validation: {exc}"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_DOC),
                "--contract",
                "guide",
                "--file",
                str(probe),
                "--project-root",
                str(project_root),
            ],
            capture_output=True,
            text=True,
            timeout=VALIDATOR_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"cannot run validate_doc.py: {exc}"
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    if result.returncode == 0:
        return None
    return (
        "composed GUIDE.md violates the 'guide' contract: "
        f"{result.stdout.strip()[:300]}"
    )


# --- writing -----------------------------------------------------------------


def write_preview(path: Path, text: str) -> str | None:
    """Write the preview artifact. Returns an error message or None."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"cannot write preview {path}: {exc}"
    return None


def apply_atomically(
    path: Path, new_text: str, original_text: str | None, project_root: Path
) -> tuple[str | None, int]:
    """Replace *path* with *new_text* under the Writer Safety Contract."""
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else None
    except (OSError, UnicodeDecodeError) as exc:
        return f"cannot re-read {path}: {exc}", EXIT_WRITE_FAILURE

    if (current is None) != (original_text is None) or (
        current is not None
        and original_text is not None
        and _sha256(current) != _sha256(original_text)
    ):
        return f"{path.name} was modified concurrently; aborting", EXIT_WRITE_FAILURE

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".GUIDE.md-", suffix=".tmp", dir=str(path.parent)
        )
    except OSError as exc:
        return f"write failure: {exc}", EXIT_WRITE_FAILURE

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_text)
        written = Path(tmp_name).read_text(encoding="utf-8")
        error = validate_guide_document(written, project_root)
        if error:
            os.unlink(tmp_name)
            return f"post-write validation failed: {error}", EXIT_CONTRACT_VIOLATION
        os.replace(tmp_name, str(path))
    except OSError as exc:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        return f"write failure: {exc}", EXIT_WRITE_FAILURE
    return None, EXIT_OK


# --- CLI ---------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Assemble root GUIDE.md from collected state plus agent prose",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="JSON file mapping section ids to markdown bodies",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write GUIDE.md; without this flag the script only previews",
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


def main() -> int:
    args = _build_parser().parse_args()
    root = args.project_root

    try:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(tz=UTC)
    except ValueError as exc:
        _emit({"ok": False, "error": f"cannot parse '--now': {exc}", "artifacts": []})
        return EXIT_BAD_INPUT

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error": f"cannot read --input: {exc}", "artifacts": []})
        return EXIT_BAD_INPUT

    schema_error = validate_input(data)
    if schema_error:
        code = (
            EXIT_BAD_INPUT
            if schema_error.startswith(("input must be", "section '"))
            else EXIT_CONTRACT_VIOLATION
        )
        _emit({"ok": False, "error": schema_error, "artifacts": []})
        return code

    guide_text, written, omitted = compose_guide(data, now)
    residual = find_placeholders(guide_text)
    if residual:
        _emit(
            {
                "ok": False,
                "error": (
                    "residual placeholder token(s) survived synthesis; fill them in "
                    "or omit the section: " + ", ".join(sorted(set(residual)))
                ),
                "residual_placeholders": sorted(set(residual)),
                "artifacts": [],
            }
        )
        return EXIT_CONTRACT_VIOLATION

    contract_error = validate_guide_document(guide_text, root)
    if contract_error:
        _emit({"ok": False, "error": contract_error, "artifacts": []})
        return EXIT_CONTRACT_VIOLATION

    guide_path = root / "GUIDE.md"
    try:
        original = (
            guide_path.read_text(encoding="utf-8") if guide_path.exists() else None
        )
    except (OSError, UnicodeDecodeError) as exc:
        _emit({"ok": False, "error": f"cannot read GUIDE.md: {exc}", "artifacts": []})
        return EXIT_BAD_INPUT

    payload: dict = {
        "ok": True,
        "guide_path": _rel(guide_path, root),
        "sections_written": written,
        "sections_omitted": omitted,
        "line_count": len(guide_text.splitlines()),
        "residual_placeholders": [],
        "applied": False,
        "preview_path": None,
        "artifacts": [],
    }

    if not args.apply:
        stamp = now.strftime("%Y%m%d-%H%M%S")
        preview = root / ".agents" / "logs" / f"guide-preview-{stamp}.md"
        error = write_preview(preview, guide_text)
        if error:
            _emit({"ok": False, "error": error, "artifacts": []})
            return EXIT_WRITE_FAILURE
        payload["result"] = "preview"
        payload["preview_path"] = _rel(preview, root)
        payload["artifacts"] = [_rel(preview, root)]
        _emit(payload)
        return EXIT_OK

    error, code = apply_atomically(guide_path, guide_text, original, root)
    if error:
        _emit({"ok": False, "error": error, "artifacts": []})
        return code

    payload["result"] = "applied"
    payload["applied"] = True
    payload["artifacts"] = [_rel(guide_path, root)]
    _emit(payload)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
