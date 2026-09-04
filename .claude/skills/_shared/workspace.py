#!/usr/bin/env python3
"""Resolve, create, and verify deterministic skill workspace paths.

Single source of truth for skill workspace naming and artifact paths, so that
feature/spike/troubleshoot/team-execute derive the same {slug} and team_name
in every phase instead of re-deriving them by hand, which is how cross-phase
artifacts silently drift out of sync.

Usage:
    python3 workspace.py --skill spike --title "DuckDB multi-tenant plan"
    python3 workspace.py --skill spike --slug duckdb-multitenant --create
    python3 workspace.py --skill spike --slug duckdb-multitenant --verify
    python3 workspace.py --skill spike --slug duckdb --verify --require prototype_dir
    python3 workspace.py --skill team-execute --slug auth --teammate backend
    python3 workspace.py --skill research-lib --title "ruamel.yaml"
    python3 workspace.py --skill design-tracker --title "Adopt DuckDB"
    python3 workspace.py --skill troubleshoot --slug login-500 --verify \
        --require diagnosis

Exit codes:
    0  resolved (preview) or created successfully
    1  bad args: missing/conflicting flags or an unknown --skill
    2  --verify found a missing or effectively empty required artifact
    3  write failure while creating the workspace directories
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_VERIFY_FAILED = 2
EXIT_WRITE_FAILED = 3

SKILL_CHOICES = (
    "feature",
    "spike",
    "troubleshoot",
    "team-execute",
    "plan",
    "research-lib",
    "design-tracker",
)

MIN_NONEMPTY_CHARS = 20

# A slug is interpolated straight into filesystem paths, so an explicitly
# supplied --slug must be constrained to what _slugify() itself can produce.
# Without this, "--slug ../../etc" would escape the workspace on --create.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# --skill research-lib names a *package*, not free text, and a package slug
# keeps its dots (see _package_slug), so it needs its own guard: SLUG_RE would
# reject the very slug _package_slug() produces for "ruamel.yaml".
PACKAGE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

# Mirrors PACKAGE_NAME_RE in update-lib-docs/lib_inventory.py, so the two
# normalizations strip PEP 508 extras and specifiers identically.
_PACKAGE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")

# Path templates are repo-relative POSIX strings; a trailing "/" marks a
# directory artifact rather than a file. team_dir is shared by every skill.
_TEAM_DIR = ".claude/logs/agent-teams/{team_name}/"

# Added by --teammate only: one file per teammate inside the shared team dir.
_WORK_LOG = ".claude/logs/agent-teams/{team_name}/{teammate}.md"

PATH_TEMPLATES: dict[str, dict[str, str]] = {
    "feature": {
        "brief": ".claude/docs/research/feature-{slug}-brief.md",
        "codebase_scan": ".claude/docs/research/feature-{slug}-codebase.md",
        "research": ".claude/docs/research/{slug}.md",
        "state_input": ".claude/logs/state-input-{slug}.json",
        "team_dir": _TEAM_DIR,
    },
    "spike": {
        "brief": ".claude/docs/research/spike-{slug}-brief.md",
        "research": ".claude/docs/research/spike-{slug}-research.md",
        "feasibility": ".claude/docs/research/spike-{slug}-feasibility.md",
        "report": ".claude/docs/research/spike-{slug}.md",
        "prototype_dir": ".claude/spikes/{slug}/",
        "team_dir": _TEAM_DIR,
    },
    "troubleshoot": {
        "bug_report": ".claude/docs/research/troubleshoot-{slug}-bug-report.md",
        "context": ".claude/docs/research/troubleshoot-{slug}-context.md",
        "root_cause": ".claude/docs/research/troubleshoot-{slug}-root-cause.md",
        "impact": ".claude/docs/research/troubleshoot-{slug}-impact.md",
        # Phase 3 deliverable, validated with `validate_doc.py --contract
        # diagnosis`. Deliberately not in REQUIRED_KEYS: phases 1-2 --verify
        # runs would then fail on a document that does not exist yet, so
        # phase 3 asks for it explicitly with `--require diagnosis`.
        "diagnosis": ".claude/logs/troubleshoot-{slug}-diagnosis.md",
        "state_input": ".claude/logs/state-input-{slug}.json",
        "team_dir": _TEAM_DIR,
    },
    "team-execute": {
        "review_security": ".claude/docs/research/review-security-{slug}.md",
        "review_quality": ".claude/docs/research/review-quality-{slug}.md",
        "review_tests": ".claude/docs/research/review-tests-{slug}.md",
        "diff_file": ".claude/logs/review-diff-{slug}.patch",
        "team_dir": _TEAM_DIR,
    },
    "plan": {
        "plan_doc": ".claude/docs/plans/{slug}.md",
    },
    "research-lib": {
        "lib_doc": ".claude/docs/libraries/{slug}.md",
    },
    # /design-tracker records a decision through update_design.py, whose input
    # is a typed JSON file. The path must be per-invocation: the skill is
    # reached from any design conversation and runs inside subagents, so a
    # single shared .claude/logs/design-input.json is a race in which one
    # recording silently overwrites another's input before the writer reads it.
    "design-tracker": {
        "design_input": ".claude/logs/design-input-{slug}.json",
    },
}

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "feature": ("brief", "codebase_scan"),
    "spike": ("brief", "research", "feasibility", "report"),
    "troubleshoot": ("bug_report", "context", "root_cause", "impact"),
    "team-execute": ("review_security", "review_quality", "review_tests"),
    "plan": ("plan_doc",),
    "research-lib": ("lib_doc",),
    "design-tracker": ("design_input",),
}


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2) — so even an argparse-level failure (an unknown flag, or a
    value that looks like an option) stays machine-readable and never
    masquerades as this tool's exit code 2."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_ARGS)


def _slugify(title: str) -> str:
    """Derive a URL-safe slug from *title*.

    Matches ``_slugify`` in ``append_state_block.py`` exactly (lowercase,
    non-``[a-z0-9]`` runs collapsed to ``-``, stripped of leading/trailing
    ``-``, truncated to 64 chars), except for the empty-slug fallback.

    Titles are expected to be short English descriptors, per the shared
    Language Protocol: slugs become file and directory names, which the
    protocol keeps in English. A title that collapses to nothing anyway
    (a purely non-Latin one) still gets a stable sha1-based slug rather than
    a generic "untitled", so two such titles can never collide — but that
    slug is opaque to a human reading the directory, so it is a safety net,
    not the intended path. The same title always yields the same slug.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:64]
    if slug:
        return slug
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
    return f"t-{digest}"


def _package_slug(raw: str) -> str:
    """Normalize a package name for ``--skill research-lib``.

    Deliberately *not* ``_slugify``: ``_slugify`` collapses ``.`` to ``-``,
    while ``lib_inventory.py``'s ``normalize_dep_name`` preserves it. Deriving
    ``.claude/docs/libraries/{slug}.md`` with ``_slugify`` would file
    ``ruamel.yaml`` under ``ruamel-yaml.md``, which the inventory would then
    report as undocumented forever.

    This function reproduces ``normalize_dep_name`` exactly — strip an npm
    scope, drop PEP 508 environment markers, keep only the leading package-name
    token (so extras and version specifiers fall away), lowercase, and map
    ``_`` to ``-`` while leaving ``.`` intact. The two implementations live in
    their own scripts (the shared contract forbids cross-script imports) and
    are held together by ``tests/test_slug_agreement.py``.
    """
    name = raw.strip()
    if name.startswith("@") and "/" in name:
        name = name.split("/", 1)[1]
    name = name.split(";", 1)[0]
    match = _PACKAGE_NAME_RE.match(name)
    name = match.group(0) if match else name
    return name.lower().replace("_", "-")


def _team_name(skill: str, slug: str) -> str:
    """Derive the shared team-directory name for *skill* + *slug*."""
    return f"{skill}-{slug}"[:64]


def resolve_paths(
    skill: str, slug: str, team_name: str, teammate: str | None = None
) -> dict[str, str]:
    """Render every path template for *skill* with *slug*/*team_name* filled in.

    With *teammate*, adds the ``work_log`` key for that teammate's log inside
    the shared team directory.
    """
    templates = dict(PATH_TEMPLATES[skill])
    if teammate:
        templates["work_log"] = _WORK_LOG
    return {
        key: template.format(slug=slug, team_name=team_name, teammate=teammate)
        for key, template in templates.items()
    }


def resolve_dirs(paths: dict[str, str]) -> list[str]:
    """Collect the deduplicated, sorted directories the given paths need."""
    dirs: set[str] = set()
    for path in paths.values():
        if path.endswith("/"):
            dirs.add(path.rstrip("/"))
        else:
            dirs.add(path.rsplit("/", 1)[0])
    return sorted(dirs)


def create_dirs(project_root: Path, dirs: list[str]) -> list[str]:
    """Create each directory (with parents) and report the newly-created ones.

    Raises OSError, which main() reports as JSON + exit 3 rather than a
    traceback (e.g. when ``.claude`` exists as a *file*).
    """
    created: list[str] = []
    for rel_dir in dirs:
        target = project_root / rel_dir
        if not target.exists():
            created.append(rel_dir)
        target.mkdir(parents=True, exist_ok=True)
    return created


def _classify_artifact(target: Path) -> str:
    """Return "present", "empty", or "missing" for one resolved artifact path.

    A directory artifact (a template ending in ``/``, such as ``prototype_dir``)
    counts as present when it holds at least one non-trivial file, so
    ``--require prototype_dir`` cannot be satisfied by an empty directory that
    ``--create`` itself made.
    """
    if target.is_dir():
        for child in sorted(target.rglob("*")):
            if not child.is_file():
                continue
            try:
                content = child.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if len(content.strip()) >= MIN_NONEMPTY_CHARS:
                return "present"
        return "empty"
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return "missing"
    return "empty" if len(content.strip()) < MIN_NONEMPTY_CHARS else "present"


def verify_paths(
    project_root: Path, paths: dict[str, str], required: tuple[str, ...]
) -> dict[str, object]:
    """Check each required artifact exists and is not effectively empty."""
    present: list[str] = []
    missing: list[str] = []
    empty: list[str] = []
    buckets = {"present": present, "empty": empty, "missing": missing}
    for key in required:
        target = project_root / paths[key]
        buckets[_classify_artifact(target)].append(key)
    return {
        "required": list(required),
        "present": present,
        "missing": missing,
        "empty": empty,
        "ok": not missing and not empty,
    }


def validate_args(args: argparse.Namespace) -> str | None:
    """Return an error message if *args* violates the CLI contract, else None."""
    if not args.skill:
        return "'--skill' is required"
    if args.skill not in SKILL_CHOICES:
        return f"'--skill' must be one of {', '.join(SKILL_CHOICES)}"
    if bool(args.title) == bool(args.slug):
        return "exactly one of '--title' or '--slug' is required"
    if args.slug:
        if args.skill == "research-lib":
            if not PACKAGE_SLUG_RE.match(args.slug):
                return (
                    "'--slug' must match [a-z0-9][a-z0-9._-]{0,63} for "
                    "'--skill research-lib'; pass '--title' to normalize a "
                    "package name"
                )
        elif not SLUG_RE.match(args.slug):
            return (
                "'--slug' must match [a-z0-9][a-z0-9-]{0,63}; "
                "pass '--title' to derive a slug from free text"
            )
    if args.create and args.verify:
        return "'--create' and '--verify' cannot be combined"
    if args.teammate is not None:
        if not SLUG_RE.match(args.teammate):
            return "'--teammate' must match [a-z0-9][a-z0-9-]{0,63}"
        if "team_dir" not in PATH_TEMPLATES[args.skill]:
            return f"'--skill {args.skill}' has no team directory for '--teammate'"
    if args.require:
        if not args.verify:
            return "'--require' is only meaningful with '--verify'"
        known = set(PATH_TEMPLATES[args.skill])
        if args.teammate is not None:
            known.add("work_log")
        unknown = [key for key in args.require if key not in known]
        if unknown:
            return (
                f"unknown '--require' key(s) for skill '{args.skill}': "
                f"{', '.join(sorted(unknown))}"
            )
    return None


def main() -> int:
    parser = JsonArgumentParser(
        description="Resolve deterministic skill workspace paths",
    )
    # --skill has no choices=, and --title/--slug/--create/--verify are not
    # marked required= or grouped as argparse-mutually-exclusive: the
    # combination rules live in validate_args() so that each violation gets a
    # message naming the actual conflict rather than argparse's generic usage
    # text. JsonArgumentParser covers whatever argparse still rejects first.
    parser.add_argument(
        "--skill",
        help=(
            "feature | spike | troubleshoot | team-execute | plan | "
            "research-lib | design-tracker"
        ),
    )
    parser.add_argument(
        "--title",
        help="Short English title for the work (becomes the slug)",
    )
    parser.add_argument("--slug", help="Pre-resolved slug (instead of --title)")
    parser.add_argument(
        "--teammate",
        help="Teammate name; adds a 'work_log' path inside the team directory",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        metavar="KEY",
        help=(
            "Extra path key that --verify must find (repeatable), for "
            "mode-specific artifacts such as 'research' or 'prototype_dir'"
        ),
    )
    parser.add_argument(
        "--create", action="store_true", help="Create the workspace directories"
    )
    parser.add_argument(
        "--verify", action="store_true", help="Verify required artifacts exist"
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    error = validate_args(args)
    if error:
        _emit({"ok": False, "error": error})
        return EXIT_BAD_ARGS

    if args.title:
        slug = (
            _package_slug(args.title)
            if args.skill == "research-lib"
            else _slugify(args.title)
        )
        guard = PACKAGE_SLUG_RE if args.skill == "research-lib" else SLUG_RE
        if not guard.match(slug):
            _emit(
                {
                    "ok": False,
                    "error": (
                        f"'--title' normalized to {slug!r}, which is not a usable "
                        f"slug for skill '{args.skill}'; pass '--slug' explicitly"
                    ),
                }
            )
            return EXIT_BAD_ARGS
    else:
        slug = args.slug

    team_name = _team_name(args.skill, slug)
    paths = resolve_paths(args.skill, slug, team_name, args.teammate)
    dirs = resolve_dirs(paths)

    created: list[str] = []
    if args.create:
        try:
            created = create_dirs(args.project_root, dirs)
        except OSError as exc:
            _emit({"ok": False, "error": f"cannot create workspace directories: {exc}"})
            return EXIT_WRITE_FAILED

    verify: dict[str, object] | None = None
    ok = True
    if args.verify:
        required = REQUIRED_KEYS[args.skill] + tuple(
            key for key in args.require if key not in REQUIRED_KEYS[args.skill]
        )
        verify = verify_paths(args.project_root, paths, required)
        ok = bool(verify["ok"])

    _emit(
        {
            "ok": ok,
            "skill": args.skill,
            "slug": slug,
            "team_name": team_name,
            "paths": paths,
            "dirs": dirs,
            "created": created,
            "artifacts": created,
            "verify": verify,
        }
    )
    return EXIT_VERIFY_FAILED if (args.verify and not ok) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
