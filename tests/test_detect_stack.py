"""Pin the reduced contract of start-project/detect_stack.py.

This script had no tests, which is how it acquired the two defects that made it
the audit's counter-example to "script everything": ``if "ty" in text`` turned a
``typing-extensions`` dependency into a confident ``uv run ty check src/``, and a
non-greedy dependency regex silently dropped every dependency after
``uvicorn[standard]``. Both landed in DESIGN.md as fact.

The tests below therefore pin *absences* as much as presences: no fabricated
command, no truncated dependency list, no traceback on an undecodable manifest.
Every run is pinned to ``--project-root tmp_path``, so the real repository is
never read.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "start-project" / "detect_stack.py"
SKELETON_AGENTS_MD = (
    "# Project — Agent Instructions\n\n## Project\n\n"
    "_Not initialized — run `/start-project` to convert this file._\n\n"
    "## Commands\n\nx\n\n## Conventions\n\nx\n\n"
    "## Agent Roles\n\nexecutor_contract.md ORCHESTRA_ROLE\n\n"
    "## Orchestra References\n\n.claude/rules/orchestration.md\n"
)


def run(root: Path, *extra: str) -> tuple[int, dict, str]:
    """Run the script against *root* and return (exit code, payload, stderr)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(root), *extra],
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    return result.returncode, payload, result.stderr


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A fixture repository with a complete, valid agent bootstrap.

    Mirrors what ``scripts/check.sh`` verifies: the root AGENTS.md skeleton,
    shared state, the CLI-subagent contract, both native runtime directories,
    and no CLAUDE.md-family file shadowing AGENTS.md.
    """
    (tmp_path / "AGENTS.md").write_text(SKELETON_AGENTS_MD, encoding="utf-8")
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "AGENTS.md").write_text("# CLI\n", encoding="utf-8")
    state = tmp_path / ".claude" / "STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text("# Agent State\n\n## Repository Identity\n", encoding="utf-8")
    for name in ("agents", "skills"):
        (tmp_path / ".claude" / name).mkdir()
    return tmp_path


def find_evidence(payload: dict, category: str, **match: str) -> list[dict]:
    """Return the evidence entries in *category* matching every field in *match*."""
    entries = payload["evidence"][category]
    return [e for e in entries if all(e.get(k) == v for k, v in match.items())]


# --- argument and root validation -------------------------------------------


def test_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--project-root" in result.stdout


def test_missing_project_root_is_bad_arguments(tmp_path: Path) -> None:
    """A typo'd root used to be indistinguishable from an empty repository:
    both produced "everything absent" and exit 2."""
    code, payload, stderr = run(tmp_path / "nope")
    assert code == 1, stderr
    assert payload["ok"] is False
    assert "--project-root" in payload["error"]


def test_project_root_pointing_at_a_file_is_bad_arguments(tmp_path: Path) -> None:
    target = tmp_path / "afile"
    target.write_text("x", encoding="utf-8")
    code, payload, stderr = run(target)
    assert code == 1, stderr
    assert payload["ok"] is False


# --- unreadable input --------------------------------------------------------


def test_undecodable_manifest_is_a_warning_not_a_traceback(project: Path) -> None:
    """Reproduces the crash: ``_safe_read`` caught only ``OSError``, so a
    non-UTF-8 manifest raised ``UnicodeDecodeError`` and exited 1 with a
    traceback and no JSON at all — at a step whose contract says stdout is
    JSON and whose exit 1 means "bad arguments"."""
    (project / "pyproject.toml").write_bytes(b'[project]\nname="caf\xe9"\nruff\n')
    code, payload, stderr = run(project)
    assert code == 0, stderr
    assert "Traceback" not in stderr
    assert payload["ok"] is True
    assert [w for w in payload["warnings"] if w["manifest"] == "pyproject.toml"]
    assert "pyproject.toml" not in payload["evidence"]["parsed_manifests"]


def test_malformed_toml_is_a_warning_not_a_crash(project: Path) -> None:
    (project / "pyproject.toml").write_text("[project\nname =", encoding="utf-8")
    code, payload, stderr = run(project)
    assert code == 0, stderr
    assert "Traceback" not in stderr
    assert [w for w in payload["warnings"] if w["manifest"] == "pyproject.toml"]


def test_malformed_package_json_is_a_warning_not_a_crash(project: Path) -> None:
    (project / "package.json").write_text("{not json", encoding="utf-8")
    code, payload, stderr = run(project)
    assert code == 0, stderr
    assert [w for w in payload["warnings"] if w["manifest"] == "package.json"]


# --- the deliberate reduction: no inference ---------------------------------


def test_no_commands_are_inferred(project: Path) -> None:
    """The script reports evidence and never a command line. ``commands`` was
    the field ``init/SKILL.md`` told the agent to copy into DESIGN.md."""
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[tool.ruff]\nline-length = 88\n',
        encoding="utf-8",
    )
    code, payload, _ = run(project)
    assert code == 0
    assert "commands" not in payload
    assert json.dumps(payload).find("uv run") == -1


def test_typing_extensions_does_not_fabricate_the_ty_tool(project: Path) -> None:
    """``if "ty" in text`` matched ``typing-extensions`` and produced
    ``uv run ty check src/`` for a project with no type checker."""
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["typing-extensions"]\n',
        encoding="utf-8",
    )
    code, payload, _ = run(project)
    assert code == 0
    assert find_evidence(payload, "tools", tool="ty") == []
    assert find_evidence(payload, "dependencies", name="typing-extensions")


def test_tools_come_from_declared_tables_only(project: Path) -> None:
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[tool.ruff.lint]\nselect = ["E"]\n\n'
        "[tool.pytest.ini_options]\naddopts = ''\n",
        encoding="utf-8",
    )
    code, payload, _ = run(project)
    assert code == 0
    ruff = find_evidence(payload, "tools", tool="ruff")
    assert ruff and ruff[0]["key"] == "tool.ruff"
    assert ruff[0]["manifest"] == "pyproject.toml"
    assert find_evidence(payload, "tools", tool="pytest")
    assert find_evidence(payload, "tools", tool="stability") == []


def test_extras_marker_does_not_truncate_the_dependency_list(project: Path) -> None:
    """The non-greedy ``dependencies\\s*=\\s*\\[(.*?)\\]`` regex stopped at the
    first ``]``, which is inside ``uvicorn[standard]``: ``httpx`` was dropped and
    nothing in the JSON said the list was partial."""
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n'
        'dependencies = ["fastapi", "uvicorn[standard]", "httpx>=0.27"]\n',
        encoding="utf-8",
    )
    code, payload, _ = run(project)
    assert code == 0
    names = [
        e["name"]
        for e in find_evidence(
            payload,
            "dependencies",
            manifest="pyproject.toml",
            key="project.dependencies",
        )
    ]
    assert names == ["fastapi", "uvicorn", "httpx"]
    uvicorn = find_evidence(payload, "dependencies", name="uvicorn")[0]
    assert uvicorn["spec"] == "uvicorn[standard]"


def test_optional_and_group_dependencies_keep_their_own_keys(project: Path) -> None:
    """The old regex also matched ``optional-dependencies`` when it came first,
    reporting development extras as runtime dependencies."""
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["fastapi"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest"]\n'
        "[dependency-groups]\n"
        'lint = ["ruff"]\n',
        encoding="utf-8",
    )
    code, payload, _ = run(project)
    assert code == 0
    assert find_evidence(payload, "dependencies", name="fastapi")[0]["key"] == (
        "project.dependencies"
    )
    assert find_evidence(payload, "dependencies", name="pytest")[0]["key"] == (
        "project.optional-dependencies.dev"
    )
    assert find_evidence(payload, "dependencies", name="ruff")[0]["key"] == (
        "dependency-groups.lint"
    )


def test_python_evidence_does_not_suppress_node_evidence(project: Path) -> None:
    """``if package_json.exists() and not commands`` meant any Python command
    found first suppressed *all* npm scripts in a polyglot repository."""
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[tool.ruff]\n', encoding="utf-8"
    )
    (project / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"lint": "eslint .", "test": "vitest run"},
                "dependencies": {"react": "^19.0.0"},
            }
        ),
        encoding="utf-8",
    )
    code, payload, _ = run(project)
    assert code == 0
    assert find_evidence(payload, "tools", tool="ruff")
    lint = find_evidence(payload, "scripts", name="lint")
    assert lint and lint[0]["command"] == "eslint ."
    assert lint[0]["key"] == "scripts.lint"
    assert find_evidence(payload, "dependencies", name="react")
    assert set(payload["evidence"]["parsed_manifests"]) == {
        "pyproject.toml",
        "package.json",
    }
    assert payload["languages"] == ["python", "javascript"]


def test_present_but_unparsed_manifest_is_named(project: Path) -> None:
    """ "No dependency evidence" must be distinguishable from "not parsed"."""
    (project / "Cargo.toml").write_text('[package]\nname = "demo"\n', encoding="utf-8")
    code, payload, _ = run(project)
    assert code == 0
    assert payload["evidence"]["unparsed_manifests"] == ["Cargo.toml"]
    assert payload["languages"] == ["rust"]


def test_absent_manifests_are_reported_as_false(project: Path) -> None:
    """Filtering ``manifests`` to present-only entries made "checked and absent"
    indistinguishable from "never checked"."""
    code, payload, _ = run(project)
    assert code == 0
    assert payload["manifests"]["pyproject.toml"] is False
    assert payload["manifests"]["Makefile"] is False
    assert payload["evidence"]["parsed_manifests"] == []


def test_ci_evidence_names_the_path(project: Path) -> None:
    (project / ".github" / "workflows").mkdir(parents=True)
    code, payload, _ = run(project)
    assert code == 0
    assert find_evidence(payload, "ci", system="github-actions")[0]["path"] == (
        ".github/workflows"
    )


# --- bootstrap integrity -----------------------------------------------------


def test_complete_bootstrap_is_ok(project: Path) -> None:
    code, payload, stderr = run(project)
    assert code == 0, stderr
    assert payload["ok"] is True
    assert all(payload["agent_bootstrap"].values())
    assert payload["artifacts"] == []
    assert "error" not in payload


def test_missing_skills_directory_fails_the_bootstrap(project: Path) -> None:
    """A missing ``.claude/skills`` disables all native skill auto-discovery,
    yet detect_stack.py used to report ``agent_bootstrap`` all-true and the
    setup skill reported success."""
    (project / ".claude" / "skills").rmdir()
    code, payload, stderr = run(project)
    assert code == 2, stderr
    assert payload["ok"] is False
    assert payload["agent_bootstrap"]["claude_skills_dir"] is False
    assert payload["agent_bootstrap"]["claude_agents_dir"] is True
    assert "claude_skills_dir" in payload["error"]


def test_runtime_directory_replaced_by_a_symlink_fails(project: Path) -> None:
    """The runtime directories are physical: a link here means a second source
    of truth somewhere else, which is exactly what this layout removed."""
    runtime_dir = project / ".claude" / "agents"
    runtime_dir.rmdir()
    runtime_dir.symlink_to("../elsewhere")
    code, payload, _ = run(project)
    assert code == 2
    assert payload["agent_bootstrap"]["claude_agents_dir"] is False


def test_missing_state_marker_fails_the_bootstrap(project: Path) -> None:
    (project / ".claude" / "STATE.md").write_text("nothing\n", encoding="utf-8")
    code, payload, _ = run(project)
    assert code == 2
    assert payload["agent_bootstrap"]["state_md"] is False
    assert "state_md" in payload["error"]


def test_complete_bootstrap_reports_the_skeleton_state(project: Path) -> None:
    code, payload, _ = run(project)
    assert code == 0
    assert payload["agents_md_state"] == "skeleton"
    assert payload["instruction_shadowing"] == {"owned": [], "shim": [], "ancestor": []}
    assert payload["bootstrap_warnings"] == []
    assert "claude_md" not in payload["agent_bootstrap"]


def test_converted_agents_md_is_reported_as_converted(project: Path) -> None:
    agents = project / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace(
            "_Not initialized — run `/start-project` to convert this file._",
            "Acme API serves invoices.",
        ),
        encoding="utf-8",
    )
    code, payload, _ = run(project)
    assert code == 0
    assert payload["agents_md_state"] == "converted"


def test_agents_md_without_orchestra_sections_is_unrecognized(project: Path) -> None:
    (project / "AGENTS.md").write_text("# Mine\n\nhand-written\n", encoding="utf-8")
    code, payload, _ = run(project)
    assert code == 0
    assert payload["agents_md_state"] == "unrecognized"


def test_missing_agents_md_fails_the_bootstrap(project: Path) -> None:
    (project / "AGENTS.md").unlink()
    code, payload, _ = run(project)
    assert code == 2
    assert payload["agent_bootstrap"]["agents_md"] is False
    assert payload["agents_md_state"] == "missing"


@pytest.mark.parametrize("name", ["CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"])
def test_owned_instruction_file_shadowing_agents_md_fails(
    project: Path, name: str
) -> None:
    """Claude Code skips AGENTS.md while any of these exists, so a set-up
    project with one is broken even though every other marker is green."""
    (project / name).write_text("# My rules\n", encoding="utf-8")
    code, payload, _ = run(project)
    assert code == 2
    assert payload["agent_bootstrap"]["no_owned_instruction_shadowing"] is False
    assert payload["instruction_shadowing"]["owned"] == [name]
    assert "no_owned_instruction_shadowing" in payload["error"]


def test_a_claude_md_that_only_imports_agents_md_is_a_shim_not_a_failure(
    project: Path,
) -> None:
    (project / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    code, payload, _ = run(project)
    assert code == 0
    assert payload["instruction_shadowing"]["shim"] == ["CLAUDE.md"]
    assert payload["instruction_shadowing"]["owned"] == []


def test_ancestor_claude_md_is_a_warning_not_a_failure(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# parent rules\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "AGENTS.md").write_text(SKELETON_AGENTS_MD, encoding="utf-8")
    (nested / ".agents").mkdir()
    (nested / ".agents" / "AGENTS.md").write_text("# CLI\n", encoding="utf-8")
    (nested / ".claude").mkdir()
    (nested / ".claude" / "STATE.md").write_text("# Agent State\n", encoding="utf-8")
    for name in ("agents", "skills"):
        (nested / ".claude" / name).mkdir()

    code, payload, _ = run(nested)

    assert code == 0, payload
    ancestor = str((tmp_path / "CLAUDE.md").resolve())
    assert ancestor in payload["instruction_shadowing"]["ancestor"]
    assert any(ancestor in w for w in payload["bootstrap_warnings"])


def test_missing_cli_subagent_contract_fails_the_bootstrap(project: Path) -> None:
    (project / ".agents" / "AGENTS.md").unlink()
    code, payload, _ = run(project)
    assert code == 2
    assert payload["agent_bootstrap"]["cli_subagent_contract"] is False
