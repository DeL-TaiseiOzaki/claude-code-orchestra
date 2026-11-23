"""Behavioral tests for start-project/write_agents_md.py.

The writer converts the root AGENTS.md skeleton into the project's own file
once. These tests pin the Writer Safety Contract (dry-run default, atomic
apply, hash guard, validation before replace), the carry-forward of the role
and reference sections, and the pending-merge hand-off from install/update.
Every run is pinned to ``--project-root tmp_path``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "start-project" / "write_agents_md.py"
SKELETON = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
STATE_WITH_PENDING = (
    "# Agent State\n\n## Main Agent\n\nClaude Code\n\n"
    "## Progress Tracker\n\nRolling progress: [PROGRESS.md](../PROGRESS.md)\n\n"
    "## Pending Instruction Merge\n\n"
    "- `CLAUDE.md` backed up to `.orchestra-backup-1/CLAUDE.md` and removed\n\n"
    "## Current Feature\n\nKeep me.\n"
)
FACTS = {
    "project_name": "Acme API",
    "identity": "Acme API serves invoices to the billing team.",
    "layout": ["`src/` - application code"],
    "commands": [{"purpose": "Test", "command": "uv run pytest -q | tee log"}],
    "conventions": ["Keep public APIs backwards compatible."],
    "languages": {"user": "English", "code": "English"},
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "AGENTS.md").write_text(SKELETON, encoding="utf-8")
    state = tmp_path / ".claude" / "STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(STATE_WITH_PENDING, encoding="utf-8")
    return tmp_path


def write_input(root: Path, facts: dict) -> Path:
    path = root / "input.json"
    path.write_text(json.dumps(facts), encoding="utf-8")
    return path


def run(root: Path, *args: str) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(root), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stderr == "", result.stderr
    return result.returncode, json.loads(result.stdout)


def test_preview_is_the_default_and_changes_nothing(project: Path) -> None:
    code, payload = run(project, "--input", str(write_input(project, FACTS)))

    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["result"] == "preview"
    assert payload["agents_md_state_before"] == "skeleton"
    assert payload["sha256_before"] == sha(SKELETON)
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == SKELETON
    preview = project / payload["preview_file"]
    assert payload["artifacts"] == [payload["preview_file"]]
    assert "# Acme API — Agent Instructions" in preview.read_text(encoding="utf-8")
    assert payload["pending_merge"] == [
        "`CLAUDE.md` backed up to `.orchestra-backup-1/CLAUDE.md` and removed"
    ]


def test_apply_converts_and_carries_roles_and_references_forward(
    project: Path,
) -> None:
    code, payload = run(
        project,
        "--input",
        str(write_input(project, FACTS)),
        "--apply",
        "--expect-hash",
        sha(SKELETON),
    )

    assert code == 0, payload
    assert payload["result"] == "applied"
    assert payload["agents_md_state_after"] == "converted"
    assert payload["artifacts"] == ["AGENTS.md"]
    converted = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert converted.startswith("# Acme API — Agent Instructions\n")
    assert "_Not initialized" not in converted
    assert "- Test: `uv run pytest -q | tee log`" in converted
    assert "- Communicate with the user in English." in converted
    assert "- Keep public APIs backwards compatible." in converted
    for heading in ("## Agent Roles", "## Orchestra References"):
        carried = SKELETON.split(f"{heading}\n", 1)[1].split("\n## ", 1)[0].strip()
        assert carried in converted
    assert len(converted.splitlines()) <= 150
    # Without --resolve-pending-merge the STATE.md record stays for later.
    assert (project / ".claude/STATE.md").read_text(
        encoding="utf-8"
    ) == STATE_WITH_PENDING


def test_reapplying_the_same_facts_is_a_no_op(project: Path) -> None:
    input_file = str(write_input(project, FACTS))
    assert run(project, "--input", input_file, "--apply")[0] == 0
    converted = (project / "AGENTS.md").read_text(encoding="utf-8")

    code, payload = run(project, "--input", input_file, "--apply")

    assert code == 0, payload
    assert payload["result"] == "no-op"
    assert payload["agents_md_state_before"] == "converted"
    assert payload["artifacts"] == []
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == converted


def pending_sha(state: str) -> str:
    body = state.split("## Pending Instruction Merge\n", 1)[1].split("\n## ", 1)[0]
    return sha(body.strip("\n"))


def test_resolve_pending_merge_removes_only_that_state_section(project: Path) -> None:
    preview_code, preview = run(project, "--input", str(write_input(project, FACTS)))
    assert preview_code == 0
    assert preview["pending_merge_sha256"] == pending_sha(STATE_WITH_PENDING)

    code, payload = run(
        project,
        "--input",
        str(write_input(project, FACTS)),
        "--apply",
        "--resolve-pending-merge",
        preview["pending_merge_sha256"],
    )

    assert code == 0, payload
    assert payload["pending_merge_resolved"] is True
    assert payload["pending_merge_resolved_entries"] == preview["pending_merge"]
    assert payload["artifacts"] == ["AGENTS.md", ".claude/STATE.md"]
    state = (project / ".claude/STATE.md").read_text(encoding="utf-8")
    assert "## Pending Instruction Merge" not in state
    assert ".orchestra-backup-1" not in state
    for kept in (
        "## Main Agent",
        "## Progress Tracker",
        "## Current Feature",
        "Keep me.",
    ):
        assert kept in state


def test_resolve_pending_merge_requires_apply(project: Path) -> None:
    code, payload = run(
        project,
        "--input",
        str(write_input(project, FACTS)),
        "--resolve-pending-merge",
        pending_sha(STATE_WITH_PENDING),
    )
    assert code == 1
    assert payload["ok"] is False


def test_a_stale_pending_hash_cannot_erase_a_newer_backup_record(project: Path) -> None:
    reviewed = pending_sha(STATE_WITH_PENDING)
    state_path = project / ".claude/STATE.md"
    newer = STATE_WITH_PENDING.replace(
        "and removed\n",
        "and removed\n- `CLAUDE.local.md` backed up to `.orchestra-backup-2/CLAUDE.local.md`\n",
    )
    state_path.write_text(newer, encoding="utf-8")

    code, payload = run(
        project,
        "--input",
        str(write_input(project, FACTS)),
        "--apply",
        "--resolve-pending-merge",
        reviewed,
    )

    assert code == 3
    assert payload["ok"] is False
    assert state_path.read_text(encoding="utf-8") == newer
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == SKELETON


def test_expect_hash_mismatch_refuses_without_writing(project: Path) -> None:
    code, payload = run(
        project,
        "--input",
        str(write_input(project, FACTS)),
        "--apply",
        "--expect-hash",
        "0" * 64,
    )

    assert code == 3
    assert payload["ok"] is False
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == SKELETON


@pytest.mark.parametrize("name", ["CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"])
def test_owned_shadowing_file_blocks_the_conversion(project: Path, name: str) -> None:
    (project / name).write_text("# rules\n", encoding="utf-8")

    code, payload = run(project, "--input", str(write_input(project, FACTS)), "--apply")

    assert code == 2
    assert name in payload["error"]
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == SKELETON


def test_a_file_without_orchestra_sections_is_not_converted(project: Path) -> None:
    (project / "AGENTS.md").write_text("# Hand-written\n", encoding="utf-8")

    code, payload = run(project, "--input", str(write_input(project, FACTS)), "--apply")

    assert code == 2
    assert payload["agents_md_state_before"] == "unrecognized"
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == "# Hand-written\n"


def test_missing_agents_md_is_a_contract_violation(project: Path) -> None:
    (project / "AGENTS.md").unlink()
    code, payload = run(project, "--input", str(write_input(project, FACTS)))
    assert code == 2
    assert payload["agents_md_state_before"] == "missing"


@pytest.mark.parametrize(
    "facts",
    [
        {"identity": "no name"},
        {**FACTS, "unexpected": True},
        {**FACTS, "identity": "## Injected heading"},
        {**FACTS, "project_name": "Two\nlines"},
        {**FACTS, "commands": [{"purpose": "Run", "command": "echo `x`"}]},
        {**FACTS, "commands": [{"purpose": "Run"}]},
        {**FACTS, "conventions": "not a list"},
        {**FACTS, "languages": {"user": "Japanese", "other": "x"}},
        {**FACTS, "identity": "_Not initialized — run `/start-project` again"},
    ],
)
def test_invalid_input_is_bad_arguments(project: Path, facts: dict) -> None:
    code, payload = run(project, "--input", str(write_input(project, facts)), "--apply")

    assert code == 1, payload
    assert payload["ok"] is False
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == SKELETON


def test_a_composed_file_over_the_line_cap_is_refused(project: Path) -> None:
    facts = {**FACTS, "conventions": [f"Rule {i}." for i in range(150)]}

    code, payload = run(project, "--input", str(write_input(project, facts)), "--apply")

    assert code == 2
    assert any("150-line cap" in e for e in payload["validation_errors"])
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == SKELETON


def test_the_converted_file_passes_the_repository_gates(tmp_path: Path) -> None:
    """A converted AGENTS.md must satisfy check.sh's bootstrap checks and the
    agents-md document contract, not only the writer's own validation."""
    project = tmp_path / "repo"
    shutil.copytree(
        REPO_ROOT,
        project,
        ignore=shutil.ignore_patterns(".git", ".venv", "*cache*", "logs"),
    )
    (project / ".claude" / "logs").mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True, timeout=60)
    code, payload = run(project, "--input", str(write_input(project, FACTS)), "--apply")
    assert code == 0, payload

    check = subprocess.run(
        ["bash", str(project / "scripts" / "check.sh")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    validate = subprocess.run(
        [
            sys.executable,
            str(project / ".claude/skills/_shared/validate_doc.py"),
            "--contract",
            "agents-md",
            "--file",
            str(project / "AGENTS.md"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert check.returncode == 0, check.stdout
    assert validate.returncode == 0, validate.stdout
