"""Contract tests for .claude/skills/_shared/run_tests.py.

The point of the script is that "the test did not pass" is four different
observations, and only one of them is a valid TDD Red. Every test below pins
one of those observations to its exit code, so the distinction cannot regress
back into "non-zero means red".

Every invocation passes ``--runner python`` so the fixture project is exercised
with the interpreter already running the suite: ``--runner auto`` would prefer
``uv run pytest``, which would resolve a fresh environment for a throwaway
tmp_path project.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_TESTS = REPO_ROOT / ".claude" / "skills" / "_shared" / "run_tests.py"

# The frozen `observed` vocabulary (skill-audit interface spec, section 5).
OBSERVED_STATES = {"passed", "failed", "collection_error", "no_tests_collected"}

PAYLOAD_KEYS = {
    "ok",
    "expected",
    "observed",
    "runner",
    "command",
    "exit_code",
    "summary",
    "failed_tests",
    "coverage_percent",
    "min_coverage",
    "log_file",
    "artifacts",
    "error",
}

FAILING_TEST = "def test_red():\n    assert False\n"
PASSING_TEST = "def test_green():\n    assert True\n"
UNIMPORTABLE_TEST = (
    "import definitely_not_a_real_module_xyz\n\n\ndef test_x():\n    pass\n"
)
EMPTY_TEST = "# no test functions here\n"
SLOW_TEST = "import time\n\n\ndef test_slow():\n    time.sleep(30)\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal project whose tests/ covers every observable outcome."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_red.py").write_text(FAILING_TEST, encoding="utf-8")
    (tests_dir / "test_green.py").write_text(PASSING_TEST, encoding="utf-8")
    (tests_dir / "test_broken.py").write_text(UNIMPORTABLE_TEST, encoding="utf-8")
    (tests_dir / "test_empty.py").write_text(EMPTY_TEST, encoding="utf-8")
    return tmp_path


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUN_TESTS), *args],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )


def payload_of(result: subprocess.CompletedProcess) -> dict:
    """Parse the single JSON object the script must print, whatever happened."""
    assert result.stdout, f"no stdout; stderr={result.stderr!r}"
    return json.loads(result.stdout)


def check(project: Path, *args: str) -> tuple[subprocess.CompletedProcess, dict]:
    result = run("--project-root", str(project), "--runner", "python", *args)
    return result, payload_of(result)


# --- argument handling -------------------------------------------------------


def test_help_exits_zero_and_documents_project_root() -> None:
    result = run("--help")
    assert result.returncode == 0, result.stderr
    assert "--project-root" in result.stdout


def test_unknown_flag_is_one_json_object_and_exit_1() -> None:
    result = run("--definitely-not-a-real-flag")
    assert result.returncode == 1
    assert payload_of(result)["ok"] is False


def test_missing_target_is_bad_arguments(project: Path) -> None:
    result, payload = check(project, "--expect", "fail")
    assert result.returncode == 1
    assert "at least one --target" in payload["error"]


def test_target_that_does_not_exist_is_bad_arguments(project: Path) -> None:
    """The mistyped test path from the audit: caught before pytest runs, so it
    can never be mistaken for a red test."""
    result, payload = check(
        project, "--target", "tests/test_typo.py", "--expect", "fail"
    )
    assert result.returncode == 1
    assert payload["error"] == "target does not exist: tests/test_typo.py"


def test_min_coverage_without_cov_is_bad_arguments(project: Path) -> None:
    result, payload = check(
        project,
        "--target",
        "tests/test_green.py",
        "--expect",
        "pass",
        "--min-coverage",
        "80",
    )
    assert result.returncode == 1
    assert "--min-coverage requires" in payload["error"]


def test_non_positive_timeout_is_bad_arguments(project: Path) -> None:
    result, payload = check(
        project,
        "--target",
        "tests/test_green.py",
        "--expect",
        "pass",
        "--timeout",
        "0",
    )
    assert result.returncode == 1
    assert "--timeout" in payload["error"]


def test_invalid_label_is_bad_arguments(project: Path) -> None:
    result, payload = check(
        project,
        "--target",
        "tests/test_green.py",
        "--expect",
        "pass",
        "--label",
        "../escape",
    )
    assert result.returncode == 1
    assert "--label" in payload["error"]


# --- the four observations --------------------------------------------------


def test_expected_red_is_satisfied_by_a_failing_test(project: Path) -> None:
    result, payload = check(
        project, "--target", "tests/test_red.py", "--expect", "fail"
    )
    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["expected"] == "failed"
    assert payload["observed"] == "failed"
    assert payload["exit_code"] == 1
    assert payload["failed_tests"] == ["tests/test_red.py::test_red"]
    assert payload["error"] is None
    assert set(payload) == PAYLOAD_KEYS


def test_expected_red_but_test_passes_is_exit_2(project: Path) -> None:
    result, payload = check(
        project, "--target", "tests/test_green.py", "--expect", "fail"
    )
    assert result.returncode == 2
    assert payload["ok"] is False
    assert payload["observed"] == "passed"
    assert "observed 'passed'" in payload["error"]


def test_collection_error_is_not_accepted_as_red(project: Path) -> None:
    """The central defect: an unimportable test file is red for the wrong
    reason, and must not satisfy --expect fail."""
    result, payload = check(
        project, "--target", "tests/test_broken.py", "--expect", "fail"
    )
    assert result.returncode == 2
    assert payload["observed"] == "collection_error"
    assert payload["exit_code"] == 2


def test_no_tests_collected_is_not_accepted_as_red(project: Path) -> None:
    result, payload = check(
        project, "--target", "tests/test_empty.py", "--expect", "fail"
    )
    assert result.returncode == 2
    assert payload["observed"] == "no_tests_collected"
    assert payload["exit_code"] == 5


def test_expected_green_is_satisfied_by_a_passing_test(project: Path) -> None:
    result, payload = check(
        project, "--target", "tests/test_green.py", "--expect", "pass"
    )
    assert result.returncode == 0
    assert payload["observed"] == "passed"


def test_expected_green_but_test_fails_is_exit_2(project: Path) -> None:
    result, payload = check(
        project, "--target", "tests/test_red.py", "--expect", "pass"
    )
    assert result.returncode == 2
    assert payload["observed"] == "failed"


def test_observed_is_always_a_frozen_state_or_null(project: Path) -> None:
    for target, expect in (
        ("tests/test_red.py", "fail"),
        ("tests/test_green.py", "pass"),
        ("tests/test_broken.py", "fail"),
        ("tests/test_empty.py", "fail"),
    ):
        _, payload = check(project, "--target", target, "--expect", expect)
        assert payload["observed"] in OBSERVED_STATES


def test_multiple_targets_are_run_together(project: Path) -> None:
    result, payload = check(
        project,
        "--target",
        "tests/test_red.py",
        "--target",
        "tests/test_green.py",
        "--expect",
        "fail",
    )
    assert result.returncode == 0
    assert payload["command"][-2:] == ["tests/test_red.py", "tests/test_green.py"]


# --- non-observations: usage error, external failure ------------------------


def test_pytest_usage_error_is_exit_1_with_null_observation(project: Path) -> None:
    """A node id that does not exist is a caller mistake, not an observation."""
    result, payload = check(
        project, "--target", "tests/test_green.py::test_absent", "--expect", "pass"
    )
    assert result.returncode == 1
    assert payload["observed"] is None
    assert "usage error" in payload["error"]


def test_timeout_is_an_external_failure(project: Path) -> None:
    (project / "tests" / "test_slow.py").write_text(SLOW_TEST, encoding="utf-8")
    result, payload = check(
        project,
        "--target",
        "tests/test_slow.py",
        "--expect",
        "pass",
        "--timeout",
        "2",
    )
    assert result.returncode == 3
    assert payload["observed"] is None
    assert "timed out" in payload["error"]


def test_missing_runner_is_an_external_failure(project: Path) -> None:
    """With nothing on PATH, `--runner pytest` cannot resolve — and reports
    that instead of inventing an observation."""
    result = run(
        "--project-root",
        str(project),
        "--runner",
        "pytest",
        "--target",
        "tests/test_green.py",
        "--expect",
        "pass",
        env={"PATH": str(project / "empty-bin")},
    )
    payload = payload_of(result)
    assert result.returncode == 3
    assert payload["observed"] is None
    assert "pytest is not on PATH" in payload["error"]


# --- logging ----------------------------------------------------------------


def test_output_is_logged_under_the_label(project: Path) -> None:
    result, payload = check(
        project,
        "--target",
        "tests/test_red.py",
        "--expect",
        "fail",
        "--label",
        "red-1",
    )
    assert result.returncode == 0
    assert payload["log_file"] == ".claude/logs/red-1.log"
    assert payload["artifacts"] == [".claude/logs/red-1.log"]
    log = project / ".claude" / "logs" / "red-1.log"
    assert "test_red" in log.read_text(encoding="utf-8")


def test_nothing_is_written_outside_the_project_root(project: Path) -> None:
    before = sorted(p.name for p in REPO_ROOT.joinpath(".claude", "logs").iterdir())
    check(project, "--target", "tests/test_red.py", "--expect", "fail")
    after = sorted(p.name for p in REPO_ROOT.joinpath(".claude", "logs").iterdir())
    assert before == after
