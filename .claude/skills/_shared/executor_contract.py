#!/usr/bin/env python3
"""Compose the prompt a consult wrapper sends to a delegated executor.

Both consult wrappers (``cli_consult.py`` and ``codex_consult.py``) import this
module so that every delegated run receives the same role contract:

* ``executor_contract.md`` (next to this file) is placed before the caller's
  prompt, followed by ``TASK_DELIMITER`` and the prompt itself, byte for byte.
* ``ORCHESTRA_ROLE=executor`` is set in the callee's environment.

A delegated runtime still auto-loads the repository's root ``AGENTS.md`` and,
for Claude Code, ``.claude/rules/``; the contract is what tells it that it is
an executor rather than the main agent. The contract is a bundled asset of the
runtime, so it is resolved next to this script rather than under
``--project-root``: a wrapper pointed at a fixture project still sends the
contract it ships with. A prompt that already starts with the composed header
is not wrapped twice. ``oversized_argv_error`` checks the composed prompt
against Linux's single-argument limit, since the contract counts against it.

The command line reports the contract the wrappers would send, so a caller can
confirm the asset is present and see its hash without spending a CLI call.

Usage:
    python3 executor_contract.py
    python3 executor_contract.py --project-root /path/to/repo

Exit codes:
    0  ok — the contract was read; ``sha256`` and ``bytes`` describe it
    1  bad arguments
    3  the contract file is missing, unreadable, or empty
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONTRACT_PATH = Path(__file__).with_name("executor_contract.md")

ROLE_ENV_VAR = "ORCHESTRA_ROLE"
ROLE_EXECUTOR = "executor"
TASK_DELIMITER = "=== DELEGATED TASK ==="
# Linux caps one argv string at MAX_ARG_STRLEN (131072 bytes, NUL included);
# a longer element makes exec fail with E2BIG. Applied on every platform.
MAX_ARG_BYTES = 131_071

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_FAILED = 3


class ContractError(Exception):
    """The executor contract cannot be loaded."""


def load_contract(path: Path = CONTRACT_PATH) -> tuple[str, str]:
    """Return ``(contract_text, sha256_hex)``; raise ``ContractError`` if unusable."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"cannot read executor contract {path}: {exc}") from exc
    if not text.strip():
        raise ContractError(f"executor contract is empty: {path}")
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def contract_header(contract: str) -> str:
    """The text placed before the caller's prompt."""
    return f"{contract.rstrip()}\n\n{TASK_DELIMITER}\n\n"


def compose_prompt(contract: str, prompt: str) -> str:
    """Prefix *prompt* with the contract exactly once; the prompt is kept intact."""
    header = contract_header(contract)
    if prompt.startswith(header):
        return prompt
    return header + prompt


def prepare_prompt(prompt: str, path: Path = CONTRACT_PATH) -> tuple[str, str]:
    """Return ``(composed_prompt, contract_sha256)``; raise ``ContractError``."""
    contract, sha = load_contract(path)
    return compose_prompt(contract, prompt), sha


def oversized_argv_error(argv: list[str]) -> str | None:
    """Return an error if any argv element exceeds the single-argument limit.

    An oversized element makes ``exec`` fail with E2BIG; refusing it here
    turns that into an argument error the caller can act on. Only the prompt
    can be the culprit: every other element arrived through this wrapper's
    own argv (already under the limit) or is a short constant or path.
    """
    longest = max(len(arg.encode("utf-8", errors="surrogateescape")) for arg in argv)
    if longest <= MAX_ARG_BYTES:
        return None
    return (
        f"prompt exceeds the single-argv limit ({longest} bytes > "
        f"{MAX_ARG_BYTES}); pass long inputs by absolute path and let the "
        "callee read them"
    )


def executor_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """A copy of *base* (default: ``os.environ``) with the executor role set."""
    source = os.environ if base is None else base
    return {**source, ROLE_ENV_VAR: ROLE_EXECUTOR}


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """Report usage errors as one JSON object on stdout with exit 1."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_ARGS)


def _display_path(path: Path, project_root: Path) -> str:
    """Repo-relative POSIX path when *path* is inside *project_root*."""
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    parser = JsonArgumentParser(
        description="Report the executor contract the consult wrappers prepend.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root used only to display the contract path "
        "(defaults to 4 levels above this script)",
    )
    args = parser.parse_args()

    try:
        contract, sha = load_contract()
    except ContractError as exc:
        _emit({"ok": False, "error": str(exc)})
        return EXIT_FAILED

    _emit(
        {
            "ok": True,
            "contract_file": _display_path(CONTRACT_PATH, args.project_root),
            "sha256": sha,
            "bytes": len(contract.encode("utf-8")),
            "role_env": {ROLE_ENV_VAR: ROLE_EXECUTOR},
            "task_delimiter": TASK_DELIMITER,
        }
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
