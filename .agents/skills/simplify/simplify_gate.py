#!/usr/bin/env python3
"""Bracket a refactor with the quality gates, so "I did not change behaviour"
and "I did not widen the scope" become checkable instead of asserted.

``simplify`` used to run ``verify.sh`` once, *after* the edits. A gate that was
already red then looked exactly like a regression the refactor had just
introduced, and nothing at all enumerated the files touched — so the skill's two
promises ("don't change behavior", "refactoring only") had no evidence behind
them.

``--phase before`` records the baseline: the gate results as they are *now*, the
current HEAD, the files that were *already* dirty, and the declared target
scope. ``--phase after`` re-runs the gates and compares, so the report
distinguishes:

* ``regressions`` — a gate that passed (or was skipped) before and fails now.
  This is the only thing the refactor can be blamed for.
* ``pre_existing_failures`` — red before, red after. Reported, never blamed.
* ``fixed`` — red before, green now.
* ``out_of_scope_files`` — a file changed that is neither in ``--scope`` nor in
  the pre-existing dirty set.

The gates themselves are not reimplemented here: ``_shared/verify.sh`` runs
them and ``_shared/gather_diff.py`` reports the changed files. This script only
expresses an *expectation* about two runs of them.

``--phase after`` requires the baseline file, which is what makes the before
phase mandatory rather than advisory. A before phase whose gates cannot run at
all (``overall: no_gates``) is exit 2: a skill that rewrites source must not be
able to declare success with zero checks executed. ``--allow-no-gates`` accepts
that state explicitly and records it in the payload, mirroring ``verify.sh``.

``--scope`` takes files and directories, not glob patterns: a directory covers
everything beneath it. Keeping it literal means the answer to "was this file in
scope" is inspectable by the reader of the JSON.

Usage:
    python3 simplify_gate.py --phase before --scope src/parser.py
    python3 simplify_gate.py --phase after --scope src/parser.py --base main
    python3 simplify_gate.py --phase before --scope src/ --allow-no-gates

Exit codes:
    0  ok — baseline recorded, or the after phase found no regression and no
       out-of-scope change
    1  bad arguments, or --phase after without a readable baseline file
    2  contract violation — a gate regressed, a file outside --scope changed,
       or no gate could run and --allow-no-gates was not passed
    3  external failure — verify.sh / gather_diff.py could not report, or the
       baseline file could not be written
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SHARED = Path(__file__).parent.parent / "_shared"
VERIFY_SH = SHARED / "verify.sh"
GATHER_DIFF = SHARED / "gather_diff.py"
DEFAULT_BASELINE = ".agents/logs/simplify-baseline.json"
SCOPE_PATCH = ".agents/logs/simplify-scope.patch"
VERIFY_TIMEOUT = 1800
GATHER_TIMEOUT = 240

EXIT_OK = 0
EXIT_BAD_INPUT = 1
EXIT_CONTRACT_VIOLATION = 2
EXIT_EXTERNAL_FAILURE = 3


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as this tool's own JSON object
    on stdout with exit 1, instead of argparse's stderr text with exit 2."""

    def error(self, message: str) -> NoReturn:
        emit({"ok": False, "error": message}, EXIT_BAD_INPUT)


def emit(payload: dict, code: int) -> NoReturn:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(code)


# --- delegated collectors ----------------------------------------------------


def run_verify(root: Path, allow_no_gates: bool) -> dict:
    """Run the shared gate runner. Exit 2 there is a failed gate, which is a
    result to record rather than an error to abort on."""
    command = ["bash", str(VERIFY_SH), "--project-root", str(root)]
    if allow_no_gates:
        command.append("--allow-no-gates")
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=VERIFY_TIMEOUT
        )
    except (OSError, subprocess.SubprocessError) as exc:
        emit(
            {"ok": False, "error": f"could not run verify.sh: {exc}"},
            EXIT_EXTERNAL_FAILURE,
        )
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        emit(
            {
                "ok": False,
                "error": "verify.sh produced no JSON",
                "verify_exit": proc.returncode,
                "stderr": proc.stderr.strip(),
            },
            EXIT_EXTERNAL_FAILURE,
        )
    if proc.returncode not in (EXIT_OK, EXIT_CONTRACT_VIOLATION):
        emit(
            {
                "ok": False,
                "error": payload.get("error", "verify.sh failed"),
                "verify_exit": proc.returncode,
            },
            EXIT_EXTERNAL_FAILURE,
        )
    return payload


def run_gather_diff(root: Path, base: str) -> dict:
    """Collect the changed-file scope. Exit 2 there means an empty diff, which
    is the expected state before the refactor and a reportable one after it."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(GATHER_DIFF),
                "--project-root",
                str(root),
                "--base",
                base,
                "--out",
                SCOPE_PATCH,
            ],
            capture_output=True,
            text=True,
            timeout=GATHER_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        emit(
            {"ok": False, "error": f"could not run gather_diff.py: {exc}"},
            EXIT_EXTERNAL_FAILURE,
        )
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        emit(
            {
                "ok": False,
                "error": "gather_diff.py produced no JSON",
                "gather_diff_exit": proc.returncode,
                "stderr": proc.stderr.strip(),
            },
            EXIT_EXTERNAL_FAILURE,
        )
    if proc.returncode not in (EXIT_OK, EXIT_CONTRACT_VIOLATION):
        emit(
            {
                "ok": False,
                "error": payload.get("error", "gather_diff.py failed"),
                "gather_diff_exit": proc.returncode,
            },
            EXIT_EXTERNAL_FAILURE,
        )
    return payload


def head_sha(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


# --- scope -------------------------------------------------------------------


def normalize(path: str) -> str:
    return path.strip().removeprefix("./").rstrip("/")


def in_scope(path: str, scope: list[str]) -> bool:
    """A path is in scope when it *is* a declared entry or sits under one.

    The `/` boundary is what keeps `--scope src/api` from also claiming
    `src/api_v2/`.
    """
    return any(path == entry or path.startswith(entry + "/") for entry in scope)


def tool_statuses(verify_payload: dict) -> dict[str, str]:
    return {
        tool: entry.get("status", "unknown")
        for tool, entry in (verify_payload.get("tools") or {}).items()
    }


def compare_gates(
    before: dict[str, str], after: dict[str, str]
) -> dict[str, list[str]]:
    """Attribute each failing gate. A tool that is red in both phases was
    already broken and is not this refactor's doing; a tool that is red only
    now is the one thing the refactor can be blamed for."""
    return {
        "regressions": [
            tool
            for tool, status in sorted(after.items())
            if status == "fail" and before.get(tool) != "fail"
        ],
        "pre_existing_failures": [
            tool
            for tool, status in sorted(after.items())
            if status == "fail" and before.get(tool) == "fail"
        ],
        "fixed": [
            tool
            for tool, status in sorted(after.items())
            if status == "pass" and before.get(tool) == "fail"
        ],
    }


# --- phases ------------------------------------------------------------------


def phase_before(
    root: Path, scope: list[str], base: str, allow_no_gates: bool, baseline: Path
) -> dict:
    verify = run_verify(root, allow_no_gates)
    diff = run_gather_diff(root, base)
    warnings: list[str] = []

    overall = verify.get("overall")
    if overall == "fail":
        warnings.append(
            "gates are already failing before any edit: the tools listed in "
            "pre_existing_failures cannot be used to judge this refactor"
        )
    if overall == "no_gates" and not allow_no_gates:
        emit(
            {
                "ok": False,
                "phase": "before",
                "error": "no quality gate could run: a refactor cannot be "
                "verified here. Provide gates, or pass --allow-no-gates and "
                "record the commands you ran by hand.",
                "overall_before": overall,
                "gates_before": tool_statuses(verify),
                "warnings": verify.get("warnings", []),
                "artifacts": [],
            },
            EXIT_CONTRACT_VIOLATION,
        )

    pre_existing = diff.get("changed_files", [])
    if pre_existing:
        warnings.append(
            f"{len(pre_existing)} file(s) were already modified before the "
            "refactor; they are recorded so the after phase does not blame "
            "this run for them"
        )

    record = {
        "phase": "before",
        "base": base,
        "head": head_sha(root),
        "scope": scope,
        "allow_no_gates": allow_no_gates,
        "overall_before": overall,
        "gates_before": tool_statuses(verify),
        "pre_existing_changes": pre_existing,
        "verify_log": verify.get("log_file"),
    }
    try:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        emit(
            {"ok": False, "error": f"cannot write baseline: {exc}"},
            EXIT_EXTERNAL_FAILURE,
        )

    baseline_rel = baseline_relative(root, baseline)
    return {
        "ok": True,
        **record,
        "baseline_file": baseline_rel,
        "warnings": warnings,
        "artifacts": [baseline_rel, SCOPE_PATCH],
    }


def phase_after(
    root: Path, scope: list[str], base: str, allow_no_gates: bool, baseline: Path
) -> dict:
    try:
        record = json.loads(baseline.read_text(encoding="utf-8"))
    except OSError as exc:
        emit(
            {
                "ok": False,
                "error": f"no baseline to compare against ({exc}): run "
                "--phase before first",
            },
            EXIT_BAD_INPUT,
        )
    except ValueError as exc:
        emit(
            {"ok": False, "error": f"baseline is not valid JSON: {exc}"},
            EXIT_BAD_INPUT,
        )
    if record.get("phase") != "before":
        emit(
            {"ok": False, "error": "baseline file is not a --phase before record"},
            EXIT_BAD_INPUT,
        )

    warnings: list[str] = []
    scope = scope or record.get("scope", [])
    if not scope:
        emit(
            {"ok": False, "error": "no --scope given and the baseline records none"},
            EXIT_BAD_INPUT,
        )
    base = base or record.get("base")

    verify = run_verify(root, allow_no_gates)
    diff = run_gather_diff(root, base)

    before = record.get("gates_before", {})
    after = tool_statuses(verify)
    verdict = compare_gates(before, after)
    regressions = verdict["regressions"]

    already_dirty = set(record.get("pre_existing_changes", []))
    changed = diff.get("changed_files", [])
    in_scope_files = [f for f in changed if in_scope(f, scope)]
    out_of_scope = [
        f for f in changed if not in_scope(f, scope) and f not in already_dirty
    ]

    overall = verify.get("overall")
    ungated = overall == "no_gates" and not allow_no_gates
    if ungated:
        warnings.append(
            "no quality gate could run after the refactor: nothing verifies "
            "that behaviour is unchanged"
        )
    if record.get("head") != head_sha(root):
        warnings.append(
            "HEAD moved between the two phases: part of the diff may predate "
            "this refactor"
        )
    if not changed:
        warnings.append("no file changed: the refactor produced no edits")

    return {
        "ok": not regressions and not out_of_scope and not ungated,
        "phase": "after",
        "base": base,
        "head": head_sha(root),
        "baseline_file": baseline_relative(root, baseline),
        "scope": scope,
        "allow_no_gates": allow_no_gates,
        "overall_before": record.get("overall_before"),
        "overall_after": overall,
        "gates": {
            tool: {"before": before.get(tool), "after": after.get(tool)}
            for tool in sorted(set(before) | set(after))
        },
        **verdict,
        "changed_files": changed,
        "in_scope_files": in_scope_files,
        "out_of_scope_files": out_of_scope,
        "pre_existing_changes": sorted(already_dirty),
        "verify_log": verify.get("log_file"),
        "diff_file": diff.get("diff_file"),
        "warnings": warnings,
        "artifacts": [SCOPE_PATCH],
    }


def baseline_relative(root: Path, baseline: Path) -> str:
    try:
        return baseline.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return str(baseline)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Compare the quality gates before and after a refactor"
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=["before", "after"],
        help="before: record the baseline. after: re-run and compare",
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="File or directory the refactor is allowed to touch (repeatable). "
        "Required in the before phase; the after phase reuses the baseline's "
        "scope when omitted",
    )
    parser.add_argument(
        "--baseline",
        default=DEFAULT_BASELINE,
        help=f"Baseline JSON written/read by the two phases (default: {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--base",
        default="",
        help="Base ref for the changed-file scope (default: main in the before "
        "phase, then whatever the baseline recorded)",
    )
    parser.add_argument(
        "--allow-no-gates",
        action="store_true",
        help="Accept 'no gate could run' instead of failing. Passed through to "
        "verify.sh and recorded in the payload",
    )
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Repository root to run the gates in",
    )
    return parser


def main() -> NoReturn:
    args = build_parser().parse_args()

    root = Path(args.project_root)
    if not root.is_dir():
        emit(
            {"ok": False, "error": f"project root is not a directory: {root}"},
            EXIT_BAD_INPUT,
        )

    baseline = Path(args.baseline)
    if not baseline.is_absolute():
        baseline = root / baseline

    scope = [normalize(entry) for entry in args.scope if normalize(entry)]
    if args.phase == "before" and not scope:
        emit(
            {
                "ok": False,
                "error": "--scope is required in the before phase: without a "
                "declared target set, 'no scope creep' cannot be checked",
            },
            EXIT_BAD_INPUT,
        )

    if args.phase == "before":
        report = phase_before(
            root, scope, args.base or "main", args.allow_no_gates, baseline
        )
    else:
        report = phase_after(root, scope, args.base, args.allow_no_gates, baseline)

    emit(report, EXIT_OK if report["ok"] else EXIT_CONTRACT_VIOLATION)


if __name__ == "__main__":
    main()
