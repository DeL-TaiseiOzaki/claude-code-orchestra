"""Behaviour tests for team-execute/check_ownership.py.

File-ownership separation is what ``team-execute/SKILL.md`` calls "the most
important factor" in preventing lost edits, and it used to be enforced by three
sentences of prose. These tests pin the one thing that is mechanical: whether N
sets of paths overlap, and whether every file that actually changed was
assigned to somebody.
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
SCRIPT = REPO_ROOT / ".claude" / "skills" / "team-execute" / "check_ownership.py"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_ownership = _load_module(SCRIPT, "check_ownership_under_test")


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
    for rel in ("src/api/routes.py", "src/core/engine.py", "tests/test_api.py"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def assignment(
    repo: Path, owners: dict[str, list[str]], name: str = "owners.json"
) -> str:
    # Under .claude/logs/ because that is where the lead is told to put it: the
    # directory is gitignored, so the assignment file is not itself a change
    # the reconcile pass has to account for.
    path = repo / ".claude" / "logs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"owners": owners}), encoding="utf-8")
    return str(path)


def run(repo: Path, *args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def parsed(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


# --- preflight ---------------------------------------------------------------


def test_disjoint_ownership_is_clean(repo: Path) -> None:
    spec = assignment(
        repo,
        {
            "impl-api": ["src/api/**"],
            "impl-core": ["src/core/**"],
            "tester": ["tests/**"],
        },
    )

    result = run(repo, "--assignment", spec, "--mode", "preflight")
    payload = parsed(result)

    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["overlaps"] == []


def test_two_owners_of_one_existing_file_is_a_contract_violation(repo: Path) -> None:
    spec = assignment(
        repo, {"impl-api": ["src/**"], "impl-core": ["src/core/engine.py"]}
    )

    result = run(repo, "--assignment", spec, "--mode", "preflight")
    payload = parsed(result)

    assert result.returncode == 2
    assert payload["ok"] is False
    assert {
        "path": "src/core/engine.py",
        "owners": ["impl-api", "impl-core"],
    } in payload["overlaps"]


def test_overlap_on_a_file_that_does_not_exist_yet_is_caught(repo: Path) -> None:
    """Two teammates told to create the same new file is the normal way this
    goes wrong, and the file is not on disk at preflight time."""
    spec = assignment(
        repo, {"impl-api": ["src/api/**"], "impl-b": ["src/api/new_endpoint.py"]}
    )

    result = run(repo, "--assignment", spec, "--mode", "preflight")

    assert result.returncode == 2
    assert parsed(result)["overlaps"][0]["path"] == "src/api/new_endpoint.py"


def test_single_star_does_not_cross_a_directory_separator(repo: Path) -> None:
    """fnmatch's ``*`` matches ``/``, which would make ``src/*`` silently own
    the whole subtree and turn a real overlap into a false clean result."""
    spec = assignment(repo, {"a": ["src/*"], "b": ["src/api/routes.py"]})

    result = run(repo, "--assignment", spec, "--mode", "preflight")

    assert result.returncode == 0, parsed(result)


def test_a_bare_directory_owns_its_subtree(repo: Path) -> None:
    spec = assignment(repo, {"a": ["src/api"], "b": ["src/api/routes.py"]})

    result = run(repo, "--assignment", spec, "--mode", "preflight")

    assert result.returncode == 2
    assert parsed(result)["overlaps"][0]["owners"] == ["a", "b"]


def test_directory_prefix_respects_the_slash_boundary(repo: Path) -> None:
    (repo / "src" / "api_v2").mkdir()
    (repo / "src" / "api_v2" / "x.py").write_text("x = 1\n", encoding="utf-8")
    spec = assignment(repo, {"a": ["src/api"], "b": ["src/api_v2"]})

    assert run(repo, "--assignment", spec, "--mode", "preflight").returncode == 0


def test_a_leading_dot_is_preserved(repo: Path) -> None:
    """`lstrip("./")` would turn `.claude/docs` into `agents/docs` and quietly
    check a tree that does not exist."""
    (repo / ".claude" / "docs").mkdir(parents=True)
    (repo / ".claude" / "docs" / "d.md").write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    spec = assignment(repo, {"a": [".claude/docs"], "b": [".claude/docs/d.md"]})

    result = run(repo, "--assignment", spec, "--mode", "preflight")

    assert result.returncode == 2
    assert parsed(result)["overlaps"][0]["path"] == ".claude/docs/d.md"


def test_patterns_matching_nothing_are_reported(repo: Path) -> None:
    spec = assignment(repo, {"a": ["src/api/**"], "b": ["frontend/**"]})

    payload = parsed(run(repo, "--assignment", spec, "--mode", "preflight"))

    assert payload["patterns_matching_nothing"] == {"b": ["frontend/**"]}
    assert payload["warnings"]


# --- reconcile ---------------------------------------------------------------


def dirty(repo: Path, rel: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 2\n", encoding="utf-8")


def test_reconcile_matches_the_assignment(repo: Path) -> None:
    dirty(repo, "src/api/routes.py")
    dirty(repo, "tests/test_api.py")
    spec = assignment(repo, {"impl-api": ["src/api/**"], "tester": ["tests/**"]})

    result = run(repo, "--assignment", spec, "--mode", "reconcile", "--base", "main")
    payload = parsed(result)

    assert result.returncode == 0, payload
    assert payload["changed_by_owner"] == {
        "impl-api": ["src/api/routes.py"],
        "tester": ["tests/test_api.py"],
    }
    assert payload["unowned_changes"] == []


def test_reconcile_flags_a_change_nobody_owned(repo: Path) -> None:
    dirty(repo, "src/api/routes.py")
    dirty(repo, "src/core/engine.py")
    spec = assignment(repo, {"impl-api": ["src/api/**"]})

    result = run(repo, "--assignment", spec, "--mode", "reconcile", "--base", "main")
    payload = parsed(result)

    assert result.returncode == 2
    assert payload["unowned_changes"] == ["src/core/engine.py"]


def test_allow_path_permits_a_shared_file(repo: Path) -> None:
    dirty(repo, "src/api/routes.py")
    dirty(repo, "PROGRESS.md")
    spec = assignment(repo, {"impl-api": ["src/api/**"]})

    result = run(
        repo,
        "--assignment",
        spec,
        "--mode",
        "reconcile",
        "--base",
        "main",
        "--allow-path",
        "PROGRESS.md",
    )

    assert result.returncode == 0, parsed(result)
    assert parsed(result)["allowed_paths"] == ["PROGRESS.md"]


def test_reconcile_reports_an_owner_that_touched_nothing(repo: Path) -> None:
    dirty(repo, "src/api/routes.py")
    spec = assignment(repo, {"impl-api": ["src/api/**"], "impl-core": ["src/core/**"]})

    payload = parsed(
        run(repo, "--assignment", spec, "--mode", "reconcile", "--base", "main")
    )

    assert payload["idle_owners"] == ["impl-core"]
    assert any("changed nothing" in warning for warning in payload["warnings"])


def test_reconcile_says_so_when_nothing_changed_at_all(repo: Path) -> None:
    spec = assignment(repo, {"impl-api": ["src/api/**"]})

    payload = parsed(
        run(repo, "--assignment", spec, "--mode", "reconcile", "--base", "main")
    )

    assert payload["changed_files"] == []
    assert any("no file changed" in warning for warning in payload["warnings"])


def test_reconcile_flags_a_changed_file_two_owners_claim(repo: Path) -> None:
    dirty(repo, "src/api/routes.py")
    spec = assignment(repo, {"a": ["src/**"], "b": ["src/api/routes.py"]})

    result = run(repo, "--assignment", spec, "--mode", "reconcile", "--base", "main")

    assert result.returncode == 2
    assert parsed(result)["overlaps"][0]["owners"] == ["a", "b"]


# --- bad input ---------------------------------------------------------------


def test_missing_assignment_file_is_bad_input(repo: Path) -> None:
    result = run(repo, "--assignment", "nope.json", "--mode", "preflight")

    assert result.returncode == 1
    assert parsed(result)["ok"] is False


def test_malformed_json_is_bad_input(repo: Path) -> None:
    path = repo / "broken.json"
    path.write_text("not json", encoding="utf-8")

    result = run(repo, "--assignment", str(path), "--mode", "preflight")

    assert result.returncode == 1
    assert "not valid JSON" in parsed(result)["error"]


def test_wrong_shape_is_bad_input(repo: Path) -> None:
    path = repo / "shape.json"
    path.write_text(json.dumps({"teams": {}}), encoding="utf-8")

    result = run(repo, "--assignment", str(path), "--mode", "preflight")

    assert result.returncode == 1
    assert "owners" in parsed(result)["error"]


def test_empty_owner_map_is_bad_input(repo: Path) -> None:
    spec = assignment(repo, {})

    result = run(repo, "--assignment", spec, "--mode", "preflight")

    assert result.returncode == 1
    assert "no owners" in parsed(result)["error"]


def test_owner_with_an_empty_pattern_list_is_bad_input(repo: Path) -> None:
    spec = assignment(repo, {"a": []})

    result = run(repo, "--assignment", spec, "--mode", "preflight")

    assert result.returncode == 1


def test_bad_mode_is_bad_input(repo: Path) -> None:
    spec = assignment(repo, {"a": ["src/**"]})

    result = run(repo, "--assignment", spec, "--mode", "guess")

    assert result.returncode == 1
    assert parsed(result)["ok"] is False


# --- pattern translation unit ------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("src/**", "src/a/b/c.py", True),
        ("src/**/x.py", "src/x.py", True),
        ("src/**/x.py", "src/a/b/x.py", True),
        ("src/*.py", "src/a.py", True),
        ("src/*.py", "src/a/b.py", False),
        ("src/?.py", "src/a.py", True),
        ("src/?.py", "src/ab.py", False),
        ("src/a.py", "src/a.py", True),
        ("src/a.py", "src/ab.py", False),
    ],
)
def test_pattern_matching(pattern: str, path: str, expected: bool) -> None:
    assert check_ownership.Pattern(pattern).matches(path) is expected
