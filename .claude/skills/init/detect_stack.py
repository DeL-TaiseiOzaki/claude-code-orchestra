#!/usr/bin/env python3
"""Report stack *evidence* and agent-bootstrap integrity for /init.

This script deliberately does **not** infer commands, tools, or a stack.  It
reports which manifest and which key each fact came from and lets the agent
decide what belongs in DESIGN.md.  The two removed inferences are why: a bare
``if "ty" in text`` substring test turned a ``typing-extensions`` dependency
into a confident ``uv run ty check src/``, and a non-greedy
``dependencies\\s*=\\s*\\[(.*?)\\]`` regex stopped at the first ``]`` — the one
inside ``uvicorn[standard]`` — silently dropping every later dependency.  Both
landed in DESIGN.md as fact because a JSON field reads as authoritative.  A
script that guesses is worse than prose; manifests are parsed with ``tomllib`` /
``json`` by key instead.

An unreadable or malformed manifest is a ``warnings`` entry and never a
traceback, and ``evidence.unparsed_manifests`` keeps "present but not parsed"
distinguishable from "parsed and empty".

Usage:
    python3 detect_stack.py
    python3 detect_stack.py --project-root /path/to/repo

Exit codes:
    0  normal (read ``warnings`` — evidence may be partial)
    1  bad arguments, including a --project-root that is not a directory
    2  agent bootstrap or shared state is invalid; ``error`` names the markers
"""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_MARKERS_MISSING = 2

# PEP 508: the distribution name ends at the first extras bracket, version
# specifier, environment-marker semicolon, or whitespace.
REQUIREMENT_NAME_RE = re.compile(r"^([A-Za-z0-9._-]+)")


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable and never
    masquerades as this tool's own exit code 2 (agent bootstrap or shared
    state invalid)."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message, "artifacts": []})
        sys.exit(EXIT_BAD_ARGS)


# manifest filename -> (language, package_manager or None)
MANIFEST_LANGUAGES: dict[str, tuple[str, str | None]] = {
    "pyproject.toml": ("python", "uv"),
    "setup.py": ("python", "pip"),
    "requirements.txt": ("python", "pip"),
    "package.json": ("javascript", "npm"),
    "Cargo.toml": ("rust", "cargo"),
    "go.mod": ("go", "go"),
}
BUILD_MANIFESTS = ("Makefile", "Dockerfile")

# Manifests this script parses for dependency / tool / script evidence. Every
# other present manifest is listed under evidence.unparsed_manifests instead of
# being silently ignored.
PARSEABLE_MANIFESTS = ("pyproject.toml", "requirements.txt", "package.json")


class Evidence:
    """Accumulator for sourced facts and for the manifests that failed to parse."""

    def __init__(self) -> None:
        self.tools: list[dict] = []
        self.scripts: list[dict] = []
        self.dependencies: list[dict] = []
        self.ci: list[dict] = []
        self.parsed_manifests: list[str] = []
        self.unparsed_manifests: list[str] = []
        self.warnings: list[dict] = []

    def warn(self, manifest: str, error: str) -> None:
        self.warnings.append({"manifest": manifest, "error": error})

    def as_dict(self) -> dict:
        return {
            "parsed_manifests": self.parsed_manifests,
            "unparsed_manifests": self.unparsed_manifests,
            "tools": self.tools,
            "scripts": self.scripts,
            "dependencies": self.dependencies,
            "ci": self.ci,
        }


def detect_manifests(root: Path) -> dict[str, bool]:
    """Report presence of every known manifest / build file, present or not.

    Absent entries stay in the mapping as ``false`` so "checked and absent" is
    never mistaken for "never checked".
    """
    names = list(MANIFEST_LANGUAGES) + list(BUILD_MANIFESTS)
    return {name: (root / name).is_file() for name in names}


def detect_languages_and_managers(
    manifests: dict[str, bool],
) -> tuple[list[str], list[str]]:
    """Derive ordered, de-duplicated languages and package managers."""
    languages: list[str] = []
    managers: list[str] = []
    for name, (language, manager) in MANIFEST_LANGUAGES.items():
        if not manifests.get(name):
            continue
        if language not in languages:
            languages.append(language)
        if manager and manager not in managers:
            managers.append(manager)
    return languages, managers


def _read_text(path: Path) -> tuple[str | None, str | None]:
    """Read a text file; return (text, error_message). Never raises."""
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, f"unreadable: {exc.strerror or exc}"
    except UnicodeDecodeError as exc:
        return None, f"not valid UTF-8: {exc}"


def _requirement_name(spec: str) -> str | None:
    """Return the distribution name of a PEP 508 requirement string."""
    match = REQUIREMENT_NAME_RE.match(spec.strip())
    return match.group(1) if match else None


def _add_dependencies(
    evidence: Evidence, manifest: str, key: str, specs: object
) -> None:
    """Record every dependency spec under *key* with the name it declares."""
    if not isinstance(specs, list):
        evidence.warn(manifest, f"'{key}' is not a list")
        return
    for spec in specs:
        if not isinstance(spec, str):
            continue
        name = _requirement_name(spec)
        if not name:
            continue
        entry = {"name": name, "spec": spec.strip(), "manifest": manifest, "key": key}
        if entry not in evidence.dependencies:
            evidence.dependencies.append(entry)


def collect_pyproject(root: Path, evidence: Evidence) -> None:
    """Collect tool tables and dependency lists from pyproject.toml by key."""
    manifest = "pyproject.toml"
    path = root / manifest
    text, error = _read_text(path)
    if text is None:
        evidence.warn(manifest, error or "unreadable")
        return
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        evidence.warn(manifest, f"invalid TOML: {exc}")
        return
    evidence.parsed_manifests.append(manifest)

    tools = data.get("tool")
    if isinstance(tools, dict):
        for name in tools:
            evidence.tools.append(
                {"tool": name, "manifest": manifest, "key": f"tool.{name}"}
            )

    project = data.get("project")
    if isinstance(project, dict):
        if "dependencies" in project:
            _add_dependencies(
                evidence, manifest, "project.dependencies", project["dependencies"]
            )
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for group, specs in optional.items():
                _add_dependencies(
                    evidence,
                    manifest,
                    f"project.optional-dependencies.{group}",
                    specs,
                )

    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for group, specs in groups.items():
            _add_dependencies(evidence, manifest, f"dependency-groups.{group}", specs)


def collect_requirements_txt(root: Path, evidence: Evidence) -> None:
    """Collect dependency names from a requirements.txt, line by line."""
    manifest = "requirements.txt"
    text, error = _read_text(root / manifest)
    if text is None:
        evidence.warn(manifest, error or "unreadable")
        return
    evidence.parsed_manifests.append(manifest)
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        _add_dependencies(evidence, manifest, manifest, [line])


def collect_package_json(root: Path, evidence: Evidence) -> None:
    """Collect npm scripts (with their real command strings) and dependencies."""
    manifest = "package.json"
    text, error = _read_text(root / manifest)
    if text is None:
        evidence.warn(manifest, error or "unreadable")
        return
    try:
        data = json.loads(text)
    except ValueError as exc:
        evidence.warn(manifest, f"invalid JSON: {exc}")
        return
    if not isinstance(data, dict):
        evidence.warn(manifest, "top level is not an object")
        return
    evidence.parsed_manifests.append(manifest)

    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        for name, command in scripts.items():
            if isinstance(command, str):
                evidence.scripts.append(
                    {
                        "name": name,
                        "command": command,
                        "manifest": manifest,
                        "key": f"scripts.{name}",
                    }
                )
    for key in ("dependencies", "devDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            for name, spec in sorted(block.items()):
                evidence.dependencies.append(
                    {
                        "name": name,
                        "spec": spec if isinstance(spec, str) else "",
                        "manifest": manifest,
                        "key": f"{key}.{name}",
                    }
                )


COLLECTORS = {
    "pyproject.toml": collect_pyproject,
    "requirements.txt": collect_requirements_txt,
    "package.json": collect_package_json,
}


def collect_evidence(root: Path, manifests: dict[str, bool]) -> Evidence:
    """Parse every present, parseable manifest; name the ones left unparsed."""
    evidence = Evidence()
    for name in PARSEABLE_MANIFESTS:
        if manifests.get(name):
            COLLECTORS[name](root, evidence)
    for name, present in manifests.items():
        if present and name not in PARSEABLE_MANIFESTS:
            evidence.unparsed_manifests.append(name)
    evidence.ci.extend(detect_ci(root))
    return evidence


def detect_ci(root: Path) -> list[dict]:
    """Detect CI systems from well-known config paths, naming the path found."""
    candidates = (
        ("github-actions", ".github/workflows", True),
        ("gitlab-ci", ".gitlab-ci.yml", False),
        ("circleci", ".circleci", True),
    )
    found: list[dict] = []
    for system, rel, is_dir in candidates:
        path = root / rel
        if path.is_dir() if is_dir else path.is_file():
            found.append({"system": system, "path": rel})
    return found


def detect_agent_bootstrap(root: Path) -> tuple[dict[str, bool], list[str]]:
    """Verify the root bootstrap files, the native runtime directories, and
    shared state.

    This mirrors ``scripts/check.sh``: ``.claude/agents`` and ``.claude/skills``
    are real directories, and a missing one disables native auto-discovery
    entirely, so /init must not report success while either is absent.
    """
    agents_md = root / "AGENTS.md"
    claude_md = root / "CLAUDE.md"
    state_md = root / ".claude" / "STATE.md"
    state_text, _ = _read_text(state_md) if state_md.is_file() else (None, None)
    status = {
        "agents_md": agents_md.is_file() and not agents_md.is_symlink(),
        "claude_md": claude_md.is_file() and not claude_md.is_symlink(),
        "state_md": state_text is not None and "# Agent State" in state_text,
        "claude_agents_dir": _is_runtime_dir(root, "agents"),
        "claude_skills_dir": _is_runtime_dir(root, "skills"),
        "cli_subagent_contract": (root / ".agents" / "AGENTS.md").is_file(),
    }
    return status, [name for name, ok in status.items() if not ok]


def _is_runtime_dir(root: Path, name: str) -> bool:
    """True when .claude/<name> is a real directory, not a symlink."""
    path = root / ".claude" / name
    return path.is_dir() and not path.is_symlink()


def build_report(root: Path) -> tuple[dict, list[str]]:
    """Assemble the evidence report; return (report, failed_bootstrap_markers)."""
    manifests = detect_manifests(root)
    languages, managers = detect_languages_and_managers(manifests)
    evidence = collect_evidence(root, manifests)
    bootstrap, failed = detect_agent_bootstrap(root)
    report = {
        "ok": not failed,
        "languages": languages,
        "package_managers": managers,
        "manifests": manifests,
        "evidence": evidence.as_dict(),
        "agent_bootstrap": bootstrap,
        "warnings": evidence.warnings,
        "artifacts": [],
    }
    return report, failed


def main() -> int:
    parser = JsonArgumentParser(
        description="Report stack evidence + agent bootstrap integrity for /init",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    args = parser.parse_args()

    if not args.project_root.is_dir():
        _emit(
            {
                "ok": False,
                "error": f"'--project-root' is not a directory: {args.project_root}",
                "artifacts": [],
            }
        )
        return EXIT_BAD_ARGS

    report, failed = build_report(args.project_root)
    if failed:
        report["error"] = "invalid agent bootstrap marker(s): " + ", ".join(failed)
    _emit(report)
    return EXIT_OK if not failed else EXIT_MARKERS_MISSING


if __name__ == "__main__":
    sys.exit(main())
