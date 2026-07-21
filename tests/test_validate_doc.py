from __future__ import annotations

import json
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
## Overview
It's a library.
"""

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

REFERENCE_TEMPLATES = {
    "spike-report": (".agents/skills/spike/references/report-template.md", None, None),
    "bug-report": (
        ".agents/skills/troubleshoot/references/bug-report-template.md",
        None,
        None,
    ),
    "work-log": (".agents/skills/_shared/work-log-format.md", None, None),
    "lib-doc": (
        ".agents/skills/research-lib/SKILL.md",
        "## Documentation Template",
        "## Validate the Document",
    ),
}


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


@pytest.mark.parametrize("contract", sorted(REFERENCE_TEMPLATES))
def test_contract_accepts_its_own_reference_template(
    tmp_path: Path, contract: str
) -> None:
    body = _extract_template(*REFERENCE_TEMPLATES[contract])
    doc = _write(tmp_path / f"{contract}.md", body)

    result = run_validate_doc("--contract", contract, "--file", str(doc))
    payload = json.loads(result.stdout)

    assert payload["sections_missing"] == [], payload
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
