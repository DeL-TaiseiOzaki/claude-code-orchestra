#!/usr/bin/env python3
"""Collect repository state for the catchup skill's Phase 1 scan.

Aggregates git state, project identity, rules/skills/agents frontmatter, design
& research docs, and local history (checkpoints, CLI logs) into a single JSON
document on stdout. The synthesis step (GUIDE.md) consumes this JSON; the
orchestrator never reads the raw files.

Graceful degradation: any missing path becomes null / "not present" and the
script still exits 0. Exit 1 only when the project root is not a git repository
(git section is null but the rest is still emitted).

Usage:
    python3 collect_repo_state.py
    python3 collect_repo_state.py --since "30 days ago" --max-commits 100

Exit codes:
    0  ok (including graceful degradation of missing paths)
    1  bad arguments, or the project root is not a git repository
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DEFAULT_SINCE = "30 days ago"
DEFAULT_MAX_COMMITS = 100
CHECKPOINT_PREVIEW = 5
CLI_LOG_TAIL = 50
FIRST_LINE_LIMIT = 200
GIT_TIMEOUT_SECONDS = 30
EXIT_BAD_ARGS = 1


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable and shares this
    tool's existing exit code 1 (also used when the project root is not a
    git repository) instead of argparse's own exit code 2."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_ARGS)


def run_git(root: Path, args: list[str]) -> str | None:
    """Run a git command from root; return stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def is_git_repo(root: Path) -> bool:
    """Return True when root is inside a git work tree."""
    return run_git(root, ["rev-parse", "--is-inside-work-tree"]) == "true"


def collect_git(root: Path, since: str, max_commits: int) -> dict | None:
    """Collect git log/branches/status/stash/diffstat, or None if not a repo."""
    if not is_git_repo(root):
        return None
    log = run_git(root, ["log", "--oneline", "-n", str(max_commits)])
    recent = run_git(root, ["log", f"--since={since}", "--stat", "--oneline"])
    branches = run_git(root, ["branch", "-a"])
    status = run_git(root, ["status", "--short"])
    stash = run_git(root, ["stash", "list"])
    diffstat = run_git(root, ["diff", "HEAD", "--stat"])
    return {
        "log": _lines(log),
        "recent_stat": recent or "",
        "branches": _lines(branches),
        "status": _lines(status),
        "stash": _lines(stash),
        "diffstat": _lines(diffstat),
    }


def _lines(text: str | None) -> list[str]:
    """Split git output into non-empty lines."""
    if not text:
        return []
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def first_line(path: Path) -> str | None:
    """Return the first non-empty line of a file, or None if absent/unreadable."""
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                return line.strip()[:FIRST_LINE_LIMIT]
    except OSError:
        return None
    return ""


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Extract a shallow YAML frontmatter block into a flat string dict."""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("|").strip()
    return fields


def collect_identity(root: Path) -> dict:
    """Report presence + first line of the key identity files."""
    identity: dict[str, object] = {}
    for name in ("README.md", "AGENTS.md", ".agents/STATE.md", "pyproject.toml"):
        path = root / name
        identity[name] = (
            {"present": True, "first_line": first_line(path)}
            if path.exists()
            else "not present"
        )
    return identity


def collect_rules(root: Path) -> list[dict] | str:
    """List rule files with their first line."""
    rules_dir = root / ".agents" / "rules"
    if not rules_dir.exists():
        return "not present"
    return [
        {"file": path.name, "first_line": first_line(path)}
        for path in sorted(rules_dir.glob("*.md"))
    ]


def collect_skills(root: Path) -> list[dict] | str:
    """List skills with name + short-description from frontmatter."""
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.exists():
        return "not present"
    skills: list[dict] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        fm = parse_frontmatter(skill_md)
        skills.append(
            {
                "name": fm.get("name", skill_md.parent.name),
                "short_description": fm.get("short-description", ""),
            }
        )
    return skills


def collect_agents(root: Path) -> list[dict] | str:
    """List agents with name + specialization (description) from frontmatter."""
    agents_dir = root / ".agents" / "agents"
    if not agents_dir.exists():
        return "not present"
    agents: list[dict] = []
    for agent_md in sorted(agents_dir.glob("*.md")):
        fm = parse_frontmatter(agent_md)
        agents.append(
            {
                "name": fm.get("name", agent_md.stem),
                "specialization": fm.get("description", ""),
            }
        )
    return agents


def collect_docs(root: Path) -> dict:
    """Report DESIGN.md presence + research/library note listings."""
    docs_dir = root / ".agents" / "docs"
    design = docs_dir / "DESIGN.md"
    return {
        "design_present": design.exists(),
        "research": _doc_listing(docs_dir / "research"),
        "libraries": _doc_listing(docs_dir / "libraries"),
    }


def _doc_listing(directory: Path) -> list[dict] | str:
    """List *.md files in a docs subdir with their first line."""
    if not directory.exists():
        return "not present"
    return [
        {"file": path.name, "first_line": first_line(path)}
        for path in sorted(directory.glob("*.md"))
    ]


def collect_checkpoints(root: Path) -> list[dict] | str:
    """Summarize the newest checkpoints (filename + first heading line)."""
    checkpoints_dir = root / ".agents" / "checkpoints"
    if not checkpoints_dir.exists():
        return "not present"
    files = sorted(
        (
            p
            for p in checkpoints_dir.glob("*.md")
            if not p.name.endswith(".analyze-prompt.md")
        ),
        key=lambda p: p.stem,
        reverse=True,
    )
    return [
        {"file": path.name, "summary": first_line(path)}
        for path in files[:CHECKPOINT_PREVIEW]
    ]


def collect_cli_tools(root: Path) -> list[dict] | str:
    """Extract recent Codex-topic entries from the CLI tools JSONL log."""
    log_file = root / ".agents" / "logs" / "cli-tools.jsonl"
    if not log_file.exists():
        return "not present"
    try:
        raw_lines = log_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "not present"
    entries: list[dict] = []
    for line in raw_lines[-CLI_LOG_TAIL:]:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("tool") == "codex":
            entries.append(
                {
                    "prompt": (record.get("prompt", "") or "")[:120],
                    "success": record.get("success"),
                }
            )
    return entries


def build_state(root: Path, since: str, max_commits: int) -> tuple[dict, bool]:
    """Assemble the full repo-state document; return (state, is_repo)."""
    git = collect_git(root, since, max_commits)
    state = {
        "git": git,
        "identity": collect_identity(root),
        "rules": collect_rules(root),
        "skills": collect_skills(root),
        "agents": collect_agents(root),
        "docs": collect_docs(root),
        "checkpoints": collect_checkpoints(root),
        "cli_tools": collect_cli_tools(root),
    }
    return state, git is not None


def main() -> int:
    parser = JsonArgumentParser(
        description="Collect repository state for the catchup skill (JSON to stdout)",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--since", default=DEFAULT_SINCE)
    parser.add_argument("--max-commits", type=int, default=DEFAULT_MAX_COMMITS)
    args = parser.parse_args()

    state, is_repo = build_state(args.project_root, args.since, args.max_commits)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0 if is_repo else EXIT_BAD_ARGS


if __name__ == "__main__":
    sys.exit(main())
