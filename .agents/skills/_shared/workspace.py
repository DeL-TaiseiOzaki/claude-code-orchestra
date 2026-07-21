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

Exit codes:
    0  resolved (preview) or created successfully
    1  bad args: missing/conflicting flags or an unknown --skill
    2  --verify found a missing or effectively empty required artifact
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

SKILL_CHOICES = ("feature", "spike", "troubleshoot", "team-execute")

MIN_NONEMPTY_CHARS = 20

# A slug is interpolated straight into filesystem paths, so an explicitly
# supplied --slug must be constrained to what _slugify() itself can produce.
# Without this, "--slug ../../etc" would escape the workspace on --create.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# Path templates are repo-relative POSIX strings; a trailing "/" marks a
# directory artifact rather than a file. team_dir is shared by every skill.
_TEAM_DIR = ".agents/logs/agent-teams/{team_name}/"

PATH_TEMPLATES: dict[str, dict[str, str]] = {
    "feature": {
        "codebase_scan": ".agents/docs/research/feature-{slug}-codebase.md",
        "research": ".agents/docs/research/{slug}.md",
        "state_input": ".agents/logs/state-input-{slug}.json",
        "team_dir": _TEAM_DIR,
    },
    "spike": {
        "research": ".agents/docs/research/spike-{slug}-research.md",
        "feasibility": ".agents/docs/research/spike-{slug}-feasibility.md",
        "report": ".agents/docs/research/spike-{slug}.md",
        "prototype_dir": ".agents/spikes/{slug}/",
        "team_dir": _TEAM_DIR,
    },
    "troubleshoot": {
        "context": ".agents/docs/research/troubleshoot-{slug}-context.md",
        "root_cause": ".agents/docs/research/troubleshoot-{slug}-root-cause.md",
        "impact": ".agents/docs/research/troubleshoot-{slug}-impact.md",
        "state_input": ".agents/logs/state-input-{slug}.json",
        "team_dir": _TEAM_DIR,
    },
    "team-execute": {
        "review_security": ".agents/docs/research/review-security-{slug}.md",
        "review_quality": ".agents/docs/research/review-quality-{slug}.md",
        "review_tests": ".agents/docs/research/review-tests-{slug}.md",
        "diff_file": ".agents/logs/review-diff.patch",
        "team_dir": _TEAM_DIR,
    },
}

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "feature": ("codebase_scan",),
    "spike": ("research", "feasibility", "report"),
    "troubleshoot": ("context", "root_cause", "impact"),
    "team-execute": ("review_security", "review_quality", "review_tests"),
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


def _team_name(skill: str, slug: str) -> str:
    """Derive the shared team-directory name for *skill* + *slug*."""
    return f"{skill}-{slug}"[:64]


def resolve_paths(skill: str, slug: str, team_name: str) -> dict[str, str]:
    """Render every path template for *skill* with *slug*/*team_name* filled in."""
    templates = PATH_TEMPLATES[skill]
    return {
        key: template.format(slug=slug, team_name=team_name)
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
    """Create each directory (with parents) and report the newly-created ones."""
    created: list[str] = []
    for rel_dir in dirs:
        target = project_root / rel_dir
        if not target.exists():
            created.append(rel_dir)
        target.mkdir(parents=True, exist_ok=True)
    return created


def verify_paths(
    project_root: Path, paths: dict[str, str], required: tuple[str, ...]
) -> dict[str, object]:
    """Check each required artifact exists and is not effectively empty."""
    present: list[str] = []
    missing: list[str] = []
    empty: list[str] = []
    for key in required:
        target = project_root / paths[key]
        try:
            content = target.read_text(encoding="utf-8")
        except OSError:
            missing.append(key)
            continue
        if len(content.strip()) < MIN_NONEMPTY_CHARS:
            empty.append(key)
        else:
            present.append(key)
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
    if args.slug and not SLUG_RE.match(args.slug):
        return (
            "'--slug' must match [a-z0-9][a-z0-9-]{0,63}; "
            "pass '--title' to derive a slug from free text"
        )
    if args.create and args.verify:
        return "'--create' and '--verify' cannot be combined"
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
    parser.add_argument("--skill", help="feature | spike | troubleshoot | team-execute")
    parser.add_argument(
        "--title",
        help="Short English title for the work (becomes the slug)",
    )
    parser.add_argument("--slug", help="Pre-resolved slug (instead of --title)")
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

    slug = _slugify(args.title) if args.title else args.slug
    team_name = _team_name(args.skill, slug)
    paths = resolve_paths(args.skill, slug, team_name)
    dirs = resolve_dirs(paths)

    created: list[str] = []
    if args.create:
        created = create_dirs(args.project_root, dirs)

    verify: dict[str, object] | None = None
    ok = True
    if args.verify:
        verify = verify_paths(args.project_root, paths, REQUIRED_KEYS[args.skill])
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
            "verify": verify,
        }
    )
    return EXIT_VERIFY_FAILED if (args.verify and not ok) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
