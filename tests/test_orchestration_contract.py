import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# One root contract: the main-agent orchestration policy and the subagent
# completion guardrails live in AGENTS.md, and CLAUDE.md was deleted. Claude
# Code reads AGENTS.md directly only while no CLAUDE.md shadows it.
CONTRACT_PATH = REPO_ROOT / "AGENTS.md"
SHADOWING_CLAUDE_FILES = ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md")
SHARED_RUNTIME_DIRS = (
    "rules",
    "skills",
    "agents",
    "hooks",
    "docs",
    "logs",
    "checkpoints",
)

REQUIRED_HEADINGS = (
    "## Mission",
    "## Non-Goals",
    "## Agent Topology",
    "## Routing Policy",
    "## Skill Catalog",
    "## Execution Patterns",
    "## Context and Document Ownership",
    "## Quality Gates",
    "## Language Protocol",
    "## Native Runtime Boundary",
)


def count_headings(content: str, heading: str) -> int:
    """Count `heading` only where it is a real heading line.

    The contract quotes its own section names inline (``see `## Guardrails
    (Completion Verification)` below``), so a substring count reads a
    cross-reference as a duplicate section. This mirrors check.sh's `grep -Fxq`.
    """
    return len(re.findall(rf"^{re.escape(heading)}$", content, re.MULTILINE))


def read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def assert_references_in_order(content: str, references: tuple[str, ...]) -> None:
    positions = [content.index(reference) for reference in references]
    assert positions == sorted(positions)


def test_root_contract_is_the_main_agent_orchestration_contract() -> None:
    """The main-agent policy sections used to live in CLAUDE.md; they are now
    the first half of the single root AGENTS.md."""
    assert CONTRACT_PATH.is_file()
    assert not CONTRACT_PATH.is_symlink()
    content = CONTRACT_PATH.read_text(encoding="utf-8")

    for heading in REQUIRED_HEADINGS:
        assert count_headings(content, heading) == 1


def test_root_contract_is_concise_complete_instruction_file() -> None:
    content = read_repo_file("AGENTS.md")

    # The cap is 400 rather than the 150 that bounded the pre-merge router:
    # one file now carries both contracts. It is a ceiling, not a target.
    assert len(content.splitlines()) <= 400
    for reference in (
        ".claude/rules/",
        ".claude/skills/",
        ".claude/agents/",
        ".claude/STATE.md",
        ".claude/docs/DESIGN.md",
    ):
        assert reference in content
    assert "Japanese" in content
    assert "Claude Code" in content
    assert "verify" in content.lower()
    assert "@orchestra:" not in content
    assert not (REPO_ROOT / ".claude/rules/orchestration.md").exists()


def test_root_contract_catalogs_every_bundled_agent_and_skill() -> None:
    content = read_repo_file("AGENTS.md")
    agent_names = {
        path.stem for path in (REPO_ROOT / ".claude" / "agents").glob("*.md")
    }
    skill_names = {
        path.parent.name
        for path in (REPO_ROOT / ".claude" / "skills").glob("*/SKILL.md")
    }

    assert agent_names
    assert skill_names
    assert all(f"`{name}`" in content for name in agent_names | skill_names)


def test_root_agents_md_is_the_self_contained_contract() -> None:
    """Claude Code auto-loads root AGENTS.md and nothing else, so the response,
    handoff, and completion-guardrail sections a delegation depends on must be
    in this file, not behind a link."""
    assert CONTRACT_PATH.is_file()
    assert not CONTRACT_PATH.is_symlink()
    content = CONTRACT_PATH.read_text(encoding="utf-8")

    for section in (
        "## Required Response Structure",
        "## Handoff Rules",
        "## Guardrails (Completion Verification)",
    ):
        assert count_headings(content, section) == 1
    assert ".claude/rules/tiers.md" in content
    for policy_heading in REQUIRED_HEADINGS:
        assert policy_heading in content


def test_claude_only_edition_has_no_peer_cli_surface() -> None:
    """The Claude Code-only edition removed the peer-CLI integration: no
    adapter directories, no cross-CLI section, no wrapper scripts, and no
    peer-CLI model setting. A half-removed integration is worse than either
    flavour, because its routing hints point at tools that are not there."""
    assert not (REPO_ROOT / ".agents").exists()
    assert not (REPO_ROOT / ".codex").exists()
    content = read_repo_file("AGENTS.md")
    assert count_headings(content, "## Cross-CLI Subagent Invocation") == 0
    for removed in (
        ".claude/skills/_shared/codex_consult.py",
        ".claude/skills/_shared/cli_consult.py",
        ".claude/skills/codex-system",
        ".claude/rules/codex-delegation.md",
        ".claude/hooks/log-cli-tools.py",
        ".claude/docs/change_main.md",
    ):
        assert not (REPO_ROOT / removed).exists(), removed
    settings = json.loads(read_repo_file(".claude/settings.json"))
    assert not any(
        key.endswith("_MODEL") and not key.startswith("CLAUDE_")
        for key in settings.get("env", {})
    )


def test_no_claude_md_shadows_the_root_contract() -> None:
    """Claude Code loads root AGENTS.md directly only while no CLAUDE.md sits in
    the working directory or above it. It reads the first CLAUDE.md it finds
    instead and silently stops loading AGENTS.md — no warning, no error — so the
    main agent would run without its contract. This invariant is what makes the
    single-root-contract design work."""
    for relative_path in SHADOWING_CLAUDE_FILES:
        path = REPO_ROOT / relative_path
        assert not path.exists(), f"{relative_path} shadows root AGENTS.md"
        assert not path.is_symlink(), f"{relative_path} shadows root AGENTS.md"


def test_contract_files_are_real_files_not_symlinks() -> None:
    """The layout is symlink-free by design: a checkout on a filesystem or CI
    runner that does not honour symlinks must still carry every contract."""
    for relative_path in (
        "AGENTS.md",
        ".claude/STATE.md",
        ".claude/rules/tiers.md",
        ".claude/docs/INDEX.md",
    ):
        path = REPO_ROOT / relative_path
        assert path.is_file()
        assert not path.is_symlink()


def test_shared_runtime_content_is_canonical_under_claude() -> None:
    for directory_name in SHARED_RUNTIME_DIRS:
        canonical = REPO_ROOT / ".claude" / directory_name
        assert canonical.is_dir()
        assert not canonical.is_symlink()


def test_claude_directory_holds_only_runtime_content() -> None:
    """`.claude/` is the one physical runtime; nothing in it is a link."""
    claude_entries = {path.name for path in (REPO_ROOT / ".claude").iterdir()}
    assert claude_entries <= {
        "settings.json",
        "settings.local.json",
        "settings.orchestra.json",
        "orchestra-version",
        "STATE.md",
        "agents",
        "skills",
        "rules",
        "hooks",
        "docs",
        "logs",
        "checkpoints",
    }
    assert not any(path.is_symlink() for path in (REPO_ROOT / ".claude").iterdir())
    assert "Claude Code" in read_repo_file(".claude/STATE.md")


def test_native_settings_reference_canonical_claude_paths_directly() -> None:
    claude_settings = read_repo_file(".claude/settings.json")

    assert ".claude/hooks/" in claude_settings
    assert ".agents/hooks/" not in claude_settings
    for hook in re.findall(r"\.claude/hooks/[A-Za-z0-9_.-]+\.py", claude_settings):
        assert (REPO_ROOT / hook).is_file(), f"settings.json wires missing {hook}"


def test_shared_runtime_docs_use_canonical_claude_paths() -> None:
    stale_paths = (
        ".agents/skills/",
        ".agents/rules/",
        ".agents/agents/",
        ".agents/docs/",
        ".agents/logs/",
        ".agents/checkpoints/",
        ".agents/STATE.md",
    )
    violations: list[str] = []
    reviews_dir = REPO_ROOT / ".claude" / "docs" / "reviews"
    logs_dir = REPO_ROOT / ".claude" / "logs"
    checker = REPO_ROOT / "scripts" / "check.sh"
    for path in (REPO_ROOT / ".claude").rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".py", ".sh"}:
            continue
        # The consistency checker has to name the legacy paths it rejects, and
        # the updater has to name the ones it migrates; quoting a path is the
        # opposite of relying on it.
        if path == checker:
            continue
        # Review notes are evidence records, not runtime documentation: an audit
        # finding has to be able to quote the legacy path it found, and a
        # proposal has to be able to name a script that does not exist yet.
        # Same rationale as check.sh's logs/checkpoints/research exclusions.
        if reviews_dir in path.parents:
            continue
        # Run logs are generated evidence, not runtime documentation, and are
        # gitignored. check.sh excludes them from its own doc scan for the same
        # reason: a migration inventory has to quote the paths it migrated away
        # from.
        if logs_dir in path.parents:
            continue
        content = path.read_text(encoding="utf-8")
        if any(stale_path in content for stale_path in stale_paths):
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []


def test_skills_do_not_treat_the_root_contract_as_mutable_state() -> None:
    violations: list[str] = []
    for path in (REPO_ROOT / ".claude" / "skills").rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        if "AGENTS.md Zone" in content or "@orchestra:repo-boundary" in content:
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []


def test_state_tools_write_canonical_claude_state_file() -> None:
    tool_paths = (
        ".claude/skills/_shared/append_state_block.py",
        ".claude/skills/checkpointing/checkpoint.py",
        ".claude/skills/checkpointing/refresh_guard.py",
        ".claude/skills/init/detect_stack.py",
    )
    for tool_path in tool_paths:
        content = read_repo_file(tool_path)
        assert ' / ".claude" / "STATE.md"' in content
        if not tool_path.endswith("detect_stack.py"):
            assert ' / "CLAUDE.md"' not in content


def test_registry_marks_main_agent_contract_as_normative() -> None:
    content = read_repo_file(".claude/docs/INDEX.md")
    matching_lines = [
        line for line in content.splitlines() if "Root agent contract" in line
    ]

    assert len(matching_lines) == 1
    assert "normative" in matching_lines[0]


def test_consistency_checker_validates_contract_and_bootstraps() -> None:
    content = read_repo_file("scripts/check.sh")

    assert "check_root_contract" in content
    assert "check_bootstrap_references" in content
    assert "check_native_boundaries" in content
