#!/usr/bin/env python3
"""Collect repository state for the catchup skill's Phase 1 scan.

Aggregates git state, project identity and current-work blocks, rules /
skills / agents frontmatter, design decisions, research & library notes,
environment commands, checkpoints, Agent Teams sessions, and CLI-log topics
into a single JSON document on stdout. Phase 2 synthesises ``GUIDE.md`` from
this JSON alone, so the collector gathers **every** dataset
``references/guide-template.md`` asks for; anything it cannot gather is named
as an error rather than rendered as an empty string.

Graceful degradation applies only to genuinely optional paths: an absent file
is ``{"present": false}``, while an unreadable one carries an ``error``. A git
subcommand that fails inside a real repository is ``null`` plus an entry in
``git.errors`` — never an empty list that reads as "clean tree".

Usage:
    python3 collect_repo_state.py
    python3 collect_repo_state.py --since "30 days ago" --max-commits 100
    python3 collect_repo_state.py --project-root /path/to/repo

Exit codes:
    0  ok (optional paths may legitimately be absent; that is reported)
    1  bad arguments
    2  the project root is not a git repository, or a SKILL.md / agent
       frontmatter yields neither a name nor a description
    3  a git subcommand failed inside a directory that *is* a git repository
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DEFAULT_SINCE = "30 days ago"
DEFAULT_MAX_COMMITS = 100
DEFAULT_CLAUDE_HOME = Path.home() / ".claude"
CHECKPOINT_PREVIEW = 5
CLI_LOG_TAIL = 50
FIRST_LINE_LIMIT = 200
GIT_TIMEOUT_SECONDS = 30
MAX_KEY_DECISIONS = 10
MAX_ENV_COMMANDS = 20

CHECKPOINT_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}$")
DESIGN_PLACEHOLDER_HEADING_MARKER = "Background & Purpose"
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
KEY_DECISIONS_HEADING = "## Key Decisions"
STATE_BLOCK_HEADINGS = {
    "current_project": "## Current Project",
    "current_feature": "## Current Feature",
    "current_bug_fix": "## Current Bug Fix",
}
FENCE_RE = re.compile(r"^```+\s*([A-Za-z0-9_+-]*)\s*$")
SHELL_FENCE_LANGUAGES = {"", "bash", "sh", "shell", "zsh", "console"}
# Command leaders worth reporting as setup/lint/test/run commands. Membership is
# how a line qualifies: the collector reports commands it *found*, with their
# source file, and never infers a command the repository does not spell out.
COMMAND_LEADERS = {
    "uv",
    "uvx",
    "pip",
    "python",
    "python3",
    "pytest",
    "ruff",
    "ty",
    "mypy",
    "make",
    "just",
    "npm",
    "pnpm",
    "yarn",
    "node",
    "docker",
    "cargo",
    "go",
    "bash",
    "sh",
    "task",
    "tox",
    "nox",
    "poetry",
    "hatch",
}

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_CONTRACT_VIOLATION = 2
EXIT_EXTERNAL_FAILURE = 3


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable and keeps exit 1
    meaning "bad arguments" only, distinct from exit 2 ("not a git
    repository")."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message, "artifacts": []})
        sys.exit(EXIT_BAD_ARGS)


# --- reading -----------------------------------------------------------------


def read_text(path: Path) -> tuple[str | None, str | None]:
    """Return (text, error). Both None means the file is absent."""
    if not path.exists():
        return None, None
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read {path.name}: {exc}"


def file_info(path: Path) -> dict:
    """Presence, first non-empty line, and error as three distinct states.

    An absent file, an unreadable one, and one whose content is blank used to
    collapse into the same ``None``; downstream that reads as "nothing here".
    """
    text, error = read_text(path)
    if error is not None:
        return {"present": True, "first_line": None, "error": error}
    if text is None:
        return {"present": False, "first_line": None, "error": None}
    for line in text.splitlines():
        if line.strip():
            return {
                "present": True,
                "first_line": line.strip()[:FIRST_LINE_LIMIT],
                "error": None,
            }
    return {"present": True, "first_line": "", "error": None}


# --- git ---------------------------------------------------------------------


def run_git(root: Path, args: list[str]) -> tuple[str | None, str | None]:
    """Run a git command from *root*; return (stdout, error)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, f"git {args[0]} timed out"
    except (FileNotFoundError, OSError) as exc:
        return None, f"git {args[0]} could not run: {exc}"
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        return None, (
            f"git {' '.join(args[:2])} exited {result.returncode}: "
            f"{detail[0] if detail else 'no stderr'}"
        )
    return result.stdout.strip(), None


def is_git_repo(root: Path) -> bool:
    """Return True when *root* is inside a git work tree."""
    output, _ = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    return output == "true"


def _lines(text: str | None) -> list[str] | None:
    """Split git output into non-empty lines; None stays None (command failed)."""
    if text is None:
        return None
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def collect_git(root: Path, since: str, max_commits: int) -> dict:
    """Collect git log/branches/status/stash/diffstat with per-command errors."""
    commands = {
        "log": ["log", "--oneline", "-n", str(max_commits)],
        "branches": ["branch", "-a"],
        "status": ["status", "--short"],
        "stash": ["stash", "list"],
        "diffstat": ["diff", "HEAD", "--stat"],
    }
    git: dict = {"errors": []}
    for key, args in commands.items():
        output, error = run_git(root, args)
        git[key] = _lines(output)
        if error:
            git["errors"].append(f"{key}: {error}")

    recent, error = run_git(root, ["log", f"--since={since}", "--stat", "--oneline"])
    git["recent_stat"] = recent
    if error:
        git["errors"].append(f"recent_stat: {error}")

    branch, error = run_git(root, ["branch", "--show-current"])
    git["current_branch"] = branch or None
    if error:
        git["errors"].append(f"current_branch: {error}")
    return git


# --- frontmatter -------------------------------------------------------------


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str | None]:
    """Extract YAML frontmatter, following one level of nesting.

    Two defects made every skill report an empty purpose: lines starting with
    whitespace were skipped, so ``metadata:`` → ``short-description:`` was
    unreachable, and ``.strip("|")`` gutted the ``description: |`` block scalar
    by discarding its marker *and* keeping nothing of the folded body. Nested
    keys are flattened as ``parent.child``; block and folded scalars are joined
    into one line.
    """
    text, error = read_text(path)
    if error is not None:
        return {}, error
    if text is None:
        return {}, f"{path.name} does not exist"
    if not text.startswith("---"):
        return {}, None

    fields: dict[str, str] = {}
    parent: str | None = None
    pending_key: str | None = None
    pending_lines: list[str] = []

    def flush() -> None:
        nonlocal pending_key, pending_lines
        if pending_key is not None:
            fields[pending_key] = " ".join(pending_lines).strip()
        pending_key, pending_lines = None, []

    for raw in text.splitlines()[1:]:
        if raw.strip() == "---":
            break
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()

        if pending_key is not None and indent > 0 and ":" not in stripped.split(" ")[0]:
            pending_lines.append(stripped)
            continue
        flush()

        if ":" not in stripped or stripped.startswith("-"):
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if indent == 0:
            parent = None
            full_key = key
        else:
            full_key = f"{parent}.{key}" if parent else key

        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            pending_key, pending_lines = full_key, []
            continue
        if not value:
            if indent == 0:
                parent = key
            continue
        fields[full_key] = value.strip('"').strip("'")

    flush()
    return fields, None


def _description(fields: dict[str, str]) -> str:
    """Best available human description: the short one, else the long one."""
    for key in ("metadata.short-description", "short-description", "description"):
        if fields.get(key):
            return fields[key].strip('"').strip("'")
    return ""


def collect_skills(root: Path, errors: list[str]) -> dict:
    """List skills with name + short-description, reporting parse failures."""
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return {"present": False, "items": [], "frontmatter_errors": []}
    items: list[dict] = []
    frontmatter_errors: list[str] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        fields, error = parse_frontmatter(skill_md)
        rel = skill_md.relative_to(root).as_posix()
        if error:
            frontmatter_errors.append(f"{rel}: {error}")
            continue
        name = fields.get("name", "")
        description = _description(fields)
        if not name and not description:
            frontmatter_errors.append(
                f"{rel}: frontmatter has neither name nor description"
            )
            continue
        items.append(
            {
                "name": name or skill_md.parent.name,
                "short_description": description,
                "file": rel,
            }
        )
    errors.extend(frontmatter_errors)
    return {
        "present": True,
        "items": items,
        "frontmatter_errors": frontmatter_errors,
    }


def collect_agents(root: Path, errors: list[str]) -> dict:
    """List agents with name + specialization, reporting parse failures."""
    agents_dir = root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return {"present": False, "items": [], "frontmatter_errors": []}
    items: list[dict] = []
    frontmatter_errors: list[str] = []
    for agent_md in sorted(agents_dir.glob("*.md")):
        fields, error = parse_frontmatter(agent_md)
        rel = agent_md.relative_to(root).as_posix()
        if error:
            frontmatter_errors.append(f"{rel}: {error}")
            continue
        name = fields.get("name", "")
        description = _description(fields)
        if not name and not description:
            frontmatter_errors.append(
                f"{rel}: frontmatter has neither name nor description"
            )
            continue
        items.append(
            {
                "name": name or agent_md.stem,
                "specialization": description,
                "model": fields.get("model", ""),
                "file": rel,
            }
        )
    errors.extend(frontmatter_errors)
    return {
        "present": True,
        "items": items,
        "frontmatter_errors": frontmatter_errors,
    }


# --- identity, docs, env -----------------------------------------------------


def _section_body(text: str, heading_prefix: str) -> str | None:
    """Body of the first top-level section whose heading starts with the prefix."""
    lines = text.splitlines()
    start: int | None = None
    for idx, line in enumerate(lines):
        if line.strip().startswith(heading_prefix):
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def collect_identity(root: Path) -> dict:
    """Presence + first line of the identity files, plus STATE.md work blocks."""
    identity: dict = {}
    for name in ("README.md", "AGENTS.md", "pyproject.toml"):
        identity[name] = file_info(root / name)

    state_path = root / ".claude" / "STATE.md"
    state_text, error = read_text(state_path)
    state: dict = {
        "present": state_text is not None,
        "path": ".claude/STATE.md",
        "error": error,
        "main_agent": None,
    }
    for key, heading in STATE_BLOCK_HEADINGS.items():
        state[key] = _section_body(state_text, heading) if state_text else None
    if state_text:
        main_agent = _section_body(state_text, "## Main Agent")
        if main_agent:
            body = [
                line.strip()
                for line in main_agent.splitlines()[1:]
                if line.strip() and not line.strip().startswith("<!--")
            ]
            state["main_agent"] = body[0] if body else None
    identity["state"] = state
    return identity


def _key_decisions(text: str) -> list[dict]:
    """Rows of the DESIGN.md ``## Key Decisions`` table, blank rows excluded."""
    body = _section_body(text, KEY_DECISIONS_HEADING)
    if body is None:
        return []
    rows: list[dict] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= set("|- :"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() == "decision" or not any(cells):
            continue
        rows.append(
            {
                "decision": cells[0],
                "rationale": cells[1] if len(cells) > 1 else "",
                "alternatives": cells[2] if len(cells) > 2 else "",
                "date": cells[3] if len(cells) > 3 else "",
            }
        )
    return rows[:MAX_KEY_DECISIONS]


def collect_docs(root: Path) -> dict:
    """DESIGN.md status + key decisions, and research / library note listings."""
    docs_dir = root / ".claude" / "docs"
    design_path = docs_dir / "DESIGN.md"
    text, error = read_text(design_path)
    design: dict = {
        "present": text is not None or error is not None,
        "error": error,
        "placeholder": None,
        "key_decisions": [],
    }
    if text is not None:
        body = _section_body(text, f"## {DESIGN_PLACEHOLDER_HEADING_MARKER}")
        if body is None:
            for line in text.splitlines():
                if line.startswith("## ") and DESIGN_PLACEHOLDER_HEADING_MARKER in line:
                    body = _section_body(text, line.strip())
                    break
        if body is not None:
            without_heading = "\n".join(body.splitlines()[1:])
            design["placeholder"] = (
                HTML_COMMENT_RE.sub("", without_heading).strip() == ""
            )
        design["key_decisions"] = _key_decisions(text)
    return {
        "design": design,
        "research": _doc_listing(docs_dir / "research"),
        "libraries": _doc_listing(docs_dir / "libraries"),
    }


def _doc_listing(directory: Path) -> dict:
    """List *.md files in a docs subdir with their first line."""
    if not directory.is_dir():
        return {"present": False, "items": []}
    return {
        "present": True,
        "items": [
            {"file": path.name, **file_info(path)}
            for path in sorted(directory.glob("*.md"))
        ],
    }


def _fenced_commands(text: str, source: str) -> list[dict]:
    """Commands found inside shell code fences, each tagged with its source."""
    found: list[dict] = []
    language: str | None = None
    for line in text.splitlines():
        fence = FENCE_RE.match(line.strip())
        if fence:
            language = None if language is not None else fence.group(1).lower()
            continue
        if language is None or language not in SHELL_FENCE_LANGUAGES:
            continue
        command = line.strip().lstrip("$").strip()
        if not command or command.startswith("#"):
            continue
        if command.split()[0] in COMMAND_LEADERS:
            found.append({"command": command, "source": source})
    return found


def collect_env(root: Path) -> dict:
    """Manifests, declared scripts, and documented commands — with provenance.

    Every entry names the file it came from. Nothing is inferred: a repository
    that documents no commands reports none rather than a plausible guess.
    """
    env: dict = {"manifests": [], "scripts": [], "commands": [], "errors": []}
    for name in ("pyproject.toml", "package.json", "Makefile", "justfile"):
        if (root / name).exists():
            env["manifests"].append(name)

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            env["errors"].append(f"cannot parse pyproject.toml: {exc}")
        else:
            for key, value in (data.get("project", {}).get("scripts") or {}).items():
                env["scripts"].append(
                    {"name": key, "entry_point": value, "source": "pyproject.toml"}
                )

    seen: set[str] = set()
    for name in ("README.md", "CONTRIBUTING.md"):
        text, error = read_text(root / name)
        if error:
            env["errors"].append(error)
            continue
        if text is None:
            continue
        for entry in _fenced_commands(text, name):
            if entry["command"] in seen:
                continue
            seen.add(entry["command"])
            env["commands"].append(entry)
    env["commands"] = env["commands"][:MAX_ENV_COMMANDS]
    return env


def collect_rules(root: Path) -> dict:
    """List rule files with their first line."""
    rules_dir = root / ".claude" / "rules"
    if not rules_dir.is_dir():
        return {"present": False, "items": []}
    return {
        "present": True,
        "items": [
            {"file": path.name, **file_info(path)}
            for path in sorted(rules_dir.glob("*.md"))
        ],
    }


# --- history -----------------------------------------------------------------


def collect_checkpoints(root: Path) -> dict:
    """Summarize the newest checkpoints (filename + first heading line)."""
    checkpoints_dir = root / ".claude" / "checkpoints"
    if not checkpoints_dir.is_dir():
        return {"present": False, "items": []}
    files = sorted(
        (p for p in checkpoints_dir.glob("*.md") if CHECKPOINT_STEM_RE.match(p.stem)),
        key=lambda p: p.stem,
        reverse=True,
    )
    return {
        "present": True,
        "items": [
            {"file": path.name, **file_info(path)}
            for path in files[:CHECKPOINT_PREVIEW]
        ],
    }


def collect_agent_teams(root: Path, claude_home: Path) -> dict:
    """Agent Teams sessions from {claude_home} plus in-repo teammate work logs."""
    teams: dict = {"sessions": [], "work_logs": [], "errors": []}

    teams_dir = claude_home / "teams"
    tasks_dir = claude_home / "tasks"
    if teams_dir.is_dir():
        for team_dir in sorted(teams_dir.iterdir()):
            if not team_dir.is_dir():
                continue
            session: dict = {
                "name": team_dir.name,
                "members": [],
                "tasks_total": 0,
                "tasks_completed": 0,
                "source": str(teams_dir),
            }
            config = team_dir / "config.json"
            if config.exists():
                try:
                    parsed = json.loads(config.read_text(encoding="utf-8"))
                    session["members"] = parsed.get("members", [])
                except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                    teams["errors"].append(f"{team_dir.name}/config.json: {exc}")
            task_dir = tasks_dir / team_dir.name
            if task_dir.is_dir():
                for task_file in sorted(task_dir.glob("*.json")):
                    try:
                        task = json.loads(task_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                        teams["errors"].append(f"{task_file.name}: {exc}")
                        continue
                    session["tasks_total"] += 1
                    if task.get("status") == "completed":
                        session["tasks_completed"] += 1
            teams["sessions"].append(session)

    logs_dir = root / ".claude" / "logs" / "agent-teams"
    if logs_dir.is_dir():
        for team_dir in sorted(logs_dir.iterdir()):
            if not team_dir.is_dir():
                continue
            for log in sorted(team_dir.glob("*.md")):
                teams["work_logs"].append(
                    {
                        "team": team_dir.name,
                        "teammate": log.stem,
                        "file": log.relative_to(root).as_posix(),
                        **file_info(log),
                    }
                )
    return teams


def collect_cli_tools(root: Path) -> dict:
    """Recent CLI-consultation topics from the JSONL log, all tools included."""
    log_file = root / ".claude" / "logs" / "cli-tools.jsonl"
    if not log_file.exists():
        return {"present": False, "items": [], "skipped_lines": 0, "error": None}
    text, error = read_text(log_file)
    if error is not None:
        return {"present": True, "items": [], "skipped_lines": 0, "error": error}
    assert text is not None

    items: list[dict] = []
    skipped = 0
    for line in text.splitlines()[-CLI_LOG_TAIL:]:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        items.append(
            {
                "tool": record.get("tool", "unknown"),
                "prompt": (record.get("prompt", "") or "")[:120],
                "success": record.get("success"),
            }
        )
    return {"present": True, "items": items, "skipped_lines": skipped, "error": None}


# --- assembly ----------------------------------------------------------------


def build_state(
    root: Path, since: str, max_commits: int, claude_home: Path
) -> tuple[dict, int]:
    """Assemble the repo-state document; return (state, exit_code)."""
    errors: list[str] = []
    repo = is_git_repo(root)
    git = collect_git(root, since, max_commits) if repo else None
    if not repo:
        errors.append(f"{root} is not a git repository")
    elif git and git["errors"]:
        errors.extend(f"git: {error}" for error in git["errors"])

    skills = collect_skills(root, errors)
    agents = collect_agents(root, errors)

    state = {
        "ok": not errors,
        "project_root": str(root),
        "git": git,
        "identity": collect_identity(root),
        "rules": collect_rules(root),
        "skills": skills,
        "agents": agents,
        "docs": collect_docs(root),
        "env": collect_env(root),
        "checkpoints": collect_checkpoints(root),
        "agent_teams": collect_agent_teams(root, claude_home),
        "cli_tools": collect_cli_tools(root),
        "errors": errors,
        "artifacts": [],
    }

    if not repo:
        return state, EXIT_CONTRACT_VIOLATION
    if skills["frontmatter_errors"] or agents["frontmatter_errors"]:
        return state, EXIT_CONTRACT_VIOLATION
    if git and git["errors"]:
        return state, EXIT_EXTERNAL_FAILURE
    return state, EXIT_OK


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Collect repository state for the catchup skill (JSON to stdout)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    parser.add_argument("--since", default=DEFAULT_SINCE)
    parser.add_argument("--max-commits", type=int, default=DEFAULT_MAX_COMMITS)
    parser.add_argument(
        "--claude-home",
        type=Path,
        default=DEFAULT_CLAUDE_HOME,
        help="Agent Teams data root (defaults to ~/.claude)",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.max_commits < 1:
        _build_parser().error("--max-commits must be >= 1")
    state, exit_code = build_state(
        args.project_root, args.since, args.max_commits, args.claude_home
    )
    _emit(state)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
