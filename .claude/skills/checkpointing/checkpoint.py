#!/usr/bin/env python3
"""
Checkpoint script: Collect all session activity and generate a comprehensive checkpoint.

Usage:
    python checkpoint.py                          # Full checkpoint (everything)
    python checkpoint.py --since YYYY-MM-DD       # Only recent activity
    python checkpoint.py --summary-file PATH      # Embed a pre-written summary block

Every run does everything:
1. Collect git history, CLI logs, Agent Teams activity, design decisions
2. Generate checkpoint file in .claude/checkpoints/ with a PROGRESS-SUMMARY block
   at the top (either supplied via --summary-file or auto-generated)
3. Regenerate the rolling PROGRESS.md (latest 5 checkpoints, newest first)
4. Ensure a Zone-C-safe PROGRESS.md link exists in CLAUDE.md
5. Output skill analysis prompt for subagent pattern discovery
"""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
LOG_FILE = PROJECT_ROOT / ".claude" / "logs" / "cli-tools.jsonl"
CHECKPOINTS_DIR = PROJECT_ROOT / ".claude" / "checkpoints"
DESIGN_FILE = PROJECT_ROOT / ".claude" / "docs" / "DESIGN.md"
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"
PROGRESS_MD = PROJECT_ROOT / "PROGRESS.md"

# Agent Teams data locations
TEAMS_DIR = Path.home() / ".claude" / "teams"
TASKS_DIR = Path.home() / ".claude" / "tasks"
WORK_LOGS_DIR = PROJECT_ROOT / ".claude" / "logs" / "agent-teams"

# PROGRESS-SUMMARY block markers (delimit the user-facing summary at the top
# of each checkpoint; PROGRESS.md is rebuilt from the content between them).
PROGRESS_SUMMARY_START = "<!-- PROGRESS-SUMMARY:START -->"
PROGRESS_SUMMARY_END = "<!-- PROGRESS-SUMMARY:END -->"

# Zone C boundary marker in CLAUDE.md (everything below this line is Zone C).
REPO_BOUNDARY_MARKER = "@orchestra:repo-boundary"

# Rolling PROGRESS.md keeps only the most recent N checkpoints.
MAX_PROGRESS_ENTRIES = 5

# Fixed Japanese subsection headings for the user-facing summary block.
SUMMARY_SUBSECTIONS = [
    "### 何をしたのか",
    "### どういうやり取りをユーザーと行ったのか",
    "### どうやったのか",
    "### 途中でどういう課題が起こったのか",
    "### 将来のアクション",
]


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


def run_git_command(args: list[str]) -> str | None:
    """Run a git command and return output, or None if failed."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def parse_cli_logs(since: str | None = None) -> list[dict]:
    """Parse JSONL log file and return entries."""
    if not LOG_FILE.exists():
        return []

    entries = []
    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since).replace(tzinfo=UTC)

    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
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
            except (json.JSONDecodeError, KeyError):
                continue

    return entries


def get_git_commits(since: str | None = None) -> list[dict]:
    """Get git commits since the specified date."""
    args = ["log", "--pretty=format:%H|%ai|%s", "-n", "100"]
    if since:
        args.extend(["--since", since])

    output = run_git_command(args)
    if not output:
        return []

    commits = []
    for line in output.split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0][:7],
                "date": parts[1],
                "message": parts[2],
            })
    return commits


def get_git_branch() -> str:
    """Get current git branch name."""
    return run_git_command(["branch", "--show-current"]) or "unknown"


def get_file_changes(since: str | None = None) -> dict[str, list[str]]:
    """Get file changes (created, modified, deleted) since the specified date."""
    changes: dict[str, list[str]] = {"created": [], "modified": [], "deleted": []}

    if since:
        args = ["log", "--since", since, "--name-status", "--pretty=format:"]
    else:
        args = ["diff", "--name-status", "HEAD~10", "HEAD"]

    output = run_git_command(args)
    if not output:
        return changes

    seen: set[str] = set()
    for line in output.split("\n"):
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


def get_file_stats(since: str | None = None) -> dict[str, tuple[int, int]]:
    """Get line additions/deletions per file."""
    if since:
        args = ["log", "--since", since, "--numstat", "--pretty=format:"]
    else:
        args = ["diff", "--numstat", "HEAD~10", "HEAD"]

    output = run_git_command(args)
    if not output:
        return {}

    stats: dict[str, tuple[int, int]] = {}
    for line in output.split("\n"):
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
            if filepath in stats:
                prev = stats[filepath]
                stats[filepath] = (prev[0] + add_count, prev[1] + del_count)
            else:
                stats[filepath] = (add_count, del_count)
        except ValueError:
            continue

    return stats


def collect_agent_teams_data() -> list[dict]:
    """Collect Agent Teams activity from ~/.claude/teams/ and ~/.claude/tasks/."""
    teams = []

    if not TEAMS_DIR.exists():
        return teams

    for team_dir in TEAMS_DIR.iterdir():
        if not team_dir.is_dir():
            continue

        team_info: dict = {"name": team_dir.name, "members": [], "tasks": []}

        # Read team config
        config_file = team_dir / "config.json"
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text(encoding="utf-8"))
                team_info["members"] = config.get("members", [])
            except (json.JSONDecodeError, OSError):
                pass

        # Read task list
        task_dir = TASKS_DIR / team_dir.name
        if task_dir.exists():
            for task_file in task_dir.glob("*.json"):
                try:
                    task = json.loads(task_file.read_text(encoding="utf-8"))
                    team_info["tasks"].append(task)
                except (json.JSONDecodeError, OSError):
                    continue

        teams.append(team_info)

    return teams


def collect_work_logs() -> dict[str, list[dict]]:
    """Collect Teammate work logs from .claude/logs/agent-teams/{team}/."""
    logs_by_team: dict[str, list[dict]] = {}

    if not WORK_LOGS_DIR.exists():
        return logs_by_team

    for team_dir in WORK_LOGS_DIR.iterdir():
        if not team_dir.is_dir():
            continue

        team_logs = []
        for log_file in sorted(team_dir.glob("*.md")):
            try:
                content = log_file.read_text(encoding="utf-8")
                team_logs.append({
                    "teammate": log_file.stem,
                    "file": str(log_file.relative_to(PROJECT_ROOT)),
                    "content": content,
                })
            except OSError:
                continue

        if team_logs:
            logs_by_team[team_dir.name] = team_logs

    return logs_by_team


def get_design_decisions_diff(since: str | None = None) -> str | None:
    """Get changes to DESIGN.md since last checkpoint or date."""
    if not DESIGN_FILE.exists():
        return None

    if since:
        args = ["log", "--since", since, "-p", "--", str(DESIGN_FILE.relative_to(PROJECT_ROOT))]
    else:
        args = ["diff", "HEAD~10", "HEAD", "--", str(DESIGN_FILE.relative_to(PROJECT_ROOT))]

    return run_git_command(args)


# ---------------------------------------------------------------------------
# Checkpoint generation
# ---------------------------------------------------------------------------


def build_summary_block(
    summary_body: str,
    commits: list[dict],
    file_changes: dict[str, list[str]],
    cli_entries: list[dict],
    teams_data: list[dict],
) -> str:
    """Wrap the user-facing '## サマリ' summary in PROGRESS-SUMMARY markers.

    `summary_body` is the markdown body (starting with '## サマリ') either
    supplied via --summary-file or auto-generated when none is provided.
    """
    body = summary_body.strip()
    if not body:
        body = auto_generate_summary_body(
            commits=commits,
            file_changes=file_changes,
            cli_entries=cli_entries,
            teams_data=teams_data,
        )
    return "\n".join([PROGRESS_SUMMARY_START, body, PROGRESS_SUMMARY_END])


def auto_generate_summary_body(
    commits: list[dict],
    file_changes: dict[str, list[str]],
    cli_entries: list[dict],
    teams_data: list[dict],
) -> str:
    """Auto-generate a '## サマリ' block from collected data (no summary file).

    The Japanese subsection headings are fixed (user-facing session record).
    The 'どういうやり取りをユーザーと行ったのか' section cannot be inferred
    from git/CLI data, so it falls back to a pointer to the sections below.
    """
    total_files = sum(len(v) for v in file_changes.values())
    codex_count = sum(1 for e in cli_entries if e.get("tool") == "codex")
    lines: list[str] = ["## サマリ", ""]

    lines.append("### 何をしたのか")
    lines.append(
        f"- {len(commits)} commits, {total_files} files changed"
    )
    if codex_count:
        lines.append(f"- Codex consultations: {codex_count}")
    for team in teams_data:
        tasks = team.get("tasks", [])
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        lines.append(
            f"- Agent Teams: {team['name']} "
            f"({completed}/{len(tasks)} tasks completed)"
        )
    lines.append("")

    lines.append("### どういうやり取りをユーザーと行ったのか")
    lines.append("(no summary file provided — see git/CLI sections below)")
    lines.append("")

    lines.append("### どうやったのか")
    if teams_data:
        lines.append("- Used Agent Teams for parallel work (see activity below)")
    if codex_count:
        lines.append("- Consulted Codex CLI (see CLI Consultations below)")
    if not teams_data and not codex_count:
        lines.append("(auto-generated — see Git Activity below)")
    lines.append("")

    lines.append("### 途中でどういう課題が起こったのか")
    lines.append("(no summary file provided)")
    lines.append("")

    lines.append("### 将来のアクション")
    lines.append("(no summary file provided)")
    lines.append("")

    return "\n".join(lines).strip()


def generate_checkpoint(
    commits: list[dict],
    file_changes: dict[str, list[str]],
    file_stats: dict[str, tuple[int, int]],
    cli_entries: list[dict],
    teams_data: list[dict],
    work_logs: dict[str, list[dict]],
    design_diff: str | None,
    branch: str,
    since: str | None,
    summary_body: str,
) -> str:
    """Generate full checkpoint markdown content."""
    now = datetime.now(UTC)
    lines: list[str] = []

    # Header uses the filename timestamp format (YYYY-MM-DD-HHMMSS, UTC).
    timestamp = now.strftime("%Y-%m-%d-%H%M%S")
    lines.append(f"# Checkpoint {timestamp}")
    lines.append("")

    # User-facing summary block (always present, wrapped in PROGRESS-SUMMARY
    # markers so PROGRESS.md can be rebuilt from it).
    lines.append(
        build_summary_block(
            summary_body=summary_body,
            commits=commits,
            file_changes=file_changes,
            cli_entries=cli_entries,
            teams_data=teams_data,
        )
    )
    lines.append("")

    # Summary
    codex_count = sum(1 for e in cli_entries if e.get("tool") == "codex")
    total_files = sum(len(v) for v in file_changes.values())
    total_tasks = sum(len(t.get("tasks", [])) for t in teams_data)
    completed_tasks = sum(
        1
        for t in teams_data
        for task in t.get("tasks", [])
        if task.get("status") == "completed"
    )

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Branch**: `{branch}`")
    lines.append(f"- **Commits**: {len(commits)}")
    lines.append(
        f"- **Files changed**: {total_files} "
        f"({len(file_changes['modified'])} modified, "
        f"{len(file_changes['created'])} created, "
        f"{len(file_changes['deleted'])} deleted)"
    )
    lines.append(f"- **Codex consultations**: {codex_count}")
    if teams_data:
        total_members = sum(len(t.get("members", [])) for t in teams_data)
        lines.append(
            f"- **Agent Teams sessions**: {len(teams_data)} "
            f"({total_members} teammates)"
        )
        lines.append(f"- **Tasks**: {completed_tasks}/{total_tasks} completed")
    total_work_logs = sum(len(logs) for logs in work_logs.values())
    if total_work_logs:
        lines.append(f"- **Teammate work logs**: {total_work_logs}")
    if since:
        lines.append(f"- **Since**: {since}")
    lines.append("")

    # Git Activity
    lines.append("## Git Activity")
    lines.append("")

    if commits:
        lines.append("### Commits")
        lines.append("")
        for commit in commits[:30]:
            lines.append(f"- `{commit['hash']}` {commit['message']}")
        if len(commits) > 30:
            lines.append(f"- ... and {len(commits) - 30} more commits")
        lines.append("")

    lines.append("### File Changes")
    lines.append("")

    for category, label in [
        ("created", "Created"),
        ("modified", "Modified"),
        ("deleted", "Deleted"),
    ]:
        files = file_changes[category]
        if files:
            lines.append(f"**{label}:**")
            for f in files[:20]:
                stat = file_stats.get(f, (0, 0))
                if category == "deleted":
                    lines.append(f"- `{f}`")
                else:
                    lines.append(f"- `{f}` (+{stat[0]}, -{stat[1]})")
            if len(files) > 20:
                lines.append(f"- ... and {len(files) - 20} more files")
            lines.append("")

    if not any(file_changes.values()):
        lines.append("No file changes detected.")
        lines.append("")

    # CLI Consultations
    lines.append("## CLI Consultations")
    lines.append("")

    codex_entries = [e for e in cli_entries if e.get("tool") == "codex"]

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

    if not cli_entries:
        lines.append("No CLI consultations recorded.")
        lines.append("")

    # Agent Teams Activity
    if teams_data:
        lines.append("## Agent Teams Activity")
        lines.append("")

        for team in teams_data:
            lines.append(f"### Team: {team['name']}")
            lines.append("")

            # Members
            members = team.get("members", [])
            if members:
                lines.append("**Composition:**")
                for member in members:
                    name = member.get("name", "unknown")
                    agent_type = member.get("agent_type", "")
                    lines.append(f"- {name} ({agent_type})")
                lines.append("")

            # Tasks
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

                # Effectiveness
                completed = sum(1 for t in tasks if t.get("status") == "completed")
                lines.append("**Effectiveness:**")
                lines.append(f"- Tasks: {completed}/{len(tasks)} completed")
                lines.append("")

    # Teammate Work Logs
    if work_logs:
        lines.append("## Teammate Work Logs")
        lines.append("")

        for team_name, logs in work_logs.items():
            lines.append(f"### Team: {team_name}")
            lines.append("")

            for log in logs:
                lines.append(f"#### {log['teammate']}")
                lines.append(f"*Source: `{log['file']}`*")
                lines.append("")
                # Include first 50 lines of log content as summary
                content_lines = log["content"].split("\n")
                for content_line in content_lines[:50]:
                    lines.append(content_line)
                if len(content_lines) > 50:
                    lines.append(
                        f"... [truncated, {len(content_lines)} total lines — "
                        f"see full log at `{log['file']}`]"
                    )
                lines.append("")

    # Design Decisions
    if design_diff:
        lines.append("## Design Decisions (Changes)")
        lines.append("")

        # Extract added lines from diff
        added_lines = [
            line[1:].strip()
            for line in design_diff.split("\n")
            if line.startswith("+") and not line.startswith("+++")
            and line.strip() not in ("+", "")
        ]
        for added in added_lines[:20]:
            lines.append(f"- {added}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Generated by checkpointing skill at {timestamp}*")

    return "\n".join(lines)


def extract_summary_block(checkpoint_text: str) -> str | None:
    """Extract the content between PROGRESS-SUMMARY markers, or None if absent.

    Returns the inner markdown (typically starting with '## サマリ'), stripped.
    """
    start = checkpoint_text.find(PROGRESS_SUMMARY_START)
    if start == -1:
        return None
    body_start = start + len(PROGRESS_SUMMARY_START)
    end = checkpoint_text.find(PROGRESS_SUMMARY_END, body_start)
    if end == -1:
        return None
    return checkpoint_text[body_start:end].strip()


def _strip_summary_heading(summary_body: str) -> str:
    """Drop a leading '## サマリ' heading so PROGRESS.md heading levels stay sane.

    In PROGRESS.md each entry's '## [ts](link)' is the heading, so the inner
    '## サマリ' line is removed; only the '###' subsections are kept.
    """
    out_lines: list[str] = []
    for line in summary_body.splitlines():
        if line.strip() == "## サマリ":
            continue
        out_lines.append(line)
    # Trim leading/trailing blank lines after removal.
    return "\n".join(out_lines).strip()


def get_checkpoint_files() -> list[Path]:
    """Return checkpoint .md files (excluding .analyze-prompt.md), newest first.

    Sort is by filename timestamp (YYYY-MM-DD-HHMMSS) which is lexicographically
    ordered, so descending name sort == newest first.
    """
    if not CHECKPOINTS_DIR.exists():
        return []
    files = [
        p
        for p in CHECKPOINTS_DIR.glob("*.md")
        if not p.name.endswith(".analyze-prompt.md")
    ]
    return sorted(files, key=lambda p: p.stem, reverse=True)


def regenerate_progress_md() -> bool:
    """Rebuild PROGRESS.md from the latest checkpoints (newest first, max 5).

    Fully overwrites PROGRESS.md every run. Each entry links to its checkpoint
    file and reproduces that checkpoint's PROGRESS-SUMMARY subsections.
    """
    checkpoint_files = get_checkpoint_files()[:MAX_PROGRESS_ENTRIES]

    lines: list[str] = [
        "# PROGRESS",
        "",
        "> Auto-maintained by /checkpointing. "
        "Shows the most recent 5 checkpoints (newest first).",
        "> Full checkpoints live in `.claude/checkpoints/` (git-ignored).",
        "",
    ]

    for cp_file in checkpoint_files:
        try:
            text = cp_file.read_text(encoding="utf-8")
        except OSError:
            continue
        summary = extract_summary_block(text)
        if summary is None:
            continue
        ts = cp_file.stem
        lines.append(f"## [{ts}](.claude/checkpoints/{ts}.md)")
        lines.append("")
        lines.append(_strip_summary_heading(summary))
        lines.append("")

    PROGRESS_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return True


def ensure_progress_link() -> bool:
    """Idempotently ensure a Zone-C PROGRESS.md link block exists in CLAUDE.md.

    Inserts a '## Progress Tracker' block below the @orchestra:repo-boundary
    marker (Zone C). Never touches Zone A/B or the marker lines. No-op if the
    block already exists.
    """
    if not CLAUDE_MD.exists():
        return False

    content = CLAUDE_MD.read_text(encoding="utf-8")

    if "## Progress Tracker" in content:
        return True  # Already present; idempotent no-op.

    lines = content.splitlines()

    # Find the last line containing the repo-boundary marker (end of the
    # marker box). Zone C begins after it.
    marker_idx = None
    for idx, line in enumerate(lines):
        if REPO_BOUNDARY_MARKER in line:
            marker_idx = idx
    if marker_idx is None:
        return False  # Cannot safely place the block without the boundary.

    block = [
        "",
        "## Progress Tracker",
        "",
        "Rolling progress summary (latest 5 checkpoints): "
        "[PROGRESS.md](./PROGRESS.md)",
    ]

    new_lines = lines[: marker_idx + 1] + block + lines[marker_idx + 1 :]
    CLAUDE_MD.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    return True


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

3. **Check against existing skills** in `.claude/skills/`:
   - start-feature, team-implement, team-review, add-feature, spike, plan, tdd
   - simplify, codex-system, design-tracker, checkpointing, context-refresh
   - research-lib, update-lib-docs, catchup, init, troubleshoot
   - If pattern matches an existing skill, note it but still report

4. **Quality criteria**:
   - Skip trivial patterns (single file edits, simple commits)
   - Focus on multi-step workflows that save time when repeated
   - Agent Teams patterns are especially valuable (team composition, task sizing)

Provide your analysis:"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Full session checkpoint with skill pattern discovery",
    )
    parser.add_argument(
        "--since",
        help="Only include data since this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--summary-file",
        help=(
            "Path to a pre-written '## サマリ' block (5 fixed subsections). "
            "When omitted, the summary is auto-generated from collected data."
        ),
    )
    args = parser.parse_args()

    summary_body = ""
    if args.summary_file:
        summary_path = Path(args.summary_file)
        if not summary_path.is_absolute():
            summary_path = PROJECT_ROOT / summary_path
        if summary_path.exists():
            summary_body = summary_path.read_text(encoding="utf-8").strip()
        else:
            print(f"  Warning: summary file not found: {summary_path}")

    print("Collecting session data...")

    # 1. Collect everything
    branch = get_git_branch()
    commits = get_git_commits(args.since)
    file_changes = get_file_changes(args.since)
    file_stats = get_file_stats(args.since)
    cli_entries = parse_cli_logs(args.since)
    teams_data = collect_agent_teams_data()
    work_logs = collect_work_logs()
    design_diff = get_design_decisions_diff(args.since)

    total_logs = sum(len(logs) for logs in work_logs.values())
    print(f"  Git: {len(commits)} commits, {sum(len(v) for v in file_changes.values())} files")
    print(f"  CLI: {len(cli_entries)} consultations")
    print(f"  Agent Teams: {len(teams_data)} teams")
    print(f"  Work logs: {total_logs} teammate logs")

    # 2. Generate checkpoint
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    checkpoint_file = CHECKPOINTS_DIR / f"{timestamp}.md"

    checkpoint_content = generate_checkpoint(
        commits=commits,
        file_changes=file_changes,
        file_stats=file_stats,
        cli_entries=cli_entries,
        teams_data=teams_data,
        work_logs=work_logs,
        design_diff=design_diff,
        branch=branch,
        since=args.since,
        summary_body=summary_body,
    )
    checkpoint_file.write_text(checkpoint_content, encoding="utf-8")
    print(f"\nCheckpoint: {checkpoint_file}")

    # 3. Generate skill analysis prompt
    prompt = generate_skill_analysis_prompt(checkpoint_content)
    prompt_file = checkpoint_file.with_suffix(".analyze-prompt.md")
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"Analysis prompt: {prompt_file}")

    # 4. Regenerate rolling PROGRESS.md (latest 5 checkpoints, newest first).
    if regenerate_progress_md():
        print(f"Progress summary: {PROGRESS_MD}")

    # 5. Ensure CLAUDE.md has a Zone-C-safe PROGRESS.md link.
    if ensure_progress_link():
        print(f"Progress link ensured in: {CLAUDE_MD}")

    print("\nDone. Next: spawn subagent to analyze the prompt file for skill patterns.")


if __name__ == "__main__":
    main()
