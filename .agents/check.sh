#!/usr/bin/env bash
# .agents/check.sh -- Consistency checker for the .agents/ directory.
# Validates shared contracts, bootstraps, tier IDs, model coherence, and updater config.
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
    local tiers="${ROOT}/.agents/rules/tiers.md"
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

    # The shared Codex wrapper carries the same fallback in Python, so it has
    # to move with the single centralized model value too.
    local consult="${ROOT}/.agents/skills/_shared/codex_consult.py"
    if [[ -f "${consult}" ]]; then
        local consult_model
        consult_model=$(grep -E '^DEFAULT_MODEL\s*=' "${consult}" \
            | head -1 | sed 's/.*=\s*"\(.*\)"/\1/')
        if [[ -z "${consult_model}" ]]; then
            echo "  Could not read DEFAULT_MODEL from codex_consult.py"
            ok=false
        elif [[ "${consult_model}" != "${settings_model}" ]]; then
            echo "  Mismatch: codex_consult.py DEFAULT_MODEL=${consult_model} != CODEX_MODEL ${settings_model}"
            ok=false
        fi
    fi

    ${ok}
}
check "Model coherence" check_model_coherence

# --------------------------------------------------------------------------
# 4) Template-owned .agents subdirectories are listed in SAFE_DIRS
# --------------------------------------------------------------------------
check_safe_dirs() {
    local update="${ROOT}/scripts/update.sh"
    if [[ ! -f "${update}" ]]; then
        echo "  scripts/update.sh not found"
        return 1
    fi
    local dir
    for dir in rules skills agents hooks workflows; do
        if ! grep -q "\".agents/${dir}\"" "${update}"; then
            echo "  .agents/${dir} not found in SAFE_DIRS"
            return 1
        fi
    done
}
check ".agents template paths in SAFE_DIRS" check_safe_dirs

# --------------------------------------------------------------------------
# 5) Root AGENTS.md is the complete shared orchestration contract
# --------------------------------------------------------------------------
check_root_contract() {
    local contract="${ROOT}/AGENTS.md"
    if [[ ! -f "${contract}" ]]; then
        echo "  AGENTS.md not found"
        return 1
    fi

    local ok=true
    local headings=(
        "## Mission"
        "## Non-Goals"
        "## Agent Topology"
        "## Routing Policy"
        "## Skill Catalog"
        "## Execution Patterns"
        "## Context and Document Ownership"
        "## Quality Gates"
        "## Language Protocol"
        "## Native Runtime Boundary"
    )
    local heading
    for heading in "${headings[@]}"; do
        if ! grep -Fxq "${heading}" "${contract}"; then
            echo "  Missing contract heading: ${heading}"
            ok=false
        fi
    done

    local definition
    for definition in "${ROOT}"/.agents/agents/*.md; do
        local agent_name
        agent_name="$(basename "${definition}" .md)"
        grep -Fq "\`${agent_name}\`" "${contract}" || {
            echo "  Missing agent in AGENTS.md catalog: ${agent_name}"
            ok=false
        }
    done
    for definition in "${ROOT}"/.agents/skills/*/SKILL.md; do
        local skill_name
        skill_name="$(basename "$(dirname "${definition}")")"
        grep -Fq "\`${skill_name}\`" "${contract}" || {
            echo "  Missing skill in AGENTS.md catalog: ${skill_name}"
            ok=false
        }
    done

    if [[ -e "${ROOT}/.agents/rules/orchestration.md" ]]; then
        echo "  Duplicate orchestration contract still exists under .agents/rules/"
        ok=false
    fi

    local index_entry
    index_entry=$(grep -F 'Root agent contract' "${ROOT}/.agents/INDEX.md" || true)
    if [[ "${index_entry}" != *"normative"* ]]; then
        echo "  Root AGENTS.md is not registered as normative in INDEX.md"
        ok=false
    fi

    ${ok}
}
check "Root orchestration contract" check_root_contract

# --------------------------------------------------------------------------
# 6) Root instructions stay minimal and carry the always-needed information
# --------------------------------------------------------------------------
check_ordered_references() {
    local file="$1"
    shift
    local previous_line=0
    local reference
    local current_line

    for reference in "$@"; do
        current_line=$(grep -nF -- "${reference}" "${file}" | head -1 | cut -d: -f1 || true)
        if [[ -z "${current_line}" ]]; then
            echo "  Missing reference in ${file#"${ROOT}/"}: ${reference}"
            return 1
        fi
        if ((current_line <= previous_line)); then
            echo "  Out-of-order reference in ${file#"${ROOT}/"}: ${reference}"
            return 1
        fi
        previous_line=${current_line}
    done
}

check_bootstrap_references() {
    local root_agents="${ROOT}/AGENTS.md"
    local ok=true

    if (( $(wc -l < "${root_agents}") > 140 )); then
        echo "  Root AGENTS.md exceeds 140 lines"
        ok=false
    fi
    local reference
    for reference in ".agents/rules/" ".agents/skills/" ".agents/agents/" \
        ".agents/STATE.md" ".agents/docs/DESIGN.md" ".agents/change_main.md"; do
        grep -Fq "${reference}" "${root_agents}" || {
            echo "  Missing essential root instruction: ${reference}"
            ok=false
        }
    done
    grep -Fq "Japanese" "${root_agents}" || ok=false
    grep -Fqi "verify" "${root_agents}" || ok=false
    if grep -q '@orchestra:' "${root_agents}"; then
        echo "  Legacy boundary marker found in shared AGENTS.md"
        ok=false
    fi

    ${ok}
}
check "Bootstrap references" check_bootstrap_references

# --------------------------------------------------------------------------
# 7) Product-native directories contain settings only and reference .agents
# --------------------------------------------------------------------------
check_native_boundaries() {
    local ok=true
    local canonical_dir
    for canonical_dir in rules skills agents hooks docs logs checkpoints; do
        local canonical="${ROOT}/.agents/${canonical_dir}"
        if [[ ! -d "${canonical}" || -L "${canonical}" ]]; then
            echo "  Canonical runtime directory is missing or a symlink: .agents/${canonical_dir}"
            ok=false
        fi
    done

    if [[ ! -L "${ROOT}/CLAUDE.md" ]] ||
        [[ "$(realpath -m -- "${ROOT}/CLAUDE.md")" != "$(realpath -m -- "${ROOT}/AGENTS.md")" ]]; then
        echo "  CLAUDE.md must be a symlink to root AGENTS.md"
        ok=false
    fi

    local forbidden_path
    for forbidden_path in \
        .claude/checkpoints .claude/docs .claude/hooks \
        .claude/logs .claude/rules .codex/skills .codex/AGENTS.md; do
        if [[ -e "${ROOT}/${forbidden_path}" || -L "${ROOT}/${forbidden_path}" ]]; then
            echo "  Shared content remains in a native directory: ${forbidden_path}"
            ok=false
        fi
    done

    # Native discovery symlinks must be symlinks into the canonical .agents/
    # directories (never real directories that would fork the SSOT).
    local discovery_link discovery_target
    for discovery_link in agents skills; do
        discovery_target="../.agents/${discovery_link}"
        if [[ ! -L "${ROOT}/.claude/${discovery_link}" ]] ||
            [[ "$(readlink -- "${ROOT}/.claude/${discovery_link}")" != "${discovery_target}" ]]; then
            echo "  Native discovery symlink missing or wrong: .claude/${discovery_link} -> ${discovery_target}"
            ok=false
        fi
    done

    local native_entry
    while IFS= read -r native_entry; do
        case "${native_entry}" in
            settings.json|settings.local.json|settings.orchestra.json|orchestra-version) ;;
            agents|skills) ;;
            *) echo "  Unexpected .claude entry: ${native_entry}"; ok=false ;;
        esac
    done < <(find "${ROOT}/.claude" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
    while IFS= read -r native_entry; do
        if [[ "${native_entry}" != "config.toml" ]]; then
            echo "  Unexpected .codex entry: ${native_entry}"
            ok=false
        fi
    done < <(find "${ROOT}/.codex" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)

    if [[ ! -f "${ROOT}/.claude/settings.json" ]] ||
        ! grep -Fq '.agents/hooks/' "${ROOT}/.claude/settings.json" ||
        grep -Fq '.claude/hooks/' "${ROOT}/.claude/settings.json"; then
        echo "  Claude settings must reference .agents/hooks directly"
        ok=false
    fi
    if [[ ! -f "${ROOT}/.codex/config.toml" ]] ||
        ! grep -Fq '.agents/skills/context-loader' "${ROOT}/.codex/config.toml" ||
        ! grep -Fq '.agents/skills/design-tracker' "${ROOT}/.codex/config.toml" ||
        grep -Fq '.codex/skills/' "${ROOT}/.codex/config.toml"; then
        echo "  Codex config must reference canonical .agents skills directly"
        ok=false
    fi

    ${ok}
}
check "Native runtime boundaries" check_native_boundaries

# --------------------------------------------------------------------------
# 8) Bundled skill scripts and the docs that invoke them stay in sync:
#    every script path named in shared markdown exists, and every bundled
#    script is reachable from at least one document.
# --------------------------------------------------------------------------
check_skill_scripts() {
    local ok=true
    # Generated content is not documentation: run logs, checkpoints, and
    # project research can quote any path and must not drive this check.
    local -a doc_scope=(
        --include='*.md'
        --exclude-dir=logs
        --exclude-dir=checkpoints
        --exclude-dir=research
    )

    # 8a) Every .agents/skills/**.py|.sh path mentioned in shared markdown resolves.
    local referenced
    referenced=$(grep -rhoE "${doc_scope[@]}" '\.agents/skills/[A-Za-z0-9_/-]+\.(py|sh)' \
        "${ROOT}/.agents" 2>/dev/null | sort -u || true)
    referenced+=$'\n'
    referenced+=$(grep -rhoE '\.agents/skills/[A-Za-z0-9_/-]+\.(py|sh)' \
        "${ROOT}/AGENTS.md" "${ROOT}/README.md" 2>/dev/null | sort -u || true)
    local ref
    while IFS= read -r ref; do
        [[ -z "${ref}" ]] && continue
        if [[ ! -f "${ROOT}/${ref}" ]]; then
            echo "  Documented script does not exist: ${ref}"
            ok=false
        fi
    done <<< "$(echo "${referenced}" | sort -u)"

    # 8b) Every bundled script is documented somewhere, so orphans surface.
    #     Matching on the bare filename is enough: a script's own directory
    #     README refers to it by name, while callers use the full path.
    local script
    while IFS= read -r script; do
        [[ -z "${script}" ]] && continue
        local rel="${script#"${ROOT}/"}"
        if ! grep -rqF "${doc_scope[@]}" "$(basename "${rel}")" \
            "${ROOT}/.agents" "${ROOT}/README.md" 2>/dev/null; then
            echo "  Bundled script is not documented in any markdown: ${rel}"
            ok=false
        fi
    done < <(find "${ROOT}/.agents/skills" -type f \( -name '*.py' -o -name '*.sh' \) | sort)

    ${ok}
}
check "Skill scripts and docs in sync" check_skill_scripts

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ ${FAIL} -gt 0 ]]; then
    exit 1
fi
exit 0
