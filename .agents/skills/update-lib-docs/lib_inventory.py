#!/usr/bin/env python3
"""Inventory ``.agents/docs/libraries/`` and cross-check declared dependencies.

Scans every ``*.md`` file in ``.agents/docs/libraries/`` for its title and the
``> **Last Updated**: ...`` / ``> **Version Checked**: ...`` metadata lines that
``research-lib``'s template emits, resolves the version this project actually
*declares* (``pyproject.toml`` / ``package.json``) and *locks* (``uv.lock`` /
``poetry.lock`` / ``package-lock.json``), and reports two independent staleness
signals: age and version drift.

Version drift compares the doc's ``Version Checked`` against the declared or
locked version, never against the latest upstream release — the upstream latest
is a research judgment, the project's own version has exactly one answer. A
verdict is only reported when it is certain: a comparison that cannot be decided
(non-numeric version, open-ended range with no lockfile) is ``version_drift:
null`` with a ``version_drift_note`` saying why, never a guess.

Broken states are reported, never smoothed away: an unreadable doc carries
``read_error``, a malformed manifest or lockfile lands in ``manifest_errors``,
and every dependency table actually parsed is listed in ``sources`` so an empty
``undocumented`` can never be mistaken for "everything is documented".

Usage:
    python3 lib_inventory.py
    python3 lib_inventory.py --stale-days 60 --today 2026-07-21
    python3 lib_inventory.py --library ruamel.yaml
    python3 lib_inventory.py --project-root /path/to/repo

Exit codes:
    0  scan completed (an empty or absent libraries dir is a valid state)
    1  bad args (--today not YYYY-MM-DD, --library not a package name,
       --project-root does not exist)
    2  a manifest or lockfile could not be parsed (see ``manifest_errors``)
    3  a library doc could not be read (see ``read_error``); takes precedence
       over 2 when both happen in one run
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
EXIT_CONTRACT = 2
EXIT_EXTERNAL = 3

# Metadata lines written by the research-lib / update-lib-docs template, e.g.:
#   > **Last Updated**: 2026-01-15
#   > **Version Checked**: 1.4.0
# This blockquote is the single canonical home of a library doc's version;
# validate_doc.py's `lib-doc` contract requires exactly these two lines.
LAST_UPDATED_RE = re.compile(r"^>\s*\*\*Last Updated\*\*:\s*(.+?)\s*$", re.MULTILINE)
VERSION_CHECKED_RE = re.compile(
    r"^>\s*\*\*Version Checked\*\*:\s*(.+?)\s*$", re.MULTILINE
)

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d")

# A bare package name, stopping before extras (`[...]`), version specifiers
# (`>=`, `==`, ...), or environment markers (`;`).
PACKAGE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")

# A normalized package name, as normalize_dep_name() produces it. Mirrors
# PACKAGE_SLUG_RE in _shared/workspace.py: --library is turned into a filename
# lookup, so a value that is not a package name (`///`, `../etc`) is rejected
# rather than joined onto a path.
NORMALIZED_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

# A plain numeric release, optionally `v`-prefixed: the only shape this script
# will order or compare. Anything else (`1.0rc1`, `2.0.0-beta.1`, `latest`)
# yields an explicit "unknown" verdict rather than a guessed one.
NUMERIC_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)$")

# One PEP 508 / npm comparison clause: an operator and a version.
SPEC_CLAUSE_RE = re.compile(r"^\s*(===|==|>=|<=|~=|!=|<|>|\^|~)?\s*(.+?)\s*$")

PYTHON = "python"
NODE = "node"


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

    ``.`` is deliberately preserved (``ruamel.yaml`` stays ``ruamel.yaml``);
    ``workspace.py``'s ``_package_slug`` mirrors this, and
    ``tests/test_slug_agreement.py`` pins the two together.
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


def split_dep_string(raw: str) -> tuple[str, str | None]:
    """Split a PEP 508 requirement into (normalized name, version spec).

    ``"Some_Package[extra]>=1.0; python_version<'3.12'"`` ->
    ``("some-package", ">=1.0")``. Extras and environment markers are dropped:
    they say *when* and *how* a dependency is installed, not which version.
    Returns ``None`` as the spec when the requirement pins nothing.
    """
    name = normalize_dep_name(raw)
    rest = raw.strip()
    if rest.startswith("@") and "/" in rest:
        rest = rest.split("/", 1)[1]
    rest = rest.split(";", 1)[0]
    match = PACKAGE_NAME_RE.match(rest)
    rest = rest[match.end() :] if match else ""
    if rest.lstrip().startswith("["):
        _, _, rest = rest.partition("]")
    spec = rest.strip()
    return name, spec or None


def _release(value: str | None) -> tuple[int, ...] | None:
    """Return the numeric release tuple of *value*, or None if it is not a
    plain numeric version this script is willing to compare."""
    if not value:
        return None
    match = NUMERIC_VERSION_RE.match(value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _pad(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[tuple, tuple]:
    """Zero-pad two release tuples to equal length so 1.4 == 1.4.0."""
    width = max(len(left), len(right))
    return (
        left + (0,) * (width - len(left)),
        right + (0,) * (width - len(right)),
    )


def _same_release(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    padded_left, padded_right = _pad(left, right)
    return padded_left == padded_right


def parse_spec(spec: str) -> dict:
    """Extract the decidable facts from a version spec.

    Returns ``{"pin": tuple|None, "lower": tuple|None, "lower_strict": bool}``.
    ``pin`` is set only by an exact equality (``==1.2.3``, or a bare npm
    version); ``lower`` by ``>=``/``>``/``~=``/``^``/``~``. Clauses this
    function cannot read are ignored rather than guessed at — an unreadable
    spec simply yields no facts, which surfaces downstream as
    ``version_drift: null``.
    """
    pin: tuple[int, ...] | None = None
    lower: tuple[int, ...] | None = None
    lower_strict = False

    for clause in spec.split(","):
        match = SPEC_CLAUSE_RE.match(clause)
        if not match:
            continue
        operator, raw_version = match.group(1), match.group(2)
        release = _release(raw_version)
        if release is None:
            continue
        if operator in (None, "==", "==="):
            pin = release
        elif operator in (">=", "~="):
            lower = release if lower is None else max(lower, release)
        elif operator == ">":
            lower = release if lower is None else max(lower, release)
            lower_strict = True
        elif operator in ("^", "~"):
            lower = release if lower is None else max(lower, release)

    return {"pin": pin, "lower": lower, "lower_strict": lower_strict}


def resolve_drift(
    version_checked: str | None,
    declared_spec: str | None,
    locked_version: str | None,
) -> tuple[bool | None, str | None, str | None]:
    """Decide whether a doc's ``Version Checked`` has drifted.

    Returns ``(drift, basis, note)`` where *drift* is True/False when the
    comparison is decidable and None when it is not. *basis* names what the
    verdict rests on so the caller can see which evidence was used.
    """
    if version_checked is None:
        return None, None, "doc has no '> **Version Checked**:' metadata line"

    checked = _release(version_checked)
    if checked is None:
        return (
            None,
            None,
            f"Version Checked {version_checked!r} is not a plain numeric "
            "version, so it cannot be compared",
        )

    locked = _release(locked_version)
    if locked is not None:
        return not _same_release(checked, locked), "locked_version", None
    if locked_version is not None:
        return (
            None,
            None,
            f"locked version {locked_version!r} is not a plain numeric version, "
            "so it cannot be compared",
        )

    if declared_spec is None:
        return None, None, "library is not a declared dependency of this project"

    facts = parse_spec(declared_spec)
    if facts["pin"] is not None:
        return not _same_release(checked, facts["pin"]), "pinned_spec", None
    if facts["lower"] is not None:
        padded_checked, padded_lower = _pad(checked, facts["lower"])
        below = (
            padded_checked <= padded_lower
            if facts["lower_strict"]
            else padded_checked < padded_lower
        )
        if below:
            return (
                True,
                "spec_lower_bound",
                f"documented version {version_checked} does not satisfy the "
                f"declared spec {declared_spec}",
            )
        return (
            None,
            "spec_lower_bound",
            f"declared spec {declared_spec} is an open range and no lockfile "
            "pins the resolved version",
        )
    return (
        None,
        None,
        f"declared spec {declared_spec!r} carries no comparable version",
    )


def scan_library(
    path: Path,
    today: date,
    stale_days: int,
    resolution: dict,
) -> dict:
    """Build the inventory entry for one library doc file.

    *resolution* maps a normalized dependency name to its declared/locked
    version facts, so the entry can report drift as well as age.
    """
    read_error: str | None = None
    text = ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # A doc that cannot be read is a broken state, not an absent optional
        # path: without read_error it would be indistinguishable from a doc
        # that merely lacks metadata, and would be reported "current".
        read_error = f"{type(exc).__name__}: {exc}"

    last_updated = _parse_date(_extract_match(LAST_UPDATED_RE, text) or "")
    version_checked = _extract_match(VERSION_CHECKED_RE, text)
    age_days = (today - last_updated).days if last_updated else None

    facts = resolution.get(normalize_dep_name(path.stem), {})
    declared_spec = facts.get("declared_spec")
    locked_version = facts.get("locked_version")

    drift, drift_basis, drift_note = resolve_drift(
        version_checked, declared_spec, locked_version
    )

    stale_reasons: list[str] = []
    if age_days is not None and age_days > stale_days:
        stale_reasons.append("age")
    if drift is True:
        stale_reasons.append("version_drift")

    return {
        "file": path.name,
        "name": _extract_title(text, path.stem),
        "last_updated": last_updated.isoformat() if last_updated else None,
        "version_checked": version_checked,
        "age_days": age_days,
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "has_metadata": last_updated is not None or version_checked is not None,
        "read_error": read_error,
        "declared_spec": declared_spec,
        "declared_in": facts.get("declared_in"),
        "locked_version": locked_version,
        "locked_in": facts.get("locked_in"),
        "ecosystem": facts.get("ecosystem"),
        "version_drift": drift,
        "version_drift_basis": drift_basis,
        "version_drift_note": drift_note,
    }


def _load_toml(path: Path) -> tuple[dict | None, str | None]:
    """Parse a TOML file into (data, error); exactly one is not None."""
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _load_json(path: Path) -> tuple[object | None, str | None]:
    """Parse a JSON file into (data, error); exactly one is not None."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _str_list(value: object) -> list[str]:
    """Keep only the string entries of *value* when it is a list."""
    return (
        [item for item in value if isinstance(item, str)]
        if isinstance(value, list)
        else []
    )


def _requirement_pairs(requirements: list[str]) -> list[tuple[str, str | None]]:
    """Split PEP 508 requirement strings into (normalized name, spec) pairs."""
    pairs = [split_dep_string(requirement) for requirement in requirements]
    return [(name, spec) for name, spec in pairs if name]


def _mapping_pairs(
    mapping: dict, skip: frozenset[str] = frozenset()
) -> list[tuple[str, str | None]]:
    """Turn a ``name = constraint`` mapping (Poetry, npm) into name/spec pairs.

    A non-string or wildcard constraint (Poetry's table form, ``"*"``) carries
    no comparable version, so the spec is ``None`` rather than an invented one.
    """
    pairs: list[tuple[str, str | None]] = []
    for raw_name, value in mapping.items():
        name = normalize_dep_name(str(raw_name))
        if not name or name in skip:
            continue
        spec = (
            value.strip() if isinstance(value, str) and value.strip() != "*" else None
        )
        pairs.append((name, spec or None))
    return pairs


DependencyTables = list[tuple[str, list[tuple[str, str | None]]]]


def _pyproject_tables(data: dict) -> DependencyTables:
    """Return (table label, name/spec pairs) for every Python dependency table
    this script understands: PEP 621, PEP 735 dependency groups, uv's
    dev-dependencies, and Poetry."""
    tables: DependencyTables = []

    def add(label: str, pairs: list[tuple[str, str | None]]) -> None:
        if pairs:
            tables.append((label, pairs))

    project = data.get("project")
    if isinstance(project, dict):
        add(
            "[project].dependencies",
            _requirement_pairs(_str_list(project.get("dependencies"))),
        )
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for group, entries in optional.items():
                add(
                    f"[project.optional-dependencies].{group}",
                    _requirement_pairs(_str_list(entries)),
                )

    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for group, entries in groups.items():
            add(
                f"[dependency-groups].{group}",
                _requirement_pairs(_str_list(entries)),
            )

    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    uv = tool.get("uv") if isinstance(tool.get("uv"), dict) else {}
    add(
        "[tool.uv].dev-dependencies",
        _requirement_pairs(_str_list(uv.get("dev-dependencies"))),
    )

    poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else {}
    for label, mapping in _poetry_mappings(poetry):
        # Poetry lists the interpreter itself as a dependency; it is not a
        # library and has no doc under .agents/docs/libraries/.
        add(label, _mapping_pairs(mapping, skip=frozenset({"python"})))
    return tables


def _poetry_mappings(poetry: dict) -> list[tuple[str, dict]]:
    """Locate Poetry's ``name = constraint`` dependency mappings."""
    candidates: list[tuple[str, object]] = [
        ("[tool.poetry.dependencies]", poetry.get("dependencies"))
    ]
    groups = poetry.get("group")
    if isinstance(groups, dict):
        for group, body in groups.items():
            if isinstance(body, dict):
                candidates.append(
                    (
                        f"[tool.poetry.group.{group}.dependencies]",
                        body.get("dependencies"),
                    )
                )
    return [
        (label, mapping) for label, mapping in candidates if isinstance(mapping, dict)
    ]


def _package_json_tables(data: object) -> DependencyTables:
    """Return (table label, name/spec pairs) for npm dependency tables."""
    if not isinstance(data, dict):
        return []
    tables: DependencyTables = []
    for key in ("dependencies", "devDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            pairs = _mapping_pairs(section)
            if pairs:
                tables.append((key, pairs))
    return tables


def _uv_lock_versions(data: dict) -> dict[str, str]:
    """Map normalized name -> version from a uv.lock / poetry.lock."""
    versions: dict[str, str] = {}
    packages = data.get("package")
    if isinstance(packages, list):
        for package in packages:
            if not isinstance(package, dict):
                continue
            name, version = package.get("name"), package.get("version")
            if isinstance(name, str) and isinstance(version, str):
                versions[normalize_dep_name(name)] = version
    return versions


def _package_lock_versions(data: object) -> dict[str, str]:
    """Map normalized name -> version from a package-lock.json (v1, v2, v3)."""
    if not isinstance(data, dict):
        return {}
    versions: dict[str, str] = {}
    packages = data.get("packages")
    if isinstance(packages, dict):
        for path_key, body in packages.items():
            if not isinstance(body, dict) or not path_key:
                continue
            version = body.get("version")
            name = body.get("name")
            if not isinstance(name, str):
                name = path_key.rsplit("node_modules/", 1)[-1]
            if isinstance(version, str) and name:
                versions[normalize_dep_name(name)] = version
    legacy = data.get("dependencies")
    if isinstance(legacy, dict):
        for name, body in legacy.items():
            if isinstance(body, dict) and isinstance(body.get("version"), str):
                versions.setdefault(normalize_dep_name(name), body["version"])
    return versions


MANIFESTS: tuple[tuple[str, str], ...] = (
    ("pyproject.toml", PYTHON),
    ("package.json", NODE),
)

LOCKFILES: tuple[tuple[str, str], ...] = (
    ("uv.lock", PYTHON),
    ("poetry.lock", PYTHON),
    ("package-lock.json", NODE),
)


def collect_dependencies(root: Path) -> dict:
    """Resolve declared and locked versions from every manifest and lockfile.

    Returns ``{"resolution": {...}, "sources": [...], "manifest_errors": [...],
    "warnings": [...]}``. A manifest that exists but cannot be parsed produces
    an error entry, never an empty dependency list — "the manifest is broken"
    and "the project has no dependencies" must not look alike.
    """
    resolution: dict[str, dict] = {}
    sources: list[dict] = []
    manifest_errors: list[dict] = []
    warnings: list[str] = []

    for filename, ecosystem in MANIFESTS:
        path = root / filename
        if not path.is_file():
            continue
        if ecosystem == PYTHON:
            data, error = _load_toml(path)
            tables = _pyproject_tables(data) if isinstance(data, dict) else []
        else:
            data, error = _load_json(path)
            tables = _package_json_tables(data)
        if error is not None:
            manifest_errors.append({"file": filename, "error": error})
            continue
        if not tables:
            warnings.append(
                f"{filename} declares no dependencies in any table this script "
                f"reads, so 'undocumented' cannot be trusted to be complete"
            )
        for label, pairs in tables:
            for name, declared_spec in pairs:
                resolution.setdefault(
                    name,
                    {
                        "name": name,
                        "declared_spec": declared_spec,
                        "declared_in": f"{filename} {label}",
                        "locked_version": None,
                        "locked_in": None,
                        "ecosystem": ecosystem,
                    },
                )
            sources.append(
                {
                    "file": filename,
                    "table": label,
                    "ecosystem": ecosystem,
                    "kind": "manifest",
                    "dependency_count": len(pairs),
                }
            )

    locked = _read_lockfiles(root, sources, manifest_errors)
    for name, entry in resolution.items():
        if name in locked:
            entry["locked_version"] = locked[name]["version"]
            entry["locked_in"] = locked[name]["file"]

    if resolution and not any(source["kind"] == "lock" for source in sources):
        warnings.append(
            "no lockfile found (uv.lock / poetry.lock / package-lock.json), so "
            "version_drift stays unknown for open-ended version ranges"
        )
    return {
        "resolution": resolution,
        "locked": locked,
        "sources": sources,
        "manifest_errors": manifest_errors,
        "warnings": warnings,
    }


def _read_lockfiles(
    root: Path,
    sources: list[dict],
    manifest_errors: list[dict],
) -> dict[str, dict]:
    """Return normalized name -> ``{version, file, ecosystem}`` for every
    lockfile present.

    A lockfile holds the whole transitive closure, so its contents are kept
    apart from the declared dependency set: folding them together would report
    every transitive package as an ``undocumented`` dependency the project is
    expected to write a library doc for.
    """
    locked: dict[str, dict] = {}
    for filename, ecosystem in LOCKFILES:
        path = root / filename
        if not path.is_file():
            continue
        if filename.endswith(".lock"):
            data, error = _load_toml(path)
            versions = _uv_lock_versions(data) if isinstance(data, dict) else {}
        else:
            data, error = _load_json(path)
            versions = _package_lock_versions(data)
        if error is not None:
            manifest_errors.append({"file": filename, "error": error})
            continue
        sources.append(
            {
                "file": filename,
                "table": "package",
                "ecosystem": ecosystem,
                "kind": "lock",
                "dependency_count": len(versions),
            }
        )
        for name, version in versions.items():
            locked.setdefault(
                name,
                {"version": version, "file": filename, "ecosystem": ecosystem},
            )
    return locked


def build_report(
    root: Path,
    stale_days: int,
    today: date,
    library: str | None = None,
) -> dict:
    """Assemble the full lib_inventory.py JSON report."""
    libraries_dir = root / ".agents" / "docs" / "libraries"
    collected = collect_dependencies(root)
    resolution = dict(collected["resolution"])
    locked: dict[str, dict] = collected["locked"]

    # A doc may exist for a transitive package the manifests never name. Its
    # locked version is still the version this project runs, so it is worth
    # comparing against — but it is deliberately not added to
    # declared_dependencies below, where it would masquerade as a declaration.
    for name, lock in locked.items():
        if name in resolution:
            continue
        if (library is not None and name == library) or (
            libraries_dir / f"{name}.md"
        ).is_file():
            resolution[name] = {
                "name": name,
                "declared_spec": None,
                "declared_in": None,
                "locked_version": lock["version"],
                "locked_in": lock["file"],
                "ecosystem": lock["ecosystem"],
            }

    doc_paths = sorted(libraries_dir.glob("*.md")) if libraries_dir.is_dir() else []
    entries = [
        scan_library(path, today, stale_days, resolution)
        for path in doc_paths
        if library is None or normalize_dep_name(path.stem) == library
    ]
    # Every doc on disk, not just the filtered entries: --library must never
    # make a documented dependency look undocumented.
    documented_stems = {normalize_dep_name(path.stem) for path in doc_paths}

    declared_names = sorted(
        name for name in collected["resolution"] if library is None or name == library
    )
    dependencies = [
        resolution[name]
        for name in sorted(resolution)
        if library is None or name == library
    ]
    undocumented = [name for name in declared_names if name not in documented_stems]
    missing_metadata = [entry["file"] for entry in entries if not entry["has_metadata"]]
    read_errors = [entry["file"] for entry in entries if entry["read_error"]]

    counts = {
        "total": len(entries),
        "stale": sum(1 for e in entries if e["stale"]),
        "missing_metadata": len(missing_metadata),
        "read_errors": len(read_errors),
        "version_drift": sum(1 for e in entries if e["version_drift"] is True),
        "drift_unknown": sum(1 for e in entries if e["version_drift"] is None),
    }

    manifest_errors = collected["manifest_errors"]
    return {
        "ok": not manifest_errors and not read_errors,
        "libraries_dir": _rel_posix(libraries_dir, root),
        "stale_days": stale_days,
        "today": today.isoformat(),
        "library": library,
        "libraries": entries,
        "counts": counts,
        "missing_metadata": missing_metadata,
        "undocumented": undocumented,
        "declared_dependencies": declared_names,
        "dependencies": dependencies,
        "sources": collected["sources"],
        "manifest_errors": manifest_errors,
        "warnings": collected["warnings"],
        "artifacts": [],
    }


def _exit_code(report: dict) -> int:
    """Map a report onto the shared exit vocabulary."""
    if report["counts"]["read_errors"]:
        return EXIT_EXTERNAL
    if report["manifest_errors"]:
        return EXIT_CONTRACT
    return EXIT_OK


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
    parser.add_argument(
        "--library",
        default=None,
        help=(
            "Restrict the report to one package (name is normalized the same "
            "way a doc filename is), for resolving a single library's "
            "declared and locked version"
        ),
    )
    args = parser.parse_args()

    root: Path = args.project_root
    if not root.is_dir():
        # A typo'd root is the most likely operator error here, and a clean
        # all-empty inventory would read as "every library is current".
        _emit({"ok": False, "error": f"project root does not exist: {root}"})
        return EXIT_BAD_INPUT

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

    library = None
    if args.library is not None:
        library = normalize_dep_name(args.library)
        if not NORMALIZED_NAME_RE.match(library):
            _emit(
                {
                    "ok": False,
                    "error": f"--library is not a package name: {args.library!r}",
                }
            )
            return EXIT_BAD_INPUT

    report = build_report(root, args.stale_days, today, library)
    _emit(report)
    return _exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
