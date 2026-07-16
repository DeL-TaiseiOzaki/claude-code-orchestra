#!/usr/bin/env bash
# Install Claude Code Orchestra into an existing Git repository.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
TEMPLATE_BOUNDARY="@orchestra:template-boundary"
REPO_BOUNDARY="@orchestra:repo-boundary"
LEGACY_BOUNDARY="@orchestra:local-boundary"

TEMPLATE_OWNED_DIRS=(
    ".claude/skills"
    ".claude/hooks"
    ".claude/rules"
    ".claude/agents"
    ".codex"
    ".agents"
)
TEMPLATE_OWNED_FILES=(
    ".claude/docs/CODEX_HANDOFF_PLAYBOOK.md"
    ".claude/docs/libraries/.gitkeep"
    ".claude/docs/reviews/.gitkeep"
    "scripts/install.sh"
    "scripts/update.sh"
    "AGENTS.md"
)
PROJECT_FILES_IF_MISSING=(
    ".claude/docs/DESIGN.md"
    ".claude/docs/research/.gitkeep"
)
GITIGNORE_ENTRIES=(
    ".claude/settings.local.json"
    ".claude/settings.orchestra.json"
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

Existing CLAUDE.md content is preserved in Zone C. Existing
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
    for path in "${TEMPLATE_OWNED_DIRS[@]}" "${TEMPLATE_OWNED_FILES[@]}" \
        "${PROJECT_FILES_IF_MISSING[@]}" "CLAUDE.md" ".claude/settings.json" \
        "VERSION"; do
        if [[ ! -e "${SOURCE_ROOT}/${path}" ]]; then
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
        "${TEMPLATE_OWNED_FILES[@]}"
        "${PROJECT_FILES_IF_MISSING[@]}"
        "CLAUDE.md"
        ".claude/settings.json"
        ".claude/settings.orchestra.json"
        ".claude/orchestra-version"
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
        "CLAUDE.md"
        ".claude/settings.json"
        ".claude/docs/DESIGN.md"
        ".gitignore"
    )
    for path in "${project_files[@]}"; do
        destination="${TARGET_ROOT}/${path}"
        if [[ -L "${destination}" ]]; then
            error "Refusing project-owned symlink: ${path}"
            exit 2
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

check_claude_md_format() {
    local claude_md="${TARGET_ROOT}/CLAUDE.md"
    [[ -f "${claude_md}" ]] || return 0

    if grep -q "${TEMPLATE_BOUNDARY}\|${REPO_BOUNDARY}\|${LEGACY_BOUNDARY}" \
        "${claude_md}"; then
        error "CLAUDE.md already contains Orchestra boundary markers."
        error "Use the existing scripts/update.sh instead of the installer."
        exit 2
    fi
}

collect_conflicts() {
    local path
    for path in "${TEMPLATE_OWNED_DIRS[@]}" "${TEMPLATE_OWNED_FILES[@]}"; do
        if [[ -e "${TARGET_ROOT}/${path}" || -L "${TARGET_ROOT}/${path}" ]]; then
            CONFLICTS+=("${path}")
        fi
    done

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
    chmod +x "${TARGET_ROOT}/scripts/install.sh" "${TARGET_ROOT}/scripts/update.sh"
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

install_claude_md() {
    local source="${SOURCE_ROOT}/CLAUDE.md"
    local destination="${TARGET_ROOT}/CLAUDE.md"
    local temporary="${TARGET_ROOT}/.CLAUDE.md.tmp.$$"

    if [[ ! -f "${destination}" ]]; then
        cp -a "${source}" "${destination}"
        info "Installed CLAUDE.md"
        return 0
    fi

    cp -a "${source}" "${temporary}"
    {
        echo ""
        echo "<!-- Existing CLAUDE.md content preserved by scripts/install.sh. -->"
        echo ""
        cat "${destination}"
    } >> "${temporary}"
    mv -f "${temporary}" "${destination}"
    info "Installed CLAUDE.md and preserved existing content in Zone C"
}

install_settings() {
    local source="${SOURCE_ROOT}/.claude/settings.json"
    local destination="${TARGET_ROOT}/.claude/settings.json"
    local candidate="${TARGET_ROOT}/.claude/settings.orchestra.json"
    mkdir -p "${TARGET_ROOT}/.claude"

    if [[ ! -f "${destination}" ]]; then
        cp -a "${source}" "${destination}"
        info "Installed .claude/settings.json"
        return 0
    fi
    if cmp -s "${source}" "${destination}"; then
        info "Preserved matching .claude/settings.json"
        return 0
    fi

    cp -a "${source}" "${candidate}.tmp.$$"
    mv -f "${candidate}.tmp.$$" "${candidate}"
    warn "Preserved existing .claude/settings.json."
    warn "Merge required Orchestra settings from .claude/settings.orchestra.json, then delete the candidate."
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
    check_claude_md_format
    collect_conflicts
    confirm_install
    backup_conflicts
    copy_owned_paths
    copy_project_files_if_missing
    install_claude_md
    install_settings
    install_version_marker
    ensure_gitignore_entries
    print_summary
}

main "$@"
