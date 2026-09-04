from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_DIR = REPO_ROOT / ".claude" / "skills" / "_shared"
SCRIPT = SHARED_DIR / "workspace.py"

ALL_SKILLS = (
    "feature",
    "spike",
    "troubleshoot",
    "team-execute",
    "plan",
    "research-lib",
)
TEAM_SKILLS = ("feature", "spike", "troubleshoot", "team-execute")

# Two titles with zero ASCII alnum characters, so both hit the sha1 fallback
# in _slugify. Content is irrelevant; only "purely non-Latin" matters here.
JAPANESE_TITLE_A = "ダックスフントの多施設調査"
JAPANESE_TITLE_B = "並行処理性能改善案"


def _load_module(path: Path, name: str) -> ModuleType:
    """Import *path* as a standalone module without executing its __main__ block."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


workspace = _load_module(SCRIPT, "workspace_under_test")
append_state_block = _load_module(
    SHARED_DIR / "append_state_block.py", "append_state_block_under_test"
)


def run_workspace(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--project-root", str(tmp_path), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def parsed(result: subprocess.CompletedProcess[str]) -> dict:
    """Assert stdout is exactly one JSON object and return it parsed."""
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected exactly one JSON line, got: {result.stdout!r}"
    return json.loads(lines[0])


def assert_all_relative(*values: str) -> None:
    for value in values:
        assert not value.startswith("/"), f"expected repo-relative path, got {value!r}"
        assert not Path(value).is_absolute(), f"expected relative path, got {value!r}"


# --- _slugify unit tests (direct import, no subprocess) --------------------


ASCII_SAMPLE_TITLES = [
    "DuckDB Multi Tenant Plan",
    "Fix bug #123: race condition!!",
    "  leading and trailing spaces  ",
    "UPPER_CASE_WITH_UNDERSCORES",
    "a" * 100,  # exercises the 64-char truncation
]


@pytest.mark.parametrize("title", ASCII_SAMPLE_TITLES)
def test_slugify_matches_append_state_block_for_ascii_titles(title: str) -> None:
    expected = append_state_block._slugify(title)
    assert expected != "untitled", "sample title should not hit the empty fallback"
    assert workspace._slugify(title) == expected


def test_slugify_empty_case_diverges_from_append_state_block_default() -> None:
    """append_state_block falls back to "untitled"; workspace must not, since
    two different untitled-colliding titles would otherwise clobber each
    other's workspace."""
    assert append_state_block._slugify(JAPANESE_TITLE_A) == "untitled"
    result = workspace._slugify(JAPANESE_TITLE_A)
    assert result != "untitled"
    assert re.fullmatch(r"t-[0-9a-f]{12}", result)


def test_slugify_is_deterministic_in_process() -> None:
    assert workspace._slugify(JAPANESE_TITLE_A) == workspace._slugify(JAPANESE_TITLE_A)


def test_required_keys_match_spec() -> None:
    assert workspace.REQUIRED_KEYS == {
        "feature": ("brief", "codebase_scan"),
        "spike": ("brief", "research", "feasibility", "report"),
        "troubleshoot": ("bug_report", "context", "root_cause", "impact"),
        "team-execute": ("review_security", "review_quality", "review_tests"),
        "plan": ("plan_doc",),
        "research-lib": ("lib_doc",),
        "design-tracker": ("design_input",),
    }


def test_diagnosis_is_not_a_default_required_key() -> None:
    """The diagnosis report is a Phase 3 deliverable. Making it required by
    default would make every Phase 1-2 `--verify` run fail on a document that
    is not supposed to exist yet, so Phase 3 asks for it with --require."""
    assert "diagnosis" in workspace.PATH_TEMPLATES["troubleshoot"]
    assert "diagnosis" not in workspace.REQUIRED_KEYS["troubleshoot"]


def test_every_skill_has_a_template_for_each_required_key() -> None:
    for skill, keys in workspace.REQUIRED_KEYS.items():
        for key in keys:
            assert key in workspace.PATH_TEMPLATES[skill], (
                f"{skill}: required key {key!r} has no path template"
            )


def test_skill_choices_and_templates_agree() -> None:
    assert set(workspace.SKILL_CHOICES) == set(workspace.PATH_TEMPLATES)
    assert set(workspace.SKILL_CHOICES) == set(workspace.REQUIRED_KEYS)


# --- resolve (happy path) ---------------------------------------------------


@pytest.mark.parametrize("skill", TEAM_SKILLS)
def test_resolve_happy_path(tmp_path: Path, skill: str) -> None:
    result = run_workspace(tmp_path, "--skill", skill, "--title", "DuckDB Plan")

    assert result.returncode == 0, result.stderr
    data = parsed(result)

    assert data["ok"] is True
    assert data["skill"] == skill
    assert data["slug"] == "duckdb-plan"
    assert data["team_name"] == f"{skill}-duckdb-plan"
    assert data["created"] == []
    assert data["verify"] is None
    assert "team_dir" in data["paths"]


def test_resolve_only_makes_no_filesystem_writes(tmp_path: Path) -> None:
    result = run_workspace(tmp_path, "--skill", "spike", "--title", "No Writes")

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_paths_match_spec_table_for_feature(tmp_path: Path) -> None:
    data = parsed(run_workspace(tmp_path, "--skill", "feature", "--title", "X"))
    slug = data["slug"]
    assert data["paths"] == {
        "brief": f".claude/docs/research/feature-{slug}-brief.md",
        "codebase_scan": f".claude/docs/research/feature-{slug}-codebase.md",
        "research": f".claude/docs/research/{slug}.md",
        "state_input": f".claude/logs/state-input-{slug}.json",
        "team_dir": f".claude/logs/agent-teams/feature-{slug}/",
    }


def test_paths_match_spec_table_for_spike(tmp_path: Path) -> None:
    data = parsed(run_workspace(tmp_path, "--skill", "spike", "--title", "X"))
    slug = data["slug"]
    assert data["paths"] == {
        "brief": f".claude/docs/research/spike-{slug}-brief.md",
        "research": f".claude/docs/research/spike-{slug}-research.md",
        "feasibility": f".claude/docs/research/spike-{slug}-feasibility.md",
        "report": f".claude/docs/research/spike-{slug}.md",
        "prototype_dir": f".claude/spikes/{slug}/",
        "team_dir": f".claude/logs/agent-teams/spike-{slug}/",
    }
    assert data["dirs"] == sorted(
        {
            ".claude/docs/research",
            f".claude/logs/agent-teams/spike-{slug}",
            f".claude/spikes/{slug}",
        }
    )


def test_paths_match_spec_table_for_troubleshoot(tmp_path: Path) -> None:
    data = parsed(run_workspace(tmp_path, "--skill", "troubleshoot", "--title", "X"))
    slug = data["slug"]
    assert data["paths"] == {
        "bug_report": f".claude/docs/research/troubleshoot-{slug}-bug-report.md",
        "context": f".claude/docs/research/troubleshoot-{slug}-context.md",
        "root_cause": f".claude/docs/research/troubleshoot-{slug}-root-cause.md",
        "impact": f".claude/docs/research/troubleshoot-{slug}-impact.md",
        "diagnosis": f".claude/logs/troubleshoot-{slug}-diagnosis.md",
        "state_input": f".claude/logs/state-input-{slug}.json",
        "team_dir": f".claude/logs/agent-teams/troubleshoot-{slug}/",
    }


def test_paths_match_spec_table_for_team_execute(tmp_path: Path) -> None:
    data = parsed(run_workspace(tmp_path, "--skill", "team-execute", "--title", "X"))
    slug = data["slug"]
    assert data["paths"] == {
        "review_security": f".claude/docs/research/review-security-{slug}.md",
        "review_quality": f".claude/docs/research/review-quality-{slug}.md",
        "review_tests": f".claude/docs/research/review-tests-{slug}.md",
        "diff_file": f".claude/logs/review-diff-{slug}.patch",
        "team_dir": f".claude/logs/agent-teams/team-execute-{slug}/",
    }


def test_paths_match_spec_table_for_plan(tmp_path: Path) -> None:
    data = parsed(run_workspace(tmp_path, "--skill", "plan", "--title", "Auth Rework"))
    assert data["paths"] == {"plan_doc": ".claude/docs/plans/auth-rework.md"}
    assert data["dirs"] == [".claude/docs/plans"]


def test_paths_match_spec_table_for_research_lib(tmp_path: Path) -> None:
    data = parsed(
        run_workspace(tmp_path, "--skill", "research-lib", "--title", "ruamel.yaml")
    )
    assert data["slug"] == "ruamel.yaml"
    assert data["paths"] == {"lib_doc": ".claude/docs/libraries/ruamel.yaml.md"}


def test_paths_match_spec_table_for_design_tracker(tmp_path: Path) -> None:
    data = parsed(
        run_workspace(tmp_path, "--skill", "design-tracker", "--title", "Adopt DuckDB")
    )
    assert data["paths"] == {
        "design_input": ".claude/logs/design-input-adopt-duckdb.json"
    }
    assert data["dirs"] == [".claude/logs"]


def test_design_tracker_input_path_is_per_invocation(tmp_path: Path) -> None:
    """Two concurrent recordings must not share one input file: the writer
    reads it after the caller writes it, so a shared path silently swaps one
    decision's input for another's."""
    first = parsed(
        run_workspace(tmp_path, "--skill", "design-tracker", "--title", "Use ReAct")
    )
    second = parsed(
        run_workspace(tmp_path, "--skill", "design-tracker", "--title", "Use DuckDB")
    )
    assert first["paths"]["design_input"] != second["paths"]["design_input"]


def test_design_tracker_verify_checks_the_input_file(tmp_path: Path) -> None:
    resolved = parsed(
        run_workspace(tmp_path, "--skill", "design-tracker", "--slug", "duckdb")
    )
    target = tmp_path / resolved["paths"]["design_input"]

    missing = run_workspace(
        tmp_path, "--skill", "design-tracker", "--slug", "duckdb", "--verify"
    )
    assert missing.returncode == 2, missing.stderr
    assert parsed(missing)["verify"]["missing"] == ["design_input"]

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '{"decisions": [{"decision": "Use DuckDB", "rationale": "embedded"}]}\n',
        encoding="utf-8",
    )
    present = run_workspace(
        tmp_path, "--skill", "design-tracker", "--slug", "duckdb", "--verify"
    )
    assert present.returncode == 0, present.stderr
    assert parsed(present)["verify"]["ok"] is True


def test_require_diagnosis_checks_the_phase_3_report(tmp_path: Path) -> None:
    resolved = parsed(run_workspace(tmp_path, "--skill", "troubleshoot", "--slug", "e"))
    for key in workspace.REQUIRED_KEYS["troubleshoot"]:
        target = tmp_path / resolved["paths"][key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x" * 25, encoding="utf-8")

    without = run_workspace(
        tmp_path, "--skill", "troubleshoot", "--slug", "e", "--verify"
    )
    assert without.returncode == 0, without.stderr

    with_require = run_workspace(
        tmp_path,
        "--skill",
        "troubleshoot",
        "--slug",
        "e",
        "--verify",
        "--require",
        "diagnosis",
    )
    assert with_require.returncode == 2, with_require.stderr
    assert parsed(with_require)["verify"]["missing"] == ["diagnosis"]

    diagnosis = tmp_path / resolved["paths"]["diagnosis"]
    diagnosis.parent.mkdir(parents=True, exist_ok=True)
    diagnosis.write_text("## Diagnosis Report: e\n" + "x" * 25, encoding="utf-8")
    filled = run_workspace(
        tmp_path,
        "--skill",
        "troubleshoot",
        "--slug",
        "e",
        "--verify",
        "--require",
        "diagnosis",
    )
    assert filled.returncode == 0, filled.stderr


# --- --teammate --------------------------------------------------------------


@pytest.mark.parametrize("skill", TEAM_SKILLS)
def test_teammate_adds_a_work_log_inside_the_team_dir(
    tmp_path: Path, skill: str
) -> None:
    data = parsed(
        run_workspace(
            tmp_path, "--skill", skill, "--slug", "shared", "--teammate", "backend-dev"
        )
    )
    assert (
        data["paths"]["work_log"]
        == f".claude/logs/agent-teams/{skill}-shared/backend-dev.md"
    )
    assert data["paths"]["work_log"].startswith(data["paths"]["team_dir"])


def test_work_log_is_absent_without_teammate(tmp_path: Path) -> None:
    data = parsed(run_workspace(tmp_path, "--skill", "spike", "--slug", "s"))
    assert "work_log" not in data["paths"]


def test_teammate_needs_no_extra_directory(tmp_path: Path) -> None:
    with_teammate = parsed(
        run_workspace(tmp_path, "--skill", "spike", "--slug", "s", "--teammate", "a")
    )
    without = parsed(run_workspace(tmp_path, "--skill", "spike", "--slug", "s"))
    assert with_teammate["dirs"] == without["dirs"]


@pytest.mark.parametrize("bad", ["Backend", "back end", "../etc"])
def test_invalid_teammate_is_rejected(tmp_path: Path, bad: str) -> None:
    result = run_workspace(
        tmp_path, "--skill", "spike", "--slug", "s", f"--teammate={bad}", "--create"
    )
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False
    assert list(tmp_path.iterdir()) == []


def test_teammate_is_rejected_for_a_teamless_skill(tmp_path: Path) -> None:
    result = run_workspace(
        tmp_path, "--skill", "plan", "--slug", "p", "--teammate", "backend"
    )
    assert result.returncode == 1, result.stderr
    assert "team" in parsed(result)["error"]


# --- --require ---------------------------------------------------------------


def test_require_adds_a_key_to_the_verified_set(tmp_path: Path) -> None:
    resolved = parsed(run_workspace(tmp_path, "--skill", "spike", "--slug", "req"))
    for key in workspace.REQUIRED_KEYS["spike"]:
        target = tmp_path / resolved["paths"][key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x" * 25, encoding="utf-8")

    without = run_workspace(tmp_path, "--skill", "spike", "--slug", "req", "--verify")
    assert without.returncode == 0, without.stderr

    with_require = run_workspace(
        tmp_path,
        "--skill",
        "spike",
        "--slug",
        "req",
        "--verify",
        "--require",
        "prototype_dir",
    )
    assert with_require.returncode == 2, with_require.stderr
    data = parsed(with_require)
    assert "prototype_dir" in data["verify"]["required"]
    assert "prototype_dir" in data["verify"]["missing"]


def test_require_accepts_a_directory_artifact_with_content(tmp_path: Path) -> None:
    resolved = parsed(run_workspace(tmp_path, "--skill", "spike", "--slug", "dir"))
    for key in workspace.REQUIRED_KEYS["spike"]:
        target = tmp_path / resolved["paths"][key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x" * 25, encoding="utf-8")
    prototype = tmp_path / resolved["paths"]["prototype_dir"]
    prototype.mkdir(parents=True, exist_ok=True)

    empty_dir = run_workspace(
        tmp_path,
        "--skill",
        "spike",
        "--slug",
        "dir",
        "--verify",
        "--require",
        "prototype_dir",
    )
    assert empty_dir.returncode == 2, "an empty prototype dir must not verify"
    assert parsed(empty_dir)["verify"]["empty"] == ["prototype_dir"]

    (prototype / "main.py").write_text(
        "print('hello prototype run')\n", encoding="utf-8"
    )
    filled = run_workspace(
        tmp_path,
        "--skill",
        "spike",
        "--slug",
        "dir",
        "--verify",
        "--require",
        "prototype_dir",
    )
    assert filled.returncode == 0, filled.stderr
    assert parsed(filled)["verify"]["ok"] is True


def test_require_is_repeatable(tmp_path: Path) -> None:
    result = run_workspace(
        tmp_path,
        "--skill",
        "feature",
        "--slug",
        "multi",
        "--verify",
        "--require",
        "research",
        "--require",
        "state_input",
    )
    assert result.returncode == 2, result.stderr
    required = parsed(result)["verify"]["required"]
    assert {"research", "state_input"} <= set(required)


def test_unknown_require_key_is_an_error(tmp_path: Path) -> None:
    result = run_workspace(
        tmp_path, "--skill", "spike", "--slug", "s", "--verify", "--require", "nope"
    )
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


def test_require_without_verify_is_an_error(tmp_path: Path) -> None:
    result = run_workspace(
        tmp_path, "--skill", "spike", "--slug", "s", "--require", "research"
    )
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


# --- guarded writes ----------------------------------------------------------


def test_create_against_a_file_shaped_agents_dir_reports_json(tmp_path: Path) -> None:
    """Regression: --create used to raise NotADirectoryError and print a
    traceback with no JSON at all when `.claude` existed as a file."""
    (tmp_path / ".claude").write_text("not a directory\n", encoding="utf-8")

    result = run_workspace(
        tmp_path, "--skill", "spike", "--title", "Guarded Write", "--create"
    )

    assert result.returncode == 3, result.stderr
    assert "Traceback" not in result.stderr
    data = parsed(result)
    assert data["ok"] is False
    assert "error" in data


def test_slug_flag_resolves_same_paths_as_title_derived_slug(tmp_path: Path) -> None:
    from_title = parsed(
        run_workspace(
            tmp_path, "--skill", "troubleshoot", "--title", "Consistency Check"
        )
    )
    from_slug = parsed(
        run_workspace(tmp_path, "--skill", "troubleshoot", "--slug", from_title["slug"])
    )
    assert from_slug["paths"] == from_title["paths"]
    assert from_slug["team_name"] == from_title["team_name"]


# --- --create ----------------------------------------------------------------


def test_create_makes_directories(tmp_path: Path) -> None:
    result = run_workspace(
        tmp_path, "--skill", "spike", "--title", "Create Me", "--create"
    )

    assert result.returncode == 0, result.stderr
    data = parsed(result)

    assert sorted(data["created"]) == sorted(data["dirs"])
    for rel_dir in data["dirs"]:
        assert (tmp_path / rel_dir).is_dir()


def test_create_is_idempotent(tmp_path: Path) -> None:
    first = parsed(
        run_workspace(tmp_path, "--skill", "spike", "--title", "Idempotent", "--create")
    )
    assert first["created"] != []

    second_result = run_workspace(
        tmp_path, "--skill", "spike", "--title", "Idempotent", "--create"
    )
    assert second_result.returncode == 0, second_result.stderr
    second = parsed(second_result)

    assert second["created"] == []
    assert second["dirs"] == first["dirs"]
    for rel_dir in second["dirs"]:
        assert (tmp_path / rel_dir).is_dir()


# --- --verify ------------------------------------------------------------


def test_verify_passes_when_all_required_present(tmp_path: Path) -> None:
    skill = "spike"
    resolved = parsed(
        run_workspace(tmp_path, "--skill", skill, "--title", "Verify Pass")
    )
    slug = resolved["slug"]

    for key in workspace.REQUIRED_KEYS[skill]:
        target = tmp_path / resolved["paths"][key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x" * 25, encoding="utf-8")

    result = run_workspace(tmp_path, "--skill", skill, "--slug", slug, "--verify")

    assert result.returncode == 0, result.stderr
    data = parsed(result)
    assert data["ok"] is True
    assert data["verify"]["ok"] is True
    assert data["verify"]["missing"] == []
    assert data["verify"]["empty"] == []
    assert sorted(data["verify"]["present"]) == sorted(workspace.REQUIRED_KEYS[skill])


def test_verify_fails_on_missing_required(tmp_path: Path) -> None:
    skill = "troubleshoot"
    result = run_workspace(
        tmp_path, "--skill", skill, "--title", "Verify Missing", "--verify"
    )

    assert result.returncode == 2, result.stderr
    data = parsed(result)
    assert data["ok"] is False
    assert sorted(data["verify"]["missing"]) == sorted(workspace.REQUIRED_KEYS[skill])
    assert data["verify"]["present"] == []


def test_verify_fails_on_effectively_empty_content(tmp_path: Path) -> None:
    skill = "feature"
    resolved = parsed(
        run_workspace(tmp_path, "--skill", skill, "--title", "Verify Empty")
    )
    slug = resolved["slug"]

    brief = tmp_path / resolved["paths"]["brief"]
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("x" * 25, encoding="utf-8")
    target = tmp_path / resolved["paths"]["codebase_scan"]
    target.write_text("too short", encoding="utf-8")  # < 20 stripped chars

    result = run_workspace(tmp_path, "--skill", skill, "--slug", slug, "--verify")

    assert result.returncode == 2, result.stderr
    data = parsed(result)
    assert data["verify"]["empty"] == ["codebase_scan"]
    assert data["verify"]["missing"] == []


# --- bad args (exit 1) -------------------------------------------------------


def test_title_and_slug_together_is_an_error(tmp_path: Path) -> None:
    result = run_workspace(tmp_path, "--skill", "spike", "--title", "X", "--slug", "x")

    assert result.returncode == 1, result.stderr
    data = parsed(result)
    assert data["ok"] is False
    assert "error" in data


def test_neither_title_nor_slug_is_an_error(tmp_path: Path) -> None:
    result = run_workspace(tmp_path, "--skill", "spike")

    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


def test_create_and_verify_together_is_an_error(tmp_path: Path) -> None:
    result = run_workspace(
        tmp_path, "--skill", "spike", "--title", "X", "--create", "--verify"
    )

    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


def test_unknown_skill_is_an_error(tmp_path: Path) -> None:
    result = run_workspace(tmp_path, "--skill", "bogus", "--title", "X")

    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


def test_missing_skill_is_an_error(tmp_path: Path) -> None:
    result = run_workspace(tmp_path, "--title", "X")

    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


# --- --slug format guard (rejects path traversal / malformed slugs) ---------


INVALID_SLUGS = [
    "MySlug",  # uppercase
    "my slug",  # space
    "-leading-hyphen",  # must start with [a-z0-9]
]


@pytest.mark.parametrize("bad_slug", INVALID_SLUGS)
def test_invalid_slug_format_is_rejected(tmp_path: Path, bad_slug: str) -> None:
    # Combined "--slug=value" form isolates validate_args()/SLUG_RE
    # specifically: a value passed as a *separate* argv token that starts
    # with "-" (e.g. "-leading-hyphen") is ambiguous for argparse's own
    # tokenizer -- it looks like an unknown option -- so that form would be
    # rejected by argparse itself first. JsonArgumentParser (below) covers
    # that path too, but the single-token form here pins down this guard's
    # own behavior in isolation.
    result = run_workspace(tmp_path, "--skill", "spike", f"--slug={bad_slug}")

    assert result.returncode == 1, result.stderr
    data = parsed(result)
    assert data["ok"] is False
    assert "error" in data


def test_dotted_slug_is_accepted_only_for_research_lib(tmp_path: Path) -> None:
    accepted = run_workspace(tmp_path, "--skill", "research-lib", "--slug=ruamel.yaml")
    assert accepted.returncode == 0, accepted.stderr
    assert parsed(accepted)["paths"]["lib_doc"].endswith("ruamel.yaml.md")

    rejected = run_workspace(tmp_path, "--skill", "spike", "--slug=ruamel.yaml")
    assert rejected.returncode == 1, rejected.stderr
    assert parsed(rejected)["ok"] is False


@pytest.mark.parametrize("bad_slug", ["../etc", "Ruamel.Yaml", ".hidden"])
def test_invalid_package_slug_is_rejected(tmp_path: Path, bad_slug: str) -> None:
    result = run_workspace(tmp_path, "--skill", "research-lib", f"--slug={bad_slug}")
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


def test_unusable_package_title_is_an_error_not_a_hash_slug(tmp_path: Path) -> None:
    """A package name is not free text: a title that normalizes to something
    PACKAGE_SLUG_RE rejects must fail loudly instead of inventing a slug that
    lib_inventory.py would never match."""
    result = run_workspace(
        tmp_path, "--skill", "research-lib", "--title", JAPANESE_TITLE_A
    )
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


def test_space_separated_dash_leading_slug_still_emits_json(tmp_path: Path) -> None:
    """Regression check: --slug passed as a separate argv token that looks
    like an option (e.g. "-leading-hyphen") makes argparse's own tokenizer
    report "expected one argument" before validate_args() ever runs.
    JsonArgumentParser must still turn that into an exit-1 JSON error rather
    than argparse's default stderr usage text + exit code 2."""
    result = run_workspace(tmp_path, "--skill", "spike", "--slug", "-leading-hyphen")

    assert result.returncode == 1, result.stderr
    assert result.stdout.strip(), "JsonArgumentParser must still emit JSON on stdout"
    data = parsed(result)
    assert data["ok"] is False
    assert "error" in data


def test_unrecognized_flag_still_emits_json_via_json_argument_parser(
    tmp_path: Path,
) -> None:
    """JsonArgumentParser must convert argparse's own parsing failures (not
    just validate_args() checks) into the JSON-on-stdout / exit-1 contract --
    e.g. an unrecognized flag, which plain argparse rejects with stderr usage
    text and exit code 2."""
    result = run_workspace(tmp_path, "--skill", "spike", "--title", "X", "--bogus-flag")

    assert result.returncode == 1, result.stderr
    data = parsed(result)
    assert data["ok"] is False
    assert "error" in data


def test_slug_path_traversal_is_rejected_before_any_write(tmp_path: Path) -> None:
    """A hand-supplied --slug is interpolated straight into filesystem paths
    (unlike --title, which always goes through _slugify() first), so it must
    be rejected before --create ever touches the filesystem."""
    result = run_workspace(
        tmp_path, "--skill", "spike", "--slug", "../../etc", "--create"
    )

    assert result.returncode == 1, result.stderr
    data = parsed(result)
    assert data["ok"] is False
    assert "error" in data
    assert list(tmp_path.iterdir()) == []


REPRESENTATIVE_TITLES = [
    "DuckDB Multi Tenant Plan",
    "a" * 100,  # exercises the 64-char truncation
    JAPANESE_TITLE_A,  # exercises the sha1 fallback
]


@pytest.mark.parametrize("title", REPRESENTATIVE_TITLES)
def test_slugify_output_always_satisfies_slug_re(title: str) -> None:
    """Property: whatever _slugify() can produce, SLUG_RE must accept it --
    the --title and --slug code paths must never diverge on what counts as
    a valid slug."""
    slug = workspace._slugify(title)
    assert workspace.SLUG_RE.match(slug), (
        f"_slugify({title!r}) produced {slug!r}, which SLUG_RE rejects"
    )


@pytest.mark.parametrize("title", REPRESENTATIVE_TITLES)
def test_slug_round_trip_from_title_is_always_accepted(
    tmp_path: Path, title: str
) -> None:
    from_title = parsed(run_workspace(tmp_path, "--skill", "spike", "--title", title))
    assert from_title["ok"] is True

    slug_result = run_workspace(
        tmp_path, "--skill", "spike", "--slug", from_title["slug"]
    )
    assert slug_result.returncode == 0, slug_result.stderr
    from_slug = parsed(slug_result)
    assert from_slug["paths"] == from_title["paths"]
    assert from_slug["team_name"] == from_title["team_name"]


# --- slug determinism / non-Latin fallback -----------------------------------


def test_slug_is_deterministic_across_runs(tmp_path: Path) -> None:
    first = parsed(run_workspace(tmp_path, "--skill", "spike", "--title", "Same Title"))
    second = parsed(
        run_workspace(tmp_path, "--skill", "spike", "--title", "Same Title")
    )
    assert first["slug"] == second["slug"]


def test_japanese_title_falls_back_to_stable_hash_slug(tmp_path: Path) -> None:
    first = parsed(
        run_workspace(tmp_path, "--skill", "spike", "--title", JAPANESE_TITLE_A)
    )
    second = parsed(
        run_workspace(tmp_path, "--skill", "spike", "--title", JAPANESE_TITLE_A)
    )

    assert first["slug"] == second["slug"]
    assert re.fullmatch(r"t-[0-9a-f]{12}", first["slug"])


def test_two_different_japanese_titles_never_collide(tmp_path: Path) -> None:
    slug_a = parsed(
        run_workspace(tmp_path, "--skill", "spike", "--title", JAPANESE_TITLE_A)
    )["slug"]
    slug_b = parsed(
        run_workspace(tmp_path, "--skill", "spike", "--title", JAPANESE_TITLE_B)
    )["slug"]

    assert slug_a != slug_b


# --- no emitted path is ever absolute ----------------------------------------


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_no_emitted_path_is_absolute(tmp_path: Path, skill: str) -> None:
    result = run_workspace(
        tmp_path, "--skill", skill, "--title", "Absolute Check", "--create"
    )
    data = parsed(result)

    assert_all_relative(*data["paths"].values())
    assert_all_relative(*data["dirs"])
    assert_all_relative(*data["created"])
