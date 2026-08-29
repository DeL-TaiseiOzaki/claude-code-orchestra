"""Behavioral tests for the delegated-run edit recorder.

The wrappers grant unrestricted write access by default, so this module is the
only thing that answers "what did that subagent actually change?". The cases
below pin the three distinctions the answer depends on: an edit is separated
from pre-existing uncommitted work, a change to a committed file is not
reported as a creation, and work the callee committed is still counted.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents" / "skills" / "_shared" / "edit_provenance.py"


def run_script(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project_root), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=60,
    )


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", ".")
    (repo / "committed.txt").write_text("base\n", encoding="utf-8")
    (repo / "already-dirty.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def snapshot(repo: Path, out: Path) -> dict:
    result = run_script(repo, "--snapshot", "--out", str(out))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def compare(repo: Path, before: Path) -> dict:
    result = run_script(repo, "--compare", str(before))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["edits"]


def test_snapshot_reports_ok_and_the_dirty_set(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "already-dirty.txt").write_text(
        "changed before the run\n", encoding="utf-8"
    )

    payload = snapshot(repo, tmp_path / "before.json")

    assert payload["ok"] is True
    assert payload["tracked"] is True
    assert payload["dirty_files"] == 1
    # Written outside the project root, so the artifact keeps its absolute
    # form rather than a misleading relative one.
    assert payload["artifacts"] == [str(tmp_path / "before.json")]


def test_edits_are_classified_by_kind(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    before = tmp_path / "before.json"
    snapshot(repo, before)

    (repo / "created.txt").write_text("new\n", encoding="utf-8")
    (repo / "committed.txt").write_text("edited by the callee\n", encoding="utf-8")
    (repo / "already-dirty.txt").unlink()

    edits = compare(repo, before)

    assert edits["tracked"] is True
    assert edits["created_files"] == ["created.txt"]
    # A tracked file that was clean at snapshot time is a change, not a
    # creation: its absence from the snapshot means "matched HEAD", not
    # "did not exist".
    assert edits["changed_files"] == ["committed.txt"]
    assert edits["deleted_files"] == ["already-dirty.txt"]
    assert edits["files_total"] == 3
    assert edits["committed"] is False


def test_pre_existing_dirt_is_not_attributed_to_the_run(tmp_path: Path) -> None:
    """Uncommitted work in the tree when the call starts is not the callee's."""
    repo = make_repo(tmp_path)
    (repo / "already-dirty.txt").write_text("mine, not the agent's\n", encoding="utf-8")
    before = tmp_path / "before.json"
    snapshot(repo, before)

    (repo / "created.txt").write_text("the agent's\n", encoding="utf-8")

    edits = compare(repo, before)

    assert edits["created_files"] == ["created.txt"]
    assert edits["changed_files"] == []
    assert edits["files_total"] == 1


def test_a_reverted_file_is_reported_as_changed_not_deleted(tmp_path: Path) -> None:
    """Restoring a dirty file to HEAD removes it from the dirty set entirely."""
    repo = make_repo(tmp_path)
    (repo / "already-dirty.txt").write_text("half-done work\n", encoding="utf-8")
    before = tmp_path / "before.json"
    snapshot(repo, before)

    (repo / "already-dirty.txt").write_text("base\n", encoding="utf-8")

    edits = compare(repo, before)

    assert edits["changed_files"] == ["already-dirty.txt"]
    assert edits["deleted_files"] == []


def test_work_the_callee_committed_is_still_counted(tmp_path: Path) -> None:
    """Committed work is clean again, so the dirty-set diff alone sees nothing."""
    repo = make_repo(tmp_path)
    before = tmp_path / "before.json"
    snapshot(repo, before)

    (repo / "feature.py").write_text("print('hi')\n", encoding="utf-8")
    (repo / "committed.txt").write_text("edited\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "agent commit")

    edits = compare(repo, before)

    assert edits["committed"] is True
    assert edits["head_before"] != edits["head_after"]
    assert edits["created_files"] == ["feature.py"]
    assert edits["changed_files"] == ["committed.txt"]


def test_a_rename_is_a_deletion_and_a_creation(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    before = tmp_path / "before.json"
    snapshot(repo, before)

    git(repo, "mv", "committed.txt", "renamed.txt")

    edits = compare(repo, before)

    assert edits["deleted_files"] == ["committed.txt"]
    assert edits["created_files"] == ["renamed.txt"]


def test_outside_a_git_repository_it_degrades_instead_of_failing(
    tmp_path: Path,
) -> None:
    """Provenance is evidence; its absence must not break the consult."""
    plain = tmp_path / "plain"
    plain.mkdir()

    result = run_script(plain, "--snapshot", "--out", str(tmp_path / "before.json"))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["tracked"] is False

    edits = compare(plain, tmp_path / "before.json")
    assert edits["tracked"] is False
    assert edits["files_total"] == 0
    assert edits["reason"]


def test_an_unreadable_snapshot_is_a_bad_argument(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")

    result = run_script(tmp_path, "--compare", str(broken))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "broken.json" in payload["error"]


def test_out_is_refused_with_compare(tmp_path: Path) -> None:
    result = run_script(tmp_path, "--compare", str(tmp_path / "x.json"), "--out", "y")

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


def test_snapshot_written_to_the_project_root_is_reported_as_an_artifact(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)

    result = run_script(repo, "--snapshot", "--out", str(repo / "snap.json"))

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["artifacts"] == ["snap.json"]
