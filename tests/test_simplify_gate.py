"""Behaviour tests for simplify/simplify_gate.py.

``simplify`` used to run ``verify.sh`` once, after the edits, so a gate that was
already red was indistinguishable from a regression the refactor had just
introduced — and nothing enumerated the changed files, so "refactoring only, no
scope creep" had no evidence behind it. These tests pin both halves: the
baseline is mandatory, and a file changed outside the declared scope fails.

The fixture project has no pyproject.toml, so ``verify.sh`` legitimately reports
``no_gates``. That is itself one of the behaviours under test: a code-editing
skill must not be able to proceed with zero checks executed unless the caller
says so explicitly.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "simplify" / "simplify_gate.py"
BASELINE = Path(".claude") / "logs" / "simplify-baseline.json"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


simplify_gate = _load_module(SCRIPT, "simplify_gate_under_test")


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main", ".")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitignore").write_text(".claude/logs/*\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "target.py").write_text("def f():\n    return 1\n", "utf-8")
    (tmp_path / "src" / "other.py").write_text("def g():\n    return 2\n", "utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def run(repo: Path, *args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def parsed(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def record_baseline(repo: Path, *extra: str):
    return run(
        repo,
        "--phase",
        "before",
        "--scope",
        "src/target.py",
        "--allow-no-gates",
        *extra,
    )


# --- the before phase is mandatory and cannot be ungated ---------------------


def test_before_phase_requires_a_declared_scope(repo: Path) -> None:
    result = run(repo, "--phase", "before")

    assert result.returncode == 1
    assert "--scope" in parsed(result)["error"]


def test_ungated_project_blocks_the_before_phase(repo: Path) -> None:
    """verify.sh reports no_gates here; a skill that rewrites source must not
    be able to declare success with zero checks executed."""
    result = run(repo, "--phase", "before", "--scope", "src/target.py")
    payload = parsed(result)

    assert result.returncode == 2
    assert payload["ok"] is False
    assert payload["overall_before"] == "no_gates"
    assert "no quality gate could run" in payload["error"]
    assert not (repo / BASELINE).exists(), "no baseline is written for a blocked run"


def test_allow_no_gates_records_the_state_explicitly(repo: Path) -> None:
    result = record_baseline(repo)
    payload = parsed(result)

    assert result.returncode == 0
    assert payload["allow_no_gates"] is True
    assert payload["overall_before"] == "no_gates"
    assert payload["baseline_file"] == BASELINE.as_posix()
    assert BASELINE.as_posix() in payload["artifacts"]
    assert (
        json.loads((repo / BASELINE).read_text(encoding="utf-8"))["phase"] == "before"
    )


def test_after_phase_without_a_baseline_is_bad_input(repo: Path) -> None:
    result = run(repo, "--phase", "after", "--scope", "src/target.py")

    assert result.returncode == 1
    assert "--phase before" in parsed(result)["error"]


def test_after_phase_rejects_a_baseline_that_is_not_one(repo: Path) -> None:
    path = repo / BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"phase": "after"}), encoding="utf-8")

    result = run(repo, "--phase", "after", "--scope", "src/target.py")

    assert result.returncode == 1
    assert "not a --phase before record" in parsed(result)["error"]


def test_after_phase_rejects_unparseable_baseline(repo: Path) -> None:
    path = repo / BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{{{", encoding="utf-8")

    result = run(repo, "--phase", "after", "--scope", "src/target.py")

    assert result.returncode == 1
    assert "not valid JSON" in parsed(result)["error"]


# --- scope enforcement -------------------------------------------------------


def test_in_scope_refactor_passes(repo: Path) -> None:
    assert record_baseline(repo).returncode == 0
    (repo / "src" / "target.py").write_text(
        "def f() -> int:\n    return 1\n", encoding="utf-8"
    )

    result = run(repo, "--phase", "after", "--allow-no-gates")
    payload = parsed(result)

    assert result.returncode == 0, payload
    assert payload["in_scope_files"] == ["src/target.py"]
    assert payload["out_of_scope_files"] == []
    assert payload["regressions"] == []


def test_an_edit_outside_the_scope_fails(repo: Path) -> None:
    assert record_baseline(repo).returncode == 0
    (repo / "src" / "target.py").write_text("def f():\n    return 1\n\n", "utf-8")
    (repo / "src" / "other.py").write_text("def g():\n    return 99\n", "utf-8")

    result = run(repo, "--phase", "after", "--allow-no-gates")
    payload = parsed(result)

    assert result.returncode == 2
    assert payload["ok"] is False
    assert payload["out_of_scope_files"] == ["src/other.py"]


def test_the_after_phase_reuses_the_recorded_scope(repo: Path) -> None:
    assert record_baseline(repo).returncode == 0

    payload = parsed(run(repo, "--phase", "after", "--allow-no-gates"))

    assert payload["scope"] == ["src/target.py"]
    assert payload["base"] == "main"


def test_a_file_already_dirty_before_the_run_is_not_blamed(repo: Path) -> None:
    (repo / "src" / "other.py").write_text("def g():\n    return 3\n", "utf-8")
    before = parsed(record_baseline(repo))
    assert before["pre_existing_changes"] == ["src/other.py"]
    assert any("already modified" in warning for warning in before["warnings"])

    (repo / "src" / "target.py").write_text("def f():\n    return 1\n\n", "utf-8")
    result = run(repo, "--phase", "after", "--allow-no-gates")
    payload = parsed(result)

    assert result.returncode == 0, payload
    assert payload["out_of_scope_files"] == []
    assert payload["pre_existing_changes"] == ["src/other.py"]


def test_a_refactor_that_changed_nothing_says_so(repo: Path) -> None:
    assert record_baseline(repo).returncode == 0

    payload = parsed(run(repo, "--phase", "after", "--allow-no-gates"))

    assert payload["changed_files"] == []
    assert any("no file changed" in warning for warning in payload["warnings"])


def test_a_directory_scope_covers_its_subtree(repo: Path) -> None:
    assert (
        run(repo, "--phase", "before", "--scope", "src/", "--allow-no-gates").returncode
        == 0
    )
    (repo / "src" / "other.py").write_text("def g():\n    return 4\n", "utf-8")

    payload = parsed(run(repo, "--phase", "after", "--allow-no-gates"))

    assert payload["scope"] == ["src"]
    assert payload["out_of_scope_files"] == []


def test_after_phase_without_allow_no_gates_fails_on_an_ungated_project(
    repo: Path,
) -> None:
    assert record_baseline(repo).returncode == 0
    (repo / "src" / "target.py").write_text("def f():\n    return 1\n\n", "utf-8")

    result = run(repo, "--phase", "after")
    payload = parsed(result)

    assert result.returncode == 2
    assert payload["overall_after"] == "no_gates"
    assert any("no quality gate" in warning for warning in payload["warnings"])


# --- gate attribution --------------------------------------------------------


def test_bad_project_root_is_bad_input(tmp_path: Path) -> None:
    result = run(tmp_path / "nope", "--phase", "before", "--scope", "src")

    assert result.returncode == 1
    assert parsed(result)["ok"] is False


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        # The distinction the whole script exists for: red-before-and-after is
        # pre-existing, red-only-now is the refactor's fault.
        ({"pytest": "fail"}, {"pytest": "fail"}, "pre_existing_failures"),
        ({"pytest": "pass"}, {"pytest": "fail"}, "regressions"),
        ({"pytest": "skipped"}, {"pytest": "fail"}, "regressions"),
        ({"pytest": "fail"}, {"pytest": "pass"}, "fixed"),
    ],
)
def test_compare_gates_attributes_each_failure(
    before: dict[str, str], after: dict[str, str], expected: str
) -> None:
    verdict = simplify_gate.compare_gates(before, after)

    assert verdict[expected] == ["pytest"]
    for key, value in verdict.items():
        if key != expected:
            assert value == []


def test_compare_gates_is_quiet_when_everything_passes() -> None:
    verdict = simplify_gate.compare_gates(
        {"ruff_check": "pass", "pytest": "pass"},
        {"ruff_check": "pass", "pytest": "pass"},
    )

    assert verdict == {"regressions": [], "pre_existing_failures": [], "fixed": []}


@pytest.mark.parametrize(
    ("path", "scope", "expected"),
    [
        ("src/a.py", ["src/a.py"], True),
        ("src/a.py", ["src"], True),
        ("src/api_v2/a.py", ["src/api"], False),
        ("tests/t.py", ["src"], False),
    ],
)
def test_in_scope(path: str, scope: list[str], expected: bool) -> None:
    assert simplify_gate.in_scope(path, scope) is expected
