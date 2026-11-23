import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION_PATH = REPO_ROOT / ".claude" / "rules" / "orchestration.md"
ORCHESTRATION_REL = ".claude/rules/orchestration.md"
CLI_CONTRACT_REL = ".claude/rules/cli-contract.md"
EXECUTOR_CONTRACT_REL = ".claude/skills/_shared/executor_contract.md"
ROUTER_PATH = REPO_ROOT / "AGENTS.md"
AGENTS_HEADINGS = (
    "## Project",
    "## Commands",
    "## Conventions",
    "## Agent Roles",
    "## Orchestra References",
)
INSTRUCTION_SHADOW_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")
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


def markdown_section(content: str, heading: str) -> str:
    """Return the body of a `## ` heading, up to the next `## ` heading."""
    return content.split(f"{heading}\n", 1)[1].split("\n## ", 1)[0]


def assert_references_in_order(content: str, references: tuple[str, ...]) -> None:
    positions = [content.index(reference) for reference in references]
    assert positions == sorted(positions)


def test_orchestration_rule_is_the_main_agent_contract() -> None:
    assert ORCHESTRATION_PATH.is_file()
    assert not ORCHESTRATION_PATH.is_symlink()
    content = ORCHESTRATION_PATH.read_text(encoding="utf-8")

    for heading in REQUIRED_HEADINGS:
        assert content.count(heading) == 1


def test_orchestration_rule_is_concise_and_complete() -> None:
    content = read_repo_file(ORCHESTRATION_REL)

    assert len(content.splitlines()) <= 150
    for reference in (
        ".claude/rules/",
        ".claude/skills/",
        ".claude/agents/",
        ".claude/STATE.md",
        ".claude/docs/DESIGN.md",
    ):
        assert reference in content
    assert "Japanese" in content
    assert ".claude/docs/change_main.md" in content
    assert "Claude Code" in content
    assert "verify" in content.lower()
    assert "@orchestra:" not in content
    assert CLI_CONTRACT_REL in content


def test_orchestration_rule_yields_to_delegated_executors() -> None:
    """Claude Code auto-loads `.claude/rules/`, so a headless `claude -p`
    executor loads this file too; its first section must scope it away."""
    content = read_repo_file(ORCHESTRATION_REL)
    scope = content.split("## Mission", 1)[0]

    assert "active main agent" in scope
    assert "delegated executor" in scope
    assert EXECUTOR_CONTRACT_REL in scope


def test_no_claude_md_exists_and_builtin_init_is_forbidden() -> None:
    """Any CLAUDE.md-family file makes Claude Code skip AGENTS.md, and the
    built-in `/init` creates one."""
    for name in INSTRUCTION_SHADOW_FILES:
        assert not (REPO_ROOT / name).exists(), name
    for rel in (
        ORCHESTRATION_REL,
        ".claude/rules/agent-state.md",
        EXECUTOR_CONTRACT_REL,
    ):
        assert "built-in `/init`" in read_repo_file(rel), rel


def test_orchestration_rule_catalogs_every_bundled_agent_and_skill() -> None:
    content = read_repo_file(ORCHESTRATION_REL)
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


def test_root_agents_md_is_the_thin_project_owned_bootstrap() -> None:
    """Root AGENTS.md is the single always-loaded file. It stays thin, carries
    the role split, and points into `.claude/` instead of restating policy —
    a delegated run gets its contract from the wrapper, not from this file."""
    assert ROUTER_PATH.is_file()
    assert not ROUTER_PATH.is_symlink()
    content = ROUTER_PATH.read_text(encoding="utf-8")

    assert len(content.splitlines()) <= 150
    assert len(content.encode("utf-8")) < 32 * 1024
    for heading in AGENTS_HEADINGS:
        assert content.splitlines().count(heading) == 1
    roles = markdown_section(content, "## Agent Roles")
    assert "ORCHESTRA_ROLE" in roles
    assert EXECUTOR_CONTRACT_REL in roles
    for route in (
        ORCHESTRATION_REL,
        CLI_CONTRACT_REL,
        EXECUTOR_CONTRACT_REL,
        ".agents/AGENTS.md",
        ".codex/AGENTS.md",
        ".claude/rules/tiers.md",
    ):
        assert route in content
    for moved in (
        "## Required Response Structure",
        "## Handoff Rules",
        "## Cross-CLI Subagent Invocation",
        "## Guardrails (Completion Verification)",
        *REQUIRED_HEADINGS,
    ):
        assert moved not in content
    assert "@orchestra:" not in content


def test_template_policy_moved_out_of_agents_md_exists_once() -> None:
    """Caller-side and callee-side halves of the old CLI contract each live in
    exactly one file now."""
    cli_contract = read_repo_file(CLI_CONTRACT_REL)
    executor = read_repo_file(EXECUTOR_CONTRACT_REL)

    for section in (
        "## Cross-CLI Subagent Invocation",
        "## Guardrails (Completion Verification)",
    ):
        assert cli_contract.count(section) == 1
        assert section not in executor
    for section in ("## Role", "## Required Response Structure", "## Handoff Rules"):
        assert executor.splitlines().count(section) == 1
        assert section not in cli_contract
    assert "ORCHESTRA_ROLE=executor" in executor
    assert "executor_contract.md" in cli_contract


def test_shipped_skeleton_is_recognized_by_the_updater() -> None:
    """update.sh replaces AGENTS.md only while it is a known shipped blob; an
    unregistered skeleton would be preserved forever as "project-owned"."""
    content = ROUTER_PATH.read_text(encoding="utf-8")
    assert "_Not initialized — run `/start-project`" in content
    blob = subprocess.run(
        ["git", "hash-object", str(ROUTER_PATH)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert f'"AGENTS.md:{blob}"' in read_repo_file("scripts/update.sh")


def test_contract_files_are_real_files_not_symlinks() -> None:
    """The layout is symlink-free by design: a checkout on a filesystem or CI
    runner that does not honour symlinks must still carry every contract."""
    for relative_path in (
        "AGENTS.md",
        ORCHESTRATION_REL,
        CLI_CONTRACT_REL,
        EXECUTOR_CONTRACT_REL,
        ".agents/AGENTS.md",
        ".codex/AGENTS.md",
        ".claude/STATE.md",
        ".claude/rules/tiers.md",
        ".claude/docs/INDEX.md",
        ".claude/docs/change_main.md",
    ):
        path = REPO_ROOT / relative_path
        assert path.is_file()
        assert not path.is_symlink()


def test_shared_runtime_content_is_canonical_under_claude() -> None:
    for directory_name in SHARED_RUNTIME_DIRS:
        canonical = REPO_ROOT / ".claude" / directory_name
        assert canonical.is_dir()
        assert not canonical.is_symlink()


def test_main_agent_change_runbook_is_present_but_not_mandatory_read() -> None:
    content = read_repo_file(".claude/docs/change_main.md")

    for heading in (
        "## Meaning of Main Agent",
        "## Invariants",
        "## Change Procedure",
        "## Validation",
        "## Rollback",
    ):
        assert heading in content
    assert "Claude Code" in read_repo_file(".claude/STATE.md")


def test_subagent_schema_directories_hold_no_runtime_content() -> None:
    """`.agents/` and `.codex/` are Antigravity's and Codex's native
    directories. Each holds that runtime's entry contract and nothing else:
    shared policy lives under `.claude/` and is referenced by path."""
    agents_entries = {path.name for path in (REPO_ROOT / ".agents").iterdir()}
    assert agents_entries == {"AGENTS.md"}

    codex_entries = {path.name for path in (REPO_ROOT / ".codex").iterdir()}
    assert codex_entries == {"config.toml", "AGENTS.md"}

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
    # Nothing in the runtime layout is reached through a link.
    for directory in (".claude", ".agents", ".codex"):
        assert not any(path.is_symlink() for path in (REPO_ROOT / directory).iterdir())


def test_native_settings_reference_canonical_claude_paths_directly() -> None:
    claude_settings = read_repo_file(".claude/settings.json")
    codex_config = read_repo_file(".codex/config.toml")

    assert ".claude/hooks/" in claude_settings
    assert ".agents/hooks/" not in claude_settings
    assert ".claude/skills/context-loader" in codex_config
    assert ".claude/skills/design-tracker" in codex_config
    assert ".codex/skills/" not in codex_config


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
    checker = REPO_ROOT / "scripts" / "check.sh"
    for path in list((REPO_ROOT / ".agents").rglob("*")) + list(
        (REPO_ROOT / ".claude").rglob("*")
    ):
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
        ".claude/skills/start-project/detect_stack.py",
    )
    for tool_path in tool_paths:
        content = read_repo_file(tool_path)
        assert ' / ".claude" / "STATE.md"' in content
        assert ' / "CLAUDE.md"' not in content


def test_runtime_adapters_defer_to_the_shared_contracts() -> None:
    """Each adapter adds only what is specific to its runtime and points at the
    executor and CLI contracts; neither restates them, which is how they used
    to drift, and neither routes an executor to the main-agent contract."""
    for adapter_path in (".agents/AGENTS.md", ".codex/AGENTS.md"):
        adapter = read_repo_file(adapter_path)
        assert "AGENTS.md" in adapter
        assert ".claude/rules/tiers.md" in adapter
        assert EXECUTOR_CONTRACT_REL in adapter
        assert CLI_CONTRACT_REL in adapter
        assert ORCHESTRATION_REL not in adapter
        # The contract lives in one place: an adapter that grew its own copy of
        # a root section is the drift this check exists to catch.
        for section in ("## Required Response Structure", "## Handoff Rules"):
            assert section not in adapter
    assert "reference only" in read_repo_file(".codex/AGENTS.md").lower()


def test_cross_cli_invocation_routes_through_the_shared_wrappers() -> None:
    """Regression guard: the cross-CLI section used to hand callers a raw
    `codex exec "<prompt>" < /dev/null` idiom, contradicting the rule (enforced
    by tests/test_shared_script_contract.py) that Codex is reached only through
    the wrapper — and leaving `claude -p` / `agy -p` with no hardened path
    at all."""
    content = read_repo_file(CLI_CONTRACT_REL)
    section = content.split("## Cross-CLI Subagent Invocation", 1)[1].split("\n## ", 1)[
        0
    ]

    for wrapper in (
        ".claude/skills/_shared/cli_consult.py",
        ".claude/skills/_shared/codex_consult.py",
    ):
        assert wrapper in section, f"cross-CLI section does not route through {wrapper}"
    for raw_idiom in ('codex exec "', 'claude -p "', 'agy -p "'):
        assert raw_idiom not in section, (
            f"cross-CLI section still recommends the raw idiom {raw_idiom!r}"
        )
    # Access must be stated per callee, in both directions.
    assert "read-only" in section.lower()
    assert "--read-only" in section

    assert "cli_consult.py" in read_repo_file(ORCHESTRATION_REL)
    assert "executor_contract.md" in section


def test_registry_marks_main_agent_contract_as_normative() -> None:
    content = read_repo_file(".claude/docs/INDEX.md")
    matching_lines = [
        line for line in content.splitlines() if "Main-agent contract" in line
    ]

    assert len(matching_lines) == 1
    assert "normative" in matching_lines[0]
    assert ORCHESTRATION_REL in matching_lines[0]
    bootstrap = [line for line in content.splitlines() if "| Root bootstrap" in line]
    assert len(bootstrap) == 1
    assert "project-owned" in bootstrap[0]


def test_consistency_checker_validates_contract_and_bootstraps() -> None:
    content = read_repo_file("scripts/check.sh")

    assert "check_root_contract" in content
    assert "check_bootstrap_references" in content
    assert "check_native_boundaries" in content
    assert "check_peer_cli_routing" in content
    assert "check_instruction_shadowing" in content
    assert "check_executor_contract_wiring" in content


def test_antigravity_is_routed_not_just_callable() -> None:
    """Antigravity used to be reachable through the wrapper but named by no
    routing document, so the main agent had no reason to pick it."""
    orchestration = read_repo_file(ORCHESTRATION_REL)
    for heading in ("## Agent Topology", "## Routing Policy"):
        assert "antigravity-delegate" in markdown_section(orchestration, heading)

    delegation = read_repo_file(".claude/rules/delegation.md")
    assert "antigravity-delegate" in markdown_section(delegation, "## Route Selection")

    tiers = read_repo_file(".claude/rules/tiers.md")
    tier_1 = markdown_section(
        tiers, "## Tier 1 -- `default` (Main Agent and Default Executors)"
    )
    assert "Antigravity" in tier_1
    assert "antigravity-delegate" in tier_1

    adapter = read_repo_file(".agents/AGENTS.md")
    assert "Tier 1" in adapter
    assert "antigravity-delegate" in adapter

    agent = read_repo_file(".claude/agents/antigravity-delegate.md")
    assert "cli_consult.py --cli antigravity --read-only" in agent


def test_orchestration_rule_describes_agents_dir_as_adapter_only() -> None:
    """`.agents/` holds exactly `AGENTS.md`; the main-agent contract used to
    list a `workflows/` tree, `tiers.md`, and `check.sh` that no longer live
    there."""
    content = read_repo_file(ORCHESTRATION_REL)
    bullet = next(
        block for block in content.split("\n- ") if block.startswith("`.agents/`")
    )

    assert "AGENTS.md" in bullet
    for stale in ("workflows/", "tiers.md", "check.sh"):
        assert stale not in bullet


def test_executor_contract_allows_prompt_specified_deliverable_format() -> None:
    """Antigravity returns `## TL;DR` / `## Deliverable` / `## Notes`; the
    executor contract must not force the six-section structure onto such a
    reply."""
    content = read_repo_file(EXECUTOR_CONTRACT_REL)
    # The structure's own code block contains `## ` lines, so cut at the next
    # top-level section instead of the first `\n## `.
    structure = content.split("## Required Response Structure", 1)[1].split(
        "## Handoff Rules", 1
    )[0]

    assert "specifies a deliverable format" in structure
    assert "## Deliverable" in structure


def test_routed_antigravity_uses_always_run_read_only() -> None:
    delegation = read_repo_file(".claude/rules/delegation.md")
    boundaries = delegation.split("### Antigravity boundaries", 1)[1].split("\n## ", 1)[
        0
    ]

    assert "alone writes" in boundaries
    assert "Codex" in boundaries
    assert "general-purpose-opus" in boundaries
    assert "read-only" in boundaries


READ_ONLY_COMMAND = "cli_consult.py --cli antigravity --read-only"
READ_ONLY_CHECK_MESSAGE = f"must call '{READ_ONLY_COMMAND}'"


def run_peer_cli_check(tmp_path: Path, agent_text: str) -> str:
    """Run scripts/check.sh against a minimal tree and return its output.

    Only the files `check_peer_cli_routing` reads are present, so unrelated
    checks fail; the assertions look for this check's own message.
    """
    for relative_path in (
        "scripts/check.sh",
        ORCHESTRATION_REL,
        ".claude/rules/delegation.md",
        ".claude/rules/tiers.md",
    ):
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / relative_path, destination)
    agent = tmp_path / ".claude/agents/antigravity-delegate.md"
    agent.parent.mkdir(parents=True)
    agent.write_text(agent_text, encoding="utf-8")

    result = subprocess.run(
        ["bash", str(tmp_path / "scripts/check.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def test_antigravity_delegate_command_carries_the_read_only_flag() -> None:
    agent = read_repo_file(".claude/agents/antigravity-delegate.md")

    assert READ_ONLY_COMMAND in agent


def test_check_script_accepts_the_agent_command_with_read_only(
    tmp_path: Path,
) -> None:
    agent = read_repo_file(".claude/agents/antigravity-delegate.md")

    output = run_peer_cli_check(tmp_path, agent)

    assert READ_ONLY_CHECK_MESSAGE not in output


def test_check_script_fails_when_the_command_drops_read_only(tmp_path: Path) -> None:
    """Prose such as "never omit `--read-only`" must not satisfy the check."""
    agent = read_repo_file(".claude/agents/antigravity-delegate.md")
    mutated = agent.replace(READ_ONLY_COMMAND, "cli_consult.py --cli antigravity")
    assert mutated != agent
    assert "never omit `--read-only`" in mutated

    output = run_peer_cli_check(tmp_path, mutated)

    assert READ_ONLY_CHECK_MESSAGE in output


def test_documented_python_floor_is_3_10() -> None:
    readme = read_repo_file("README.md")

    assert "Python >= 3.10" in readme
    assert "3.11" not in readme
