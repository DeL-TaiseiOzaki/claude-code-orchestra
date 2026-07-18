from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_SOURCE_DIR = REPO_ROOT / ".claude" / "hooks"
DISPATCHER_NAME = "post-bash-check.py"


def build_isolated_hooks_dir(tmp_path: Path) -> Path:
    """Copy .claude/hooks/ into an isolated tmp project so log-cli-tools.py's
    LOG_DIR (Path(__file__).parent.parent / "logs") resolves under tmp_path
    instead of writing into the real repo's .claude/logs/."""
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
    assert "codex-debugger" in context


def test_pytest_failure_dedups_generic_error_hint(tmp_path: Path) -> None:
    """Coordination fix under test: when post-test-analysis already produced
    a targeted hint, the generic error-to-codex hint must be suppressed."""
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
    assert "[Codex Debug Suggestion]" in context
    assert "[Error Detected]" not in context


def test_codex_exec_command_logs_jsonl_and_confirms(tmp_path: Path) -> None:
    hooks_dir = build_isolated_hooks_dir(tmp_path)
    log_file = hooks_dir.parent / "logs" / "cli-tools.jsonl"
    payload = bash_hook_input(
        command=(
            'codex exec --model "gpt-5.6-sol" --sandbox read-only '
            '"Analyze this failure" 2>/dev/null'
        ),
        stdout="Codex analysis result here",
        exit_code=0,
    )

    result = run_dispatcher(hooks_dir, payload)

    assert result.returncode == 0, result.stderr
    assert log_file.is_file()
    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert len(entries) == 1
    assert entries[0]["tool"] == "codex"
    assert entries[0]["prompt"] == "Analyze this failure"
    assert entries[0]["success"] is True

    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "[LOG] Codex call logged" in context


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


def test_malformed_stdin_does_not_crash(tmp_path: Path) -> None:
    hooks_dir = build_isolated_hooks_dir(tmp_path)

    empty_result = run_dispatcher(hooks_dir, "")
    assert empty_result.returncode == 0, empty_result.stderr
    assert empty_result.stdout.strip() == ""

    garbage_result = run_dispatcher(hooks_dir, "this is not json at all")
    assert garbage_result.returncode == 0, garbage_result.stderr
    assert garbage_result.stdout.strip() == ""
