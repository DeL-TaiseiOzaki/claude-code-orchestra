from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents" / "skills" / "_shared" / "codex_consult.py"


def write_fake_codex(
    bin_dir: Path,
    *,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    sleep: float = 0.0,
    argv_log: Path | None = None,
) -> Path:
    """Write a fake ``codex`` executable into *bin_dir* for test isolation.

    Uses ``repr()`` (not str.format) to embed the string arguments as Python
    literals, so stdout/stderr content containing quotes, braces, or newlines
    round-trips into the generated script safely.
    """
    script = bin_dir / "codex"
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


def run_codex_consult(
    tmp_path: Path,
    args: list[str],
    *,
    path_prefix: Path | None = None,
    no_codex: bool = False,
    env_overrides: dict[str, str] | None = None,
    stdin_input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    if no_codex:
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


def write_prompt(tmp_path: Path, text: str, name: str = "prompt.txt") -> Path:
    prompt_file = tmp_path / name
    prompt_file.write_text(text, encoding="utf-8")
    return prompt_file


def test_success_writes_response_and_reports_head(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="Codex response body\n", exit_code=0)
    prompt_file = write_prompt(tmp_path, "Objective: do the thing")

    result = run_codex_consult(
        tmp_path,
        ["--prompt-file", str(prompt_file), "--label", "unit-test"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["model"] == "gpt-5.6-sol"
    assert payload["sandbox"] == "read-only"
    assert payload["write_access"] is False
    assert payload["timed_out"] is False
    assert payload["error"] is None
    assert "Codex response body" in payload["response_head"]
    assert payload["response_chars"] == len("Codex response body\n")
    assert payload["stderr_file"] is None

    response_file = payload["response_file"]
    assert not Path(response_file).is_absolute()
    response_path = tmp_path / response_file
    assert response_path.is_file()
    assert response_path.read_text(encoding="utf-8") == "Codex response body\n"


def test_nonzero_exit_captures_stderr_and_fails(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(
        bin_dir, stdout="partial\n", stderr="boom: something broke\n", exit_code=1
    )
    prompt_file = write_prompt(tmp_path, "Objective: fail please")

    result = run_codex_consult(
        tmp_path,
        ["--prompt-file", str(prompt_file), "--label", "fail-case"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert payload["timed_out"] is False
    assert payload["error"]
    assert "1" in payload["error"]

    assert payload["stderr_file"] is not None
    assert not Path(payload["stderr_file"]).is_absolute()
    stderr_path = tmp_path / payload["stderr_file"]
    assert stderr_path.is_file()
    assert "boom" in stderr_path.read_text(encoding="utf-8")


def test_timeout_reports_timed_out_and_persists_output(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, sleep=30.0, stdout="should never fully print")
    prompt_file = write_prompt(tmp_path, "Objective: hang forever")

    result = run_codex_consult(
        tmp_path,
        [
            "--prompt-file",
            str(prompt_file),
            "--label",
            "hang-case",
            "--timeout",
            "1",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["timed_out"] is True
    assert "timed out" in payload["error"]

    # Whatever was captured before the kill must still be persisted.
    response_path = tmp_path / payload["response_file"]
    assert response_path.is_file()


def test_codex_missing_from_path_reports_actionable_error(tmp_path: Path) -> None:
    prompt_file = write_prompt(tmp_path, "Objective: anything")

    result = run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file)], no_codex=True
    )

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "npm install -g @openai/codex@latest" in payload["error"]


def test_both_prompt_sources_is_bad_args(tmp_path: Path) -> None:
    prompt_file = write_prompt(tmp_path, "x")

    result = run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file), "--prompt-stdin"]
    )

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "exactly one" in payload["error"]


def test_neither_prompt_source_is_bad_args(tmp_path: Path) -> None:
    result = run_codex_consult(tmp_path, [])

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "exactly one" in payload["error"]


def test_prompt_stdin_reads_prompt_from_stdin(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="ok from stdin prompt\n")

    result = run_codex_consult(
        tmp_path,
        ["--prompt-stdin"],
        path_prefix=bin_dir,
        stdin_input="Objective: via stdin",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_prompt_with_nested_quotes_and_newline_round_trips_byte_identical(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    tricky_prompt = (
        "Objective: handle \"double quotes\" and 'single quotes' together\n"
        "Second line with a trailing backslash \\ and a $variable and `backticks`"
    )
    write_fake_codex(bin_dir, stdout="ok\n", argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, tricky_prompt)

    result = run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file)], path_prefix=bin_dir
    )

    assert result.returncode == 0, result.stderr
    recorded_argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert recorded_argv[-1] == tricky_prompt


def test_codex_model_env_var_is_honoured_and_flag_overrides_it(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="ok\n")
    prompt_file = write_prompt(tmp_path, "Objective: model check")

    env_result = run_codex_consult(
        tmp_path,
        ["--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
        env_overrides={"CODEX_MODEL": "gpt-custom-env"},
    )
    assert env_result.returncode == 0, env_result.stderr
    env_payload = json.loads(env_result.stdout)
    assert env_payload["model"] == "gpt-custom-env"

    override_result = run_codex_consult(
        tmp_path,
        ["--prompt-file", str(prompt_file), "--model", "gpt-explicit"],
        path_prefix=bin_dir,
        env_overrides={"CODEX_MODEL": "gpt-custom-env"},
    )
    assert override_result.returncode == 0, override_result.stderr
    override_payload = json.loads(override_result.stdout)
    assert override_payload["model"] == "gpt-explicit"


def test_skip_git_repo_check_is_forwarded_before_the_prompt(tmp_path: Path) -> None:
    """A non-git working directory is the one case that genuinely needs an
    extra codex flag, so the wrapper forwards it explicitly rather than
    forcing callers back to a raw `codex exec`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_codex(bin_dir, stdout="ok\n", argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: anything")

    result = run_codex_consult(
        tmp_path,
        ["--prompt-file", str(prompt_file), "--skip-git-repo-check"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    recorded_argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert "--skip-git-repo-check" in recorded_argv
    # The prompt must stay the final element so it is never parsed as a flag.
    assert recorded_argv[-1] == "Objective: anything"


def test_skip_git_repo_check_is_absent_by_default(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_codex(bin_dir, stdout="ok\n", argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: anything")

    run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file)], path_prefix=bin_dir
    )

    recorded_argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert "--skip-git-repo-check" not in recorded_argv


def test_config_overrides_are_forwarded_in_order(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_codex(bin_dir, stdout="ok\n", argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: anything")

    result = run_codex_consult(
        tmp_path,
        [
            "--prompt-file",
            str(prompt_file),
            "--config",
            "model_reasoning_effort=low",
            "--config",
            "hide_agent_reasoning=true",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv.count("--config") == 2
    assert argv[argv.index("--config") + 1] == "model_reasoning_effort=low"
    assert argv[-1] == "Objective: anything"


def test_config_override_touching_sandbox_is_refused(tmp_path: Path) -> None:
    """--sandbox must remain the single visible statement of write access, so
    a --config override that could contradict it is rejected outright."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="ok\n")
    prompt_file = write_prompt(tmp_path, "Objective: anything")

    for denied in ("sandbox_mode=danger-full-access", "approval_policy=never"):
        result = run_codex_consult(
            tmp_path,
            ["--prompt-file", str(prompt_file), "--config", denied],
            path_prefix=bin_dir,
        )
        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "refused" in payload["error"]


def test_malformed_config_override_is_bad_args(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="ok\n")
    prompt_file = write_prompt(tmp_path, "Objective: anything")

    for bad in ("no-equals-sign", "=novalue", "key="):
        result = run_codex_consult(
            tmp_path,
            ["--prompt-file", str(prompt_file), "--config", bad],
            path_prefix=bin_dir,
        )
        assert result.returncode == 1, result.stderr
        assert json.loads(result.stdout)["ok"] is False
