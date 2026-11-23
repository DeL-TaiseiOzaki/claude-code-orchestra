#!/usr/bin/env bash
# scripts/check.sh -- Consistency checker for the repository's agent contracts.
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
    local index="${ROOT}/.claude/docs/INDEX.md"
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
    local tiers="${ROOT}/.claude/rules/tiers.md"
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
    # Generated run logs can quote this very pattern (a consult that read
    # check.sh), so they are not part of the shared configuration.
    fallbacks=$(grep -rhoE --exclude-dir=logs '\$\{CODEX_MODEL:-[^}]+\}' \
        "${ROOT}/.claude/" "${ROOT}/.codex/" 2>/dev/null \
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
    local consult="${ROOT}/.claude/skills/_shared/codex_consult.py"
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
# 4) Template-owned runtime subdirectories are listed in SAFE_DIRS
# --------------------------------------------------------------------------
check_safe_dirs() {
    local update="${ROOT}/scripts/update.sh"
    if [[ ! -f "${update}" ]]; then
        echo "  scripts/update.sh not found"
        return 1
    fi
    local dir
    for dir in .claude/rules .claude/skills .claude/agents .claude/hooks; do
        if ! grep -q "\"${dir}\"" "${update}"; then
            echo "  ${dir} not found in SAFE_DIRS"
            return 1
        fi
    done
}
check "Template runtime paths in SAFE_DIRS" check_safe_dirs

# --------------------------------------------------------------------------
# 5) .claude/rules/orchestration.md is the complete main-agent contract
# --------------------------------------------------------------------------
check_root_contract() {
    local contract="${ROOT}/.claude/rules/orchestration.md"
    if [[ ! -f "${contract}" || -L "${contract}" ]]; then
        echo "  .claude/rules/orchestration.md not found, or is a symlink instead of a real file"
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
        if [[ "$(grep -Fxc "${heading}" "${contract}" || true)" != "1" ]]; then
            echo "  Contract heading missing or duplicated: ${heading}"
            ok=false
        fi
    done

    local definition
    for definition in "${ROOT}"/.claude/agents/*.md; do
        local agent_name
        agent_name="$(basename "${definition}" .md)"
        grep -Fq "\`${agent_name}\`" "${contract}" || {
            echo "  Missing agent in orchestration.md catalog: ${agent_name}"
            ok=false
        }
    done
    for definition in "${ROOT}"/.claude/skills/*/SKILL.md; do
        local skill_name
        skill_name="$(basename "$(dirname "${definition}")")"
        grep -Fq "\`${skill_name}\`" "${contract}" || {
            echo "  Missing skill in orchestration.md catalog: ${skill_name}"
            ok=false
        }
    done

    if (( $(wc -l < "${contract}") > 150 )); then
        echo "  orchestration.md exceeds 150 lines"
        ok=false
    fi
    local reference
    for reference in ".claude/rules/" ".claude/skills/" ".claude/agents/" \
        ".claude/STATE.md" ".claude/docs/DESIGN.md" ".claude/docs/change_main.md" \
        ".claude/rules/cli-contract.md" "executor_contract.md"; do
        grep -Fq "${reference}" "${contract}" || {
            echo "  Missing essential reference in orchestration.md: ${reference}"
            ok=false
        }
    done
    grep -Fqi "verify" "${contract}" || ok=false
    # The scope line keeps a wrapper-started executor from acting as main.
    grep -Fq "delegated executor" "${contract}" || {
        echo "  orchestration.md does not scope itself away from delegated executors"
        ok=false
    }
    grep -Fq "built-in \`/init\`" "${contract}" || {
        echo "  orchestration.md does not forbid Claude Code's built-in /init"
        ok=false
    }

    local index_entry
    index_entry=$(grep -F 'Main-agent contract' "${ROOT}/.claude/docs/INDEX.md" || true)
    if [[ "${index_entry}" != *"normative"* || "${index_entry}" != *"orchestration.md"* ]]; then
        echo "  orchestration.md is not registered as normative in INDEX.md"
        ok=false
    fi

    ${ok}
}
check "Main-agent orchestration contract" check_root_contract

# --------------------------------------------------------------------------
# 6) Root AGENTS.md is the single, thin, project-owned bootstrap; the
#    template policy it points to exists under .claude/
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

# Body of a "## " section (up to the next "## " heading).
markdown_section() {
    local file="$1" heading="$2"
    awk -v h="${heading}" '$0 == h {found = 1; next} found && /^## / {exit} found {print}' "${file}"
}

AGENTS_SKELETON_MARKER='_Not initialized — run `/start-project`'

check_bootstrap_references() {
    local agents="${ROOT}/AGENTS.md"
    local ok=true

    if [[ ! -f "${agents}" || -L "${agents}" ]]; then
        echo "  Root AGENTS.md not found, or is a symlink instead of a real file"
        return 1
    fi
    local heading
    for heading in "## Project" "## Commands" "## Conventions" "## Agent Roles" \
        "## Orchestra References"; do
        if [[ "$(grep -Fxc "${heading}" "${agents}" || true)" != "1" ]]; then
            echo "  Root AGENTS.md heading missing or duplicated: ${heading}"
            ok=false
        fi
    done
    if (( $(wc -l < "${agents}") > 150 )); then
        echo "  Root AGENTS.md exceeds 150 lines"
        ok=false
    fi
    if (( $(wc -c < "${agents}") >= 32768 )); then
        echo "  Root AGENTS.md is 32 KiB or larger"
        ok=false
    fi
    if grep -q '@orchestra:' "${agents}"; then
        echo "  Legacy boundary marker found in root AGENTS.md"
        ok=false
    fi
    local roles references marker
    roles="$(markdown_section "${agents}" "## Agent Roles")"
    for marker in "executor_contract.md" "ORCHESTRA_ROLE"; do
        grep -Fq "${marker}" <<< "${roles}" || {
            echo "  Root AGENTS.md Agent Roles does not mention ${marker}"
            ok=false
        }
    done
    references="$(markdown_section "${agents}" "## Orchestra References")"
    for marker in ".claude/rules/orchestration.md" ".claude/rules/cli-contract.md"; do
        grep -Fq "${marker}" <<< "${references}" || {
            echo "  Root AGENTS.md Orchestra References does not mention ${marker}"
            ok=false
        }
    done

    # An unconverted skeleton must be one update.sh recognizes, or the next
    # update would treat it as project-owned and never replace it.
    if grep -Fq "${AGENTS_SKELETON_MARKER}" "${agents}"; then
        local blob
        blob="$(git hash-object -- "${agents}")"
        grep -Fq "\"AGENTS.md:${blob}\"" "${ROOT}/scripts/update.sh" || {
            echo "  Skeleton AGENTS.md blob ${blob} is not in update.sh KNOWN_TEMPLATE_BLOBS"
            ok=false
        }
    fi

    local cli_contract="${ROOT}/.claude/rules/cli-contract.md"
    local section
    for section in "## Cross-CLI Subagent Invocation" \
        "## Guardrails (Completion Verification)"; do
        grep -Fxq "${section}" "${cli_contract}" 2>/dev/null || {
            echo "  .claude/rules/cli-contract.md is missing: ${section}"
            ok=false
        }
    done
    local executor="${ROOT}/.claude/skills/_shared/executor_contract.md"
    for section in "## Role" "## Required Response Structure" "## Handoff Rules"; do
        grep -Fxq "${section}" "${executor}" 2>/dev/null || {
            echo "  executor_contract.md is missing: ${section}"
            ok=false
        }
    done

    ${ok}
}
check "Bootstrap references" check_bootstrap_references

# --------------------------------------------------------------------------
# 6b) No instruction file shadows AGENTS.md: Claude Code skips AGENTS.md while
#     CLAUDE.md, CLAUDE.local.md, or .claude/CLAUDE.md exists in the project or
#     a parent. A file that only imports "@AGENTS.md" is the manual fallback.
# --------------------------------------------------------------------------
is_agents_shim() {
    [[ "$(tr -d '[:space:]' < "$1" 2>/dev/null)" == "@AGENTS.md" ]]
}

check_instruction_shadowing() {
    local ok=true name path dir user_memory
    for name in CLAUDE.md CLAUDE.local.md .claude/CLAUDE.md; do
        path="${ROOT}/${name}"
        if [[ -e "${path}" || -L "${path}" ]] && ! is_agents_shim "${path}"; then
            echo "  ${name} shadows AGENTS.md; back it up and remove it (scripts/update.sh does this)"
            ok=false
        fi
    done
    user_memory="${HOME:-/nonexistent}/.claude/CLAUDE.md"
    dir="$(dirname "${ROOT}")"
    while :; do
        for name in CLAUDE.md CLAUDE.local.md .claude/CLAUDE.md; do
            path="${dir%/}/${name}"
            [[ "${path}" == "${user_memory}" ]] && continue
            if [[ -f "${path}" ]] && ! is_agents_shim "${path}"; then
                echo "  WARN: ${path} (a parent directory) makes Claude Code skip AGENTS.md"
            fi
        done
        [[ "${dir}" == "/" ]] && break
        dir="$(dirname "${dir}")"
    done
    ${ok}
}
check "No instruction file shadows AGENTS.md" check_instruction_shadowing

# --------------------------------------------------------------------------
# 6c) Both consult wrappers inject the executor contract
# --------------------------------------------------------------------------
check_executor_contract_wiring() {
    local ok=true wrapper
    local shared="${ROOT}/.claude/skills/_shared"
    for wrapper in cli_consult.py codex_consult.py; do
        grep -Fq "executor_contract.prepare_prompt" "${shared}/${wrapper}" &&
            grep -Fq "executor_contract.executor_env" "${shared}/${wrapper}" || {
            echo "  ${wrapper} does not inject the executor contract"
            ok=false
        }
    done
    grep -Fq 'ROLE_ENV_VAR = "ORCHESTRA_ROLE"' "${shared}/executor_contract.py" 2>/dev/null || {
        echo "  executor_contract.py does not define ORCHESTRA_ROLE"
        ok=false
    }
    ${ok}
}
check "Executor contract wiring" check_executor_contract_wiring

# --------------------------------------------------------------------------
# 7) Runtime layout: .claude/ is the physical source, .agents/ and .codex/
#    carry subagent schema only
# --------------------------------------------------------------------------
check_native_boundaries() {
    local ok=true
    local canonical_dir
    for canonical_dir in rules skills agents hooks docs logs checkpoints; do
        local canonical="${ROOT}/.claude/${canonical_dir}"
        if [[ ! -d "${canonical}" || -L "${canonical}" ]]; then
            echo "  Canonical runtime directory is missing or a symlink: .claude/${canonical_dir}"
            ok=false
        fi
    done

    # The layout is symlink-free: every contract file is a real file so the
    # checkout survives filesystems and CI runners that do not honour symlinks.
    local real_file
    for real_file in AGENTS.md .agents/AGENTS.md .codex/AGENTS.md \
        .claude/STATE.md .claude/rules/tiers.md .claude/rules/orchestration.md \
        .claude/rules/cli-contract.md .claude/skills/_shared/executor_contract.md \
        .claude/docs/INDEX.md .claude/docs/change_main.md; do
        if [[ ! -f "${ROOT}/${real_file}" || -L "${ROOT}/${real_file}" ]]; then
            echo "  Must be a real file, not a symlink or missing: ${real_file}"
            ok=false
        fi
    done

    # Shared runtime content must not be duplicated back into the subagent
    # schema directories.
    local forbidden_path
    for forbidden_path in \
        .agents/rules .agents/skills .agents/agents .agents/hooks \
        .agents/docs .agents/logs .agents/checkpoints .agents/STATE.md \
        .codex/skills; do
        if [[ -e "${ROOT}/${forbidden_path}" || -L "${ROOT}/${forbidden_path}" ]]; then
            echo "  Runtime content duplicated into a subagent schema directory: ${forbidden_path}"
            ok=false
        fi
    done

    local native_entry
    while IFS= read -r native_entry; do
        case "${native_entry}" in
            settings.json|settings.local.json|settings.orchestra.json|orchestra-version) ;;
            agents|skills|rules|hooks|docs|logs|checkpoints|STATE.md) ;;
            *) echo "  Unexpected .claude entry: ${native_entry}"; ok=false ;;
        esac
    done < <(find "${ROOT}/.claude" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
    while IFS= read -r native_entry; do
        case "${native_entry}" in
            config.toml|config.orchestra.toml|AGENTS.md) ;;
            *) echo "  Unexpected .codex entry: ${native_entry}"; ok=false ;;
        esac
    done < <(find "${ROOT}/.codex" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
    # .agents/ is Antigravity's native directory and holds exactly one thing:
    # the CLI-subagent contract it loads. Shared policy lives under .claude/
    # and is referenced by path.
    while IFS= read -r native_entry; do
        if [[ "${native_entry}" != "AGENTS.md" ]]; then
            echo "  Unexpected .agents entry: ${native_entry}"
            ok=false
        fi
    done < <(find "${ROOT}/.agents" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)

    if [[ ! -f "${ROOT}/.claude/settings.json" ]] ||
        ! grep -Fq '.claude/hooks/' "${ROOT}/.claude/settings.json" ||
        grep -Fq '.agents/hooks/' "${ROOT}/.claude/settings.json"; then
        echo "  Claude settings must reference .claude/hooks directly"
        ok=false
    fi
    if [[ ! -f "${ROOT}/.codex/config.toml" ]] ||
        ! grep -Fq '.claude/skills/context-loader' "${ROOT}/.codex/config.toml" ||
        ! grep -Fq '.claude/skills/design-tracker' "${ROOT}/.codex/config.toml" ||
        grep -Fq '.codex/skills/' "${ROOT}/.codex/config.toml"; then
        echo "  Codex config must reference canonical .claude skills directly"
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
    # Generated content is not documentation: run logs, checkpoints, project
    # research, and review notes can quote any path and must not drive this
    # check. Review notes in particular record audit findings and proposals, so
    # they name scripts that do not exist yet by design.
    local -a doc_scope=(
        --include='*.md'
        --exclude-dir=logs
        --exclude-dir=checkpoints
        --exclude-dir=research
        --exclude-dir=reviews
    )

    # 8a) Every .claude/skills/**.py|.sh path mentioned in shared markdown resolves.
    local referenced
    referenced=$(grep -rhoE "${doc_scope[@]}" '\.claude/skills/[A-Za-z0-9_/-]+\.(py|sh)' \
        "${ROOT}/.claude" "${ROOT}/.agents" "${ROOT}/.codex" 2>/dev/null | sort -u || true)
    referenced+=$'\n'
    referenced+=$(grep -rhoE '\.claude/skills/[A-Za-z0-9_/-]+\.(py|sh)' \
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
            "${ROOT}/.claude" "${ROOT}/.agents" "${ROOT}/README.md" 2>/dev/null; then
            echo "  Bundled script is not documented in any markdown: ${rel}"
            ok=false
        fi
    done < <(find "${ROOT}/.claude/skills" -type f \( -name '*.py' -o -name '*.sh' \) | sort)

    ${ok}
}
check "Skill scripts and docs in sync" check_skill_scripts

# --------------------------------------------------------------------------
# 9) Peer-CLI routing: Antigravity is a formally routed Tier 1 subagent, not
#    just a callable wrapper target, and orchestration.md describes .agents/
#    truthfully.
# --------------------------------------------------------------------------
check_peer_cli_routing() {
    local ok=true
    local agent="${ROOT}/.claude/agents/antigravity-delegate.md"

    if [[ ! -f "${agent}" ]]; then
        echo "  Missing agent definition: .claude/agents/antigravity-delegate.md"
        return 1
    fi
    grep -Fxq 'model: sonnet' "${agent}" || {
        echo "  antigravity-delegate.md must declare 'model: sonnet'"
        ok=false
    }
    grep -Fq 'cli_consult.py --cli antigravity' "${agent}" || {
        echo "  antigravity-delegate.md must call 'cli_consult.py --cli antigravity'"
        ok=false
    }
    # The flag must sit in the command itself; prose such as "never omit
    # `--read-only`" must not be able to satisfy the check on its own.
    grep -Fq -- 'cli_consult.py --cli antigravity --read-only' "${agent}" || {
        echo "  antigravity-delegate.md must call 'cli_consult.py --cli antigravity --read-only'"
        ok=false
    }
    grep -Fq 'antigravity-delegate' "${ROOT}/.claude/rules/delegation.md" || {
        echo "  delegation.md does not route to antigravity-delegate"
        ok=false
    }
    grep -Fq 'Antigravity' "${ROOT}/.claude/rules/tiers.md" || {
        echo "  tiers.md does not place Antigravity in a tier"
        ok=false
    }

    # The .agents/ bullet used to list a workflows/ tree, tiers.md, and
    # check.sh that no longer live there.
    local agents_bullet
    agents_bullet=$(awk '/^- `\.agents\/`/ {found = 1; print; next}
        found && /^- / {exit} found {print}' "${ROOT}/.claude/rules/orchestration.md")
    local stale
    for stale in 'workflows/' 'tiers.md' 'check.sh'; do
        if grep -Fq "${stale}" <<< "${agents_bullet}"; then
            echo "  orchestration.md .agents/ bullet still mentions ${stale}"
            ok=false
        fi
    done

    ${ok}
}
check "Peer CLI routing" check_peer_cli_routing

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ ${FAIL} -gt 0 ]]; then
    exit 1
fi
exit 0
