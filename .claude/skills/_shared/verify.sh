#!/usr/bin/env bash
# verify.sh — quality-gate runner for the orchestra skills.
#
# Runs configured quality gates (ruff check, ruff format, ty, pytest) against
# the project, logging full output and emitting a single JSON summary on stdout.
#
# Usage:
#   bash verify.sh [--project-root DIR]
#
# Exit: 0  overall is "pass" or "no_gates"
#       1  at least one tool failed

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# --- Argument parsing ---------------------------------------------------------
while [ "$#" -gt 0 ]; do
    case "$1" in
        --project-root)
            [ "$#" -ge 2 ] || { printf '{"error":"--project-root requires a value"}\n'; exit 1; }
            PROJECT_ROOT="$(cd "$2" 2>/dev/null && pwd)" || { printf '{"error":"directory not found: %s"}\n' "$2"; exit 1; }
            shift 2
            ;;
        *)
            printf '{"error":"unknown argument: %s"}\n' "$1"
            exit 1
            ;;
    esac
done

LOG_DIR="$PROJECT_ROOT/.claude/logs"
LOG_FILE="$LOG_DIR/verify.log"
LOG_FILE_REL=".claude/logs/verify.log"
PYPROJECT="$PROJECT_ROOT/pyproject.toml"

mkdir -p "$LOG_DIR"
: >"$LOG_FILE"

# --- Helper: check whether pyproject.toml mentions a tool --------------------
pyproject_mentions() {
    [ -f "$PYPROJECT" ] && grep -q "$1" "$PYPROJECT"
}

# --- Collect results in temp dir ---------------------------------------------
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# Per-tool result files: <tool>.status  <tool>.exit  <tool>.reason  <tool>.summary
record_skip() {
    # $1 = tool name, $2 = reason
    echo "skipped" >"$TMP_DIR/$1.status"
    echo "$2"      >"$TMP_DIR/$1.reason"
}

record_run() {
    # $1 = tool name, $2... = command
    local tool="$1"; shift
    {
        echo "========================================"
        echo "  $tool"
        echo "========================================"
    } >>"$LOG_FILE"

    local out_file="$TMP_DIR/$tool.out"
    if (cd "$PROJECT_ROOT" && "$@") >"$out_file" 2>&1; then
        echo "pass" >"$TMP_DIR/$tool.status"
        echo "0"    >"$TMP_DIR/$tool.exit"
    else
        local ec=$?
        echo "fail" >"$TMP_DIR/$tool.status"
        echo "$ec"  >"$TMP_DIR/$tool.exit"
    fi
    cat "$out_file" >>"$LOG_FILE"
    echo "" >>"$LOG_FILE"
}

# --- Gate 1: ruff check ------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    record_skip ruff_check "uv not available"
elif ! [ -f "$PYPROJECT" ]; then
    record_skip ruff_check "pyproject.toml not found"
elif ! pyproject_mentions ruff; then
    record_skip ruff_check "ruff not configured in pyproject.toml"
else
    record_run ruff_check uv run ruff check .
fi

# --- Gate 2: ruff format ------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    record_skip ruff_format "uv not available"
elif ! [ -f "$PYPROJECT" ]; then
    record_skip ruff_format "pyproject.toml not found"
elif ! pyproject_mentions ruff; then
    record_skip ruff_format "ruff not configured in pyproject.toml"
else
    record_run ruff_format uv run ruff format --check .
fi

# --- Gate 3: ty ---------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    record_skip ty "uv not available"
elif ! [ -f "$PYPROJECT" ]; then
    record_skip ty "pyproject.toml not found"
elif ! pyproject_mentions ty; then
    record_skip ty "ty not configured in pyproject.toml"
elif ! [ -d "$PROJECT_ROOT/src" ]; then
    record_skip ty "src/ not found"
else
    record_run ty uv run ty check src/
fi

# --- Gate 4: pytest -----------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    record_skip pytest "uv not available"
elif ! [ -f "$PYPROJECT" ]; then
    record_skip pytest "pyproject.toml not found"
elif ! pyproject_mentions pytest; then
    record_skip pytest "pytest not configured in pyproject.toml"
elif ! [ -d "$PROJECT_ROOT/tests" ] && ! grep -q '\[tool\.pytest' "$PYPROJECT" 2>/dev/null; then
    record_skip pytest "tests/ not found and no [tool.pytest] in pyproject.toml"
else
    record_run pytest uv run pytest -q
    # pytest exit code 5 = no tests collected: that is absence of a gate,
    # not a failure — report it as skipped so overall stays truthful.
    if [ "$(cat "$TMP_DIR/pytest.exit" 2>/dev/null)" = "5" ]; then
        echo "skipped" >"$TMP_DIR/pytest.status"
        echo "no tests collected (pytest exit 5)" >"$TMP_DIR/pytest.reason"
    fi
    # Extract summary line from pytest output (e.g. "2 passed in 0.5s")
    if [ -f "$TMP_DIR/pytest.out" ]; then
        PYTEST_SUMMARY="$(tail -5 "$TMP_DIR/pytest.out" | grep -E '(passed|failed|error)' | tail -1)"
        if [ -n "$PYTEST_SUMMARY" ]; then
            echo "$PYTEST_SUMMARY" >"$TMP_DIR/pytest.summary"
        fi
    fi
fi

# --- Assemble JSON (delegated to python3 for correct escaping) ---------------
python3 - "$TMP_DIR" "$LOG_FILE_REL" <<'PY'
import json
import os
import sys

tmp_dir = sys.argv[1]
log_file_rel = sys.argv[2]

TOOLS = ["ruff_check", "ruff_format", "ty", "pytest"]


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


tools = {}
any_ran = False
any_failed = False

for tool in TOOLS:
    status = read_text(os.path.join(tmp_dir, f"{tool}.status"))
    if not status:
        status = "skipped"

    entry = {"status": status}

    if status == "skipped":
        reason = read_text(os.path.join(tmp_dir, f"{tool}.reason"))
        if reason:
            entry["reason"] = reason
    else:
        any_ran = True
        exit_code = read_text(os.path.join(tmp_dir, f"{tool}.exit"))
        if exit_code:
            entry["exit_code"] = int(exit_code)
        if status == "fail":
            any_failed = True

    summary = read_text(os.path.join(tmp_dir, f"{tool}.summary"))
    if summary:
        entry["summary"] = summary

    tools[tool] = entry

if any_failed:
    overall = "fail"
elif not any_ran:
    overall = "no_gates"
else:
    overall = "pass"

report = {
    "overall": overall,
    "tools": tools,
    "log_file": log_file_rel,
}
print(json.dumps(report, ensure_ascii=False, indent=2))

# Exit code: 1 if any tool failed, 0 otherwise
sys.exit(1 if any_failed else 0)
PY
