"""Enforce the Writer Safety Contract for _shared/append_state_block.py.

This script mutates ``.agents/STATE.md`` — the file every session reads first —
and had no test file at all. The tests below pin the four documented guarantees
(dry-run by default, atomic replace, concurrent-modification guard, validation
of the composed result before replacing), the ``## Repository Identity`` writer
that ``init/SKILL.md`` previously performed by hand with raw Edit/Write, and the
``progress_tracker_preserved`` field, which used to be a hard-coded ``True``.

Every test runs against a copy of the repository's own STATE.md under
``--project-root tmp_path``, so the real shared state is never touched.
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
SCRIPT = REPO_ROOT / ".agents" / "skills" / "_shared" / "append_state_block.py"
TEMPLATE_STATE = REPO_ROOT / ".agents" / "STATE.md"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


asb = _load_module(SCRIPT, "append_state_block_writer_under_test")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A fixture repository whose .agents/STATE.md is a copy of the real one."""
    state = tmp_path / ".agents" / "STATE.md"
    state.parent.mkdir(parents=True)
    shutil.copy(TEMPLATE_STATE, state)
    return tmp_path


def state_text(project: Path) -> str:
    return (project / ".agents" / "STATE.md").read_text(encoding="utf-8")


def write_input(project: Path, data: dict, name: str = "input.json") -> Path:
    path = project / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(
    project: Path, block_type: str, data: dict, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--type",
            block_type,
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


BLOCK = {
    "title": "Wave 1 shared writers",
    "sections": [{"heading": "Scope", "content": "- update_design\n- state blocks"}],
}
IDENTITY = {"identity": "A tool-neutral multi-agent orchestration contract repo."}


# --- dry run -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("block_type", "data"),
    [
        ("feature", BLOCK),
        ("bug-fix", BLOCK),
        ("project", BLOCK),
        ("repository-identity", IDENTITY),
    ],
)
def test_dry_run_changes_nothing_on_disk(
    project: Path, block_type: str, data: dict
) -> None:
    before = state_text(project)
    result = run(project, block_type, data)

    assert result.returncode == 0, result.stderr
    payload = parsed(result)
    assert payload["ok"] is True
    assert payload["result"] == "preview"
    assert state_text(project) == before
    preview = Path(payload["preview_file"])
    assert preview.is_file()
    assert payload["artifacts"] == [
        preview.resolve().relative_to(project.resolve()).as_posix()
    ]


def test_apply_reports_the_state_document_as_an_artifact(project: Path) -> None:
    payload = parsed(run(project, "feature", BLOCK, "--apply"))
    assert payload["result"] == "applied"
    assert payload["artifacts"] == [".agents/STATE.md"]


# --- work blocks -------------------------------------------------------------


def test_apply_appends_the_block_and_keeps_the_fixed_sections(project: Path) -> None:
    result = run(project, "feature", BLOCK, "--apply")
    assert result.returncode == 0, result.stderr

    text = state_text(project)
    assert "## Current Feature: Wave 1 shared writers" in text
    assert text.count(asb.STATE_HEADING) == 1
    assert text.count(asb.PROGRESS_TRACKER_HEADING) == 1
    assert "## Main Agent" in text
    assert text.count("## Repository Identity") == 1


def test_reapplying_the_same_block_is_a_no_op(project: Path) -> None:
    run(project, "feature", BLOCK, "--apply")
    after_first = state_text(project)

    second = run(project, "feature", BLOCK, "--apply")
    assert second.returncode == 0, second.stderr
    assert parsed(second)["result"] == "no-op"
    assert state_text(project) == after_first


def test_a_changed_block_with_the_same_id_is_a_conflict(project: Path) -> None:
    run(project, "feature", BLOCK, "--apply")
    before = state_text(project)

    changed = dict(
        BLOCK, sections=[{"heading": "Scope", "content": "- something else"}]
    )
    result = run(project, "feature", changed, "--apply")

    assert result.returncode == 3, result.stderr
    assert parsed(result)["ok"] is False
    assert state_text(project) == before


def test_a_missing_title_is_bad_input(project: Path) -> None:
    result = run(project, "feature", {"sections": []}, "--apply")
    assert result.returncode == 1, result.stderr
    assert "title" in parsed(result)["error"]


# --- Repository Identity writer ----------------------------------------------


def test_identity_writer_replaces_only_the_identity_body(project: Path) -> None:
    before = state_text(project)
    assert "_Not initialized yet." in before

    result = run(project, "repository-identity", IDENTITY, "--apply")
    assert result.returncode == 0, result.stderr

    text = state_text(project)
    assert IDENTITY["identity"] in text
    assert "_Not initialized yet." not in text
    assert asb.IDENTITY_MANAGED_COMMENT in text
    assert asb.IDENTITY_DESIGN_POINTER in text
    # Everything outside the section is untouched.
    assert text.split(asb.IDENTITY_HEADING)[0] == before.split(asb.IDENTITY_HEADING)[0]
    assert (
        text.split(asb.PROGRESS_TRACKER_HEADING)[1]
        == before.split(asb.PROGRESS_TRACKER_HEADING)[1]
    )


def test_identity_writer_is_idempotent(project: Path) -> None:
    run(project, "repository-identity", IDENTITY, "--apply")
    after_first = state_text(project)

    second = run(project, "repository-identity", IDENTITY, "--apply")
    assert parsed(second)["result"] == "no-op"
    assert state_text(project) == after_first


def test_identity_writer_preserves_an_existing_work_block(project: Path) -> None:
    run(project, "feature", BLOCK, "--apply")
    run(project, "repository-identity", IDENTITY, "--apply")

    text = state_text(project)
    assert "## Current Feature: Wave 1 shared writers" in text
    assert "- update_design" in text
    assert IDENTITY["identity"] in text


def test_identity_writer_creates_the_section_when_it_is_missing(project: Path) -> None:
    state = project / ".agents" / "STATE.md"
    lines = state.read_text(encoding="utf-8").splitlines()
    start = lines.index(asb.IDENTITY_HEADING)
    end = lines.index(asb.PROGRESS_TRACKER_HEADING)
    state.write_text("\n".join(lines[:start] + lines[end:]) + "\n", encoding="utf-8")

    result = run(project, "repository-identity", IDENTITY, "--apply")
    assert result.returncode == 0, result.stderr

    text = state_text(project)
    assert text.count(asb.IDENTITY_HEADING) == 1
    assert text.index(asb.IDENTITY_HEADING) < text.index(asb.PROGRESS_TRACKER_HEADING)
    assert IDENTITY["identity"] in text


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"identity": ""},
        {"identity": "   "},
        {"identity": "line\n\nsecond paragraph"},
        {"identity": "## Injected Heading"},
        {"identity": "text\n---\nmore"},
        {"identity": "ok", "extra": "field"},
    ],
)
def test_a_malformed_identity_input_is_rejected(project: Path, bad: dict) -> None:
    before = state_text(project)
    result = run(project, "repository-identity", bad, "--apply")
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False
    assert state_text(project) == before


# --- progress_tracker_preserved ----------------------------------------------


def test_progress_tracker_preserved_is_a_real_check(project: Path) -> None:
    """P3 item 22: the field was a hard-coded True that two skills instruct
    agents to verify. It must now be derived from the composed document."""
    original = state_text(project)
    appended = original + "\n---\n\n## Current Feature: X\n"
    assert asb.progress_tracker_preserved(original, appended) is True

    clobbered = original.replace(
        "Rolling progress summary", "Rolling progress summary REWRITTEN"
    )
    assert asb.progress_tracker_preserved(original, clobbered) is False

    deleted = original.replace(asb.PROGRESS_TRACKER_HEADING, "## Something Else")
    assert asb.progress_tracker_preserved(original, deleted) is False


def test_a_composition_that_clobbers_the_tracker_is_refused(project: Path) -> None:
    original = state_text(project)
    clobbered = original.replace("[PROGRESS.md](../PROGRESS.md)", "(deleted)")
    error = asb.validate_composition(clobbered, original, identity=False)
    assert error is not None
    assert asb.PROGRESS_TRACKER_HEADING in error


@pytest.mark.parametrize("mode", ["preview", "apply"])
def test_progress_tracker_preserved_is_reported_on_every_path(
    project: Path, mode: str
) -> None:
    extra = ["--apply"] if mode == "apply" else []
    payload = parsed(run(project, "feature", BLOCK, *extra))
    assert payload["progress_tracker_preserved"] is True


# --- structure guards --------------------------------------------------------


def test_a_state_document_without_the_tracker_is_exit_2(project: Path) -> None:
    state = project / ".agents" / "STATE.md"
    state.write_text("# Agent State\n\nnothing else\n", encoding="utf-8")

    result = run(project, "feature", BLOCK, "--apply")
    assert result.returncode == 2, result.stderr
    assert asb.PROGRESS_TRACKER_HEADING in parsed(result)["error"]


def test_a_missing_state_document_is_exit_2(tmp_path: Path) -> None:
    result = run(tmp_path, "feature", BLOCK, "--apply")
    assert result.returncode == 2, result.stderr
    assert parsed(result)["ok"] is False


def test_a_duplicated_identity_heading_is_refused(project: Path) -> None:
    state = project / ".agents" / "STATE.md"
    before = state.read_text(encoding="utf-8")
    state.write_text(before + f"\n{asb.IDENTITY_HEADING}\n\nsecond\n", encoding="utf-8")

    result = run(project, "repository-identity", IDENTITY, "--apply")
    assert result.returncode == 2, result.stderr
    assert asb.IDENTITY_HEADING in parsed(result)["error"]


# --- injectable clock --------------------------------------------------------


def test_now_names_the_preview_file_deterministically(project: Path) -> None:
    payload = parsed(run(project, "feature", BLOCK, "--now", "2020-02-29T23:59:59"))
    assert Path(payload["preview_file"]).name == "state-preview-20200229-235959.md"


def test_an_unparseable_now_is_bad_args(project: Path) -> None:
    result = run(project, "feature", BLOCK, "--now", "yesterday")
    assert result.returncode == 1, result.stderr
    assert parsed(result)["ok"] is False


# --- atomic apply: hash guard and pre-replace validation ---------------------


def _argv(project: Path, block_type: str, data: dict) -> list[str]:
    return [
        "append_state_block.py",
        "--project-root",
        str(project),
        "--type",
        block_type,
        "--input",
        str(write_input(project, data)),
        "--apply",
    ]


def test_the_hash_guard_refuses_a_document_changed_since_load(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = project / ".agents" / "STATE.md"
    real_read_text = Path.read_text
    real_write_text = Path.write_text
    reads = {"state": 0}

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "STATE.md":
            reads["state"] += 1
            if reads["state"] == 1:
                text = real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]
                # Simulate another writer landing between load and replace.
                real_write_text(self, text + "\n<!-- concurrent note -->\n")  # type: ignore[arg-type]
                return text
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type,return-value]

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    monkeypatch.setattr(sys, "argv", _argv(project, "feature", BLOCK))

    assert asb.main() == 3
    text = real_read_text(state)  # type: ignore[arg-type]
    assert "concurrent note" in text, "the concurrent write must survive"
    assert "Wave 1 shared writers" not in text, "our write must not have landed"


def test_validation_runs_before_the_replace_and_leaves_no_temp_file(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = project / ".agents" / "STATE.md"
    before = state.read_text(encoding="utf-8")
    calls = {"n": 0}

    def failing_second_validation(
        new_text: str, original_text: str, identity: bool
    ) -> str | None:
        calls["n"] += 1
        # First call is the pre-write check; the second validates the bytes
        # actually written to the temp file, immediately before os.replace.
        return "injected structural damage" if calls["n"] == 2 else None

    monkeypatch.setattr(asb, "validate_composition", failing_second_validation)
    monkeypatch.setattr(sys, "argv", _argv(project, "feature", BLOCK))

    assert asb.main() == 2
    assert state.read_text(encoding="utf-8") == before
    leftovers = list(state.parent.glob(".state-md-*"))
    assert leftovers == [], f"temp file left behind: {leftovers}"


def test_help_exits_zero_and_lists_the_identity_type(project: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert asb.IDENTITY_TYPE in result.stdout
