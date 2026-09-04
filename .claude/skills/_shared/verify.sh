#!/usr/bin/env bash
# verify.sh — quality-gate runner for the orchestra skills.
#
# Runs configured quality gates (ruff check, ruff format, ty, pytest) against
# the project, logging full output and emitting a single JSON summary on stdout.
# Shell scripts are not exempt from the Shared Script Contract
# (.claude/skills/_shared/README.md): one JSON object on every path, `ok` on
# success and failure alike, and the shared exit-code vocabulary.
#
# Usage:
#   bash verify.sh [--project-root DIR] [--allow-no-gates]
#   bash verify.sh --help
#
# Exit codes:
#   0  ok — overall "pass" (or "no_gates" with --allow-no-gates)
#   1  bad arguments
#   2  contract violation — at least one gate failed, or no gate could run at
#      all (overall "no_gates") without --allow-no-gates. A skill that edits
#      code must not be able to declare done with zero checks executed.
#   3  external failure — the log directory or log file could not be written

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ALLOW_NO_GATES=0

EXIT_BAD_ARGS=1
EXIT_CONTRACT_VIOLATION=2
EXIT_EXTERNAL_FAILURE=3

# --- Helper: single-line JSON error object, always with "ok" ------------------
fail_json() {
    # $1 = exit code, $2 = message
    python3 -c 'import json,sys;print(json.dumps({"ok": False, "error": sys.argv[1]}))' "$2"
    exit "$1"
}

usage_json() {
    python3 - <<'PY'
import json

print(
    json.dumps(
        {
            "ok": True,
            "usage": (
                "bash verify.sh [--project-root DIR] [--allow-no-gates] | "
                "bash verify.sh --help"
            ),
            "description": (
                "Run the configured quality gates (ruff check, ruff format, ty, "
                "pytest) and emit one JSON summary."
            ),
            "flags": {
                "--project-root DIR": "Repository root to run the gates in "
                "(default: the repository containing this script).",
                "--allow-no-gates": "Treat overall 'no_gates' as success "
                "(exit 0) instead of a contract violation.",
                "--help": "Print this object and exit 0.",
            },
            "exit_codes": {
                "0": "ok - overall 'pass', or 'no_gates' with --allow-no-gates",
                "1": "bad arguments",
                "2": "a gate failed, or no gate ran and --allow-no-gates was "
                "not passed",
                "3": "external failure - the log file could not be written",
            },
            "payload": {
                "ok": "boolean",
                "overall": "pass | fail | no_gates",
                "tools": "per-tool status/exit_code/reason/summary",
                "log_file": "repo-relative path to the full gate output",
                "artifacts": "repo-relative paths this run wrote",
            },
        },
        indent=2,
    )
)
PY
    exit 0
}

# --- Argument parsing ---------------------------------------------------------
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            usage_json
            ;;
        --project-root)
            [ "$#" -ge 2 ] || fail_json "$EXIT_BAD_ARGS" "--project-root requires a value"
            # The failure is handled on this same line, so suppressing cd's own
            # stderr keeps the one-JSON-object contract without hiding anything.
            PROJECT_ROOT="$(cd "$2" 2>/dev/null && pwd)" || fail_json "$EXIT_BAD_ARGS" "directory not found: $2"
            shift 2
            ;;
        --allow-no-gates)
            ALLOW_NO_GATES=1
            shift
            ;;
        *)
            fail_json "$EXIT_BAD_ARGS" "unknown argument: $1"
            ;;
    esac
done

LOG_DIR="$PROJECT_ROOT/.claude/logs"
LOG_FILE="$LOG_DIR/verify.log"
LOG_FILE_REL=".claude/logs/verify.log"
PYPROJECT="$PROJECT_ROOT/pyproject.toml"

# Guarded writes: a log directory that cannot be created is an external
# failure reported as JSON, not a bare shell error on stderr.
mkdir -p "$LOG_DIR" || fail_json "$EXIT_EXTERNAL_FAILURE" "cannot create log directory: $LOG_DIR"
: >"$LOG_FILE" || fail_json "$EXIT_EXTERNAL_FAILURE" "cannot write log file: $LOG_FILE"

# --- Helper: check whether pyproject.toml mentions a tool --------------------
pyproject_mentions() {
    [ -f "$PYPROJECT" ] && grep -q "$1" "$PYPROJECT"
}

# --- Collect results in temp dir ---------------------------------------------
TMP_DIR="$(mktemp -d)" || fail_json "$EXIT_EXTERNAL_FAILURE" "cannot create temp directory"
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
    # not a failure — report it as skipped so overall stays truthful. It then
    # counts toward "no_gates", which is itself a failure unless the caller
    # passed --allow-no-gates.
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
python3 - "$TMP_DIR" "$LOG_FILE_REL" "$ALLOW_NO_GATES" <<'PY'
import json
import os
import sys

tmp_dir = sys.argv[1]
log_file_rel = sys.argv[2]
allow_no_gates = sys.argv[3] == "1"

EXIT_CONTRACT_VIOLATION = 2

TOOLS = ["ruff_check", "ruff_format", "ty", "pytest"]


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError as exc:
        return f"__read_error__: {exc}"


tools = {}
any_ran = False
any_failed = False
warnings = []

for tool in TOOLS:
    status = read_text(os.path.join(tmp_dir, f"{tool}.status"))
    if status.startswith("__read_error__"):
        # Degradation is reported, never an invisible fallback to "skipped".
        warnings.append(f"{tool}: could not read recorded status ({status})")
        status = ""
    if not status:
        status = "skipped"

    entry = {"status": status}

    if status == "skipped":
        reason = read_text(os.path.join(tmp_dir, f"{tool}.reason"))
        if reason and not reason.startswith("__read_error__"):
            entry["reason"] = reason
    else:
        any_ran = True
        exit_code = read_text(os.path.join(tmp_dir, f"{tool}.exit"))
        if exit_code.isdigit():
            entry["exit_code"] = int(exit_code)
        if status == "fail":
            any_failed = True

    summary = read_text(os.path.join(tmp_dir, f"{tool}.summary"))
    if summary and not summary.startswith("__read_error__"):
        entry["summary"] = summary

    tools[tool] = entry

if any_failed:
    overall = "fail"
elif not any_ran:
    overall = "no_gates"
else:
    overall = "pass"

# "No gate could run" is not success: it means nothing was verified. It is
# only acceptable when the caller says so explicitly.
if overall == "no_gates" and not allow_no_gates:
    warnings.append(
        "no quality gate could run: pass --allow-no-gates to accept this"
    )

ok = overall == "pass" or (overall == "no_gates" and allow_no_gates)

report = {
    "ok": ok,
    "overall": overall,
    "allow_no_gates": allow_no_gates,
    "tools": tools,
    "warnings": warnings,
    "log_file": log_file_rel,
    "artifacts": [log_file_rel],
}
print(json.dumps(report, ensure_ascii=False, indent=2))

sys.exit(0 if ok else EXIT_CONTRACT_VIOLATION)
PY
