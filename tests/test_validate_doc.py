from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_DOC = REPO_ROOT / ".agents" / "skills" / "_shared" / "validate_doc.py"

# Per-file result shape — identical across every contract (role_variant is
# null for contracts without variants).
FILE_RESULT_KEYS = {
    "ok",
    "file",
    "role_variant",
    "sections_found",
    "sections_missing",
    "metadata_missing",
    "warnings",
}

# Directory-mode payload shape — stable whether or not --expect-files is given
# (``error`` is added on top when an expectation fails).
DIR_RESULT_KEYS = {
    "ok",
    "contract",
    "results",
    "files_checked",
    "files_failed",
    "expect_files",
    "warnings",
}

IMPLEMENTER_LOG = """\
# Work Log: Implementer
## Summary
Did the thing.
## Tasks Completed
- [x] task1: done
## Communication with Teammates
None
## Issues Encountered
None
"""

REVIEWER_LOG = """\
# Work Log: Reviewer
## Summary
Reviewed the thing.
## Review Scope
Files X, Y
## Findings
- [Low] foo.py:1 - nit
## Communication with Teammates
None
## Issues Encountered
None
"""

INCOMPLETE_IMPLEMENTER_LOG = """\
# Work Log: Broken
## Summary
Incomplete.
"""

INCOMPLETE_REVIEWER_LOG = """\
# Work Log: Broken Reviewer
## Summary
Incomplete.
## Review Scope
Files X
"""

LIB_DOC_OK = """\
# some-lib

> **Last Updated**: 2026-07-25
> **Version Checked**: 1.4.0

## Overview
It's a library.
## Core Features
- feature 1
## Constraints & Notes
None
## References
- https://example.com
"""

LIB_DOC_MISSING = """\
# some-lib

> **Last Updated**: 2026-07-25
> **Version Checked**: 1.4.0

## Overview
It's a library.
"""

# Every required heading, but no machine-readable version metadata: the state
# that made every research-lib doc invisible to update-lib-docs.
LIB_DOC_NO_METADATA = LIB_DOC_OK.replace(
    "> **Last Updated**: 2026-07-25\n> **Version Checked**: 1.4.0\n", ""
)

SPIKE_REPORT_OK = """\
# Spike: something
## Question
Can we do X?
## Verdict
Yes.
## Success Criteria Evaluation
Tried it, worked.
## Risks
None major.
## Recommendation
Implement it.
"""

SPIKE_REPORT_MISSING = """\
# Spike: something
## Question
Can we do X?
"""

BUG_REPORT_OK = """\
# Bug: something broke
## Error
It broke.
## Reproduction
1. Do X
2. See Y
## Immediate Context
Failing call chain.
## Affected Area
foo.py
## Initial Hypotheses
Maybe Z.
"""

BUG_REPORT_MISSING = """\
# Bug: something broke
## Error
It broke.
"""


def run_validate_doc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(VALIDATE_DOC), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# --- per-contract pass/fail ---


def test_lib_doc_contract_pass(tmp_path: Path) -> None:
    doc = _write(tmp_path / "some-lib.md", LIB_DOC_OK)
    result = run_validate_doc("--contract", "lib-doc", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True
    assert payload["sections_missing"] == []
    assert payload["role_variant"] is None


def test_lib_doc_contract_fail(tmp_path: Path) -> None:
    doc = _write(tmp_path / "some-lib.md", LIB_DOC_MISSING)
    result = run_validate_doc("--contract", "lib-doc", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    assert payload["ok"] is False
    assert payload["sections_missing"] == [
        "Core Features",
        "Constraints & Notes",
        "References",
    ]


def test_lib_doc_requires_the_version_metadata_block(tmp_path: Path) -> None:
    """All sections present but no `> **Version Checked**:` line is still a
    contract violation: without it the doc is invisible to update-lib-docs."""
    doc = _write(tmp_path / "some-lib.md", LIB_DOC_NO_METADATA)
    result = run_validate_doc("--contract", "lib-doc", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    assert payload["ok"] is False
    assert payload["sections_missing"] == []
    assert payload["metadata_missing"] == ["Last Updated", "Version Checked"]


def test_lib_doc_metadata_must_carry_a_value(tmp_path: Path) -> None:
    """An empty `> **Version Checked**:` is the same as no metadata at all."""
    doc = _write(
        tmp_path / "some-lib.md",
        LIB_DOC_OK.replace("> **Version Checked**: 1.4.0", "> **Version Checked**:"),
    )
    result = run_validate_doc("--contract", "lib-doc", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    assert payload["metadata_missing"] == ["Version Checked"]


def test_contracts_without_metadata_requirements_report_an_empty_list(
    tmp_path: Path,
) -> None:
    doc = _write(tmp_path / "log.md", IMPLEMENTER_LOG)
    result = run_validate_doc("--contract", "work-log", "--file", str(doc))
    assert json.loads(result.stdout)["metadata_missing"] == []


def test_spike_report_contract_pass(tmp_path: Path) -> None:
    doc = _write(tmp_path / "spike.md", SPIKE_REPORT_OK)
    result = run_validate_doc("--contract", "spike-report", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True


def test_spike_report_contract_fail(tmp_path: Path) -> None:
    doc = _write(tmp_path / "spike.md", SPIKE_REPORT_MISSING)
    result = run_validate_doc("--contract", "spike-report", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    assert payload["ok"] is False
    assert payload["sections_missing"] == [
        "Verdict",
        "Success Criteria Evaluation",
        "Risks",
        "Recommendation",
    ]


def test_bug_report_contract_pass(tmp_path: Path) -> None:
    doc = _write(tmp_path / "bug.md", BUG_REPORT_OK)
    result = run_validate_doc("--contract", "bug-report", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True


def test_bug_report_contract_fail(tmp_path: Path) -> None:
    doc = _write(tmp_path / "bug.md", BUG_REPORT_MISSING)
    result = run_validate_doc("--contract", "bug-report", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    assert payload["ok"] is False
    assert payload["sections_missing"] == [
        "Reproduction",
        "Immediate Context",
        "Affected Area",
        "Initial Hypotheses",
    ]


# --- new contracts: minimal failing document reports the right names ---------
#
# Each expected list is the contract's own required set, which the pinned
# template tests below tie back to the document the skill tells agents to write.

NEW_CONTRACT_EXPECTATIONS = {
    "plan-doc": (
        "## Implementation Plan: x\n### Purpose\np\n",
        ["Scope", "Implementation Steps", "Risks & Considerations", "Open Questions"],
    ),
    "spike-brief": (
        "## Spike Brief: x\n### Question\nq\n",
        [
            "Parameters",
            "Success Criteria",
            "Sub-questions",
            "Critical Path",
            "Investigation Plan",
        ],
    ),
    "diagnosis": (
        "## Diagnosis Report: x\n### Error Reproduction\nr\n",
        [
            "Root Cause",
            "Impact Assessment",
            "Fix Plan",
            "Alternative Approaches Considered",
            "Next Steps",
        ],
    ),
    "checkpoint-summary": (
        "## サマリ\n### 何をしたのか\n- a\n",
        [
            "どういうやり取りをユーザーと行ったのか",
            "どうやったのか",
            "途中でどういう課題が起こったのか",
            "将来のアクション",
        ],
    ),
    "progress": (
        "# PROGRESS\n## [2026-07-25-120000](x.md)\n### 何をしたのか\n- a\n",
        ["将来のアクション"],
    ),
    "guide": (
        "# Project Guide\n## 1. What is this project?\n- x\n",
        ["3. Recent Work", "5. Capabilities", "7. How to Resume Work"],
    ),
}


@pytest.mark.parametrize("contract", sorted(NEW_CONTRACT_EXPECTATIONS))
def test_new_contract_reports_its_missing_sections(
    tmp_path: Path, contract: str
) -> None:
    body, expected_missing = NEW_CONTRACT_EXPECTATIONS[contract]
    doc = _write(tmp_path / f"{contract}.md", body)

    result = run_validate_doc("--contract", contract, "--file", str(doc))
    payload = json.loads(result.stdout)

    assert result.returncode == 2, result.stderr
    assert payload["sections_missing"] == expected_missing


# --- feature-brief mode auto-detection ---------------------------------------

FEATURE_BRIEF_EXISTING = """\
## Feature Brief: x
### Current State
- Architecture: a
### Feature Goal
g
### Scope
- Include: i
### Complexity Classification (from Codex)
- Classification: SIMPLE
### Integration Points
- a: b
### Risks
- r: m
### Success Criteria
- c
"""

PROJECT_BRIEF_GREENFIELD = """\
## Project Brief: x
### Current State
- Architecture: a
### Goal
g
### Scope
- Include: i
### Constraints
- c
### Success Criteria
- c
"""


def test_feature_brief_existing_mode_auto_detect(tmp_path: Path) -> None:
    doc = _write(tmp_path / "brief.md", FEATURE_BRIEF_EXISTING)
    result = run_validate_doc("--contract", "feature-brief", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["role_variant"] == "existing"
    assert payload["sections_missing"] == []


def test_feature_brief_greenfield_mode_auto_detect(tmp_path: Path) -> None:
    doc = _write(tmp_path / "brief.md", PROJECT_BRIEF_GREENFIELD)
    result = run_validate_doc("--contract", "feature-brief", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["role_variant"] == "greenfield"
    assert payload["sections_missing"] == []


def test_feature_brief_existing_marker_selects_the_stricter_variant(
    tmp_path: Path,
) -> None:
    """One existing-mode heading flips the whole document, so an
    existing-mode brief cannot pass under the shorter greenfield set."""
    body = PROJECT_BRIEF_GREENFIELD.replace(
        "### Goal", "### Feature Goal"
    )  # existing-mode marker
    doc = _write(tmp_path / "hybrid.md", body)

    result = run_validate_doc("--contract", "feature-brief", "--file", str(doc))
    payload = json.loads(result.stdout)

    assert result.returncode == 2, result.stderr
    assert payload["role_variant"] == "existing"
    assert payload["sections_missing"] == [
        "Complexity Classification",
        "Integration Points",
        "Risks",
    ]


def test_greenfield_goal_is_not_satisfied_by_a_feature_goal_heading(
    tmp_path: Path,
) -> None:
    """`Goal` and `Feature Goal` are distinct required names — the whole-token
    prefix rule must not collapse one into the other. A brief with only
    `### Feature Goal` is judged in existing mode and must not silently satisfy
    the greenfield `Goal` requirement."""
    body = PROJECT_BRIEF_GREENFIELD.replace("### Goal", "### Feature Goal")
    doc = _write(tmp_path / "brief.md", body)
    payload = json.loads(
        run_validate_doc("--contract", "feature-brief", "--file", str(doc)).stdout
    )
    assert payload["role_variant"] == "existing"
    assert "Feature Goal" in payload["sections_found"]
    assert "Goal" not in payload["sections_found"]


# --- work-log variant auto-detection ---


def test_work_log_implementer_auto_detect(tmp_path: Path) -> None:
    doc = _write(tmp_path / "implementer.md", IMPLEMENTER_LOG)
    result = run_validate_doc("--contract", "work-log", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["role_variant"] == "implementer"
    assert payload["sections_missing"] == []


def test_work_log_reviewer_auto_detect(tmp_path: Path) -> None:
    doc = _write(tmp_path / "reviewer.md", REVIEWER_LOG)
    result = run_validate_doc("--contract", "work-log", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["role_variant"] == "reviewer"
    assert payload["sections_missing"] == []


def test_work_log_reviewer_marker_wins_even_with_tasks_completed(
    tmp_path: Path,
) -> None:
    # A single reviewer-only heading (Findings/Review Scope) is enough to flip
    # the whole file to the reviewer variant, even when implementer headings
    # are also present.
    hybrid = IMPLEMENTER_LOG + "\n## Findings\n- note\n"
    doc = _write(tmp_path / "hybrid.md", hybrid)
    result = run_validate_doc("--contract", "work-log", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert payload["role_variant"] == "reviewer"
    assert "Review Scope" in payload["sections_missing"]
    assert result.returncode == 2


def test_work_log_missing_sections_is_contract_violation(tmp_path: Path) -> None:
    doc = _write(tmp_path / "broken.md", INCOMPLETE_IMPLEMENTER_LOG)
    result = run_validate_doc("--contract", "work-log", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    assert payload["ok"] is False
    assert payload["sections_missing"] == [
        "Tasks Completed",
        "Communication with Teammates",
        "Issues Encountered",
    ]


def test_work_log_reviewer_missing_findings_is_contract_violation(
    tmp_path: Path,
) -> None:
    doc = _write(tmp_path / "broken-reviewer.md", INCOMPLETE_REVIEWER_LOG)
    result = run_validate_doc("--contract", "work-log", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    assert payload["role_variant"] == "reviewer"
    assert "Findings" in payload["sections_missing"]


# --- empty-body warnings ---


def test_empty_body_produces_warning_but_still_ok(tmp_path: Path) -> None:
    content = IMPLEMENTER_LOG.replace("Did the thing.", "")
    doc = _write(tmp_path / "empty-body.md", content)
    result = run_validate_doc("--contract", "work-log", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True
    assert payload["warnings"] == ["section 'Summary' is present but has an empty body"]


# --- heading-less / degenerate input (graceful degradation) ---


def test_file_with_no_headings_reports_all_missing(tmp_path: Path) -> None:
    doc = _write(tmp_path / "plain.md", "just some prose, no headings at all\n")
    result = run_validate_doc("--contract", "lib-doc", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 2, result.stderr
    assert payload["sections_found"] == []
    assert payload["sections_missing"] == [
        "Overview",
        "Core Features",
        "Constraints & Notes",
        "References",
    ]


# --- --dir batch mode ---


def test_dir_mode_all_pass(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "b-implementer.md", IMPLEMENTER_LOG)
    _write(team_dir / "a-reviewer.md", REVIEWER_LOG)

    result = run_validate_doc("--contract", "work-log", "--dir", str(team_dir))
    payload = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True
    assert payload["files_checked"] == 2
    assert payload["files_failed"] == 0
    assert len(payload["results"]) == 2
    # Deterministic, sorted-by-name order.
    assert payload["results"][0]["file"].endswith("a-reviewer.md")
    assert payload["results"][1]["file"].endswith("b-implementer.md")


def test_dir_mode_mixed_pass_fail(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "a.md", IMPLEMENTER_LOG)
    _write(team_dir / "broken.md", INCOMPLETE_IMPLEMENTER_LOG)

    result = run_validate_doc("--contract", "work-log", "--dir", str(team_dir))
    payload = json.loads(result.stdout)

    assert result.returncode == 2, result.stderr
    assert payload["ok"] is False
    assert payload["files_checked"] == 2
    assert payload["files_failed"] == 1


def test_dir_mode_empty_dir(tmp_path: Path) -> None:
    """Without --expect-files an empty directory stays exit 0 — but the state
    is named in `warnings`, never reported as a silent all-clear."""
    team_dir = tmp_path / "team"
    team_dir.mkdir()

    result = run_validate_doc("--contract", "work-log", "--dir", str(team_dir))
    payload = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert payload == {
        "ok": True,
        "contract": "work-log",
        "results": [],
        "files_checked": 0,
        "files_failed": 0,
        "expect_files": None,
        "warnings": [
            "no *.md files found: pass --expect-files N to make this a failure"
        ],
    }


def test_dir_mode_is_non_recursive(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "a.md", IMPLEMENTER_LOG)
    nested = team_dir / "nested"
    nested.mkdir()
    _write(nested / "b.md", INCOMPLETE_IMPLEMENTER_LOG)  # would fail if scanned

    result = run_validate_doc("--contract", "work-log", "--dir", str(team_dir))
    payload = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert payload["files_checked"] == 1


def test_dir_mode_ignores_non_markdown_files(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "a.md", IMPLEMENTER_LOG)
    _write(team_dir / "notes.txt", "not markdown")

    result = run_validate_doc("--contract", "work-log", "--dir", str(team_dir))
    payload = json.loads(result.stdout)

    assert payload["files_checked"] == 1


# --- --expect-files: an empty (or short) directory cannot pass -----------------
#
# The defect this closes: `--contract work-log --dir <fresh team dir>` returned
# `ok: true, files_checked: 0`, exit 0, so "no teammate wrote a log at all" was
# indistinguishable from "every log is valid".


def test_expect_files_satisfied(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "a.md", IMPLEMENTER_LOG)
    _write(team_dir / "b.md", REVIEWER_LOG)

    result = run_validate_doc(
        "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "2"
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True
    assert payload["expect_files"] == 2
    assert payload["warnings"] == []
    assert "error" not in payload


def test_expect_files_on_empty_dir_is_a_contract_violation(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()

    result = run_validate_doc(
        "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "3"
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2, result.stderr
    assert payload["ok"] is False
    assert payload["error"] == "expected 3 files, found 0"
    assert payload["files_checked"] == 0


def test_expect_files_too_few(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "a.md", IMPLEMENTER_LOG)

    result = run_validate_doc(
        "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "2"
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2, result.stderr
    assert payload["error"] == "expected 2 files, found 1"
    # The one file that exists is still validated and reported.
    assert payload["files_checked"] == 1
    assert payload["files_failed"] == 0


def test_expect_files_too_many_also_fails(tmp_path: Path) -> None:
    """An unexpected extra document means the caller's model of the run is
    wrong, which is worth surfacing in both directions."""
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "a.md", IMPLEMENTER_LOG)
    _write(team_dir / "b.md", REVIEWER_LOG)

    result = run_validate_doc(
        "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "1"
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2, result.stderr
    assert payload["error"] == "expected 1 files, found 2"


def test_expect_files_zero_is_a_valid_expectation(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()

    result = run_validate_doc(
        "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "0"
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True
    assert payload["expect_files"] == 0
    # An explicit expectation replaces the "you should have used
    # --expect-files" warning.
    assert payload["warnings"] == []


def test_expect_files_count_mismatch_wins_over_valid_files(tmp_path: Path) -> None:
    """A satisfied per-file contract must not mask a missing document."""
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "a.md", IMPLEMENTER_LOG)

    result = run_validate_doc(
        "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "3"
    )
    payload = json.loads(result.stdout)

    assert payload["files_failed"] == 0
    assert payload["ok"] is False
    assert result.returncode == 2


def test_expect_files_requires_dir(tmp_path: Path) -> None:
    """Silently ignoring the flag would let a caller believe an expectation was
    checked when it was not."""
    doc = _write(tmp_path / "x.md", IMPLEMENTER_LOG)
    result = run_validate_doc(
        "--contract", "work-log", "--file", str(doc), "--expect-files", "1"
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 1, result.stderr
    assert payload["ok"] is False
    assert "--expect-files is only valid with --dir" in payload["error"]


def test_expect_files_rejects_negative(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    result = run_validate_doc(
        "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "-1"
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 1, result.stderr
    assert payload["ok"] is False


def test_expect_files_rejects_non_integer(tmp_path: Path) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    result = run_validate_doc(
        "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "two"
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 1, result.stderr
    assert payload["ok"] is False


def test_dir_payload_shape_is_stable_with_and_without_expect_files(
    tmp_path: Path,
) -> None:
    team_dir = tmp_path / "team"
    team_dir.mkdir()
    _write(team_dir / "a.md", IMPLEMENTER_LOG)

    without = json.loads(
        run_validate_doc("--contract", "work-log", "--dir", str(team_dir)).stdout
    )
    with_expect = json.loads(
        run_validate_doc(
            "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "1"
        ).stdout
    )
    failing = json.loads(
        run_validate_doc(
            "--contract", "work-log", "--dir", str(team_dir), "--expect-files", "2"
        ).stdout
    )

    assert set(without.keys()) == DIR_RESULT_KEYS
    assert set(with_expect.keys()) == DIR_RESULT_KEYS
    assert set(failing.keys()) == DIR_RESULT_KEYS | {"error"}


# --- bad args / not found ---


def test_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"
    result = run_validate_doc("--contract", "work-log", "--file", str(missing))
    payload = json.loads(result.stdout)
    assert result.returncode == 1, result.stderr
    assert payload == {
        "ok": False,
        "file": str(missing),
        "error": "file does not exist",
    }


def test_dir_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    result = run_validate_doc("--contract", "work-log", "--dir", str(missing))
    payload = json.loads(result.stdout)
    assert result.returncode == 1, result.stderr
    assert payload == {
        "ok": False,
        "dir": str(missing),
        "error": "directory does not exist",
    }


def test_dir_path_is_actually_a_file(tmp_path: Path) -> None:
    a_file = _write(tmp_path / "im-a-file.md", LIB_DOC_OK)
    result = run_validate_doc("--contract", "work-log", "--dir", str(a_file))
    payload = json.loads(result.stdout)
    assert result.returncode == 1, result.stderr
    assert payload["error"] == "not a directory"


def test_unknown_contract_name(tmp_path: Path) -> None:
    doc = _write(tmp_path / "x.md", LIB_DOC_OK)
    result = run_validate_doc("--contract", "bogus", "--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 1, result.stderr
    assert payload["ok"] is False
    assert "invalid choice" in payload["error"]


def test_missing_contract_flag_is_bad_args(tmp_path: Path) -> None:
    doc = _write(tmp_path / "x.md", LIB_DOC_OK)
    result = run_validate_doc("--file", str(doc))
    payload = json.loads(result.stdout)
    assert result.returncode == 1, result.stderr
    assert payload["ok"] is False


def test_file_and_dir_are_mutually_exclusive(tmp_path: Path) -> None:
    doc = _write(tmp_path / "x.md", LIB_DOC_OK)
    result = run_validate_doc(
        "--contract", "lib-doc", "--file", str(doc), "--dir", str(tmp_path)
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1, result.stderr
    assert payload["ok"] is False


def test_neither_file_nor_dir_given(tmp_path: Path) -> None:
    result = run_validate_doc("--contract", "lib-doc")
    payload = json.loads(result.stdout)
    assert result.returncode == 1, result.stderr
    assert payload["ok"] is False


# --- stdout contract: exactly one JSON object, always ---


def test_stdout_is_exactly_one_json_object(tmp_path: Path) -> None:
    doc = _write(tmp_path / "x.md", LIB_DOC_OK)
    result = run_validate_doc("--contract", "lib-doc", "--file", str(doc))
    # json.loads succeeding on the *entire* stdout (not a prefix of it) proves
    # nothing else was printed alongside the JSON object.
    json.loads(result.stdout)
    assert result.stdout.strip().startswith("{")


# --- determinism ---


def test_repeated_runs_are_identical(tmp_path: Path) -> None:
    doc = _write(tmp_path / "x.md", REVIEWER_LOG)
    first = run_validate_doc("--contract", "work-log", "--file", str(doc))
    second = run_validate_doc("--contract", "work-log", "--file", str(doc))
    assert first.stdout == second.stdout
    assert first.returncode == second.returncode


# --- --project-root resolves relative --file/--dir paths ---


def test_relative_file_path_resolved_against_project_root(tmp_path: Path) -> None:
    _write(tmp_path / "x.md", REVIEWER_LOG)
    result = run_validate_doc(
        "--contract", "work-log", "--file", "x.md", "--project-root", str(tmp_path)
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["file"] == str(tmp_path / "x.md")


# --- JSON key-shape contract: identical across every contract ---


def test_file_result_keys_are_stable_across_contracts(tmp_path: Path) -> None:
    lib_doc = _write(tmp_path / "lib.md", LIB_DOC_OK)
    work_log = _write(tmp_path / "log.md", IMPLEMENTER_LOG)
    failing = _write(tmp_path / "failing.md", LIB_DOC_MISSING)

    lib_doc_result = json.loads(
        run_validate_doc("--contract", "lib-doc", "--file", str(lib_doc)).stdout
    )
    work_log_result = json.loads(
        run_validate_doc("--contract", "work-log", "--file", str(work_log)).stdout
    )
    failing_result = json.loads(
        run_validate_doc("--contract", "lib-doc", "--file", str(failing)).stdout
    )

    # Same key set whether the file passes (lib_doc, work_log) or fails
    # (failing), and whether the contract has variants (work-log) or not.
    assert set(lib_doc_result.keys()) == FILE_RESULT_KEYS
    assert set(work_log_result.keys()) == FILE_RESULT_KEYS
    assert set(failing_result.keys()) == FILE_RESULT_KEYS


def test_output_is_indent2_json(tmp_path: Path) -> None:
    doc = _write(tmp_path / "good.md", IMPLEMENTER_LOG)
    result = run_validate_doc("--contract", "work-log", "--file", str(doc))
    payload = json.loads(result.stdout)
    # Reproduce the script's own formatting call and assert exact equality,
    # proving indent=2 (not compact json.dumps) formatting is used.
    assert result.stdout == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# --- Contracts must accept the templates they exist to check -----------------
#
# A contract that rejects a document produced by following its own template
# verbatim is worse than no contract: it trains agents to ignore the check.
# These tests pin each contract to the reference template it mirrors, so the
# two cannot drift apart.

# contract -> one or more (rel_path, start_marker, end_marker) template specs.
# A contract with variants (work-log, feature-brief) pins every variant, so no
# mode can drift unnoticed behind a passing sibling.
REFERENCE_TEMPLATES: dict[str, tuple[tuple[str, str | None, str | None], ...]] = {
    "spike-report": (
        (".agents/skills/spike/references/report-template.md", None, None),
    ),
    "bug-report": (
        (
            ".agents/skills/troubleshoot/references/bug-report-template.md",
            None,
            None,
        ),
    ),
    "work-log": ((".agents/skills/_shared/work-log-format.md", None, None),),
    "lib-doc": (
        (
            ".agents/skills/research-lib/SKILL.md",
            "## Documentation Template",
            "## Validate the Document",
        ),
    ),
    "plan-doc": ((".agents/skills/plan/SKILL.md", "### 4. Output Format", "## Notes"),),
    "feature-brief": (
        (
            ".agents/skills/feature/references/brief-templates.md",
            "## Feature Brief (MODE=existing)",
            "## Project Brief (MODE=greenfield)",
        ),
        (
            ".agents/skills/feature/references/brief-templates.md",
            "## Project Brief (MODE=greenfield)",
            None,
        ),
    ),
    "spike-brief": ((".agents/skills/spike/references/brief-template.md", None, None),),
    "diagnosis": (
        (".agents/skills/troubleshoot/references/diagnosis-template.md", None, None),
    ),
    "checkpoint-summary": (
        (
            ".agents/skills/checkpointing/references/formats.md",
            "## Checkpoint File Format",
            "## Rolling PROGRESS.md Format",
        ),
    ),
    "progress": (
        (
            ".agents/skills/checkpointing/references/formats.md",
            "## Rolling PROGRESS.md Format",
            None,
        ),
    ),
    "guide": ((".agents/skills/catchup/references/guide-template.md", None, None),),
}

# `{placeholder}` tokens as the templates write them.
PLACEHOLDER_RE = re.compile(r"\{[^{}\n]*\}")

TEMPLATE_CASES = [
    (contract, index)
    for contract in sorted(REFERENCE_TEMPLATES)
    for index in range(len(REFERENCE_TEMPLATES[contract]))
]


def _extract_template(rel_path: str, start: str | None, end: str | None) -> str:
    """Pull the template body out of a reference document."""
    text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    if start is not None:
        text = text.split(start, 1)[1]
    if end is not None:
        text = text.split(end, 1)[0]
    if "```markdown" in text:
        text = text.split("```markdown", 1)[1]
    return text


def _template_body(contract: str, index: int) -> str:
    return _extract_template(*REFERENCE_TEMPLATES[contract][index])


@pytest.mark.parametrize(("contract", "index"), TEMPLATE_CASES)
def test_contract_accepts_its_own_reference_template(
    tmp_path: Path, contract: str, index: int
) -> None:
    body = _template_body(contract, index)
    doc = _write(tmp_path / f"{contract}-{index}.md", body)

    result = run_validate_doc("--contract", contract, "--file", str(doc))
    payload = json.loads(result.stdout)

    assert payload["sections_missing"] == [], payload


@pytest.mark.parametrize(("contract", "index"), TEMPLATE_CASES)
def test_reference_template_satisfies_the_full_contract(
    tmp_path: Path, contract: str, index: int
) -> None:
    """Sections *and* required metadata: a template that cannot produce a
    passing document is a broken template, not an agent error."""
    body = _template_body(contract, index)
    doc = _write(tmp_path / f"{contract}-{index}.md", body)

    result = run_validate_doc("--contract", contract, "--file", str(doc))
    payload = json.loads(result.stdout)

    assert payload["metadata_missing"] == [], payload
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(("contract", "index"), TEMPLATE_CASES)
def test_contract_accepts_a_document_rendered_from_its_template(
    tmp_path: Path, contract: str, index: int
) -> None:
    """Closes half of the produced-doc gap: the template-pinning tests above
    validate the *skeleton*, which still contains `{placeholder}` tokens. An
    agent submits the rendered result, so a required heading that only matches
    while its placeholder is intact (`## Fix Plan ({N} tasks) -- ...`) would
    pass the skeleton test and fail in production. Full prose adequacy is not
    checkable here — that stays a Codex/user gate."""
    body = PLACEHOLDER_RE.sub("filled", _template_body(contract, index))
    doc = _write(tmp_path / f"{contract}-{index}-rendered.md", body)

    result = run_validate_doc("--contract", contract, "--file", str(doc))
    payload = json.loads(result.stdout)

    assert payload["sections_missing"] == [], payload
    assert payload["metadata_missing"] == [], payload
    assert result.returncode == 0, result.stderr


def test_every_contract_has_a_pinned_reference_template() -> None:
    """A contract with no template behind it is unverifiable configuration."""
    declared = json.loads(
        subprocess.run(
            [
                "python3",
                "-c",
                "import json,sys;"
                f"sys.path.insert(0, {str(VALIDATE_DOC.parent)!r});"
                "import validate_doc;"
                "print(json.dumps(sorted(validate_doc.CONTRACTS)))",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    assert declared == sorted(REFERENCE_TEMPLATES)


def _declared(expression: str) -> object:
    """Evaluate *expression* against a freshly imported validate_doc module."""
    return json.loads(
        subprocess.run(
            [
                "python3",
                "-c",
                "import json,sys;"
                f"sys.path.insert(0, {str(VALIDATE_DOC.parent)!r});"
                "import validate_doc;"
                f"print(json.dumps({expression}))",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )


def test_metadata_requirements_reference_real_contracts() -> None:
    """A REQUIRED_METADATA key that matches no contract is dead configuration
    that would silently never be enforced."""
    metadata_contracts = _declared("sorted(validate_doc.REQUIRED_METADATA)")
    contracts = _declared("sorted(validate_doc.CONTRACTS)")
    assert isinstance(metadata_contracts, list)
    assert isinstance(contracts, list)
    assert set(metadata_contracts) <= set(contracts)


def test_heading_with_inline_value_satisfies_the_contract(tmp_path: Path) -> None:
    """`## Verdict: GO` must satisfy a required `Verdict` section — templates
    routinely carry the value in the heading itself."""
    body = (
        "## Question\nq\n## Verdict: GO\nv\n## Success Criteria Evaluation\ns\n"
        "## Risks\nr\n## Recommendation\nrec\n"
    )
    doc = _write(tmp_path / "spike.md", body)

    result = run_validate_doc("--contract", "spike-report", "--file", str(doc))

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["sections_missing"] == []


def test_deeper_heading_level_still_satisfies_the_contract(tmp_path: Path) -> None:
    """The bug-report template nests its sections at `###` under a `##` title."""
    body = (
        "## Bug Report: x\n### Error\ne\n### Reproduction\nr\n"
        "### Immediate Context\nc\n### Affected Area\na\n"
        "### Initial Hypotheses (informed by Codex analysis)\nh\n"
    )
    doc = _write(tmp_path / "bug.md", body)

    result = run_validate_doc("--contract", "bug-report", "--file", str(doc))

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["sections_missing"] == []
