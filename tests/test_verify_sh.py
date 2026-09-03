"""Contract tests for `.agents/skills/_shared/verify.sh`.

No test invoked this script before, which is how three defects survived: no
`--help` (`{"error":"unknown argument: --help"}`, exit 1 — the first command a
caller tries), no `ok` field on the success payload, and `overall: "no_gates"`
exiting 0 so a code-editing skill could declare done with zero checks executed.

Shell scripts are not exempt from the Shared Script Contract
(`.agents/skills/_shared/README.md`), so the same clauses are asserted here as
`test_shared_script_contract.py` asserts for the Python helpers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SH = REPO_ROOT / ".agents" / "skills" / "_shared" / "verify.sh"

# Running the real gates needs uv on PATH. Its absence is an environment fact,
# not a defect in verify.sh — and it is exactly what the no_gates tests below
# cover deliberately.
requires_uv = pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv is not installed in this environment"
)

FIXTURE_PYPROJECT = """\
[project]
name = "fx"
version = "0.1.0"
requires-python = ">=3.11"

[dependency-groups]
dev = ["ruff", "pytest"]
"""

PASSING_TEST = "def test_ok():\n    assert True\n"
FAILING_TEST = "def test_bad():\n    assert False\n"


def run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(VERIFY_SH), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )


def payload_of(result: subprocess.CompletedProcess[str]) -> dict:
    """Parse stdout as exactly one JSON object.

    json.loads rejects trailing data, so success here also proves nothing was
    printed alongside the object.
    """
    assert result.stdout.strip().startswith("{"), result.stdout
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, dict)
    return parsed


def make_project(root: Path, test_body: str | None) -> Path:
    (root / "pyproject.toml").write_text(FIXTURE_PYPROJECT, encoding="utf-8")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    if test_body is not None:
        (tests_dir / "test_fx.py").write_text(test_body, encoding="utf-8")
    return root


# --- --help -------------------------------------------------------------------


def test_help_exits_zero_and_is_json(tmp_path: Path) -> None:
    result = run_verify("--help")
    payload = payload_of(result)
    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True
    assert "--project-root" in result.stdout
    assert "--allow-no-gates" in result.stdout


def test_help_documents_the_exit_vocabulary() -> None:
    payload = payload_of(run_verify("--help"))
    assert set(payload["exit_codes"]) == {"0", "1", "2", "3"}


def test_short_help_flag_also_works() -> None:
    result = run_verify("-h")
    assert result.returncode == 0, result.stderr
    assert payload_of(result)["ok"] is True


def test_help_does_not_write_the_log_file(tmp_path: Path) -> None:
    """--help must answer without touching the filesystem."""
    project = make_project(tmp_path, PASSING_TEST)
    run_verify("--project-root", str(project), "--help")
    assert not (project / ".agents" / "logs" / "verify.log").exists()


# --- bad arguments (exit 1) ---------------------------------------------------


def test_unknown_flag_is_exit_1_with_one_json_object() -> None:
    result = run_verify("--definitely-not-a-real-flag")
    payload = payload_of(result)
    assert result.returncode == 1, result.stdout
    assert payload == {
        "ok": False,
        "error": "unknown argument: --definitely-not-a-real-flag",
    }


def test_project_root_without_a_value_is_exit_1() -> None:
    result = run_verify("--project-root")
    payload = payload_of(result)
    assert result.returncode == 1, result.stdout
    assert payload["ok"] is False


def test_project_root_pointing_nowhere_is_exit_1(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    result = run_verify("--project-root", str(missing))
    payload = payload_of(result)
    assert result.returncode == 1, result.stdout
    assert payload["ok"] is False
    assert "directory not found" in payload["error"]


def test_bad_argument_never_writes_a_log_into_the_real_repo() -> None:
    """An argument error must fail before any filesystem work."""
    before = (REPO_ROOT / ".agents" / "logs" / "verify.log").exists()
    run_verify("--definitely-not-a-real-flag")
    assert (REPO_ROOT / ".agents" / "logs" / "verify.log").exists() == before


# --- no_gates is a failure unless explicitly allowed (exit 2) ----------------


def test_no_gates_is_a_contract_violation(tmp_path: Path) -> None:
    """The defect this closes: a project where no gate can run reported
    exit 0, so `simplify` could edit code and declare done having verified
    nothing."""
    result = run_verify("--project-root", str(tmp_path))
    payload = payload_of(result)

    assert result.returncode == 2, result.stdout
    assert payload["ok"] is False
    assert payload["overall"] == "no_gates"
    assert payload["allow_no_gates"] is False
    assert payload["warnings"], "the no_gates state must be explained"


def test_allow_no_gates_makes_it_success(tmp_path: Path) -> None:
    result = run_verify("--project-root", str(tmp_path), "--allow-no-gates")
    payload = payload_of(result)

    assert result.returncode == 0, result.stdout
    assert payload["ok"] is True
    assert payload["overall"] == "no_gates"
    assert payload["allow_no_gates"] is True


def test_no_gates_reports_why_each_tool_was_skipped(tmp_path: Path) -> None:
    payload = payload_of(run_verify("--project-root", str(tmp_path)))
    assert set(payload["tools"]) == {"ruff_check", "ruff_format", "ty", "pytest"}
    for tool, entry in payload["tools"].items():
        assert entry["status"] == "skipped", tool
        assert entry["reason"], f"{tool} was skipped without a reason"


# --- real gate runs ----------------------------------------------------------


@requires_uv
def test_passing_gates(tmp_path: Path) -> None:
    project = make_project(tmp_path, PASSING_TEST)
    result = run_verify("--project-root", str(project))
    payload = payload_of(result)

    assert result.returncode == 0, result.stdout
    assert payload["ok"] is True
    assert payload["overall"] == "pass"
    assert payload["tools"]["pytest"]["status"] == "pass"
    assert payload["tools"]["pytest"]["exit_code"] == 0
    assert payload["warnings"] == []


@requires_uv
def test_failing_gate_is_exit_2_not_1(tmp_path: Path) -> None:
    """Gate failure is a contract violation (2); exit 1 is reserved for bad
    arguments, which callers must be able to tell apart."""
    project = make_project(tmp_path, FAILING_TEST)
    result = run_verify("--project-root", str(project))
    payload = payload_of(result)

    assert result.returncode == 2, result.stdout
    assert payload["ok"] is False
    assert payload["overall"] == "fail"
    assert payload["tools"]["pytest"]["status"] == "fail"
    assert payload["tools"]["pytest"]["exit_code"] != 0


@requires_uv
def test_no_tests_collected_counts_as_absence_of_a_gate(tmp_path: Path) -> None:
    """pytest exit 5 is "no gate", not "gate failed" — and with ruff still
    running, overall stays `pass`."""
    project = make_project(tmp_path, None)
    result = run_verify("--project-root", str(project))
    payload = payload_of(result)

    assert payload["tools"]["pytest"]["status"] == "skipped"
    assert "no tests collected" in payload["tools"]["pytest"]["reason"]
    assert payload["overall"] == "pass"
    assert result.returncode == 0, result.stdout


@requires_uv
def test_log_file_and_artifacts_are_repo_relative_and_written(tmp_path: Path) -> None:
    project = make_project(tmp_path, PASSING_TEST)
    payload = payload_of(run_verify("--project-root", str(project)))

    assert payload["log_file"] == ".agents/logs/verify.log"
    assert payload["artifacts"] == [".agents/logs/verify.log"]
    written = project / payload["log_file"]
    assert written.is_file()
    # The gate output really is captured, not just claimed.
    assert "ruff_check" in written.read_text(encoding="utf-8")


@requires_uv
def test_project_root_is_honoured_for_every_path_it_touches(tmp_path: Path) -> None:
    """--project-root must relocate the log too: a fixture run may not write
    into the real repository."""
    project = make_project(tmp_path, PASSING_TEST)
    real_log = REPO_ROOT / ".agents" / "logs" / "verify.log"
    before = real_log.stat().st_mtime_ns if real_log.exists() else None

    run_verify("--project-root", str(project))

    after = real_log.stat().st_mtime_ns if real_log.exists() else None
    assert after == before


# --- payload shape is stable across outcomes ---------------------------------

REPORT_KEYS = {
    "ok",
    "overall",
    "allow_no_gates",
    "tools",
    "warnings",
    "log_file",
    "artifacts",
}


@requires_uv
def test_report_keys_are_identical_on_pass_fail_and_no_gates(tmp_path: Path) -> None:
    for name in ("pass", "fail", "bare"):
        (tmp_path / name).mkdir()
    passing = make_project(tmp_path / "pass", PASSING_TEST)
    failing = make_project(tmp_path / "fail", FAILING_TEST)
    bare = tmp_path / "bare"

    payloads = [
        payload_of(run_verify("--project-root", str(project)))
        for project in (passing, failing, bare)
    ]
    for payload in payloads:
        assert set(payload.keys()) == REPORT_KEYS
        assert isinstance(payload["ok"], bool)
