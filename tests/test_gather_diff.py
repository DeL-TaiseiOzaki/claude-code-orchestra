"""Behaviour tests for _shared/gather_diff.py.

The script exists because its shell predecessor scoped the review to
``main...HEAD`` — committed history only — while the Agent Teams implement
phase never commits. With the teammates' edits in the working tree it returned
``changed_files: []`` and exit 0, and the three reviewers spawned next reviewed
nothing and reported a clean review. The first two tests below are the
regression tests for exactly that: uncommitted work must be in scope, and an
empty scope must never exit 0.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents" / "skills" / "_shared" / "gather_diff.py"

PATCH_PATH = Path(".agents") / "logs" / "review-diff.patch"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gather_diff = _load_module(SCRIPT, "gather_diff_under_test")


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with one commit on ``main``."""
    git(tmp_path, "init", "-q", "-b", "main", ".")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitignore").write_text(".agents/logs/*\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text(
        "def a():\n    return 1\n", encoding="utf-8"
    )
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def run(repo: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def parsed(result: subprocess.CompletedProcess[str]) -> dict:
    """Assert stdout is exactly one JSON object and return it parsed."""
    return json.loads(result.stdout)


# --- the defect this script exists to fix ------------------------------------


def test_uncommitted_teammate_work_is_in_scope(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text(
        'def a():\n    return 1\n\n\ndef b(password="hunter2"):\n    return password\n',
        encoding="utf-8",
    )
    (repo / "src" / "new_module.py").write_text("def c():\n    return 3\n", "utf-8")

    result = run(repo)
    payload = parsed(result)

    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["scope_empty"] is False
    assert payload["changed_files"] == ["src/mod.py", "src/new_module.py"]
    assert payload["worktree_files"] == ["src/mod.py"]
    assert payload["untracked_files"] == ["src/new_module.py"]
    # The patch a reviewer reads must actually contain the uncommitted change,
    # including the untracked file git diff alone never shows.
    patch = (repo / PATCH_PATH).read_text(encoding="utf-8")
    assert "hunter2" in patch
    assert "new_module.py" in patch
    assert payload["patch_bytes"] == len(patch.encode("utf-8"))


def test_empty_scope_fails_instead_of_reading_as_a_clean_review(repo: Path) -> None:
    result = run(repo)
    payload = parsed(result)

    assert result.returncode == 2, "an empty scope must not exit 0"
    assert payload["ok"] is False
    assert payload["scope_empty"] is True
    assert payload["changed_files"] == []
    assert any("empty" in warning for warning in payload["warnings"])
    assert (repo / PATCH_PATH).read_bytes() == b""


def test_committed_only_view_is_the_old_behaviour_and_now_fails(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")

    result = run(repo, "--no-include-uncommitted")
    payload = parsed(result)

    assert payload["include_uncommitted"] is False
    assert payload["scope_empty"] is True
    assert result.returncode == 2


def test_committed_history_is_still_in_scope(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    git(repo, "commit", "-aqm", "change it")

    payload = parsed(run(repo, "--base", "HEAD~1"))

    assert payload["ok"] is True
    assert payload["committed_files"] == ["src/mod.py"]
    assert len(payload["commits"]) == 1
    assert "change it" in payload["commits"][0]


def test_the_patch_file_is_not_part_of_its_own_scope(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")

    first = parsed(run(repo))
    second = parsed(run(repo))

    assert first["changed_files"] == second["changed_files"] == ["src/mod.py"]


# --- error paths: valid JSON everywhere -------------------------------------


def test_base_ref_error_is_valid_json(repo: Path) -> None:
    """The shell original built this payload with printf and unescaped input,
    so a ref containing a quote produced JSON that json.load rejected."""
    result = run(repo, "--base", 'no"such"ref')
    payload = parsed(result)

    assert result.returncode == 2
    assert payload["ok"] is False
    assert payload["error"] == 'base ref not found: no"such"ref'
    assert payload["base"] == 'no"such"ref'


def test_not_a_git_repository_is_a_contract_violation(tmp_path: Path) -> None:
    result = run(tmp_path)

    assert result.returncode == 2
    assert parsed(result)["ok"] is False


def test_repository_without_commits(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main", ".")

    result = run(tmp_path)

    assert result.returncode == 2
    assert "no commits" in parsed(result)["error"]


def test_missing_project_root_is_bad_input(tmp_path: Path) -> None:
    result = run(tmp_path / "nope")

    assert result.returncode == 1
    assert parsed(result)["ok"] is False


def test_out_must_stay_inside_the_project_root(repo: Path) -> None:
    result = run(repo, "--out", "/tmp/escaped.patch")

    assert result.returncode == 1
    assert "--out" in parsed(result)["error"]


def test_out_is_honoured(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")

    payload = parsed(run(repo, "--out", ".agents/logs/custom.patch"))

    assert payload["diff_file"] == ".agents/logs/custom.patch"
    assert payload["artifacts"] == [".agents/logs/custom.patch"]
    assert (repo / ".agents" / "logs" / "custom.patch").is_file()


# --- ruff: absent tool is skipped, not failed --------------------------------


def test_absent_linter_is_skipped_not_failed(repo: Path) -> None:
    """verify.sh reports an absent tool as status "skipped"; the shell original
    reported ok:false here, so a machine without ruff looked like a change with
    lint errors."""
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    # A PATH that still has git (the script needs it) but no ruff.
    fake_bin = repo / "fake-bin"
    fake_bin.mkdir()
    git_path = shutil.which("git")
    assert git_path
    (fake_bin / "git").symlink_to(git_path)
    env = dict(os.environ, PATH=str(fake_bin))

    payload = parsed(run(repo, env=env))

    assert payload["ruff"]["status"] == "skipped"
    assert payload["ruff"]["reason"] == "ruff not available"
    assert payload["ok"] is True, "a missing linter must not fail the collection"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_ruff_lints_only_the_changed_files(repo: Path) -> None:
    """Repo-wide lint debt must not be attributed to this change."""
    (repo / "src" / "debt.py").write_text("import os\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "pre-existing lint debt")
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")

    payload = parsed(run(repo))

    assert payload["ruff"]["scope"] == "changed_files"
    assert payload["ruff"]["files_linted"] == 1
    assert payload["ruff"]["status"] == "pass"
    assert payload["ruff"]["issues"] == 0


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_ruff_reports_issues_in_the_changed_files(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("import os\n", encoding="utf-8")

    payload = parsed(run(repo))

    assert payload["ruff"]["status"] == "fail"
    assert payload["ruff"]["issues"] >= 1


def test_non_python_changes_skip_the_linter(repo: Path) -> None:
    (repo / "README.md").write_text("# hi\n", encoding="utf-8")

    payload = parsed(run(repo))

    assert payload["ruff"]["status"] == "skipped"
    assert payload["ruff"]["reason"] == "no changed Python files"


# --- coverage: a parsed number or a loud null -------------------------------


def test_coverage_percent_is_parsed_from_json(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    (repo / "coverage.json").write_text(
        json.dumps({"totals": {"percent_covered": 83.4567}}), encoding="utf-8"
    )

    payload = parsed(run(repo))

    assert payload["coverage"]["report"] == "coverage.json"
    assert payload["coverage"]["percent"] == 83.46


def test_coverage_percent_is_parsed_from_xml(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    (repo / "coverage.xml").write_text(
        '<coverage line-rate="0.7125"/>', encoding="utf-8"
    )

    payload = parsed(run(repo))

    assert payload["coverage"]["percent"] == 71.25


def test_unparseable_coverage_reports_null_percent_with_a_warning(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    (repo / "coverage.xml").write_text("not xml at all", encoding="utf-8")

    payload = parsed(run(repo))

    assert payload["coverage"]["percent"] is None
    assert any("coverage.xml" in warning for warning in payload["warnings"])


def test_absent_coverage_is_null_and_says_so(repo: Path) -> None:
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")

    payload = parsed(run(repo))

    assert payload["coverage"] is None
    assert any("coverage" in warning for warning in payload["warnings"])


def test_stale_coverage_report_is_flagged(repo: Path) -> None:
    report = repo / "coverage.json"
    report.write_text(json.dumps({"totals": {"percent_covered": 90.0}}), "utf-8")
    os.utime(report, (1_000_000, 1_000_000))
    (repo / "src" / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")

    payload = parsed(run(repo))

    assert payload["coverage"]["stale_vs_scope"] is True
    assert any("predates" in warning for warning in payload["warnings"])


# --- pattern translation of the scope helpers -------------------------------


def test_untracked_patch_survives_a_binary_file(repo: Path) -> None:
    (repo / "src" / "blob.bin").write_bytes(b"\x00\x01\x02binary\xff")

    payload = parsed(run(repo))

    assert payload["ok"] is True
    assert "src/blob.bin" in payload["changed_files"]


def test_module_exposes_the_exit_vocabulary() -> None:
    assert gather_diff.EXIT_OK == 0
    assert gather_diff.EXIT_BAD_INPUT == 1
    assert gather_diff.EXIT_CONTRACT_VIOLATION == 2
    assert gather_diff.EXIT_EXTERNAL_FAILURE == 3
