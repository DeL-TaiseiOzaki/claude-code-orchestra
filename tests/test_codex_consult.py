from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "_shared" / "codex_consult.py"


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
    # The wrapper's default matches .codex/config.toml rather than being
    # quietly stricter than the CLI a caller would have run by hand.
    assert payload["sandbox"] == "danger-full-access"
    assert payload["write_access"] is True
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


def test_neither_prompt_source_falls_back_to_the_label_path(tmp_path: Path) -> None:
    """Five skills hand-typed `.claude/logs/codex/prompt-{label}.md` 23 times.
    With neither flag, the wrapper reads exactly that path itself."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_codex(bin_dir, stdout="ok\n", argv_log=argv_log)
    default_prompt = tmp_path / ".claude" / "logs" / "codex" / "prompt-design.md"
    default_prompt.parent.mkdir(parents=True)
    default_prompt.write_text("Objective: from the label path", encoding="utf-8")

    result = run_codex_consult(tmp_path, ["--label", "design"], path_prefix=bin_dir)

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["ok"] is True
    recorded_argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert recorded_argv[-1] == "Objective: from the label path"


def test_neither_prompt_source_and_no_default_file_is_bad_args(tmp_path: Path) -> None:
    result = run_codex_consult(tmp_path, [])

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    # The error names the path it looked for, so the caller can either create
    # it or pass a source explicitly.
    assert "prompt-consult.md" in payload["error"]
    assert "--prompt-stdin" in payload["error"]


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


# --- prompt persistence, injectable clock, collisions, guarded writes --------


def test_prompt_is_persisted_next_to_the_response_even_from_stdin(
    tmp_path: Path,
) -> None:
    """codex-system/SKILL.md promises the prompt sits next to the response.
    On the --prompt-stdin path the prompt used to exist nowhere at all."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="an answer\n")

    result = run_codex_consult(
        tmp_path,
        ["--prompt-stdin", "--label", "stdin-case"],
        path_prefix=bin_dir,
        stdin_input="Objective: only ever on stdin",
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    prompt_file = payload["prompt_file"]
    assert not Path(prompt_file).is_absolute()
    assert prompt_file.endswith(".prompt.md")
    assert (tmp_path / prompt_file).read_text(
        encoding="utf-8"
    ) == "Objective: only ever on stdin"
    # The prompt and the response share one stem, so a reader finds the pair.
    assert prompt_file[: -len(".prompt.md")] == payload["response_file"][: -len(".md")]


def test_now_pins_the_log_filenames(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="ok\n")
    prompt_file = write_prompt(tmp_path, "Objective: pinned clock")

    result = run_codex_consult(
        tmp_path,
        [
            "--prompt-file",
            str(prompt_file),
            "--label",
            "pinned",
            "--now",
            "2026-07-25T10:00:00+00:00",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["response_file"] == ".claude/logs/codex/20260725T100000Z-pinned.md"
    assert payload["prompt_file"] == (
        ".claude/logs/codex/20260725T100000Z-pinned.prompt.md"
    )


def test_unparseable_now_is_bad_args(tmp_path: Path) -> None:
    prompt_file = write_prompt(tmp_path, "Objective: bad clock")

    result = run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file), "--now", "yesterday"]
    )

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "ISO 8601" in payload["error"]


def test_same_second_and_label_cannot_overwrite_an_earlier_response(
    tmp_path: Path,
) -> None:
    """Second-granularity names plus the default --label consult meant two
    parallel consults silently destroyed one another's answer."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    prompt_file = write_prompt(tmp_path, "Objective: collide")
    same_second = ["--now", "2026-07-25T10:00:00+00:00"]

    write_fake_codex(bin_dir, stdout="first answer\n")
    first = run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file), *same_second], path_prefix=bin_dir
    )
    write_fake_codex(bin_dir, stdout="second answer\n")
    second = run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file), *same_second], path_prefix=bin_dir
    )

    assert first.returncode == 0, first.stdout
    assert second.returncode == 0, second.stdout
    first_file = json.loads(first.stdout)["response_file"]
    second_file = json.loads(second.stdout)["response_file"]
    assert first_file != second_file
    assert (tmp_path / first_file).read_text(encoding="utf-8") == "first answer\n"
    assert (tmp_path / second_file).read_text(encoding="utf-8") == "second answer\n"


def test_unwritable_log_directory_is_json_and_exit_3(tmp_path: Path) -> None:
    """`.claude/logs` as a regular file used to produce a bare
    NotADirectoryError traceback and exit 1, which the shared exit vocabulary
    reads as 'bad arguments'."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="ok\n")
    prompt_file = write_prompt(tmp_path, "Objective: unwritable logs")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "logs").write_text("not a directory", encoding="utf-8")

    result = run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file)], path_prefix=bin_dir
    )

    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "cannot create log directory" in payload["error"]
    assert payload["artifacts"] == []
    assert result.stderr == ""


def test_unwritable_prompt_file_is_json_and_exit_3(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="ok\n")
    prompt_file = write_prompt(tmp_path, "Objective: unwritable prompt copy")
    # A directory sitting exactly where the prompt copy must go: the write
    # raises OSError, which must surface as JSON rather than a traceback.
    blocked = tmp_path / ".claude" / "logs" / "codex"
    blocked.mkdir(parents=True)
    (blocked / "20260725T100000Z-blocked.prompt.md").mkdir()

    result = run_codex_consult(
        tmp_path,
        [
            "--prompt-file",
            str(prompt_file),
            "--label",
            "blocked",
            "--now",
            "2026-07-25T10:00:00+00:00",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "cannot write" in payload["error"]
    assert result.stderr == ""


def test_success_reports_artifacts_and_a_verified_response(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="body\n", stderr="a warning\n")
    prompt_file = write_prompt(tmp_path, "Objective: artifacts")

    result = run_codex_consult(
        tmp_path, ["--prompt-file", str(prompt_file)], path_prefix=bin_dir
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["response_verified"] is True
    assert payload["artifacts"] == [
        payload["prompt_file"],
        payload["response_file"],
        payload["stderr_file"],
    ]
    for relative in payload["artifacts"]:
        assert not Path(relative).is_absolute()
        assert (tmp_path / relative).is_file()


# --- provenance: which subagent changed which files --------------------------


def init_git_repo(root: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "."],
        cwd=root,
        check=True,
        capture_output=True,
        timeout=60,
    )
    (root / "existing.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "-A"], cwd=root, check=True, capture_output=True, timeout=60
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "init",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        timeout=60,
    )


def write_editing_fake_codex(bin_dir: Path, target: Path) -> None:
    """A fake codex that edits a file, the way a real unrestricted run would."""
    script = bin_dir / "codex"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        f"pathlib.Path({str(target)!r}).write_text('written by the callee\\n')\n"
        "print('TL;DR done')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def test_the_files_the_callee_edited_are_reported(tmp_path: Path) -> None:
    """Unrestricted access is only acceptable because the edit is recorded."""
    init_git_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_editing_fake_codex(bin_dir, tmp_path / "existing.py")
    prompt_file = write_prompt(tmp_path, "Objective: fix it")

    result = run_codex_consult(
        tmp_path,
        ["--prompt-file", str(prompt_file), "--caller", "general-purpose-opus"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["caller"] == "general-purpose-opus"
    assert payload["label"] == "consult"
    assert payload["edits"]["tracked"] is True
    assert payload["edits"]["changed_files"] == ["existing.py"]
    assert payload["edits"]["files_total"] == 1


def test_caller_falls_back_to_the_environment(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, stdout="ok\n")
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_codex_consult(
        tmp_path,
        ["--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
        env_overrides={"ORCHESTRA_CALLER": "feature-lead"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["caller"] == "feature-lead"


def test_read_only_is_still_available_as_an_explicit_opt_in(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_codex(bin_dir, stdout="ok\n", argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: review")

    result = run_codex_consult(
        tmp_path,
        ["--prompt-file", str(prompt_file), "--sandbox", "read-only"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["sandbox"] == "read-only"
    assert payload["write_access"] is False
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    # Always sent explicitly, whichever value is in force.
    assert argv[argv.index("--sandbox") + 1] == "read-only"
