from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def run_install(
    target: Path,
    *options: str,
    script: Path = INSTALL_SCRIPT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), "--yes", *options, str(target)],
        check=False,
        capture_output=True,
        text=True,
    )


def build_template_repo(tmp_path: Path, name: str = "template") -> Path:
    """Copy this repository into a fresh git repo so scripts under test can
    be run against a template source distinct from the live checkout."""
    template = tmp_path / name
    shutil.copytree(
        REPO_ROOT,
        template,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
        ),
    )
    subprocess.run(["git", "init", "-q", str(template)], check=True)
    subprocess.run(
        ["git", "-C", str(template), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(template), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(["git", "-C", str(template), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(template), "commit", "-qm", "template"], check=True
    )
    return template


def run_update(
    target: Path,
    template: Path,
    *options: str,
    extra_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "ORCHESTRA_TEMPLATE_REPO": str(template)}
    if extra_path is not None:
        env["PATH"] = f"{extra_path}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", str(target / "scripts/update.sh"), "--yes", *options],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def find_debris(root: Path) -> list[Path]:
    """Locate any leftover stage-and-swap artifacts under root (excluding .git)."""
    debris: list[Path] = []
    for pattern in ("*.orchestra-staging.*", "*.orchestra-old.*"):
        for match in root.rglob(pattern):
            if ".git" in match.relative_to(root).parts:
                continue
            debris.append(match)
    return debris


def test_install_adds_complete_template_without_overwriting_project_version(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    (target / "README.md").write_text("# Existing project\n", encoding="utf-8")
    (target / "VERSION").write_text("9.4.1\n", encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    assert (target / "README.md").read_text(encoding="utf-8") == "# Existing project\n"
    assert (target / "VERSION").read_text(encoding="utf-8") == "9.4.1\n"
    assert (target / ".claude/orchestra-version").read_text(encoding="utf-8") == (
        REPO_ROOT / "VERSION"
    ).read_text(encoding="utf-8")
    assert (target / ".claude/docs/INDEX.md").is_file()
    assert (target / ".claude/docs/change_main.md").is_file()
    assert (target / ".agents/AGENTS.md").is_file()
    assert (target / ".claude/rules/tiers.md").is_file()
    assert (target / ".codex/AGENTS.md").is_file()
    assert "## Skill Catalog" in (target / ".claude/rules/orchestration.md").read_text(
        encoding="utf-8"
    )
    assert (target / ".claude/rules/cli-contract.md").is_file()
    assert (target / ".claude/skills/_shared/executor_contract.md").is_file()
    assert (target / ".claude/skills/start-project/write_agents_md.py").is_file()
    assert not (target / ".claude/skills/init").exists()
    assert (target / ".claude/rules").is_dir()
    assert (target / ".claude/skills").is_dir()
    assert (target / ".claude/agents").is_dir()
    assert (target / ".claude/hooks").is_dir()
    assert (target / "AGENTS.md").is_file()
    assert not (target / "AGENTS.md").is_symlink()
    # The shipped skeleton, byte for byte; no CLAUDE.md is shipped at all.
    assert (target / "AGENTS.md").read_bytes() == (REPO_ROOT / "AGENTS.md").read_bytes()
    for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
        assert not (target / name).exists()
    assert {path.name for path in (target / ".claude").iterdir()} == {
        "orchestra-version",
        "settings.json",
        "STATE.md",
        "agents",
        "skills",
        "rules",
        "hooks",
        "docs",
        "logs",
        "checkpoints",
    }
    assert not any(path.is_symlink() for path in (target / ".claude").iterdir())
    assert {path.name for path in (target / ".codex").iterdir()} == {
        "config.toml",
        "AGENTS.md",
    }
    assert (target / "scripts/install.sh").is_file()
    assert (target / "scripts/update.sh").is_file()
    assert (target / ".claude/settings.json").is_file()
    assert (target / ".claude/docs/research/.gitkeep").is_file()
    assert (target / ".claude/STATE.md").is_file()
    assert "@orchestra:" not in (target / "AGENTS.md").read_text(encoding="utf-8")
    gitignore = (target / ".gitignore").read_text(encoding="utf-8")
    # Ignoring CLAUDE.local.md would hide a file that silently disables AGENTS.md.
    assert "CLAUDE.local.md" not in gitignore
    assert ".claude/logs/" in gitignore
    assert ".claude/checkpoints/" in gitignore
    assert ".orchestra-backup-*/" in gitignore


def test_install_backs_up_and_removes_claude_instruction_files(
    tmp_path: Path,
) -> None:
    """Claude Code skips AGENTS.md while any CLAUDE.md-family file exists, so
    install backs each one up, removes it without a prompt, prints where the
    backup went, and records it for /start-project to offer merging."""
    target = tmp_path / "project"
    init_git_repo(target)
    contents = {
        "CLAUDE.md": "# Existing instructions\n\nKeep this project rule.\n",
        "CLAUDE.local.md": "# My local notes\n",
        ".claude/CLAUDE.md": "# Nested instructions\n",
    }
    for name, content in contents.items():
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(content, encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    backups = list(target.glob(".orchestra-backup-*"))
    assert len(backups) == 1
    state = (target / ".claude/STATE.md").read_text(encoding="utf-8")
    assert state.count("## Pending Instruction Merge") == 1
    for name, content in contents.items():
        assert not (target / name).exists(), name
        assert (backups[0] / name).read_text(encoding="utf-8") == content
        backup_rel = f"{backups[0].name}/{name}"
        assert backup_rel in result.stdout
        assert f"`{name}` backed up to `{backup_rel}`" in state
        # The content itself stays in the backup, not in the bootstrap.
        assert content.strip() not in (target / "AGENTS.md").read_text(encoding="utf-8")
    validate = subprocess.run(
        [
            "python3",
            str(target / ".claude/skills/_shared/validate_doc.py"),
            "--contract",
            "state-doc",
            "--file",
            str(target / ".claude/STATE.md"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout


def test_install_keeps_a_claude_md_that_only_imports_agents_md(tmp_path: Path) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    (target / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert list(target.glob(".orchestra-backup-*")) == []


def test_install_backs_up_an_existing_agents_md_before_installing_the_skeleton(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    (target / "AGENTS.md").write_text("# Our Codex notes\n", encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    assert (target / "AGENTS.md").read_bytes() == (REPO_ROOT / "AGENTS.md").read_bytes()
    backups = list(target.glob(".orchestra-backup-*"))
    assert (backups[0] / "AGENTS.md").read_text(
        encoding="utf-8"
    ) == "# Our Codex notes\n"
    assert "`AGENTS.md` backed up to" in (target / ".claude/STATE.md").read_text(
        encoding="utf-8"
    )


def test_install_refuses_template_owned_path_conflicts_by_default(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    custom_file = target / ".claude/rules/custom.md"
    custom_file.parent.mkdir(parents=True)
    custom_file.write_text("custom contract\n", encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 2
    assert "--force" in result.stderr
    assert custom_file.read_text(encoding="utf-8") == "custom contract\n"
    assert not (target / "AGENTS.md").exists()


def test_force_install_backs_up_conflicts_before_replacing_them(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    custom_file = target / ".claude/rules/custom.md"
    custom_file.parent.mkdir(parents=True)
    custom_file.write_text("custom contract\n", encoding="utf-8")

    result = run_install(target, "--force")

    assert result.returncode == 0, result.stderr
    backups = list(target.glob(".orchestra-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / ".claude/rules/custom.md").read_text(
        encoding="utf-8"
    ) == "custom contract\n"
    assert (target / ".claude/docs/INDEX.md").is_file()
    assert not (target / ".claude/rules/custom.md").exists()


def test_install_refuses_to_destroy_existing_native_subagents_and_skills(
    tmp_path: Path,
) -> None:
    """A repo that already uses Claude Code natively keeps its own subagents and
    skills in .claude/. Linking those paths must never silently delete them."""
    target = tmp_path / "project"
    init_git_repo(target)
    existing_agent = target / ".claude/agents/my-agent.md"
    existing_agent.parent.mkdir(parents=True)
    existing_agent.write_text("user's own subagent\n", encoding="utf-8")
    existing_skill = target / ".claude/skills/my-skill/SKILL.md"
    existing_skill.parent.mkdir(parents=True)
    existing_skill.write_text("user's own skill\n", encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 2
    assert "--force" in result.stderr
    assert existing_agent.read_text(encoding="utf-8") == "user's own subagent\n"
    assert existing_skill.read_text(encoding="utf-8") == "user's own skill\n"
    assert not (target / "AGENTS.md").exists()


def test_force_install_backs_up_existing_native_subagents_and_skills(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    existing_agent = target / ".claude/agents/my-agent.md"
    existing_agent.parent.mkdir(parents=True)
    existing_agent.write_text("user's own subagent\n", encoding="utf-8")

    result = run_install(target, "--force")

    assert result.returncode == 0, result.stderr
    backups = list(target.glob(".orchestra-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / ".claude/agents/my-agent.md").read_text(
        encoding="utf-8"
    ) == "user's own subagent\n"
    assert (target / ".claude/agents").is_dir()
    assert not (target / ".claude/agents").is_symlink()
    assert (target / ".claude/agents/general-purpose-opus.md").is_file()


def test_install_skips_python_bytecode_from_the_source_tree(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    for directory in (".claude/skills/_shared", ".claude/hooks"):
        cache = template / directory / "__pycache__"
        cache.mkdir()
        (cache / "x.pyc").write_bytes(b"\x00")
    (template / ".claude/hooks/stray.pyc").write_bytes(b"\x00")
    target = tmp_path / "project"
    init_git_repo(target)

    result = run_install(target, script=template / "scripts/install.sh")

    assert result.returncode == 0, result.stderr
    assert (target / ".claude/skills/_shared").is_dir()
    assert list((target / ".claude").rglob("__pycache__")) == []
    assert list((target / ".claude").rglob("*.pyc")) == []


def test_install_retires_a_legacy_claude_md_symlink(tmp_path: Path) -> None:
    """Pre-2.0 installs shipped CLAUDE.md as a symlink to AGENTS.md. Any
    CLAUDE.md now disables AGENTS.md, so the link is backed up as a link and
    removed without a prompt — never written through."""
    target = tmp_path / "project"
    init_git_repo(target)
    (target / "AGENTS.md").write_text("# Old bootstrap\n", encoding="utf-8")
    (target / "CLAUDE.md").symlink_to("AGENTS.md")

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    assert not (target / "CLAUDE.md").exists()
    assert not (target / "CLAUDE.md").is_symlink()
    backups = list(target.glob(".orchestra-backup-*"))
    assert len(backups) == 1
    # The backup is self-contained: the link's content, not a link that would
    # dangle (or point at the new skeleton) once moved.
    assert not (backups[0] / "CLAUDE.md").is_symlink()
    assert (backups[0] / "CLAUDE.md").read_text(encoding="utf-8") == "# Old bootstrap\n"
    assert (backups[0] / "AGENTS.md").read_text(encoding="utf-8") == "# Old bootstrap\n"
    assert "legacy symlink to AGENTS.md, no merge needed" in (
        target / ".claude/STATE.md"
    ).read_text(encoding="utf-8")
    assert (target / "AGENTS.md").read_bytes() == (REPO_ROOT / "AGENTS.md").read_bytes()


def test_install_preserves_existing_settings_and_writes_merge_candidate(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    settings = target / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    custom_settings = '{"language": "english"}\n'
    settings.write_text(custom_settings, encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    assert settings.read_text(encoding="utf-8") == custom_settings
    candidate = target / ".claude/settings.orchestra.json"
    assert candidate.read_text(encoding="utf-8") == (
        REPO_ROOT / ".claude/settings.json"
    ).read_text(encoding="utf-8")
    assert "settings.orchestra.json" in result.stdout


def test_install_preserves_existing_codex_config_and_writes_merge_candidate(
    tmp_path: Path,
) -> None:
    """`.codex/config.toml` is a settings file, not template content.

    It used to sit inside the wholesale-replaced `.codex/` directory, so an
    install or update silently overwrote a downstream project's model choice,
    approval policy, and sandbox mode — while `.claude/settings.json`, the same
    kind of file, was carefully preserved.
    """
    target = tmp_path / "project"
    init_git_repo(target)
    config = target / ".codex/config.toml"
    config.parent.mkdir(parents=True)
    custom_config = 'model = "gpt-5.6-sol-mini"\n'
    config.write_text(custom_config, encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    assert config.read_text(encoding="utf-8") == custom_config
    candidate = target / ".codex/config.orchestra.toml"
    assert candidate.read_text(encoding="utf-8") == (
        REPO_ROOT / ".codex/config.toml"
    ).read_text(encoding="utf-8")
    assert "config.orchestra.toml" in result.stdout
    # The adapter beside it is template content and is still installed.
    assert (target / ".codex/AGENTS.md").is_file()


def test_update_never_overwrites_codex_config(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = tmp_path / "project"
    init_git_repo(target)
    assert run_install(target, script=template / "scripts/install.sh").returncode == 0

    config = target / ".codex/config.toml"
    edited = config.read_text(encoding="utf-8").replace(
        'model_reasoning_effort = "xhigh"', 'model_reasoning_effort = "medium"'
    )
    assert edited != config.read_text(encoding="utf-8")
    config.write_text(edited, encoding="utf-8")

    update_result = run_update(target, template)

    assert update_result.returncode == 0, update_result.stderr
    assert config.read_text(encoding="utf-8") == edited


def test_install_refuses_parent_symlink_that_escapes_target(tmp_path: Path) -> None:
    target = tmp_path / "project"
    outside = tmp_path / "outside"
    init_git_repo(target)
    outside.mkdir()
    (target / ".claude").symlink_to(outside, target_is_directory=True)

    result = run_install(target)

    assert result.returncode == 2
    assert "symlinked parent" in result.stderr
    assert list(outside.iterdir()) == []


def test_install_refuses_parent_symlink_that_aliases_inside_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    aliased_directory = target / "aliased"
    init_git_repo(target)
    aliased_directory.mkdir()
    (target / ".claude").symlink_to(aliased_directory, target_is_directory=True)

    result = run_install(target)

    assert result.returncode == 2
    assert "symlinked parent" in result.stderr
    assert list(aliased_directory.iterdir()) == []


def test_install_refuses_non_regular_project_file_before_writing(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    (target / "CLAUDE.md").mkdir()

    result = run_install(target)

    assert result.returncode == 2
    assert "regular file" in result.stderr
    assert not (target / "AGENTS.md").exists()


def test_update_uses_namespaced_version_file_and_preserves_project_version(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)

    target = tmp_path / "project"
    init_git_repo(target)
    (target / "VERSION").write_text("9.4.1\n", encoding="utf-8")
    install_result = run_install(target, script=template / "scripts/install.sh")
    assert install_result.returncode == 0, install_result.stderr

    (template / "VERSION").write_text("0.3.1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(template), "add", "VERSION"], check=True)
    subprocess.run(
        ["git", "-C", str(template), "commit", "-qm", "release 0.3.1"],
        check=True,
    )

    update_result = run_update(target, template)

    assert update_result.returncode == 0, update_result.stderr
    assert (target / "VERSION").read_text(encoding="utf-8") == "9.4.1\n"
    assert (target / ".claude/orchestra-version").read_text(
        encoding="utf-8"
    ) == "0.3.1\n"


def test_install_creates_real_runtime_directories(tmp_path: Path) -> None:
    target = tmp_path / "project"
    init_git_repo(target)

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    # The runtime is physically owned by .claude/: nothing here is reached
    # through a link, and nothing is duplicated into .agents/ or .codex/.
    for directory in (".claude", ".agents", ".codex"):
        assert not any(path.is_symlink() for path in (target / directory).iterdir())
    for legacy in ("rules", "skills", "agents", "hooks", "docs"):
        assert not (target / ".agents" / legacy).exists()
    assert (target / ".claude/agents/general-purpose-opus.md").is_file()
    assert (target / ".claude/skills/context-loader/SKILL.md").is_file()
    assert not any(path.is_symlink() for path in (target / ".codex").iterdir())
    assert ".claude/hooks/" in (target / ".claude/settings.json").read_text(
        encoding="utf-8"
    )


def test_update_removes_legacy_agents_runtime_paths(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)

    target = tmp_path / "project"
    init_git_repo(target)
    install_result = run_install(target, script=template / "scripts/install.sh")
    assert install_result.returncode == 0, install_result.stderr
    subprocess.run(["git", "-C", str(target), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(target), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(target), "config", "user.name", "Test User"], check=True
    )
    subprocess.run(
        ["git", "-C", str(target), "commit", "-qm", "initial install"], check=True
    )

    # Recreate the pre-2.0 shape: the runtime lived under .agents/, and Codex
    # kept a copy of the skills it enabled.
    legacy_runtime = target / ".agents/rules"
    legacy_runtime.mkdir(parents=True)
    (legacy_runtime / "coding-principles.md").write_text("stale\n", encoding="utf-8")
    codex_skills = target / ".codex/skills"
    codex_skills.mkdir()
    (codex_skills / "legacy.md").write_text("legacy\n", encoding="utf-8")
    legacy_project_files = {
        "docs/DESIGN.md": "# Legacy design\n",
        "logs/session.log": "legacy log\n",
        "checkpoints/session.md": "legacy checkpoint\n",
    }
    for relative_path, content in legacy_project_files.items():
        legacy_path = target / ".agents" / relative_path
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(content, encoding="utf-8")
    claude_settings = target / ".claude/settings.json"
    claude_settings.write_text(
        claude_settings.read_text(encoding="utf-8").replace(
            ".claude/hooks/", ".agents/hooks/"
        ),
        encoding="utf-8",
    )

    update_result = run_update(target, template)

    assert update_result.returncode == 0, update_result.stderr
    # Template content that moved to .claude/ is removed from .agents/, and
    # .codex/skills stays removed (Codex resolves skills through config.toml
    # path= instead).
    assert not legacy_runtime.exists()
    assert not codex_skills.exists()
    assert (target / ".claude/rules").is_dir()
    assert not (target / ".claude/rules").is_symlink()
    assert {path.name for path in (target / ".codex").iterdir()} == {
        "config.toml",
        "AGENTS.md",
    }
    migrated_settings = claude_settings.read_text(encoding="utf-8")
    assert ".claude/hooks/" in migrated_settings
    assert ".agents/hooks/" not in migrated_settings
    # Project-owned data is moved, never deleted.
    for relative_path in ("logs/session.log", "checkpoints/session.md"):
        assert (target / ".claude" / relative_path).read_text(encoding="utf-8") == (
            legacy_project_files[relative_path]
        )
    migration_backups = list(target.glob(".orchestra-backup-native-migration-*"))
    assert len(migration_backups) == 1
    assert (migration_backups[0] / ".agents/docs/DESIGN.md").read_text(
        encoding="utf-8"
    ) == legacy_project_files["docs/DESIGN.md"]


DEPRECATED_GEMINI_TEMPLATE_FILES = (
    ".gemini/GEMINI.md",
    ".gemini/settings.json",
    ".gemini/skills/context-loader/SKILL.md",
)


def install_project_for_update(tmp_path: Path, template: Path) -> Path:
    target = tmp_path / "project"
    init_git_repo(target)
    install_result = run_install(target, script=template / "scripts/install.sh")
    assert install_result.returncode == 0, install_result.stderr
    subprocess.run(["git", "-C", str(target), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(target), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(target), "config", "user.name", "Test User"], check=True
    )
    subprocess.run(
        ["git", "-C", str(target), "commit", "-qm", "initial install"], check=True
    )
    return target


# Verbatim copy of `.gemini/settings.json` as the template once shipped it (git
# blob b5c01c35fb8bc866e3c411bad6b589ea1c51a2f6), which update.sh must recognize.
SHIPPED_GEMINI_SETTINGS = """{
  "context": {
    "fileName": ["GEMINI.md", "AGENTS.md"],
    "discoveryMaxDirs": 200,
    "respectGitIgnore": true,
    "respectGeminiIgnore": true
  },
  "model": {
    "default": "gemini-2.5-pro"
  },
  "sandbox": {
    "enabled": false
  }
}
"""

# One shipped blob per deprecated path, for the files too large to inline.
SHIPPED_GEMINI_BLOBS = {
    ".gemini/GEMINI.md": "5e9502598c6d7932b87098fe8ace24e9910cc2ea",
    ".gemini/settings.json": "b5c01c35fb8bc866e3c411bad6b589ea1c51a2f6",
    ".gemini/skills/context-loader/SKILL.md": (
        "0494ab2d9e228f601aa04f3daa9aea738664db31"
    ),
}


def shipped_gemini_content(relative_path: str) -> str:
    """Return the shipped content of a deprecated file from this repo's history."""
    if relative_path == ".gemini/settings.json":
        return SHIPPED_GEMINI_SETTINGS
    blob = SHIPPED_GEMINI_BLOBS[relative_path]
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-p", blob],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"blob {blob} is not in this clone's history")
    return result.stdout


def write_deprecated_gemini_files(target: Path) -> None:
    for relative_path in DEPRECATED_GEMINI_TEMPLATE_FILES:
        path = target / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(shipped_gemini_content(relative_path), encoding="utf-8")


def test_shipped_gemini_settings_fixture_matches_the_pinned_blob() -> None:
    blob = subprocess.run(
        ["git", "hash-object", "--stdin"],
        input=SHIPPED_GEMINI_SETTINGS,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert blob == SHIPPED_GEMINI_BLOBS[".gemini/settings.json"]


def test_update_backs_up_deprecated_gemini_template_files_and_removes_empty_dir(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    write_deprecated_gemini_files(target)

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert not (target / ".gemini").exists()
    backups = list(target.glob(".orchestra-backup-deprecated-*"))
    assert len(backups) == 1
    for relative_path in DEPRECATED_GEMINI_TEMPLATE_FILES:
        assert (backups[0] / relative_path).read_text(
            encoding="utf-8"
        ) == shipped_gemini_content(relative_path)


def test_update_keeps_a_customized_gemini_file_and_warns(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    settings = target / ".gemini/settings.json"
    settings.parent.mkdir(parents=True)
    customized = SHIPPED_GEMINI_SETTINGS.replace("gemini-2.5-pro", "my-own-model")
    settings.write_text(customized, encoding="utf-8")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert settings.read_text(encoding="utf-8") == customized
    assert list(target.glob(".orchestra-backup-deprecated-*")) == []
    assert "Kept deprecated template files" in result.stdout
    assert ".gemini/settings.json" in result.stdout


def test_update_moves_matching_gemini_file_but_keeps_a_customized_one(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    settings = target / ".gemini/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(SHIPPED_GEMINI_SETTINGS, encoding="utf-8")
    gemini_md = target / ".gemini/GEMINI.md"
    gemini_md.write_text("my own Gemini instructions\n", encoding="utf-8")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert not settings.exists()
    assert gemini_md.read_text(encoding="utf-8") == "my own Gemini instructions\n"
    backups = list(target.glob(".orchestra-backup-deprecated-*"))
    assert len(backups) == 1
    assert (backups[0] / ".gemini/settings.json").read_text(
        encoding="utf-8"
    ) == SHIPPED_GEMINI_SETTINGS
    assert not (backups[0] / ".gemini/GEMINI.md").exists()
    assert ".gemini/GEMINI.md" in result.stdout


def test_update_keeps_user_owned_files_in_the_gemini_directory(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)
    write_deprecated_gemini_files(target)
    user_file = target / ".gemini/skills/mine/SKILL.md"
    user_file.parent.mkdir(parents=True)
    user_file.write_text("user skill\n", encoding="utf-8")
    user_settings = target / ".gemini/extra.json"
    user_settings.write_text("{}\n", encoding="utf-8")

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert user_file.read_text(encoding="utf-8") == "user skill\n"
    assert user_settings.read_text(encoding="utf-8") == "{}\n"
    for relative_path in DEPRECATED_GEMINI_TEMPLATE_FILES:
        assert not (target / relative_path).exists()
    # The emptied context-loader directory goes; the user's directories stay.
    assert not (target / ".gemini/skills/context-loader").exists()
    assert (target / ".gemini/skills/mine").is_dir()


def test_update_without_deprecated_gemini_files_creates_no_backup(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)
    target = install_project_for_update(tmp_path, template)

    result = run_update(target, template)

    assert result.returncode == 0, result.stderr
    assert list(target.glob(".orchestra-backup-deprecated-*")) == []


def test_update_migrates_legacy_claude_zones_into_shared_state(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)
    target = tmp_path / "project"
    init_git_repo(target)
    install_result = run_install(target, script=template / "scripts/install.sh")
    assert install_result.returncode == 0, install_result.stderr

    legacy_state = "## Current Project\n\nKeep this migrated state.\n"
    (target / "CLAUDE.md").write_text(
        "# Old Claude adapter\n\n"
        "# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "# @orchestra:template-boundary\n"
        "# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "## Repository Identity\n\nLegacy project.\n\n"
        "# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "# @orchestra:repo-boundary\n"
        "# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n" + legacy_state,
        encoding="utf-8",
    )
    (target / "AGENTS.md").write_text("# Old CLI bootstrap\n", encoding="utf-8")

    update_result = run_update(target, template)

    assert update_result.returncode == 0, update_result.stderr
    # Legacy zones are migrated first, then the CLAUDE.md that held them is
    # backed up and removed; an unrecognized AGENTS.md is the project's own.
    assert not (target / "CLAUDE.md").exists()
    migrated = (target / ".claude/STATE.md").read_text(encoding="utf-8")
    assert "Legacy project." in migrated
    assert legacy_state.strip() in migrated
    backups = list(target.glob(".orchestra-backup-instructions-*"))
    assert len(backups) == 1
    assert "Legacy project." in (backups[0] / "CLAUDE.md").read_text(encoding="utf-8")
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert agents == "# Old CLI bootstrap\n"


def test_update_leaves_no_stage_and_swap_debris_and_syncs_safe_dirs(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)

    target = tmp_path / "project"
    init_git_repo(target)
    install_result = run_install(target, script=template / "scripts/install.sh")
    assert install_result.returncode == 0, install_result.stderr

    marker = "# updated marker for debris test\n"
    (template / ".claude/docs/INDEX.md").write_text(
        (template / ".claude/docs/INDEX.md").read_text(encoding="utf-8") + marker,
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(template), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(template), "commit", "-qm", "bump .agents content"],
        check=True,
    )

    update_result = run_update(target, template)

    assert update_result.returncode == 0, update_result.stderr
    assert find_debris(target) == []
    assert (target / ".claude/docs/INDEX.md").read_text(encoding="utf-8") == (
        template / ".claude/docs/INDEX.md"
    ).read_text(encoding="utf-8")


def test_update_rolls_back_safe_dir_on_mid_swap_failure(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)

    target = tmp_path / "project"
    init_git_repo(target)
    install_result = run_install(target, script=template / "scripts/install.sh")
    assert install_result.returncode == 0, install_result.stderr

    original_index = (target / ".claude/docs/INDEX.md").read_text(encoding="utf-8")
    original_listing = sorted(
        p.relative_to(target / ".agents") for p in (target / ".agents").rglob("*")
    )

    marker = "# should never reach the target on a rolled-back update\n"
    (template / ".claude/docs/INDEX.md").write_text(
        (template / ".claude/docs/INDEX.md").read_text(encoding="utf-8") + marker,
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(template), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(template), "commit", "-qm", "bump .agents content"],
        check=True,
    )

    # Shim `mv` on PATH to fail specifically on the second (staging -> live)
    # rename of the .claude/rules swap, simulating a crash between the two mv
    # calls in sync_safe_dirs(). Every other invocation delegates to the
    # real mv so the rest of the update proceeds normally.
    shim_dir = tmp_path / "fake-bin"
    shim_dir.mkdir()
    mv_shim = shim_dir / "mv"
    mv_shim.write_text(
        "#!/usr/bin/env bash\n"
        'for arg in "$@"; do\n'
        '    if [[ "${arg}" == *".claude/rules.orchestra-staging."* ]]; then\n'
        '        echo "shim: simulated mid-swap mv failure" >&2\n'
        "        exit 1\n"
        "    fi\n"
        "done\n"
        'exec /bin/mv "$@"\n',
        encoding="utf-8",
    )
    mv_shim.chmod(0o755)

    update_result = run_update(target, template, extra_path=shim_dir)

    assert update_result.returncode != 0
    assert find_debris(target) == []
    restored_listing = sorted(
        p.relative_to(target / ".agents") for p in (target / ".agents").rglob("*")
    )
    assert restored_listing == original_listing
    assert (target / ".claude/docs/INDEX.md").read_text(
        encoding="utf-8"
    ) == original_index


def test_a_freshly_installed_project_passes_its_own_consistency_check(
    tmp_path: Path,
) -> None:
    """`scripts/check.sh` ships with the template, so it must pass where it lands.

    It passed in this repository and failed in every downstream project:
    `INDEX.md` names `.claude/docs/plans/`, whose marker file is tracked here
    but was absent from both distribution lists, so check 1 reported
    `Missing: .claude/docs/plans/` on a clean install. A check that only holds
    in the repository that authors it is not a check.
    """
    target = tmp_path / "project"
    init_git_repo(target)

    assert run_install(target).returncode == 0

    result = subprocess.run(
        ["bash", str(target / "scripts/check.sh")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout
