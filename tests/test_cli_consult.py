"""Behavioral tests for the cross-CLI subagent wrapper.

Every test puts a fake `claude` / `gemini` executable first on PATH, so the
wrapper's real argv, access mapping, and JSON contract are exercised without
any CLI installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents" / "skills" / "_shared" / "cli_consult.py"


def write_fake_cli(
    bin_dir: Path,
    name: str,
    *,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    sleep: float = 0.0,
    argv_log: Path | None = None,
) -> Path:
    """Write a fake CLI executable named *name* into *bin_dir*.

    Uses ``repr()``/``json.dumps`` to embed arguments as literals so content
    with quotes, braces, or newlines round-trips into the generated script.
    """
    script = bin_dir / name
    lines = [
        "#!/usr/bin/env python3",
        "import json",
        "import sys",
        "import time",
        f"argv_log = {json.dumps(str(argv_log) if argv_log else '')}",
        "if argv_log:",
        "    with open(argv_log, 'w', encoding='utf-8') as f:",
        "        json.dump(sys.argv, f)",
        f"time.sleep({sleep!r})",
        f"sys.stdout.write({stdout!r})",
        f"sys.stderr.write({stderr!r})",
        f"sys.exit({exit_code!r})",
        "",
    ]
    script.write_text("\n".join(lines), encoding="utf-8")
    script.chmod(0o755)
    return script


def run_cli_consult(
    tmp_path: Path,
    args: list[str],
    *,
    path_prefix: Path | None = None,
    empty_path: bool = False,
    stdin_input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if empty_path:
        empty_bin = tmp_path / "empty_bin"
        empty_bin.mkdir(exist_ok=True)
        env["PATH"] = str(empty_bin)
    elif path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(tmp_path), *args],
        input=stdin_input,
        stdin=subprocess.DEVNULL if stdin_input is None else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def write_prompt(tmp_path: Path, text: str) -> Path:
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text(text, encoding="utf-8")
    return prompt_file


def claude_envelope(result: str, *, session_id: str = "sess-1", is_error: bool = False):
    return json.dumps(
        {
            "type": "result",
            "result": result,
            "session_id": session_id,
            "is_error": is_error,
        }
    )


# --- Claude Code callee -----------------------------------------------------


def test_claude_success_reports_result_and_session_id(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(
        bin_dir,
        "claude",
        stdout=claude_envelope("The answer body", session_id="abc-123"),
        argv_log=argv_log,
    )
    prompt_file = write_prompt(tmp_path, "Objective: review the design")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file), "--label", "unit-test"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["cli"] == "claude"
    assert payload["session_id"] == "abc-123"
    assert payload["write_access"] is False
    assert payload["error"] is None
    # The envelope's `result` is the response, not the transport wrapper.
    assert payload["response_head"] == "The answer body"
    assert payload["response_chars"] == len("The answer body")

    response_file = payload["response_file"]
    assert not Path(response_file).is_absolute()
    assert (tmp_path / response_file).read_text(encoding="utf-8") == "The answer body"
    assert response_file.startswith(".agents/logs/claude/")

    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[1:4] == ["-p", "--output-format", "json"]
    # Read-only by default, and the prompt is the final argv element.
    assert "--permission-mode" in argv and argv[
        argv.index("--permission-mode") + 1
    ] == ("plan")
    assert argv[-1] == "Objective: review the design"


def test_claude_write_access_switches_permission_mode(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("done"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Implement the fix")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file), "--write-access"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["write_access"] is True
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"


def test_claude_is_error_envelope_fails_even_on_exit_zero(tmp_path: Path) -> None:
    """A callee that exits 0 while reporting an error must not read as success."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(
        bin_dir,
        "claude",
        stdout=claude_envelope("hit the turn limit", is_error=True),
        exit_code=0,
    )
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 0
    assert "error" in payload["error"]


def test_claude_unparseable_stdout_is_kept_verbatim(tmp_path: Path) -> None:
    """A changed output shape must never be reported as an empty answer."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, "claude", stdout="not json at all\n")
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["response_head"] == "not json at all\n"
    assert payload["session_id"] is None


# --- Gemini callee ----------------------------------------------------------


def test_gemini_captures_text_output_and_approval_mode(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "gemini", stdout="Gemini answer\n", argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: research")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "gemini", "--prompt-file", str(prompt_file), "--model", "flash"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["cli"] == "gemini"
    assert payload["model"] == "flash"
    assert payload["response_head"] == "Gemini answer\n"
    assert payload["response_file"].startswith(".agents/logs/gemini/")

    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[1] == "-p"
    assert argv[argv.index("--approval-mode") + 1] == "default"
    assert argv[argv.index("--model") + 1] == "flash"


def test_gemini_rejects_resume(tmp_path: Path) -> None:
    """A flag the callee has no equivalent for is an argument error, not a run."""
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "gemini", "--prompt-file", str(prompt_file), "--resume", "abc"],
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "--resume" in payload["error"]


# --- Failure paths ----------------------------------------------------------


def test_nonzero_exit_captures_stderr_file(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, "gemini", stdout="partial", stderr="boom\n", exit_code=4)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "gemini", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 4
    assert "exited with code 4" in payload["error"]
    assert (tmp_path / payload["stderr_file"]).read_text(encoding="utf-8") == "boom\n"


def test_timeout_is_reported_not_hung(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, "claude", stdout="late", sleep=5.0)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file), "--timeout", "1"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["timed_out"] is True
    assert "timed out after 1s" in payload["error"]


def test_missing_cli_is_exit_2_with_install_hint(tmp_path: Path) -> None:
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file)],
        empty_path=True,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "not found on PATH" in payload["error"]
    assert "npm install" in payload["error"]


def test_codex_is_not_accepted_here(tmp_path: Path) -> None:
    """Codex keeps its own wrapper, so there is one implementation per callee."""
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path, ["--cli", "codex", "--prompt-file", str(prompt_file)]
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "codex" in payload["error"]


def test_prompt_stdin_is_accepted(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "gemini", stdout="ok", argv_log=argv_log)

    result = run_cli_consult(
        tmp_path,
        ["--cli", "gemini", "--prompt-stdin"],
        path_prefix=bin_dir,
        stdin_input="Objective: piped prompt",
    )

    assert result.returncode == 0, result.stderr
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[-1] == "Objective: piped prompt"


def test_both_prompt_sources_is_an_argument_error(tmp_path: Path) -> None:
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "claude",
            "--prompt-file",
            str(prompt_file),
            "--prompt-stdin",
        ],
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


def test_bad_label_is_rejected_before_running(tmp_path: Path) -> None:
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "claude",
            "--prompt-file",
            str(prompt_file),
            "--label",
            "../escape",
        ],
    )

    assert result.returncode == 1
    assert "--label" in json.loads(result.stdout)["error"]


def test_permission_flags_cannot_be_smuggled_through_cli_arg(tmp_path: Path) -> None:
    """--write-access must stay the single visible statement of access."""
    prompt_file = write_prompt(tmp_path, "Objective: x")

    for smuggled in ("--permission-mode", "--yolo", "--approval-mode=yolo"):
        result = run_cli_consult(
            tmp_path,
            [
                "--cli",
                "claude",
                "--prompt-file",
                str(prompt_file),
                f"--cli-arg={smuggled}",
            ],
        )
        assert result.returncode == 1, smuggled
        payload = json.loads(result.stdout)
        assert "--write-access" in payload["error"], smuggled


def test_cli_arg_passthrough_reaches_the_callee(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "claude",
            "--prompt-file",
            str(prompt_file),
            "--cli-arg=--max-turns",
            "--cli-arg",
            "8",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[argv.index("--max-turns") + 1] == "8"
