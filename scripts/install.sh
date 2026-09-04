#!/usr/bin/env bash
# Install Claude Code Orchestra into an existing Git repository.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
TEMPLATE_OWNED_DIRS=(
    ".claude/rules"
    ".claude/skills"
    ".claude/agents"
    ".claude/hooks"
)
# Runtime content that pre-2.0 installations kept under .agents/. The main
# agent runtime is now physically owned by .claude/, so these paths are stale.
# They are reported as conflicts and only removed after the user accepts the
# backup, never migrated silently.
LEGACY_RUNTIME_PATHS=(
    ".agents/workflows"
    ".agents/rules"
    ".agents/skills"
    ".agents/agents"
    ".agents/hooks"
    ".agents/docs"
    ".agents/logs"
    ".agents/checkpoints"
    ".agents/STATE.md"
    ".codex/skills"
)
# Template-owned files that no template-owned directory already covers.
# `.claude/rules/`, `.claude/skills/`, `.claude/agents/`, `.claude/hooks/`,
# above are replaced wholesale, so their contents must not be repeated here.
TEMPLATE_OWNED_FILES=(
    ".agents/AGENTS.md"
    ".codex/AGENTS.md"
    ".claude/docs/INDEX.md"
    ".claude/docs/change_main.md"
    ".claude/docs/CODEX_HANDOFF_PLAYBOOK.md"
    ".claude/docs/libraries/.gitkeep"
    ".claude/docs/plans/.gitkeep"
    ".claude/docs/reviews/.gitkeep"
    "scripts/check.sh"
    "scripts/install.sh"
    "scripts/update.sh"
)
# Machine-readable native settings. These are the user's to edit — a downstream
# project changes its model, approval policy, or hooks here — so they are never
# overwritten; when they differ from the template a merge candidate is written
# beside them. Format: "<settings-path>:<candidate-path>".
NATIVE_SETTINGS=(
    ".claude/settings.json:.claude/settings.orchestra.json"
    ".codex/config.toml:.codex/config.orchestra.toml"
)
PROJECT_FILES_IF_MISSING=(
    ".claude/STATE.md"
    ".claude/docs/DESIGN.md"
    ".claude/docs/research/.gitkeep"
)
GITIGNORE_ENTRIES=(
    ".claude/settings.local.json"
    ".claude/settings.orchestra.json"
    ".codex/config.orchestra.toml"
    "CLAUDE.local.md"
    ".claude/logs/"
    ".claude/checkpoints/"
    ".orchestra-backup-*/"
)

AUTO_YES=false
FORCE=false
TARGET_ARG="."
TARGET_SET=false
TARGET_ROOT=""
BACKUP_ROOT=""
CONFLICTS=()

info() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
error() { echo "[ERROR] $*" >&2; }

usage() {
    cat <<'EOF'
Usage: scripts/install.sh [OPTIONS] [TARGET_DIR]

Install Claude Code Orchestra into an existing Git repository.

Options:
  -y, --yes    Skip confirmation prompts
  -f, --force  Back up and replace conflicting template-owned paths
  -h, --help   Show this help message

Existing AGENTS.md and CLAUDE.md content is preserved in .claude/STATE.md.
The template installs the root AGENTS.md router and the CLAUDE.md main-agent
contract as real files. Existing
.claude/settings.json is never overwritten; a merge candidate is written to
.claude/settings.orchestra.json when the files differ.
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y|--yes)
                AUTO_YES=true
                shift
                ;;
            -f|--force)
                FORCE=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            -*)
                error "Unknown option: $1"
                usage >&2
                exit 2
                ;;
            *)
                if [[ "${TARGET_SET}" == true ]]; then
                    error "Only one TARGET_DIR may be specified."
                    exit 2
                fi
                TARGET_ARG="$1"
                TARGET_SET=true
                shift
                ;;
        esac
    done
}

require_source_paths() {
    local path
    for path in "${TEMPLATE_OWNED_DIRS[@]}" \
        "${TEMPLATE_OWNED_FILES[@]}" "${PROJECT_FILES_IF_MISSING[@]}" \
        "AGENTS.md" "CLAUDE.md" ".claude/settings.json" ".codex/config.toml" \
        "VERSION"; do
        if [[ ! -e "${SOURCE_ROOT}/${path}" && ! -L "${SOURCE_ROOT}/${path}" ]]; then
            error "Template source is incomplete: ${path} is missing."
            exit 1
        fi
    done
}

resolve_target() {
    if [[ ! -d "${TARGET_ARG}" ]]; then
        error "Target directory does not exist: ${TARGET_ARG}"
        exit 2
    fi
    TARGET_ROOT="$(cd "${TARGET_ARG}" && pwd -P)"
    if [[ "${TARGET_ROOT}" == "${SOURCE_ROOT}" ]]; then
        error "The template repository cannot be installed into itself."
        error "Use scripts/update.sh to update an existing installation."
        exit 2
    fi
    if ! git -C "${TARGET_ROOT}" rev-parse --is-inside-work-tree &>/dev/null; then
        error "Target is not a Git repository: ${TARGET_ROOT}"
        exit 2
    fi
}

validate_destination_paths() {
    local path resolved parent component current
    local paths=(
        "${TEMPLATE_OWNED_DIRS[@]}"
        "${LEGACY_RUNTIME_PATHS[@]}"
        "${TEMPLATE_OWNED_FILES[@]}"
        "${PROJECT_FILES_IF_MISSING[@]}"
        "AGENTS.md"
        "CLAUDE.md"
        ".claude/settings.json"
        ".claude/settings.orchestra.json"
        ".claude/orchestra-version"
        ".codex/config.toml"
        ".codex/config.orchestra.toml"
        ".gitignore"
    )
    for path in "${paths[@]}"; do
        current="${TARGET_ROOT}"
        parent="$(dirname "${path}")"
        IFS='/' read -r -a parent_components <<< "${parent}"
        for component in "${parent_components[@]}"; do
            [[ "${component}" == "." || -z "${component}" ]] && continue
            current="${current}/${component}"
            if [[ -L "${current}" ]]; then
                error "Refusing symlinked parent for managed path: ${path}"
                exit 2
            fi
        done

        resolved="$(realpath -m -- "${TARGET_ROOT}/${path}")"
        if [[ "${resolved}" != "${TARGET_ROOT}/"* ]]; then
            error "Refusing path that resolves outside the target: ${path} -> ${resolved}"
            exit 2
        fi
    done
}

validate_project_files() {
    local path destination
    local project_files=(
        "AGENTS.md"
        "CLAUDE.md"
        ".claude/settings.json"
        ".codex/config.toml"
        ".claude/STATE.md"
        ".claude/docs/DESIGN.md"
        ".gitignore"
    )
    for path in "${project_files[@]}"; do
        destination="${TARGET_ROOT}/${path}"
        if [[ -L "${destination}" ]]; then
            # A pre-2.0 CLAUDE.md -> AGENTS.md link is the one symlink we know
            # how to retire: it is backed up as a conflict and replaced with the
            # real contract file. Any other symlink here is still refused.
            if [[ "${path}" != "CLAUDE.md" ]]; then
                error "Refusing project-owned symlink: ${path}"
                exit 2
            fi
            continue
        fi
        if [[ -e "${destination}" && ! -f "${destination}" ]]; then
            error "Expected a regular file at project-owned path: ${path}"
            exit 2
        fi
        if [[ -f "${destination}" && ! -r "${destination}" ]]; then
            error "Project-owned file is not readable: ${path}"
            exit 2
        fi
    done
}

collect_conflicts() {
    local path
    for path in "${TEMPLATE_OWNED_DIRS[@]}" "${LEGACY_RUNTIME_PATHS[@]}" \
        "${TEMPLATE_OWNED_FILES[@]}"; do
        if [[ -e "${TARGET_ROOT}/${path}" || -L "${TARGET_ROOT}/${path}" ]]; then
            CONFLICTS+=("${path}")
        fi
    done

    # A pre-2.0 installation left CLAUDE.md as a symlink to AGENTS.md. Both are
    # real files now, so report the link instead of writing through it.
    if [[ -L "${TARGET_ROOT}/CLAUDE.md" ]]; then
        CONFLICTS+=("CLAUDE.md")
    fi

    if [[ ${#CONFLICTS[@]} -eq 0 ]]; then
        return 0
    fi

    warn "Template-owned paths already exist:"
    printf '  %s\n' "${CONFLICTS[@]}"
    if [[ "${FORCE}" == false ]]; then
        error "Installation stopped before making changes."
        error "Review the paths, then re-run with --force to back up and replace them."
        exit 2
    fi
}

confirm_install() {
    local status
    status="$(git -C "${TARGET_ROOT}" status --porcelain 2>/dev/null || true)"
    if [[ -n "${status}" ]]; then
        warn "The target repository has uncommitted or untracked changes."
    fi
    if [[ "${AUTO_YES}" == true ]]; then
        return 0
    fi

    local response
    read -r -p "Install Orchestra into ${TARGET_ROOT}? [y/N] " response
    case "${response}" in
        [yY]|[yY][eE][sS]) ;;
        *)
            info "Installation cancelled."
            exit 0
            ;;
    esac
}

backup_conflicts() {
    [[ ${#CONFLICTS[@]} -gt 0 ]] || return 0

    BACKUP_ROOT="${TARGET_ROOT}/.orchestra-backup-$(date +%Y%m%d%H%M%S)-$$"
    local path
    for path in "${CONFLICTS[@]}"; do
        mkdir -p "${BACKUP_ROOT}/$(dirname "${path}")"
        cp -a "${TARGET_ROOT}/${path}" "${BACKUP_ROOT}/${path}"
    done
    warn "Conflicting paths were backed up to ${BACKUP_ROOT}"
}

copy_owned_paths() {
    local path destination temporary
    for path in "${TEMPLATE_OWNED_DIRS[@]}"; do
        destination="${TARGET_ROOT}/${path}"
        rm -rf -- "${destination}"
        mkdir -p "$(dirname "${destination}")"
        cp -a "${SOURCE_ROOT}/${path}" "${destination}"
        info "Installed ${path}/"
    done

    for path in "${TEMPLATE_OWNED_FILES[@]}"; do
        destination="${TARGET_ROOT}/${path}"
        mkdir -p "$(dirname "${destination}")"
        temporary="${destination}.tmp.$$"
        cp -a "${SOURCE_ROOT}/${path}" "${temporary}"
        mv -f "${temporary}" "${destination}"
        info "Installed ${path}"
    done
    chmod +x "${TARGET_ROOT}/scripts/check.sh" \
        "${TARGET_ROOT}/scripts/install.sh" "${TARGET_ROOT}/scripts/update.sh"
}

remove_legacy_runtime_paths() {
    local path
    for path in "${LEGACY_RUNTIME_PATHS[@]}" "CLAUDE.md"; do
        if [[ "${path}" == "CLAUDE.md" && ! -L "${TARGET_ROOT}/CLAUDE.md" ]]; then
            continue
        fi
        if [[ -e "${TARGET_ROOT}/${path}" || -L "${TARGET_ROOT}/${path}" ]]; then
            rm -rf -- "${TARGET_ROOT:?}/${path}"
            info "Removed legacy path ${path}"
        fi
    done
}

copy_project_files_if_missing() {
    local path destination
    for path in "${PROJECT_FILES_IF_MISSING[@]}"; do
        destination="${TARGET_ROOT}/${path}"
        if [[ -e "${destination}" || -L "${destination}" ]]; then
            info "Preserved existing ${path}"
            continue
        fi
        mkdir -p "$(dirname "${destination}")"
        cp -a "${SOURCE_ROOT}/${path}" "${destination}"
        info "Installed ${path}"
    done
}

install_agent_files() {
    local existing_agents="${TARGET_ROOT}/AGENTS.md"
    local existing_claude="${TARGET_ROOT}/CLAUDE.md"
    local state="${TARGET_ROOT}/.claude/STATE.md"
    local name source destination temporary
    mkdir -p "${TARGET_ROOT}/.claude/logs" "${TARGET_ROOT}/.claude/checkpoints"

    if [[ -f "${existing_agents}" ]]; then
        {
            echo ""
            echo "<!-- Existing AGENTS.md content preserved by scripts/install.sh. -->"
            echo ""
            cat "${existing_agents}"
        } >> "${state}"
    fi
    if [[ -f "${existing_claude}" ]] \
        && { [[ ! -f "${existing_agents}" ]] || ! cmp -s "${existing_agents}" "${existing_claude}"; }; then
        {
            echo ""
            echo "<!-- Existing CLAUDE.md content preserved by scripts/install.sh. -->"
            echo ""
            cat "${existing_claude}"
        } >> "${state}"
    fi
    for name in "AGENTS.md" "CLAUDE.md"; do
        source="${SOURCE_ROOT}/${name}"
        destination="${TARGET_ROOT}/${name}"
        temporary="${TARGET_ROOT}/.${name}.tmp.$$"
        cp -a "${source}" "${temporary}"
        mv -f "${temporary}" "${destination}"
    done
    info "Installed AGENTS.md and CLAUDE.md; preserved existing instructions in .claude/STATE.md"
}

install_settings() {
    local entry settings_path candidate_path source destination candidate
    for entry in "${NATIVE_SETTINGS[@]}"; do
        settings_path="${entry%%:*}"
        candidate_path="${entry##*:}"
        source="${SOURCE_ROOT}/${settings_path}"
        destination="${TARGET_ROOT}/${settings_path}"
        candidate="${TARGET_ROOT}/${candidate_path}"
        mkdir -p "$(dirname "${destination}")"

        if [[ ! -f "${destination}" ]]; then
            cp -a "${source}" "${destination}"
            info "Installed ${settings_path}"
            continue
        fi
        if cmp -s "${source}" "${destination}"; then
            info "Preserved matching ${settings_path}"
            continue
        fi

        cp -a "${source}" "${candidate}.tmp.$$"
        mv -f "${candidate}.tmp.$$" "${candidate}"
        warn "Preserved existing ${settings_path}."
        warn "Merge required Orchestra settings from ${candidate_path}, then delete the candidate."
    done
}

install_version_marker() {
    local destination="${TARGET_ROOT}/.claude/orchestra-version"
    cp -a "${SOURCE_ROOT}/VERSION" "${destination}.tmp.$$"
    mv -f "${destination}.tmp.$$" "${destination}"
    info "Recorded Orchestra version in .claude/orchestra-version"
}

ensure_gitignore_entries() {
    local gitignore="${TARGET_ROOT}/.gitignore"
    local missing=()
    local entry
    touch "${gitignore}"
    for entry in "${GITIGNORE_ENTRIES[@]}"; do
        if ! grep -Fqx "${entry}" "${gitignore}"; then
            missing+=("${entry}")
        fi
    done
    [[ ${#missing[@]} -gt 0 ]] || return 0

    if [[ -s "${gitignore}" ]]; then
        echo "" >> "${gitignore}"
    fi
    echo "# Claude Code Orchestra local state" >> "${gitignore}"
    printf '%s\n' "${missing[@]}" >> "${gitignore}"
    info "Updated .gitignore with Orchestra local-state paths"
}

print_summary() {
    echo ""
    info "Claude Code Orchestra installation complete."
    info "Project files such as README.md and VERSION were preserved."
    if [[ -f "${TARGET_ROOT}/.claude/settings.orchestra.json" ]]; then
        warn "Complete the settings merge before starting Claude Code."
    else
        info "Next: start Claude Code and run /init."
    fi
}

main() {
    parse_args "$@"
    require_source_paths
    resolve_target
    validate_destination_paths
    validate_project_files
    collect_conflicts
    confirm_install
    backup_conflicts
    remove_legacy_runtime_paths
    copy_owned_paths
    copy_project_files_if_missing
    install_agent_files
    install_settings
    install_version_marker
    ensure_gitignore_entries
    print_summary
}

main "$@"
