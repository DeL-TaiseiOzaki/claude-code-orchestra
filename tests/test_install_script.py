from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

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
    assert (target / ".agents/INDEX.md").is_file()
    assert (target / "AGENTS.md").is_file()
    assert (target / "scripts/install.sh").is_file()
    assert (target / "scripts/update.sh").is_file()
    assert (target / ".claude/settings.json").is_file()
    assert (target / ".claude/docs/DESIGN.md").is_file()
    assert (target / ".claude/docs/research/.gitkeep").is_file()
    assert "@orchestra:template-boundary" in (target / "CLAUDE.md").read_text(
        encoding="utf-8"
    )
    gitignore = (target / ".gitignore").read_text(encoding="utf-8")
    assert ".claude/logs/" in gitignore
    assert ".claude/checkpoints/" in gitignore
    assert ".orchestra-backup-*/" in gitignore


def test_install_preserves_existing_claude_md_as_zone_c(tmp_path: Path) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    existing_content = "# Existing instructions\n\nKeep this project rule.\n"
    (target / "CLAUDE.md").write_text(existing_content, encoding="utf-8")

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    installed = (target / "CLAUDE.md").read_text(encoding="utf-8")
    repo_boundary_index = installed.index("@orchestra:repo-boundary")
    existing_index = installed.index(existing_content.strip())
    assert existing_index > repo_boundary_index
    assert installed.count(existing_content.strip()) == 1


def test_install_refuses_template_owned_path_conflicts_by_default(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    init_git_repo(target)
    custom_file = target / ".agents/custom.md"
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
    custom_file = target / ".agents/custom.md"
    custom_file.parent.mkdir(parents=True)
    custom_file.write_text("custom contract\n", encoding="utf-8")

    result = run_install(target, "--force")

    assert result.returncode == 0, result.stderr
    backups = list(target.glob(".orchestra-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / ".agents/custom.md").read_text(
        encoding="utf-8"
    ) == "custom contract\n"
    assert (target / ".agents/INDEX.md").is_file()
    assert not (target / ".agents/custom.md").exists()


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


def test_install_creates_resolving_design_tracker_symlink(tmp_path: Path) -> None:
    target = tmp_path / "project"
    init_git_repo(target)

    result = run_install(target)

    assert result.returncode == 0, result.stderr
    link = target / ".codex/skills/design-tracker"
    assert link.is_symlink()
    assert link.is_dir()
    assert link.resolve() == (target / ".claude/skills/design-tracker").resolve()


def test_install_repairs_design_tracker_symlink_via_update(tmp_path: Path) -> None:
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

    link = target / ".codex/skills/design-tracker"
    link.unlink()
    link.write_text("not a symlink anymore\n", encoding="utf-8")

    update_result = run_update(target, template)

    assert update_result.returncode == 0, update_result.stderr
    assert link.is_symlink()
    assert link.resolve() == (target / ".claude/skills/design-tracker").resolve()


def test_update_leaves_no_stage_and_swap_debris_and_syncs_safe_dirs(
    tmp_path: Path,
) -> None:
    template = build_template_repo(tmp_path)

    target = tmp_path / "project"
    init_git_repo(target)
    install_result = run_install(target, script=template / "scripts/install.sh")
    assert install_result.returncode == 0, install_result.stderr

    marker = "# updated marker for debris test\n"
    (template / ".agents/INDEX.md").write_text(
        (template / ".agents/INDEX.md").read_text(encoding="utf-8") + marker,
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
    assert (target / ".agents/INDEX.md").read_text(encoding="utf-8") == (
        template / ".agents/INDEX.md"
    ).read_text(encoding="utf-8")


def test_update_rolls_back_safe_dir_on_mid_swap_failure(tmp_path: Path) -> None:
    template = build_template_repo(tmp_path)

    target = tmp_path / "project"
    init_git_repo(target)
    install_result = run_install(target, script=template / "scripts/install.sh")
    assert install_result.returncode == 0, install_result.stderr

    original_index = (target / ".agents/INDEX.md").read_text(encoding="utf-8")
    original_listing = sorted(
        p.relative_to(target / ".agents") for p in (target / ".agents").rglob("*")
    )

    marker = "# should never reach the target on a rolled-back update\n"
    (template / ".agents/INDEX.md").write_text(
        (template / ".agents/INDEX.md").read_text(encoding="utf-8") + marker,
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(template), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(template), "commit", "-qm", "bump .agents content"],
        check=True,
    )

    # Shim `mv` on PATH to fail specifically on the second (staging -> live)
    # rename of the .agents swap, simulating a crash between the two mv
    # calls in sync_safe_dirs(). Every other invocation delegates to the
    # real mv so the rest of the update proceeds normally.
    shim_dir = tmp_path / "fake-bin"
    shim_dir.mkdir()
    mv_shim = shim_dir / "mv"
    mv_shim.write_text(
        "#!/usr/bin/env bash\n"
        'for arg in "$@"; do\n'
        '    if [[ "${arg}" == *".agents.orchestra-staging."* ]]; then\n'
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
    assert (target / ".agents/INDEX.md").read_text(encoding="utf-8") == original_index
