"""Behavioural tests for checkpointing/refresh_guard.py.

Three reproduced data-loss defects are pinned here as regressions:

1. a ``## Progress Tracker`` sitting after a working block was silently dropped
   by ``compose``, so ``verify`` failed and the next checkpoint re-appended it —
   an every-session loop;
2. a user's ``## My Manual Notes`` block was deleted and reported as
   ``blocks_pruned: []``, while ``.agents/rules/agent-state.md`` explicitly
   sanctions manual notes;
3. ``--project-root`` was ignored for research notes because the directories were
   module-level constants, so a fixture run proposed moving real repository files.

Plus the Writer Safety Contract for ``--mode apply`` and the fact that ``check``,
``plan`` and ``verify`` are now genuinely different operations rather than
byte-identical code paths.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents" / "skills" / "checkpointing" / "refresh_guard.py"

CANONICAL_STATE = (
    "# Agent State\n\n"
    "## Main Agent\n\nClaude Code\n\n"
    "## Repository Identity\n\nSome identity.\n\n"
    "## Progress Tracker\n\n"
    "Rolling progress summary (latest 5 checkpoints): [PROGRESS.md](../PROGRESS.md)\n\n"
    "## Current Feature: alpha\n\n- 2026-07-01 started\n\n"
    "## My Manual Notes\n\n- The deploy key rotates on the 1st.\n\n"
    "## Current Feature: beta\n\n- 2026-07-20 started\n"
)

# The shape checkpoint.py used to produce: tracker appended after the blocks.
STATE_WITH_TRAILING_TRACKER = (
    "# Agent State\n\n"
    "## Main Agent\n\nClaude Code\n\n"
    "## Current Feature: alpha\n\n- 2026-07-01 started\n\n"
    "## Progress Tracker\n\n"
    "Rolling progress summary (latest 5 checkpoints): [PROGRESS.md](../PROGRESS.md)\n"
)


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rg = _load_module(SCRIPT, "refresh_guard_under_test")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "STATE.md").write_text(CANONICAL_STATE, encoding="utf-8")
    return tmp_path


def run(project: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def parsed(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


# --- data loss regressions ---------------------------------------------------


def test_manual_notes_survive_compaction(project: Path) -> None:
    result = run(project, "--mode", "compose")

    assert result.returncode == 0, result.stdout
    payload = parsed(result)
    assert payload["blocks_pruned"] == ["## Current Feature: alpha"]
    assert "## My Manual Notes" in payload["sections_preserved"]
    assert payload["sections_dropped"] == []
    composed = (project / ".agents" / "logs" / "composed-state.md").read_text(
        encoding="utf-8"
    )
    assert "The deploy key rotates on the 1st." in composed
    assert "2026-07-01 started" not in composed
    assert "2026-07-20 started" in composed


def test_a_trailing_progress_tracker_is_not_dropped(project: Path) -> None:
    """The every-session loop: compose used to keep only the prefix before the
    first working block, so a tracker appended after one vanished, verify exited
    2, and the next checkpoint re-appended it."""
    (project / ".agents" / "STATE.md").write_text(
        STATE_WITH_TRAILING_TRACKER, encoding="utf-8"
    )

    composed_result = run(project, "--mode", "compose")

    assert composed_result.returncode == 0, composed_result.stdout
    composed_path = project / ".agents" / "logs" / "composed-state.md"
    composed = composed_path.read_text(encoding="utf-8")
    assert composed.count("## Progress Tracker") == 1

    # Applying the candidate and verifying is the step that used to exit 2.
    (project / ".agents" / "STATE.md").write_text(composed, encoding="utf-8")
    assert run(project, "--mode", "verify").returncode == 0


def test_section_order_is_preserved_exactly(project: Path) -> None:
    composed = rg.compose_state(CANONICAL_STATE.splitlines()).text
    assert rg.top_headings(composed.splitlines()) == [
        "## Main Agent",
        "## Repository Identity",
        "## Progress Tracker",
        "## My Manual Notes",
        "## Current Feature: beta",
    ]


def test_a_composition_that_would_drop_a_section_aborts(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sections_dropped is recomputed from the composed text, so a regression in
    the pruning loop is a failure rather than a silent deletion."""

    def lossy_compose(lines: list[str]) -> rg.Compaction:
        kept = [line for line in lines if "Manual Notes" not in line]
        return rg.Compaction("\n".join(kept) + "\n", [], [], ["## My Manual Notes"])

    monkeypatch.setattr(rg, "compose_state", lossy_compose)
    monkeypatch.setattr(
        sys,
        "argv",
        ["refresh_guard.py", "--project-root", str(project), "--mode", "plan"],
    )

    assert rg.main() == 2


# --- --project-root is honoured by every path -------------------------------


def test_research_notes_come_from_the_given_root(project: Path) -> None:
    research = project / ".agents" / "docs" / "research"
    research.mkdir(parents=True)
    (research / "fixture-only-note.md").write_text("# note\n", encoding="utf-8")

    payload = parsed(run(project, "--mode", "plan"))

    assert [note["file"] for note in payload["research_notes"]] == [
        "fixture-only-note.md"
    ]
    assert payload["move_plan"] == [
        {
            "src": ".agents/docs/research/fixture-only-note.md",
            "dst": ".agents/docs/research/archive/fixture-only-note.md",
            "mode": "create",
            "suggested": True,
        }
    ]
    assert any("suggestion" in w for w in payload["warnings"])


def test_no_module_level_path_constant_bakes_in_a_directory() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for name in ("STATE_MD =", "RESEARCH_DIR =", "ARCHIVE_DIR ="):
        assert name not in source, f"{name} reintroduces a baked-in directory"


def test_an_active_note_is_not_proposed_for_archiving(project: Path) -> None:
    research = project / ".agents" / "docs" / "research"
    research.mkdir(parents=True)
    (research / "beta.md").write_text("# beta\n", encoding="utf-8")

    payload = parsed(run(project, "--mode", "plan"))

    assert payload["research_notes"][0]["active"] is True
    assert payload["move_plan"] == []


# --- the modes are different operations -------------------------------------


def test_check_is_structure_only(project: Path) -> None:
    payload = parsed(run(project, "--mode", "check"))

    assert payload["structure"] == {
        "state_heading": 1,
        "progress_tracker": 1,
        "ok": True,
    }
    assert [b["heading"] for b in payload["work_blocks"]] == [
        "## Current Feature: alpha",
        "## Current Feature: beta",
    ]
    for absent in ("research_notes", "move_plan", "blocks_pruned", "composed_state"):
        assert absent not in payload, f"check must not collect {absent}"


def test_plan_adds_the_preview_without_writing(project: Path) -> None:
    payload = parsed(run(project, "--mode", "plan"))

    assert payload["blocks_pruned"] == ["## Current Feature: alpha"]
    assert "research_notes" in payload
    assert "composed_state" not in payload
    assert not (project / ".agents" / "logs").exists()


def test_compose_writes_only_the_draft(project: Path) -> None:
    payload = parsed(run(project, "--mode", "compose"))

    assert payload["composed_state"] == ".agents/logs/composed-state.md"
    assert payload["artifacts"] == [".agents/logs/composed-state.md"]
    assert (project / ".agents" / "STATE.md").read_text(
        encoding="utf-8"
    ) == CANONICAL_STATE


def test_verify_reports_whether_compaction_landed(project: Path) -> None:
    pending = run(project, "--mode", "verify")
    assert pending.returncode == 2
    assert parsed(pending)["compaction_applied"] is False

    run(project, "--mode", "apply", "--apply")

    applied = run(project, "--mode", "verify")
    assert applied.returncode == 0, applied.stdout
    assert parsed(applied)["compaction_applied"] is True


def test_an_invalid_structure_is_exit_2(project: Path) -> None:
    (project / ".agents" / "STATE.md").write_text("# Agent State\n", encoding="utf-8")

    result = run(project, "--mode", "check")

    assert result.returncode == 2
    assert parsed(result)["structure"]["progress_tracker"] == 0


def test_an_absent_state_md_is_exit_3(tmp_path: Path) -> None:
    result = run(tmp_path, "--mode", "check")

    assert result.returncode == 3
    assert parsed(result)["ok"] is False


# --- Writer Safety for --mode apply -----------------------------------------


def test_apply_previews_by_default(project: Path) -> None:
    payload = parsed(
        run(project, "--mode", "apply", "--now", "2026-07-25T10:00:00+00:00")
    )

    assert payload["applied"] is False
    assert payload["preview_file"] == (
        ".agents/logs/state-compaction-preview-20260725-100000.md"
    )
    assert (project / ".agents" / "STATE.md").read_text(
        encoding="utf-8"
    ) == CANONICAL_STATE


def test_apply_writes_atomically_and_reports_both_hashes(project: Path) -> None:
    before = hashlib.sha256(CANONICAL_STATE.encode("utf-8")).hexdigest()

    payload = parsed(run(project, "--mode", "apply", "--apply"))

    assert payload["applied"] is True
    assert payload["state_hash_before"] == before
    after = (project / ".agents" / "STATE.md").read_text(encoding="utf-8")
    assert (
        payload["state_hash_after"] == hashlib.sha256(after.encode("utf-8")).hexdigest()
    )
    assert "2026-07-01 started" not in after
    assert "The deploy key rotates on the 1st." in after


def test_expect_hash_mismatch_refuses_to_write(project: Path) -> None:
    result = run(project, "--mode", "apply", "--apply", "--expect-hash", "deadbeef")

    assert result.returncode == 3
    assert "does not match on-disk" in parsed(result)["error"]
    assert (project / ".agents" / "STATE.md").read_text(
        encoding="utf-8"
    ) == CANONICAL_STATE


def test_the_hash_guard_refuses_a_state_changed_since_load(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = project / ".agents" / "STATE.md"
    real_read_text = Path.read_text
    real_write_text = Path.write_text
    reads = {"n": 0}

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "STATE.md":
            reads["n"] += 1
            if reads["n"] == 1:
                text = real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]
                real_write_text(self, text + "\n<!-- concurrent note -->\n")  # type: ignore[arg-type]
                return text
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type,return-value]

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "refresh_guard.py",
            "--project-root",
            str(project),
            "--mode",
            "apply",
            "--apply",
        ],
    )

    assert rg.main() == 3
    text = real_read_text(state)  # type: ignore[arg-type]
    assert "concurrent note" in text, "the concurrent write must survive"
    assert "2026-07-01 started" in text, "our compaction must not have landed"


def test_validation_runs_before_the_replace_and_leaves_no_temp_file(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = project / ".agents" / "STATE.md"
    calls = {"n": 0}

    def failing_second_validation(
        new_text: str, original_lines: list[str]
    ) -> str | None:
        calls["n"] += 1
        return "injected structural damage" if calls["n"] == 2 else None

    monkeypatch.setattr(rg, "validate_composition", failing_second_validation)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "refresh_guard.py",
            "--project-root",
            str(project),
            "--mode",
            "apply",
            "--apply",
        ],
    )

    assert rg.main() == 2
    assert state.read_text(encoding="utf-8") == CANONICAL_STATE
    assert list(state.parent.glob(".state-md-*")) == []


# --- CLI contract ------------------------------------------------------------


def test_help_lists_every_mode() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    for mode in ("check", "plan", "compose", "apply", "verify"):
        assert mode in result.stdout
