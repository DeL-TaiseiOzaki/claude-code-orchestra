from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION_PATH = REPO_ROOT / "AGENTS.md"
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


def read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def assert_references_in_order(content: str, references: tuple[str, ...]) -> None:
    positions = [content.index(reference) for reference in references]
    assert positions == sorted(positions)


def test_root_agents_is_shared_orchestration_contract() -> None:
    assert ORCHESTRATION_PATH.is_file()
    content = ORCHESTRATION_PATH.read_text(encoding="utf-8")

    for heading in REQUIRED_HEADINGS:
        assert content.count(heading) == 1


def test_root_agents_md_is_concise_complete_instruction_file() -> None:
    content = read_repo_file("AGENTS.md")

    assert len(content.splitlines()) <= 140
    for reference in (
        ".agents/rules/",
        ".agents/skills/",
        ".agents/agents/",
        ".agents/STATE.md",
        ".agents/docs/DESIGN.md",
    ):
        assert reference in content
    assert "Japanese" in content
    assert ".agents/change_main.md" in content
    assert "Claude Code" in content
    assert "verify" in content.lower()
    assert "@orchestra:" not in content
    assert not (REPO_ROOT / ".agents/rules/orchestration.md").exists()


def test_root_agents_catalogs_every_bundled_agent_and_skill() -> None:
    content = read_repo_file("AGENTS.md")
    agent_names = {
        path.stem for path in (REPO_ROOT / ".agents" / "agents").glob("*.md")
    }
    skill_names = {
        path.parent.name
        for path in (REPO_ROOT / ".agents" / "skills").glob("*/SKILL.md")
    }

    assert agent_names
    assert skill_names
    assert all(f"`{name}`" in content for name in agent_names | skill_names)


def test_claude_md_is_symlink_to_root_agents_md() -> None:
    claude_md = REPO_ROOT / "CLAUDE.md"

    assert claude_md.is_symlink()
    assert claude_md.resolve() == (REPO_ROOT / "AGENTS.md").resolve()
    assert claude_md.read_text(encoding="utf-8") == read_repo_file("AGENTS.md")


def test_shared_runtime_content_is_canonical_under_agents() -> None:
    for directory_name in SHARED_RUNTIME_DIRS:
        canonical = REPO_ROOT / ".agents" / directory_name
        assert canonical.is_dir()
        assert not canonical.is_symlink()


def test_main_agent_change_runbook_is_present_but_not_mandatory_read() -> None:
    content = read_repo_file(".agents/change_main.md")

    for heading in (
        "## Meaning of Main Agent",
        "## Invariants",
        "## Change Procedure",
        "## Validation",
        "## Rollback",
    ):
        assert heading in content
    assert "Claude Code" in read_repo_file(".agents/STATE.md")


def test_native_runtime_directories_only_keep_native_settings() -> None:
    claude_real_files = {
        path.name for path in (REPO_ROOT / ".claude").iterdir() if not path.is_symlink()
    }
    assert claude_real_files <= {
        "settings.json",
        "settings.local.json",
        "settings.orchestra.json",
        "orchestra-version",
    }

    codex_real_files = {
        path.name for path in (REPO_ROOT / ".codex").iterdir() if not path.is_symlink()
    }
    assert codex_real_files == {"config.toml"}
    # The only symlinks allowed in .claude are the native discovery links that
    # point Claude Code's subagent/skill discovery at the canonical .agents/
    # directories. No shared content is physically duplicated.
    claude_symlinks = {
        path.name: path.readlink().as_posix()
        for path in (REPO_ROOT / ".claude").iterdir()
        if path.is_symlink()
    }
    assert claude_symlinks == {
        "agents": "../.agents/agents",
        "skills": "../.agents/skills",
    }
    assert not any(path.is_symlink() for path in (REPO_ROOT / ".codex").iterdir())


def test_native_settings_reference_canonical_agents_paths_directly() -> None:
    claude_settings = read_repo_file(".claude/settings.json")
    codex_config = read_repo_file(".codex/config.toml")

    assert ".agents/hooks/" in claude_settings
    assert ".claude/hooks/" not in claude_settings
    assert ".agents/skills/context-loader" in codex_config
    assert ".agents/skills/design-tracker" in codex_config
    assert ".codex/skills/" not in codex_config


def test_shared_runtime_docs_use_canonical_agents_paths() -> None:
    stale_paths = (
        ".claude/skills/",
        ".claude/rules/",
        ".claude/agents/",
        ".claude/docs/",
        ".claude/logs/",
        ".claude/checkpoints/",
        ".agents/rules/agents-md-zones.md",
    )
    violations: list[str] = []
    reviews_dir = REPO_ROOT / ".agents" / "docs" / "reviews"
    for path in (REPO_ROOT / ".agents").rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".py", ".sh"}:
            continue
        # Review notes are evidence records, not runtime documentation: an audit
        # finding has to be able to quote the legacy path it found, and a
        # proposal has to be able to name a script that does not exist yet.
        # Same rationale as check.sh's logs/checkpoints/research exclusions.
        if reviews_dir in path.parents:
            continue
        content = path.read_text(encoding="utf-8")
        if any(stale_path in content for stale_path in stale_paths):
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []


def test_skills_do_not_treat_root_agents_as_mutable_state() -> None:
    violations: list[str] = []
    for path in (REPO_ROOT / ".agents" / "skills").rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        if "AGENTS.md Zone" in content or "@orchestra:repo-boundary" in content:
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []


def test_state_tools_write_canonical_agents_state_file() -> None:
    tool_paths = (
        ".agents/skills/_shared/append_state_block.py",
        ".agents/skills/checkpointing/checkpoint.py",
        ".agents/skills/checkpointing/refresh_guard.py",
        ".agents/skills/init/detect_stack.py",
    )
    for tool_path in tool_paths:
        content = read_repo_file(tool_path)
        assert ' / ".agents" / "STATE.md"' in content
        if not tool_path.endswith("detect_stack.py"):
            assert ' / "CLAUDE.md"' not in content


def test_cli_contract_extends_root_orchestration_contract() -> None:
    content = read_repo_file(".agents/rules/cli-execution.md")

    assert "AGENTS.md" in content
    assert ".agents/rules/orchestration.md" not in content


def test_cross_cli_invocation_routes_through_the_shared_wrappers() -> None:
    """Regression guard: the cross-CLI section used to hand callers a raw
    `codex exec "<prompt>" < /dev/null` idiom, contradicting the rule (enforced
    by tests/test_shared_script_contract.py) that Codex is reached only through
    the wrapper — and leaving `claude -p` / `agy -p` with no hardened path
    at all."""
    content = read_repo_file(".agents/rules/cli-execution.md")
    section = content.split("## Cross-CLI Subagent Invocation", 1)[1].split("\n## ", 1)[
        0
    ]

    for wrapper in (
        ".agents/skills/_shared/cli_consult.py",
        ".agents/skills/_shared/codex_consult.py",
    ):
        assert wrapper in section, f"cross-CLI section does not route through {wrapper}"
    for raw_idiom in ('codex exec "', 'claude -p "', 'agy -p "'):
        assert raw_idiom not in section, (
            f"cross-CLI section still recommends the raw idiom {raw_idiom!r}"
        )
    # Access must be stated per callee, in both directions.
    assert "read-only" in section.lower()
    assert "--read-only" in section

    root = read_repo_file("AGENTS.md")
    assert "cli_consult.py" in root


def test_registry_marks_root_agents_contract_as_normative() -> None:
    content = read_repo_file(".agents/INDEX.md")
    matching_lines = [
        line for line in content.splitlines() if "Root agent contract" in line
    ]

    assert len(matching_lines) == 1
    assert "normative" in matching_lines[0]


def test_consistency_checker_validates_contract_and_bootstraps() -> None:
    content = read_repo_file(".agents/check.sh")

    assert "check_root_contract" in content
    assert "check_bootstrap_references" in content
    assert "check_native_boundaries" in content
