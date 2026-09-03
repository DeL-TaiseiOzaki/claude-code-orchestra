"""Pin the reduced contract of init/detect_stack.py.

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
SCRIPT = REPO_ROOT / ".agents" / "skills" / "init" / "detect_stack.py"


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

    Mirrors what ``.agents/check.sh`` verifies: the root bootstrap, the
    ``CLAUDE.md`` symlink, shared state, and both native discovery symlinks.
    """
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").symlink_to("AGENTS.md")
    state = tmp_path / ".agents" / "STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text("# Agent State\n\n## Repository Identity\n", encoding="utf-8")
    for name in ("agents", "skills"):
        (tmp_path / ".agents" / name).mkdir()
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / name).symlink_to(f"../.agents/{name}")
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


def test_dangling_discovery_symlink_fails_the_bootstrap(project: Path) -> None:
    """A dangling ``.claude/skills`` disables all native skill auto-discovery,
    yet detect_stack.py reported ``agent_bootstrap`` all-true and /init reported
    success. SKILL.md claimed exit 2 covered the discovery symlink; only
    ``check.sh`` actually looked."""
    (project / ".claude" / "skills").unlink()
    code, payload, stderr = run(project)
    assert code == 2, stderr
    assert payload["ok"] is False
    assert payload["agent_bootstrap"]["claude_skills_link"] is False
    assert payload["agent_bootstrap"]["claude_agents_link"] is True
    assert "claude_skills_link" in payload["error"]


def test_discovery_symlink_to_the_wrong_target_fails(project: Path) -> None:
    link = project / ".claude" / "agents"
    link.unlink()
    link.symlink_to("../elsewhere")
    code, payload, _ = run(project)
    assert code == 2
    assert payload["agent_bootstrap"]["claude_agents_link"] is False


def test_missing_state_marker_fails_the_bootstrap(project: Path) -> None:
    (project / ".agents" / "STATE.md").write_text("nothing\n", encoding="utf-8")
    code, payload, _ = run(project)
    assert code == 2
    assert payload["agent_bootstrap"]["state_md"] is False
    assert "state_md" in payload["error"]


def test_broken_claude_symlink_fails_the_bootstrap(project: Path) -> None:
    (project / "CLAUDE.md").unlink()
    code, payload, _ = run(project)
    assert code == 2
    assert payload["agent_bootstrap"]["claude_symlink"] is False
