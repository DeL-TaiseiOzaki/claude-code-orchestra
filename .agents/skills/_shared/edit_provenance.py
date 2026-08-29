#!/usr/bin/env python3
"""Record which files a delegated CLI run actually edited.

The wrappers grant unrestricted write access by default, so "what was this
subagent allowed to touch?" is no longer an interesting question — "what did
it touch?" is the only one left, and nothing used to answer it. The consult
log recorded the prompt, the model, and the response; the ``artifacts`` field
named the wrapper's *own* log files, never the source files the callee
rewrote. A delegated run could rewrite the repository and leave no
machine-readable trace of having done so.

This module closes that gap. A snapshot is taken immediately before the
callee starts and another immediately after it exits; the difference is the
run's edit set. Only the *dirty set* is hashed — the files ``git status``
already considers changed, plus any path carried over from the earlier
snapshot — so the cost is proportional to the work in flight, not to the size
of the repository.

Three states are distinguished, because "the file is different now" hides
them:

* ``created_files``  — absent (or untracked and non-existent) before, present after.
* ``changed_files``  — present in both, different content.
* ``deleted_files``  — present before, gone after.

A file that was already dirty when the run started and was *not* touched by
it hashes identically in both snapshots and is excluded, so pre-existing
uncommitted work is never misattributed to the callee. Parallel teammates
editing disjoint files stay separable for the same reason; genuinely
concurrent edits to the *same* file cannot be attributed by observation
alone, which is why file ownership stays part of the Agent Teams contract.

Outside a git repository the snapshot degrades to ``tracked: false`` and the
comparison reports empty sets rather than failing: provenance is evidence,
and its absence must not break the consult that produced it.

Usage:
    python3 edit_provenance.py --snapshot
    python3 edit_provenance.py --snapshot --out /tmp/before.json
    python3 edit_provenance.py --compare /tmp/before.json

Exit codes:
    0  a snapshot was taken, or a comparison was produced (including the
       degraded "not a git repository" form)
    1  bad arguments, or an unreadable / malformed snapshot file
    3  git failed, or the snapshot file could not be written
"""

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_FAILED = 3

GIT_TIMEOUT = 60

# Hashing a multi-gigabyte build artifact that happens to be untracked would
# stall the consult it is supposed to annotate. Past this size the fingerprint
# degrades to the file's length, which still detects the appends and rewrites
# an agent produces while costing nothing to compute.
MAX_HASH_BYTES = 8 * 1024 * 1024
HASH_CHUNK = 1024 * 1024


def _emit(obj: dict) -> None:
    """Print a single JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors through this tool's own
    JSON-on-stdout / exit-1 contract instead of argparse's default stderr
    text + exit(2)."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": message})
        sys.exit(EXIT_BAD_ARGS)


def _git(args: list[str], project_root: Path) -> tuple[str | None, str | None]:
    """Run a git command; return ``(stdout, error)`` with exactly one set."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError:
        return None, "git not found on PATH"
    except subprocess.TimeoutExpired:
        return None, f"git {' '.join(args)} timed out after {GIT_TIMEOUT}s"
    except OSError as exc:
        return None, f"cannot run git {' '.join(args)}: {exc}"
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        return None, f"git {' '.join(args)} exited {result.returncode}: {detail}"
    return result.stdout, None


def parse_status_z(raw: str) -> dict[str, str]:
    """Parse ``git status --porcelain=v1 -uall -z`` into ``{path: status}``.

    In the NUL-separated form a rename or copy record is followed by a second
    record holding the *source* path. Consuming it explicitly keeps the source
    side of a rename in the dirty set — it is a deletion the run is
    responsible for — and stops it from being misread as a status code for the
    next file.
    """
    tokens = raw.split("\0")
    entries: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        record = tokens[index]
        index += 1
        if len(record) < 4:
            continue
        status, path = record[:2], record[3:]
        if status[0] in ("R", "C") and index < len(tokens):
            origin = tokens[index]
            index += 1
            if origin:
                entries[origin] = status
        entries[path] = status
    return entries


def fingerprint(path: Path) -> str | None:
    """Return a content fingerprint for *path*, or ``None`` if it is absent.

    Unreadable is reported the same way as absent on purpose: the comparison
    only ever asks "is this different from before?", and a file that cannot be
    read at either end is not evidence of an edit.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_HASH_BYTES:
        return f"size:{size}"
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(HASH_CHUNK):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def take_snapshot(
    project_root: Path, extra_paths: Iterable[str] = ()
) -> tuple[dict, str | None]:
    """Fingerprint the repository's dirty set plus *extra_paths*.

    *extra_paths* carries the earlier snapshot's paths into the later one, so
    a file the run restored to its committed state is still fingerprinted and
    reported as changed instead of vanishing from the comparison and reading
    as a deletion.
    """
    head, head_error = _git(["rev-parse", "HEAD"], project_root)
    if head_error is not None:
        # No HEAD is not a failure: an empty repository, or none at all.
        head = None
    status_raw, status_error = _git(
        ["status", "--porcelain=v1", "-uall", "-z"], project_root
    )
    if status_error is not None:
        return {
            "tracked": False,
            "head": None,
            "entries": {},
            "reason": status_error,
        }, None
    statuses = parse_status_z(status_raw or "")
    for path in extra_paths:
        statuses.setdefault(path, "  ")
    entries = {
        path: {"status": status, "fingerprint": fingerprint(project_root / path)}
        for path, status in sorted(statuses.items())
    }
    return {
        "tracked": True,
        "head": head.strip() if head else None,
        "entries": entries,
        "reason": None,
    }, None


def _classify_new_dirt(status: str, after_hash: str | None) -> str:
    """Classify a path that was clean when the run started.

    Its absence from the earlier snapshot says only that it matched HEAD then,
    which is not the same as "it did not exist" — so the verdict comes from the
    status code rather than from the missing fingerprint. Reading the absence
    as non-existence is what once reported every edit to a committed file as a
    creation.
    """
    if after_hash is None:
        return "deleted"
    # `R`/`C` mark the *destination* of a rename or copy; the source side is a
    # separate record whose file is gone, so it takes the branch above.
    if status.startswith("?") or "A" in status or status[0] in ("R", "C"):
        return "created"
    if "D" in status:
        return "deleted"
    return "changed"


def _classify(before: dict | None, after: dict | None) -> str | None:
    """Return ``created`` / ``changed`` / ``deleted`` for one path, or None.

    ``None`` means the path carries no evidence of an edit by this run: it
    either never changed, or it was already dirty and stayed byte-identical.
    """
    after_hash = after["fingerprint"] if after else None
    if before is None:
        return _classify_new_dirt(after["status"] if after else "  ", after_hash)
    before_hash = before["fingerprint"]
    if before_hash == after_hash:
        return None
    if after_hash is None:
        return "deleted"
    if before_hash is None:
        return "created"
    return "changed"


COMMIT_STATUS_BUCKET = {"A": "created", "D": "deleted"}


def collect_commit_edits(
    project_root: Path, head_before: str | None, head_after: str | None
) -> dict[str, list[str]]:
    """Bucket the paths touched by commits made *during* the run.

    A callee with unrestricted access can commit its own work. Those files are
    clean again by the time the later snapshot is taken, so the dirty-set
    difference sees nothing at all — the loudest possible edit would have been
    the one edit this module missed.
    """
    buckets: dict[str, list[str]] = {"created": [], "changed": [], "deleted": []}
    if not head_before or not head_after or head_before == head_after:
        return buckets
    raw, error = _git(
        ["diff", "--name-status", "-z", f"{head_before}..{head_after}"], project_root
    )
    if error is not None or raw is None:
        return buckets
    tokens = [token for token in raw.split("\0") if token]
    index = 0
    while index + 1 < len(tokens):
        status = tokens[index]
        index += 1
        # A rename record carries both the old and the new path.
        if status.startswith(("R", "C")) and index + 1 < len(tokens):
            buckets["deleted"].append(tokens[index])
            buckets["created"].append(tokens[index + 1])
            index += 2
            continue
        buckets[COMMIT_STATUS_BUCKET.get(status[0], "changed")].append(tokens[index])
        index += 1
    return buckets


def compare_snapshots(
    before: dict, after: dict, commit_edits: dict[str, list[str]] | None = None
) -> dict:
    """Difference two snapshots into this run's edit set."""
    if not (before.get("tracked") and after.get("tracked")):
        return {
            "tracked": False,
            "changed_files": [],
            "created_files": [],
            "deleted_files": [],
            "files_total": 0,
            "head_before": before.get("head"),
            "head_after": after.get("head"),
            "committed": False,
            "reason": before.get("reason") or after.get("reason"),
        }
    before_entries = before.get("entries") or {}
    after_entries = after.get("entries") or {}
    buckets: dict[str, list[str]] = {"created": [], "changed": [], "deleted": []}
    for path in sorted(set(before_entries) | set(after_entries)):
        verdict = _classify(before_entries.get(path), after_entries.get(path))
        if verdict is not None:
            buckets[verdict].append(path)
    for verdict, paths in (commit_edits or {}).items():
        buckets[verdict].extend(paths)
    # A file can be both committed and dirty again; it is one edit either way.
    for verdict in buckets:
        buckets[verdict] = sorted(set(buckets[verdict]))
    head_before = before.get("head")
    head_after = after.get("head")
    return {
        "tracked": True,
        "changed_files": buckets["changed"],
        "created_files": buckets["created"],
        "deleted_files": buckets["deleted"],
        "files_total": sum(len(paths) for paths in buckets.values()),
        "head_before": head_before,
        "head_after": head_after,
        "committed": bool(head_before and head_after and head_before != head_after),
        "reason": None,
    }


def edits_since(project_root: Path, before: dict) -> dict:
    """Take the closing snapshot and return this run's edit set.

    This is the entry point the consult wrappers call: one function so the two
    of them cannot drift into disagreeing about what "the callee edited this"
    means.
    """
    after, error = take_snapshot(project_root, (before.get("entries") or {}).keys())
    if error is not None:
        return {
            "tracked": False,
            "changed_files": [],
            "created_files": [],
            "deleted_files": [],
            "files_total": 0,
            "head_before": before.get("head"),
            "head_after": None,
            "committed": False,
            "reason": error,
        }
    commit_edits = collect_commit_edits(
        project_root, before.get("head"), after.get("head")
    )
    return compare_snapshots(before, after, commit_edits)


def _guarded_write(path: Path, text: str) -> str | None:
    """Write *text* to *path*; return an error message, never raise."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"cannot write {path}: {exc}"
    return None


def _repo_relative(path: Path, project_root: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _load_snapshot(path: Path) -> tuple[dict | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read snapshot {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"snapshot {path} is not valid JSON: {exc}"
    if not isinstance(payload, dict) or "entries" not in payload:
        return None, f"snapshot {path} is not an edit-provenance snapshot"
    return payload, None


def main() -> int:
    parser = JsonArgumentParser(
        description="Snapshot and diff the files a delegated run edited.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--snapshot",
        action="store_true",
        help="Fingerprint the current dirty set and print it",
    )
    mode.add_argument(
        "--compare",
        type=Path,
        metavar="SNAPSHOT",
        help="Take a snapshot now and diff it against SNAPSHOT",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Also write the snapshot to this file (--snapshot only)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to 4 levels above this script)",
    )
    args = parser.parse_args()
    project_root = args.project_root

    if not project_root.is_dir():
        _emit(
            {"ok": False, "error": f"--project-root is not a directory: {project_root}"}
        )
        return EXIT_BAD_ARGS
    if args.out is not None and args.compare is not None:
        _emit({"ok": False, "error": "--out applies to --snapshot only"})
        return EXIT_BAD_ARGS

    if args.snapshot:
        snapshot, error = take_snapshot(project_root)
        if error is not None:
            _emit({"ok": False, "error": error, "artifacts": []})
            return EXIT_FAILED
        artifacts: list[str] = []
        if args.out is not None:
            write_error = _guarded_write(args.out, json.dumps(snapshot))
            if write_error is not None:
                _emit({"ok": False, "error": write_error, "artifacts": []})
                return EXIT_FAILED
            artifacts.append(_repo_relative(args.out, project_root))
        _emit(
            {
                "ok": True,
                "mode": "snapshot",
                "tracked": snapshot["tracked"],
                "head": snapshot["head"],
                "dirty_files": len(snapshot["entries"]),
                "snapshot": snapshot,
                "artifacts": artifacts,
                "error": None,
            }
        )
        return EXIT_OK

    before, load_error = _load_snapshot(args.compare)
    if before is None:
        _emit({"ok": False, "error": load_error, "artifacts": []})
        return EXIT_BAD_ARGS
    _emit(
        {
            "ok": True,
            "mode": "compare",
            "edits": edits_since(project_root, before),
            "artifacts": [],
            "error": None,
        }
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
