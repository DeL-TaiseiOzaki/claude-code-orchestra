from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_SOURCE_DIR = REPO_ROOT / ".claude" / "hooks"
DISPATCHER_NAME = "post-bash-check.py"


def build_isolated_hooks_dir(tmp_path: Path) -> Path:
    """Copy canonical hooks into an isolated tmp project so the dispatcher
    under test never resolves paths inside the real repo's .claude/."""
    hooks_dir = tmp_path / ".claude" / "hooks"
    shutil.copytree(HOOKS_SOURCE_DIR, hooks_dir)
    return hooks_dir


def run_dispatcher(
    hooks_dir: Path, payload: dict | str
) -> subprocess.CompletedProcess[str]:
    stdin_text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        ["python3", str(hooks_dir / DISPATCHER_NAME)],
        input=stdin_text,
        check=False,
        capture_output=True,
        text=True,
    )


def bash_hook_input(command: str, stdout: str, exit_code: int = 1) -> dict:
    """Build a PostToolUse Bash payload.

    ``exit_code`` is consumed by no hook. A captured real payload
    carries just ``{stdout, stderr, interrupted, isImage, noOutputExpected}``
    under ``tool_response`` — and a failing Bash command does not reach the
    hook at all — so no error-detection logic may key off it.
    """
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout, "exit_code": exit_code},
    }


def test_traceback_output_triggers_debugging_hint(tmp_path: Path) -> None:
    hooks_dir = build_isolated_hooks_dir(tmp_path)
    payload = bash_hook_input(
        command="python3 script.py",
        stdout=(
            "Running script...\n"
            "Traceback (most recent call last):\n"
            '  File "script.py", line 5, in <module>\n'
            '    raise ValueError("bad input")\n'
            "ValueError: bad input\n"
        ),
    )

    result = run_dispatcher(hooks_dir, payload)

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "[Error Detected]" in context
    assert "`debugger`" in context


def test_pytest_failure_dedups_generic_error_hint(tmp_path: Path) -> None:
    """Coordination fix under test: when post-test-analysis already produced
    a targeted hint, the generic error-to-debugger hint must be suppressed."""
    hooks_dir = build_isolated_hooks_dir(tmp_path)
    payload = bash_hook_input(
        command="uv run pytest tests/",
        stdout=(
            "FAILED tests/test_foo.py::test_bar\n"
            "AssertionError: expected 1 got 2\n"
            "Traceback (most recent call last):\n"
            '  File "test_foo.py", line 10, in test_bar\n'
            "    assert 1 == 2\n"
            "1 failed, 2 passed\n"
        ),
    )

    result = run_dispatcher(hooks_dir, payload)

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "[Debug Suggestion]" in context
    assert "[Error Detected]" not in context


def test_benign_output_produces_no_hint(tmp_path: Path) -> None:
    hooks_dir = build_isolated_hooks_dir(tmp_path)
    payload = bash_hook_input(
        command="ls -la",
        stdout="total 42\ndrwxr-xr-x  5 user user 4096 Jan 1 12:00 .\n",
        exit_code=0,
    )

    result = run_dispatcher(hooks_dir, payload)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_green_pytest_output_produces_no_hint(tmp_path: Path) -> None:
    """A passing suite must stay silent.

    Regression guard: the bare `ERROR`/`failed`/`Error:` patterns matched the
    word "error" inside test *names*, so this exact output — 8 passed, 0
    failed — produced "Test failure with error details (2 issues)".
    """
    hooks_dir = build_isolated_hooks_dir(tmp_path)
    payload = bash_hook_input(
        command="uv run pytest tests/test_post_bash_check.py -v",
        stdout=(
            "tests/test_post_bash_check.py::test_traceback_output_triggers_"
            "debugging_hint PASSED [ 12%]\n"
            "tests/test_post_bash_check.py::test_pytest_failure_dedups_generic_"
            "error_hint PASSED [ 25%]\n"
            "tests/test_post_bash_check.py::test_benign_output_produces_no_hint "
            "PASSED [ 87%]\n"
            "============================== 8 passed in 0.30s "
            "===============================\n"
        ),
        exit_code=0,
    )

    result = run_dispatcher(hooks_dir, payload)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_clean_mypy_output_on_errors_module_produces_no_hint(tmp_path: Path) -> None:
    """Boundary case: a success message whose only "error" is a file name."""
    hooks_dir = build_isolated_hooks_dir(tmp_path)
    payload = bash_hook_input(
        command="uv run mypy src/errors.py",
        stdout="Success: no issues found in 1 source file (src/errors.py)\n",
        exit_code=0,
    )

    result = run_dispatcher(hooks_dir, payload)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_benign_nonzero_exit_produces_no_hint(tmp_path: Path) -> None:
    """`diff` reporting differences is an answer, not a failure.

    Regression guard for the "command exited with code 1 - likely a silent
    failure" branch, which fired on every loud non-zero exit. The branch is
    gone (the real PostToolUse payload carries no exit status at all), and this
    test keeps any replacement from re-introducing the behaviour.
    """
    hooks_dir = build_isolated_hooks_dir(tmp_path)
    payload = bash_hook_input(
        command="diff a.txt b.txt",
        stdout="1c1\n< alpha\n---\n> beta\n",
        exit_code=1,
    )

    result = run_dispatcher(hooks_dir, payload)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_deprecation_warnings_alone_produce_no_hint(tmp_path: Path) -> None:
    """A warning is not an error, even when two of them travel together."""
    hooks_dir = build_isolated_hooks_dir(tmp_path)
    payload = bash_hook_input(
        command="uv pip install requests",
        stdout=(
            "DEPRECATION: the legacy resolver is deprecated\n"
            "Could not find a cached wheel, building from source\n"
            "Successfully installed requests-2.32.3\n"
        ),
        exit_code=0,
    )

    result = run_dispatcher(hooks_dir, payload)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_malformed_stdin_does_not_crash(tmp_path: Path) -> None:
    hooks_dir = build_isolated_hooks_dir(tmp_path)

    empty_result = run_dispatcher(hooks_dir, "")
    assert empty_result.returncode == 0, empty_result.stderr
    assert empty_result.stdout.strip() == ""

    garbage_result = run_dispatcher(hooks_dir, "this is not json at all")
    assert garbage_result.returncode == 0, garbage_result.stderr
    assert garbage_result.stdout.strip() == ""
