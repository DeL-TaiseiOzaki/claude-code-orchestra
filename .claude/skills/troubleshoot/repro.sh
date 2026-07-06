#!/usr/bin/env bash
# repro.sh — reproduce an error and capture context for the troubleshoot skill.
#
# Runs the repro command, captures stdout/stderr/exit code to a log file, pulls
# recent git history (and optional blame), and emits a JSON summary on stdout.
# The repro command's own exit code is reported *inside* the JSON; this script
# itself exits 0 in capture mode (1 only on bad arguments).
#
# Usage:
#   bash repro.sh "<repro-command>" [--file <path>] [--bisect-good <ref>]
# Example:
#   bash repro.sh "python3 -m pytest tests/test_x.py" --file src/x.py
#
# Exit: 0 capture completed (see JSON "exit_code" for the command result)
#       1 bad arguments (missing repro command)

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LOG_DIR="$REPO_ROOT/.claude/logs"
LOG_FILE="$LOG_DIR/troubleshoot-repro.log"
LOG_FILE_REL=".claude/logs/troubleshoot-repro.log"

TAIL_LINES=40
RECENT_COMMITS=20

bad_args() {
    printf '{"error":"%s"}\n' "$1"
    exit 1
}

# --- Argument parsing --------------------------------------------------------
if [ "$#" -lt 1 ]; then
    bad_args "missing repro command"
fi

REPRO_CMD="$1"
shift
case "$REPRO_CMD" in
    --*) bad_args "first argument must be the repro command" ;;
esac

BLAME_FILE=""
BISECT_GOOD=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --file)
            [ "$#" -ge 2 ] || bad_args "--file requires a value"
            BLAME_FILE="$2"
            shift 2
            ;;
        --bisect-good)
            [ "$#" -ge 2 ] || bad_args "--bisect-good requires a value"
            BISECT_GOOD="$2"
            shift 2
            ;;
        *)
            bad_args "unknown argument: $1"
            ;;
    esac
done

mkdir -p "$LOG_DIR"

# --- Run the repro command ---------------------------------------------------
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
OUT_FILE="$TMP_DIR/stdout"
ERR_FILE="$TMP_DIR/stderr"

bash -c "$REPRO_CMD" >"$OUT_FILE" 2>"$ERR_FILE"
REPRO_EXIT=$?

{
    echo "# repro command: $REPRO_CMD"
    echo "# exit code: $REPRO_EXIT"
    echo "# --- stdout ---"
    cat "$OUT_FILE"
    echo "# --- stderr ---"
    cat "$ERR_FILE"
} >"$LOG_FILE"

# --- Git context -------------------------------------------------------------
git -C "$REPO_ROOT" log --oneline -n "$RECENT_COMMITS" \
    >"$TMP_DIR/commits" 2>/dev/null || true

BLAME_OUT="$TMP_DIR/blame"
: >"$BLAME_OUT"
if [ -n "$BLAME_FILE" ]; then
    git -C "$REPO_ROOT" log -1 --oneline -- "$BLAME_FILE" \
        >"$BLAME_OUT" 2>/dev/null || true
fi

# --- Assemble JSON (delegated to python3 for correct escaping) ---------------
python3 - "$REPRO_CMD" "$REPRO_EXIT" "$OUT_FILE" "$ERR_FILE" \
    "$TMP_DIR/commits" "$BLAME_OUT" "$LOG_FILE_REL" "$TAIL_LINES" <<'PY'
import sys
import json

(cmd, exit_code, out_path, err_path,
 commits_path, blame_path, log_file_rel, tail_lines) = sys.argv[1:9]
tail_n = int(tail_lines)


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def tail(text, n):
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def read_lines(path):
    return [ln for ln in read_text(path).splitlines() if ln.strip()]


def extract_traceback(stderr):
    marker = "Traceback (most recent call last)"
    idx = stderr.find(marker)
    if idx == -1:
        return None
    return stderr[idx:].strip()


stderr_text = read_text(err_path)
blame_lines = read_lines(blame_path)

report = {
    "repro_command": cmd,
    "exit_code": int(exit_code),
    "stdout_tail": tail(read_text(out_path), tail_n),
    "stderr_tail": tail(stderr_text, tail_n),
    "traceback": extract_traceback(stderr_text),
    "recent_commits": read_lines(commits_path),
    "blame": blame_lines[0] if blame_lines else None,
    "log_file": log_file_rel,
}
print(json.dumps(report, ensure_ascii=False, indent=2))
PY

exit 0
