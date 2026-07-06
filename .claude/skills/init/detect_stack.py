#!/usr/bin/env python3
"""Detect tech stack, commands, and CLAUDE.md boundary markers for /init.

Scans manifest files to infer languages, package managers, common commands,
libraries, and CI, plus verifies the CLAUDE.md 3-zone boundary markers. Output
is a single JSON document on stdout that /init maps into DESIGN.md and Zone B.

Usage:
    python3 detect_stack.py
    python3 detect_stack.py --project-root /path/to/repo

Exit codes:
    0  normal
    2  CLAUDE.md boundary marker(s) missing (init must request ./scripts/update.sh)
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

TEMPLATE_BOUNDARY_MARKER = "@orchestra:template-boundary"
REPO_BOUNDARY_MARKER = "@orchestra:repo-boundary"
EXIT_MARKERS_MISSING = 2

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


def detect_manifests(root: Path) -> dict[str, bool]:
    """Report presence of each known manifest / build file."""
    names = list(MANIFEST_LANGUAGES) + list(BUILD_MANIFESTS)
    return {name: (root / name).exists() for name in names}


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


def detect_commands(root: Path) -> dict[str, str]:
    """Infer common lint/test/format commands from pyproject/package manifests."""
    commands: dict[str, str] = {}
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = _safe_read(pyproject)
        if "ruff" in text:
            commands["lint"] = "uv run ruff check ."
            commands["format"] = "uv run ruff format ."
        if "pytest" in text or "[tool.pytest" in text:
            commands["test"] = "uv run pytest"
        if "ty" in text:
            commands["typecheck"] = "uv run ty check src/"
    package_json = root / "package.json"
    if package_json.exists() and not commands:
        scripts = _npm_scripts(package_json)
        for key in ("lint", "test", "build"):
            if key in scripts:
                commands[key] = f"npm run {key}"
    return commands


def _npm_scripts(path: Path) -> dict[str, str]:
    """Return the "scripts" object from package.json, or empty on failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    scripts = data.get("scripts", {})
    return scripts if isinstance(scripts, dict) else {}


def detect_libraries(root: Path) -> list[str]:
    """Extract top-level dependency names (best effort) from manifests."""
    libraries: list[str] = []
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        libraries.extend(_pyproject_deps(pyproject))
    package_json = root / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            libraries.extend(sorted(data.get("dependencies", {}).keys()))
        except (OSError, ValueError):
            pass
    return libraries


def _pyproject_deps(path: Path) -> list[str]:
    """Parse dependency names from a pyproject.toml [project] dependencies list."""
    text = _safe_read(path)
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return []
    deps: list[str] = []
    for raw in match.group(1).split(","):
        item = raw.strip().strip('"').strip("'")
        if not item:
            continue
        name = re.split(r"[<>=!~\[ ]", item, maxsplit=1)[0].strip()
        if name:
            deps.append(name)
    return deps


def detect_ci(root: Path) -> list[str]:
    """Detect CI systems from well-known config paths."""
    ci: list[str] = []
    if (root / ".github" / "workflows").is_dir():
        ci.append("github-actions")
    if (root / ".gitlab-ci.yml").exists():
        ci.append("gitlab-ci")
    if (root / ".circleci").is_dir():
        ci.append("circleci")
    return ci


def detect_markers(root: Path) -> tuple[dict[str, bool], bool]:
    """Verify CLAUDE.md 3-zone boundary markers; return (markers, ok)."""
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        markers = {"template_boundary": False, "repo_boundary": False}
        return markers, False
    text = _safe_read(claude_md)
    markers = {
        "template_boundary": TEMPLATE_BOUNDARY_MARKER in text,
        "repo_boundary": REPO_BOUNDARY_MARKER in text,
    }
    return markers, markers["template_boundary"] and markers["repo_boundary"]


def _safe_read(path: Path) -> str:
    """Read a text file, returning empty string on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_report(root: Path) -> tuple[dict, bool]:
    """Assemble the detection report; return (report, markers_ok)."""
    manifests = detect_manifests(root)
    languages, managers = detect_languages_and_managers(manifests)
    markers, markers_ok = detect_markers(root)
    report = {
        "languages": languages,
        "package_managers": managers,
        "manifests": {name: present for name, present in manifests.items() if present},
        "commands": detect_commands(root),
        "libraries": detect_libraries(root),
        "ci": detect_ci(root),
        "claude_md_markers": markers,
    }
    return report, markers_ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect tech stack + CLAUDE.md markers for /init (JSON to stdout)",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    report, markers_ok = build_report(args.project_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if markers_ok else EXIT_MARKERS_MISSING


if __name__ == "__main__":
    sys.exit(main())
