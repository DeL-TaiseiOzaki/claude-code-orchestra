#!/usr/bin/env bash
# ==============================================================================
# scripts/update.sh — Claude Code Orchestra Template Updater
#
# Fetches the latest version of the claude-code-orchestra template and safely
# updates local files. Template-owned directories are fully overwritten, while
# hybrid files (CLAUDE.md) use a boundary marker to preserve local customizations.
#
# Usage:
#   ./scripts/update.sh            # Update to latest main
#   ./scripts/update.sh v0.2.0     # Update to a specific tag/ref
#   ./scripts/update.sh --yes      # Skip confirmation prompts
# ==============================================================================
set -euo pipefail

# =============================================================================
# Constants
# =============================================================================
TEMPLATE_REPO="https://github.com/DeL-TaiseiOzaki/claude-code-orchestra.git"
BOUNDARY_MARKER="@orchestra:local-boundary"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Directories/files to overwrite entirely from template
SAFE_DIRS=(
    ".claude/skills"
    ".claude/hooks"
    ".claude/rules"
    ".claude/agents"
    ".codex"
    ".gemini"
)
SAFE_FILES=(
    ".claude/docs/CODEX_HANDOFF_PLAYBOOK.md"
    ".claude/docs/libraries/_TEMPLATE.md"
    "scripts/update.sh"
)

# Hybrid files that use boundary-based merging
HYBRID_FILES=(
    "CLAUDE.md"
)

# Settings files shown as diff only
SETTINGS_FILES=(
    ".claude/settings.json"
)

# =============================================================================
# Color output (with fallback for non-color terminals)
# =============================================================================
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    BOLD=$(tput bold)
    RESET=$(tput sgr0)
else
    GREEN=""
    YELLOW=""
    RED=""
    BOLD=""
    RESET=""
fi

# =============================================================================
# Utility functions
# =============================================================================
info()    { echo "${GREEN}[INFO]${RESET} $*"; }
warn()    { echo "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo "${RED}[ERROR]${RESET} $*" >&2; }
header()  { echo ""; echo "${BOLD}━━━ $* ━━━${RESET}"; }

TMPDIR_UPDATE=""
UPDATED_FILES=()
AUTO_YES=false
TARGET_REF=""

cleanup() {
    if [[ -n "${TMPDIR_UPDATE}" && -d "${TMPDIR_UPDATE}" ]]; then
        rm -rf "${TMPDIR_UPDATE}"
    fi
}
trap cleanup EXIT

# =============================================================================
# Parse arguments
# =============================================================================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y|--yes)
                AUTO_YES=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS] [VERSION_REF]"
                echo ""
                echo "Options:"
                echo "  -y, --yes    Skip confirmation prompts"
                echo "  -h, --help   Show this help message"
                echo ""
                echo "Arguments:"
                echo "  VERSION_REF  Git ref to checkout (tag, branch, commit). Default: main"
                exit 0
                ;;
            -*)
                error "Unknown option: $1"
                exit 1
                ;;
            *)
                TARGET_REF="$1"
                shift
                ;;
        esac
    done
}

# =============================================================================
# Phase 1: Pre-flight checks
# =============================================================================
preflight_checks() {
    header "Pre-flight Checks"

    # Verify we are in a git repo
    if ! git -C "${PROJECT_ROOT}" rev-parse --is-inside-work-tree &>/dev/null; then
        error "Not inside a git repository. Run this script from within your project."
        exit 1
    fi
    info "Git repository detected."

    # Check for uncommitted changes
    if ! git -C "${PROJECT_ROOT}" diff --quiet || ! git -C "${PROJECT_ROOT}" diff --cached --quiet; then
        warn "You have uncommitted changes."
        if [[ "${AUTO_YES}" == false ]]; then
            read -r -p "${YELLOW}Continue anyway? [y/N]${RESET} " response
            case "${response}" in
                [yY][eE][sS]|[yY]) ;;
                *)
                    info "Aborted. Please commit or stash your changes first."
                    exit 0
                    ;;
            esac
        else
            warn "Proceeding despite uncommitted changes (--yes flag)."
        fi
    else
        info "Working tree is clean."
    fi

    # Check for untracked files in paths we will overwrite
    local untracked
    untracked="$(git -C "${PROJECT_ROOT}" ls-files --others --exclude-standard 2>/dev/null || true)"
    if [[ -n "${untracked}" ]]; then
        warn "There are untracked files in the repository."
    fi

    # Read current VERSION
    if [[ -f "${PROJECT_ROOT}/VERSION" ]]; then
        OLD_VERSION="$(cat "${PROJECT_ROOT}/VERSION" | tr -d '[:space:]')"
        info "Current version: ${BOLD}${OLD_VERSION}${RESET}"
    else
        OLD_VERSION="(none)"
        warn "No VERSION file found. This may be a first-time setup."
    fi
}

# =============================================================================
# Phase 2: Fetch latest template
# =============================================================================
fetch_template() {
    header "Fetching Template"

    TMPDIR_UPDATE="$(mktemp -d)"
    info "Cloning template to temporary directory..."

    local clone_args=(--depth 1)
    if [[ -n "${TARGET_REF}" ]]; then
        clone_args+=(--branch "${TARGET_REF}")
        info "Target ref: ${BOLD}${TARGET_REF}${RESET}"
    fi

    if ! git clone "${clone_args[@]}" "${TEMPLATE_REPO}" "${TMPDIR_UPDATE}/template" 2>&1 | tail -1; then
        error "Failed to clone template repository."
        error "URL: ${TEMPLATE_REPO}"
        if [[ -n "${TARGET_REF}" ]]; then
            error "Ref: ${TARGET_REF}"
        fi
        exit 1
    fi

    TEMPLATE_DIR="${TMPDIR_UPDATE}/template"

    # Read new VERSION
    if [[ -f "${TEMPLATE_DIR}/VERSION" ]]; then
        NEW_VERSION="$(cat "${TEMPLATE_DIR}/VERSION" | tr -d '[:space:]')"
    else
        NEW_VERSION="(unknown)"
        warn "Template does not contain a VERSION file."
    fi

    info "Version: ${BOLD}${OLD_VERSION}${RESET} -> ${BOLD}${NEW_VERSION}${RESET}"
}

# =============================================================================
# Phase 3: Safe files (full overwrite)
# =============================================================================
sync_safe_dirs() {
    header "Updating Safe Directories"

    for dir in "${SAFE_DIRS[@]}"; do
        local src="${TEMPLATE_DIR}/${dir}/"
        local dst="${PROJECT_ROOT}/${dir}/"

        if [[ ! -d "${src}" ]]; then
            warn "Template does not contain ${dir}/, skipping."
            continue
        fi

        mkdir -p "${dst}"
        rsync -a --delete "${src}" "${dst}"
        info "Synced ${dir}/"
        UPDATED_FILES+=("${dir}/")
    done
}

sync_safe_files() {
    header "Updating Safe Files"

    for file in "${SAFE_FILES[@]}"; do
        local src="${TEMPLATE_DIR}/${file}"
        local dst="${PROJECT_ROOT}/${file}"

        if [[ ! -f "${src}" ]]; then
            warn "Template does not contain ${file}, skipping."
            continue
        fi

        mkdir -p "$(dirname "${dst}")"
        cp -f "${src}" "${dst}"
        info "Updated ${file}"
        UPDATED_FILES+=("${file}")
    done

    # Ensure scripts/update.sh stays executable after self-update
    if [[ -f "${PROJECT_ROOT}/scripts/update.sh" ]]; then
        chmod +x "${PROJECT_ROOT}/scripts/update.sh"
    fi
}

# =============================================================================
# Phase 4: Hybrid files (smart merge using separator)
# =============================================================================
merge_hybrid_files() {
    header "Merging Hybrid Files"

    for file in "${HYBRID_FILES[@]}"; do
        local src="${TEMPLATE_DIR}/${file}"
        local dst="${PROJECT_ROOT}/${file}"

        if [[ ! -f "${src}" ]]; then
            warn "Template does not contain ${file}, skipping."
            continue
        fi

        if [[ ! -f "${dst}" ]]; then
            info "Local ${file} does not exist. Copying from template."
            cp -f "${src}" "${dst}"
            UPDATED_FILES+=("${file}")
            continue
        fi

        local template_has_boundary=false
        local local_has_boundary=false

        if grep -q "${BOUNDARY_MARKER}" "${src}" 2>/dev/null; then
            template_has_boundary=true
        fi
        if grep -q "${BOUNDARY_MARKER}" "${dst}" 2>/dev/null; then
            local_has_boundary=true
        fi

        # Extract template part (above boundary) from new template
        local new_template_part
        if [[ "${template_has_boundary}" == true ]]; then
            # Get everything up to (but not including) the first boundary marker line
            new_template_part="$(awk "/${BOUNDARY_MARKER}/{found=1} !found{print}" "${src}")"
        else
            # No boundary in template; use the entire file
            new_template_part="$(cat "${src}")"
        fi

        # Extract local part (boundary line and everything below) from local file
        local local_below_boundary
        if [[ "${local_has_boundary}" == true ]]; then
            # Get the boundary block and everything below it
            # Find the line number of the first separator line before the boundary marker
            local boundary_line_num
            boundary_line_num="$(grep -n "${BOUNDARY_MARKER}" "${dst}" | head -1 | cut -d: -f1)"
            # Look backwards from the boundary marker to find the separator block start
            # The block is: separator line, marker line, separator line
            local block_start=$((boundary_line_num - 1))
            # Check if the line before is a separator line
            local line_before
            line_before="$(sed -n "${block_start}p" "${dst}")"
            if echo "${line_before}" | grep -q "^# ━"; then
                block_start=$((block_start))
            else
                block_start=$((boundary_line_num))
            fi
            # Also check for blank line before the block
            local blank_check=$((block_start - 1))
            if [[ ${blank_check} -ge 1 ]]; then
                local check_line
                check_line="$(sed -n "${blank_check}p" "${dst}")"
                if [[ -z "${check_line}" ]]; then
                    block_start=${blank_check}
                fi
            fi
            local_below_boundary="$(tail -n +"${block_start}" "${dst}")"
        else
            # No boundary in local file; treat entire local file as local content
            # We will prepend the template part + boundary
            local_below_boundary=""
        fi

        # Save old template portion for diff
        local old_template_part=""
        if [[ "${local_has_boundary}" == true ]]; then
            local boundary_line_num
            boundary_line_num="$(grep -n "${BOUNDARY_MARKER}" "${dst}" | head -1 | cut -d: -f1)"
            local block_start=$((boundary_line_num - 1))
            local line_before
            line_before="$(sed -n "${block_start}p" "${dst}")"
            if echo "${line_before}" | grep -q "^# ━"; then
                block_start=$((block_start))
            else
                block_start=$((boundary_line_num))
            fi
            local blank_check=$((block_start - 1))
            if [[ ${blank_check} -ge 1 ]]; then
                local check_line
                check_line="$(sed -n "${blank_check}p" "${dst}")"
                if [[ -z "${check_line}" ]]; then
                    block_start=${blank_check}
                fi
            fi
            # Everything before the block start is the old template part
            local lines_before=$((block_start - 1))
            if [[ ${lines_before} -gt 0 ]]; then
                old_template_part="$(head -n "${lines_before}" "${dst}")"
            fi
        else
            old_template_part="$(cat "${dst}")"
        fi

        # Build the merged file
        local merged_file="${TMPDIR_UPDATE}/merged_${file//\//_}"

        if [[ "${local_has_boundary}" == true ]]; then
            # Template part + local boundary and below
            {
                echo "${new_template_part}"
                echo "${local_below_boundary}"
            } > "${merged_file}"
        else
            # No boundary in local file: prepend template + boundary + original content
            {
                echo "${new_template_part}"
                echo ""
                echo "# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo "# ${BOUNDARY_MARKER}"
                echo "# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo ""
                cat "${dst}"
            } > "${merged_file}"
        fi

        # Show diff of the template portion
        local old_part_file="${TMPDIR_UPDATE}/old_template_part"
        local new_part_file="${TMPDIR_UPDATE}/new_template_part"
        echo "${old_template_part}" > "${old_part_file}"
        echo "${new_template_part}" > "${new_part_file}"

        local template_diff
        template_diff="$(diff -u "${old_part_file}" "${new_part_file}" --label "local (template section)" --label "new template" 2>/dev/null || true)"

        if [[ -n "${template_diff}" ]]; then
            info "Template portion of ${file} has changed:"
            echo "${template_diff}"
        else
            info "Template portion of ${file} is unchanged."
        fi

        cp -f "${merged_file}" "${dst}"
        UPDATED_FILES+=("${file}")
        info "Merged ${file}"
    done
}

# =============================================================================
# Phase 5: Settings files (diff only, no auto-merge)
# =============================================================================
check_settings_files() {
    header "Checking Settings Files"

    for file in "${SETTINGS_FILES[@]}"; do
        local src="${TEMPLATE_DIR}/${file}"
        local dst="${PROJECT_ROOT}/${file}"

        if [[ ! -f "${src}" ]]; then
            warn "Template does not contain ${file}, skipping."
            continue
        fi

        if [[ ! -f "${dst}" ]]; then
            info "Local ${file} does not exist. You may want to copy it from the template."
            info "  cp ${src} ${dst}"
            continue
        fi

        local settings_diff
        settings_diff="$(diff -u "${dst}" "${src}" --label "local" --label "template" 2>/dev/null || true)"

        if [[ -n "${settings_diff}" ]]; then
            warn "${file} differs from template (NOT auto-merged):"
            echo "${settings_diff}"
            echo ""
            warn "Please review and merge ${file} manually."
        else
            info "${file} matches template. No action needed."
        fi
    done
}

# =============================================================================
# Phase 6: VERSION update
# =============================================================================
update_version() {
    header "Updating VERSION"

    if [[ -f "${TEMPLATE_DIR}/VERSION" ]]; then
        cp -f "${TEMPLATE_DIR}/VERSION" "${PROJECT_ROOT}/VERSION"
        info "VERSION updated to ${BOLD}${NEW_VERSION}${RESET}"
        UPDATED_FILES+=("VERSION")
    else
        warn "No VERSION file in template. Skipping version update."
    fi
}

# =============================================================================
# Phase 7: Summary
# =============================================================================
print_summary() {
    header "Update Summary"

    echo ""
    info "Version: ${BOLD}${OLD_VERSION}${RESET} -> ${BOLD}${NEW_VERSION}${RESET}"
    echo ""

    if [[ ${#UPDATED_FILES[@]} -gt 0 ]]; then
        info "Updated files/directories:"
        for item in "${UPDATED_FILES[@]}"; do
            echo "  ${GREEN}+${RESET} ${item}"
        done
    else
        info "No files were updated."
    fi

    echo ""

    # Check if settings file differed
    for file in "${SETTINGS_FILES[@]}"; do
        local src="${TEMPLATE_DIR}/${file}"
        local dst="${PROJECT_ROOT}/${file}"
        if [[ -f "${src}" && -f "${dst}" ]]; then
            local settings_diff
            settings_diff="$(diff -q "${dst}" "${src}" 2>/dev/null || true)"
            if [[ -n "${settings_diff}" ]]; then
                warn "Remember to review and manually merge: ${BOLD}${file}${RESET}"
            fi
        fi
    done

    echo ""
    info "Please review the changes and commit when ready:"
    echo "  git add -A && git commit -m \"chore: update orchestra template to ${NEW_VERSION}\""
    echo ""
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo "${BOLD}Claude Code Orchestra — Template Updater${RESET}"

    parse_args "$@"
    preflight_checks
    fetch_template
    sync_safe_dirs
    sync_safe_files
    merge_hybrid_files
    check_settings_files
    update_version
    print_summary

    info "Done!"
}

main "$@"
