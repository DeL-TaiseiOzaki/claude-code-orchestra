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
# Claude Code (>= 2.1.277) skips AGENTS.md while any of these exists in the
# project or a parent, so install backs each one up and removes it. A file that
# only imports "@AGENTS.md" is the documented manual fallback and is kept.
INSTRUCTION_SHADOW_FILES=(
    "CLAUDE.md"
    "CLAUDE.local.md"
    ".claude/CLAUDE.md"
)
PENDING_MERGE_HEADING="## Pending Instruction Merge"
GITIGNORE_ENTRIES=(
    ".claude/settings.local.json"
    ".claude/settings.orchestra.json"
    ".codex/config.orchestra.toml"
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
PENDING_MERGE_ENTRIES=()

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

The template installs the root AGENTS.md skeleton; run /start-project in
Claude Code afterwards to convert it into the project's own instructions.
Existing CLAUDE.md, CLAUDE.local.md, and .claude/CLAUDE.md files stop Claude
Code from loading AGENTS.md, so they are backed up to .orchestra-backup-*/ and
removed; an existing AGENTS.md is backed up before the skeleton replaces it.
Each backup is printed and recorded under "## Pending Instruction Merge" in
.claude/STATE.md so /start-project can offer to merge it. Existing
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
        "AGENTS.md" ".claude/settings.json" ".codex/config.toml" \
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
        "${INSTRUCTION_SHADOW_FILES[@]}"
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

is_instruction_shadow_file() {
    local candidate="$1" name
    for name in "${INSTRUCTION_SHADOW_FILES[@]}"; do
        [[ "${candidate}" == "${name}" ]] && return 0
    done
    return 1
}

# A file whose only content is "@AGENTS.md" imports AGENTS.md instead of
# shadowing it (the README's manual fallback); it is left in place.
is_agents_shim() {
    [[ -f "$1" && ! -L "$1" && "$(tr -d '[:space:]' < "$1")" == "@AGENTS.md" ]]
}

validate_project_files() {
    local path destination
    local project_files=(
        "AGENTS.md"
        "${INSTRUCTION_SHADOW_FILES[@]}"
        ".claude/settings.json"
        ".codex/config.toml"
        ".claude/STATE.md"
        ".claude/docs/DESIGN.md"
        ".gitignore"
    )
    for path in "${project_files[@]}"; do
        destination="${TARGET_ROOT}/${path}"
        if [[ -L "${destination}" ]]; then
            # A CLAUDE.md-family link (pre-2.0 installs shipped CLAUDE.md ->
            # AGENTS.md) is backed up as a link and removed, never followed.
            # Any other symlink here is still refused.
            if ! is_instruction_shadow_file "${path}"; then
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

ensure_backup_root() {
    if [[ -z "${BACKUP_ROOT}" ]]; then
        BACKUP_ROOT="${TARGET_ROOT}/.orchestra-backup-$(date +%Y%m%d%H%M%S)-$$"
    fi
}

backup_conflicts() {
    [[ ${#CONFLICTS[@]} -gt 0 ]] || return 0

    ensure_backup_root
    local path
    for path in "${CONFLICTS[@]}"; do
        mkdir -p "${BACKUP_ROOT}/$(dirname "${path}")"
        cp -a "${TARGET_ROOT}/${path}" "${BACKUP_ROOT}/${path}"
    done
    warn "Conflicting paths were backed up to ${BACKUP_ROOT}"
}

# Remove ignored Python bytecode that cp -a copied from the local working tree.
# Scoped strictly to the destination path passed in.
prune_bytecode() {
    local destination="$1"
    [[ -d "${destination}" ]] || return 0
    find "${destination}" -name __pycache__ -type d -prune -exec rm -rf -- {} +
    find "${destination}" -name '*.pyc' -type f -delete
}

copy_owned_paths() {
    local path destination temporary
    for path in "${TEMPLATE_OWNED_DIRS[@]}"; do
        destination="${TARGET_ROOT}/${path}"
        rm -rf -- "${destination}"
        mkdir -p "$(dirname "${destination}")"
        cp -a "${SOURCE_ROOT}/${path}" "${destination}"
        prune_bytecode "${destination}"
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
    for path in "${LEGACY_RUNTIME_PATHS[@]}"; do
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

# Back up one project file into BACKUP_ROOT and queue a pending-merge entry
# for .claude/STATE.md. A symlink that resolves to a regular file is backed up
# as that content, so the backup stays readable after it moves; a dangling
# link is kept as a link.
backup_instruction_file() {
    local path="$1" note="$2" backup_rel source
    source="${TARGET_ROOT}/${path}"
    ensure_backup_root
    mkdir -p "${BACKUP_ROOT}/$(dirname "${path}")"
    if [[ -L "${source}" && -f "${source}" ]]; then
        cp -L -- "${source}" "${BACKUP_ROOT}/${path}"
    else
        cp -a -- "${source}" "${BACKUP_ROOT}/${path}"
    fi
    backup_rel="${BACKUP_ROOT#"${TARGET_ROOT}/"}/${path}"
    PENDING_MERGE_ENTRIES+=("\`${path}\` backed up to \`${backup_rel}\` and ${note} (scripts/install.sh)")
    warn "Backed up ${path} to ${backup_rel} (${note})"
}

# How a removed instruction file is labelled for /start-project: only the
# pre-2.0 CLAUDE.md -> AGENTS.md link is known to need no merge.
instruction_file_note() {
    local destination="$1" link_target
    if [[ ! -L "${destination}" ]]; then
        echo "removed: Claude Code skips AGENTS.md while it exists"
        return 0
    fi
    link_target="$(readlink -- "${destination}")"
    if [[ ! -e "${destination}" ]]; then
        echo "removed: dangling symlink to ${link_target}, kept as a link"
    elif [[ "$(realpath -- "${destination}")" == "$(realpath -m -- "${TARGET_ROOT}/AGENTS.md")" ]]; then
        echo "removed: legacy symlink to AGENTS.md, no merge needed"
    else
        echo "removed: symlink to ${link_target}, content copied, review for merge"
    fi
}

retire_instruction_shadow_files() {
    local path destination
    for path in "${INSTRUCTION_SHADOW_FILES[@]}"; do
        destination="${TARGET_ROOT}/${path}"
        [[ -e "${destination}" || -L "${destination}" ]] || continue
        if is_agents_shim "${destination}"; then
            info "Kept ${path}: it only imports @AGENTS.md"
            continue
        fi
        backup_instruction_file "${path}" "$(instruction_file_note "${destination}")"
        rm -f -- "${destination}"
    done
}

# Append queued entries under "## Pending Instruction Merge" in STATE.md,
# creating the section at the end of the file when it is absent.
record_pending_merge() {
    [[ ${#PENDING_MERGE_ENTRIES[@]} -gt 0 ]] || return 0
    local state="${TARGET_ROOT}/.claude/STATE.md" entries="" entry
    for entry in "${PENDING_MERGE_ENTRIES[@]}"; do
        entries+="- ${entry}"$'\n'
    done
    if ! grep -Fqx "${PENDING_MERGE_HEADING}" "${state}"; then
        {
            echo ""
            echo "${PENDING_MERGE_HEADING}"
            echo ""
            echo "<!-- Written by scripts/install.sh and scripts/update.sh. /start-project offers to merge these backups into AGENTS.md, then removes this section. -->"
            echo ""
        } >> "${state}"
        printf '%s' "${entries}" >> "${state}"
    else
        awk -v heading="${PENDING_MERGE_HEADING}" -v entries="${entries}" '
            $0 == heading { inside = 1; print; next }
            inside && /^## / { printf "%s\n", entries; inside = 0 }
            { print }
            END { if (inside) printf "%s", entries }
        ' "${state}" > "${state}.tmp.$$"
        mv -f "${state}.tmp.$$" "${state}"
    fi
    info "Recorded ${#PENDING_MERGE_ENTRIES[@]} backup(s) under '${PENDING_MERGE_HEADING}' in .claude/STATE.md"
}

install_agent_files() {
    local existing_agents="${TARGET_ROOT}/AGENTS.md"
    local source="${SOURCE_ROOT}/AGENTS.md"
    local temporary="${TARGET_ROOT}/.AGENTS.md.tmp.$$"
    mkdir -p "${TARGET_ROOT}/.claude/logs" "${TARGET_ROOT}/.claude/checkpoints"

    retire_instruction_shadow_files
    if [[ -f "${existing_agents}" ]] && cmp -s "${source}" "${existing_agents}"; then
        info "AGENTS.md already matches the template skeleton"
    elif [[ -f "${existing_agents}" ]] \
        && grep -Fxq "## Agent Roles" "${existing_agents}" \
        && grep -Fxq "## Orchestra References" "${existing_agents}"; then
        info "Preserved project-owned AGENTS.md (already in Orchestra format)"
    else
        if [[ -f "${existing_agents}" ]]; then
            backup_instruction_file "AGENTS.md" "replaced by the Orchestra skeleton"
        fi
        cp -a "${source}" "${temporary}"
        mv -f "${temporary}" "${existing_agents}"
        info "Installed the AGENTS.md skeleton; run /start-project to convert it"
    fi
    record_pending_merge
}

warn_ancestor_shadowing() {
    local dir name path user_memory="${HOME:-/nonexistent}/.claude/CLAUDE.md"
    dir="$(dirname "${TARGET_ROOT}")"
    while :; do
        for name in "${INSTRUCTION_SHADOW_FILES[@]}"; do
            path="${dir%/}/${name}"
            [[ "${path}" == "${user_memory}" ]] && continue
            if [[ -f "${path}" ]] && ! is_agents_shim "${path}"; then
                warn "${path} (a parent directory) makes Claude Code skip AGENTS.md here."
            fi
        done
        [[ "${dir}" == "/" ]] && break
        dir="$(dirname "${dir}")"
    done
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
    warn_ancestor_shadowing
    if [[ ${#PENDING_MERGE_ENTRIES[@]} -gt 0 ]]; then
        warn "Backed-up instruction files (offered for merging by /start-project):"
        printf '  %s\n' "${PENDING_MERGE_ENTRIES[@]}"
    fi
    if [[ -f "${TARGET_ROOT}/.claude/settings.orchestra.json" ]]; then
        warn "Complete the settings merge before starting Claude Code."
    else
        info "Next: start Claude Code and run /start-project (not the built-in /init, which creates CLAUDE.md)."
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
