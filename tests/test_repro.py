"""Tests for troubleshoot/repro.py — the port of the untested repro.sh.

The shell original had no test at all, which is how it kept a deadline-less
`bash -c`, a parsed-but-ignored `--bisect-good`, invalid JSON on quoted
arguments, and an empty commit list standing in for "no git repository". Every
one of those four is pinned below.

The generic Shared Script Contract checks (--help, unknown flag, docstring,
no swallowed errors) are covered for every bundled script by
tests/test_shared_script_contract.py; this module covers repro.py's own
behaviour.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPRO = REPO_ROOT / ".claude" / "skills" / "troubleshoot" / "repro.py"

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_EXPECTATION_FAILED = 2
EXIT_EXTERNAL_FAILURE = 3

PAYLOAD_KEYS = {
    "ok",
    "repro_command",
    "label",
    "timeout",
    "exit_code",
    "expected_exit",
    "timed_out",
    "stdout_tail",
    "stderr_tail",
    "traceback",
    "traceback_format",
    "git_available",
    "git_error",
    "recent_commits",
    "blame",
    "blame_error",
    "bisect",
    "log_file",
    "artifacts",
}


def run(project_root: Path, *args: str) -> tuple[int, dict]:
    """Invoke repro.py against *project_root* and parse its single JSON object.

    json.loads rejects trailing data, so parsing here doubles as the
    "exactly one JSON object on stdout" assertion for every path exercised.
    """
    completed = subprocess.run(
        [sys.executable, str(REPRO), *args, "--project-root", str(project_root)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.returncode, json.loads(completed.stdout)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A three-commit fixture repository, so git context has something to find."""
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
        )

    git("init", "-q", ".")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (root / "f.txt").write_text("one\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "c1: add f")
    (root / "f.txt").write_text("one\ntwo\n", encoding="utf-8")
    git("commit", "-qam", "c2: change f")
    (root / "other.txt").write_text("x\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "c3: other")
    return root


# --- capture basics ----------------------------------------------------------


def test_capture_reports_full_payload_and_writes_the_log(tmp_path: Path) -> None:
    code, payload = run(tmp_path, "echo hello")
    assert code == EXIT_OK
    assert payload["ok"] is True
    assert set(payload) == PAYLOAD_KEYS
    assert payload["exit_code"] == 0
    assert payload["stdout_tail"] == "hello"
    log = tmp_path / payload["log_file"]
    assert log.is_file()
    assert "hello" in log.read_text(encoding="utf-8")
    assert payload["artifacts"] == [payload["log_file"]]


def test_failing_command_is_reported_inside_the_json_not_as_an_exit_code(
    tmp_path: Path,
) -> None:
    """A failing repro command is the *expected* case: capture succeeded."""
    code, payload = run(tmp_path, "exit 7")
    assert code == EXIT_OK
    assert payload["ok"] is True
    assert payload["exit_code"] == 7


def test_command_may_be_passed_via_flag(tmp_path: Path) -> None:
    code, payload = run(tmp_path, "--command", "echo flagged")
    assert code == EXIT_OK
    assert payload["repro_command"] == "echo flagged"


def test_command_passed_twice_is_a_bad_argument(tmp_path: Path) -> None:
    code, payload = run(tmp_path, "echo a", "--command", "echo b")
    assert code == EXIT_BAD_ARGS
    assert payload["ok"] is False


def test_missing_command_is_a_bad_argument(tmp_path: Path) -> None:
    code, payload = run(tmp_path)
    assert code == EXIT_BAD_ARGS
    assert "repro command is required" in payload["error"]


@pytest.mark.parametrize("command", ["", "   "])
def test_blank_command_is_rejected(tmp_path: Path, command: str) -> None:
    code, payload = run(tmp_path, command)
    assert code == EXIT_BAD_ARGS
    assert payload["ok"] is False


def test_quoted_argument_still_yields_valid_json(tmp_path: Path) -> None:
    """repro.sh built its error JSON with printf on unescaped input, so
    `repro.sh true '--we"ird'` emitted output json.load could not parse."""
    code, payload = run(tmp_path, "true", '--we"ird')
    assert code == EXIT_BAD_ARGS
    assert payload["ok"] is False
    assert '--we"ird' in payload["error"]


# --- the deadline (repro.sh had none) ----------------------------------------


def test_hanging_command_hits_the_deadline(tmp_path: Path) -> None:
    code, payload = run(tmp_path, "sleep 30", "--timeout", "1")
    assert code == EXIT_EXTERNAL_FAILURE
    assert payload["timed_out"] is True
    assert payload["ok"] is False
    assert payload["exit_code"] is None
    assert "timed out" in payload["error"]


def test_default_timeout_is_120_seconds(tmp_path: Path) -> None:
    _code, payload = run(tmp_path, "true")
    assert payload["timeout"] == 120


@pytest.mark.parametrize("value", ["0", "-5"])
def test_nonpositive_timeout_is_a_bad_argument(tmp_path: Path, value: str) -> None:
    code, payload = run(tmp_path, "true", "--timeout", value)
    assert code == EXIT_BAD_ARGS
    assert payload["ok"] is False


# --- --expect-exit: "the fix is verified" as an exit code --------------------


def test_expect_exit_match_is_exit_zero(tmp_path: Path) -> None:
    code, payload = run(tmp_path, "true", "--expect-exit", "0")
    assert code == EXIT_OK
    assert payload["ok"] is True
    assert payload["expected_exit"] == 0


def test_expect_exit_mismatch_is_a_contract_violation(tmp_path: Path) -> None:
    code, payload = run(tmp_path, "exit 3", "--expect-exit", "0")
    assert code == EXIT_EXPECTATION_FAILED
    assert payload["ok"] is False
    assert payload["expected_exit"] == 0
    assert payload["exit_code"] == 3
    assert payload["error"] == "expected exit 0, got 3"


# --- --label keys the log, so re-running cannot destroy the evidence ---------


def test_label_keys_the_log_file(tmp_path: Path) -> None:
    _code, first = run(tmp_path, "echo original", "--label", "bug-initial")
    _code, second = run(tmp_path, "echo verify", "--label", "bug-fix-verify")
    assert first["log_file"] == ".claude/logs/troubleshoot-repro-bug-initial.log"
    assert second["log_file"] == ".claude/logs/troubleshoot-repro-bug-fix-verify.log"
    assert "original" in (tmp_path / first["log_file"]).read_text(encoding="utf-8")


def test_unlabelled_runs_share_one_log_path(tmp_path: Path) -> None:
    _code, payload = run(tmp_path, "true")
    assert payload["log_file"] == ".claude/logs/troubleshoot-repro.log"
    assert payload["label"] is None


@pytest.mark.parametrize("label", ["Bad Label", "../escape", "-leading", "under_score"])
def test_unsafe_label_is_rejected(tmp_path: Path, label: str) -> None:
    code, payload = run(tmp_path, "true", "--label", label)
    assert code == EXIT_BAD_ARGS
    assert payload["ok"] is False


def test_a_max_length_slug_plus_a_phase_suffix_is_still_a_valid_label(
    tmp_path: Path,
) -> None:
    """workspace.py slugs run to 64 characters and the skill appends a phase
    suffix, so the label limit must leave room for it."""
    label = f"{'a' * 64}-fix-verify"
    code, payload = run(tmp_path, "true", "--label", label)
    assert code == EXIT_OK
    assert payload["log_file"] == f".claude/logs/troubleshoot-repro-{label}.log"


# --- traceback extraction is honest about what it recognizes ----------------


def test_python_traceback_is_extracted_and_labelled(tmp_path: Path) -> None:
    code, payload = run(tmp_path, "python3 -c 'raise ValueError(\"boom\")'")
    assert code == EXIT_OK
    assert payload["traceback_format"] == "python"
    assert "ValueError: boom" in payload["traceback"]


def test_non_python_failure_reports_a_null_traceback_format(tmp_path: Path) -> None:
    """`traceback: null` must be readable as "no CPython traceback", not as
    "no stack information exists" — hence the companion format field."""
    code, payload = run(tmp_path, "echo 'panic: runtime error' >&2; exit 2")
    assert code == EXIT_OK
    assert payload["traceback"] is None
    assert payload["traceback_format"] is None
    assert "panic: runtime error" in payload["stderr_tail"]


# --- git context: absent history is reported, never faked --------------------


def test_missing_git_repository_is_reported_not_shown_as_empty_history(
    tmp_path: Path,
) -> None:
    code, payload = run(tmp_path, "true")
    assert code == EXIT_OK
    assert payload["git_available"] is False
    assert payload["git_error"]
    assert payload["recent_commits"] == []


def test_recent_commits_and_blame_come_from_the_repository(git_repo: Path) -> None:
    code, payload = run(git_repo, "true", "--file", "f.txt")
    assert code == EXIT_OK
    assert payload["git_available"] is True
    assert payload["git_error"] is None
    assert len(payload["recent_commits"]) == 3
    assert payload["blame"].endswith("c2: change f")
    assert payload["blame_error"] is None


def test_unknown_blame_file_reports_an_error_rather_than_a_bare_null(
    git_repo: Path,
) -> None:
    code, payload = run(git_repo, "true", "--file", "nope.txt")
    assert code == EXIT_OK
    assert payload["blame"] is None
    assert payload["blame_error"] == "file not found: nope.txt"


def test_untracked_blame_file_reports_that_no_commit_touches_it(
    git_repo: Path,
) -> None:
    (git_repo / "fresh.txt").write_text("new\n", encoding="utf-8")
    code, payload = run(git_repo, "true", "--file", "fresh.txt")
    assert code == EXIT_OK
    assert payload["blame"] is None
    assert payload["blame_error"] == "no commit touches fresh.txt"


# --- --bisect-good actually does something now -------------------------------


def test_bisect_good_reports_the_candidate_range(git_repo: Path) -> None:
    """repro.sh parsed --bisect-good, assigned it, and never used it: the flag
    was accepted with exit 0 and no bisect key in the payload at all."""
    code, payload = run(git_repo, "true", "--bisect-good", "HEAD~2")
    assert code == EXIT_OK
    bisect = payload["bisect"]
    assert bisect["good_ref"] == "HEAD~2"
    assert bisect["error"] is None
    assert bisect["candidate_count"] == 2
    assert bisect["bisect_command"] == "git bisect start HEAD HEAD~2"


def test_bisect_good_honours_the_file_filter(git_repo: Path) -> None:
    code, payload = run(git_repo, "true", "--bisect-good", "HEAD~2", "--file", "f.txt")
    assert code == EXIT_OK
    bisect = payload["bisect"]
    assert bisect["path_filter"] == "f.txt"
    assert bisect["candidate_count"] == 1
    assert bisect["candidate_commits"][0].endswith("c2: change f")


def test_bisect_is_null_when_not_requested(git_repo: Path) -> None:
    _code, payload = run(git_repo, "true")
    assert payload["bisect"] is None


def test_unresolvable_bisect_ref_is_a_bad_argument(git_repo: Path) -> None:
    code, payload = run(git_repo, "true", "--bisect-good", "no-such-ref")
    assert code == EXIT_BAD_ARGS
    assert payload["ok"] is False
    assert "no-such-ref" in payload["error"]


def test_bisect_outside_a_git_repository_is_a_bad_argument(tmp_path: Path) -> None:
    code, payload = run(tmp_path, "true", "--bisect-good", "HEAD")
    assert code == EXIT_BAD_ARGS
    assert payload["ok"] is False


def test_bad_ref_is_rejected_before_the_repro_command_runs(git_repo: Path) -> None:
    """Argument validation must not cost a repro run: the sentinel file proves
    the command never executed."""
    sentinel = git_repo / "ran.txt"
    code, _payload = run(git_repo, f"touch {sentinel}", "--bisect-good", "no-such-ref")
    assert code == EXIT_BAD_ARGS
    assert not sentinel.exists()


# --- project-root isolation --------------------------------------------------


def test_project_root_must_be_a_directory(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere"
    code, payload = run(missing, "true")
    assert code == EXIT_BAD_ARGS
    assert payload["ok"] is False


def test_log_path_is_relative_to_project_root(tmp_path: Path) -> None:
    """log_file is repo-relative and resolves under --project-root, so a test
    (or a fixture run) can never write into the real repository."""
    _code, payload = run(tmp_path, "echo isolated")
    assert not Path(payload["log_file"]).is_absolute()
    assert (tmp_path / payload["log_file"]).is_file()
