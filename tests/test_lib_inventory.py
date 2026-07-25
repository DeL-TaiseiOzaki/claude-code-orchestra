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

    assert entry["stale_reasons"] == ["age"]
    assert entry["read_error"] is None

    assert payload["counts"] == {
        "total": 1,
        "stale": 1,
        "missing_metadata": 0,
        "read_errors": 0,
        "version_drift": 0,
        "drift_unknown": 1,
    }
    assert payload["declared_dependencies"] == ["duckdb", "fastapi"]
    assert payload["undocumented"] == ["fastapi"]
    assert payload["manifest_errors"] == []
    assert payload["artifacts"] == []


def test_missing_libraries_dir_is_a_valid_empty_state(tmp_path: Path) -> None:
    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["libraries"] == []
    assert payload["counts"]["total"] == 0
    assert payload["undocumented"] == []
    assert payload["declared_dependencies"] == []


def test_empty_libraries_dir_is_a_valid_state(tmp_path: Path) -> None:
    (tmp_path / ".agents" / "docs" / "libraries").mkdir(parents=True)

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["libraries"] == []
    assert payload["counts"]["total"] == 0


def test_nonexistent_project_root_is_a_bad_argument(tmp_path: Path) -> None:
    """CONTRACT CHANGE (was: degrades gracefully to an empty exit-0 inventory).

    A typo'd --project-root is the likeliest operator error when this runs from
    another repository, and a clean all-empty report reads as "every library is
    current". A root that does not exist is bad input (exit 1), not an absent
    optional path: nothing was scanned, so nothing can be asserted about
    currency. Contrast the two tests below, which keep exit 0 for a genuinely
    absent optional file inside an existing root.
    """
    ghost_root = tmp_path / "does-not-exist"

    result = run_inventory(ghost_root)

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "does not exist" in payload["error"]


def test_absent_manifests_stay_a_valid_empty_state(tmp_path: Path) -> None:
    """The absent-optional-path exemption (_shared/README.md) still holds: a
    project with no pyproject.toml and no package.json has nothing to
    cross-check, which is a real answer rather than a hidden failure."""
    write_library(tmp_path, "duckdb.md", "# DuckDB\n")

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["declared_dependencies"] == []
    assert payload["manifest_errors"] == []
    assert payload["sources"] == []


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


def test_malformed_pyproject_is_reported_not_swallowed(tmp_path: Path) -> None:
    """CONTRACT CHANGE (was: test_malformed_pyproject_does_not_crash, which
    asserted declared_dependencies == [] at exit 0).

    Not crashing is necessary but was being met by making a broken manifest
    indistinguishable from a project with no dependencies: `undocumented`
    emptied out and update-lib-docs concluded "everything is current". The
    parse error is now a reported state (`manifest_errors`) with `ok: false`
    and exit 2, per _shared/README.md "errors are never swallowed".
    """
    (tmp_path / "pyproject.toml").write_text(
        "this is not [valid toml", encoding="utf-8"
    )

    result = run_inventory(tmp_path)

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert [error["file"] for error in payload["manifest_errors"]] == ["pyproject.toml"]
    assert "TOMLDecodeError" in payload["manifest_errors"][0]["error"]
    assert payload["declared_dependencies"] == []


def test_malformed_package_json_is_reported_not_swallowed(tmp_path: Path) -> None:
    """CONTRACT CHANGE, same reasoning as the pyproject case above."""
    (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")

    result = run_inventory(tmp_path)

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert [error["file"] for error in payload["manifest_errors"]] == ["package.json"]


def test_malformed_lockfile_is_reported(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["duckdb>=1.0"]\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text("not [valid toml", encoding="utf-8")

    result = run_inventory(tmp_path)

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert [error["file"] for error in payload["manifest_errors"]] == ["uv.lock"]
    # The manifest still parsed, so its facts survive alongside the error.
    assert payload["declared_dependencies"] == ["duckdb"]


def test_unreadable_doc_is_reported_not_blanked(tmp_path: Path) -> None:
    """An unreadable doc used to become text="", i.e. exactly what a doc with
    no metadata looks like, and was reported documented-and-current at exit 0.
    This is a broken state, not an absent optional path, so it carries
    `read_error` and exits 3 (external/read failure)."""
    libraries_dir = tmp_path / ".agents" / "docs" / "libraries"
    libraries_dir.mkdir(parents=True)
    (libraries_dir / "broken.md").write_bytes(b"\xff\xfe not utf-8 at all")

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["counts"]["read_errors"] == 1
    entry = payload["libraries"][0]
    assert "UnicodeDecodeError" in entry["read_error"]


def test_missing_metadata_names_are_emitted(tmp_path: Path) -> None:
    """The count alone was unusable: update-lib-docs scopes a run to lists of
    names, so a bare integer could not be acted on."""
    write_library(tmp_path, "duckdb.md", "# DuckDB\n\nNo metadata block.\n")

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["missing_metadata"] == ["duckdb.md"]
    assert payload["counts"]["missing_metadata"] == 1


# --- version drift -----------------------------------------------------------
#
# Age was the only staleness signal; version_checked was parsed and never
# compared with anything. Drift is only ever reported when it is decidable:
# an undecidable comparison is null plus a note, never a guess.


def _write_declared(root: Path, spec: str) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\ndependencies = ["duckdb{spec}"]\n', encoding="utf-8"
    )


def test_lockfile_mismatch_is_drift_and_makes_the_doc_stale(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-07-24\n> **Version Checked**: 1.4.0\n",
    )
    _write_declared(tmp_path, ">=1.0")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "duckdb"\nversion = "2.1.3"\n', encoding="utf-8"
    )

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    assert result.returncode == 0, result.stderr
    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["locked_version"] == "2.1.3"
    assert entry["locked_in"] == "uv.lock"
    assert entry["version_drift"] is True
    assert entry["version_drift_basis"] == "locked_version"
    # One day old: age alone would have called this current.
    assert entry["age_days"] == 1
    assert entry["stale"] is True
    assert entry["stale_reasons"] == ["version_drift"]


def test_lockfile_match_is_not_drift(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-07-24\n> **Version Checked**: 2.1\n",
    )
    _write_declared(tmp_path, ">=1.0")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "duckdb"\nversion = "2.1.0"\n', encoding="utf-8"
    )

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["version_drift"] is False, "2.1 and 2.1.0 are the same release"
    assert entry["stale"] is False


def test_documented_version_below_the_declared_lower_bound_is_drift(
    tmp_path: Path,
) -> None:
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-07-24\n> **Version Checked**: 1.4.0\n",
    )
    _write_declared(tmp_path, ">=2.0")

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["declared_spec"] == ">=2.0"
    assert entry["version_drift"] is True
    assert entry["version_drift_basis"] == "spec_lower_bound"
    assert ">=2.0" in entry["version_drift_note"]


def test_open_range_without_a_lockfile_is_unknown_not_clean(tmp_path: Path) -> None:
    """The doc satisfies `>=1.0`, but nothing here says which version is
    actually resolved. Reporting `false` would be a guess dressed up as a fact,
    so the verdict is null with a note naming the missing evidence."""
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-07-24\n> **Version Checked**: 1.4.0\n",
    )
    _write_declared(tmp_path, ">=1.0")

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    payload = json.loads(result.stdout)
    entry = payload["libraries"][0]
    assert entry["version_drift"] is None
    assert entry["version_drift_basis"] == "spec_lower_bound"
    assert "no lockfile" in entry["version_drift_note"]
    assert payload["counts"]["drift_unknown"] == 1
    assert any("no lockfile found" in warning for warning in payload["warnings"])


def test_pinned_spec_mismatch_is_drift(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-07-24\n> **Version Checked**: 1.4.0\n",
    )
    _write_declared(tmp_path, "==1.5.0")

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["version_drift"] is True
    assert entry["version_drift_basis"] == "pinned_spec"


def test_non_numeric_documented_version_is_unknown(tmp_path: Path) -> None:
    """A prerelease or free-text version cannot be ordered by this script, and
    an invented ordering is worse than an honest 'unknown'."""
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-07-24\n> **Version Checked**: 2.0.0-rc.1\n",
    )
    _write_declared(tmp_path, "==2.0.0")

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["version_drift"] is None
    assert "not a plain numeric version" in entry["version_drift_note"]


def test_doc_for_an_undeclared_library_reports_why_drift_is_unknown(
    tmp_path: Path,
) -> None:
    write_library(
        tmp_path,
        "duckdb.md",
        "# DuckDB\n\n> **Last Updated**: 2026-07-24\n> **Version Checked**: 1.4.0\n",
    )

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["version_drift"] is None
    assert "not a declared dependency" in entry["version_drift_note"]


# --- dependency sources ------------------------------------------------------


def test_poetry_and_pep735_tables_are_read_and_reported(tmp_path: Path) -> None:
    """Reading only [project] made a Poetry or PEP 735 project look like a
    project with zero dependencies, so the whole cross-check no-opped."""
    (tmp_path / "pyproject.toml").write_text(
        "[dependency-groups]\n"
        'test = ["pytest>=8.0"]\n'
        "\n"
        "[tool.poetry.dependencies]\n"
        'python = "^3.12"\n'
        'requests = "^2.31.0"\n',
        encoding="utf-8",
    )

    result = run_inventory(tmp_path)

    payload = json.loads(result.stdout)
    assert payload["declared_dependencies"] == ["pytest", "requests"], (
        "python is the interpreter, not a documentable library"
    )
    tables = {source["table"] for source in payload["sources"]}
    assert tables == {"[dependency-groups].test", "[tool.poetry.dependencies]"}


def test_a_manifest_with_no_readable_dependency_table_warns(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n', encoding="utf-8"
    )

    result = run_inventory(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["sources"] == []
    assert any(
        "declares no dependencies" in warning for warning in payload["warnings"]
    ), payload["warnings"]


def test_lockfile_only_packages_are_not_reported_undocumented(tmp_path: Path) -> None:
    """A lockfile holds the transitive closure. Folding it into the declared
    set would demand a library doc for every indirect package."""
    _write_declared(tmp_path, ">=1.0")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "duckdb"\nversion = "1.4.0"\n\n'
        '[[package]]\nname = "some-transitive-dep"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )

    result = run_inventory(tmp_path)

    payload = json.loads(result.stdout)
    assert payload["declared_dependencies"] == ["duckdb"]
    assert payload["undocumented"] == ["duckdb"]


def test_package_lock_json_versions_are_resolved(tmp_path: Path) -> None:
    write_library(
        tmp_path,
        "lodash.md",
        "# lodash\n\n> **Last Updated**: 2026-07-24\n> **Version Checked**: 4.17.20\n",
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"lodash": "^4.0.0"}}), encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "app"},
                    "node_modules/lodash": {"version": "4.17.21"},
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_inventory(tmp_path, "--today", "2026-07-25")

    entry = json.loads(result.stdout)["libraries"][0]
    assert entry["locked_version"] == "4.17.21"
    assert entry["locked_in"] == "package-lock.json"
    assert entry["ecosystem"] == "node"
    assert entry["version_drift"] is True


# --- --library ---------------------------------------------------------------


def test_library_filter_resolves_one_package(tmp_path: Path) -> None:
    """research-lib needs the version *this project* declares before it can
    fill in `> **Version Checked**:`."""
    _write_declared(tmp_path, ">=1.0")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "duckdb"\nversion = "1.4.0"\n', encoding="utf-8"
    )

    result = run_inventory(tmp_path, "--library", "DuckDB")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["library"] == "duckdb"
    assert payload["dependencies"] == [
        {
            "name": "duckdb",
            "declared_spec": ">=1.0",
            "declared_in": "pyproject.toml [project].dependencies",
            "locked_version": "1.4.0",
            "locked_in": "uv.lock",
            "ecosystem": "python",
        }
    ]


def test_library_filter_narrows_the_doc_list(tmp_path: Path) -> None:
    write_library(tmp_path, "duckdb.md", "# DuckDB\n")
    write_library(tmp_path, "fastapi.md", "# FastAPI\n")

    result = run_inventory(tmp_path, "--library", "fastapi")

    payload = json.loads(result.stdout)
    assert [entry["file"] for entry in payload["libraries"]] == ["fastapi.md"]


def test_library_filter_rejects_a_non_package_name(tmp_path: Path) -> None:
    result = run_inventory(tmp_path, "--library", "///")

    assert result.returncode == 1, result.stdout
    assert json.loads(result.stdout)["ok"] is False


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
