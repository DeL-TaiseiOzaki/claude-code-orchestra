"""Boundary tests for the hook thresholds changed in PR #35.

Each hook gets one prompt/payload that must fire and one that must not. The
no-fire half is the point: every defect these tests guard against was a hint
that fired on a successful command, a benign prompt, or an ordinary edit, and
a hint that fires on everything is one the operator learns to skim past.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".agents" / "hooks"


def load_hook(filename: str) -> ModuleType:
    """Import a hyphenated hook script by path (not a valid module name)."""
    module_name = filename.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, HOOKS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_router = load_hook("agent-router.py")
check_before_write = load_hook("check-codex-before-write.py")
error_to_codex = load_hook("error-to-codex.py")
post_test_analysis = load_hook("post-test-analysis.py")
post_impl_review = load_hook("post-implementation-review.py")


def bash_payload(command: str, stdout: str) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False},
    }


# --- agent-router.py -------------------------------------------------------


def test_detect_agent_with_genuine_design_question_routes_to_codex():
    agent, trigger = agent_router.detect_agent(
        "How should I design the retry layer? I am not sure about the trade-off."
    )
    assert agent == "codex"
    assert trigger in {"design", "not sure", "trade-off"}


def test_detect_agent_with_mechanical_ask_does_not_route():
    assert agent_router.detect_agent("add a --dry-run option to the CLI") == (None, "")
    assert agent_router.detect_agent("make the docstring better") == (None, "")
    assert agent_router.detect_agent("相談なんだけど昼食は?") == (None, "")


def test_detect_agent_with_two_character_japanese_prompt_still_routes():
    """The deleted `len(prompt) < 3` gate skipped exactly this prompt."""
    agent, trigger = agent_router.detect_agent("設計")
    assert (agent, trigger) == ("codex", "設計")


# --- check-codex-before-write.py -------------------------------------------


def test_should_suggest_codex_for_large_new_written_file():
    suggest, reason = check_before_write.should_suggest_codex(
        "/repo/tools/helper.py", "x = 1\n" * 200, is_new_file=True
    )
    assert suggest is True
    assert "new file" in reason


def test_should_suggest_codex_not_for_medium_prose_edit():
    """Boundary: 210 characters of an Edit is a paragraph, not a new file."""
    suggest, reason = check_before_write.should_suggest_codex(
        "/repo/docs/notes.md", "a" * 210, is_new_file=False
    )
    assert (suggest, reason) == (False, "")


def test_should_suggest_codex_ignores_build_artefact_paths():
    suggest, _ = check_before_write.should_suggest_codex("/repo/__pycache__/x.pyc", "")
    assert suggest is False


def test_should_suggest_codex_counts_only_real_definitions():
    suggest, _ = check_before_write.should_suggest_codex(
        "/repo/x.h", "typedef struct A A;\ntypedef struct B B;\n"
    )
    assert suggest is False

    suggest, reason = check_before_write.should_suggest_codex(
        "/repo/x.py", "def alpha():\n    pass\n\ndef beta():\n    pass\n"
    )
    assert suggest is True
    assert "definitions" in reason


# --- error-to-codex.py -----------------------------------------------------


def test_error_hook_fires_on_real_traceback():
    context = error_to_codex.build_context(
        bash_payload(
            "python3 script.py",
            'Traceback (most recent call last):\n  File "s.py", line 1\n'
            "ValueError: bad input\n",
        )
    )
    assert context is not None
    assert "[Error Detected]" in context


def test_error_hook_quiet_on_two_weak_signals():
    """Boundary: MIN_WEAK_SIGNALS is 3, so a deprecation plus a "Could not"
    that a healthy pip install prints must not be enough."""
    context = error_to_codex.build_context(
        bash_payload(
            "uv pip install requests",
            "Could not find a cached wheel, building from source\n"
            "Retrying after the request timed out\n"
            "Successfully installed requests-2.32.3\n",
        )
    )
    assert context is None


# --- post-test-analysis.py -------------------------------------------------


def test_test_analysis_fires_on_red_suite():
    context = post_test_analysis.build_context(
        bash_payload(
            "uv run pytest tests/",
            "FAILED tests/test_foo.py::test_bar\n"
            "E   assert 1 == 2\n"
            "1 failed, 2 passed\n",
        )
    )
    assert context is not None
    assert "[Codex Debug Suggestion]" in context


def test_test_analysis_quiet_on_green_suite_with_error_in_test_names():
    context = post_test_analysis.build_context(
        bash_payload(
            "uv run pytest tests/ -v",
            "tests/t.py::test_error_hint PASSED [ 50%]\n"
            "tests/t.py::test_traceback_hint PASSED [100%]\n"
            "8 passed in 0.30s\n",
        )
    )
    assert context is None


# --- post-implementation-review.py -----------------------------------------


def test_should_suggest_review_at_the_file_threshold():
    state = {"files_changed": ["a.py", "b.py"], "total_lines": 2}
    suggest, reason = post_impl_review.should_suggest_review(state)
    assert suggest is True
    assert reason == "2 files modified"


def test_should_suggest_review_below_the_file_threshold():
    state = {"files_changed": ["a.py"], "total_lines": 1}
    assert post_impl_review.should_suggest_review(state) == (False, "")


def test_should_suggest_review_debounces_then_rearms_when_work_doubles():
    """The one-shot latch let two one-line edits spend the session's only
    nudge; the doubling rule keeps the debounce but re-arms for real work."""
    state = {
        "files_changed": ["a.py", "b.py", "c.py"],
        "total_lines": 3,
        "suggested_at_files": 2,
        "suggested_at_lines": 2,
    }
    assert post_impl_review.should_suggest_review(state) == (False, "")

    state["files_changed"].append("d.py")
    suggest, reason = post_impl_review.should_suggest_review(state)
    assert suggest is True
    assert reason == "4 files modified"


def test_review_hook_end_to_end_stays_quiet_on_a_single_file(tmp_path: Path):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps({"files_changed": ["a.py"], "total_lines": 1}), encoding="utf-8"
    )
    state = post_impl_review.load_state(str(state_file))
    assert post_impl_review.should_suggest_review(state) == (False, "")
