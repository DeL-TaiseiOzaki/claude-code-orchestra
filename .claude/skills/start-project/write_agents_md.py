#!/usr/bin/env python3
"""Convert the root ``AGENTS.md`` into the project's own instructions.

``/start-project`` runs this once per project. The shipped ``AGENTS.md`` is a
skeleton; this writer replaces it with a document built from typed project
facts, carrying the ``## Agent Roles`` and ``## Orchestra References`` sections
forward verbatim from the file it converts, so the role split between the main
agent and delegated executors survives the conversion. Template updates never
rewrite the converted file (``scripts/update.sh`` replaces ``AGENTS.md`` only
while it is byte-identical to a known shipped skeleton).

The module also owns the ``AGENTS.md`` model the other start-project helper
reads: the required headings, the size caps, the skeleton marker, the state
classification, and the instruction files that stop Claude Code from loading
``AGENTS.md`` (``detect_stack.py`` imports them).

Input JSON (``--input``), unknown keys rejected::

    {"project_name": "Acme API",
     "identity": "One paragraph: what the repository is and who it serves.",
     "layout": ["`src/` - application code"],
     "commands": [{"purpose": "Test", "command": "uv run pytest"}],
     "conventions": ["Keep public APIs backwards compatible."],
     "languages": {"user": "Japanese", "code": "English"}}

Only ``project_name`` and ``identity`` are required. ``scripts/install.sh`` and
``scripts/update.sh`` record backups of removed ``CLAUDE.md``-family files in
the ``## Pending Instruction Merge`` section of ``.claude/STATE.md``; the
payload lists them under ``pending_merge`` with ``pending_merge_sha256``, and
``--resolve-pending-merge <that sha256>`` removes the section in the same
``--apply`` once their content was merged into ``conventions`` (or deliberately
dropped) with the user's approval. The hash pins the entries that were
reviewed: a section that gained or lost an entry since the preview is refused,
so a stale call cannot erase a newer backup record.

Writer Safety Contract: dry-run by default (the preview is written under
``.claude/logs/``), ``--apply`` replaces atomically after validating the
composed document, ``--expect-hash`` pins the ``AGENTS.md`` content that was
reviewed, and a file that changed while the run was composing is never
overwritten.

Usage:
    python3 write_agents_md.py --input .claude/logs/start-project-agents-input.json
    python3 write_agents_md.py --input .claude/logs/start-project-agents-input.json \
        --apply --expect-hash <sha256_before from the preview>
    python3 write_agents_md.py --input ... --apply \
        --resolve-pending-merge <pending_merge_sha256 from the preview>

Exit codes:
    0  ok (preview, applied, or no-op)
    1  bad arguments, or an unreadable or invalid input file
    2  contract violation: AGENTS.md is missing or has no Agent Roles /
       Orchestra References to carry forward, an owned CLAUDE.md-family file
       shadows it, or the composed document fails validation
    3  write failure, or AGENTS.md / STATE.md changed (--expect-hash or
       --resolve-pending-merge hash mismatch, or a concurrent modification)
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_CONTRACT = 2
EXIT_FAILED = 3

REQUIRED_HEADINGS = (
    "## Project",
    "## Commands",
    "## Conventions",
    "## Agent Roles",
    "## Orchestra References",
)
CARRIED_SECTIONS = ("## Agent Roles", "## Orchestra References")
MAX_LINES = 150
MAX_BYTES = 32 * 1024
SKELETON_MARKER = "_Not initialized — run `/start-project`"
LEGACY_MARKER = "@orchestra:"
ROLE_MARKERS = ("executor_contract.md", "ORCHESTRA_ROLE")
REFERENCE_MARKERS = (".claude/rules/orchestration.md", ".claude/rules/cli-contract.md")
# Any of these in the project root or a parent stops Claude Code (>= 2.1.277)
# from loading AGENTS.md. A file whose only content is `@AGENTS.md` imports it
# instead, which is the documented manual fallback, not a shadow.
SHADOW_NAMES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")
SHIM_CONTENT = "@AGENTS.md"
PENDING_HEADING = "## Pending Instruction Merge"
STATE_REQUIRED = ("## Main Agent", "## Progress Tracker")
PREVIEW_NAME = "start-project-agents-preview.md"

INTRO = (
    "Root instructions that every agent runtime loads automatically (Claude Code,\n"
    "Codex, Antigravity, and other CLIs that read `AGENTS.md`). This file belongs\n"
    "to the project; template updates never rewrite it. Template policy lives\n"
    "under `.claude/` and is listed in Orchestra References."
)
DEFAULT_LANGUAGES = {"user": "Japanese", "code": "English"}
INPUT_KEYS = {
    "project_name",
    "identity",
    "layout",
    "commands",
    "conventions",
    "languages",
}
MAX_NAME_CHARS = 100
MAX_TEXT_CHARS = 2000
MAX_ITEM_CHARS = 500


class InputError(Exception):
    """The typed input is invalid (exit 1)."""


class ConcurrentModification(Exception):
    """A target file changed between load and replace (exit 3)."""


# --- AGENTS.md model ---------------------------------------------------------


def split_sections(text: str) -> dict[str, str]:
    """Map each ``## `` heading line to its body (up to the next ``## ``)."""
    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(body).strip("\n")
            current, body = line.rstrip(), []
        elif current is not None:
            body.append(line)
    if current is not None:
        sections[current] = "\n".join(body).strip("\n")
    return sections


def classify_agents_md(text: str | None) -> str:
    """``missing`` | ``skeleton`` | ``converted`` | ``unrecognized``."""
    if text is None:
        return "missing"
    sections = split_sections(text)
    if not all(heading in sections for heading in CARRIED_SECTIONS):
        return "unrecognized"
    return "skeleton" if SKELETON_MARKER in text else "converted"


def validation_errors(text: str, *, converted: bool) -> list[str]:
    """Contract violations of an AGENTS.md document; empty when valid."""
    errors: list[str] = []
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        errors.append("the first line must be a '# ' title")
    for heading in REQUIRED_HEADINGS:
        count = sum(1 for line in lines if line.rstrip() == heading)
        if count != 1:
            errors.append(f"'{heading}' must appear exactly once (found {count})")
    if len(lines) > MAX_LINES:
        errors.append(f"{len(lines)} lines exceeds the {MAX_LINES}-line cap")
    if len(text.encode("utf-8")) >= MAX_BYTES:
        errors.append(f"size must stay under {MAX_BYTES} bytes")
    if LEGACY_MARKER in text:
        errors.append(f"legacy boundary marker '{LEGACY_MARKER}' found")
    if converted and SKELETON_MARKER in text:
        errors.append("the skeleton placeholder is still present")
    sections = split_sections(text)
    roles = sections.get("## Agent Roles", "")
    refs = sections.get("## Orchestra References", "")
    errors.extend(
        f"'## Agent Roles' must mention {marker}"
        for marker in ROLE_MARKERS
        if marker not in roles
    )
    errors.extend(
        f"'## Orchestra References' must mention {marker}"
        for marker in REFERENCE_MARKERS
        if marker not in refs
    )
    return errors


def is_shim(path: Path) -> bool:
    """True when *path* only imports AGENTS.md (the manual fallback)."""
    try:
        return path.read_text(encoding="utf-8").strip() == SHIM_CONTENT
    except (OSError, UnicodeDecodeError):
        return False


def find_instruction_shadows(root: Path) -> dict[str, list[str]]:
    """Report CLAUDE.md-family files that would stop AGENTS.md from loading.

    ``owned`` are inside *root* (install and update remove them), ``shim``
    only import AGENTS.md, and ``ancestor`` sit in a parent directory, which
    this project cannot fix. The user-level ``~/.claude/CLAUDE.md`` is a
    separate memory mechanism and is not reported.
    """
    report: dict[str, list[str]] = {"owned": [], "shim": [], "ancestor": []}
    for name in SHADOW_NAMES:
        path = root / name
        if path.is_file() or path.is_symlink():
            report["shim" if is_shim(path) else "owned"].append(name)
    user_memory = Path.home() / ".claude" / "CLAUDE.md"
    for parent in root.resolve().parents:
        for name in SHADOW_NAMES:
            path = parent / name
            if path == user_memory or not path.is_file() or is_shim(path):
                continue
            report["ancestor"].append(str(path))
    return report


# --- input -------------------------------------------------------------------


def _text(value: object, field: str, limit: int, *, single_line: bool) -> str:
    """Validate one string field: non-empty, bounded, and heading-free."""
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"'{field}' must be a non-empty string")
    value = value.strip()
    if len(value) > limit:
        raise InputError(f"'{field}' exceeds {limit} characters")
    if single_line and "\n" in value:
        raise InputError(f"'{field}' must be a single line")
    if any(line.lstrip().startswith("#") for line in value.splitlines()):
        raise InputError(f"'{field}' must not contain a markdown heading")
    if LEGACY_MARKER in value or SKELETON_MARKER in value:
        raise InputError(f"'{field}' contains a reserved marker")
    return value


def _string_list(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InputError(f"'{field}' must be a list of strings")
    return [
        _text(item, f"{field}[{i}]", MAX_ITEM_CHARS, single_line=True)
        for i, item in enumerate(value)
    ]


def _commands(value: object) -> list[tuple[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InputError("'commands' must be a list of {purpose, command} objects")
    commands: list[tuple[str, str]] = []
    for i, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"purpose", "command"}:
            raise InputError(f"'commands[{i}]' must have exactly purpose and command")
        purpose = _text(
            item["purpose"], f"commands[{i}].purpose", MAX_ITEM_CHARS, single_line=True
        )
        command = _text(
            item["command"], f"commands[{i}].command", MAX_ITEM_CHARS, single_line=True
        )
        if "`" in command:
            raise InputError(f"'commands[{i}].command' must not contain a backtick")
        commands.append((purpose, command))
    return commands


def _languages(value: object) -> dict[str, str]:
    if value is None:
        return dict(DEFAULT_LANGUAGES)
    if not isinstance(value, dict) or not set(value) <= set(DEFAULT_LANGUAGES):
        raise InputError("'languages' must be an object with 'user' and/or 'code'")
    return {
        key: _text(value.get(key, default), f"languages.{key}", 40, single_line=True)
        for key, default in DEFAULT_LANGUAGES.items()
    }


def parse_input(raw: object) -> dict:
    """Validate the typed input; raise ``InputError``."""
    if not isinstance(raw, dict):
        raise InputError("input must be a JSON object")
    unknown = sorted(set(raw) - INPUT_KEYS)
    if unknown:
        raise InputError(f"unknown input keys: {unknown}")
    return {
        "project_name": _text(
            raw.get("project_name"), "project_name", MAX_NAME_CHARS, single_line=True
        ),
        "identity": _text(
            raw.get("identity"), "identity", MAX_TEXT_CHARS, single_line=False
        ),
        "layout": _string_list(raw.get("layout"), "layout"),
        "commands": _commands(raw.get("commands")),
        "conventions": _string_list(raw.get("conventions"), "conventions"),
        "languages": _languages(raw.get("languages")),
    }


# --- composition -------------------------------------------------------------


def compose(facts: dict, carried: dict[str, str]) -> str:
    """Render the converted AGENTS.md."""
    parts = [f"# {facts['project_name']} — Agent Instructions", INTRO]
    project = [facts["identity"]]
    if facts["layout"]:
        project.append("Layout:\n\n" + "\n".join(f"- {i}" for i in facts["layout"]))
    parts.append("## Project\n\n" + "\n\n".join(project))
    commands = [f"- {purpose}: `{command}`" for purpose, command in facts["commands"]]
    parts.append(
        "## Commands\n\n"
        + ("\n".join(commands) or "_No commands are declared by the repository._")
    )
    languages = facts["languages"]
    conventions = [
        "- Think and reason in English.",
        "- Write code, identifiers, comments, commands, and technical documents "
        f"in {languages['code']}.",
        f"- Communicate with the user in {languages['user']}.",
        *(f"- {item}" for item in facts["conventions"]),
    ]
    parts.append("## Conventions\n\n" + "\n".join(conventions))
    parts.extend(f"{heading}\n\n{carried[heading]}" for heading in CARRIED_SECTIONS)
    return "\n\n".join(parts) + "\n"


def remove_pending_section(state: str) -> str:
    """Drop the ``## Pending Instruction Merge`` section from STATE.md text."""
    lines = state.splitlines(keepends=True)
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.rstrip() == PENDING_HEADING:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "".join(out))


# --- io ----------------------------------------------------------------------


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


class JsonArgumentParser(argparse.ArgumentParser):
    """Report usage errors as one JSON object on stdout with exit 1."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message, "artifacts": []})
        sys.exit(EXIT_BAD_ARGS)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _atomic_write(path: Path, text: str, expected_before: str | None) -> None:
    """Write via a same-directory temp file; refuse if *path* changed meanwhile."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if tmp.read_text(encoding="utf-8") != text:
            raise OSError(f"temporary file for {path.name} did not verify")
        if expected_before is not None and _read(path) != expected_before:
            raise ConcurrentModification(f"{path.name} changed during the run")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _pending_entries(state: str | None) -> list[str]:
    if state is None:
        return []
    body = split_sections(state).get(PENDING_HEADING, "")
    return [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]


def _pending_sha(state: str | None) -> str | None:
    """sha256 of the pending-merge section body, or None when there is none."""
    if state is None or PENDING_HEADING not in split_sections(state):
        return None
    return _sha(split_sections(state)[PENDING_HEADING])


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Convert root AGENTS.md into the project's own instructions.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Typed JSON input")
    parser.add_argument(
        "--apply", action="store_true", help="Replace AGENTS.md (default: preview)"
    )
    parser.add_argument(
        "--expect-hash",
        default=None,
        help="sha256 of the AGENTS.md content that was reviewed",
    )
    parser.add_argument(
        "--resolve-pending-merge",
        default=None,
        metavar="SHA256",
        help="With --apply, remove '## Pending Instruction Merge' from STATE.md; "
        "the value is pending_merge_sha256 from the reviewed preview",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    return parser


def run(args: argparse.Namespace) -> tuple[dict, int]:  # noqa: C901 — linear CLI flow
    root: Path = args.project_root
    if not root.is_dir():
        return {"error": f"--project-root is not a directory: {root}"}, EXIT_BAD_ARGS
    if args.resolve_pending_merge is not None and not args.apply:
        return {"error": "--resolve-pending-merge requires --apply"}, EXIT_BAD_ARGS
    input_path = args.input if args.input.is_absolute() else root / args.input
    try:
        facts = parse_input(json.loads(input_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"error": f"cannot read input: {exc}"}, EXIT_BAD_ARGS
    except InputError as exc:
        return {"error": str(exc)}, EXIT_BAD_ARGS

    agents_path = root / "AGENTS.md"
    state_path = root / ".claude" / "STATE.md"
    try:
        current = _read(agents_path)
        state = _read(state_path)
    except (OSError, UnicodeDecodeError) as exc:
        return {"error": f"cannot read project documents: {exc}"}, EXIT_BAD_ARGS
    state_before = classify_agents_md(current)
    shadows = find_instruction_shadows(root)
    report: dict = {
        "agents_md_state_before": state_before,
        "instruction_shadowing": shadows,
        "pending_merge": _pending_entries(state),
        "pending_merge_sha256": _pending_sha(state),
    }
    if current is None or state_before == "unrecognized":
        report["error"] = (
            "AGENTS.md has no '## Agent Roles' and '## Orchestra References' to "
            "carry forward; reinstall the Orchestra skeleton first"
            if current is not None
            else "AGENTS.md does not exist; reinstall the Orchestra skeleton first"
        )
        return report, EXIT_CONTRACT
    if shadows["owned"]:
        report["error"] = (
            "Claude Code will not load AGENTS.md while these exist: "
            + ", ".join(shadows["owned"])
            + " (back them up and remove them, or re-run scripts/update.sh)"
        )
        return report, EXIT_CONTRACT
    sha_before = _sha(current)
    report["sha256_before"] = sha_before
    if args.expect_hash is not None and args.expect_hash != sha_before:
        report["error"] = "AGENTS.md does not match --expect-hash"
        return report, EXIT_FAILED

    sections = split_sections(current)
    composed = compose(facts, {h: sections[h] for h in CARRIED_SECTIONS})
    errors = validation_errors(composed, converted=True)
    report.update(
        {
            "sha256_after": _sha(composed),
            "lines": len(composed.splitlines()),
            "bytes": len(composed.encode("utf-8")),
            "validation_errors": errors,
        }
    )
    if errors:
        report["error"] = "composed AGENTS.md fails validation"
        return report, EXIT_CONTRACT

    if not args.apply:
        preview = root / ".claude" / "logs" / PREVIEW_NAME
        try:
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_text(composed, encoding="utf-8")
        except OSError as exc:
            report["error"] = f"cannot write preview: {exc}"
            return report, EXIT_FAILED
        report.update({"result": "preview", "preview_file": _relative(preview, root)})
        report["artifacts"] = [_relative(preview, root)]
        return report, EXIT_OK

    artifacts: list[str] = []
    new_state = state
    if args.resolve_pending_merge is not None:
        if args.resolve_pending_merge != report["pending_merge_sha256"]:
            report["error"] = (
                "## Pending Instruction Merge does not match --resolve-pending-merge "
                "(it changed since the preview, or there is none); re-run the preview"
            )
            return report, EXIT_FAILED
        new_state = remove_pending_section(state)
        state_lines = [line.rstrip() for line in new_state.splitlines()]
        missing = [h for h in STATE_REQUIRED if state_lines.count(h) != 1]
        if missing:
            report["error"] = f"STATE.md would lose or duplicate {missing}"
            return report, EXIT_CONTRACT
    try:
        if composed != current:
            _atomic_write(agents_path, composed, current)
            artifacts.append("AGENTS.md")
        if new_state is not None and new_state != state:
            _atomic_write(state_path, new_state, state)
            artifacts.append(".claude/STATE.md")
    except ConcurrentModification as exc:
        report.update({"error": str(exc), "artifacts": artifacts})
        return report, EXIT_FAILED
    except OSError as exc:
        report.update({"error": f"write failed: {exc}", "artifacts": artifacts})
        return report, EXIT_FAILED

    written = _read(agents_path)
    if written != composed or validation_errors(written, converted=True):
        report.update({"error": "AGENTS.md did not verify after the write"})
        report["artifacts"] = artifacts
        return report, EXIT_FAILED
    report.update(
        {
            "result": "applied" if artifacts else "no-op",
            "agents_md_state_after": classify_agents_md(written),
            "pending_merge_resolved": ".claude/STATE.md" in artifacts,
            "pending_merge_resolved_entries": (
                report["pending_merge"] if ".claude/STATE.md" in artifacts else []
            ),
            "artifacts": artifacts,
        }
    )
    return report, EXIT_OK


def main() -> int:
    args = build_parser().parse_args()
    report, code = run(args)
    report.setdefault("artifacts", [])
    _emit({"ok": code == EXIT_OK, **report})
    return code


if __name__ == "__main__":
    sys.exit(main())
