"""Enforce the Writer Safety Contract for _shared/update_design.py.

``update_design.py`` and ``append_state_block.py`` were the only shared scripts
with no test file, which is exactly why ``update_design.py`` drifted from the
contract it is documented to follow (no pre-replace validation, no dedup of
section updates, decision dedup keyed on today's date, unescaped table cells,
rows inserted after the section's trailing blank line).

Every test runs against a copy of the repository's own DESIGN.md under
``--project-root tmp_path``, so the real document is never touched and the
writers stay pinned to the document shape they actually have to edit.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "_shared" / "update_design.py"
TEMPLATE_DESIGN = REPO_ROOT / ".claude" / "docs" / "DESIGN.md"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update_design = _load_module(SCRIPT, "update_design_under_test")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A fixture repository whose DESIGN.md is a copy of the real one."""
    design = tmp_path / ".claude" / "docs" / "DESIGN.md"
    design.parent.mkdir(parents=True)
    shutil.copy(TEMPLATE_DESIGN, design)
    return tmp_path


def design_text(project: Path) -> str:
    return (project / ".claude" / "docs" / "DESIGN.md").read_text(encoding="utf-8")


def write_input(project: Path, data: dict) -> Path:
    path = project / "input.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(project: Path, data: dict, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--input",
            str(write_input(project, data)),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def parsed(result: subprocess.CompletedProcess[str]) -> dict:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected exactly one JSON line, got: {result.stdout!r}"
    return json.loads(lines[0])


def table_rows(text: str, header: str) -> list[str]:
    lines = text.splitlines()
    found = update_design._find_table(lines, header)
    assert found is not None, f"table {header!r} not found"
    header_idx, last_row = found
    return lines[header_idx + 2 : last_row + 1]


DECISION = {
    "decisions": [
        {
            "decision": "Use one shared writer",
            "rationale": "single validation path",
            "alternatives": "hand edits",
        }
    ]
}

REQUIREMENTS_HEADER = "| ID | Requirement | Priority | Notes |"
NFR_HEADER = "| Category | Requirement | Metric / Target |"
TECH_HEADER = "| Area | Technology | Rationale | Alternatives Considered |"
ROLES_HEADER = "| Agent | Role | Responsibilities |"


# --- dry run -----------------------------------------------------------------


def test_dry_run_changes_nothing_on_disk(project: Path) -> None:
    before = design_text(project)
    result = run(project, DECISION)

    assert result.returncode == 0, result.stderr
    data = parsed(result)
    assert data["ok"] is True
    assert data["result"] == "preview"
    assert design_text(project) == before


def test_dry_run_preview_file_holds_the_composed_document(project: Path) -> None:
    data = parsed(run(project, DECISION))
    preview = Path(data["preview_file"])
    assert preview.is_file()
    assert "Use one shared writer" in preview.read_text(encoding="utf-8")
    assert data["artifacts"] == [
        preview.resolve().relative_to(project.resolve()).as_posix()
    ]


def test_apply_reports_the_document_as_an_artifact(project: Path) -> None:
    data = parsed(run(project, DECISION, "--apply"))
    assert data["result"] == "applied"
    assert data["artifacts"] == [".claude/docs/DESIGN.md"]


# --- typed table writers -----------------------------------------------------


def test_requirement_row_lands_inside_the_table(project: Path) -> None:
    """Regression: a hand-written row was inserted after the section's trailing
    blank line, so it was no longer part of the table, and the blank line before
    the next heading was consumed."""
    result = run(
        project,
        {
            "requirements": [
                {
                    "id": "FR-7",
                    "requirement": "Serve reports",
                    "priority": "High",
                    "notes": "n",
                }
            ]
        },
        "--apply",
    )
    assert result.returncode == 0, result.stderr
    text = design_text(project)
    lines = text.splitlines()

    row_idx = next(i for i, line in enumerate(lines) if line.startswith("| FR-7 "))
    assert lines[row_idx - 1].startswith("|"), "row must be adjacent to the table"

    next_heading = next(
        i for i in range(row_idx, len(lines)) if lines[i].startswith("#")
    )
    assert lines[next_heading - 1].strip() == "", (
        "the blank line before the next heading must survive"
    )
    assert parsed(result)["rows_appended"] == {"requirements": 1}


@pytest.mark.parametrize(
    ("key", "row", "header"),
    [
        (
            "requirements",
            {"id": "FR-9", "requirement": "A|B split", "priority": "Low"},
            REQUIREMENTS_HEADER,
        ),
        (
            "nfr",
            {"category": "Security", "requirement": "TLS 1.3|1.2", "metric": "p99"},
            NFR_HEADER,
        ),
        (
            "tech_choices",
            {
                "area": "Storage",
                "technology": "SQLite",
                "rationale": "embedded|simple",
                "alternatives": "Postgres",
            },
            TECH_HEADER,
        ),
        (
            "agent_roles",
            {"agent": "Lead", "role": "Router", "responsibilities": "route|verify"},
            ROLES_HEADER,
        ),
    ],
)
def test_pipe_in_a_cell_is_escaped_and_never_splits_the_row(
    project: Path, key: str, row: dict, header: str
) -> None:
    result = run(project, {key: [row]}, "--apply")
    assert result.returncode == 0, result.stderr

    text = design_text(project)
    assert "\\|" in text
    width = len(update_design._split_row(header))
    for line in table_rows(text, header):
        assert len(update_design._split_row(line)) == width, (
            f"unescaped pipe split a cell: {line!r}"
        )


def test_multiline_cell_content_stays_on_one_row(project: Path) -> None:
    run(
        project,
        {
            "nfr": [
                {"category": "Availability", "requirement": "a\nb", "metric": "99.9%"}
            ]
        },
        "--apply",
    )
    rows = table_rows(design_text(project), NFR_HEADER)
    assert any("a<br>b" in row for row in rows)


def test_an_unfilled_template_row_is_completed_in_place(project: Path) -> None:
    """The DESIGN.md template ships "| Performance | | |"; filling it beats
    appending a second Performance row and leaving the empty one behind."""
    before = len(table_rows(design_text(project), NFR_HEADER))
    run(
        project,
        {
            "nfr": [
                {
                    "category": "Performance",
                    "requirement": "p95 < 200ms",
                    "metric": "200ms",
                }
            ]
        },
        "--apply",
    )
    rows = table_rows(design_text(project), NFR_HEADER)
    assert len(rows) == before
    assert any("p95 < 200ms" in row for row in rows)


def test_a_duplicate_requirement_id_is_a_contract_violation(project: Path) -> None:
    run(
        project,
        {"requirements": [{"id": "FR-42", "requirement": "First", "priority": "High"}]},
        "--apply",
    )
    result = run(
        project,
        {
            "requirements": [
                {"id": "FR-42", "requirement": "Different", "priority": "Low"}
            ]
        },
        "--apply",
    )
    assert result.returncode == 2, result.stderr
    data = parsed(result)
    assert data["ok"] is False
    assert "FR-42" in data["error"]
    assert "Different" not in design_text(project)


def test_a_table_row_passed_as_a_section_update_is_refused(project: Path) -> None:
    """The untyped path is how the unescaped, orphaned row got written; it now
    names the typed key instead of writing anything."""
    result = run(
        project,
        {
            "section_updates": [
                {
                    "heading": "## 機能要件 (Functional Requirements)",
                    "content": "| FR-3 | x | y | z |",
                }
            ]
        },
        "--apply",
    )
    assert result.returncode == 2, result.stderr
    assert "requirements" in parsed(result)["error"]
    assert "FR-3" not in design_text(project)


# --- re-run safety -----------------------------------------------------------


def test_reapplying_the_same_table_rows_is_a_no_op(project: Path) -> None:
    payload = {
        "requirements": [{"id": "FR-5", "requirement": "Once", "priority": "High"}],
        "nfr": [{"category": "Security", "requirement": "TLS", "metric": "1.3"}],
        "tech_choices": [{"area": "CI", "technology": "GH Actions"}],
        "agent_roles": [{"agent": "Lead", "role": "Router"}],
    }
    first = run(project, payload, "--apply")
    assert first.returncode == 0, first.stderr
    after_first = design_text(project)

    second = run(project, payload, "--apply")
    assert second.returncode == 0, second.stderr
    data = parsed(second)
    assert data["result"] == "no-op"
    assert data["skipped_duplicates"] == 4
    assert design_text(project) == after_first


def test_reapplying_a_section_update_does_not_duplicate_it(project: Path) -> None:
    """Regression: section_updates were never deduped, so a retried phase
    appended the same paragraph again."""
    payload = {
        "section_updates": [
            {"heading": "## 制約 (Constraints)", "content": "- Stdlib only"}
        ]
    }
    run(project, payload, "--apply")
    run(project, payload, "--apply")
    assert design_text(project).count("- Stdlib only") == 1


def test_a_decision_reapplied_on_a_later_day_is_not_duplicated(project: Path) -> None:
    """Regression: decision dedup compared the date too, so the same decision
    re-applied tomorrow was written a second time."""
    first = run(project, DECISION, "--apply", "--now", "2026-07-25T09:00:00")
    assert first.returncode == 0, first.stderr
    assert "2026-07-25" in design_text(project)

    second = run(project, DECISION, "--apply", "--now", "2026-07-26T09:00:00")
    assert parsed(second)["result"] == "no-op"
    assert design_text(project).count("Use one shared writer") == 1


# --- --require-change --------------------------------------------------------


def test_require_change_turns_a_no_op_into_exit_2(project: Path) -> None:
    """design-tracker/SKILL.md told the agent to check ok:true and report
    "recorded"; a no-op satisfied that while writing nothing."""
    run(project, DECISION, "--apply")

    result = run(project, DECISION, "--apply", "--require-change")

    assert result.returncode == 2, result.stderr
    data = parsed(result)
    assert data["ok"] is False
    assert data["result"] == "no-op"
    assert data["artifacts"] == []


def test_require_change_is_satisfied_by_a_real_change(project: Path) -> None:
    result = run(project, DECISION, "--apply", "--require-change")
    assert result.returncode == 0, result.stderr
    assert parsed(result)["result"] == "applied"


def test_a_no_op_without_require_change_stays_exit_0(project: Path) -> None:
    run(project, DECISION, "--apply")
    result = run(project, DECISION, "--apply")
    assert result.returncode == 0, result.stderr
    assert parsed(result)["ok"] is True


# --- injectable clock --------------------------------------------------------


def test_now_makes_the_stamped_date_deterministic(project: Path) -> None:
    run(project, DECISION, "--apply", "--now", "2020-02-29T23:59:59")
    rows = table_rows(design_text(project), update_design.DECISIONS_HEADER)
    assert any(row.rstrip().endswith("| 2020-02-29 |") for row in rows)


def test_now_also_names_the_preview_file(project: Path) -> None:
    data = parsed(run(project, DECISION, "--now", "2020-02-29T23:59:59"))
    assert Path(data["preview_file"]).name == "design-preview-20200229-235959.md"


def test_an_unparseable_now_is_bad_args(project: Path) -> None:
    result = run(project, DECISION, "--now", "yesterday")
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


# --- concurrent modification + pre-replace validation ------------------------


def test_the_hash_guard_refuses_a_document_changed_since_load(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    design = project / ".claude" / "docs" / "DESIGN.md"
    real_read_text = Path.read_text
    reads = {"design": 0}

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "DESIGN.md":
            reads["design"] += 1
            if reads["design"] == 1:
                text = real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]
                # Simulate another writer landing between load and replace.
                real_write_text = Path.write_text
                real_write_text(self, text + "\n<!-- concurrent edit -->\n")  # type: ignore[arg-type]
                return text
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type,return-value]

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_design.py",
            "--project-root",
            str(project),
            "--input",
            str(write_input(project, DECISION)),
            "--apply",
        ],
    )

    assert update_design.main() == 3
    text = real_read_text(design)  # type: ignore[arg-type]
    assert "concurrent edit" in text, "the concurrent write must survive"
    assert "Use one shared writer" not in text, "our write must not have landed"


def test_validation_runs_before_the_replace_and_leaves_no_temp_file(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_shared/README.md requires validating the composed result *before*
    os.replace; the previous implementation replaced unconditionally."""
    design = project / ".claude" / "docs" / "DESIGN.md"
    before = design.read_text(encoding="utf-8")
    calls = {"n": 0}

    def failing_second_validation(new_text: str, original_text: str) -> str | None:
        calls["n"] += 1
        # First call is the pre-composition check; the second is the one made
        # against the bytes actually written to the temp file.
        return "injected structural damage" if calls["n"] == 2 else None

    monkeypatch.setattr(
        update_design, "validate_composition", failing_second_validation
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_design.py",
            "--project-root",
            str(project),
            "--input",
            str(write_input(project, DECISION)),
            "--apply",
        ],
    )

    assert update_design.main() == 2
    assert design.read_text(encoding="utf-8") == before
    leftovers = list(design.parent.glob(".design-md-*"))
    assert leftovers == [], f"temp file left behind: {leftovers}"


def test_a_malformed_table_blocks_the_write(project: Path) -> None:
    design = project / ".claude" / "docs" / "DESIGN.md"
    damaged = design.read_text(encoding="utf-8").replace(
        "| FR-1 | | | |", "| FR-1 | only two |"
    )
    design.write_text(damaged, encoding="utf-8")

    result = run(
        project,
        {"requirements": [{"id": "FR-8", "requirement": "New", "priority": "High"}]},
        "--apply",
    )

    assert result.returncode == 2, result.stderr
    assert "cells" in parsed(result)["error"]
    assert design.read_text(encoding="utf-8") == damaged


def test_a_lost_heading_blocks_the_write(project: Path) -> None:
    original = design_text(project)
    broken = original.replace("## Key Decisions\n", "Key Decisions\n") + "x" * 200
    error = update_design.validate_composition(broken, original)
    assert error is not None
    assert "Key Decisions" in error


# --- structure and input errors ----------------------------------------------


def test_a_missing_design_document_is_exit_2(tmp_path: Path) -> None:
    result = run(tmp_path, DECISION, "--apply")
    assert result.returncode == 2, result.stderr
    assert "init" in parsed(result)["error"]


def test_a_duplicated_decisions_table_is_refused(project: Path) -> None:
    design = project / ".claude" / "docs" / "DESIGN.md"
    text = design.read_text(encoding="utf-8")
    design.write_text(text + "\n" + update_design.DECISIONS_HEADER + "\n", "utf-8")

    result = run(project, DECISION, "--apply")
    assert result.returncode == 2, result.stderr
    assert "table" in parsed(result)["error"]


def test_an_empty_payload_is_bad_input(project: Path) -> None:
    result = run(project, {}, "--apply")
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


def test_an_unknown_row_field_is_bad_input(project: Path) -> None:
    result = run(project, {"nfr": [{"category": "X", "requirement": "y", "oops": "z"}]})
    assert result.returncode == 1, result.stderr
    assert "oops" in parsed(result)["error"]


def test_a_row_missing_a_required_field_is_bad_input(project: Path) -> None:
    result = run(project, {"requirements": [{"requirement": "no id"}]})
    assert result.returncode == 1, result.stderr
    assert "id" in parsed(result)["error"]


def test_unparseable_input_json_is_bad_input(project: Path) -> None:
    bad = project / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--input",
            str(bad),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


def test_help_exits_zero(project: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "--require-change" in result.stdout
