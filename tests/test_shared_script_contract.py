"""Enforce the Shared Script Contract (.claude/skills/_shared/README.md)
across every bundled helper under .claude/skills/, so a new script cannot
silently drift from it.

Scripts are discovered with ``rglob`` rather than a hardcoded list: the
point of this test is that adding a new bundled script automatically pulls
it into the contract, instead of relying on someone remembering to list it.

Shell scripts are **not** exempt. They used to be: the JSON, ``--project-root``
and docstring clauses were applied to ``PYTHON_SCRIPTS`` only and no test ever
invoked a ``.sh`` helper, which is how three real defects (invalid JSON on a
quoted argument, an empty review scope reported as success, and a parsed but
unused ``--bisect-good``) stayed invisible until an audit read the sources.

Clauses that are *not* machine-checked here, and why, so a reader does not
mistake this file for full coverage:

* **Verified success path** — "the script re-read what it wrote and validated
  it" cannot be distinguished from the outside from "the script wrote it and
  reported success". Each writer's own test file asserts it (for example
  ``tests/test_codex_consult.py::test_success_reports_artifacts_and_a_verified_response``).
* **Re-run safety** — needs typed, script-specific input to apply twice; it
  lives in ``tests/test_update_design.py`` and the other writer test files.
* **Graceful degradation** — whether a particular absent optional path *should*
  be ``null`` + exit 0 or a named failure state is a judgment about that
  script's domain, not a property of the payload shape.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

PYTHON_SCRIPTS = sorted(SKILLS_DIR.rglob("*.py"))
SHELL_SCRIPTS = sorted(SKILLS_DIR.rglob("*.sh"))
ALL_SCRIPTS = sorted(PYTHON_SCRIPTS + SHELL_SCRIPTS)

assert PYTHON_SCRIPTS, f"no bundled Python scripts found under {SKILLS_DIR}"
assert SHELL_SCRIPTS, f"no bundled shell scripts found under {SKILLS_DIR}"

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


def _invoke(
    script: Path, project_root: Path, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    """Run *script* whatever its language, with --project-root pinned.

    Shell helpers answer the same contract as the Python ones, so every clause
    below can be parametrized over ``ALL_SCRIPTS`` instead of quietly skipping
    the two languages' difference.
    """
    if script.suffix == ".py":
        return _run(script, project_root, *extra_args)
    return subprocess.run(
        ["bash", str(script), "--project-root", str(project_root), *extra_args],
        capture_output=True,
        text=True,
        timeout=120,
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


# --- 6. shell helpers answer the same --help / JSON / exit contract ----------


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=_script_id)
def test_shell_help_exits_zero_and_documents_project_root(
    script: Path, tmp_path: Path
) -> None:
    """`bash verify.sh --help` used to print {"error":"unknown argument:
    --help"} and exit 1 — the first command a caller tries."""
    result = subprocess.run(
        ["bash", str(script), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload.get("ok") is True, payload
    assert "--project-root" in result.stdout, (
        f"{_script_id(script)} --help does not document --project-root"
    )
    assert "exit_codes" in payload, (
        f"{_script_id(script)} --help does not document its exit codes"
    )


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=_script_id)
def test_shell_unknown_flag_stays_on_json_contract(
    script: Path, tmp_path: Path
) -> None:
    result = _invoke(script, tmp_path, "--definitely-not-a-real-flag")
    assert result.returncode == 1, (
        f"{_script_id(script)}: expected exit 1 for an unrecognized flag, "
        f"got {result.returncode}\nstdout={result.stdout!r}"
    )
    payload = json.loads(result.stdout)
    assert payload.get("ok") is False, payload


# --- 7. `ok` is a boolean on every payload, and the exit vocabulary holds ----

EXIT_VOCABULARY = {0, 1, 2, 3}

# checkpoint.py's success path is a human-readable report by documented
# exception (_shared/README.md); its *error* paths are JSON like everyone
# else's, which is what the bare invocation below exercises.
PROSE_SUCCESS_SCRIPTS = {SKILLS_DIR / "checkpointing" / "checkpoint.py"}


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=_script_id)
def test_bare_invocation_emits_one_json_object_with_a_boolean_ok(
    script: Path, tmp_path: Path
) -> None:
    """Run each script with nothing but --project-root against an empty root.

    Unlike the unknown-flag case this reaches the script's own code, so a
    missing-input path that used to exit before printing anything — or a write
    that raised an OSError traceback instead of reporting it — fails here.
    """
    result = _invoke(script, tmp_path)
    assert result.returncode in EXIT_VOCABULARY, (
        f"{_script_id(script)}: exit {result.returncode} is outside the shared "
        f"vocabulary {sorted(EXIT_VOCABULARY)}\nstderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert isinstance(payload.get("ok"), bool), (
        f"{_script_id(script)}: payload has no boolean 'ok'; a caller "
        f"branching on it reads None\npayload={payload!r}"
    )
    # Silence always means success: ok and the exit code may never disagree.
    assert payload["ok"] is (result.returncode == 0), (
        f"{_script_id(script)}: ok={payload['ok']} with exit "
        f"{result.returncode}\npayload={payload!r}"
    )
    assert "Traceback" not in result.stderr, (
        f"{_script_id(script)} leaked a traceback:\n{result.stderr}"
    )


# --- 8. the success path carries `ok: true` ----------------------------------
#
# There is no generic "succeed" invocation, so a success case is registered per
# script: args plus the fixture the script needs to have something to succeed
# at. Every discovered script must appear either here or in SUCCESS_EXEMPT,
# and an exemption must name a test file that actually exercises the script —
# so a new helper cannot land with its success path unchecked anywhere.


def _prep_nothing(root: Path) -> None:
    return None


def _prep_agent_docs(root: Path) -> None:
    (root / ".claude" / "rules").mkdir(parents=True)
    (root / ".claude" / "rules" / "coding.md").write_text(
        "# Coding\n", encoding="utf-8"
    )
    (root / ".claude" / "docs").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "docs" / "DESIGN.md").write_text("# Design\n", encoding="utf-8")
    (root / ".claude" / "STATE.md").write_text("# State\n", encoding="utf-8")
    (root / "PROGRESS.md").write_text("# Progress\n", encoding="utf-8")


def _prep_git_repo(root: Path) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(root / "gitconfig")}
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env, timeout=60)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=test",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=root,
        check=True,
        env=env,
        timeout=60,
    )


SUCCESS_CASES: dict[Path, tuple[Callable[[Path], None], list[str]]] = {
    SKILLS_DIR / "_shared" / "verify.sh": (_prep_nothing, ["--allow-no-gates"]),
    SKILLS_DIR / "_shared" / "edit_provenance.py": (_prep_git_repo, ["--snapshot"]),
    SKILLS_DIR / "context-loader" / "load_context.py": (_prep_agent_docs, []),
    SKILLS_DIR / "catchup" / "collect_repo_state.py": (_prep_git_repo, []),
    SKILLS_DIR / "troubleshoot" / "repro.py": (_prep_nothing, ["true"]),
    SKILLS_DIR / "update-lib-docs" / "lib_inventory.py": (_prep_nothing, []),
}

SUCCESS_EXEMPT: dict[Path, str] = {
    # Needs a fake codex/claude/agy executable on PATH.
    SKILLS_DIR / "_shared" / "codex_consult.py": "tests/test_codex_consult.py",
    SKILLS_DIR / "_shared" / "cli_consult.py": "tests/test_cli_consult.py",
    # Needs typed JSON input built against the script's own schema.
    SKILLS_DIR
    / "_shared"
    / "append_state_block.py": "tests/test_append_state_block.py",
    SKILLS_DIR / "_shared" / "update_design.py": "tests/test_update_design.py",
    SKILLS_DIR / "_shared" / "validate_doc.py": "tests/test_validate_doc.py",
    SKILLS_DIR / "catchup" / "write_guide.py": "tests/test_write_guide.py",
    SKILLS_DIR / "checkpointing" / "checkpoint.py": "tests/test_checkpoint.py",
    SKILLS_DIR / "checkpointing" / "refresh_guard.py": "tests/test_refresh_guard.py",
    SKILLS_DIR / "team-execute" / "check_ownership.py": "tests/test_check_ownership.py",
    # Needs a git history with a non-empty diff.
    SKILLS_DIR / "_shared" / "gather_diff.py": "tests/test_gather_diff.py",
    SKILLS_DIR / "_shared" / "verify_delegation.py": "tests/test_verify_delegation.py",
    SKILLS_DIR / "simplify" / "simplify_gate.py": "tests/test_simplify_gate.py",
    # Needs a real test run / a complete agent bootstrap to succeed.
    SKILLS_DIR / "_shared" / "run_tests.py": "tests/test_run_tests.py",
    SKILLS_DIR / "init" / "detect_stack.py": "tests/test_detect_stack.py",
    # Resolved paths are asserted directly there, including the relative form.
    SKILLS_DIR / "_shared" / "workspace.py": "tests/test_workspace.py",
}


def test_every_script_has_a_registered_success_case_or_a_named_owner_test() -> None:
    registered = set(SUCCESS_CASES) | set(SUCCESS_EXEMPT)
    missing = {_script_id(s) for s in ALL_SCRIPTS} - {_script_id(s) for s in registered}
    assert not missing, (
        "these bundled scripts have no success case here and no named test "
        f"file: {sorted(missing)}. Add one, or add an entry to SUCCESS_EXEMPT "
        "pointing at the test file that exercises the script's success path."
    )
    stale = {_script_id(s) for s in registered} - {_script_id(s) for s in ALL_SCRIPTS}
    assert not stale, f"registered scripts that no longer exist: {sorted(stale)}"


@pytest.mark.parametrize("script", sorted(SUCCESS_EXEMPT), ids=_script_id)
def test_success_exemption_names_a_test_file_that_exercises_the_script(
    script: Path,
) -> None:
    """An exemption is only honest if the coverage it claims exists."""
    owner_test = REPO_ROOT / SUCCESS_EXEMPT[script]
    assert owner_test.is_file(), (
        f"{_script_id(script)} is exempted in favour of {SUCCESS_EXEMPT[script]}, "
        "which does not exist"
    )
    assert script.name in owner_test.read_text(encoding="utf-8"), (
        f"{SUCCESS_EXEMPT[script]} never mentions {script.name}"
    )


@pytest.mark.parametrize("script", sorted(SUCCESS_CASES), ids=_script_id)
def test_success_payload_carries_ok_true_and_relative_artifacts(
    script: Path, tmp_path: Path
) -> None:
    prep, args = SUCCESS_CASES[script]
    prep(tmp_path)

    result = _invoke(script, tmp_path, *args)

    assert result.returncode == 0, (
        f"{_script_id(script)} {args}: expected a successful run, got exit "
        f"{result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload.get("ok") is True, (
        f"{_script_id(script)}: a successful run must report ok: true, "
        f"got {payload.get('ok')!r} — a caller branching on payload.ok reads "
        "success as failure"
    )
    # `artifacts` is additive, so a read-only helper may omit it; when present
    # it must be the documented shape.
    if "artifacts" in payload:
        assert isinstance(payload["artifacts"], list), payload["artifacts"]
        for entry in payload["artifacts"]:
            assert isinstance(entry, str), entry
            assert not Path(entry).is_absolute(), (
                f"{_script_id(script)} reports a non-relative artifact: {entry}"
            )
            assert "\\" not in entry, f"artifact is not POSIX: {entry}"


# --- 9. a script that writes files reports what it wrote --------------------

# Text markers for "this script creates or replaces files". Deliberately
# source-text based: the alternative is to run every script in a mode that
# writes, which no single invocation can do.
WRITE_MARKERS = (
    "write_text(",
    "os.replace(",
    ".mkdir(",
    "os.open(",
    "mkdir -p",
)


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=_script_id)
def test_writer_scripts_report_an_artifacts_list(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    if not any(marker in text for marker in WRITE_MARKERS):
        return
    assert '"artifacts"' in text, (
        f"{_script_id(script)} creates files but never reports 'artifacts'; a "
        "caller cannot log, diff, or roll back what it cannot name"
    )


# --- 10. a script that stamps a timestamp accepts an injected clock ---------

CLOCK_MARKERS = ("datetime.now(", "date.today(", "datetime.utcnow(", "time.time(")

# Documented exception (_shared/README.md): lib_inventory.py takes
# `--today YYYY-MM-DD` instead of `--now ISO8601`. It stamps nothing — the
# date is only compared against `Last Updated` for staleness — and its strict
# format is pinned by tests/test_lib_inventory.py.
CLOCK_FLAG_EXCEPTIONS = {SKILLS_DIR / "update-lib-docs" / "lib_inventory.py": "--today"}


@pytest.mark.parametrize("script", PYTHON_SCRIPTS, ids=_script_id)
def test_clock_reading_scripts_accept_an_injected_clock(
    script: Path, tmp_path: Path
) -> None:
    text = script.read_text(encoding="utf-8")
    if not any(marker in text for marker in CLOCK_MARKERS):
        return
    expected_flag = CLOCK_FLAG_EXCEPTIONS.get(script, "--now")
    result = _run(script, tmp_path, "--help")
    assert result.returncode == 0, result.stderr
    # \b so a flag that merely starts with the same letters (--nowish) does not
    # satisfy the clause.
    assert re.search(rf"{re.escape(expected_flag)}\b", result.stdout), (
        f"{_script_id(script)} reads the clock but --help does not offer "
        f"{expected_flag}: its timestamped output cannot be pinned by a test"
    )
    # One reading per run: two direct clock reads can disagree with each other
    # inside a single payload (a filename stamped a second after its header).
    assert sum(text.count(marker) for marker in CLOCK_MARKERS) == 1, (
        f"{_script_id(script)} reads the clock more than once; resolve it once "
        "and pass the value down"
    )


# --- 11. the documented exit codes stay inside the shared vocabulary --------

EXIT_LINE_RE = re.compile(r"^\s{2,}(\d+)\s{2,}\S")


@pytest.mark.parametrize("script", PYTHON_SCRIPTS, ids=_script_id)
def test_documented_exit_codes_are_from_the_shared_vocabulary(script: Path) -> None:
    """The mapping of a code onto *this* script's meaning is prose and cannot
    be machine-checked; that the codes exist in the shared vocabulary can."""
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    docstring = ast.get_docstring(tree) or ""
    section = docstring.split("Exit codes:", 1)[1]
    documented = {
        int(match.group(1))
        for match in (EXIT_LINE_RE.match(line) for line in section.splitlines())
        if match
    }
    assert documented, f"{_script_id(script)} documents no exit code meanings"
    assert documented <= EXIT_VOCABULARY, (
        f"{_script_id(script)} documents exit codes outside the shared "
        f"vocabulary: {sorted(documented - EXIT_VOCABULARY)}"
    )
    assert 0 in documented and 1 in documented, (
        f"{_script_id(script)} must document at least 0 (ok) and 1 (bad args), "
        f"documents {sorted(documented)}"
    )


# --- 12. standard library only ----------------------------------------------
#
# A sibling module inside `_shared/` is not a third-party dependency: Python
# puts the script's own directory on sys.path, so importing one keeps the
# "runs wherever python3 does" property this clause exists to protect. The
# alternative — copying a helper into both consult wrappers — is the drift the
# bundled runtime was created to prevent. A sibling must still satisfy every
# other clause here, so it cannot become a back door for an unchecked helper.
SHARED_MODULES = {path.stem for path in (SKILLS_DIR / "_shared").glob("*.py")}


@pytest.mark.parametrize("script", PYTHON_SCRIPTS, ids=_script_id)
def test_no_third_party_imports(script: Path) -> None:
    """The README states stdlib-only; nothing verified it, so the first
    `import yaml` would have landed unnoticed and broken every environment
    that has python3 but not that package."""
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module of its own to resolve.
            roots = (
                [node.module.split(".")[0]] if node.level == 0 and node.module else []
            )
        else:
            continue
        for root in roots:
            assert root in sys.stdlib_module_names or root in SHARED_MODULES, (
                f"{_script_id(script)} imports non-stdlib {root!r}"
            )


# --- 13. an unwritable .claude/ is reported, never a traceback ---------------


@pytest.mark.parametrize("script", sorted(SUCCESS_CASES), ids=_script_id)
def test_success_case_against_an_unwritable_agents_dir_reports_json(
    script: Path, tmp_path: Path
) -> None:
    """Same invocation as the success case, but with `.claude` as a regular
    file so anything the script tries to create under it fails.

    An unguarded write used to surface here as a bare ``NotADirectoryError``
    traceback with no JSON at all and exit 1 — which the shared exit-code
    vocabulary reads as "bad arguments". A script that needs nothing under
    `.claude` may still succeed; what it may not do is crash.
    """
    _, args = SUCCESS_CASES[script]
    (tmp_path / ".claude").write_text("not a directory", encoding="utf-8")

    result = _invoke(script, tmp_path, *args)

    assert "Traceback" not in result.stderr, (
        f"{_script_id(script)} let an unguarded write raise:\n{result.stderr}"
    )
    assert result.returncode in EXIT_VOCABULARY, result.returncode
    payload = json.loads(result.stdout)
    assert isinstance(payload.get("ok"), bool), payload
    assert payload["ok"] is (result.returncode == 0), payload
