from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents" / "skills" / "context-loader" / "load_context.py"

DESIGN_PLACEHOLDER = (
    "# Design Document\n\n"
    "## 背景・目的 (Background & Purpose)\n\n"
    "<!-- Why does this project exist? What problem does it solve, for whom?\n"
    "     State the business/technical context and the goal in a few sentences. -->\n\n"
    "## スコープ (Scope)\n\n"
    "### In Scope\n\n"
    "- \n"
)

DESIGN_FILLED = (
    "# Design Document\n\n"
    "## 背景・目的 (Background & Purpose)\n\n"
    "<!-- Why does this project exist? -->\n\n"
    "This project is a task inventory service for engineering teams.\n\n"
    "## スコープ (Scope)\n\n"
    "### In Scope\n\n"
    "- Ticket creation\n"
)


def run_load_context(
    project_root: Path, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project_root), *extra_args],
        capture_output=True,
        text=True,
        check=False,
    )


def write_rules(root: Path, stems: list[str]) -> None:
    rules_dir = root / ".agents" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (rules_dir / f"{stem}.md").write_text(f"# {stem}\n", encoding="utf-8")


def write_state(root: Path, main_agent_block: str = "\nClaude Code\n") -> None:
    agents_dir = root / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    text = (
        "# Agent State\n\n"
        "## Main Agent\n"
        f"{main_agent_block}\n"
        "## Repository Identity\n\nSome identity.\n\n"
        "## Progress Tracker\n\nRolling.\n"
    )
    (agents_dir / "STATE.md").write_text(text, encoding="utf-8")


def test_happy_path_full_context_and_rule_ordering(tmp_path: Path) -> None:
    write_rules(
        tmp_path,
        ["testing", "coding-principles", "zzz-extra", "aaa-extra", "dev-environment"],
    )
    write_state(tmp_path)
    docs_dir = tmp_path / ".agents" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "DESIGN.md").write_text(DESIGN_FILLED, encoding="utf-8")
    (tmp_path / "PROGRESS.md").write_text("# Progress\n", encoding="utf-8")
    libraries_dir = docs_dir / "libraries"
    libraries_dir.mkdir(parents=True, exist_ok=True)
    (libraries_dir / "duckdb.md").write_text("# DuckDB\n", encoding="utf-8")
    (libraries_dir / "fastapi.md").write_text("# FastAPI\n", encoding="utf-8")

    result = run_load_context(tmp_path, "--task-libraries", "duckdb")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    # Preferred prefix first (only the ones present, in prefix order), then
    # unrecognised files appended alphabetically.
    assert payload["rules"]["files"] == [
        ".agents/rules/coding-principles.md",
        ".agents/rules/dev-environment.md",
        ".agents/rules/testing.md",
        ".agents/rules/aaa-extra.md",
        ".agents/rules/zzz-extra.md",
    ]
    assert payload["state"]["present"] is True
    assert payload["state"]["main_agent"] == "Claude Code"
    assert payload["design"]["present"] is True
    assert payload["design"]["placeholder"] is False
    assert payload["progress"]["present"] is True
    assert payload["libraries"]["files"] == ["duckdb.md", "fastapi.md"]
    assert payload["libraries"]["matched"] == ["duckdb.md"]
    assert payload["missing"] == []
    assert payload["warnings"] == []
    assert payload["read_order"] == [
        ".agents/rules/coding-principles.md",
        ".agents/rules/dev-environment.md",
        ".agents/rules/testing.md",
        ".agents/rules/aaa-extra.md",
        ".agents/rules/zzz-extra.md",
        ".agents/STATE.md",
        ".agents/docs/DESIGN.md",
        ".agents/docs/libraries/duckdb.md",
    ]


def test_missing_optional_inputs_degrade_gracefully(tmp_path: Path) -> None:
    write_rules(tmp_path, ["coding-principles"])
    write_state(tmp_path)

    result = run_load_context(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["design"]["present"] is False
    assert payload["design"]["placeholder"] is True
    assert payload["progress"]["present"] is False
    assert payload["libraries"]["present"] is False
    assert payload["libraries"]["files"] == []
    assert payload["libraries"]["matched"] == []
    assert ".agents/docs/DESIGN.md" in payload["missing"]
    assert "PROGRESS.md" in payload["missing"]
    assert any("/init" in w for w in payload["warnings"])
    # Absent files are never dereferenced in the read plan.
    assert ".agents/docs/DESIGN.md" not in payload["read_order"]


def test_missing_rules_dir_exits_2(tmp_path: Path) -> None:
    write_state(tmp_path)

    result = run_load_context(tmp_path)

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert ".agents/rules" in payload["missing"]


def test_missing_state_md_exits_2(tmp_path: Path) -> None:
    write_rules(tmp_path, ["coding-principles"])

    result = run_load_context(tmp_path)

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert ".agents/STATE.md" in payload["missing"]


def test_main_agent_missing_value_parses_to_none(tmp_path: Path) -> None:
    write_rules(tmp_path, ["coding-principles"])
    write_state(tmp_path, main_agent_block="\n")  # heading present, no value line

    result = run_load_context(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"]["present"] is True
    assert payload["state"]["main_agent"] is None


def test_real_repo_design_template_is_detected_as_placeholder(tmp_path: Path) -> None:
    """Regression guard tied to the actual pristine template (see commit
    'Keep distributed DESIGN.md a pristine placeholder')."""
    write_rules(tmp_path, ["coding-principles"])
    write_state(tmp_path)
    docs_dir = tmp_path / ".agents" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    real_design = (REPO_ROOT / ".agents" / "docs" / "DESIGN.md").read_text(
        encoding="utf-8"
    )
    (docs_dir / "DESIGN.md").write_text(real_design, encoding="utf-8")

    result = run_load_context(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["design"]["present"] is True
    assert payload["design"]["placeholder"] is True
    assert any("/init" in w for w in payload["warnings"])


def test_task_libraries_matches_by_substring(tmp_path: Path) -> None:
    write_rules(tmp_path, ["coding-principles"])
    write_state(tmp_path)
    libraries_dir = tmp_path / ".agents" / "docs" / "libraries"
    libraries_dir.mkdir(parents=True, exist_ok=True)
    (libraries_dir / "duckdb-python.md").write_text(
        "# DuckDB Python\n", encoding="utf-8"
    )
    (libraries_dir / "fastapi.md").write_text("# FastAPI\n", encoding="utf-8")

    result = run_load_context(
        tmp_path, "--task-libraries", " duckdb , nothing-matches "
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["libraries"]["matched"] == ["duckdb-python.md"]
    assert payload["read_order"][-1] == ".agents/docs/libraries/duckdb-python.md"


def test_no_task_libraries_matches_nothing(tmp_path: Path) -> None:
    write_rules(tmp_path, ["coding-principles"])
    write_state(tmp_path)
    libraries_dir = tmp_path / ".agents" / "docs" / "libraries"
    libraries_dir.mkdir(parents=True, exist_ok=True)
    (libraries_dir / "duckdb.md").write_text("# DuckDB\n", encoding="utf-8")

    result = run_load_context(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["libraries"]["files"] == ["duckdb.md"]
    assert payload["libraries"]["matched"] == []
    assert all(
        not p.startswith(".agents/docs/libraries/") for p in payload["read_order"]
    )


def test_deterministic_across_runs(tmp_path: Path) -> None:
    write_rules(tmp_path, ["coding-principles", "testing"])
    write_state(tmp_path)

    first = run_load_context(tmp_path)
    second = run_load_context(tmp_path)

    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(first.stdout) == json.loads(second.stdout)


def test_stdout_is_single_json_line(tmp_path: Path) -> None:
    write_rules(tmp_path, ["coding-principles"])
    write_state(tmp_path)

    result = run_load_context(tmp_path)

    assert result.stdout.count("\n") == 1
    json.loads(result.stdout)


def test_placeholder_fixture_itself_is_detected(tmp_path: Path) -> None:
    """Sanity-check the DESIGN_PLACEHOLDER/DESIGN_FILLED fixtures used above."""
    write_rules(tmp_path, ["coding-principles"])
    write_state(tmp_path)
    docs_dir = tmp_path / ".agents" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "DESIGN.md").write_text(DESIGN_PLACEHOLDER, encoding="utf-8")

    result = run_load_context(tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["design"]["placeholder"] is True
