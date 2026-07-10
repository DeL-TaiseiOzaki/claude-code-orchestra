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
TEMPLATE_BOUNDARY="@orchestra:template-boundary"
REPO_BOUNDARY="@orchestra:repo-boundary"
LEGACY_BOUNDARY="@orchestra:local-boundary"
BOUNDARY_LINE="# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Directories/files to overwrite entirely from template
SAFE_DIRS=(
    ".claude/skills"
    ".claude/hooks"
    ".claude/rules"
    ".claude/agents"
    ".codex"
    ".agents"
)
SAFE_FILES=(
    ".claude/docs/CODEX_HANDOFF_PLAYBOOK.md"
    ".claude/docs/libraries/_TEMPLATE.md"
    ".claude/docs/reviews/.gitkeep"
    "scripts/update.sh"
    "AGENTS.md"
)

# Paths that previous template versions installed but no longer ship.
# The updater removes these from the local project so that orphans from
# deprecated features (e.g. removed CLI integrations) don't linger.
#
# When you remove an entry from SAFE_DIRS or SAFE_FILES, add the old path
# here so existing projects get cleaned up on their next update.
# Each entry MUST start with "." (a dotfile/dot-dir) to keep the blast
# radius scoped to template-owned locations.
DEPRECATED_PATHS=(
    ".gemini"
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
# Phase 2.5: Remove deprecated paths (orphans from older template versions)
# =============================================================================
# Runs BEFORE sync_safe_dirs so future deprecations that overlap with new
# SAFE_DIRS don't fight rsync. Each entry is validated against several
# defense-in-depth checks before `rm -rf` to prevent foot-guns.
cleanup_deprecated_paths() {
    header "Cleaning Up Deprecated Paths"

    if [[ ${#DEPRECATED_PATHS[@]} -eq 0 ]]; then
        info "No deprecated paths configured."
        return 0
    fi

    local project_root_abs
    project_root_abs="$(cd "${PROJECT_ROOT}" && pwd -P)"

    for path in "${DEPRECATED_PATHS[@]}"; do
        local trimmed="${path//[[:space:]]/}"
        if [[ -z "${trimmed}" ]]; then
            warn "Skipping empty DEPRECATED_PATHS entry."
            continue
        fi
        if [[ "${path}" == "." || "${path}" == "./" ]]; then
            error "Refusing to remove '.' (would target project root). Skipping."
            continue
        fi
        if [[ "${path:0:1}" != "." ]]; then
            error "DEPRECATED_PATHS entry must start with '.': '${path}'. Skipping."
            continue
        fi
        if [[ "${path}" == /* ]]; then
            error "DEPRECATED_PATHS entry must be relative: '${path}'. Skipping."
            continue
        fi
        # Substring catches '.foo/../../etc' as well as leading '..'
        if [[ "${path}" == *".."* ]]; then
            error "DEPRECATED_PATHS entry contains '..': '${path}'. Skipping."
            continue
        fi

        local target="${PROJECT_ROOT}/${path}"

        if [[ ! -e "${target}" && ! -L "${target}" ]]; then
            continue
        fi

        # Escape check: resolve symlinks in parent components and ensure
        # the final target is still strictly inside PROJECT_ROOT.
        local resolved
        resolved="$(realpath -m -- "${target}")"
        if [[ "${resolved}" != "${project_root_abs}/"* ]]; then
            error "Refusing to remove '${path}': resolves outside PROJECT_ROOT (${resolved})."
            continue
        fi
        if [[ "${resolved}" == "${project_root_abs}" ]]; then
            error "Refusing to remove '${path}': resolves to PROJECT_ROOT itself."
            continue
        fi

        warn "Removing deprecated path: ${path}"
        if git -C "${PROJECT_ROOT}" ls-files --error-unmatch -- "${path}" &>/dev/null; then
            git -C "${PROJECT_ROOT}" rm -rf --quiet --ignore-unmatch -- "${path}" \
                || rm -rf -- "${target}"
        else
            rm -rf -- "${target}"
        fi
        UPDATED_FILES+=("REMOVED: ${path}")
    done
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
# Phase 4: Hybrid files (3-zone merge: template | repo-identity | working-state)
# =============================================================================
#
# CLAUDE.md layout:
#   Zone A — Orchestra concept & template base (replaced from new template)
#   @orchestra:template-boundary
#   Zone B — Repository identity (managed by /init, preserved across updates)
#   @orchestra:repo-boundary
#   Zone C — Working state (appended by skills, preserved across updates)
#
# Migration: files using the legacy @orchestra:local-boundary marker are
# auto-migrated — their content below the legacy marker becomes Zone C,
# and Zone B is reset to the template placeholder so /init can populate it.
# Re-running on an already-migrated file is a no-op (idempotent).

# Strip leading blank or ━ separator lines from stdin
_strip_leading_frame() {
    awk '
    started == 0 {
        if ($0 ~ /^[[:space:]]*$/ || $0 ~ /^# ━/) next
        started = 1
    }
    started { print }'
}

# Strip trailing blank or ━ separator lines from stdin
_strip_trailing_frame() {
    awk '
    { buf[NR] = $0 }
    END {
        last = NR
        while (last > 0 && (buf[last] ~ /^[[:space:]]*$/ || buf[last] ~ /^# ━/)) last--
        for (i = 1; i <= last; i++) print buf[i]
    }'
}

# Print content above the first line matching the given marker, with trailing frame stripped
_extract_zone_above() {
    local file="$1"
    local marker="$2"
    awk -v m="${marker}" 'index($0, m) { exit } { print }' "${file}" | _strip_trailing_frame
}

# Print content between marker1 and marker2, with surrounding frames stripped
_extract_zone_between() {
    local file="$1"
    local m1="$2"
    local m2="$3"
    awk -v m1="${m1}" -v m2="${m2}" '
        index($0, m1) { inside = 1; next }
        index($0, m2) { exit }
        inside { print }
    ' "${file}" | _strip_leading_frame | _strip_trailing_frame
}

# Print content after the marker's box, with leading frame stripped
_extract_zone_below() {
    local file="$1"
    local marker="$2"
    awk -v m="${marker}" 'found { print } index($0, m) { found = 1 }' "${file}" | _strip_leading_frame
}

# Detect local CLAUDE.md format: "new" | "legacy" | "none"
_detect_format() {
    local file="$1"
    local has_template=false has_repo=false has_legacy=false
    grep -q "${TEMPLATE_BOUNDARY}" "${file}" 2>/dev/null && has_template=true
    grep -q "${REPO_BOUNDARY}" "${file}" 2>/dev/null && has_repo=true
    grep -q "${LEGACY_BOUNDARY}" "${file}" 2>/dev/null && has_legacy=true

    if [[ "${has_template}" == true && "${has_repo}" == true ]]; then
        echo "new"
    elif [[ "${has_legacy}" == true ]]; then
        echo "legacy"
    else
        echo "none"
    fi
}

# Emit a boundary block (3 lines: ━, marker, ━) to stdout
_emit_boundary_block() {
    local marker="$1"
    echo "${BOUNDARY_LINE}"
    echo "# ${marker}"
    echo "${BOUNDARY_LINE}"
}

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

        local zone_a zone_b zone_c fmt
        zone_a="$(_extract_zone_above "${src}" "${TEMPLATE_BOUNDARY}")"
        fmt="$(_detect_format "${dst}")"

        case "${fmt}" in
            new)
                zone_b="$(_extract_zone_between "${dst}" "${TEMPLATE_BOUNDARY}" "${REPO_BOUNDARY}")"
                zone_c="$(_extract_zone_below "${dst}" "${REPO_BOUNDARY}")"
                ;;
            legacy)
                # Legacy 2-zone layout: below the old marker becomes Zone C.
                # Zone B is reset to the template placeholder so /init can fill it.
                zone_b="$(_extract_zone_between "${src}" "${TEMPLATE_BOUNDARY}" "${REPO_BOUNDARY}")"
                zone_c="$(_extract_zone_below "${dst}" "${LEGACY_BOUNDARY}")"
                warn "Migrated ${file} from legacy @orchestra:local-boundary layout to 3-zone layout."
                warn "  → Re-run /init to populate the new 'Repository Identity' section."
                ;;
            none)
                # No recognizable markers — treat the whole local file as Zone C
                # and add the template's Zone A and Zone B placeholder around it.
                zone_b="$(_extract_zone_between "${src}" "${TEMPLATE_BOUNDARY}" "${REPO_BOUNDARY}")"
                zone_c="$(cat "${dst}")"
                warn "${file} has no recognized boundary markers; wrapping existing content as Zone C."
                warn "  → Re-run /init to populate the new 'Repository Identity' section."
                ;;
        esac

        # Capture the old Zone A for diff reporting (best-effort)
        local old_zone_a=""
        case "${fmt}" in
            new)     old_zone_a="$(_extract_zone_above "${dst}" "${TEMPLATE_BOUNDARY}")" ;;
            legacy)  old_zone_a="$(_extract_zone_above "${dst}" "${LEGACY_BOUNDARY}")" ;;
            none)    old_zone_a="" ;;
        esac

        # Build the merged file
        local merged_file="${TMPDIR_UPDATE}/merged_${file//\//_}"
        {
            printf '%s\n' "${zone_a}"
            echo ""
            _emit_boundary_block "${TEMPLATE_BOUNDARY}"
            echo ""
            printf '%s\n' "${zone_b}"
            echo ""
            _emit_boundary_block "${REPO_BOUNDARY}"
            echo ""
            printf '%s\n' "${zone_c}"
        } > "${merged_file}"

        # Diff the template portion (Zone A) only
        local old_file="${TMPDIR_UPDATE}/old_zone_a"
        local new_file="${TMPDIR_UPDATE}/new_zone_a"
        printf '%s\n' "${old_zone_a}" > "${old_file}"
        printf '%s\n' "${zone_a}" > "${new_file}"

        local zone_a_diff
        zone_a_diff="$(diff -u "${old_file}" "${new_file}" --label "local (Zone A)" --label "new template (Zone A)" 2>/dev/null || true)"

        if [[ -n "${zone_a_diff}" ]]; then
            info "Zone A of ${file} has changed:"
            echo "${zone_a_diff}"
        else
            info "Zone A of ${file} is unchanged."
        fi

        cp -f "${merged_file}" "${dst}"
        UPDATED_FILES+=("${file}")
        info "Merged ${file} (format: ${fmt})"
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
            if [[ "${item}" == REMOVED:* ]]; then
                echo "  ${RED}-${RESET} ${item#REMOVED: }"
            else
                echo "  ${GREEN}+${RESET} ${item}"
            fi
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
    cleanup_deprecated_paths
    sync_safe_dirs
    sync_safe_files
    merge_hybrid_files
    check_settings_files
    update_version
    print_summary

    info "Done!"
}

main "$@"
