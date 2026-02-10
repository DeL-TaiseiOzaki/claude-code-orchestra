#!/usr/bin/env python3
"""
Checkpoint script: Collect all session activity and generate a comprehensive checkpoint.

Usage:
    python checkpoint.py                          # Full checkpoint (everything)
    python checkpoint.py --since YYYY-MM-DD       # Only recent activity
    python checkpoint.py --label "feature-name"   # Custom label for the checkpoint

Every run does everything:
1. Collect git history, CLI logs, Agent Teams activity, design decisions
2. Generate checkpoint file in .claude/checkpoints/ (with slug + frontmatter)
3. Update CLAUDE.md with session history summary
4. Update INDEX.md catalog for fast retrieval
5. Output skill analysis prompt for subagent pattern discovery
"""

import argparse
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
LOG_FILE = PROJECT_ROOT / ".claude" / "logs" / "cli-tools.jsonl"
CHECKPOINTS_DIR = PROJECT_ROOT / ".claude" / "checkpoints"
DESIGN_FILE = PROJECT_ROOT / ".claude" / "docs" / "DESIGN.md"
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"

# Agent Teams data locations
TEAMS_DIR = Path.home() / ".claude" / "teams"
TASKS_DIR = Path.home() / ".claude" / "tasks"

INDEX_FILE = CHECKPOINTS_DIR / "INDEX.md"

SESSION_HISTORY_HEADER = "## Session History"

# Conventional commit prefixes to category mapping
COMMIT_TYPE_CATEGORIES: dict[str, str] = {
    "feat": "feature",
    "fix": "bugfix",
    "refactor": "refactor",
    "docs": "docs",
    "test": "testing",
    "chore": "chore",
    "perf": "performance",
    "ci": "ci",
    "style": "style",
    "build": "build",
}


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
            commits.append(
                {
                    "hash": parts[0][:7],
                    "date": parts[1],
                    "message": parts[2],
                }
            )
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


def get_design_decisions_diff(since: str | None = None) -> str | None:
    """Get changes to DESIGN.md since last checkpoint or date."""
    if not DESIGN_FILE.exists():
        return None

    if since:
        args = [
            "log",
            "--since",
            since,
            "-p",
            "--",
            str(DESIGN_FILE.relative_to(PROJECT_ROOT)),
        ]
    else:
        args = [
            "diff",
            "HEAD~10",
            "HEAD",
            "--",
            str(DESIGN_FILE.relative_to(PROJECT_ROOT)),
        ]

    return run_git_command(args)


# ---------------------------------------------------------------------------
# Slug, tags, and frontmatter helpers
# ---------------------------------------------------------------------------


def _slugify(text: str, max_length: int = 40) -> str:
    """Convert text to a URL/filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_length].rstrip("-")


def generate_slug(
    commits: list[dict],
    cli_entries: list[dict],
    teams_data: list[dict],
    label: str | None = None,
) -> str:
    """Generate a meaningful slug from session activity.

    Priority:
    1. User-provided label
    2. Most common commit type + scope keywords
    3. Fallback to "session"
    """
    if label:
        return _slugify(label)

    if not commits:
        if teams_data:
            return _slugify(teams_data[0].get("name", "team-session"))
        return "session"

    # Extract commit type prefixes and meaningful words
    type_counts: Counter[str] = Counter()
    words: Counter[str] = Counter()
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "to",
        "in",
        "of",
        "with",
        "on",
        "at",
        "by",
        "from",
        "is",
        "it",
        "as",
        "be",
        "was",
        "are",
    }

    for commit in commits:
        msg = commit["message"]
        # Parse conventional commit prefix: "feat: add X" or "feat(scope): add X"
        match = re.match(r"^(\w+)(?:\(([^)]+)\))?:\s*(.+)", msg)
        if match:
            commit_type, scope, description = match.groups()
            if commit_type in COMMIT_TYPE_CATEGORIES:
                type_counts[commit_type] += 1
            if scope:
                words[scope.lower()] += 2  # Scope gets extra weight
            msg = description

        # Extract keywords from message
        for word in re.findall(r"[a-zA-Z]{3,}", msg):
            word_lower = word.lower()
            if word_lower not in stop_words:
                words[word_lower] += 1

    # Build slug from most common type + top keywords
    parts: list[str] = []

    if type_counts:
        top_type = type_counts.most_common(1)[0][0]
        parts.append(COMMIT_TYPE_CATEGORIES.get(top_type, top_type))

    if words:
        top_words = [w for w, _ in words.most_common(3)]
        parts.extend(top_words)

    if not parts:
        return "session"

    return _slugify("-".join(parts))


def extract_tags(
    commits: list[dict],
    file_changes: dict[str, list[str]],
    cli_entries: list[dict],
    teams_data: list[dict],
) -> list[str]:
    """Extract semantic tags from session activity for searchability."""
    tags: set[str] = set()

    # From commit types
    for commit in commits:
        match = re.match(r"^(\w+)(?:\([^)]+\))?:", commit["message"])
        if match:
            commit_type = match.group(1)
            category = COMMIT_TYPE_CATEGORIES.get(commit_type)
            if category:
                tags.add(category)

    # From file paths — extract top-level directories
    all_files = file_changes.get("created", []) + file_changes.get("modified", [])
    for filepath in all_files:
        parts = filepath.split("/")
        if len(parts) > 1:
            tags.add(parts[0])
        # Detect test files
        if "test" in filepath.lower():
            tags.add("testing")
        # Detect skill/hook changes
        if "skills/" in filepath:
            tags.add("skills")
        if "hooks/" in filepath:
            tags.add("hooks")

    # From CLI usage
    if any(e.get("tool") == "codex" for e in cli_entries):
        tags.add("codex")
    if any(e.get("tool") == "gemini" for e in cli_entries):
        tags.add("gemini")

    # From Agent Teams
    if teams_data:
        tags.add("agent-teams")
        for team in teams_data:
            tags.add(f"team:{team['name']}")

    return sorted(tags)


def generate_frontmatter(
    timestamp: str,
    slug: str,
    branch: str,
    tags: list[str],
    commits: list[dict],
    file_changes: dict[str, list[str]],
    cli_entries: list[dict],
    teams_data: list[dict],
    since: str | None,
) -> str:
    """Generate YAML frontmatter for quick scanning by Claude Code.

    Claude can read the first ~20 lines to decide if a checkpoint is relevant
    without parsing the entire file.
    """
    codex_count = sum(1 for e in cli_entries if e.get("tool") == "codex")
    gemini_count = sum(1 for e in cli_entries if e.get("tool") == "gemini")
    total_files = sum(len(v) for v in file_changes.values())

    # Build one-line summary from top commit messages
    summary_parts: list[str] = []
    for commit in commits[:3]:
        msg = commit["message"]
        match = re.match(r"^\w+(?:\([^)]+\))?:\s*(.+)", msg)
        summary_parts.append(match.group(1) if match else msg)
    summary = "; ".join(summary_parts) if summary_parts else "no commits"

    lines = [
        "---",
        f"id: {slug}-{timestamp}",
        f"timestamp: {timestamp}",
        f"branch: {branch}",
        f"slug: {slug}",
        f'summary: "{summary}"',
        f"tags: [{', '.join(tags)}]",
        f"commits: {len(commits)}",
        f"files_changed: {total_files}",
        f"codex_consultations: {codex_count}",
        f"gemini_researches: {gemini_count}",
        f"agent_teams: {len(teams_data)}",
    ]
    if since:
        lines.append(f"since: {since}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def update_index(
    checkpoint_filename: str,
    timestamp: str,
    slug: str,
    branch: str,
    tags: list[str],
    commits: list[dict],
    file_changes: dict[str, list[str]],
    cli_entries: list[dict],
    teams_data: list[dict],
) -> None:
    """Update INDEX.md catalog with a new checkpoint entry.

    INDEX.md is a single file Claude Code reads to find relevant checkpoints.
    Format: table rows sorted newest-first, with tags and summary for search.
    """
    codex_count = sum(1 for e in cli_entries if e.get("tool") == "codex")
    gemini_count = sum(1 for e in cli_entries if e.get("tool") == "gemini")
    total_files = sum(len(v) for v in file_changes.values())

    # Build summary from top commit messages
    summary_parts: list[str] = []
    for commit in commits[:2]:
        msg = commit["message"]
        match = re.match(r"^\w+(?:\([^)]+\))?:\s*(.+)", msg)
        summary_parts.append(match.group(1) if match else msg)
    summary = "; ".join(summary_parts) if summary_parts else "no commits"
    # Truncate for table readability
    if len(summary) > 60:
        summary = summary[:57] + "..."

    tag_str = ", ".join(tags[:5])
    stats = f"{len(commits)}c/{total_files}f"
    if codex_count:
        stats += f"/{codex_count}cx"
    if gemini_count:
        stats += f"/{gemini_count}gm"
    if teams_data:
        stats += f"/{len(teams_data)}tm"

    new_row = (
        f"| {timestamp} | [{slug}]({checkpoint_filename}) "
        f"| {branch} | {tag_str} | {stats} | {summary} |"
    )

    if INDEX_FILE.exists():
        content = INDEX_FILE.read_text(encoding="utf-8")
        # Insert new row right after the header separator line
        table_sep = "|---|---|---|---|---|---|"
        if table_sep in content:
            content = content.replace(table_sep, f"{table_sep}\n{new_row}", 1)
        else:
            # Corrupted or missing table — rebuild header + row
            content = _build_index_header() + new_row + "\n"
    else:
        content = _build_index_header() + new_row + "\n"

    INDEX_FILE.write_text(content, encoding="utf-8")


def _build_index_header() -> str:
    """Build the INDEX.md header with table structure."""
    return (
        "# Checkpoint Index\n"
        "\n"
        "Quick-reference catalog of all checkpoints. "
        "Read this file to find the right checkpoint without scanning every file.\n"
        "\n"
        "**Stats format**: `{commits}c/{files}f/{codex}cx/{gemini}gm/{teams}tm`\n"
        "\n"
        "| Timestamp | Checkpoint | Branch | Tags | Stats | Summary |\n"
        "|---|---|---|---|---|---|\n"
    )


# ---------------------------------------------------------------------------
# Checkpoint generation
# ---------------------------------------------------------------------------


def generate_checkpoint(
    commits: list[dict],
    file_changes: dict[str, list[str]],
    file_stats: dict[str, tuple[int, int]],
    cli_entries: list[dict],
    teams_data: list[dict],
    design_diff: str | None,
    branch: str,
    since: str | None,
) -> str:
    """Generate full checkpoint markdown content."""
    now = datetime.now(UTC)
    lines: list[str] = []

    # Header
    lines.append(f"# Checkpoint: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append("")

    # Summary
    codex_count = sum(1 for e in cli_entries if e.get("tool") == "codex")
    gemini_count = sum(1 for e in cli_entries if e.get("tool") == "gemini")
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
    lines.append(f"- **Gemini researches**: {gemini_count}")
    if teams_data:
        total_members = sum(len(t.get("members", [])) for t in teams_data)
        lines.append(
            f"- **Agent Teams sessions**: {len(teams_data)} ({total_members} teammates)"
        )
        lines.append(f"- **Tasks**: {completed_tasks}/{total_tasks} completed")
    if since:
        lines.append(f"- **Since**: {since}")
    lines.append("")

    # Git History
    lines.append("## Git History")
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
    gemini_entries = [e for e in cli_entries if e.get("tool") == "gemini"]

    for entries, name in [(codex_entries, "Codex"), (gemini_entries, "Gemini")]:
        if entries:
            lines.append(
                f"### {name} ({len(entries)} {'consultations' if name == 'Codex' else 'researches'})"
            )
            lines.append("")
            for entry in entries[:15]:
                status = "✓" if entry.get("success", False) else "✗"
                prompt = entry.get("prompt", "")[:100].replace("\n", " ")
                lines.append(f"- {status} {prompt}...")
            if len(entries) > 15:
                lines.append(f"- ... and {len(entries) - 15} more")
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

    # Design Decisions
    if design_diff:
        lines.append("## Design Decisions (Changes)")
        lines.append("")

        # Extract added lines from diff
        added_lines = [
            line[1:].strip()
            for line in design_diff.split("\n")
            if line.startswith("+")
            and not line.startswith("+++")
            and line.strip() not in ("+", "")
        ]
        for added in added_lines[:20]:
            lines.append(f"- {added}")
        lines.append("")

    # Footer
    timestamp = now.strftime("%Y-%m-%d-%H%M%S")
    lines.append("---")
    lines.append(f"*Generated by checkpointing skill at {timestamp}*")

    return "\n".join(lines)


def generate_session_summary(
    commits: list[dict],
    file_changes: dict[str, list[str]],
    cli_entries: list[dict],
    teams_data: list[dict],
) -> str:
    """Generate concise session summary for CLAUDE.md."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    total_files = sum(len(v) for v in file_changes.values())
    codex_count = sum(1 for e in cli_entries if e.get("tool") == "codex")
    gemini_count = sum(1 for e in cli_entries if e.get("tool") == "gemini")

    summary_lines = [f"### {today}", ""]
    summary_lines.append(f"- {len(commits)} commits, {total_files} files changed")

    if codex_count:
        summary_lines.append(f"- Codex: {codex_count} consultations")
    if gemini_count:
        summary_lines.append(f"- Gemini: {gemini_count} researches")

    for team in teams_data:
        tasks = team.get("tasks", [])
        members = team.get("members", [])
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        summary_lines.append(
            f"- Agent Teams: {team['name']} "
            f"({len(members)} teammates, {completed}/{len(tasks)} tasks)"
        )

    summary_lines.append("")
    return "\n".join(summary_lines)


def update_claude_md(session_summary: str) -> bool:
    """Update CLAUDE.md with session history summary."""
    if not CLAUDE_MD.exists():
        return False

    content = CLAUDE_MD.read_text(encoding="utf-8")

    if SESSION_HISTORY_HEADER in content:
        # Append to existing section
        content = content.rstrip() + "\n\n" + session_summary
    else:
        # Create new section
        content = (
            content.rstrip()
            + "\n\n"
            + SESSION_HISTORY_HEADER
            + "\n\n"
            + session_summary
        )

    CLAUDE_MD.write_text(content, encoding="utf-8")
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
   - startproject, team-implement, team-review, plan, tdd, simplify
   - codex-system, gemini-system, design-tracker, checkpointing
   - research-lib, update-design, update-lib-docs, init
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
        "--label",
        help="Custom label for the checkpoint (used in filename and slug)",
    )
    args = parser.parse_args()

    print("Collecting session data...")

    # 1. Collect everything
    branch = get_git_branch()
    commits = get_git_commits(args.since)
    file_changes = get_file_changes(args.since)
    file_stats = get_file_stats(args.since)
    cli_entries = parse_cli_logs(args.since)
    teams_data = collect_agent_teams_data()
    design_diff = get_design_decisions_diff(args.since)

    print(
        f"  Git: {len(commits)} commits, {sum(len(v) for v in file_changes.values())} files"
    )
    print(f"  CLI: {len(cli_entries)} consultations")
    print(f"  Agent Teams: {len(teams_data)} teams")

    # 2. Generate slug and tags for meaningful naming
    slug = generate_slug(
        commits=commits,
        cli_entries=cli_entries,
        teams_data=teams_data,
        label=args.label,
    )
    tags = extract_tags(
        commits=commits,
        file_changes=file_changes,
        cli_entries=cli_entries,
        teams_data=teams_data,
    )
    print(f"  Slug: {slug}")
    print(f"  Tags: {', '.join(tags)}")

    # 3. Generate checkpoint with frontmatter
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    checkpoint_filename = f"{timestamp}-{slug}.md"
    checkpoint_file = CHECKPOINTS_DIR / checkpoint_filename

    frontmatter = generate_frontmatter(
        timestamp=timestamp,
        slug=slug,
        branch=branch,
        tags=tags,
        commits=commits,
        file_changes=file_changes,
        cli_entries=cli_entries,
        teams_data=teams_data,
        since=args.since,
    )

    checkpoint_body = generate_checkpoint(
        commits=commits,
        file_changes=file_changes,
        file_stats=file_stats,
        cli_entries=cli_entries,
        teams_data=teams_data,
        design_diff=design_diff,
        branch=branch,
        since=args.since,
    )
    checkpoint_content = frontmatter + checkpoint_body
    checkpoint_file.write_text(checkpoint_content, encoding="utf-8")
    print(f"\nCheckpoint: {checkpoint_file}")

    # 4. Update INDEX.md catalog
    update_index(
        checkpoint_filename=checkpoint_filename,
        timestamp=timestamp,
        slug=slug,
        branch=branch,
        tags=tags,
        commits=commits,
        file_changes=file_changes,
        cli_entries=cli_entries,
        teams_data=teams_data,
    )
    print(f"Index: {INDEX_FILE}")

    # 5. Update CLAUDE.md
    session_summary = generate_session_summary(
        commits=commits,
        file_changes=file_changes,
        cli_entries=cli_entries,
        teams_data=teams_data,
    )
    if update_claude_md(session_summary):
        print(f"Session history: {CLAUDE_MD}")

    # 6. Generate skill analysis prompt
    prompt = generate_skill_analysis_prompt(checkpoint_content)
    prompt_file = checkpoint_file.with_suffix(".analyze-prompt.md")
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"Analysis prompt: {prompt_file}")

    print("\nDone. Next: spawn subagent to analyze the prompt file for skill patterns.")


if __name__ == "__main__":
    main()
