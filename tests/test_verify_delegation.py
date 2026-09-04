"""Pin the Guardrail-evidence contract of _shared/verify_delegation.py.

The load-bearing property is a *negative* one: there is no verdict that means
"accepted". Three sibling skills cite this script as the step that makes
root `AGENTS.md`'s Guardrails executable, and the whole point is
that it collects evidence and hands the decision back. A future change that adds
a `clean` verdict would let every caller skip the review, so
``test_verdict_is_always_needs_review`` guards the interface, not just the code.

Every test builds a throwaway git repository under ``tmp_path``, so no run reads
or writes the real repository.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "_shared" / "verify_delegation.py"


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def run(root: Path, *extra: str) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(root), *extra],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "Traceback" not in result.stderr, result.stderr
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    return result.returncode, payload


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with one committed source file and one test file."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "T")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text(
        "def add(x, y):\n    return x + y\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_a.py").write_text(
        "from src.a import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


# --- the frozen interface ----------------------------------------------------


def test_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    for flag in ("--base", "--expect-files", "--forbid-outside", "--project-root"):
        assert flag in result.stdout


def test_payload_carries_every_frozen_key(repo: Path) -> None:
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n    return x + y + 0\n", encoding="utf-8"
    )
    code, payload = run(repo)
    assert code in (0, 2)
    for key in (
        "deletions",
        "placeholders",
        "weakened_tests",
        "out_of_scope_files",
        "verdict",
        "ok",
        "artifacts",
    ):
        assert key in payload


def test_verdict_is_always_needs_review(repo: Path) -> None:
    """No input may produce an accepting verdict — not a clean diff, not an
    empty scope, not a bad argument."""
    _, clean = run(repo)
    assert clean["verdict"] == "needs-review"

    (repo / "src" / "a.py").write_text("def add(x, y):\n    pass\n", encoding="utf-8")
    _, dirty = run(repo)
    assert dirty["verdict"] == "needs-review"

    _, bad = run(repo, "--label", "Not A Slug")
    assert bad["verdict"] == "needs-review"

    _, unresolvable = run(repo, "--base", "no-such-ref")
    assert unresolvable["verdict"] == "needs-review"


def test_no_verdict_ever_reads_as_accepted(repo: Path) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ('"clean"', '"accepted"', '"pass"', '"approved"'):
        assert forbidden not in source, (
            f"{forbidden} appears in verify_delegation.py: the script must never "
            "be able to report an accepted delegation"
        )


# --- evidence collection -----------------------------------------------------


def test_empty_scope_is_not_success(repo: Path) -> None:
    """CONTRACT CHANGE (was: ok is False on any finding).

    `ok` now reports whether *collection* succeeded, so a run that collected
    cleanly and found something is `ok: true` with exit 2. An empty scope is
    still a violated expectation and still exits 2.
    """
    code, payload = run(repo)
    assert code == 2
    assert payload["ok"] is True
    assert payload["expectations_violated"] == 1
    assert payload["scope_empty"] is True
    assert payload["changed_files"] == []


def test_uncommitted_work_is_included(repo: Path) -> None:
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n    return x + y\n\n\ndef sub(x, y):\n    return x - y\n",
        encoding="utf-8",
    )
    code, payload = run(repo)
    assert payload["changed_files"] == ["src/a.py"]
    assert payload["scope_empty"] is False
    assert code == 0, payload


def test_untracked_file_is_scanned_as_additions(repo: Path) -> None:
    (repo / "src" / "b.py").write_text(
        "def todo_later():\n    raise NotImplementedError\n", encoding="utf-8"
    )
    code, payload = run(repo)
    assert code == 2
    assert "src/b.py" in payload["untracked_files"]
    assert [p for p in payload["placeholders"] if p["file"] == "src/b.py"]


def test_deleted_lines_are_reported_with_samples(repo: Path) -> None:
    """CONTRACT CHANGE (was: exit 2 on any deletion).

    Deletions are evidence, not a verdict: any removed non-blank line counts,
    so driving the exit code from them made exit 2 the routine outcome and
    taught callers that this script's failure is noise. They are still reported
    in full, and `verdict` is still `needs-review`.
    """
    (repo / "src" / "a.py").write_text("def add(x, y):\n", encoding="utf-8")
    code, payload = run(repo)
    assert code == 0, payload
    assert payload["verdict"] == "needs-review"
    assert payload["actionable_total"] == 0
    assert payload["findings_total"] == 1
    entry = next(d for d in payload["deletions"] if d["file"] == "src/a.py")
    assert entry["deleted_lines"] == 1
    assert entry["samples"] == ["return x + y"]
    assert entry["file_deleted"] is False


def test_deleted_file_is_flagged(repo: Path) -> None:
    """CONTRACT CHANGE (was: exit 2). A whole deleted file is still reported as
    evidence with `file_deleted`, but like any deletion it is not actionable on
    its own — see test_deleted_lines_are_reported_with_samples."""
    (repo / "src" / "a.py").unlink()
    code, payload = run(repo)
    assert code == 0, payload
    entry = next(d for d in payload["deletions"] if d["file"] == "src/a.py")
    assert entry["file_deleted"] is True


def test_placeholder_and_swallowed_exception_are_reported(repo: Path) -> None:
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n"
        "    # TODO: implement\n"
        "    try:\n"
        "        return x + y\n"
        "    except TypeError: pass\n",
        encoding="utf-8",
    )
    code, payload = run(repo)
    assert code == 2
    patterns = {p["pattern"] for p in payload["placeholders"]}
    assert "todo-marker" in patterns
    assert "swallowed-exception" in patterns


def test_a_returned_placeholder_is_actionable(repo: Path) -> None:
    (repo / "src" / "a.py").write_text(
        'def add(x, y):\n    return "placeholder"\n', encoding="utf-8"
    )
    code, payload = run(repo)
    assert code == 2
    assert {p["pattern"] for p in payload["placeholders"]} == {"placeholder-text"}


def test_prose_about_placeholders_is_not_a_finding(repo: Path) -> None:
    """The word "placeholder" in prose is not evidence of a stub.

    Matching it bare made this check fire on its own documentation — including
    the Guardrails section that describes it — and a check that fires on
    innocuous content teaches callers to skim past it, which is the failure the
    exit-code split above exists to prevent.
    """
    (repo / "docs.md").write_text(
        "The `placeholders` field names added lines that look like a stub.\n"
        "A placeholder completion must be rejected.\n",
        encoding="utf-8",
    )
    code, payload = run(repo)
    assert payload["placeholders"] == []
    assert payload["actionable_total"] == 0
    assert code == 0, payload


def test_skip_marker_in_a_test_is_weakening(repo: Path) -> None:
    (repo / "tests" / "test_a.py").write_text(
        "import pytest\n"
        "from src.a import add\n\n\n"
        "@pytest.mark.skip\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    code, payload = run(repo)
    assert code == 2
    assert [w for w in payload["weakened_tests"] if w["pattern"] == "skip-marker"]


def test_removed_assertion_is_weakening(repo: Path) -> None:
    (repo / "tests" / "test_a.py").write_text(
        "from src.a import add\n\n\ndef test_add():\n    add(1, 2)\n", encoding="utf-8"
    )
    code, payload = run(repo)
    assert code == 2
    entry = next(
        w for w in payload["weakened_tests"] if w["pattern"] == "assertions-removed"
    )
    assert entry["removed_assertions"] == 1


def test_deleted_test_file_is_weakening(repo: Path) -> None:
    (repo / "tests" / "test_a.py").unlink()
    code, payload = run(repo)
    assert code == 2
    assert [w for w in payload["weakened_tests"] if w["pattern"] == "test-file-deleted"]


def test_a_skip_outside_a_test_path_is_not_weakening(repo: Path) -> None:
    """The heuristic must not fire on production code that legitimately mentions
    skipping; that is what makes the report readable enough to be used."""
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n    # it.skip(x)\n    return x + y\n", encoding="utf-8"
    )
    _, payload = run(repo)
    assert payload["weakened_tests"] == []


# --- explicit expectations ---------------------------------------------------


def test_out_of_scope_file_is_a_violation(repo: Path) -> None:
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n    return x + y\n\n\ndef mul(x, y):\n    return x * y\n",
        encoding="utf-8",
    )
    code, payload = run(repo, "--forbid-outside", "src")
    assert code == 2
    assert payload["out_of_scope_files"] == ["README.md"]


def test_scope_restriction_accepts_files_inside_it(repo: Path) -> None:
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n    return x + y\n\n\ndef mul(x, y):\n    return x * y\n",
        encoding="utf-8",
    )
    code, payload = run(repo, "--forbid-outside", "src", "--forbid-outside", "tests")
    assert code == 0, payload
    assert payload["out_of_scope_files"] == []


def test_missing_expected_file_is_a_violation(repo: Path) -> None:
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n    return x + y\n\n\ndef mul(x, y):\n    return x * y\n",
        encoding="utf-8",
    )
    code, payload = run(repo, "--expect-files", "tests/test_mul.py")
    assert code == 2
    assert payload["missing_expected_files"] == ["tests/test_mul.py"]


def test_expected_files_present_pass(repo: Path) -> None:
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n    return x + y\n\n\ndef mul(x, y):\n    return x * y\n",
        encoding="utf-8",
    )
    code, payload = run(repo, "--expect-files", "src/a.py")
    assert code == 0, payload
    assert payload["missing_expected_files"] == []


# --- arguments, base refs, and captured diff --------------------------------


def test_base_ref_is_honoured(repo: Path) -> None:
    (repo / "src" / "c.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "delegated")
    code, payload = run(repo, "--base", "HEAD~1")
    assert payload["changed_files"] == ["src/c.py"]
    assert code == 0, payload


def test_unresolvable_base_is_bad_arguments(repo: Path) -> None:
    code, payload = run(repo, "--base", "definitely-not-a-ref")
    assert code == 1
    assert payload["ok"] is False
    assert "--base" in payload["error"]


def test_not_a_git_repository_is_external_failure(tmp_path: Path) -> None:
    code, payload = run(tmp_path)
    assert code == 3
    assert payload["ok"] is False


def test_missing_project_root_is_bad_arguments(tmp_path: Path) -> None:
    code, payload = run(tmp_path / "nope")
    assert code == 1
    assert "--project-root" in payload["error"]


def test_unknown_flag_is_bad_arguments(repo: Path) -> None:
    code, payload = run(repo, "--not-a-flag")
    assert code == 1
    assert payload["ok"] is False


def test_captured_diff_is_reported_as_an_artifact(repo: Path) -> None:
    (repo / "src" / "a.py").write_text(
        "def add(x, y):\n    return x + y\n\n\ndef mul(x, y):\n    return x * y\n",
        encoding="utf-8",
    )
    code, payload = run(repo, "--label", "implement", "--now", "2026-07-25T09:00:00")
    assert code == 0, payload
    assert payload["diff_file"] == payload["artifacts"][0]
    written = repo / payload["diff_file"]
    assert written.name == "implement-20260725-090000.diff"
    assert "def mul" in written.read_text(encoding="utf-8")


def test_unparsable_now_is_bad_arguments(repo: Path) -> None:
    code, payload = run(repo, "--now", "yesterday")
    assert code == 1
    assert "--now" in payload["error"]


def test_bad_label_is_bad_arguments(repo: Path) -> None:
    code, payload = run(repo, "--label", "Bad Label")
    assert code == 1
    assert "--label" in payload["error"]
