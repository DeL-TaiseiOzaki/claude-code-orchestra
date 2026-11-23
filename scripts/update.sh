#!/usr/bin/env bash
# ==============================================================================
# scripts/update.sh — Claude Code Orchestra Template Updater
#
# Fetches the latest version of the claude-code-orchestra template and safely
# updates local files. Template-owned content is centralized under .claude/;
# mutable project context is preserved in .claude/STATE.md and .claude/docs/.
#
# Usage:
#   ./scripts/update.sh            # Update to latest main
#   ./scripts/update.sh v0.2.0     # Update to a specific tag/ref
#   ./scripts/update.sh --yes      # Skip confirmation prompts
#   ORCHESTRA_TEMPLATE_REPO=/path/to/template ./scripts/update.sh   # other source
#
# Root AGENTS.md is project-owned once /start-project converts it and is never
# rewritten. CLAUDE.md, CLAUDE.local.md, and .claude/CLAUDE.md are backed up
# and removed (they stop Claude Code from loading AGENTS.md).
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
    ".claude/rules"
    ".claude/skills"
    ".claude/agents"
    ".claude/hooks"
)
# Files that no SAFE_DIR already covers. `.claude/rules/`, `.claude/skills/`,
# above are replaced wholesale, so their contents must not be repeated here.
#
# Root AGENTS.md is deliberately absent: it belongs to the project once
# /start-project converts it, so reconcile_agents_md replaces it only while it
# is byte-identical to a shipped skeleton (KNOWN_TEMPLATE_BLOBS). There is no
# CLAUDE.md; retire_instruction_shadow_files backs up and removes any.
SAFE_FILES=(
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

# Paths that previous template versions installed but no longer ship.
# The updater removes these from the local project so that orphans from
# deprecated features (e.g. removed CLI integrations) don't linger.
#
# When you remove an entry from SAFE_DIRS or SAFE_FILES, add the old path
# here so existing projects get cleaned up on their next update.
# Each entry MUST start with "." (a dotfile/dot-dir) to keep the blast
# radius scoped to template-owned locations.
DEPRECATED_PATHS=(
    ".agents/workflows"
    ".agents/rules"
    ".agents/skills"
    ".agents/agents"
    ".agents/hooks"
    ".codex/skills"
)

# Individual files the old template shipped inside a directory the user may
# also own. `.gemini/` is the Gemini CLI's own directory, so it is never removed
# as a whole: only these three files (the complete set the template installed)
# are moved into a backup (and only when their content is a shipped template
# version), and a parent directory is removed only if that left it
# empty. Same rules as DEPRECATED_PATHS: relative, no "..", starts with ".".
DEPRECATED_TEMPLATE_FILES=(
    ".gemini/GEMINI.md"
    ".gemini/settings.json"
    ".gemini/skills/context-loader/SKILL.md"
)

# "<path>:<git blob hash>" for every version of those three files the template
# ever shipped (taken from git history). A file is moved only when its content
# hashes to one of these, so a Gemini CLI config the user customized (or created
# themselves at the same path) is left in place and reported instead.
KNOWN_TEMPLATE_BLOBS=(
    ".gemini/GEMINI.md:08fc6214cd37b5c5ba132f8ca98a32d592cd6c07"
    ".gemini/GEMINI.md:183c1b16fc97a87bfc251b230c5607bb7d1c7083"
    ".gemini/GEMINI.md:281f636716d8b2aa98c88f4eb3034768200a3b31"
    ".gemini/GEMINI.md:28214dd7c949a85518ca9719251648b8738639c2"
    ".gemini/GEMINI.md:30fe2b3154fda77d556fb57ea2abccb247047f5f"
    ".gemini/GEMINI.md:5e9502598c6d7932b87098fe8ace24e9910cc2ea"
    ".gemini/GEMINI.md:6237b1a11ea4149ff88b3e205e175bb05d3156da"
    ".gemini/GEMINI.md:6c43023a948cc90d85169e1acc8d8ced245ef3e7"
    ".gemini/GEMINI.md:df432d49f3f86b6586e7c09c137a09ad83a39d22"
    ".gemini/settings.json:142940f1205c27318eb41d58c33696c988ba4722"
    ".gemini/settings.json:8af4e802aa36505126f98c0995d7dc5199056f64"
    ".gemini/settings.json:b5c01c35fb8bc866e3c411bad6b589ea1c51a2f6"
    ".gemini/settings.json:ca7830421b46b1e16db0c6335eb29e3c02bb1435"
    ".gemini/skills/context-loader/SKILL.md:0494ab2d9e228f601aa04f3daa9aea738664db31"
    ".gemini/skills/context-loader/SKILL.md:11208d484db9d88c297b0f6f57ffae022ee9e43c"
    # Every root AGENTS.md the template ever shipped, plus the current
    # skeleton (scripts/check.sh fails while an unconverted skeleton is not
    # listed). Only these are replaced on update; anything else is the
    # project's own converted file and is never rewritten.
    "AGENTS.md:09bf014c67893ae22f938da0785323ee5456280a"
    "AGENTS.md:14054e1f826887df0828f2610efe376dc9a82f73"
    "AGENTS.md:200310a6eeca345de15efea086c242285656917c"
    "AGENTS.md:24af8785045f8fe00c1b4a6072878d4510130f17"
    "AGENTS.md:26941d80fa2a98bc126279d7cf041426cb9c442d"
    "AGENTS.md:3771fcd37b102405b5685d310ac93de06c5afcf8"
    "AGENTS.md:3e12663c2f79e88d1d77f885254eb421fa11a3ab"
    "AGENTS.md:4239ca937a905bf1a17cf4d9f6ac72d10a466c1e"
    "AGENTS.md:4328811822e49952afbadf0802a1d7dde94a6fb1"
    "AGENTS.md:51c7158710ac22cbfc60dda80658388003d53347"
    "AGENTS.md:57b4bcc0d2759b2f7f2c39b9efe0ea980a024038"
    "AGENTS.md:60bf015b7e28a1b90d6b79de21bbabcbbc1d4636"
    "AGENTS.md:69348a0883bb06cc4f00f1b97fe371b587cc03d4"
    "AGENTS.md:6c91b2ac323a8d18e383f4149f7a07acc703d011"
    "AGENTS.md:6e79177ba1d1ea052281e6a59885e5ca269f75b2"
    "AGENTS.md:74ec55fd7093f8505c03142247f1398bb8248517"
    "AGENTS.md:7529ed6447317b7ff146d5f79a00f35093a21545"
    "AGENTS.md:76af6047b5ff2bf6edcb3b5540b94ef70c7dcebe"
    "AGENTS.md:7c9b31a86558b888ce07e1caaccb31113f539280"
    "AGENTS.md:90c08e26f7b2d761e0e81a91a859a15ea5f062e2"
    "AGENTS.md:93292af845ad6c2d5d544dc8d3a27fe7ac3f3b9a"
    "AGENTS.md:9ac157e36c8ee4b815e06642a22e0c6d8baba0a6"
    "AGENTS.md:a7ee7dd2ad130e6f38d6bd7588fef99a0bee8228"
    "AGENTS.md:a801564fa7aa7f538a1c6a3c6247512dd026fedb"
    "AGENTS.md:aa31c6ecd77e58c6f0abda6d2c6542c359a01eb0"
    "AGENTS.md:c10a7c8da09a5c18eee3d474f4c5903aa1971625"
    "AGENTS.md:c97635ab800e3e5c2633c207c21bbbbc44912716"
    "AGENTS.md:cce6f8eaf074dace1bac756ffbbcfc9a7c4592e0"
    "AGENTS.md:cd9406b58af07698b0fe943e23300bc94e7fc92b"
    "AGENTS.md:d3ae4edd959df8256139ce6a2eff1834ba94f61b"
    "AGENTS.md:d889c23e87d4b7766567bf3832f2226afa928f03"
    "AGENTS.md:dca40f87696d90e1dfd20aa58f7d60d6a10c3589"
    "AGENTS.md:ddad544bb23a56891bbbedc3538b0545f1e2d36d"
    "AGENTS.md:e6c87e0e25fc0dd4fb0f2debed4ef0c01b569959"
    "AGENTS.md:e8c2fb8661265872fda7603f66622649f7807c43"
    "AGENTS.md:f1a479286f736634f2ea994bbb71e06f207698bc"
    "AGENTS.md:f3845fc1e3358adf019a9844ca165c31b11d7d2c"
    "AGENTS.md:f80715eb7591ea310f8e617dc83c9bd64d931f2a"
    "AGENTS.md:fa1fe64a07894e40f87f0b70183115dc91df1215"
    "AGENTS.md:fa553c9c5062cf67ba85e0184cd58721148b5e8b"
    "AGENTS.md:fddfe747ed53adc9ba0c0341614181fd1babd23f"
    "AGENTS.md:ff64f178ea0c7cbcc11872bd1643072a20f2d563"
    "AGENTS.md:7d87ef22bfe50baa2b16fbcb36a6074333edbc29"
    # Every CLAUDE.md the template shipped. Any CLAUDE.md is backed up and
    # removed; these only label the backup as a template copy (no merge needed).
    "CLAUDE.md:002d3da24b730393b7e8916b73f86c6bc6b925f0"
    "CLAUDE.md:086c2efe3b98c00a075550b4da3cc2ace322f8a7"
    "CLAUDE.md:1000caec68de0266d7a907f1e48b6a19e419a3ab"
    "CLAUDE.md:11fbc419ef477695d098410c0f793cacf95142a6"
    "CLAUDE.md:154c9a8eb85956a25723c2c85a2525669e51fe56"
    "CLAUDE.md:1ab380dacb04bc7ff850da3e2503be059ea38341"
    "CLAUDE.md:1cd810ef0c9daae5f31f1819c4f2fa59d8449e06"
    "CLAUDE.md:2442521532448dcc3f6eb429db616daf6d05685d"
    "CLAUDE.md:247fa29ddb049c28b4e3f74dcfd89d0cc296f138"
    "CLAUDE.md:27b2947458b374f7b48efe7e72630c9705bcf37c"
    "CLAUDE.md:34c350c07a4b55676f5363a8c4f9455aba3e68a2"
    "CLAUDE.md:3a2b3aec7754727778a24eb5d1d97481e24905f6"
    "CLAUDE.md:47dc3e3d863cfb5727b87d785d09abf9743c0a72"
    "CLAUDE.md:5bf3bfe6481dc9f4b62474df2b641863abaaeea7"
    "CLAUDE.md:5f61cf8d1de48a38f171f7d7cbbe9d07e0d0e902"
    "CLAUDE.md:67d416138e1ef64e504b9e35dd3ac4f6533d41ca"
    "CLAUDE.md:6a491c217e92c102e7cb4f66a41b01e563ac32c5"
    "CLAUDE.md:6fef065991838b6c26eb7a583c79505f94d73619"
    "CLAUDE.md:7c2a526ff679c3be57090eb40dbbb779b00e692d"
    "CLAUDE.md:83f0c349c405771ddc0cf906e5c0e23364c43f28"
    "CLAUDE.md:94359728542c63b9425cd775ec8a8875eb1ca0ca"
    "CLAUDE.md:9924405446b46208c6dba05f113c74f87c7c2f9c"
    "CLAUDE.md:b37d07ccad9a2a6969201e28eef0c6c2be00dfe1"
    "CLAUDE.md:b4dcee828231df83e2a7697084e94ec6ad359b25"
    "CLAUDE.md:c3088595960f14ea8ceb0961142368897bfb6ad3"
    "CLAUDE.md:cf8640a10722600459cb92fa4f0afdfdb3faeac3"
    "CLAUDE.md:d1fb3bc09ed3c51b152d94ead49e9ea361d015e5"
    "CLAUDE.md:d643f42d5d73ce224e203abf61a2fbac7e946ab3"
    "CLAUDE.md:d986d7645de8d370ff8c3ad68c563d0deb543906"
    "CLAUDE.md:dd1ba85b591d2aa975ca324474a4b2cdc8773e4a"
    "CLAUDE.md:e0753db912868721ac4547629a933126df895568"
    "CLAUDE.md:e3c51f4abdd5ce158b23357159b7fe4dbd350b47"
    "CLAUDE.md:e76f3e972c61fed0f55dcf634fd8b381f8287c94"
    "CLAUDE.md:ed8e4b4170b17f0d1d8575f473b2bcb270d3a714"
)

# Claude Code (>= 2.1.277) skips AGENTS.md while any of these exists in the
# project or a parent. Each is backed up and removed on update; a file whose
# only content is "@AGENTS.md" imports AGENTS.md instead and is kept.
INSTRUCTION_SHADOW_FILES=(
    "CLAUDE.md"
    "CLAUDE.local.md"
    ".claude/CLAUDE.md"
)
PENDING_MERGE_HEADING="## Pending Instruction Merge"

# Project-owned data that pre-2.0 installations kept under .agents/. It is
# moved to .claude/ rather than removed: these directories hold the project's
# own design docs, logs, and checkpoints, not template content.
LEGACY_PROJECT_DIRS=(
    "docs"
    "logs"
    "checkpoints"
)

# Machine-readable native settings: never overwritten, shown as a diff only.
# A downstream project edits its model, approval policy, and hooks here.
SETTINGS_FILES=(
    ".claude/settings.json"
    ".codex/config.toml"
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

# =============================================================================
# Phase 2.6: Move individual deprecated template files into a backup
# =============================================================================
# Unlike cleanup_deprecated_paths this never deletes: each existing file whose
# content matches a shipped template blob (KNOWN_TEMPLATE_BLOBS) is moved to
# .orchestra-backup-deprecated-<ts>-$$/<same relative path>, then any parent
# directory left empty is removed (rmdir refuses a non-empty one, so a user's
# own files under .gemini/ are never touched). A file with any other content is
# left in place with a warning.
is_known_template_blob() {
    local path="$1" file="$2" hash entry
    [[ -L "${file}" ]] && return 1
    hash="$(git hash-object -- "${file}" 2>/dev/null)" || return 1
    for entry in "${KNOWN_TEMPLATE_BLOBS[@]}"; do
        [[ "${entry}" == "${path}:${hash}" ]] && return 0
    done
    return 1
}

cleanup_deprecated_template_files() {
    header "Backing Up Deprecated Template Files"

    local project_root_abs
    project_root_abs="$(cd "${PROJECT_ROOT}" && pwd -P)"
    local backup_root="" moved=() kept=()

    local path
    for path in "${DEPRECATED_TEMPLATE_FILES[@]}"; do
        if [[ -z "${path//[[:space:]]/}" || "${path:0:1}" != "." ||
            "${path}" == /* || "${path}" == *".."* ]]; then
            error "Invalid DEPRECATED_TEMPLATE_FILES entry: '${path}'. Skipping."
            continue
        fi

        local target="${PROJECT_ROOT}/${path}"
        if [[ ! -f "${target}" && ! -L "${target}" ]]; then
            continue
        fi

        local resolved
        resolved="$(realpath -m -- "${target}")"
        if [[ "${resolved}" != "${project_root_abs}/"* ]]; then
            error "Refusing to move '${path}': resolves outside PROJECT_ROOT (${resolved})."
            continue
        fi

        if ! is_known_template_blob "${path}" "${target}"; then
            kept+=("${path}")
            continue
        fi

        if [[ -z "${backup_root}" ]]; then
            backup_root="${PROJECT_ROOT}/.orchestra-backup-deprecated-$(date +%Y%m%d%H%M%S)-$$"
        fi
        mkdir -p -- "${backup_root}/$(dirname "${path}")"
        cp -a -- "${target}" "${backup_root}/${path}"
        if git -C "${PROJECT_ROOT}" ls-files --error-unmatch -- "${path}" &>/dev/null; then
            git -C "${PROJECT_ROOT}" rm -f --quiet --ignore-unmatch -- "${path}" \
                || rm -f -- "${target}"
        else
            rm -f -- "${target}"
        fi

        local parent
        parent="$(dirname "${path}")"
        while [[ "${parent}" != "." && "${parent}" != "/" ]]; do
            rmdir -- "${PROJECT_ROOT}/${parent}" 2>/dev/null || break
            parent="$(dirname "${parent}")"
        done

        moved+=("${path}")
        UPDATED_FILES+=("REMOVED: ${path} (backed up)")
    done

    if [[ ${#kept[@]} -gt 0 ]]; then
        warn "Kept deprecated template files whose content differs from any shipped template (customized or user-owned); remove them yourself if unwanted:"
        for path in "${kept[@]}"; do
            echo "  ${path}"
        done
    fi
    if [[ ${#moved[@]} -eq 0 ]]; then
        [[ ${#kept[@]} -gt 0 ]] || info "No deprecated template files found."
        return 0
    fi
    warn "Moved deprecated template files to ${backup_root}:"
    for path in "${moved[@]}"; do
        echo "  ${path}"
    done
}

migrate_legacy_native_data() {
    header "Migrating Legacy Project Data"

    local name legacy canonical backup_root=""
    for name in "${LEGACY_PROJECT_DIRS[@]}"; do
        legacy="${PROJECT_ROOT}/.agents/${name}"
        canonical="${PROJECT_ROOT}/.claude/${name}"
        if [[ ! -d "${legacy}" || -L "${legacy}" ]]; then
            continue
        fi

        if [[ ! -e "${canonical}" ]] ||
            [[ -d "${canonical}" && -z "$(find "${canonical}" -mindepth 1 -print -quit)" ]]; then
            rm -rf -- "${canonical}"
            mkdir -p "$(dirname "${canonical}")"
            mv -- "${legacy}" "${canonical}"
            UPDATED_FILES+=(".claude/${name} (migrated from .agents/${name})")
            continue
        fi

        if [[ -z "${backup_root}" ]]; then
            backup_root="${PROJECT_ROOT}/.orchestra-backup-native-migration-$(date +%Y%m%d%H%M%S)-$$"
        fi
        mkdir -p "${backup_root}/.agents" "${canonical}"
        cp -a -- "${legacy}" "${backup_root}/.agents/${name}"
        cp -an -- "${legacy}/." "${canonical}/"
        rm -rf -- "${legacy}"
        UPDATED_FILES+=(".claude/${name} (merged from .agents/${name})")
    done

    # Shared state is a single file, not a directory, but has the same
    # project-owned character: never drop it, move it if .claude/ has none.
    local legacy_state="${PROJECT_ROOT}/.agents/STATE.md"
    local canonical_state="${PROJECT_ROOT}/.claude/STATE.md"
    if [[ -f "${legacy_state}" && ! -L "${legacy_state}" ]]; then
        mkdir -p "${PROJECT_ROOT}/.claude"
        if [[ ! -e "${canonical_state}" ]]; then
            mv -- "${legacy_state}" "${canonical_state}"
            UPDATED_FILES+=(".claude/STATE.md (migrated from .agents/STATE.md)")
        else
            if [[ -z "${backup_root}" ]]; then
                backup_root="${PROJECT_ROOT}/.orchestra-backup-native-migration-$(date +%Y%m%d%H%M%S)-$$"
            fi
            mkdir -p "${backup_root}/.agents"
            cp -a -- "${legacy_state}" "${backup_root}/.agents/STATE.md"
            rm -f -- "${legacy_state}"
            warn "Both .agents/STATE.md and .claude/STATE.md existed; kept .claude/STATE.md."
        fi
    fi

    if [[ -n "${backup_root}" ]]; then
        warn "Legacy project data was backed up before merging: ${backup_root}"
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
# Mutable context lives in .claude/STATE.md. Boundary helpers remain only to
# migrate older 2/3-zone AGENTS.md or CLAUDE.md files before
# retire_instruction_shadow_files and reconcile_agents_md replace them.

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

    local state="${PROJECT_ROOT}/.claude/STATE.md"
    mkdir -p "${PROJECT_ROOT}/.claude/docs/research" \
        "${PROJECT_ROOT}/.claude/logs" "${PROJECT_ROOT}/.claude/checkpoints"
    if [[ ! -f "${state}" ]]; then
        cp -f "${TEMPLATE_DIR}/.claude/STATE.md" "${state}"
        UPDATED_FILES+=(".claude/STATE.md")
    fi
    if [[ ! -f "${PROJECT_ROOT}/.claude/docs/DESIGN.md" ]]; then
        cp -f "${TEMPLATE_DIR}/.claude/docs/DESIGN.md" \
            "${PROJECT_ROOT}/.claude/docs/DESIGN.md"
        UPDATED_FILES+=(".claude/docs/DESIGN.md")
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
    warn "Migrated legacy agent state from ${label} to .claude/STATE.md."
}

# Append entries under "## Pending Instruction Merge" in .claude/STATE.md (the
# section is created at the end of the file when absent), so /start-project can
# offer to merge each backup into AGENTS.md.
record_pending_merge() {
    [[ $# -gt 0 ]] || return 0
    local state="${PROJECT_ROOT}/.claude/STATE.md" entries="" entry
    for entry in "$@"; do
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
    UPDATED_FILES+=(".claude/STATE.md (${PENDING_MERGE_HEADING#\#\# })")
}

is_agents_shim() {
    [[ -f "$1" && ! -L "$1" && "$(tr -d '[:space:]' < "$1")" == "@AGENTS.md" ]]
}

# Path-safety guards shared by the two bootstrap phases below: relative, no
# "..", no symlinked parent, and resolving strictly inside PROJECT_ROOT.
safe_bootstrap_path() {
    local path="$1" project_root_abs current component resolved
    local -a components
    project_root_abs="$(cd "${PROJECT_ROOT}" && pwd -P)"
    if [[ -z "${path}" || "${path}" == /* || "${path}" == *".."* ]]; then
        error "Refusing unsafe bootstrap path: '${path}'"
        return 1
    fi
    current="${PROJECT_ROOT}"
    IFS='/' read -r -a components <<< "$(dirname "${path}")"
    for component in "${components[@]}"; do
        [[ "${component}" == "." || -z "${component}" ]] && continue
        current="${current}/${component}"
        if [[ -L "${current}" ]]; then
            error "Refusing '${path}': a parent directory is a symlink."
            return 1
        fi
    done
    # The parent is resolved, not the file: a symlinked instruction file is
    # itself the project's entry (backed up as a link, then unlinked) and its
    # target is never followed.
    resolved="$(realpath -m -- "$(dirname "${PROJECT_ROOT}/${path}")")/$(basename "${path}")"
    if [[ "${resolved}" != "${project_root_abs}/"* ]]; then
        error "Refusing '${path}': resolves outside PROJECT_ROOT (${resolved})."
        return 1
    fi
}

# Copy one file into a timestamped backup directory, created on first use, and
# set LAST_BACKUP to its path relative to the project root. A symlink that
# resolves to a regular file is backed up as that content, so the backup stays
# readable after it moves; a dangling link is kept as a link. Called directly
# (never in a subshell) so the backup root persists for print_summary.
INSTRUCTION_BACKUP_ROOT=""
LAST_BACKUP=""
backup_bootstrap_file() {
    local path="$1"
    if [[ -z "${INSTRUCTION_BACKUP_ROOT}" ]]; then
        INSTRUCTION_BACKUP_ROOT="${PROJECT_ROOT}/.orchestra-backup-instructions-$(date +%Y%m%d%H%M%S)-$$"
    fi
    mkdir -p -- "${INSTRUCTION_BACKUP_ROOT}/$(dirname "${path}")"
    if [[ -L "${PROJECT_ROOT}/${path}" && -f "${PROJECT_ROOT}/${path}" ]]; then
        cp -L -- "${PROJECT_ROOT}/${path}" "${INSTRUCTION_BACKUP_ROOT}/${path}"
    else
        cp -a -- "${PROJECT_ROOT}/${path}" "${INSTRUCTION_BACKUP_ROOT}/${path}"
    fi
    LAST_BACKUP="${INSTRUCTION_BACKUP_ROOT#"${PROJECT_ROOT}/"}/${path}"
}

# CLAUDE.md, CLAUDE.local.md, and .claude/CLAUDE.md each make Claude Code skip
# AGENTS.md, so every one is backed up and removed without a prompt (pre-2.0
# CLAUDE.md -> AGENTS.md symlinks included). Runs after
# migrate_legacy_agent_state, which reads legacy zones out of CLAUDE.md first.
retire_instruction_shadow_files() {
    header "Retiring Files That Shadow AGENTS.md"

    local path target backup note entries=()
    for path in "${INSTRUCTION_SHADOW_FILES[@]}"; do
        target="${PROJECT_ROOT}/${path}"
        [[ -e "${target}" || -L "${target}" ]] || continue
        safe_bootstrap_path "${path}" || continue
        if is_agents_shim "${target}"; then
            info "Kept ${path}: it only imports @AGENTS.md"
            continue
        fi
        if [[ -d "${target}" && ! -L "${target}" ]]; then
            warn "Skipped ${path}: it is a directory, not an instruction file."
            continue
        fi
        if [[ -L "${target}" && ! -e "${target}" ]]; then
            note="dangling symlink to $(readlink -- "${target}"), kept as a link"
        elif [[ -L "${target}" && "$(realpath -- "${target}")" == "$(realpath -m -- "${PROJECT_ROOT}/AGENTS.md")" ]]; then
            note="legacy symlink to AGENTS.md, no merge needed"
        elif [[ -L "${target}" ]]; then
            note="symlink to $(readlink -- "${target}"), content copied, review for merge"
        elif is_known_template_blob "${path}" "${target}"; then
            note="template copy, no merge needed"
        else
            note="project instructions, review for merge"
        fi
        backup_bootstrap_file "${path}"
        backup="${LAST_BACKUP}"
        if git -C "${PROJECT_ROOT}" ls-files --error-unmatch -- "${path}" &>/dev/null; then
            git -C "${PROJECT_ROOT}" rm -f --quiet --ignore-unmatch -- "${path}" \
                || rm -f -- "${target}"
        else
            rm -f -- "${target}"
        fi
        warn "Backed up ${path} to ${backup} and removed it (${note})."
        entries+=("\`${path}\` backed up to \`${backup}\` and removed by scripts/update.sh (${note})")
        UPDATED_FILES+=("REMOVED: ${path} (backed up to ${backup})")
    done
    if [[ ${#entries[@]} -eq 0 ]]; then
        info "No CLAUDE.md, CLAUDE.local.md, or .claude/CLAUDE.md to retire."
        return 0
    fi
    record_pending_merge "${entries[@]}"
}

# Root AGENTS.md is project-owned once /start-project converts it. It is
# replaced only while it is a known shipped version (or missing); a legacy
# zoned file whose state migrate_legacy_agent_state already moved is backed up
# first; anything else is the project's own file and is never rewritten.
reconcile_agents_md() {
    header "Reconciling Root AGENTS.md"

    local src="${TEMPLATE_DIR}/AGENTS.md" dst="${PROJECT_ROOT}/AGENTS.md" backup
    if [[ ! -f "${src}" ]]; then
        warn "Template does not contain AGENTS.md, skipping."
        return 0
    fi
    safe_bootstrap_path "AGENTS.md" || return 0
    if [[ -f "${dst}" && ! -L "${dst}" ]] && cmp -s "${src}" "${dst}"; then
        info "AGENTS.md is the current skeleton; run /start-project to convert it."
        return 0
    fi
    if [[ -e "${dst}" || -L "${dst}" ]]; then
        if [[ -L "${dst}" ]]; then
            backup_bootstrap_file "AGENTS.md"
            backup="${LAST_BACKUP}"
            rm -f -- "${dst}"
            record_pending_merge "\`AGENTS.md\` (a symlink) backed up to \`${backup}\` and replaced by the skeleton (scripts/update.sh)"
        elif is_known_template_blob "AGENTS.md" "${dst}"; then
            info "AGENTS.md is a shipped template version; replacing it with the skeleton."
        elif [[ "$(_detect_format "${dst}")" != "none" ]]; then
            backup_bootstrap_file "AGENTS.md"
            backup="${LAST_BACKUP}"
            record_pending_merge "\`AGENTS.md\` (legacy zoned format) backed up to \`${backup}\` and replaced by the skeleton (scripts/update.sh)"
            warn "Backed up legacy AGENTS.md to ${backup}."
        else
            info "Preserved project-owned AGENTS.md; template updates never rewrite it."
            return 0
        fi
    fi
    cp -f "${src}" "${dst}.tmp.$$"
    mv -f "${dst}.tmp.$$" "${dst}"
    UPDATED_FILES+=("AGENTS.md (skeleton; run /start-project to convert it)")
    info "Installed the AGENTS.md skeleton; run /start-project to convert it."
}

warn_ancestor_shadowing() {
    local dir name path user_memory="${HOME:-/nonexistent}/.claude/CLAUDE.md"
    dir="$(dirname "$(cd "${PROJECT_ROOT}" && pwd -P)")"
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

# =============================================================================
# Phase 5: Native settings migration and diff
# =============================================================================
migrate_native_settings_paths() {
    local settings="${PROJECT_ROOT}/.claude/settings.json"
    [[ -f "${settings}" ]] || return 0
    if ! grep -Eq '\.agents/(hooks|logs)/' "${settings}"; then
        return 0
    fi

    sed -i -e 's#\.agents/hooks/#.claude/hooks/#g' \
        -e 's#\.agents/logs/#.claude/logs/#g' "${settings}"
    UPDATED_FILES+=(".claude/settings.json (migrated hook and log paths)")
    info "Migrated legacy .agents paths in settings to .claude paths."
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

    warn_ancestor_shadowing
    if [[ -n "${INSTRUCTION_BACKUP_ROOT}" ]]; then
        warn "Instruction-file backups: ${INSTRUCTION_BACKUP_ROOT}"
        warn "They are listed under '${PENDING_MERGE_HEADING}' in .claude/STATE.md; run /start-project to merge them."
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
    cleanup_deprecated_template_files
    migrate_legacy_agent_state
    retire_instruction_shadow_files
    sync_safe_dirs
    sync_safe_files
    reconcile_agents_md
    migrate_native_settings_paths
    check_settings_files
    update_version
    print_summary

    info "Done!"
}

main "$@"
