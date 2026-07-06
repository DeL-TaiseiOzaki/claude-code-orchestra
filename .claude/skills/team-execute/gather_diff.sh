#!/usr/bin/env bash
# gather_diff.sh — collect review scope for the team-execute skill (Phase 2 REVIEW).
#
# Writes the full diff to .claude/logs/review-diff.patch (can be large) and
# emits a lightweight JSON summary on stdout for the reviewers to consume.
#
# Usage:   bash gather_diff.sh [base-ref]     (base-ref defaults to "main")
# Exit:    0 normal
#          1 not a git repository, or base ref does not exist
# coverage / ruff failures are recorded in the JSON and never fail the script.

set -u

BASE="${1:-main}"

# Resolve repo root from this script's location (.claude/skills/team-execute/).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LOG_DIR="$REPO_ROOT/.claude/logs"
DIFF_FILE="$LOG_DIR/review-diff.patch"
DIFF_FILE_REL=".claude/logs/review-diff.patch"

fail_json() {
    # $1 = human-readable error message
    printf '{"error":"%s","base":"%s"}\n' "$1" "$BASE"
    exit 1
}

# --- Preconditions -----------------------------------------------------------
if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    fail_json "not a git repository"
fi

if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$BASE" >/dev/null 2>&1; then
    fail_json "base ref not found: $BASE"
fi

mkdir -p "$LOG_DIR"

HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "")"
RANGE="${BASE}...HEAD"

# --- Collect scope -----------------------------------------------------------
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

git -C "$REPO_ROOT" diff --name-only "$RANGE" >"$TMP_DIR/files" 2>/dev/null || true
git -C "$REPO_ROOT" log "${BASE}..HEAD" --oneline >"$TMP_DIR/commits" 2>/dev/null || true
git -C "$REPO_ROOT" diff "$RANGE" >"$DIFF_FILE" 2>/dev/null || true

DIFFSTAT="$(git -C "$REPO_ROOT" diff --shortstat "$RANGE" 2>/dev/null | sed 's/^[[:space:]]*//')"

# --- Ruff (best effort; never fatal) -----------------------------------------
RUFF_JSON="$TMP_DIR/ruff.json"
if command -v ruff >/dev/null 2>&1; then
    if ruff check "$REPO_ROOT" --output-format=json >"$RUFF_JSON" 2>/dev/null; then
        RUFF_AVAILABLE=1
    else
        # ruff ran but reported issues (non-zero exit still yields JSON).
        RUFF_AVAILABLE=1
    fi
else
    RUFF_AVAILABLE=0
    printf '[]' >"$RUFF_JSON"
fi

# --- Coverage (best effort; parse existing report if present) ----------------
COVERAGE_FILE=""
for candidate in "$REPO_ROOT/coverage.json" "$REPO_ROOT/coverage.xml"; do
    if [ -f "$candidate" ]; then
        COVERAGE_FILE="$candidate"
        break
    fi
done

# --- Assemble JSON (delegated to python3 for correct escaping) ---------------
python3 - "$BASE" "$HEAD_SHA" "$DIFFSTAT" "$DIFF_FILE_REL" \
    "$TMP_DIR/files" "$TMP_DIR/commits" "$RUFF_JSON" "$RUFF_AVAILABLE" \
    "$COVERAGE_FILE" <<'PY'
import json
import sys

(base, head, diffstat, diff_file_rel,
 files_path, commits_path, ruff_path, ruff_available,
 coverage_file) = sys.argv[1:10]


def read_lines(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return [ln.rstrip("\n") for ln in handle if ln.strip()]
    except OSError:
        return []


changed_files = read_lines(files_path)
commits = read_lines(commits_path)

if ruff_available == "1":
    try:
        with open(ruff_path, encoding="utf-8") as handle:
            issues = json.load(handle)
        ruff = {"ok": len(issues) == 0, "issues": len(issues)}
    except (OSError, ValueError):
        ruff = {"ok": False, "issues": None, "note": "ruff output unparseable"}
else:
    ruff = {"ok": False, "issues": None, "note": "ruff not available"}

coverage = {"report": coverage_file} if coverage_file else None

report = {
    "base": base,
    "head": head,
    "changed_files": changed_files,
    "diffstat": diffstat,
    "commits": commits,
    "coverage": coverage,
    "ruff": ruff,
    "diff_file": diff_file_rel,
}
print(json.dumps(report, ensure_ascii=False, indent=2))
PY
