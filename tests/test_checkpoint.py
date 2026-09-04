"""Behavioural tests for checkpointing/checkpoint.py.

The script writes two user-owned, git-tracked documents (root ``PROGRESS.md``
and ``.claude/STATE.md``) and had no dedicated tests at all. These pin the
Writer Safety Contract for both writes, the single injected clock, and the
central contract change: a missing or incomplete five-part summary is a failure,
never a generated substitute.

Every test runs under ``--project-root tmp_path`` with ``--claude-home`` pinned
to an empty directory, so neither the real repository nor the invoking user's
Agent Teams data is ever touched.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "skills" / "checkpointing" / "checkpoint.py"
VALIDATE_DOC = REPO_ROOT / ".claude" / "skills" / "_shared" / "validate_doc.py"

NOW = "2026-07-25T10:00:00+00:00"
STAMP = "2026-07-25-100000"

VALID_SUMMARY = "\n".join(
    [
        "## サマリ",
        "",
        "### 何をしたのか",
        "- Broke the every-session loop.",
        "",
        "### どういうやり取りをユーザーと行ったのか",
        "- The user approved the fix plan.",
        "",
        "### どうやったのか",
        "- Rewrote compose_state to walk sections.",
        "",
        "### 途中でどういう課題が起こったのか",
        "- compose dropped every trailing section.",
        "",
        "### 将来のアクション",
        "- Land Wave 2.",
        "",
    ]
)

STATE_WITH_WORK_BLOCK = (
    "# Agent State\n\n"
    "## Main Agent\n\nClaude Code\n\n"
    "## Repository Identity\n\nSome identity.\n\n"
    "## Current Feature: alpha\n\n- 2026-07-01 started\n"
)


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cp = _load_module(SCRIPT, "checkpoint_under_test")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A git repository with shared state and a fresh pending summary."""
    (tmp_path / ".claude" / "logs").mkdir(parents=True)
    (tmp_path / ".claude" / "STATE.md").write_text(
        STATE_WITH_WORK_BLOCK, encoding="utf-8"
    )
    (tmp_path / ".claude" / "logs" / "pending-summary.md").write_text(
        VALID_SUMMARY, encoding="utf-8"
    )
    (tmp_path / "claude-home").mkdir()
    for args in (
        ["init", "-q", "."],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "T"],
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: initial"], cwd=tmp_path, check=True)
    return tmp_path


def run(project: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--claude-home",
            str(project / "claude-home"),
            "--now",
            NOW,
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def summary_flag(project: Path) -> list[str]:
    return ["--summary-file", ".claude/logs/pending-summary.md"]


# --- the summary is judgment, never generated --------------------------------


def test_the_five_subsections_match_the_shared_contract() -> None:
    """The writer's heading list and validate_doc.py's registry are one contract."""
    validate_doc = _load_module(VALIDATE_DOC, "validate_doc_for_checkpoint")
    required, _ = validate_doc.CONTRACTS["checkpoint-summary"](set())
    assert cp.SUMMARY_SUBSECTIONS == [f"### {name}" for name in required]


def test_a_missing_summary_flag_is_a_contract_violation(project: Path) -> None:
    result = run(project)

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "--summary-file is required" in payload["error"]
    assert not (project / "PROGRESS.md").exists()
    assert not (project / ".claude" / "checkpoints").exists()


def test_an_unreadable_summary_file_writes_nothing(project: Path) -> None:
    result = run(project, "--summary-file", "does-not-exist.md", "--apply")

    assert result.returncode == 2, result.stdout
    assert not (project / "PROGRESS.md").exists()
    assert (project / ".claude" / "STATE.md").read_text(
        encoding="utf-8"
    ) == STATE_WITH_WORK_BLOCK


def test_an_incomplete_summary_names_the_missing_sections(project: Path) -> None:
    (project / "partial.md").write_text(
        "## サマリ\n\n### 何をしたのか\n- only one\n", encoding="utf-8"
    )

    result = run(project, "--summary-file", "partial.md", "--apply")

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert "将来のアクション" in payload["error"]
    assert not (project / "PROGRESS.md").exists()


def test_an_empty_summary_file_is_rejected(project: Path) -> None:
    (project / "empty.md").write_text("   \n", encoding="utf-8")

    result = run(project, "--summary-file", "empty.md")

    assert result.returncode == 2, result.stdout
    assert "is empty" in json.loads(result.stdout)["error"]


def test_no_generated_summary_fallback_remains() -> None:
    """The commit-count substitute is deleted, not merely unreachable."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "auto_generate_summary_body" not in source
    assert "(no summary file provided)" not in source


def test_a_summary_older_than_the_newest_checkpoint_is_stale(project: Path) -> None:
    checkpoints = project / ".claude" / "checkpoints"
    checkpoints.mkdir(parents=True)
    old = checkpoints / "2026-07-24-090000.md"
    old.write_text("# Checkpoint\n", encoding="utf-8")
    summary = project / ".claude" / "logs" / "pending-summary.md"
    import os

    os.utime(summary, (0, 0))

    result = run(project, *summary_flag(project), "--apply")

    assert result.returncode == 2, result.stdout
    assert "older than the newest checkpoint" in json.loads(result.stdout)["error"]


# --- dry-run by default ------------------------------------------------------


def test_dry_run_writes_only_previews(project: Path) -> None:
    result = run(project, *summary_flag(project))

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["result"] == "preview"
    assert not (project / "PROGRESS.md").exists()
    assert (project / ".claude" / "STATE.md").read_text(
        encoding="utf-8"
    ) == STATE_WITH_WORK_BLOCK
    assert not (project / ".claude" / "checkpoints" / f"{STAMP}.md").exists()
    previews = sorted(p.name for p in (project / ".claude" / "logs").glob("*preview*"))
    assert previews == [
        "checkpoint-preview-20260725-100000.md",
        "index-preview-20260725-100000.md",
        "progress-preview-20260725-100000.md",
        "state-preview-20260725-100000.md",
    ]
    assert payload["artifacts"] == payload["preview_files"]
    assert not (project / ".claude" / "checkpoints" / "INDEX.md").exists()


def test_the_progress_preview_matches_what_apply_writes(project: Path) -> None:
    run(project, *summary_flag(project))
    preview = (
        project / ".claude" / "logs" / "progress-preview-20260725-100000.md"
    ).read_text(encoding="utf-8")

    run(project, *summary_flag(project), "--apply")

    assert (project / "PROGRESS.md").read_text(encoding="utf-8") == preview


# --- apply -------------------------------------------------------------------


def test_apply_writes_checkpoint_progress_and_the_tracker(project: Path) -> None:
    result = run(project, *summary_flag(project), "--apply")

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["result"] == "applied"
    assert payload["progress_entries"] == 1
    assert payload["state_updated"] is True
    assert payload["summary_validated"] is True

    checkpoint = project / ".claude" / "checkpoints" / f"{STAMP}.md"
    assert checkpoint.is_file()
    assert checkpoint.with_suffix(".analyze-prompt.md").is_file()

    progress = (project / "PROGRESS.md").read_text(encoding="utf-8")
    assert f"## [{STAMP}](.claude/checkpoints/{STAMP}.md)" in progress
    assert "Broke the every-session loop." in progress
    assert "## サマリ" not in progress


def test_the_tracker_lands_before_the_first_work_block(project: Path) -> None:
    """A stable home the compaction pass preserves.

    Appending the tracker at the end of the file put it after the working
    blocks, where compaction deleted it, so every session re-appended it.
    """
    run(project, *summary_flag(project), "--apply")

    lines = (project / ".claude" / "STATE.md").read_text(encoding="utf-8").splitlines()
    assert lines.count("## Progress Tracker") == 1
    assert lines.index("## Progress Tracker") < lines.index("## Current Feature: alpha")
    assert lines.index("## Repository Identity") < lines.index("## Progress Tracker")


def test_the_tracker_write_is_idempotent(project: Path) -> None:
    run(project, *summary_flag(project), "--apply")
    before = (project / ".claude" / "STATE.md").read_text(encoding="utf-8")

    (project / "second.md").write_text(VALID_SUMMARY, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--claude-home",
            str(project / "claude-home"),
            "--now",
            "2026-07-25T11:00:00+00:00",
            "--json",
            "--summary-file",
            "second.md",
            "--apply",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["state_updated"] is False
    assert payload["progress_entries"] == 2
    assert (project / ".claude" / "STATE.md").read_text(encoding="utf-8") == before


def test_consume_summary_deletes_the_draft(project: Path) -> None:
    summary = project / ".claude" / "logs" / "pending-summary.md"

    result = run(project, *summary_flag(project), "--apply", "--consume-summary")

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["summary_consumed"] is True
    assert not summary.exists()


def test_an_existing_checkpoint_timestamp_is_never_overwritten(project: Path) -> None:
    run(project, *summary_flag(project), "--apply")
    checkpoint = project / ".claude" / "checkpoints" / f"{STAMP}.md"
    before = checkpoint.read_text(encoding="utf-8")
    (project / "again.md").write_text(VALID_SUMMARY, encoding="utf-8")

    result = run(project, "--summary-file", "again.md", "--apply")

    assert result.returncode == 3, result.stdout
    assert "already exists" in json.loads(result.stdout)["error"]
    assert checkpoint.read_text(encoding="utf-8") == before


# --- the single injected clock ----------------------------------------------


def test_one_clock_makes_filename_header_and_footer_agree(project: Path) -> None:
    run(project, *summary_flag(project), "--apply")

    text = (project / ".claude" / "checkpoints" / f"{STAMP}.md").read_text(
        encoding="utf-8"
    )
    assert text.startswith("---\n")
    assert f"\ntimestamp: {STAMP}\n" in text
    assert f"\n# Checkpoint {STAMP}\n" in text
    assert text.rstrip().endswith(f"*Generated by checkpointing skill at {STAMP}*")


def test_an_unparseable_now_is_bad_args(project: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--now",
            "yesterday",
            "--summary-file",
            ".claude/logs/pending-summary.md",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout
    assert json.loads(result.stdout)["ok"] is False


def test_an_unparseable_since_emits_json_instead_of_a_traceback(project: Path) -> None:
    result = run(project, *summary_flag(project), "--since", "30 days ago")

    assert result.returncode == 1, result.stdout
    assert json.loads(result.stdout)["ok"] is False
    assert result.stderr == ""


# --- shared state preconditions ---------------------------------------------


def test_an_absent_state_md_is_a_hard_stop(project: Path) -> None:
    (project / ".claude" / "STATE.md").unlink()

    result = run(project, *summary_flag(project), "--apply")

    assert result.returncode == 2, result.stdout
    assert "shared state must exist" in json.loads(result.stdout)["error"]


def test_two_tracker_headings_are_rejected_not_tolerated(project: Path) -> None:
    """The substring presence test used to accept a state refresh_guard calls
    invalid, so the two scripts disagreed on the same invariant."""
    state = project / ".claude" / "STATE.md"
    state.write_text(
        state.read_text(encoding="utf-8")
        + "\n## Progress Tracker\n\none\n\n## Progress Tracker\n\ntwo\n",
        encoding="utf-8",
    )

    result = run(project, *summary_flag(project), "--apply")

    assert result.returncode == 2, result.stdout
    assert "expected 0 or 1" in json.loads(result.stdout)["error"]


# --- honest collectors -------------------------------------------------------


def test_a_failed_collector_is_reported_not_rendered_as_no_activity(
    tmp_path: Path,
) -> None:
    (tmp_path / ".claude" / "logs").mkdir(parents=True)
    (tmp_path / ".claude" / "STATE.md").write_text(
        STATE_WITH_WORK_BLOCK, encoding="utf-8"
    )
    (tmp_path / ".claude" / "logs" / "pending-summary.md").write_text(
        VALID_SUMMARY, encoding="utf-8"
    )
    (tmp_path / "claude-home").mkdir()

    result = run(tmp_path, *summary_flag(tmp_path), "--apply")

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["collector_errors"], "a non-git directory must not read as clean"
    checkpoint = (tmp_path / ".claude" / "checkpoints" / f"{STAMP}.md").read_text(
        encoding="utf-8"
    )
    assert "## Collector Status" in checkpoint
    assert "FAILED" in checkpoint


def test_a_malformed_cli_log_line_is_counted(project: Path) -> None:
    (project / ".claude" / "logs" / "cli-tools.jsonl").write_text(
        '{"tool": "codex", "prompt": "ok", "timestamp": "2026-07-25T09:00:00Z"}\n'
        "not json at all\n",
        encoding="utf-8",
    )

    result = run(project, *summary_flag(project), "--apply")

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["skipped_records"]["cli_log_lines"] == 1


# --- checkpoint discovery ----------------------------------------------------


def test_only_timestamp_named_files_count_as_checkpoints(tmp_path: Path) -> None:
    """Path.glob("*.md") matches dotfiles, so a pending draft used to occupy a
    PROGRESS.md slot and silently push a real entry out."""
    checkpoints = tmp_path / ".claude" / "checkpoints"
    checkpoints.mkdir(parents=True)
    for name in (
        "2026-07-25-100000.md",
        ".pending-summary.md",
        "notes.md",
        "2026-07-25-100000.analyze-prompt.md",
    ):
        (checkpoints / name).write_text("# x\n", encoding="utf-8")

    found = [path.name for path in cp.get_checkpoint_files(tmp_path)]

    assert found == ["2026-07-25-100000.md"]


def test_progress_md_keeps_at_most_five_entries(project: Path) -> None:
    checkpoints = project / ".claude" / "checkpoints"
    checkpoints.mkdir(parents=True)
    for day in range(1, 8):
        (checkpoints / f"2026-07-0{day}-120000.md").write_text(
            f"# Checkpoint\n{cp.PROGRESS_SUMMARY_START}\n## サマリ\n\n"
            f"### 何をしたのか\n- day {day}\n\n### 将来のアクション\n- next\n"
            f"{cp.PROGRESS_SUMMARY_END}\n",
            encoding="utf-8",
        )

    composition = cp.compose_progress_md(project)

    assert composition.entries == cp.MAX_PROGRESS_ENTRIES
    assert "2026-07-07-120000" in composition.text
    assert "2026-07-02-120000" not in composition.text


def test_a_checkpoint_without_markers_is_counted_not_silently_skipped(
    project: Path,
) -> None:
    checkpoints = project / ".claude" / "checkpoints"
    checkpoints.mkdir(parents=True)
    (checkpoints / "2026-07-01-120000.md").write_text(
        "# Checkpoint\n", encoding="utf-8"
    )

    composition = cp.compose_progress_md(project)

    assert composition.entries == 0
    assert composition.skipped_no_marker == 1


# --- Writer Safety: hash guard and pre-replace validation --------------------


def _argv(project: Path, *extra: str) -> list[str]:
    return [
        "checkpoint.py",
        "--project-root",
        str(project),
        "--claude-home",
        str(project / "claude-home"),
        "--now",
        NOW,
        "--json",
        "--summary-file",
        ".claude/logs/pending-summary.md",
        "--apply",
        *extra,
    ]


def test_the_hash_guard_refuses_a_progress_md_changed_since_load(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    progress = project / "PROGRESS.md"
    progress.write_text(
        "# PROGRESS\n\n## [old](x.md)\n\n### 何をしたのか\n- a\n\n### 将来のアクション\n- b\n",
        encoding="utf-8",
    )
    real_read_text = Path.read_text
    real_write_text = Path.write_text
    reads = {"n": 0}

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "PROGRESS.md":
            reads["n"] += 1
            if reads["n"] == 1:
                text = real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]
                real_write_text(self, text + "\n<!-- concurrent note -->\n")  # type: ignore[arg-type]
                return text
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type,return-value]

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    monkeypatch.setattr(sys, "argv", _argv(project))

    assert cp.main() == 3
    text = real_read_text(progress)  # type: ignore[arg-type]
    assert "concurrent note" in text, "the concurrent write must survive"
    assert STAMP not in text, "our write must not have landed"


def test_validation_runs_before_the_replace_and_leaves_no_temp_file(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    progress = project / "PROGRESS.md"
    progress.write_text(
        "# PROGRESS\n\n## [old](x.md)\n\n### 何をしたのか\n- a\n\n### 将来のアクション\n- b\n",
        encoding="utf-8",
    )
    before = progress.read_text(encoding="utf-8")
    calls = {"n": 0}

    def failing_second_validation(text: str, project_root: Path) -> str | None:
        calls["n"] += 1
        # Call 1 is the pre-write check; call 2 validates the bytes actually
        # written to the temp file, immediately before os.replace.
        return "injected structural damage" if calls["n"] == 2 else None

    monkeypatch.setattr(cp, "validate_progress_document", failing_second_validation)
    monkeypatch.setattr(sys, "argv", _argv(project))

    assert cp.main() == 2
    assert progress.read_text(encoding="utf-8") == before
    leftovers = list(project.glob(".PROGRESS.md-*"))
    assert leftovers == [], f"temp file left behind: {leftovers}"


def test_a_state_write_that_would_lose_a_heading_is_refused(project: Path) -> None:
    state_before = (project / ".claude" / "STATE.md").read_text(encoding="utf-8")
    damaged = "# Agent State\n\n## Progress Tracker\n\nlink\n"

    error = cp.validate_state_composition(damaged, state_before)

    assert error is not None
    assert "## Main Agent" in error


# --- fast retrieval: frontmatter, slug, tags, INDEX.md -----------------------


def test_frontmatter_carries_the_slug_tags_and_counts(project: Path) -> None:
    run(project, *summary_flag(project), "--apply")

    text = (project / ".claude" / "checkpoints" / f"{STAMP}.md").read_text(
        encoding="utf-8"
    )
    fields = cp.parse_frontmatter(text)

    assert fields["timestamp"] == STAMP
    assert fields["id"] == f"{fields['slug']}-{STAMP}"
    # The fixture's only commit is "feat: initial", so the slug must say so
    # rather than falling back to the generic session name.
    assert fields["slug"].startswith("feature")
    assert "feature" in fields["tags"]
    assert fields["summary"] == "initial"
    assert fields["commits"] == "1"


def test_a_label_overrides_the_derived_slug(project: Path) -> None:
    result = run(
        project, *summary_flag(project), "--apply", "--label", "Auth Redesign!"
    )

    assert json.loads(result.stdout)["slug"] == "auth-redesign"
    fields = cp.parse_frontmatter(
        (project / ".claude" / "checkpoints" / f"{STAMP}.md").read_text(
            encoding="utf-8"
        )
    )
    assert fields["slug"] == "auth-redesign"


def test_a_non_ascii_label_falls_back_instead_of_emitting_an_empty_slug() -> None:
    assert cp.derive_slug(cp.Collected(), label="認証の再設計") == cp.DEFAULT_SLUG


def test_frontmatter_survives_a_quote_in_the_headline(project: Path) -> None:
    collected = cp.Collected(commits=[{"message": 'fix: quote "x" and \\ backslash'}])

    text = cp.build_frontmatter(collected, STAMP, "bugfix", ["bugfix"], None)

    assert cp.parse_frontmatter(text + "\n")["summary"] == 'quote "x" and \\ backslash'


def test_the_index_catalogs_every_checkpoint_newest_first(project: Path) -> None:
    run(project, *summary_flag(project), "--apply")
    (project / ".claude" / "logs" / "pending-summary.md").write_text(
        VALID_SUMMARY, encoding="utf-8"
    )
    later = "2026-07-26T10:00:00+00:00"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--claude-home",
            str(project / "claude-home"),
            "--now",
            later,
            "--json",
            "--summary-file",
            ".claude/logs/pending-summary.md",
            "--apply",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    index = (project / ".claude" / "checkpoints" / "INDEX.md").read_text(
        encoding="utf-8"
    )
    rows = [line for line in index.splitlines() if line.startswith("| 2026-")]

    assert len(rows) == 2
    assert rows[0].startswith("| 2026-07-26-100000 |"), index
    assert rows[1].startswith(f"| {STAMP} |"), index
    assert f"({STAMP}.md)" in rows[1]


def test_the_index_is_rebuilt_not_appended(project: Path) -> None:
    """A deleted checkpoint must disappear from the catalog.

    An append-only table would keep advertising a file that is no longer
    there, which is worse than having no index at all.
    """
    run(project, *summary_flag(project), "--apply")
    index_path = project / ".claude" / "checkpoints" / "INDEX.md"
    assert f"| {STAMP} |" in index_path.read_text(encoding="utf-8")

    (project / ".claude" / "checkpoints" / f"{STAMP}.md").unlink()

    assert f"| {STAMP} |" not in cp.compose_index_md(project)


def test_a_checkpoint_without_frontmatter_still_gets_a_row(project: Path) -> None:
    checkpoints = project / ".claude" / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    (checkpoints / "2026-01-01-000000.md").write_text(
        "# Checkpoint 2026-01-01-000000\n", encoding="utf-8"
    )

    index = cp.compose_index_md(project)

    assert "| 2026-01-01-000000 |" in index
    assert "(2026-01-01-000000.md)" in index


def test_the_index_preview_matches_what_apply_writes(project: Path) -> None:
    run(project, *summary_flag(project))
    preview = (
        project / ".claude" / "logs" / "index-preview-20260725-100000.md"
    ).read_text(encoding="utf-8")

    run(project, *summary_flag(project), "--apply")

    assert (project / ".claude" / "checkpoints" / "INDEX.md").read_text(
        encoding="utf-8"
    ) == preview


def test_the_index_is_never_mistaken_for_a_checkpoint(project: Path) -> None:
    """INDEX.md lives beside the checkpoints; PROGRESS.md must not list it."""
    run(project, *summary_flag(project), "--apply")

    stems = [path.stem for path in cp.get_checkpoint_files(project)]

    assert stems == [STAMP]
    assert "INDEX" not in (project / "PROGRESS.md").read_text(encoding="utf-8")


# --- fast retrieval: tags, escaping, regeneration ----------------------------


def test_tags_name_the_commit_types_and_directories_touched() -> None:
    """The index is searched by tag, so tags must describe the session."""
    collected = cp.Collected(
        commits=[{"message": "feat: add index"}, {"message": "fix: escape pipes"}],
        file_changes={
            "created": [".claude/skills/catchup/collect_repo_state.py"],
            "modified": ["tests/test_checkpoint.py"],
            "deleted": [],
        },
        cli_entries=[{"tool": "codex"}],
    )

    tags = cp.derive_tags(collected)

    assert {"feature", "bugfix", "tests", "testing", "skills", "codex"} <= set(tags)
    assert tags == sorted(tags)


def test_a_tag_cannot_break_the_frontmatter_flow_sequence() -> None:
    """`tags: [a, #b]` is a fatal YAML parse error: `, #` opens a comment.

    Tags come from directory and Agent Teams session names, so the characters
    that can arrive are not under this script's control.
    """
    collected = cp.Collected(
        file_changes={
            "created": ["#weird/x.py", "&anchor/y.py", "{brace}/z.py"],
            "modified": [],
            "deleted": [],
        },
        teams_data=[{"name": "a: b *alias"}],
    )

    tags = cp.derive_tags(collected)

    assert tags, tags
    for tag in tags:
        assert re.fullmatch(r"[A-Za-z0-9._/-]+", tag), tag
    assert "team-a-b-alias" in tags


def test_a_pipe_in_the_summary_stays_inside_its_index_column() -> None:
    row = cp._index_row(
        "2026-01-01-000000",
        {"slug": "s", "branch": "a|b", "summary": "add x | drop y", "commits": "1"},
    )

    cells = re.split(r"(?<!\\)\|", row)

    assert len(cells) == 8, row  # 6 cells plus the outer empties
    assert "add x \\| drop y" in row
    assert "a\\|b" in row


def test_a_bracket_in_the_slug_cannot_break_the_index_link() -> None:
    """A hand-edited frontmatter must not destroy the catalog's only link."""
    row = cp._index_row("2026-01-01-000000", {"slug": "broken] (x"})

    assert row.count("](") == 1, row
    assert "](2026-01-01-000000.md)" in row


def test_an_unterminated_frontmatter_block_yields_no_fields() -> None:
    """Without a closing fence a body line is indistinguishable from a field."""
    text = "---\nslug: real\n\n# Checkpoint\n\ncommits: 999\nsummary: injected\n"

    assert cp.parse_frontmatter(text) == {}
    assert cp.parse_frontmatter("---\nslug: real\n---\n\n# C\ncommits: 999\n") == {
        "slug": "real"
    }


def test_regenerating_the_index_is_byte_identical(project: Path) -> None:
    """The catalog is rebuilt on every run; drift would be invisible."""
    run(project, *summary_flag(project), "--apply")
    on_disk = (project / ".claude" / "checkpoints" / "INDEX.md").read_text(
        encoding="utf-8"
    )

    first = cp.compose_index_md(project)
    second = cp.compose_index_md(project)

    assert first == second
    assert first == on_disk


def test_a_failed_index_write_does_not_orphan_the_state_tracker(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INDEX.md is derivable and rebuilt next run; the tracker link is not.

    Aborting the whole run on a stale index used to leave a checkpoint and a
    PROGRESS.md entry with nothing in STATE.md pointing at them.
    """
    real_atomic_replace = cp.atomic_replace

    def failing(path: Path, new_text: str, original_text, validate=None):
        if path.name == cp.INDEX_FILENAME:
            return f"{path.name} was modified concurrently; aborting", 3
        return real_atomic_replace(path, new_text, original_text, validate)

    monkeypatch.setattr(cp, "atomic_replace", failing)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "checkpoint.py",
            "--project-root",
            str(project),
            "--claude-home",
            str(project / "claude-home"),
            "--now",
            NOW,
            "--json",
            *summary_flag(project),
            "--apply",
        ],
    )

    assert cp.main() == 3
    state = (project / ".claude" / "STATE.md").read_text(encoding="utf-8")
    progress = (project / "PROGRESS.md").read_text(encoding="utf-8")
    assert (project / ".claude" / "checkpoints" / f"{STAMP}.md").exists()
    assert STAMP in progress, progress
    assert "## Progress Tracker" in state, state
    assert "PROGRESS.md" in state, state


# --- CLI contract ------------------------------------------------------------


def test_help_exits_zero_and_documents_apply() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "--apply" in result.stdout
    assert "--project-root" in result.stdout
