#!/usr/bin/env python3
"""Generate a session checkpoint and rebuild the rolling PROGRESS.md.

Collects git history, CLI logs, Agent Teams activity, and design changes,
embeds the agent-written five-part Japanese summary, then rewrites root
``PROGRESS.md`` and the ``## Progress Tracker`` link in ``.agents/STATE.md``.

The summary is never generated. It is the one irreducible judgment in the
skill — what mattered this session, what the user decided, which problems were
real — so a missing, empty, stale, or contract-violating ``--summary-file`` is a
contract violation (exit 2) and nothing is written. An earlier revision
substituted commit counts for meaning and still exited 0.

``PROGRESS.md`` and ``.agents/STATE.md`` are user-owned, git-tracked documents,
so both writes follow the Writer Safety Contract: dry-run by default, ``--apply``
to write, atomic ``os.replace``, a content-hash concurrent-modification guard,
and validation of the composed document before it replaces the original.

Usage:
    python3 checkpoint.py --summary-file .agents/logs/pending-summary.md
    python3 checkpoint.py --summary-file PATH --apply
    python3 checkpoint.py --summary-file PATH --apply --consume-summary
    python3 checkpoint.py --summary-file PATH --since 2026-07-01 --json
    python3 checkpoint.py --summary-file PATH --now 2026-07-25T12:00:00+00:00

Exit codes:
    0  preview written (default) or checkpoint applied
    1  bad arguments (unparseable --since or --now)
    2  contract violation — no/missing/empty/stale/invalid summary file,
       .agents/STATE.md absent, 0 or >=2 Progress Tracker headings, or an
       invalid composed PROGRESS.md
    3  external failure — validator subprocess failed, checkpoint timestamp
       already taken, concurrent modification, or a write failure
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
VALIDATE_DOC = (
    PROJECT_ROOT / ".agents" / "skills" / "_shared" / "validate_doc.py"
).resolve()

# Agent Teams data lives under the invoking user's Claude home rather than the
# repository, so it gets its own override instead of riding on --project-root.
DEFAULT_CLAUDE_HOME = Path.home() / ".claude"

# PROGRESS-SUMMARY block markers (delimit the user-facing summary at the top
# of each checkpoint; PROGRESS.md is rebuilt from the content between them).
PROGRESS_SUMMARY_START = "<!-- PROGRESS-SUMMARY:START -->"
PROGRESS_SUMMARY_END = "<!-- PROGRESS-SUMMARY:END -->"

# Rolling PROGRESS.md keeps only the most recent N checkpoints.
MAX_PROGRESS_ENTRIES = 5

# Checkpoint filenames are exactly YYYY-MM-DD-HHMMSS.md. Matching the pattern
# (rather than every *.md) keeps drafts and dotfiles out of the rolling list —
# Path.glob("*.md") does match dotfiles.
CHECKPOINT_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}$")

SUMMARY_HEADING = "## サマリ"

# Fixed Japanese subsection headings for the user-facing summary block. The same
# five names are the `checkpoint-summary` contract in _shared/validate_doc.py,
# which is what actually enforces them; this list documents them next to the
# writer and is asserted against the contract by tests/test_checkpoint.py.
SUMMARY_SUBSECTIONS = [
    "### 何をしたのか",
    "### どういうやり取りをユーザーと行ったのか",
    "### どうやったのか",
    "### 途中でどういう課題が起こったのか",
    "### 将来のアクション",
]

STATE_TRACKER_HEADING = "## Progress Tracker"
STATE_TRACKER_BODY = (
    "Rolling progress summary (latest 5 checkpoints): [PROGRESS.md](../PROGRESS.md)"
)
CURRENT_BLOCK_RE = re.compile(r"^## Current (Project|Feature|Bug Fix)\b")
TOP_HEADING_RE = re.compile(r"^## ")

GIT_TIMEOUT_SECONDS = 30
VALIDATOR_TIMEOUT_SECONDS = 30

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_CONTRACT_VIOLATION = 2
EXIT_EXTERNAL_FAILURE = 3


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable rather than
    plain usage text on stderr, matching the shared script contract even
    though this script's normal output is human-readable progress text."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message, "artifacts": []})
        sys.exit(EXIT_BAD_ARGS)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


@dataclass
class GitResult:
    """A git invocation's outcome, keeping "failed" distinct from "no output"."""

    ok: bool
    output: str = ""
    error: str | None = None


@dataclass
class Collected:
    """Everything gathered for one checkpoint, plus honest failure records."""

    branch: str = "unknown"
    commits: list[dict] = field(default_factory=list)
    file_changes: dict[str, list[str]] = field(
        default_factory=lambda: {"created": [], "modified": [], "deleted": []}
    )
    file_stats: dict[str, tuple[int, int]] = field(default_factory=dict)
    cli_entries: list[dict] = field(default_factory=list)
    teams_data: list[dict] = field(default_factory=list)
    work_logs: dict[str, list[dict]] = field(default_factory=dict)
    design_diff: str | None = None
    collector_errors: list[str] = field(default_factory=list)
    skipped_records: dict[str, int] = field(default_factory=dict)


def run_git_command(args: list[str], project_root: Path) -> GitResult:
    """Run a git command, distinguishing failure from empty output."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return GitResult(False, error=f"git {args[0]} timed out")
    except (FileNotFoundError, OSError) as exc:
        return GitResult(False, error=f"git {args[0]} could not run: {exc}")
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        return GitResult(
            False,
            error=f"git {args[0]} exited {result.returncode}: "
            f"{detail[0] if detail else 'no stderr'}",
        )
    return GitResult(True, output=result.stdout.strip())


def parse_cli_logs(
    project_root: Path, collected: Collected, since: str | None = None
) -> list[dict]:
    """Parse the CLI-tools JSONL log, counting the records it had to skip."""
    log_file = project_root / ".agents" / "logs" / "cli-tools.jsonl"
    if not log_file.exists():
        return []

    since_dt = datetime.fromisoformat(since).replace(tzinfo=UTC) if since else None
    try:
        raw = log_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        collected.collector_errors.append(f"cannot read cli-tools.jsonl: {exc}")
        return []

    entries: list[dict] = []
    skipped = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if since_dt:
                entry_dt = datetime.fromisoformat(
                    entry["timestamp"].replace("Z", "+00:00")
                )
                if entry_dt < since_dt:
                    continue
            entries.append(entry)
        except (json.JSONDecodeError, KeyError, ValueError):
            skipped += 1
    if skipped:
        collected.skipped_records["cli_log_lines"] = skipped
    return entries


def get_git_commits(
    project_root: Path, collected: Collected, since: str | None = None
) -> list[dict]:
    """Get git commits since the specified date."""
    args = ["log", "--pretty=format:%H|%ai|%s", "-n", "100"]
    if since:
        args.extend(["--since", since])

    result = run_git_command(args, project_root)
    if not result.ok:
        collected.collector_errors.append(f"commits: {result.error}")
        return []

    commits = []
    for line in result.output.split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append(
                {"hash": parts[0][:7], "date": parts[1], "message": parts[2]}
            )
    return commits


def get_git_branch(project_root: Path, collected: Collected) -> str:
    """Get current git branch name."""
    result = run_git_command(["branch", "--show-current"], project_root)
    if not result.ok:
        collected.collector_errors.append(f"branch: {result.error}")
        return "unknown"
    return result.output or "unknown"


def get_file_changes(
    project_root: Path, collected: Collected, since: str | None = None
) -> dict[str, list[str]]:
    """Get file changes (created, modified, deleted) since the specified date."""
    changes: dict[str, list[str]] = {"created": [], "modified": [], "deleted": []}

    if since:
        args = ["log", "--since", since, "--name-status", "--pretty=format:"]
    else:
        args = ["diff", "--name-status", "HEAD~10", "HEAD"]

    result = run_git_command(args, project_root)
    if not result.ok:
        collected.collector_errors.append(f"file changes: {result.error}")
        return changes

    seen: set[str] = set()
    for line in result.output.split("\n"):
        line = line.strip()
        if not line or "\t" not in line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, filepath = parts[0], parts[1]
        if filepath in seen:
            continue
        seen.add(filepath)
        if status.startswith("A"):
            changes["created"].append(filepath)
        elif status.startswith("M"):
            changes["modified"].append(filepath)
        elif status.startswith("D"):
            changes["deleted"].append(filepath)

    return changes


def get_file_stats(
    project_root: Path, collected: Collected, since: str | None = None
) -> dict[str, tuple[int, int]]:
    """Get line additions/deletions per file."""
    if since:
        args = ["log", "--since", since, "--numstat", "--pretty=format:"]
    else:
        args = ["diff", "--numstat", "HEAD~10", "HEAD"]

    result = run_git_command(args, project_root)
    if not result.ok:
        collected.collector_errors.append(f"file stats: {result.error}")
        return {}

    stats: dict[str, tuple[int, int]] = {}
    for line in result.output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, filepath = parts
        try:
            add_count = int(added) if added != "-" else 0
            del_count = int(deleted) if deleted != "-" else 0
        except ValueError:
            continue
        prev = stats.get(filepath, (0, 0))
        stats[filepath] = (prev[0] + add_count, prev[1] + del_count)

    return stats


def collect_agent_teams_data(claude_home: Path, collected: Collected) -> list[dict]:
    """Collect Agent Teams activity from {claude_home}/teams and /tasks."""
    teams_dir = claude_home / "teams"
    tasks_dir = claude_home / "tasks"
    teams: list[dict] = []

    if not teams_dir.is_dir():
        return teams

    skipped = 0
    for team_dir in sorted(teams_dir.iterdir()):
        if not team_dir.is_dir():
            continue

        team_info: dict = {"name": team_dir.name, "members": [], "tasks": []}

        config_file = team_dir / "config.json"
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text(encoding="utf-8"))
                team_info["members"] = config.get("members", [])
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                skipped += 1

        task_dir = tasks_dir / team_dir.name
        if task_dir.is_dir():
            for task_file in sorted(task_dir.glob("*.json")):
                try:
                    team_info["tasks"].append(
                        json.loads(task_file.read_text(encoding="utf-8"))
                    )
                except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                    skipped += 1

        teams.append(team_info)

    if skipped:
        collected.skipped_records["agent_teams_files"] = skipped
    return teams


def collect_work_logs(
    project_root: Path, collected: Collected
) -> dict[str, list[dict]]:
    """Collect Teammate work logs from .agents/logs/agent-teams/{team}/."""
    logs_by_team: dict[str, list[dict]] = {}
    work_logs_dir = project_root / ".agents" / "logs" / "agent-teams"

    if not work_logs_dir.is_dir():
        return logs_by_team

    for team_dir in sorted(work_logs_dir.iterdir()):
        if not team_dir.is_dir():
            continue
        team_logs = []
        for log_file in sorted(team_dir.glob("*.md")):
            try:
                content = log_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                collected.collector_errors.append(f"work log {log_file.name}: {exc}")
                continue
            team_logs.append(
                {
                    "teammate": log_file.stem,
                    "file": _rel(log_file, project_root),
                    "content": content,
                }
            )
        if team_logs:
            logs_by_team[team_dir.name] = team_logs

    return logs_by_team


def get_design_decisions_diff(
    project_root: Path, collected: Collected, since: str | None = None
) -> str | None:
    """Get changes to DESIGN.md since last checkpoint or date."""
    design_file = project_root / ".agents" / "docs" / "DESIGN.md"
    if not design_file.exists():
        return None

    rel = _rel(design_file, project_root)
    if since:
        args = ["log", "--since", since, "-p", "--", rel]
    else:
        args = ["diff", "HEAD~10", "HEAD", "--", rel]

    result = run_git_command(args, project_root)
    if not result.ok:
        collected.collector_errors.append(f"design diff: {result.error}")
        return None
    return result.output or None


def collect_everything(
    project_root: Path, claude_home: Path, since: str | None
) -> Collected:
    """Run every collector, recording each failure instead of swallowing it."""
    collected = Collected()
    collected.branch = get_git_branch(project_root, collected)
    collected.commits = get_git_commits(project_root, collected, since)
    collected.file_changes = get_file_changes(project_root, collected, since)
    collected.file_stats = get_file_stats(project_root, collected, since)
    collected.cli_entries = parse_cli_logs(project_root, collected, since)
    collected.teams_data = collect_agent_teams_data(claude_home, collected)
    collected.work_logs = collect_work_logs(project_root, collected)
    collected.design_diff = get_design_decisions_diff(project_root, collected, since)
    return collected


# ---------------------------------------------------------------------------
# Summary validation
# ---------------------------------------------------------------------------


def newest_checkpoint_mtime(project_root: Path) -> float | None:
    """Modification time of the newest existing checkpoint file, or None."""
    files = get_checkpoint_files(project_root)
    if not files:
        return None
    return max(path.stat().st_mtime for path in files)


def validate_summary_contract(summary_path: Path, project_root: Path) -> str | None:
    """Gate the summary on validate_doc.py's ``checkpoint-summary`` contract.

    Returns None when valid, otherwise an error message. The five-part contract
    lives in one registry (``_shared/validate_doc.py``) rather than being
    re-implemented here, so the writer and the validator cannot drift.
    """
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_DOC),
                "--contract",
                "checkpoint-summary",
                "--file",
                str(summary_path),
                "--project-root",
                str(project_root),
            ],
            capture_output=True,
            text=True,
            timeout=VALIDATOR_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f"cannot run validate_doc.py: {exc}") from exc

    if result.returncode == 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"validate_doc.py exited {result.returncode} without JSON: "
            f"{result.stderr.strip()[:200]}"
        ) from None
    missing = payload.get("sections_missing") or []
    if missing:
        return f"summary is missing required section(s): {', '.join(missing)}"
    return payload.get("error") or "summary does not satisfy checkpoint-summary"


# ---------------------------------------------------------------------------
# Checkpoint generation
# ---------------------------------------------------------------------------


def build_summary_block(summary_body: str) -> str:
    """Wrap the agent-written '## サマリ' summary in PROGRESS-SUMMARY markers."""
    return "\n".join(
        [PROGRESS_SUMMARY_START, summary_body.strip(), PROGRESS_SUMMARY_END]
    )


def _append_summary_section(lines: list[str], collected: Collected) -> None:
    codex_count = sum(1 for e in collected.cli_entries if e.get("tool") == "codex")
    total_files = sum(len(v) for v in collected.file_changes.values())
    total_tasks = sum(len(t.get("tasks", [])) for t in collected.teams_data)
    completed_tasks = sum(
        1
        for t in collected.teams_data
        for task in t.get("tasks", [])
        if task.get("status") == "completed"
    )

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Branch**: `{collected.branch}`")
    lines.append(f"- **Commits**: {len(collected.commits)}")
    lines.append(
        f"- **Files changed**: {total_files} "
        f"({len(collected.file_changes['modified'])} modified, "
        f"{len(collected.file_changes['created'])} created, "
        f"{len(collected.file_changes['deleted'])} deleted)"
    )
    lines.append(f"- **Codex consultations**: {codex_count}")
    if collected.teams_data:
        total_members = sum(len(t.get("members", [])) for t in collected.teams_data)
        lines.append(
            f"- **Agent Teams sessions**: {len(collected.teams_data)} "
            f"({total_members} teammates)"
        )
        lines.append(f"- **Tasks**: {completed_tasks}/{total_tasks} completed")
    total_work_logs = sum(len(logs) for logs in collected.work_logs.values())
    if total_work_logs:
        lines.append(f"- **Teammate work logs**: {total_work_logs}")
    lines.append("")


def _append_collector_status(lines: list[str], collected: Collected) -> None:
    """Record collector failures in the checkpoint itself.

    Without this, "git could not run" and "nothing happened this session" read
    identically to whoever reads the checkpoint months later.
    """
    lines.append("## Collector Status")
    lines.append("")
    if not collected.collector_errors and not collected.skipped_records:
        lines.append("All collectors succeeded.")
        lines.append("")
        return
    for error in collected.collector_errors:
        lines.append(f"- FAILED: {error}")
    for key, count in sorted(collected.skipped_records.items()):
        lines.append(f"- SKIPPED: {count} unreadable/malformed {key}")
    lines.append("")


def _append_git_activity(lines: list[str], collected: Collected) -> None:
    lines.append("## Git Activity")
    lines.append("")

    if collected.commits:
        lines.append("### Commits")
        lines.append("")
        for commit in collected.commits[:30]:
            lines.append(f"- `{commit['hash']}` {commit['message']}")
        if len(collected.commits) > 30:
            lines.append(f"- ... and {len(collected.commits) - 30} more commits")
        lines.append("")

    lines.append("### File Changes")
    lines.append("")
    for category, label in [
        ("created", "Created"),
        ("modified", "Modified"),
        ("deleted", "Deleted"),
    ]:
        files = collected.file_changes[category]
        if not files:
            continue
        lines.append(f"**{label}:**")
        for name in files[:20]:
            stat = collected.file_stats.get(name, (0, 0))
            if category == "deleted":
                lines.append(f"- `{name}`")
            else:
                lines.append(f"- `{name}` (+{stat[0]}, -{stat[1]})")
        if len(files) > 20:
            lines.append(f"- ... and {len(files) - 20} more files")
        lines.append("")

    if not any(collected.file_changes.values()):
        lines.append("No file changes detected.")
        lines.append("")


def _append_cli_consultations(lines: list[str], collected: Collected) -> None:
    lines.append("## CLI Consultations")
    lines.append("")
    codex_entries = [e for e in collected.cli_entries if e.get("tool") == "codex"]
    if codex_entries:
        lines.append(f"### Codex ({len(codex_entries)} consultations)")
        lines.append("")
        for entry in codex_entries[:15]:
            status = "✓" if entry.get("success", False) else "✗"
            prompt = entry.get("prompt", "")[:100].replace("\n", " ")
            lines.append(f"- {status} {prompt}...")
        if len(codex_entries) > 15:
            lines.append(f"- ... and {len(codex_entries) - 15} more")
        lines.append("")
    if not collected.cli_entries:
        lines.append("No CLI consultations recorded.")
        lines.append("")


def _append_agent_teams(lines: list[str], collected: Collected) -> None:
    if not collected.teams_data:
        return
    lines.append("## Agent Teams Activity")
    lines.append("")
    for team in collected.teams_data:
        lines.append(f"### Team: {team['name']}")
        lines.append("")
        members = team.get("members", [])
        if members:
            lines.append("**Composition:**")
            for member in members:
                name = member.get("name", "unknown")
                agent_type = member.get("agent_type", "")
                lines.append(f"- {name} ({agent_type})")
            lines.append("")
        tasks = team.get("tasks", [])
        if tasks:
            lines.append("**Task List:**")
            for task in tasks:
                subject = task.get("task_subject", task.get("subject", "unknown"))
                status = task.get("status", "unknown")
                owner = task.get("teammate_name", "")
                checkbox = "x" if status == "completed" else " "
                owner_str = f" ({owner})" if owner else ""
                lines.append(f"- [{checkbox}] {subject}{owner_str}")
            lines.append("")
            completed = sum(1 for t in tasks if t.get("status") == "completed")
            lines.append("**Effectiveness:**")
            lines.append(f"- Tasks: {completed}/{len(tasks)} completed")
            lines.append("")


def _append_work_logs(lines: list[str], collected: Collected) -> None:
    if not collected.work_logs:
        return
    lines.append("## Teammate Work Logs")
    lines.append("")
    for team_name, logs in collected.work_logs.items():
        lines.append(f"### Team: {team_name}")
        lines.append("")
        for log in logs:
            lines.append(f"#### {log['teammate']}")
            lines.append(f"*Source: `{log['file']}`*")
            lines.append("")
            content_lines = log["content"].split("\n")
            lines.extend(content_lines[:50])
            if len(content_lines) > 50:
                lines.append(
                    f"... [truncated, {len(content_lines)} total lines — "
                    f"see full log at `{log['file']}`]"
                )
            lines.append("")


def _append_design_decisions(lines: list[str], collected: Collected) -> None:
    if not collected.design_diff:
        return
    lines.append("## Design Decisions (Changes)")
    lines.append("")
    added_lines = [
        line[1:].strip()
        for line in collected.design_diff.split("\n")
        if line.startswith("+")
        and not line.startswith("+++")
        and line.strip() not in ("+", "")
    ]
    for added in added_lines[:20]:
        lines.append(f"- {added}")
    lines.append("")


def generate_checkpoint(
    collected: Collected, since: str | None, summary_body: str, timestamp: str
) -> str:
    """Generate full checkpoint markdown content for the injected *timestamp*."""
    lines: list[str] = [f"# Checkpoint {timestamp}", ""]
    lines.append(build_summary_block(summary_body))
    lines.append("")
    _append_summary_section(lines, collected)
    if since:
        lines.append(f"- **Since**: {since}")
        lines.append("")
    _append_collector_status(lines, collected)
    _append_git_activity(lines, collected)
    _append_cli_consultations(lines, collected)
    _append_agent_teams(lines, collected)
    _append_work_logs(lines, collected)
    _append_design_decisions(lines, collected)
    lines.append("---")
    lines.append(f"*Generated by checkpointing skill at {timestamp}*")
    return "\n".join(lines)


def extract_summary_block(checkpoint_text: str) -> str | None:
    """Extract the content between PROGRESS-SUMMARY markers, or None if absent."""
    start = checkpoint_text.find(PROGRESS_SUMMARY_START)
    if start == -1:
        return None
    body_start = start + len(PROGRESS_SUMMARY_START)
    end = checkpoint_text.find(PROGRESS_SUMMARY_END, body_start)
    if end == -1:
        return None
    return checkpoint_text[body_start:end].strip()


def _strip_summary_heading(summary_body: str) -> str:
    """Drop a leading '## サマリ' heading so PROGRESS.md heading levels stay sane."""
    kept = [
        line for line in summary_body.splitlines() if line.strip() != SUMMARY_HEADING
    ]
    return "\n".join(kept).strip()


def get_checkpoint_files(project_root: Path) -> list[Path]:
    """Return checkpoint files matching YYYY-MM-DD-HHMMSS.md, newest first."""
    checkpoints_dir = project_root / ".agents" / "checkpoints"
    if not checkpoints_dir.is_dir():
        return []
    files = [
        path
        for path in checkpoints_dir.glob("*.md")
        if CHECKPOINT_STEM_RE.match(path.stem)
    ]
    return sorted(files, key=lambda p: p.stem, reverse=True)


@dataclass
class ProgressComposition:
    """The PROGRESS.md text plus honest counts of what was and was not used."""

    text: str
    entries: int = 0
    skipped_unreadable: int = 0
    skipped_no_marker: int = 0


def compose_progress_md(
    project_root: Path, pending: dict[str, str] | None = None
) -> ProgressComposition:
    """Compose PROGRESS.md from the newest checkpoints (newest first, max 5).

    *pending* maps a not-yet-written checkpoint stem to its content, so a
    dry-run previews exactly the document ``--apply`` would produce.
    """
    pending = pending or {}
    stems: dict[str, Path | None] = {stem: None for stem in pending}
    for path in get_checkpoint_files(project_root):
        stems.setdefault(path.stem, path)

    composition = ProgressComposition(text="")
    lines: list[str] = [
        "# PROGRESS",
        "",
        "> Auto-maintained by /checkpointing. "
        "Shows the most recent 5 checkpoints (newest first).",
        "> Full checkpoints live in `.agents/checkpoints/` (git-ignored).",
        "",
    ]

    for stem in sorted(stems, reverse=True)[:MAX_PROGRESS_ENTRIES]:
        path = stems[stem]
        if path is None:
            text = pending[stem]
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                composition.skipped_unreadable += 1
                continue
        summary = extract_summary_block(text)
        if summary is None:
            composition.skipped_no_marker += 1
            continue
        lines.append(f"## [{stem}](.agents/checkpoints/{stem}.md)")
        lines.append("")
        lines.append(_strip_summary_heading(summary))
        lines.append("")
        composition.entries += 1

    composition.text = "\n".join(lines).rstrip() + "\n"
    return composition


def compose_state_with_tracker(text: str) -> tuple[str, int]:
    """Return (new_state_text, tracker_heading_count_before).

    The tracker is inserted at its canonical position — immediately before the
    first ``## Current *`` working block — rather than appended at the end of the
    file. An appended tracker sat after the working blocks, where the compaction
    pass used to delete it, so every session re-appended it and the next
    compaction dropped it again.
    """
    lines = text.splitlines()
    count = sum(1 for line in lines if line.strip() == STATE_TRACKER_HEADING)
    if count != 0:
        return text, count

    block = [STATE_TRACKER_HEADING, "", STATE_TRACKER_BODY, ""]
    insert_at = next(
        (i for i, line in enumerate(lines) if CURRENT_BLOCK_RE.match(line.strip())),
        None,
    )
    if insert_at is None:
        new_lines = [*[line for line in lines], "", *block]
    else:
        new_lines = [*lines[:insert_at], *block, *lines[insert_at:]]
    new_text = "\n".join(new_lines).rstrip("\n") + "\n"
    return new_text, count


def validate_state_composition(new_text: str, original_text: str) -> str | None:
    """Return an error if the composed STATE.md is malformed, else None."""
    new_lines = new_text.splitlines()
    trackers = sum(1 for line in new_lines if line.strip() == STATE_TRACKER_HEADING)
    if trackers != 1:
        return f"expected exactly 1 '{STATE_TRACKER_HEADING}' heading, found {trackers}"
    surviving = [line.strip() for line in new_lines if TOP_HEADING_RE.match(line)]
    for heading in (
        line.strip()
        for line in original_text.splitlines()
        if TOP_HEADING_RE.match(line)
    ):
        if heading not in surviving:
            return f"composed document lost the heading '{heading}'"
        surviving = surviving[surviving.index(heading) + 1 :]
    return None


def generate_skill_analysis_prompt(checkpoint_content: str) -> str:
    """Generate prompt for AI skill pattern discovery."""
    return f"""Analyze the following checkpoint and identify reusable work patterns that could become skills.

A "skill" is a repeatable workflow pattern that can be triggered by specific phrases and executed consistently.

## Checkpoint Content

{checkpoint_content}

## Analysis Instructions

1. **Identify Patterns** in:
   - Sequences of commits forming logical workflows
   - File change patterns (e.g., test + implementation together)
   - CLI consultation sequences (research → design → implement)
   - Agent Teams coordination patterns (team composition, task sizing, communication)
   - Multi-step operations that could be templated

2. **For each potential skill, provide**:
   - **Name**: Short, descriptive (e.g., "tdd-feature", "research-implement")
   - **Description**: What this skill accomplishes
   - **Trigger phrases**: Japanese + English
   - **Workflow steps**: Ordered list of actions
   - **Confidence**: 0.0-1.0 (only suggest >= 0.6)
   - **Evidence**: What in the checkpoint suggests this pattern

3. **Check against existing skills** in `.agents/skills/`:
   - feature, team-execute, spike, plan, tdd
   - simplify, codex-system, design-tracker, checkpointing
   - research-lib, update-lib-docs, catchup, init, troubleshoot
   - If pattern matches an existing skill, note it but still report

4. **Quality criteria**:
   - Skip trivial patterns (single file edits, simple commits)
   - Focus on multi-step workflows that save time when repeated
   - Agent Teams patterns are especially valuable (team composition, task sizing)

Provide your analysis:"""


# ---------------------------------------------------------------------------
# Guarded writes
# ---------------------------------------------------------------------------


def write_new_file(path: Path, text: str) -> str | None:
    """Create *path*, refusing to overwrite. Returns an error message or None."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        return f"{path} already exists; refusing to overwrite"
    except OSError as exc:
        return f"cannot write {path}: {exc}"
    return None


def write_preview(path: Path, text: str) -> str | None:
    """Write a preview artifact. Returns an error message or None."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"cannot write preview {path}: {exc}"
    return None


def atomic_replace(
    path: Path,
    new_text: str,
    original_text: str | None,
    validate: object = None,
) -> tuple[str | None, int]:
    """Atomically replace *path* under the Writer Safety Contract.

    *original_text* is the content read earlier (None when the file did not
    exist); a mismatch means another writer landed in between and the write is
    abandoned. *validate* receives the bytes actually written to the temp file
    and returns an error message when the composition is unusable — checked
    before ``os.replace``, never after.
    """
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else None
    except (OSError, UnicodeDecodeError) as exc:
        return f"cannot re-read {path}: {exc}", EXIT_EXTERNAL_FAILURE

    if (current is None) != (original_text is None) or (
        current is not None
        and original_text is not None
        and _sha256(current) != _sha256(original_text)
    ):
        return (
            f"{path.name} was modified concurrently; aborting",
            EXIT_EXTERNAL_FAILURE,
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}-", suffix=".tmp", dir=str(path.parent)
        )
    except OSError as exc:
        return f"write failure: {exc}", EXIT_EXTERNAL_FAILURE

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_text)
        written = Path(tmp_name).read_text(encoding="utf-8")
        if callable(validate):
            error = validate(written)
            if error:
                os.unlink(tmp_name)
                return (
                    f"post-write validation failed: {error}",
                    EXIT_CONTRACT_VIOLATION,
                )
        os.replace(tmp_name, str(path))
    except OSError as exc:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        return f"write failure: {exc}", EXIT_EXTERNAL_FAILURE
    return None, EXIT_OK


def validate_progress_document(text: str, project_root: Path) -> str | None:
    """Validate composed PROGRESS.md against validate_doc.py's ``progress``."""
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", encoding="utf-8", delete=False
        ) as handle:
            handle.write(text)
            probe = Path(handle.name)
    except OSError as exc:
        return f"cannot stage PROGRESS.md for validation: {exc}"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_DOC),
                "--contract",
                "progress",
                "--file",
                str(probe),
                "--project-root",
                str(project_root),
            ],
            capture_output=True,
            text=True,
            timeout=VALIDATOR_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"cannot run validate_doc.py: {exc}"
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    if result.returncode == 0:
        return None
    return f"composed PROGRESS.md violates the 'progress' contract: {result.stdout.strip()[:300]}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Full session checkpoint with skill pattern discovery",
    )
    parser.add_argument(
        "--since", help="Only include data since this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--summary-file",
        help=(
            "Path to the agent-written '## サマリ' block (5 fixed subsections, "
            "gated by validate_doc.py --contract checkpoint-summary). Required: "
            "a missing summary is exit 2, never an auto-generated substitute."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write; without this flag the script only previews",
    )
    parser.add_argument(
        "--consume-summary",
        action="store_true",
        help="Delete --summary-file after a successful --apply, so a stale "
        "draft cannot be embedded in the next session's checkpoint",
    )
    parser.add_argument(
        "--now", help="ISO 8601 timestamp to stamp instead of the real clock"
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of prose"
    )
    parser.add_argument(
        "--claude-home",
        type=Path,
        default=DEFAULT_CLAUDE_HOME,
        help="Agent Teams data root (defaults to ~/.claude)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    return parser


def _resolve_summary(
    args: argparse.Namespace, root: Path
) -> tuple[Path | None, str, str]:
    """Resolve and read --summary-file. Returns (path, body, error)."""
    if not args.summary_file:
        return (
            None,
            "",
            (
                "--summary-file is required: the five-part Japanese summary is "
                "agent-written judgment and is never generated"
            ),
        )
    path = Path(args.summary_file)
    if not path.is_absolute():
        path = root / path
    try:
        body = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        return path, "", f"cannot read summary file {path}: {exc}"
    if not body:
        return path, "", f"summary file {path} is empty"
    return path, body, ""


@dataclass
class Preflight:
    """Preconditions checked before anything is collected or written."""

    error: str | None = None
    exit_code: int = EXIT_OK
    summary_path: Path | None = None
    summary_body: str = ""
    now: datetime | None = None


def _preflight(args: argparse.Namespace, root: Path) -> Preflight:
    """Validate every precondition before anything is collected or written."""

    def fail(message: str, code: int) -> Preflight:
        return Preflight(error=message, exit_code=code)

    try:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(tz=UTC)
    except ValueError as exc:
        return fail(f"cannot parse '--now': {exc}", EXIT_BAD_ARGS)
    if args.since:
        try:
            datetime.fromisoformat(args.since)
        except ValueError as exc:
            return fail(f"cannot parse '--since': {exc}", EXIT_BAD_ARGS)

    summary_path, summary_body, error = _resolve_summary(args, root)
    if error:
        return fail(error, EXIT_CONTRACT_VIOLATION)
    assert summary_path is not None

    try:
        contract_error = validate_summary_contract(summary_path, root)
    except RuntimeError as exc:
        return fail(str(exc), EXIT_EXTERNAL_FAILURE)
    if contract_error:
        return fail(contract_error, EXIT_CONTRACT_VIOLATION)

    newest = newest_checkpoint_mtime(root)
    if newest is not None and summary_path.stat().st_mtime < newest:
        return fail(
            f"summary file {summary_path} is older than the newest checkpoint; "
            "rewrite it for this session (a stale draft would be embedded silently)",
            EXIT_CONTRACT_VIOLATION,
        )

    state_path = root / ".agents" / "STATE.md"
    if not state_path.is_file():
        return fail(
            f"{state_path} is absent: shared state must exist before checkpointing",
            EXIT_CONTRACT_VIOLATION,
        )
    try:
        state_text = state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return fail(f"cannot read {state_path}: {exc}", EXIT_CONTRACT_VIOLATION)
    trackers = sum(
        1 for line in state_text.splitlines() if line.strip() == STATE_TRACKER_HEADING
    )
    if trackers > 1:
        return fail(
            f"{state_path} has {trackers} '{STATE_TRACKER_HEADING}' headings; "
            "expected 0 or 1",
            EXIT_CONTRACT_VIOLATION,
        )

    return Preflight(summary_path=summary_path, summary_body=summary_body, now=now)


def _human_report(payload: dict) -> str:
    lines = [
        f"Result: {payload['result']}",
        f"  Checkpoint:   {payload['checkpoint_path']}",
        f"  Prompt:       {payload['prompt_path']}",
        f"  PROGRESS.md:  {payload['progress_path']} ({payload['progress_entries']} entries)",
        f"  STATE.md:     {payload['state_path']} "
        f"(tracker {'inserted' if payload['state_updated'] else 'already present'})",
        f"  Git:          {payload['commits']} commits, {payload['files_changed']} files",
        f"  CLI:          {payload['cli_consultations']} consultations",
        f"  Agent Teams:  {payload['agent_teams']} teams, {payload['work_logs']} work logs",
    ]
    for error in payload["collector_errors"]:
        lines.append(f"  COLLECTOR FAILED: {error}")
    for warning in payload["warnings"]:
        lines.append(f"  WARNING: {warning}")
    if payload["result"] == "preview":
        lines.append("  Re-run with --apply to write the checkpoint.")
    else:
        lines.append("  Next: analyze the prompt file for skill patterns.")
    return "\n".join(lines)


def main() -> int:  # noqa: C901 — single-function CLI entry point
    args = _build_parser().parse_args()
    root = args.project_root

    preflight = _preflight(args, root)
    if preflight.error is not None:
        _emit({"ok": False, "error": preflight.error, "artifacts": []})
        return preflight.exit_code
    summary_path, summary_body, now = (
        preflight.summary_path,
        preflight.summary_body,
        preflight.now,
    )
    assert summary_path is not None and now is not None

    collected = collect_everything(root, args.claude_home, args.since)

    timestamp = now.strftime("%Y-%m-%d-%H%M%S")
    checkpoint_path = root / ".agents" / "checkpoints" / f"{timestamp}.md"
    if checkpoint_path.exists():
        _emit(
            {
                "ok": False,
                "error": f"{checkpoint_path} already exists; pass a distinct --now",
                "artifacts": [],
            }
        )
        return EXIT_EXTERNAL_FAILURE

    checkpoint_content = generate_checkpoint(
        collected, args.since, summary_body, timestamp
    )
    prompt_path = checkpoint_path.with_suffix(".analyze-prompt.md")
    prompt_content = generate_skill_analysis_prompt(checkpoint_content)

    progress = compose_progress_md(root, {timestamp: checkpoint_content})
    progress_path = root / "PROGRESS.md"
    progress_before: str | None
    try:
        progress_before = (
            progress_path.read_text(encoding="utf-8")
            if progress_path.exists()
            else None
        )
    except (OSError, UnicodeDecodeError) as exc:
        _emit(
            {
                "ok": False,
                "error": f"cannot read {progress_path}: {exc}",
                "artifacts": [],
            }
        )
        return EXIT_CONTRACT_VIOLATION

    progress_error = validate_progress_document(progress.text, root)
    if progress_error:
        _emit({"ok": False, "error": progress_error, "artifacts": []})
        return EXIT_CONTRACT_VIOLATION

    state_path = root / ".agents" / "STATE.md"
    state_before = state_path.read_text(encoding="utf-8")
    state_after, trackers_before = compose_state_with_tracker(state_before)
    state_error = validate_state_composition(state_after, state_before)
    if state_error:
        _emit({"ok": False, "error": state_error, "artifacts": []})
        return EXIT_CONTRACT_VIOLATION

    warnings: list[str] = []
    if progress.skipped_unreadable:
        warnings.append(f"{progress.skipped_unreadable} checkpoint(s) were unreadable")
    if progress.skipped_no_marker:
        warnings.append(
            f"{progress.skipped_no_marker} checkpoint(s) had no PROGRESS-SUMMARY block"
        )

    payload = {
        "ok": True,
        "result": "applied" if args.apply else "preview",
        "checkpoint_path": _rel(checkpoint_path, root),
        "prompt_path": _rel(prompt_path, root),
        "progress_path": _rel(progress_path, root),
        "progress_entries": progress.entries,
        "state_path": _rel(state_path, root),
        "state_updated": trackers_before == 0,
        "summary_validated": True,
        "summary_consumed": False,
        "commits": len(collected.commits),
        "files_changed": sum(len(v) for v in collected.file_changes.values()),
        "cli_consultations": len(collected.cli_entries),
        "agent_teams": len(collected.teams_data),
        "work_logs": sum(len(logs) for logs in collected.work_logs.values()),
        "collector_errors": collected.collector_errors,
        "skipped_records": collected.skipped_records,
        "warnings": warnings,
        "artifacts": [],
    }

    logs_dir = root / ".agents" / "logs"
    stamp = now.strftime("%Y%m%d-%H%M%S")

    if not args.apply:
        previews = {
            logs_dir / f"checkpoint-preview-{stamp}.md": checkpoint_content,
            logs_dir / f"progress-preview-{stamp}.md": progress.text,
            logs_dir / f"state-preview-{stamp}.md": state_after,
        }
        for path, text in previews.items():
            error = write_preview(path, text)
            if error:
                _emit({"ok": False, "error": error, "artifacts": []})
                return EXIT_EXTERNAL_FAILURE
        payload["preview_files"] = [_rel(path, root) for path in previews]
        payload["artifacts"] = list(payload["preview_files"])
    else:
        for path, text in (
            (checkpoint_path, checkpoint_content),
            (prompt_path, prompt_content),
        ):
            error = write_new_file(path, text)
            if error:
                _emit({"ok": False, "error": error, "artifacts": []})
                return EXIT_EXTERNAL_FAILURE

        error, code = atomic_replace(
            progress_path,
            progress.text,
            progress_before,
            lambda written: validate_progress_document(written, root),
        )
        if error:
            _emit({"ok": False, "error": error, "artifacts": []})
            return code

        if trackers_before == 0:
            error, code = atomic_replace(
                state_path,
                state_after,
                state_before,
                lambda written: validate_state_composition(written, state_before),
            )
            if error:
                _emit({"ok": False, "error": error, "artifacts": []})
                return code

        payload["artifacts"] = [
            _rel(checkpoint_path, root),
            _rel(prompt_path, root),
            _rel(progress_path, root),
        ]
        if trackers_before == 0:
            payload["artifacts"].append(_rel(state_path, root))

        if args.consume_summary:
            try:
                summary_path.unlink()
                payload["summary_consumed"] = True
            except OSError as exc:
                payload["warnings"].append(f"cannot delete {summary_path}: {exc}")

    if args.json:
        _emit(payload)
    else:
        print(_human_report(payload))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
