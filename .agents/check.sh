#!/usr/bin/env bash
# .agents/check.sh -- Consistency checker for the .agents/ directory.
# Validates cross-file references, tier IDs, model coherence, and update.sh config.
# Exit 0 only if all checks pass.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PASS=0
FAIL=0

check() {
    local name="$1"
    shift
    if "$@"; then
        echo "PASS: ${name}"
        PASS=$((PASS + 1))
    else
        echo "FAIL: ${name}"
        FAIL=$((FAIL + 1))
    fi
}

# --------------------------------------------------------------------------
# 1) Every relative markdown link / canonical-file path in INDEX.md exists
# --------------------------------------------------------------------------
check_index_links() {
    local index="${ROOT}/.agents/INDEX.md"
    if [[ ! -f "${index}" ]]; then
        echo "  INDEX.md not found"
        return 1
    fi
    local ok=true
    # Extract paths that look like relative refs: backtick-wrapped or link targets
    # Matches: `path/to/file` and (path/to/file) patterns
    local paths
    paths=$(grep -oE '`\.[^`]+`' "${index}" | tr -d '`' || true)
    paths+=$'\n'
    paths+=$(grep -oE '\(\.[^)]+\)' "${index}" | tr -d '()' || true)
    # Deduplicate and filter
    paths=$(echo "${paths}" | sort -u | grep -v '^$' || true)
    while IFS= read -r p; do
        [[ -z "${p}" ]] && continue
        local target="${ROOT}/${p}"
        if [[ ! -e "${target}" ]]; then
            echo "  Missing: ${p}"
            ok=false
        fi
    done <<< "${paths}"
    ${ok}
}
check "INDEX.md links resolve" check_index_links

# --------------------------------------------------------------------------
# 2) Tier IDs default/sol/fable all appear in tiers.md
# --------------------------------------------------------------------------
check_tier_ids() {
    local tiers="${ROOT}/.agents/tiers.md"
    if [[ ! -f "${tiers}" ]]; then
        echo "  tiers.md not found"
        return 1
    fi
    local ok=true
    for id in default sol fable; do
        if ! grep -q "\`${id}\`" "${tiers}"; then
            echo "  Missing tier ID: ${id}"
            ok=false
        fi
    done
    ${ok}
}
check "Tier IDs present in tiers.md" check_tier_ids

# --------------------------------------------------------------------------
# 3) Model coherence: CODEX_MODEL in settings.json == model in config.toml
#    == fallback values in ${CODEX_MODEL:-...} across .claude/ and .codex/
#    (gpt-5.5-mini is excluded from comparison)
# --------------------------------------------------------------------------
check_model_coherence() {
    local settings="${ROOT}/.claude/settings.json"
    local config="${ROOT}/.codex/config.toml"
    local ok=true

    # Extract CODEX_MODEL from settings.json
    local settings_model
    settings_model=$(python3 -c "
import json, sys
with open('${settings}') as f:
    d = json.load(f)
print(d.get('env', {}).get('CODEX_MODEL', ''))
" 2>/dev/null)

    if [[ -z "${settings_model}" ]]; then
        echo "  Could not read CODEX_MODEL from ${settings}"
        return 1
    fi

    # Extract model from config.toml (simple grep; avoids toml parser dep)
    local config_model
    config_model=$(grep -E '^model\s*=' "${config}" | head -1 | sed 's/.*=\s*"\(.*\)"/\1/')

    if [[ -z "${config_model}" ]]; then
        echo "  Could not read model from ${config}"
        return 1
    fi

    # Compare settings vs config
    if [[ "${settings_model}" != "${config_model}" ]]; then
        echo "  Mismatch: settings.json CODEX_MODEL=${settings_model} vs config.toml model=${config_model}"
        ok=false
    fi

    # Extract distinct fallback values from ${CODEX_MODEL:-...} patterns
    local fallbacks
    fallbacks=$(grep -rhoE '\$\{CODEX_MODEL:-[^}]+\}' "${ROOT}/.claude/" "${ROOT}/.codex/" 2>/dev/null \
        | sed 's/.*:-\(.*\)}/\1/' \
        | sort -u \
        | grep -v 'gpt-5.5-mini' || true)

    while IFS= read -r fb; do
        [[ -z "${fb}" ]] && continue
        if [[ "${fb}" != "${settings_model}" ]]; then
            echo "  Mismatch: fallback ${fb} != CODEX_MODEL ${settings_model}"
            ok=false
        fi
    done <<< "${fallbacks}"

    ${ok}
}
check "Model coherence" check_model_coherence

# --------------------------------------------------------------------------
# 4) .agents listed in SAFE_DIRS of scripts/update.sh
# --------------------------------------------------------------------------
check_safe_dirs() {
    local update="${ROOT}/scripts/update.sh"
    if [[ ! -f "${update}" ]]; then
        echo "  scripts/update.sh not found"
        return 1
    fi
    if grep -q '".agents"' "${update}"; then
        return 0
    else
        echo "  .agents not found in SAFE_DIRS"
        return 1
    fi
}
check ".agents in SAFE_DIRS" check_safe_dirs

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ ${FAIL} -gt 0 ]]; then
    exit 1
fi
exit 0
