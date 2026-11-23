"""scripts/update.sh and the project-owned root AGENTS.md.

Root AGENTS.md belongs to the project once /start-project converts it, so the
updater replaces it only while it is byte-identical to a shipped skeleton.
CLAUDE.md, CLAUDE.local.md, and .claude/CLAUDE.md stop Claude Code from loading
AGENTS.md, so the updater backs them up, removes them, and records the backups
for /start-project. Template policy keeps flowing through `.claude/rules/`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_install_script import (
    REPO_ROOT,
    build_template_repo,
    install_project_for_update,
    run_update,
)

SKELETON_MARKER = "_Not initialized — run `/start-project`"
FACTS = {
    "project_name": "Acme API",
    "identity": "Acme API serves invoices to the billing team.",
    "commands": [{"purpose": "Test", "command": "uv run pytest"}],
}


def commit_template(template: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(template), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(template), "commit", "-qm", message], check=True)


def convert_agents_md(target: Path) -> str:
    """Run the start-project writer in *target* and return the converted file."""
    input_file = target / ".claude" / "logs" / "agents-input.json"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_text(json.dumps(FACTS), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(target / ".claude/skills/start-project/write_agents_md.py"),
            "--project-root",
            str(target),
            "--input",
            str(input_file),
            "--apply",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    return (target / "AGENTS.md").read_text(encoding="utf-8")


def bump_rules(template: Path) -> str:
    marker = "\n<!-- template rule update -->\n"
    rule = template / ".claude/rules/orchestration.md"
    rule.write_text(rule.read_text(encoding="utf-8") + marker, encoding="utf-8")
    return marker


def test_update_never_rewrites_a_converted_agents_md(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    converted = convert_agents_md(target)
    marker = bump_rules(template)
    (template / "AGENTS.md").write_text(
        (template / "AGENTS.md").read_text(encoding="utf-8") + "\nNew skeleton line.\n",
        encoding="utf-8",
    )
    commit_template(template, "template change")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == converted
    assert "Preserved project-owned AGENTS.md" in result.stdout
    assert marker in (target / ".claude/rules/orchestration.md").read_text(
        encoding="utf-8"
    )


def test_update_replaces_an_unconverted_known_skeleton(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    new_skeleton = (
        (template / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace(
            "# Project — Agent Instructions", "# Project — Agent Instructions (v2)"
        )
    )
    (template / "AGENTS.md").write_text(new_skeleton, encoding="utf-8")
    commit_template(template, "new skeleton")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == new_skeleton
    assert list(target.glob(".orchestra-backup-instructions-*")) == []


def test_update_replaces_a_previously_shipped_agents_md_version(tmp_path: Path) -> None:
    """Projects on an older release hold the old self-contained CLI contract;
    it is template content, so it becomes the skeleton without a backup."""
    old = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-p", "762ecb5:AGENTS.md"],
        capture_output=True,
        text=True,
        check=False,
    )
    if old.returncode != 0:
        pytest.skip("commit 762ecb5 is not in this clone's history")
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    (target / "AGENTS.md").write_text(old.stdout, encoding="utf-8")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert SKELETON_MARKER in (target / "AGENTS.md").read_text(encoding="utf-8")
    assert list(target.glob(".orchestra-backup-instructions-*")) == []


def test_update_backs_up_removes_and_records_claude_instruction_files(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    contents = {
        "CLAUDE.md": "# Team rules\n\nAlways write tests.\n",
        "CLAUDE.local.md": "# Mine\n",
        ".claude/CLAUDE.md": "# Nested\n",
    }
    for name, content in contents.items():
        (target / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(target), "add", "CLAUDE.md"], check=True)
    subprocess.run(["git", "-C", str(target), "commit", "-qm", "add rules"], check=True)

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    backups = list(target.glob(".orchestra-backup-instructions-*"))
    assert len(backups) == 1
    state = (target / ".claude/STATE.md").read_text(encoding="utf-8")
    assert state.count("## Pending Instruction Merge") == 1
    for name, content in contents.items():
        assert not (target / name).exists(), name
        assert (backups[0] / name).read_text(encoding="utf-8") == content
        assert f"`{name}` backed up to `{backups[0].name}/{name}`" in state
        assert f"Backed up {name} to {backups[0].name}/{name}" in result.stdout
    assert "project instructions, review for merge" in state
    # A tracked CLAUDE.md is removed from the index too.
    tracked = subprocess.run(
        ["git", "-C", str(target), "ls-files", "CLAUDE.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert tracked == ""


def test_a_second_update_appends_to_the_pending_merge_section(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    (target / "CLAUDE.md").write_text("# one\n", encoding="utf-8")
    assert run_update(target, template).returncode == 0
    (target / "CLAUDE.local.md").write_text("# two\n", encoding="utf-8")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    state = (target / ".claude/STATE.md").read_text(encoding="utf-8")
    assert state.count("## Pending Instruction Merge") == 1
    assert "`CLAUDE.md` backed up to" in state
    assert "`CLAUDE.local.md` backed up to" in state


def test_update_labels_a_shipped_claude_md_as_a_template_copy(tmp_path: Path) -> None:
    shipped = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-p", "762ecb5:CLAUDE.md"],
        capture_output=True,
        text=True,
        check=False,
    )
    if shipped.returncode != 0:
        pytest.skip("commit 762ecb5 is not in this clone's history")
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    (target / "CLAUDE.md").write_text(shipped.stdout, encoding="utf-8")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert not (target / "CLAUDE.md").exists()
    assert "template copy, no merge needed" in (target / ".claude/STATE.md").read_text(
        encoding="utf-8"
    )


def test_update_keeps_a_claude_md_that_only_imports_agents_md(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    (target / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert list(target.glob(".orchestra-backup-instructions-*")) == []


def test_update_backs_up_a_legacy_zoned_agents_md_before_replacing_it(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    zoned = (
        "# Old bootstrap\n\n# @orchestra:template-boundary\n\n"
        "## Repository Identity\n\nZoned project.\n\n"
        "# @orchestra:repo-boundary\n\n## Current Project\n\nZoned state.\n"
    )
    (target / "AGENTS.md").write_text(zoned, encoding="utf-8")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert SKELETON_MARKER in (target / "AGENTS.md").read_text(encoding="utf-8")
    backups = list(target.glob(".orchestra-backup-instructions-*"))
    assert (backups[0] / "AGENTS.md").read_text(encoding="utf-8") == zoned
    state = (target / ".claude/STATE.md").read_text(encoding="utf-8")
    assert "Zoned state." in state
    assert "`AGENTS.md` (legacy zoned format) backed up to" in state


def test_update_installs_a_missing_agents_md(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    (target / "AGENTS.md").unlink()

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert (target / "AGENTS.md").read_bytes() == (template / "AGENTS.md").read_bytes()


def test_update_retires_a_symlinked_instruction_file_but_not_its_target(
    tmp_path: Path,
) -> None:
    """A CLAUDE.md-family link is backed up as a link and removed; the file
    it points to, outside the project, is never followed or deleted."""
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "CLAUDE.md").write_text("# not ours\n", encoding="utf-8")
    (target / "CLAUDE.local.md").symlink_to(outside / "CLAUDE.md")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    # The link itself is the project's file and is retired; its target is not.
    assert not (target / "CLAUDE.local.md").is_symlink()
    assert (outside / "CLAUDE.md").read_text(encoding="utf-8") == "# not ours\n"
    # The backup holds the content, readable after the move, and asks for review.
    backups = list(target.glob(".orchestra-backup-instructions-*"))
    backup = backups[0] / "CLAUDE.local.md"
    assert not backup.is_symlink()
    assert backup.read_text(encoding="utf-8") == "# not ours\n"
    assert "content copied, review for merge" in (
        target / ".claude/STATE.md"
    ).read_text(encoding="utf-8")


def test_update_keeps_a_dangling_instruction_symlink_as_a_link(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    (target / "CLAUDE.md").symlink_to("missing-rules.md")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert not (target / "CLAUDE.md").is_symlink()
    backups = list(target.glob(".orchestra-backup-instructions-*"))
    assert (backups[0] / "CLAUDE.md").is_symlink()
    assert "dangling symlink to missing-rules.md" in (
        target / ".claude/STATE.md"
    ).read_text(encoding="utf-8")
