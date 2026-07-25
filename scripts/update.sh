#!/usr/bin/env bash
# ==============================================================================
# scripts/update.sh — Claude Code Orchestra Template Updater
#
# Fetches the latest version of the claude-code-orchestra template and safely
# updates local files. Template-owned content is centralized under .agents/;
# mutable project context is preserved in .agents/STATE.md and .agents/docs/.
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
TEMPLATE_REPO="${ORCHESTRA_TEMPLATE_REPO:-https://github.com/DeL-TaiseiOzaki/claude-code-orchestra.git}"
LOCAL_VERSION_FILE=".claude/orchestra-version"
TEMPLATE_BOUNDARY="@orchestra:template-boundary"
REPO_BOUNDARY="@orchestra:repo-boundary"
LEGACY_BOUNDARY="@orchestra:local-boundary"
BOUNDARY_LINE="# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Directories/files to overwrite entirely from template
SAFE_DIRS=(
    ".codex"
    ".agents/rules"
    ".agents/skills"
    ".agents/agents"
    ".agents/hooks"
    ".agents/workflows"
)
SAFE_FILES=(
    "AGENTS.md"
    ".agents/INDEX.md"
    ".agents/check.sh"
    ".agents/change_main.md"
    ".agents/docs/CODEX_HANDOFF_PLAYBOOK.md"
    ".agents/docs/libraries/.gitkeep"
    ".agents/docs/reviews/.gitkeep"
    "scripts/install.sh"
    "scripts/update.sh"
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
    ".claude/checkpoints"
    ".claude/docs"
    ".claude/hooks"
    ".claude/logs"
    ".claude/rules"
    ".codex/skills"
)

# Native discovery symlinks kept in sync on every update. Product-native
# runtimes (Claude Code) auto-discover subagents and skills only from their own
# directories, which cannot be configured to point elsewhere. Linking those
# native paths to the canonical .agents/ directories gives native
# auto-discovery while .agents/ stays the single physical source.
# Format: "<native-path>:<relative-target>" (target resolved from .claude/).
NATIVE_DISCOVERY_LINKS=(
    ".claude/agents:../.agents/agents"
    ".claude/skills:../.agents/skills"
)

LEGACY_PROJECT_DIRS=(
    "docs"
    "logs"
    "checkpoints"
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
SELF_UPDATED=false

# In-flight stage-and-swap tracking (see sync_safe_dirs). At most one
# SAFE_DIR is mid-transition at a time since the loop is sequential; the
# trap below inspects these to roll back a crash cleanly.
CURRENT_STAGING_DIR=""
CURRENT_OLD_DIR=""
CURRENT_LIVE_DIR=""
SWAP_IN_PROGRESS=false

cleanup() {
    # Roll back a stage-and-swap that was interrupted mid-transition: the
    # live directory has already been renamed to CURRENT_OLD_DIR but the
    # staged replacement has not yet been moved into place. Restore the
    # original so the target repo is never left without the directory.
    if [[ "${SWAP_IN_PROGRESS}" == true && -n "${CURRENT_OLD_DIR}" && -d "${CURRENT_OLD_DIR}" ]]; then
        rm -rf "${CURRENT_LIVE_DIR}"
        mv "${CURRENT_OLD_DIR}" "${CURRENT_LIVE_DIR}"
    fi
    # Remove any leftover staging directory (either the swap never started,
    # or it already completed and this is just belt-and-suspenders).
    if [[ -n "${CURRENT_STAGING_DIR}" && -d "${CURRENT_STAGING_DIR}" ]]; then
        rm -rf "${CURRENT_STAGING_DIR}"
    fi
    # Remove a leftover .orchestra-old.$$ if the swap completed but cleanup
    # of the old copy was interrupted.
    if [[ -n "${CURRENT_OLD_DIR}" && -d "${CURRENT_OLD_DIR}" ]]; then
        rm -rf "${CURRENT_OLD_DIR}"
    fi

    if [[ -n "${TMPDIR_UPDATE}" && -d "${TMPDIR_UPDATE}" ]]; then
        rm -rf "${TMPDIR_UPDATE}"
    fi
}
trap cleanup EXIT INT TERM

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

    # Read the installed Orchestra version. The repository's root VERSION,
    # when present, belongs to the downstream project and is never touched.
    if [[ -f "${PROJECT_ROOT}/${LOCAL_VERSION_FILE}" ]]; then
        OLD_VERSION="$(tr -d '[:space:]' < "${PROJECT_ROOT}/${LOCAL_VERSION_FILE}")"
        info "Current version: ${BOLD}${OLD_VERSION}${RESET}"
    else
        OLD_VERSION="(none)"
        warn "No ${LOCAL_VERSION_FILE} found. This may be a first-time setup."
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

migrate_legacy_native_data() {
    header "Migrating Legacy Native Data"

    local name legacy canonical backup_root=""
    for name in "${LEGACY_PROJECT_DIRS[@]}"; do
        legacy="${PROJECT_ROOT}/.claude/${name}"
        canonical="${PROJECT_ROOT}/.agents/${name}"
        if [[ ! -d "${legacy}" || -L "${legacy}" ]]; then
            continue
        fi

        if [[ ! -e "${canonical}" ]] ||
            [[ -d "${canonical}" && -z "$(find "${canonical}" -mindepth 1 -print -quit)" ]]; then
            rm -rf -- "${canonical}"
            mkdir -p "$(dirname "${canonical}")"
            mv -- "${legacy}" "${canonical}"
            UPDATED_FILES+=(".agents/${name} (migrated from .claude/${name})")
            continue
        fi

        if [[ -z "${backup_root}" ]]; then
            backup_root="${PROJECT_ROOT}/.orchestra-backup-native-migration-$(date +%Y%m%d%H%M%S)-$$"
        fi
        mkdir -p "${backup_root}/.claude" "${canonical}"
        cp -a -- "${legacy}" "${backup_root}/.claude/${name}"
        cp -an -- "${legacy}/." "${canonical}/"
        UPDATED_FILES+=(".agents/${name} (merged from .claude/${name})")
    done

    if [[ -n "${backup_root}" ]]; then
        warn "Legacy native data was backed up before merging: ${backup_root}"
    fi
}

# =============================================================================
# Phase 3: Safe files (full overwrite)
# =============================================================================
# Stage-and-swap keeps a crash (Ctrl-C, power loss, copy failure) from ever
# leaving a SAFE_DIR half-updated. Each directory is staged and swapped
# independently: a mid-run interruption may leave later SAFE_DIRS un-synced
# (the update is simply incomplete and re-runnable), but it can never corrupt
# a directory that was in flight. The staging/old siblings live inside the
# target repo (same filesystem as the destination) so the final `mv` swaps
# are atomic renames, not copies.
sync_safe_dirs() {
    header "Updating Safe Directories"

    for dir in "${SAFE_DIRS[@]}"; do
        local src="${TEMPLATE_DIR}/${dir}/"
        local dst="${PROJECT_ROOT}/${dir}"

        if [[ ! -d "${src}" ]]; then
            warn "Template does not contain ${dir}/, skipping."
            continue
        fi

        local staging="${dst}.orchestra-staging.$$"
        local old="${dst}.orchestra-old.$$"
        rm -rf "${staging}" "${old}"
        mkdir -p "${staging}"

        # Track in-flight state so the EXIT/INT/TERM trap can roll back if
        # anything below fails or the process is interrupted.
        CURRENT_STAGING_DIR="${staging}"
        CURRENT_OLD_DIR="${old}"
        CURRENT_LIVE_DIR="${dst}"
        SWAP_IN_PROGRESS=false

        # `cp -a` rather than rsync: the staging directory was just created
        # empty, so rsync's --delete had nothing to delete and its only job
        # here was an attribute-preserving tree copy. rsync is absent from
        # minimal images (containers, CI runners), where the updater died with
        # exit 127 partway through; cp ships with coreutils everywhere.
        # The trailing "." copies dotfiles too and preserves symlinks.
        cp -a "${src}." "${staging}/"

        if [[ -d "${dst}" ]]; then
            SWAP_IN_PROGRESS=true
            mv "${dst}" "${old}"
            mv "${staging}" "${dst}"
            SWAP_IN_PROGRESS=false
            rm -rf "${old}"
        else
            mkdir -p "$(dirname "${dst}")"
            mv "${staging}" "${dst}"
        fi

        # Swap completed; clear in-flight tracking so the trap is a no-op
        # for this directory.
        CURRENT_STAGING_DIR=""
        CURRENT_OLD_DIR=""
        CURRENT_LIVE_DIR=""

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
        if [[ "${file}" == "scripts/update.sh" && -f "${dst}" ]] \
            && ! cmp -s "${src}" "${dst}"; then
            SELF_UPDATED=true
        fi
        # Copy via temp + mv: an atomic rename gives the destination a new
        # inode, so the running update.sh keeps reading its original file
        # instead of a half-overwritten one (self-update safety).
        cp -f "${src}" "${dst}.tmp.$$"
        mv -f "${dst}.tmp.$$" "${dst}"
        info "Updated ${file}"
        UPDATED_FILES+=("${file}")
    done

    # Ensure scripts/update.sh stays executable after self-update
    if [[ -f "${PROJECT_ROOT}/scripts/update.sh" ]]; then
        chmod +x "${PROJECT_ROOT}/scripts/update.sh"
    fi
}

# =============================================================================
# Phase 4: Legacy state migration
# =============================================================================
#
# Current releases keep AGENTS.md immutable and store mutable context in
# .agents/STATE.md. Boundary helpers remain only to migrate older 2/3-zone
# AGENTS.md or CLAUDE.md files before the minimal bootstrap overwrites them.

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

# Detect a local agent-contract format: "new" | "legacy" | "none"
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

migrate_legacy_agent_state() {
    header "Preserving Agent State"

    local state="${PROJECT_ROOT}/.agents/STATE.md"
    mkdir -p "${PROJECT_ROOT}/.agents/docs/research" \
        "${PROJECT_ROOT}/.agents/logs" "${PROJECT_ROOT}/.agents/checkpoints"
    if [[ ! -f "${state}" ]]; then
        cp -f "${TEMPLATE_DIR}/.agents/STATE.md" "${state}"
        UPDATED_FILES+=(".agents/STATE.md")
    fi
    if [[ ! -f "${PROJECT_ROOT}/.agents/docs/DESIGN.md" ]]; then
        cp -f "${TEMPLATE_DIR}/.agents/docs/DESIGN.md" \
            "${PROJECT_ROOT}/.agents/docs/DESIGN.md"
        UPDATED_FILES+=(".agents/docs/DESIGN.md")
    fi

    local source="" fmt="none" label=""
    for label in CLAUDE.md AGENTS.md; do
        local candidate="${PROJECT_ROOT}/${label}"
        [[ -f "${candidate}" && ! -L "${candidate}" ]] || continue
        fmt="$(_detect_format "${candidate}")"
        if [[ "${fmt}" != "none" ]]; then
            source="${candidate}"
            break
        fi
    done
    [[ -n "${source}" ]] || return 0

    local migration_marker="<!-- Migrated from legacy ${label} by scripts/update.sh. -->"
    if grep -Fqx "${migration_marker}" "${state}"; then
        info "Legacy state from ${label} was already migrated."
        return 0
    fi

    local identity="" working=""
    if [[ "${fmt}" == "new" ]]; then
        identity="$(_extract_zone_between "${source}" "${TEMPLATE_BOUNDARY}" "${REPO_BOUNDARY}")"
        working="$(_extract_zone_below "${source}" "${REPO_BOUNDARY}")"
    else
        working="$(_extract_zone_below "${source}" "${LEGACY_BOUNDARY}")"
    fi
    {
        echo ""
        echo "${migration_marker}"
        [[ -z "${identity}" ]] || printf '\n%s\n' "${identity}"
        [[ -z "${working}" ]] || printf '\n%s\n' "${working}"
    } >> "${state}"
    warn "Migrated legacy agent state from ${label} to .agents/STATE.md."
}

repair_claude_entrypoint() {
    header "Repairing Claude Entry Point"

    local link="${PROJECT_ROOT}/CLAUDE.md"
    local canonical="${PROJECT_ROOT}/AGENTS.md"
    if [[ -L "${link}" ]] \
        && [[ "$(realpath -m -- "${link}")" == "$(realpath -m -- "${canonical}")" ]]; then
        info "Verified CLAUDE.md -> AGENTS.md"
        return 0
    fi
    rm -rf -- "${link}"
    ln -s "AGENTS.md" "${link}"
    UPDATED_FILES+=("CLAUDE.md -> AGENTS.md")
}

# Recreate/heal the native discovery symlinks so Claude Code auto-discovers the
# canonical .agents/ subagents and skills. migrate_legacy_native_data already
# skips symlinks, so an already-healed link is left untouched; a stale real
# directory or a corrupted link is replaced with the correct symlink.
link_native_discovery_dirs() {
    header "Linking Native Discovery Directories"

    local entry native_path target link backup_root=""
    for entry in "${NATIVE_DISCOVERY_LINKS[@]}"; do
        native_path="${entry%%:*}"
        target="${entry##*:}"
        link="${PROJECT_ROOT}/${native_path}"
        if [[ -L "${link}" && "$(readlink -- "${link}")" == "${target}" ]]; then
            info "Verified ${native_path} -> ${target}"
            continue
        fi
        # Real content here is project-owned (a repo that kept its own
        # subagents/skills natively, or a link corrupted into a file). Preserve
        # it before replacing, so the link step can never destroy user data.
        if [[ -e "${link}" || -L "${link}" ]]; then
            if [[ -z "${backup_root}" ]]; then
                backup_root="${PROJECT_ROOT}/.orchestra-backup-native-discovery-$(date +%Y%m%d%H%M%S)-$$"
            fi
            mkdir -p "${backup_root}/$(dirname -- "${native_path}")"
            cp -a -- "${link}" "${backup_root}/${native_path}"
            rm -rf -- "${link}"
        fi
        mkdir -p "$(dirname -- "${link}")"
        ln -s "${target}" "${link}"
        UPDATED_FILES+=("${native_path} -> ${target}")
    done

    if [[ -n "${backup_root}" ]]; then
        warn "Existing native discovery content was backed up: ${backup_root}"
    fi
}

# =============================================================================
# Phase 5: Native settings migration and diff
# =============================================================================
migrate_native_settings_paths() {
    local settings="${PROJECT_ROOT}/.claude/settings.json"
    [[ -f "${settings}" ]] || return 0
    if ! grep -Fq '.claude/hooks/' "${settings}"; then
        return 0
    fi

    sed -i 's#\.claude/hooks/#.agents/hooks/#g' "${settings}"
    UPDATED_FILES+=(".claude/settings.json (migrated hook paths)")
    info "Migrated .claude hook paths to canonical .agents/hooks paths."
}

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
# Phase 6: Installed Orchestra version update
# =============================================================================
update_version() {
    header "Updating Orchestra Version"

    if [[ -f "${TEMPLATE_DIR}/VERSION" ]]; then
        local destination="${PROJECT_ROOT}/${LOCAL_VERSION_FILE}"
        mkdir -p "$(dirname "${destination}")"
        cp -f "${TEMPLATE_DIR}/VERSION" "${destination}.tmp.$$"
        mv -f "${destination}.tmp.$$" "${destination}"
        info "${LOCAL_VERSION_FILE} updated to ${BOLD}${NEW_VERSION}${RESET}"
        UPDATED_FILES+=("${LOCAL_VERSION_FILE}")
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

    if [[ "${SELF_UPDATED}" == "true" ]]; then
        warn "scripts/update.sh itself was updated during this run."
        warn "Run ${BOLD}./scripts/update.sh${RESET} once more to sync targets added in the new version (e.g. new template directories)."
        echo ""
    fi

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
    migrate_legacy_native_data
    cleanup_deprecated_paths
    migrate_legacy_agent_state
    sync_safe_dirs
    sync_safe_files
    repair_claude_entrypoint
    link_native_discovery_dirs
    migrate_native_settings_paths
    check_settings_files
    update_version
    print_summary

    info "Done!"
}

main "$@"
