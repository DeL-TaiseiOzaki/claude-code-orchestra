from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents" / "skills" / "update-lib-docs" / "lib_inventory.py"


def run_inventory(
    project_root: Path, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project_root), *extra_args],
        capture_output=True,
        text=True,
        check=False,
    )


def write_library(root: Path, filename: str, content: str) -> None:
    libraries_dir = root / ".agents" / "docs" / "libraries"
    libraries_dir.mkdir(parents=True, exist_ok=True)
    (libraries_dir / filename).write_text(content, encoding="utf-8")


def test_happy_path_computes_age_and_staleness(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n"
        "> **Last Updated**: 2026-01-01\n"
        "> **Version Checked**: 1.4.0\n\n"
        "## Recent Changes\n- Something\n",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["duckdb>=1.0", "fastapi"]\n',
        encoding="utf-8",
    )

    result = run_inventory(tmp_path, "--today", "2026-07-21")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["libraries_dir"] == ".agents/docs/libraries"
    assert payload["stale_days"] == 90
    assert len(payload["libraries"]) == 1

    entry = payload["libraries"][0]
    assert entry["file"] == "duckdb.md"
    assert entry["name"] == "DuckDB"
    assert entry["last_updated"] == "2026-01-01"
    assert entry["version_checked"] == "1.4.0"
    assert entry["age_days"] == (date(2026, 7, 21) - date(2026, 1, 1)).days
    assert entry["stale"] is True
    assert entry["has_metadata"] is True

    assert payload["counts"] == {"total": 1, "stale": 1, "missing_metadata": 0}
    assert payload["declared_dependencies"] == ["duckdb", "fastapi"]
    assert payload["undocumented"] == ["fastapi"]


def test_missing_libraries_dir_is_a_valid_empty_state(tmp_path: Path) -> None:
    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["libraries"] == []
    assert payload["counts"] == {"total": 0, "stale": 0, "missing_metadata": 0}
    assert payload["undocumented"] == []
    assert payload["declared_dependencies"] == []


def test_empty_libraries_dir_is_a_valid_state(tmp_path: Path) -> None:
    (tmp_path / ".agents" / "docs" / "libraries").mkdir(parents=True)

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["libraries"] == []
    assert payload["counts"]["total"] == 0


def test_nonexistent_project_root_degrades_gracefully(tmp_path: Path) -> None:
    ghost_root = tmp_path / "does-not-exist"

    result = run_inventory(ghost_root)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["libraries"] == []
    assert payload["declared_dependencies"] == []


def test_malformed_metadata_does_not_crash(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "broken.md",
        "# Broken Lib\n\n> **Last Updated**: not-a-real-date\n\nBody text.\n",
    )

    result = run_inventory(tmp_path, "--today", "2026-07-21")

    assert result.returncode == 0, result.stderr
    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["last_updated"] is None
    assert entry["age_days"] is None
    assert entry["stale"] is False
    assert entry["has_metadata"] is False


def test_file_with_no_metadata_and_no_heading_falls_back_to_stem(
    tmp_path: Path,
) -> None:
    write_library(
        tmp_path, "no-heading.md", "Just some body text, no heading at all.\n"
    )

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["name"] == "no-heading"
    assert entry["last_updated"] is None
    assert entry["has_metadata"] is False
    assert json.loads(result.stdout)["counts"]["missing_metadata"] == 1


def test_slash_date_format_is_parsed(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "fastapi.md",
        "# FastAPI\n\n> **Last Updated**: 2026/06/01\n> **Version Checked**: 0.115\n",
    )

    result = run_inventory(tmp_path, "--today", "2026-07-01")

    assert result.returncode == 0, result.stderr
    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["last_updated"] == "2026-06-01"
    assert entry["age_days"] == (date(2026, 7, 1) - date(2026, 6, 1)).days
    assert entry["stale"] is False  # 30 days < default 90-day threshold


def test_today_override_is_deterministic_across_runs(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-01-01\n> **Version Checked**: 1.0\n",
    )

    first = run_inventory(tmp_path, "--today", "2026-07-21")
    second = run_inventory(tmp_path, "--today", "2026-07-21")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)


def test_custom_stale_days_threshold(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-06-01\n> **Version Checked**: 1.0\n",
    )

    result = run_inventory(tmp_path, "--today", "2026-07-01", "--stale-days", "10")

    assert result.returncode == 0, result.stderr
    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["stale"] is True


def test_dependency_normalization_and_undocumented(tmp_path: Path) -> None:
    write_library(tmp_path, "duckdb.md", "# DuckDB\n")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'dependencies = ["DuckDB>=1.0", "Some_Package[extra]>=1.0; python_version<\'3.12\'"]\n'
        "\n"
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8.0"]\n',
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"@scope/Pkg": "^1.0.0", "lodash": "^4.0.0"},
                "devDependencies": {"eslint": "^9.0.0"},
            }
        ),
        encoding="utf-8",
    )

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["declared_dependencies"] == [
        "duckdb",
        "eslint",
        "lodash",
        "pkg",
        "pytest",
        "some-package",
    ]
    assert payload["undocumented"] == [
        "eslint",
        "lodash",
        "pkg",
        "pytest",
        "some-package",
    ]


def test_malformed_pyproject_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "this is not [valid toml", encoding="utf-8"
    )

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["declared_dependencies"] == []


def test_malformed_package_json_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["declared_dependencies"] == []


def test_bad_today_arg_exits_1(tmp_path: Path) -> None:
    result = run_inventory(tmp_path, "--today", "not-a-date")

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "error" in payload


def test_bad_today_arg_rejects_slash_format(tmp_path: Path) -> None:
    """--today is documented as strictly YYYY-MM-DD, unlike in-doc metadata dates."""
    result = run_inventory(tmp_path, "--today", "2026/07/21")

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False


def test_stdout_is_single_json_line(tmp_path: Path) -> None:
    result = run_inventory(tmp_path)

    assert result.stdout.count("\n") == 1
    json.loads(result.stdout)
