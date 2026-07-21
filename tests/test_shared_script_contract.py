"""Enforce the Shared Script Contract (.agents/skills/_shared/README.md)
across every bundled helper under .agents/skills/, so a new script cannot
silently drift from it.

Scripts are discovered with ``rglob`` rather than a hardcoded list: the
point of this test is that adding a new bundled script automatically pulls
it into the contract, instead of relying on someone remembering to list it.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"

PYTHON_SCRIPTS = sorted(SKILLS_DIR.rglob("*.py"))
SHELL_SCRIPTS = sorted(SKILLS_DIR.rglob("*.sh"))
ALL_SCRIPTS = sorted(PYTHON_SCRIPTS + SHELL_SCRIPTS)

assert PYTHON_SCRIPTS, f"no bundled Python scripts found under {SKILLS_DIR}"

# A bare `except:` swallows *everything*, including KeyboardInterrupt and
# SystemExit; every bundled script must name what it catches. Matched
# line-by-line (not via ast) so the same check also covers .sh scripts,
# where it is trivially a no-op.
BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:\s*(#.*)?$")

# subprocess(..., shell=True) re-opens the shell-injection and quoting risk
# that the argv-list form avoids.
FORBIDDEN_SUBSTRINGS = ("shell=True",)

# In a Python script, "2>/dev/null" can only be part of a shell command
# string — the exact pattern that made a crashed CLI indistinguishable from an
# empty answer. Shell scripts are exempt: there the same token is the idiomatic
# probe (`command -v uv >/dev/null 2>&1`, `git rev-parse ... 2>/dev/null ||
# true`) where the missing result is an explicitly handled state on the same
# line, not a discarded error.
PYTHON_ONLY_FORBIDDEN = ("2>/dev/null",)

# The Codex CLI is reached only through the shared wrapper, which closes stdin,
# captures stderr, and enforces a timeout. A direct `codex exec` anywhere in a
# bundled script would reintroduce all three failure modes.
CODEX_WRAPPER = SKILLS_DIR / "_shared" / "codex_consult.py"


def _script_id(script: Path) -> str:
    return str(script.relative_to(REPO_ROOT))


def _run(
    script: Path, project_root: Path, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    """Invoke *script* with --project-root pinned to an isolated directory.

    Every bundled Python script accepts --project-root, so no invocation in
    this test ever needs to touch (or can accidentally write into) the real
    repository.
    """
    return subprocess.run(
        [sys.executable, str(script), "--project-root", str(project_root), *extra_args],
        capture_output=True,
        text=True,
        timeout=30,
    )


# --- 1. module docstring documents Usage: and Exit codes: -------------------


@pytest.mark.parametrize("script", PYTHON_SCRIPTS, ids=_script_id)
def test_module_docstring_has_usage_and_exit_codes(script: Path) -> None:
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    docstring = ast.get_docstring(tree)
    assert docstring, f"{_script_id(script)} has no module docstring"
    assert "Usage:" in docstring, f"{_script_id(script)} docstring missing 'Usage:'"
    assert "Exit codes:" in docstring, (
        f"{_script_id(script)} docstring missing 'Exit codes:'"
    )


# --- 2/4. --help exits 0 and documents --project-root -----------------------


@pytest.mark.parametrize("script", PYTHON_SCRIPTS, ids=_script_id)
def test_help_exits_zero_and_documents_project_root(
    script: Path, tmp_path: Path
) -> None:
    result = _run(script, tmp_path, "--help")
    assert result.returncode == 0, result.stderr
    assert "--project-root" in result.stdout, (
        f"{_script_id(script)} --help does not document --project-root"
    )


# --- 3. an argparse-level failure stays on the JSON contract ----------------


@pytest.mark.parametrize("script", PYTHON_SCRIPTS, ids=_script_id)
def test_unknown_flag_stays_on_json_contract(script: Path, tmp_path: Path) -> None:
    result = _run(script, tmp_path, "--definitely-not-a-real-flag")
    assert result.returncode == 1, (
        f"{_script_id(script)}: expected exit 1 for an unrecognized flag, "
        f"got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # json.loads rejects trailing data, so this also proves stdout holds
    # exactly one JSON value rather than JSON plus leftover usage text.
    payload = json.loads(result.stdout)
    assert payload.get("ok") is False, (
        f"{_script_id(script)}: expected {{'ok': false, ...}}, got {payload!r}"
    )


# --- 5. no bundled script swallows an error ---------------------------------


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=_script_id)
def test_no_swallowed_errors(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    forbidden_here = FORBIDDEN_SUBSTRINGS
    if script.suffix == ".py":
        forbidden_here += PYTHON_ONLY_FORBIDDEN
    for forbidden in forbidden_here:
        assert forbidden not in text, (
            f"{_script_id(script)} contains forbidden {forbidden!r}"
        )
    for lineno, line in enumerate(text.splitlines(), start=1):
        assert not BARE_EXCEPT_RE.match(line), (
            f"{_script_id(script)}:{lineno} has a bare 'except:' clause"
        )


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=_script_id)
def test_codex_is_reached_only_through_the_wrapper(script: Path) -> None:
    if script == CODEX_WRAPPER:
        return
    text = script.read_text(encoding="utf-8")
    assert "codex exec" not in text, (
        f"{_script_id(script)} invokes `codex exec` directly; call "
        f"{_script_id(CODEX_WRAPPER)} instead"
    )
