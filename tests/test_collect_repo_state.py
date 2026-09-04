"""Behavioural tests for catchup/collect_repo_state.py.

The headline regression: **all 15 skills reported ``short_description: ""``**
against the real repository, because the frontmatter parser skipped indented
lines (making nested ``metadata: short-description:`` unreachable) and gutted
``description: |`` block scalars. GUIDE.md's slash-command purpose column was
therefore structurally always empty, and the failure looked like a legitimately
empty field rather than a parse error.

The rest pin the datasets ``references/guide-template.md`` asks for and the
honest-degradation rules: absent, unreadable, and empty are three states, and a
failed git subcommand is never rendered as a clean tree.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "catchup" / "collect_repo_state.py"


def run(project: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--claude-home",
            str(project / "claude-home"),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def init_repo(root: Path) -> None:
    (root / "claude-home").mkdir(exist_ok=True)
    for args in (
        ["init", "-q", "."],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "T"],
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "seed.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: seed"], cwd=root, check=True)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init_repo(tmp_path)
    return tmp_path


def write_skill(root: Path, name: str, frontmatter: str) -> None:
    skill_dir = root / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\n{frontmatter}\n---\n\n# {name}\n", encoding="utf-8"
    )


# --- the frontmatter regression ---------------------------------------------


def test_every_real_skill_reports_a_purpose() -> None:
    """Run against the actual repository: the empty purpose column was the
    defect, so the fixture that matters is the repo itself."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout[-2000:]
    payload = json.loads(result.stdout)
    empty = [
        item["name"]
        for item in payload["skills"]["items"]
        if not item["short_description"]
    ]
    assert empty == [], f"skills with no purpose: {empty}"
    assert payload["skills"]["frontmatter_errors"] == []
    assert all(item["specialization"] for item in payload["agents"]["items"])


def test_nested_metadata_short_description_is_reached(project: Path) -> None:
    write_skill(
        project,
        "nested",
        "name: nested\ndescription: long form\nmetadata:\n  short-description: The short one",
    )

    payload = json.loads(run(project).stdout)

    assert payload["skills"]["items"] == [
        {
            "name": "nested",
            "short_description": "The short one",
            "file": ".claude/skills/nested/SKILL.md",
        }
    ]


def test_a_block_scalar_description_is_joined_not_gutted(project: Path) -> None:
    write_skill(
        project,
        "blocky",
        "name: blocky\ndescription: |\n  First line of the description.\n  Second line.",
    )

    payload = json.loads(run(project).stdout)

    assert payload["skills"]["items"][0]["short_description"] == (
        "First line of the description. Second line."
    )


def test_a_quoted_description_keeps_no_quotes(project: Path) -> None:
    write_skill(project, "quoted", 'name: quoted\ndescription: "Quoted purpose."')

    payload = json.loads(run(project).stdout)

    assert payload["skills"]["items"][0]["short_description"] == "Quoted purpose."


def test_frontmatter_with_neither_name_nor_description_is_exit_2(
    project: Path,
) -> None:
    write_skill(project, "nameless", "model: opus")

    result = run(project)

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(
        "neither name nor description" in error
        for error in payload["skills"]["frontmatter_errors"]
    )
    assert payload["errors"]


# --- exit vocabulary ---------------------------------------------------------


def test_not_a_git_repository_is_a_contract_violation_not_bad_args(
    tmp_path: Path,
) -> None:
    (tmp_path / "claude-home").mkdir()

    result = run(tmp_path)

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["git"] is None
    assert any("not a git repository" in error for error in payload["errors"])


def test_the_success_payload_carries_ok(project: Path) -> None:
    result = run(project)

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["git"]["errors"] == []
    assert payload["git"]["current_branch"]


def test_an_unknown_flag_is_exit_1(project: Path) -> None:
    result = run(project, "--definitely-not-a-flag")

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


# --- the datasets guide-template.md asks for --------------------------------


def test_state_working_blocks_are_collected(project: Path) -> None:
    (project / ".claude").mkdir(exist_ok=True)
    (project / ".claude" / "STATE.md").write_text(
        "# Agent State\n\n## Main Agent\n\nClaude Code\n\n"
        "## Current Project: orchestra\n\n- Wave 2 in flight\n\n"
        "## Current Bug Fix: loop\n\n- tracker loop\n",
        encoding="utf-8",
    )

    state = json.loads(run(project).stdout)["identity"]["state"]

    assert state["main_agent"] == "Claude Code"
    assert "Wave 2 in flight" in state["current_project"]
    assert "tracker loop" in state["current_bug_fix"]
    assert state["current_feature"] is None


def test_design_key_decisions_are_collected_and_placeholders_flagged(
    project: Path,
) -> None:
    docs = project / ".claude" / "docs"
    docs.mkdir(parents=True)
    (docs / "DESIGN.md").write_text(
        "# Design\n\n## 背景・目的 (Background & Purpose)\n\n"
        "<!-- comment only -->\n\n"
        "## Key Decisions\n\n"
        "| Decision | Rationale | Alternatives Considered | Date |\n"
        "|---|---|---|---|\n"
        "| Use uv | fast, lockfile | pip | 2026-07-01 |\n"
        "| | | | |\n",
        encoding="utf-8",
    )

    design = json.loads(run(project).stdout)["docs"]["design"]

    assert design["present"] is True
    assert design["placeholder"] is True
    assert design["key_decisions"] == [
        {
            "decision": "Use uv",
            "rationale": "fast, lockfile",
            "alternatives": "pip",
            "date": "2026-07-01",
        }
    ]


def test_env_commands_carry_their_source_and_are_never_invented(
    project: Path,
) -> None:
    (project / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n\n[project.scripts]\nx-cli = "x:main"\n',
        encoding="utf-8",
    )
    (project / "README.md").write_text(
        "# X\n\n```bash\nuv sync\npytest -q\n# a comment\n```\n\n"
        "```python\nimport x\n```\n",
        encoding="utf-8",
    )

    env = json.loads(run(project).stdout)["env"]

    assert env["manifests"] == ["pyproject.toml"]
    assert env["scripts"] == [
        {"name": "x-cli", "entry_point": "x:main", "source": "pyproject.toml"}
    ]
    assert env["commands"] == [
        {"command": "uv sync", "source": "README.md"},
        {"command": "pytest -q", "source": "README.md"},
    ]
    assert env["errors"] == []


def test_a_repository_with_no_documented_commands_reports_none(project: Path) -> None:
    (project / "README.md").write_text("# X\n\nProse only.\n", encoding="utf-8")

    env = json.loads(run(project).stdout)["env"]

    assert env["commands"] == []


def test_agent_teams_sessions_and_work_logs_are_collected(project: Path) -> None:
    teams = project / "claude-home" / "teams" / "wave2"
    teams.mkdir(parents=True)
    (teams / "config.json").write_text(
        json.dumps({"members": [{"name": "ctx", "agent_type": "opus"}]}),
        encoding="utf-8",
    )
    tasks = project / "claude-home" / "tasks" / "wave2"
    tasks.mkdir(parents=True)
    (tasks / "1.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (tasks / "2.json").write_text(json.dumps({"status": "pending"}), encoding="utf-8")
    logs = project / ".claude" / "logs" / "agent-teams" / "wave2"
    logs.mkdir(parents=True)
    (logs / "ctx.md").write_text("## Summary\nDid the work.\n", encoding="utf-8")

    teams_payload = json.loads(run(project).stdout)["agent_teams"]

    assert teams_payload["sessions"][0]["name"] == "wave2"
    assert teams_payload["sessions"][0]["tasks_total"] == 2
    assert teams_payload["sessions"][0]["tasks_completed"] == 1
    assert teams_payload["work_logs"][0]["teammate"] == "ctx"
    assert teams_payload["errors"] == []


def test_a_malformed_team_config_is_reported(project: Path) -> None:
    teams = project / "claude-home" / "teams" / "broken"
    teams.mkdir(parents=True)
    (teams / "config.json").write_text("{not json", encoding="utf-8")

    teams_payload = json.loads(run(project).stdout)["agent_teams"]

    assert teams_payload["errors"]


def test_cli_tools_includes_every_tool_and_counts_bad_lines(project: Path) -> None:
    logs = project / ".claude" / "logs"
    logs.mkdir(parents=True)
    (logs / "cli-tools.jsonl").write_text(
        json.dumps({"tool": "codex", "prompt": "design"})
        + "\n"
        + json.dumps({"tool": "antigravity", "prompt": "research"})
        + "\nnot json\n",
        encoding="utf-8",
    )

    cli = json.loads(run(project).stdout)["cli_tools"]

    assert [item["tool"] for item in cli["items"]] == ["codex", "antigravity"]
    assert cli["skipped_lines"] == 1
    assert cli["error"] is None


def test_an_absent_cli_log_is_distinct_from_an_unreadable_one(project: Path) -> None:
    absent = json.loads(run(project).stdout)["cli_tools"]
    assert absent == {"present": False, "items": [], "skipped_lines": 0, "error": None}

    logs = project / ".claude" / "logs"
    logs.mkdir(parents=True)
    (logs / "cli-tools.jsonl").write_bytes(b"\xff\xfe not utf-8\n")

    broken = json.loads(run(project).stdout)["cli_tools"]
    assert broken["present"] is True
    assert broken["error"] is not None


def test_only_timestamp_named_checkpoints_are_listed(project: Path) -> None:
    checkpoints = project / ".claude" / "checkpoints"
    checkpoints.mkdir(parents=True)
    (checkpoints / "2026-07-25-100000.md").write_text(
        "# Checkpoint\n", encoding="utf-8"
    )
    (checkpoints / ".pending-summary.md").write_text("## サマリ\n", encoding="utf-8")

    payload = json.loads(run(project).stdout)["checkpoints"]

    assert [item["file"] for item in payload["items"]] == ["2026-07-25-100000.md"]


def test_an_unreadable_rule_file_is_reported_not_blank(project: Path) -> None:
    rules = project / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "broken.md").write_bytes(b"\xff\xfe not utf-8\n")

    items = json.loads(run(project).stdout)["rules"]["items"]

    assert items[0]["present"] is True
    assert items[0]["error"] is not None
    assert items[0]["first_line"] is None


def test_help_exits_zero_and_documents_project_root() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "--project-root" in result.stdout
    assert "--claude-home" in result.stdout
