"""Behavioral tests for the cross-CLI subagent wrapper.

Every test puts a fake `claude` / `agy` executable first on PATH, so the
wrapper's real argv, access mapping, and JSON contract are exercised without
any CLI installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "_shared" / "cli_consult.py"
EXECUTOR_CONTRACT_FILE = (
    REPO_ROOT / ".claude" / "skills" / "_shared" / "executor_contract.md"
)
EXECUTOR_CONTRACT = EXECUTOR_CONTRACT_FILE.read_text(encoding="utf-8")


def composed(prompt: str) -> str:
    """What the wrapper must send: the executor contract, the delimiter, then
    the caller's prompt byte for byte. Built from the asset file directly, not
    from the module under test."""
    return f"{EXECUTOR_CONTRACT.rstrip()}\n\n=== DELEGATED TASK ===\n\n{prompt}"


# Linux MAX_ARG_STRLEN (131072) minus the NUL terminator.
MAX_ARG_BYTES = 131_071
# The limit applies to the composed prompt, so the contract counts against it.
CONTRACT_OVERHEAD = len(composed("").encode("utf-8"))


def write_fake_cli(
    bin_dir: Path,
    name: str,
    *,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    sleep: float = 0.0,
    argv_log: Path | None = None,
    create_file: Path | None = None,
    env_log: Path | None = None,
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
        f"env_log = {json.dumps(str(env_log) if env_log else '')}",
        "if env_log:",
        "    import os",
        "    with open(env_log, 'w', encoding='utf-8') as f:",
        "        json.dump({'ORCHESTRA_ROLE': os.environ.get('ORCHESTRA_ROLE')}, f)",
        f"create_file = {json.dumps(str(create_file) if create_file else '')}",
        "if create_file:",
        "    with open(create_file, 'w', encoding='utf-8') as f:",
        "        f.write('written by the callee')",
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
    exact_path: str | None = None,
    stdin_input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if exact_path is not None:
        env["PATH"] = exact_path
    elif empty_path:
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


def agy_envelope(
    response: str,
    *,
    status: str = "SUCCESS",
    conversation_id: str = "conv-1",
    denied_actions: list[dict] | None = None,
) -> str:
    """The single-line envelope `agy --output-format json` prints (agy 1.5.14)."""
    envelope: dict = {
        "conversation_id": conversation_id,
        "status": status,
        "response": response,
        "duration_seconds": 1.0,
        "num_turns": 1,
    }
    if denied_actions is not None:
        envelope["denied_actions"] = denied_actions
    return json.dumps(envelope)


def init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, timeout=60)


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
    assert payload["write_access"] is True
    assert payload["error"] is None
    # The envelope's `result` is the response, not the transport wrapper.
    assert payload["response_head"] == "The answer body"
    assert payload["response_chars"] == len("The answer body")

    response_file = payload["response_file"]
    assert not Path(response_file).is_absolute()
    assert (tmp_path / response_file).read_text(encoding="utf-8") == "The answer body"
    assert response_file.startswith(".claude/logs/claude/")

    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[1:4] == ["-p", "--output-format", "json"]
    # Unrestricted by default, and the prompt is the final argv element.
    assert "--permission-mode" in argv and argv[
        argv.index("--permission-mode") + 1
    ] == ("bypassPermissions")
    assert argv[-1] == composed("Objective: review the design")


def test_claude_read_only_switches_permission_mode(tmp_path: Path) -> None:
    """--read-only is the opt-in now; it must reach the callee's own flag."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("done"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Review the design")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file), "--read-only"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["write_access"] is False
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[argv.index("--permission-mode") + 1] == "plan"


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


# --- Antigravity callee -----------------------------------------------------


def test_antigravity_parses_json_envelope(tmp_path: Path) -> None:
    """agy's answer is the envelope's `response`; the prompt is the attached
    `-p=` element, last, after every flag (a bare `-p` swallows the next one)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(
        bin_dir,
        "agy",
        stdout=agy_envelope("Antigravity answer\n", conversation_id="conv-9"),
        argv_log=argv_log,
    )
    prompt_file = write_prompt(tmp_path, "Objective: research")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file), "--model", "fast"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["cli"] == "antigravity"
    assert payload["model"] == "fast"
    assert payload["response_head"] == "Antigravity answer\n"
    assert payload["conversation_id"] == "conv-9"
    assert payload["envelope_status"] == "SUCCESS"
    # Not a resumable id: agy restores no history in print mode.
    assert payload["session_id"] is None
    assert payload["denied_actions"] == []
    assert payload["warnings"] == []
    assert payload["response_file"].startswith(".claude/logs/antigravity/")
    assert (tmp_path / payload["response_file"]).read_text(
        encoding="utf-8"
    ) == "Antigravity answer\n"

    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[-1] == "-p=" + composed("Objective: research")
    assert argv[-3:-1] == ["--output-format", "json"]
    assert argv.index("--model") < len(argv) - 3
    assert argv[argv.index("--model") + 1] == "fast"
    assert argv.count("-p") == 0


def test_antigravity_argv_order_with_every_option(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)
    media = tmp_path / "media"
    media.mkdir()
    extra = tmp_path / "extra"
    extra.mkdir()
    prompt_file = write_prompt(tmp_path, "Describe the clip")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "antigravity",
            "--prompt-file",
            str(prompt_file),
            "--model",
            "fast",
            "--add-dir",
            str(media),
            "--add-dir",
            str(extra),
            "--cli-arg=--effort",
            "--cli-arg",
            "high",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["add_dirs"] == [str(media.resolve()), str(extra.resolve())]
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[1:] == [
        "--dangerously-skip-permissions",
        "--model",
        "fast",
        f"--add-dir={media.resolve()}",
        f"--add-dir={extra.resolve()}",
        "--effort",
        "high",
        "--output-format",
        "json",
        "-p=" + composed("Describe the clip"),
    ]


def test_antigravity_write_access_is_explicitly_unrestricted(tmp_path: Path) -> None:
    """agy's own default lets a risk judge soft-deny steps; the wrapper's
    unrestricted default must say so in the call instead."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["write_access"] is True
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert "--dangerously-skip-permissions" in argv
    assert "--settings" not in argv
    assert "--mode" not in argv


def test_antigravity_read_only_sends_session_deny_rules(tmp_path: Path) -> None:
    """--read-only maps onto deny rules, the only mechanism that blocked writes
    in the probe; `--mode plan` is not read-only and must not be used."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file), "--read-only"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["write_access"] is False
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert set(settings["permissions"]["deny"]) == {
        "write_file(*)",
        "command(*)",
        "mcp(*)",
        # Reads reach outside the workspace, so the network stays closed.
        "read_url(*)",
        "execute_url(*)",
    }
    assert "--dangerously-skip-permissions" not in argv
    assert "--mode" not in argv
    assert argv[-1] == "-p=" + composed("Objective: x")


def test_antigravity_prompt_starting_with_dash_stays_attached(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "--not-a-flag\n- item one")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[-1] == "-p=" + composed("--not-a-flag\n- item one")


def test_antigravity_non_success_status_fails_and_keeps_raw_output(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    raw = agy_envelope("partial", status="ERROR")
    write_fake_cli(bin_dir, "agy", stdout=raw)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 0
    assert payload["envelope_status"] == "ERROR"
    assert "status 'ERROR'" in payload["error"]
    assert (tmp_path / payload["response_file"]).read_text(encoding="utf-8") == raw


def test_antigravity_unparseable_output_fails_but_is_saved_verbatim(
    tmp_path: Path,
) -> None:
    """Exit 0 with a changed output shape must fail closed without losing it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    prompt_file = write_prompt(tmp_path, "Objective: x")

    for raw in ("plain text answer\n", "[1, 2]", ""):
        write_fake_cli(bin_dir, "agy", stdout=raw)
        result = run_cli_consult(
            tmp_path,
            ["--cli", "antigravity", "--prompt-file", str(prompt_file)],
            path_prefix=bin_dir,
        )

        assert result.returncode == 3, raw
        payload = json.loads(result.stdout)
        assert payload["ok"] is False, raw
        assert "unparseable agy envelope" in payload["error"], raw
        assert payload["response_verified"] is True, raw
        saved = (tmp_path / payload["response_file"]).read_text(encoding="utf-8")
        assert saved == raw


def test_antigravity_empty_response_fails(tmp_path: Path) -> None:
    """A refused task still reports SUCCESS; an empty answer is the tell."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    prompt_file = write_prompt(tmp_path, "Objective: x")

    for empty in ("", "  \n"):
        write_fake_cli(bin_dir, "agy", stdout=agy_envelope(empty))
        result = run_cli_consult(
            tmp_path,
            ["--cli", "antigravity", "--prompt-file", str(prompt_file)],
            path_prefix=bin_dir,
        )

        assert result.returncode == 3, repr(empty)
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "empty response" in payload["error"]


def test_antigravity_denied_actions_become_warnings_not_failure(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    denied = [{"action": "command", "display_name": "Bash"}]
    write_fake_cli(
        bin_dir,
        "agy",
        stdout=agy_envelope("Deliverable text", denied_actions=denied),
        stderr=(
            "jetski: no output produced \u2014 a tool required the "
            '"command" permission that headless mode cannot prompt for, '
            "so it was auto-denied\n"
        ),
    )
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file), "--read-only"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["denied_actions"] == denied
    warnings = payload["warnings"]
    assert any("command (Bash)" in warning for warning in warnings), warnings
    assert any("soft denial" in warning for warning in warnings), warnings


def test_antigravity_deny_rule_message_becomes_a_warning(tmp_path: Path) -> None:
    """Hard denies appear only in the response prose, never in denied_actions."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(
        bin_dir,
        "agy",
        stdout=agy_envelope(
            "Permission denied for write_file(/x/probe.txt). "
            "Matches user-configured deny rule."
        ),
    )
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file), "--read-only"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert any("deny rule" in warning for warning in payload["warnings"])


def test_read_only_run_with_edits_warns(tmp_path: Path) -> None:
    """Provenance cannot tell writers apart, so edits under --read-only are a
    warning (possibly a concurrent writer), not a failure."""
    init_git_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(
        bin_dir, "agy", stdout=agy_envelope("ok"), create_file=tmp_path / "new.txt"
    )
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file), "--read-only"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["edits"]["created_files"] == ["new.txt"]
    assert any("under --read-only" in warning for warning in payload["warnings"])


def test_antigravity_rejects_resume(tmp_path: Path) -> None:
    """A flag the callee has no equivalent for is an argument error, not a run:
    agy accepts --conversation but restores no history in print mode."""
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file), "--resume", "abc"],
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "--resume" in payload["error"]
    assert "does not restore history" in payload["error"]


def test_add_dir_must_exist(tmp_path: Path) -> None:
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "antigravity",
            "--prompt-file",
            str(prompt_file),
            "--add-dir",
            str(tmp_path / "missing"),
        ],
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "--add-dir" in payload["error"]


def test_claude_add_dir_uses_the_attached_form(tmp_path: Path) -> None:
    """Claude's --add-dir is variadic: a separate value would let it swallow
    the positional prompt as one more directory."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("ok"), argv_log=argv_log)
    media = tmp_path / "media"
    media.mkdir()
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "claude",
            "--prompt-file",
            str(prompt_file),
            "--add-dir",
            str(media),
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert f"--add-dir={media.resolve()}" in argv
    assert argv[-1] == composed("Objective: x")


# --- Failure paths ----------------------------------------------------------


def test_nonzero_exit_captures_stderr_file(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, "agy", stdout="partial", stderr="boom\n", exit_code=4)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 4
    assert "exited with code 4" in payload["error"]
    assert (tmp_path / payload["stderr_file"]).read_text(encoding="utf-8") == "boom\n"


@pytest.mark.parametrize(
    ("cli", "binary"), [("claude", "claude"), ("antigravity", "agy")]
)
def test_timeout_is_reported_not_hung(tmp_path: Path, cli: str, binary: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, binary, stdout="late", sleep=5.0)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", cli, "--prompt-file", str(prompt_file), "--timeout", "1"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["timed_out"] is True
    assert f"{cli} timed out after 1s" in payload["error"]
    # A list on every path, so callers can iterate it without a None check.
    assert payload["denied_actions"] == []


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
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-stdin"],
        path_prefix=bin_dir,
        stdin_input="Objective: piped prompt",
    )

    assert result.returncode == 0, result.stderr
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[-1] == "-p=" + composed("Objective: piped prompt")


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


@pytest.mark.parametrize("cli", ["claude", "antigravity"])
def test_permission_flags_cannot_be_smuggled_through_cli_arg(
    tmp_path: Path, cli: str
) -> None:
    """The wrapper's own flag must stay the single statement of access."""
    prompt_file = write_prompt(tmp_path, "Objective: x")

    for smuggled in (
        "--permission-mode",
        "--dangerously-skip-permissions",
        "--sandbox",
        "--mode=plan",
        "--mode",
        "--settings={}",
        "--allowedTools=Bash",
    ):
        result = run_cli_consult(
            tmp_path,
            ["--cli", cli, "--prompt-file", str(prompt_file), f"--cli-arg={smuggled}"],
        )
        assert result.returncode == 1, smuggled
        payload = json.loads(result.stdout)
        assert "--read-only" in payload["error"], smuggled


@pytest.mark.parametrize("cli", ["claude", "antigravity"])
def test_wrapper_owned_flags_are_refused(tmp_path: Path, cli: str) -> None:
    """Prompt placement, output format, workspace, and session flags belong to
    the wrapper; a passthrough copy would contradict or break the call."""
    prompt_file = write_prompt(tmp_path, "Objective: x")

    for owned in (
        "--output-format=text",
        "--input-format",
        "-p",
        "--print",
        "--prompt=hi",
        "--add-dir=/tmp",
        "--conversation",
        "--continue",
        "-c",
        "--resume",
        "-r",
        "--prompt-interactive",
        "-i",
    ):
        result = run_cli_consult(
            tmp_path,
            ["--cli", cli, "--prompt-file", str(prompt_file), f"--cli-arg={owned}"],
        )
        assert result.returncode == 1, owned
        payload = json.loads(result.stdout)
        assert "wrapper sets this flag" in payload["error"], owned


@pytest.mark.parametrize("cli", ["claude", "antigravity"])
def test_bare_option_terminator_is_refused(tmp_path: Path, cli: str) -> None:
    """A passthrough `--` would turn agy's `--output-format json -p=...` into
    stray positionals (agy exits 2); refuse it before spawning."""
    prompt_file = write_prompt(tmp_path, "Objective: x")

    for terminator in ("--", "-"):
        result = run_cli_consult(
            tmp_path,
            [
                "--cli",
                cli,
                "--prompt-file",
                str(prompt_file),
                f"--cli-arg={terminator}",
            ],
        )
        assert result.returncode == 1, terminator
        payload = json.loads(result.stdout)
        assert "end option parsing" in payload["error"], terminator


def test_exact_denylist_does_not_overmatch(tmp_path: Path) -> None:
    """`mode` is a substring of `--model`; exact entries must not catch it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "antigravity",
            "--prompt-file",
            str(prompt_file),
            "--cli-arg=--model=fast",
            "--cli-arg=--fallback-model",
            "--cli-arg",
            "slow",
            "--cli-arg=--effort",
            "--cli-arg",
            "high",
            "--cli-arg=--print-timeout=60s",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    for forwarded in (
        "--model=fast",
        "--fallback-model",
        "--effort",
        "--print-timeout=60s",
    ):
        assert forwarded in argv, forwarded
    assert argv[-1] == "-p=" + composed("Objective: x")


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


# --- prompt persistence, injectable clock, collisions, guarded writes --------


def test_prompt_is_persisted_next_to_the_response_even_from_stdin(
    tmp_path: Path,
) -> None:
    """A consult must stay diagnosable: on the --prompt-stdin path the prompt
    that was actually sent used to exist nowhere at all."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("an answer"))

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-stdin", "--label", "stdin-case"],
        path_prefix=bin_dir,
        stdin_input="Objective: only ever on stdin",
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    prompt_file = payload["prompt_file"]
    assert not Path(prompt_file).is_absolute()
    # What is persisted is what was sent: the composed executor prompt.
    assert (tmp_path / prompt_file).read_text(encoding="utf-8") == composed(
        "Objective: only ever on stdin"
    )
    assert prompt_file[: -len(".prompt.md")] == payload["response_file"][: -len(".md")]


def test_now_pins_the_log_filenames(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"))
    prompt_file = write_prompt(tmp_path, "Objective: pinned clock")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "antigravity",
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
    assert (
        payload["response_file"]
        == ".claude/logs/antigravity/20260725T100000Z-pinned.md"
    )
    assert payload["prompt_file"] == (
        ".claude/logs/antigravity/20260725T100000Z-pinned.prompt.md"
    )


def test_unparseable_now_is_bad_args(tmp_path: Path) -> None:
    prompt_file = write_prompt(tmp_path, "Objective: bad clock")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file), "--now", "yesterday"],
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
    base = ["--cli", "antigravity", "--prompt-file", str(prompt_file), *same_second]

    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("first answer"))
    first = run_cli_consult(tmp_path, base, path_prefix=bin_dir)
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("second answer"))
    second = run_cli_consult(tmp_path, base, path_prefix=bin_dir)

    assert first.returncode == 0, first.stdout
    assert second.returncode == 0, second.stdout
    first_file = json.loads(first.stdout)["response_file"]
    second_file = json.loads(second.stdout)["response_file"]
    assert first_file != second_file
    assert (tmp_path / first_file).read_text(encoding="utf-8") == "first answer"
    assert (tmp_path / second_file).read_text(encoding="utf-8") == "second answer"


def test_unwritable_log_directory_is_json_and_exit_3(tmp_path: Path) -> None:
    """`.claude/logs` as a regular file used to produce a bare
    NotADirectoryError traceback and exit 1, which the shared exit vocabulary
    reads as 'bad arguments'."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("hi"))
    prompt_file = write_prompt(tmp_path, "Objective: unwritable logs")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "logs").write_text("not a directory", encoding="utf-8")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
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
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("hi"))
    prompt_file = write_prompt(tmp_path, "Objective: unwritable prompt copy")
    blocked = tmp_path / ".claude" / "logs" / "claude"
    blocked.mkdir(parents=True)
    (blocked / "20260725T100000Z-blocked.prompt.md").mkdir()

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "claude",
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
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("body"), stderr="warn\n")
    prompt_file = write_prompt(tmp_path, "Objective: artifacts")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
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


# --- argv-size guard, exec failures, Python 3.10 clock parsing ---------------


@pytest.mark.parametrize(
    ("cli", "prompt"),
    [
        # One byte past the limit once agy's attached "-p=" is counted.
        ("antigravity", "x" * (MAX_ARG_BYTES - len("-p=") - CONTRACT_OVERHEAD + 1)),
        ("claude", "x" * (MAX_ARG_BYTES - CONTRACT_OVERHEAD + 1)),
        # The limit is in bytes: ~43.7k Japanese characters already exceed it.
        ("antigravity", "あ" * (MAX_ARG_BYTES // 3)),
    ],
)
def test_over_long_prompt_is_refused_before_spawning(
    tmp_path: Path, cli: str, prompt: str
) -> None:
    """E2BIG used to escape subprocess.run as a traceback with no JSON."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, prompt)

    result = run_cli_consult(
        tmp_path,
        ["--cli", cli, "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"].startswith("prompt exceeds the single-argv limit")
    assert "absolute path" in payload["error"]
    assert result.stderr == ""
    assert not argv_log.exists()
    assert not (tmp_path / ".claude" / "logs").exists()


def test_prompt_at_the_argv_limit_still_runs(tmp_path: Path) -> None:
    """The guard is exact: the largest element Linux accepts is not refused."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)
    prompt = "x" * (MAX_ARG_BYTES - len("-p=") - CONTRACT_OVERHEAD)
    prompt_file = write_prompt(tmp_path, prompt)

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert len(argv[-1].encode("utf-8")) == MAX_ARG_BYTES


def test_callee_that_cannot_be_executed_is_json_and_exit_3(tmp_path: Path) -> None:
    """An exec failure (here ENOEXEC) is an external failure, not a traceback,
    and never falls through to a later `agy` on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    garbage = bin_dir / "agy"
    garbage.write_bytes(b"\x00\x01not an executable format\n")
    garbage.chmod(0o755)
    # A later, working `agy` that exec's own PATH walk would have started.
    fallback_dir = tmp_path / "fallback_bin"
    fallback_dir.mkdir()
    fallback_log = tmp_path / "fallback-ran.json"
    fallback = fallback_dir / "agy"
    fallback.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"open({str(fallback_log)!r}, 'w').write('ran')\n"
        f"sys.stdout.write({agy_envelope('ok')!r})\n",
        encoding="utf-8",
    )
    fallback.chmod(0o755)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "antigravity", "--prompt-file", str(prompt_file)],
        exact_path=f"{bin_dir}{os.pathsep}{fallback_dir}",
    )

    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] is None
    assert "cannot start antigravity" in payload["error"]
    assert payload["denied_actions"] == []
    assert result.stderr == ""
    assert not fallback_log.exists()
    assert (tmp_path / payload["prompt_file"]).is_file()


def test_now_accepts_a_zulu_suffix_on_python_310(tmp_path: Path) -> None:
    """3.10's fromisoformat rejects "Z"; the wrapper must not depend on 3.11."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("ok"))
    prompt_file = write_prompt(tmp_path, "Objective: zulu")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "claude",
            "--prompt-file",
            str(prompt_file),
            "--label",
            "zulu",
            "--now",
            "2026-07-25T10:00:00Z",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["response_file"] == ".claude/logs/claude/20260725T100000Z-zulu.md"


def test_claude_payload_keeps_its_shape_and_gains_no_agy_fields(
    tmp_path: Path,
) -> None:
    """Shared code paths changed; Claude's argv and result must not."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("body"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file), "--model", "opus"],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["warnings"] == []
    assert payload["denied_actions"] == []
    assert payload["conversation_id"] is None
    assert payload["envelope_status"] is None
    assert payload["add_dirs"] == []
    argv = json.loads(argv_log.read_text(encoding="utf-8"))
    assert argv[1:] == [
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        "opus",
        composed("Objective: x"),
    ]


@pytest.mark.parametrize("cli", ["claude", "antigravity"])
def test_remote_session_flags_are_refused(tmp_path: Path, cli: str) -> None:
    """--remote-agent / --remote-control move where the session runs, so the
    wrapper's own call can no longer be the visible statement of it."""
    prompt_file = write_prompt(tmp_path, "Objective: x")

    for remote in (
        "--remote-agent",
        "--remote-agent=cloud",
        "--remote-control",
        "--remote-control=on",
    ):
        result = run_cli_consult(
            tmp_path,
            ["--cli", cli, "--prompt-file", str(prompt_file), f"--cli-arg={remote}"],
        )
        assert result.returncode == 1, remote
        payload = json.loads(result.stdout)
        assert "wrapper sets this flag" in payload["error"], remote


@pytest.mark.parametrize(
    "log_flag", ["--log-file", "--log-file=/tmp/agy.log", "--LOG-FILE=x"]
)
def test_log_file_flag_is_refused(tmp_path: Path, log_flag: str) -> None:
    """agy's --log-file makes the process itself write to any path; no deny
    rule covers that, so a --read-only run could still write outside the repo."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "agy", stdout=agy_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = run_cli_consult(
        tmp_path,
        [
            "--cli",
            "antigravity",
            "--prompt-file",
            str(prompt_file),
            "--read-only",
            f"--cli-arg={log_flag}",
        ],
        path_prefix=bin_dir,
    )

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert "write its own log" in payload["error"], log_flag
    assert not argv_log.exists()
    assert not (tmp_path / ".claude" / "logs" / "antigravity").exists()


# --- agy_envelope.py: the parsing half, also runnable offline ----------------

AGY_ENVELOPE_SCRIPT = SCRIPT.with_name("agy_envelope.py")


def run_agy_envelope(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(AGY_ENVELOPE_SCRIPT),
            "--project-root",
            str(tmp_path),
            *args,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_agy_envelope_cli_accepts_a_success_envelope(tmp_path: Path) -> None:
    (tmp_path / "out.json").write_text(agy_envelope("Deliverable"), encoding="utf-8")

    result = run_agy_envelope(tmp_path, "--stdout-file", "out.json")

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["status"] == "SUCCESS"
    assert payload["warnings"] == []


def test_agy_envelope_cli_reports_warnings_from_stderr_and_denials(
    tmp_path: Path,
) -> None:
    denied = [{"action": "command", "display_name": "Bash"}]
    (tmp_path / "out.json").write_text(
        agy_envelope("Deliverable", denied_actions=denied), encoding="utf-8"
    )
    (tmp_path / "err.txt").write_text("tool was auto-denied\n", encoding="utf-8")

    result = run_agy_envelope(
        tmp_path, "--stdout-file", "out.json", "--stderr-file", "err.txt"
    )

    assert result.returncode == 0, result.stdout
    warnings = json.loads(result.stdout)["warnings"]
    assert any("command (Bash)" in warning for warning in warnings), warnings
    assert any("soft denial" in warning for warning in warnings), warnings


def test_agy_envelope_cli_fails_closed_on_an_unusable_envelope(tmp_path: Path) -> None:
    for name, text, expected in (
        ("garbage.json", "not json", "unparseable agy envelope"),
        ("empty.json", agy_envelope("  "), "empty response"),
        ("bad.json", agy_envelope("x", status="ERROR"), "reported status"),
    ):
        (tmp_path / name).write_text(text, encoding="utf-8")

        result = run_agy_envelope(tmp_path, "--stdout-file", name)

        assert result.returncode == 3, name
        payload = json.loads(result.stdout)
        assert payload["ok"] is False, name
        assert expected in payload["error"], name


def test_agy_envelope_cli_missing_input_is_bad_args(tmp_path: Path) -> None:
    result = run_agy_envelope(tmp_path, "--stdout-file", "absent.json")

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


# --- executor contract -------------------------------------------------------


@pytest.mark.parametrize("cli", ["claude", "antigravity"])
def test_every_prompt_carries_the_executor_contract_and_the_executor_role(
    tmp_path: Path, cli: str
) -> None:
    """A delegated `claude -p` auto-loads AGENTS.md and `.claude/rules/`, the
    main-agent contract included; the injected contract and the environment
    are what make it an executor instead of a second main agent."""
    import hashlib

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    env_log = tmp_path / "env.json"
    stdout = claude_envelope("ok") if cli == "claude" else agy_envelope("ok")
    name = "claude" if cli == "claude" else "agy"
    write_fake_cli(bin_dir, name, stdout=stdout, argv_log=argv_log, env_log=env_log)
    prompt_file = write_prompt(tmp_path, "Objective: role check")

    env_prefix = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(tmp_path),
            "--cli",
            cli,
            "--prompt-file",
            str(prompt_file),
        ],
        stdin=subprocess.DEVNULL,
        env={**os.environ, "PATH": env_prefix, "ORCHESTRA_ROLE": "main"},
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout
    sent = json.loads(argv_log.read_text(encoding="utf-8"))[-1]
    sent = sent.removeprefix("-p=")
    assert sent.startswith(EXECUTOR_CONTRACT.rstrip())
    assert sent.count("=== DELEGATED TASK ===") == 1
    assert sent.count("## Handoff Rules") == 1
    assert sent.endswith("\n\nObjective: role check")
    assert json.loads(env_log.read_text(encoding="utf-8")) == {
        "ORCHESTRA_ROLE": "executor"
    }
    payload = json.loads(result.stdout)
    assert (
        payload["executor_contract_sha"]
        == hashlib.sha256(EXECUTOR_CONTRACT.encode("utf-8")).hexdigest()
    )


def test_an_already_composed_prompt_is_not_wrapped_twice(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, composed("Objective: once"))

    result = run_cli_consult(
        tmp_path,
        ["--cli", "claude", "--prompt-file", str(prompt_file)],
        path_prefix=bin_dir,
    )

    assert result.returncode == 0, result.stdout
    assert json.loads(argv_log.read_text(encoding="utf-8"))[-1] == composed(
        "Objective: once"
    )


def test_missing_executor_contract_fails_before_spawning(tmp_path: Path) -> None:
    import shutil

    shared = tmp_path / "shared"
    shutil.copytree(SCRIPT.parent, shared, ignore=shutil.ignore_patterns("__pycache__"))
    (shared / "executor_contract.md").write_text("  \n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_log = tmp_path / "argv.json"
    write_fake_cli(bin_dir, "claude", stdout=claude_envelope("ok"), argv_log=argv_log)
    prompt_file = write_prompt(tmp_path, "Objective: x")

    result = subprocess.run(
        [
            sys.executable,
            str(shared / "cli_consult.py"),
            "--project-root",
            str(tmp_path),
            "--cli",
            "claude",
            "--prompt-file",
            str(prompt_file),
        ],
        stdin=subprocess.DEVNULL,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "executor contract" in payload["error"]
    assert not argv_log.exists()
