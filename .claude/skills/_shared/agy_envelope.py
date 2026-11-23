#!/usr/bin/env python3
"""Parse Antigravity (``agy``) JSON envelopes and collect its refusal signals.

``agy --output-format json`` exits 0 with ``"status": "SUCCESS"`` even after it
refused work, so an exit code alone proves nothing. This module holds the pure
parsing half of that check, split out of ``cli_consult.py`` to keep the wrapper
within the file-size limit: ``extract_antigravity_result`` fails closed on an
unusable envelope, and ``antigravity_warnings`` collects the refusals that do
not fail the run (denied actions, soft denials on stderr, deny rules quoted in
the response).

``cli_consult.py`` imports the two functions; the command line below lets a
saved run be re-checked offline against the same logic.

Usage:
    python3 agy_envelope.py --stdout-file response.json
    python3 agy_envelope.py --stdout-file response.json --stderr-file stderr.txt

Exit codes:
    0  the envelope is a usable SUCCESS response (warnings may still be listed)
    1  bad arguments, or an input file that cannot be read
    3  the envelope is unusable: not JSON, non-SUCCESS status, or empty response
"""

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_FAILED = 3

AGY_SUCCESS_STATUS = "SUCCESS"
# agy prints these on stderr when a tool needed a permission that headless
# mode cannot prompt for; the run still exits 0.
AGY_SOFT_DENY_MARKERS = ("auto-denied", "no output produced")
# A hard deny (a session or user deny rule) appears only in the response prose.
AGY_DENY_RULE_MARKER = "Matches user-configured deny rule"
STDERR_EXCERPT_CHARS = 240


def extract_antigravity_result(stdout_text: str) -> dict:
    """Parse ``agy --output-format json`` stdout; fail closed.

    Returns ``response`` (the text to save), ``conversation_id``, ``status``,
    ``denied_actions`` (a list), and ``error`` (why the envelope is unusable,
    else ``None``). agy exits 0 with ``SUCCESS`` even after refusing work, so
    only a ``SUCCESS`` envelope with a non-empty string ``response`` counts.
    Whenever the envelope is unusable the raw stdout is returned as
    ``response``, so the evidence is saved rather than lost.
    """
    parsed: dict = {
        "response": stdout_text,
        "conversation_id": None,
        "status": None,
        "denied_actions": [],
        "error": None,
    }
    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError:
        return {**parsed, "error": "unparseable agy envelope: stdout is not JSON"}
    if not isinstance(payload, dict):
        return {**parsed, "error": "unparseable agy envelope: not a JSON object"}
    conversation = payload.get("conversation_id")
    status = payload.get("status")
    response = payload.get("response")
    denied = payload.get("denied_actions") or []
    parsed = {
        **parsed,
        "conversation_id": conversation if isinstance(conversation, str) else None,
        "status": status if isinstance(status, str) else None,
        # A changed shape must still surface as a warning, not vanish.
        "denied_actions": denied if isinstance(denied, list) else [denied],
    }
    if status != AGY_SUCCESS_STATUS:
        return {**parsed, "error": f"antigravity reported status {status!r}"}
    if not isinstance(response, str) or not response.strip():
        return {**parsed, "error": "antigravity returned an empty response"}
    return {**parsed, "response": response}


def _describe_denied(action: object) -> str:
    """Render one ``denied_actions`` entry as ``action (display name)``."""
    if not isinstance(action, dict):
        return str(action)
    name = action.get("action")
    display = action.get("display_name")
    return f"{name} ({display})" if display else str(name)


def antigravity_warnings(
    denied_actions: list, stderr_text: str, response_text: str
) -> list[str]:
    """Collect the refusal signals agy reports without failing the run.

    A denial alone does not flip ``ok``: under ``--read-only`` a denied write
    or shell attempt is expected and the deliverable may still be complete.
    """
    warnings: list[str] = []
    if denied_actions:
        names = ", ".join(_describe_denied(action) for action in denied_actions)
        warnings.append(
            f"agy denied {len(denied_actions)} action(s) it could not prompt "
            f"for: {names}"
        )
    soft_denies = [
        line.strip()
        for line in stderr_text.splitlines()
        if any(marker in line for marker in AGY_SOFT_DENY_MARKERS)
    ]
    if soft_denies:
        excerpt = soft_denies[0][:STDERR_EXCERPT_CHARS]
        warnings.append(f"agy stderr reports a soft denial: {excerpt}")
    if AGY_DENY_RULE_MARKER in response_text:
        warnings.append(
            "a deny rule blocked at least one action (quoted in the response); "
            "check that the deliverable is complete"
        )
    return warnings


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that keeps usage errors on the JSON / exit-1 contract."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_ARGS)


def _read_text(path: Path, project_root: Path) -> tuple[str | None, str | None]:
    """Return ``(text, error)``; a relative *path* resolves under the root."""
    resolved = path if path.is_absolute() else project_root / path
    try:
        return resolved.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return None, f"cannot read {path}: {exc.strerror or exc}"


def main() -> int:
    parser = JsonArgumentParser(
        description="Check a saved `agy --output-format json` run.",
    )
    parser.add_argument(
        "--stdout-file",
        type=Path,
        required=True,
        help="File holding agy's stdout (the JSON envelope)",
    )
    parser.add_argument(
        "--stderr-file",
        type=Path,
        default=None,
        help="File holding agy's stderr, scanned for soft denials",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root that relative file arguments resolve against "
        "(defaults to 4 levels above this script)",
    )
    args = parser.parse_args()

    stdout_text, error = _read_text(args.stdout_file, args.project_root)
    stderr_text: str | None = ""
    if error is None and args.stderr_file is not None:
        stderr_text, error = _read_text(args.stderr_file, args.project_root)
    if error is not None or stdout_text is None or stderr_text is None:
        _emit({"ok": False, "error": error or "input could not be read"})
        return EXIT_BAD_ARGS

    envelope = extract_antigravity_result(stdout_text)
    warnings = antigravity_warnings(
        envelope["denied_actions"], stderr_text, envelope["response"]
    )
    _emit(
        {
            "ok": envelope["error"] is None,
            "error": envelope["error"],
            "status": envelope["status"],
            "conversation_id": envelope["conversation_id"],
            "warnings": warnings,
        }
    )
    return EXIT_OK if envelope["error"] is None else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
