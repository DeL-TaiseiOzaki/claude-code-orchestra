#!/usr/bin/env python3
"""Inventory ``.agents/docs/libraries/`` metadata and cross-check dependencies.

Scans every ``*.md`` file in ``.agents/docs/libraries/`` for its title and the
``> **Last Updated**: ...`` / ``> **Version Checked**: ...`` metadata lines
written by the ``update-lib-docs`` skill, computes staleness, and cross
references declared dependencies from ``pyproject.toml`` and ``package.json``
to report which libraries have no documentation file at all.

Usage:
    python3 lib_inventory.py
    python3 lib_inventory.py --stale-days 60 --today 2026-07-21

Exit codes:
    0  scan completed (an empty or absent libraries dir is a valid state)
    1  bad args (e.g. --today not in YYYY-MM-DD format)
"""

import argparse
import json
import re
import sys
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

DEFAULT_STALE_DAYS = 90

EXIT_OK = 0
EXIT_BAD_INPUT = 1

# Metadata lines written by the update-lib-docs skill, e.g.:
#   > **Last Updated**: 2026-01-15
#   > **Version Checked**: 1.4.0
LAST_UPDATED_RE = re.compile(r"^>\s*\*\*Last Updated\*\*:\s*(.+?)\s*$", re.MULTILINE)
VERSION_CHECKED_RE = re.compile(
    r"^>\s*\*\*Version Checked\*\*:\s*(.+?)\s*$", re.MULTILINE
)

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d")

# A bare package name, stopping before extras (`[...]`), version specifiers
# (`>=`, `==`, ...), or environment markers (`;`).
PACKAGE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_INPUT)


def _rel_posix(path: Path, root: Path) -> str:
    """Render *path* as a POSIX-style string relative to *root*."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _parse_date(value: str) -> date | None:
    """Parse *value* as an ISO or ``YYYY/MM/DD`` date; None if neither fits."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_today_arg(value: str) -> date | None:
    """Parse the strict ``--today YYYY-MM-DD`` override."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _extract_match(pattern: re.Pattern[str], text: str) -> str | None:
    """Return the first captured group of *pattern* in *text*, stripped."""
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _extract_title(text: str, fallback: str) -> str:
    """Return the first ``# `` (H1) heading text, else *fallback*."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def normalize_dep_name(raw: str) -> str:
    """Normalize a dependency name for cross-ecosystem matching.

    Lowercases, maps underscores to hyphens, strips PEP 508 extras/version
    specifiers/environment markers, and collapses an npm scope
    (``@scope/pkg`` -> ``pkg``).
    """
    name = raw.strip()
    if name.startswith("@") and "/" in name:
        name = name.split("/", 1)[1]
    name = name.split(";", 1)[
        0
    ]  # drop environment markers, e.g. "; python_version<..."
    match = PACKAGE_NAME_RE.match(name)
    name = match.group(0) if match else name
    return name.lower().replace("_", "-")


def scan_library(path: Path, today: date, stale_days: int) -> dict:
    """Build the inventory entry for one library doc file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""

    last_updated = _parse_date(_extract_match(LAST_UPDATED_RE, text) or "")
    version_checked = _extract_match(VERSION_CHECKED_RE, text)
    age_days = (today - last_updated).days if last_updated else None
    stale = age_days is not None and age_days > stale_days

    return {
        "file": path.name,
        "name": _extract_title(text, path.stem),
        "last_updated": last_updated.isoformat() if last_updated else None,
        "version_checked": version_checked,
        "age_days": age_days,
        "stale": stale,
        "has_metadata": last_updated is not None or version_checked is not None,
    }


def _pyproject_dep_strings(path: Path) -> list[str]:
    """Return raw PEP 508 strings from [project] dependencies + optional-dependencies."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return []
    project = data.get("project")
    if not isinstance(project, dict):
        return []

    deps: list[str] = [d for d in project.get("dependencies", []) if isinstance(d, str)]
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group in optional.values():
            if isinstance(group, list):
                deps.extend(d for d in group if isinstance(d, str))
    return deps


def _package_json_dep_names(path: Path) -> list[str]:
    """Return raw dependency names (keys) from dependencies + devDependencies."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []

    names: list[str] = []
    for key in ("dependencies", "devDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            names.extend(str(name) for name in section)
    return names


def build_report(root: Path, stale_days: int, today: date) -> dict:
    """Assemble the full lib_inventory.py JSON report."""
    libraries_dir = root / ".agents" / "docs" / "libraries"
    entries = (
        [scan_library(p, today, stale_days) for p in sorted(libraries_dir.glob("*.md"))]
        if libraries_dir.is_dir()
        else []
    )
    documented_stems = {normalize_dep_name(Path(e["file"]).stem) for e in entries}

    raw_deps: list[str] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        raw_deps.extend(_pyproject_dep_strings(pyproject))
    package_json = root / "package.json"
    if package_json.is_file():
        raw_deps.extend(_package_json_dep_names(package_json))

    declared = sorted(
        {normalize_dep_name(d) for d in raw_deps if normalize_dep_name(d)}
    )
    undocumented = [d for d in declared if d not in documented_stems]

    counts = {
        "total": len(entries),
        "stale": sum(1 for e in entries if e["stale"]),
        "missing_metadata": sum(1 for e in entries if not e["has_metadata"]),
    }

    return {
        "ok": True,
        "libraries_dir": _rel_posix(libraries_dir, root),
        "stale_days": stale_days,
        "libraries": entries,
        "counts": counts,
        "undocumented": undocumented,
        "declared_dependencies": declared,
    }


def main() -> int:
    parser = JsonArgumentParser(
        description="Inventory .agents/docs/libraries/ metadata (JSON to stdout)",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    parser.add_argument(
        "--today",
        default=None,
        help="Override the clock for deterministic tests (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    if args.today is not None:
        today = _parse_today_arg(args.today)
        if today is None:
            _emit(
                {
                    "ok": False,
                    "error": f"--today must be YYYY-MM-DD, got {args.today!r}",
                }
            )
            return EXIT_BAD_INPUT
    else:
        today = datetime.now(tz=UTC).date()

    report = build_report(args.project_root, args.stale_days, today)
    _emit(report)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
