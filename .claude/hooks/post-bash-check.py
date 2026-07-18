#!/usr/bin/env python3
"""
PostToolUse hook: Single dispatcher for all Bash-matcher checks.

Consolidates error-to-codex.py, post-test-analysis.py, and log-cli-tools.py
into one process: reads stdin JSON once, then runs each check in-process
via its pure function instead of spawning three separate python3
processes that each re-parse stdin independently.

Coordination fix (not just a perf fix): dedups the generic error-detection
hint against the more targeted test-failure hint. If post-test-analysis
already produced a hint for this output, error-to-codex's hint is
redundant and is suppressed.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

# Sibling scripts, loaded by path since their filenames are not valid
# Python module identifiers (hyphens).
HOOKS_DIR = Path(__file__).parent
LOG_CLI_TOOLS_PATH = HOOKS_DIR / "log-cli-tools.py"
POST_TEST_ANALYSIS_PATH = HOOKS_DIR / "post-test-analysis.py"
ERROR_TO_CODEX_PATH = HOOKS_DIR / "error-to-codex.py"


def load_sibling_module(path: Path, module_name: str) -> ModuleType:
    """Load a sibling hook script as an importable module by file path.

    Hyphenated filenames (e.g. "log-cli-tools.py") cannot be imported by
    name, so this uses importlib.util.spec_from_file_location instead.
    Each sibling script has an `if __name__ == "__main__":` guard, so
    loading it here has no side effects (no stdin read, no exit).
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        # Malformed/empty stdin: fail open, no crash.
        sys.exit(0)

    contexts: list[str] = []

    # 1. Logging always happens first, regardless of the other checks.
    try:
        log_cli_tools = load_sibling_module(LOG_CLI_TOOLS_PATH, "log_cli_tools")
        log_context = log_cli_tools.process_bash(data)
        if log_context:
            contexts.append(log_context)
    except Exception:
        pass

    # 2. Test/build failure analysis: the more targeted hint.
    test_context = None
    try:
        post_test_analysis = load_sibling_module(
            POST_TEST_ANALYSIS_PATH, "post_test_analysis"
        )
        test_context = post_test_analysis.build_context(data)
        if test_context:
            contexts.append(test_context)
    except Exception:
        pass

    # 3. Generic error detection: only if the targeted hint above found
    #    nothing. Emitting both was the original redundancy this
    #    dispatcher exists to fix.
    if not test_context:
        try:
            error_to_codex = load_sibling_module(ERROR_TO_CODEX_PATH, "error_to_codex")
            error_context = error_to_codex.build_context(data)
            if error_context:
                contexts.append(error_context)
        except Exception:
            pass

    if contexts:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "\n\n".join(contexts),
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
