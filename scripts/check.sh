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
# 2) Tier IDs default/deep/fable all appear in tiers.md
# --------------------------------------------------------------------------
check_tier_ids() {
    local tiers="${ROOT}/.claude/rules/tiers.md"
    if [[ ! -f "${tiers}" ]]; then
        echo "  tiers.md not found"
        return 1
    fi
    local ok=true
    for id in default deep fable; do
        if ! grep -q "\`${id}\`" "${tiers}"; then
            echo "  Missing tier ID: ${id}"
            ok=false
        fi
    done
    ${ok}
}
check "Tier IDs present in tiers.md" check_tier_ids

# --------------------------------------------------------------------------
# 3) Model coherence: every bundled agent pins a Claude model in its
#    frontmatter, unspecified subagents default to a model in settings.json,
#    and no peer-CLI model setting survives (Claude Code-only edition).
# --------------------------------------------------------------------------
check_model_coherence() {
    local settings="${ROOT}/.claude/settings.json"
    local ok=true

    local default_model
    default_model=$(python3 -c "
import json
with open('${settings}') as f:
    d = json.load(f)
print(d.get('env', {}).get('CLAUDE_CODE_SUBAGENT_MODEL', ''))
" 2>/dev/null || true)
    if [[ -z "${default_model}" ]]; then
        echo "  Could not read env.CLAUDE_CODE_SUBAGENT_MODEL from ${settings}"
        ok=false
    fi

    local definition model
    for definition in "${ROOT}"/.claude/agents/*.md; do
        model=$(sed -n '2,/^---$/p' "${definition}" | grep -E '^model:' | head -1 \
            | sed 's/^model:[[:space:]]*//' || true)
        case "${model}" in
            opus|sonnet|haiku|fable|inherit|claude-*) ;;
            *)
                echo "  Agent without a Claude model in frontmatter: ${definition#"${ROOT}/"} (model='${model}')"
                ok=false
                ;;
        esac
    done

    # A leftover peer-CLI model variable means a half-removed integration.
    if grep -Eq '"[A-Z]+_MODEL"' "${settings}" &&
        ! python3 -c "
import json, sys
with open('${settings}') as f:
    env = json.load(f).get('env', {})
extra = [k for k in env if k.endswith('_MODEL') and not k.startswith('CLAUDE_')]
sys.exit(1 if extra else 0)
" 2>/dev/null; then
        echo "  settings.json env carries a non-Claude *_MODEL variable"
        ok=false
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
# 5) Root AGENTS.md is the complete contract: the main-agent orchestration
#    policy and the subagent completion guardrails live in the one file
#    Claude Code auto-loads.
# --------------------------------------------------------------------------
check_root_contract() {
    local contract="${ROOT}/AGENTS.md"
    if [[ ! -f "${contract}" || -L "${contract}" ]]; then
        echo "  AGENTS.md not found, or is a symlink instead of a real file"
        return 1
    fi

    local ok=true
    # The main-agent policy sections come first, the response, handoff, and
    # guardrail sections after; every section has to be in this one file.
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
        "## Required Response Structure"
        "## Handoff Rules"
        "## Internal Context References"
        "## Guardrails (Completion Verification)"
    )
    local heading
    for heading in "${headings[@]}"; do
        if ! grep -Fxq "${heading}" "${contract}"; then
            echo "  Missing contract heading: ${heading}"
            ok=false
        fi
    done

    local definition
    for definition in "${ROOT}"/.claude/agents/*.md; do
        local agent_name
        agent_name="$(basename "${definition}" .md)"
        grep -Fq "\`${agent_name}\`" "${contract}" || {
            echo "  Missing agent in AGENTS.md catalog: ${agent_name}"
            ok=false
        }
    done
    for definition in "${ROOT}"/.claude/skills/*/SKILL.md; do
        local skill_name
        skill_name="$(basename "$(dirname "${definition}")")"
        grep -Fq "\`${skill_name}\`" "${contract}" || {
            echo "  Missing skill in AGENTS.md catalog: ${skill_name}"
            ok=false
        }
    done

    # Tier definitions stay reachable from the root contract.
    local reference
    for reference in ".claude/rules/tiers.md"; do
        grep -Fq "${reference}" "${contract}" || {
            echo "  Missing route in root AGENTS.md: ${reference}"
            ok=false
        }
    done

    if [[ -e "${ROOT}/.claude/rules/orchestration.md" ]]; then
        echo "  Duplicate orchestration contract still exists under .claude/rules/"
        ok=false
    fi

    local index_entry
    index_entry=$(grep -F 'Root agent contract' "${ROOT}/.claude/docs/INDEX.md" || true)
    if [[ "${index_entry}" != *"normative"* ]]; then
        echo "  Root agent contract is not registered as normative in INDEX.md"
        ok=false
    fi

    ${ok}
}
check "Root orchestration contract" check_root_contract

# --------------------------------------------------------------------------
# 5b) No CLAUDE.md anywhere: Claude Code reads root AGENTS.md directly ONLY
#     while no CLAUDE.md sits in the working directory or above it. A
#     CLAUDE.md shadows the contract silently -- no warning, no error.
# --------------------------------------------------------------------------
check_no_claude_md() {
    local ok=true
    local shadow
    for shadow in CLAUDE.md .claude/CLAUDE.md CLAUDE.local.md; do
        if [[ -e "${ROOT}/${shadow}" || -L "${ROOT}/${shadow}" ]]; then
            echo "  ${shadow} exists: Claude Code reads it instead of root AGENTS.md"
            echo "  and silently stops loading the contract. Delete it; the merged"
            echo "  main-agent policy belongs in AGENTS.md."
            ok=false
        fi
    done
    ${ok}
}
check "No CLAUDE.md shadows AGENTS.md" check_no_claude_md

# --------------------------------------------------------------------------
# 6) Root instructions stay bounded and carry the always-needed information
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

    # The merged contract carries two roles, so the cap is 400 rather than the
    # 150 that bounded the old router-only file. It is a ceiling, not a target:
    # detail belongs under .claude/rules/.
    if (( $(wc -l < "${root_agents}") > 400 )); then
        echo "  AGENTS.md exceeds 400 lines"
        ok=false
    fi
    local reference
    for reference in ".claude/rules/" ".claude/skills/" ".claude/agents/" \
        ".claude/STATE.md" ".claude/docs/DESIGN.md"; do
        grep -Fq "${reference}" "${root_agents}" || {
            echo "  Missing essential root instruction: ${reference}"
            ok=false
        }
    done
    grep -Fq "Japanese" "${root_agents}" || ok=false
    grep -Fqi "verify" "${root_agents}" || ok=false
    if grep -q '@orchestra:' "${root_agents}"; then
        echo "  Legacy boundary marker found in AGENTS.md"
        ok=false
    fi

    ${ok}
}
check "Bootstrap references" check_bootstrap_references

# --------------------------------------------------------------------------
# 7) Runtime layout: .claude/ is the one physical runtime. The Claude
#    Code-only edition ships no peer-CLI adapter directories, so .agents/ and
#    .codex/ must be absent from the template.
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
    for real_file in AGENTS.md .claude/STATE.md .claude/rules/tiers.md \
        .claude/docs/INDEX.md; do
        if [[ ! -f "${ROOT}/${real_file}" || -L "${ROOT}/${real_file}" ]]; then
            echo "  Must be a real file, not a symlink or missing: ${real_file}"
            ok=false
        fi
    done

    # Peer-CLI adapter directories belong to the multi-CLI flavour on main.
    local peer_dir
    for peer_dir in .agents .codex; do
        if [[ -e "${ROOT}/${peer_dir}" || -L "${ROOT}/${peer_dir}" ]]; then
            echo "  Peer-CLI adapter directory present in the Claude Code-only edition: ${peer_dir}"
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

    if [[ ! -f "${ROOT}/.claude/settings.json" ]] ||
        ! grep -Fq '.claude/hooks/' "${ROOT}/.claude/settings.json" ||
        grep -Fq '.agents/hooks/' "${ROOT}/.claude/settings.json"; then
        echo "  Claude settings must reference .claude/hooks directly"
        ok=false
    fi

    # Every hook wired in settings.json must exist, so a renamed or deleted
    # hook cannot leave a dangling command behind.
    local hook
    while IFS= read -r hook; do
        [[ -z "${hook}" ]] && continue
        if [[ ! -f "${ROOT}/${hook}" ]]; then
            echo "  settings.json wires a missing hook: ${hook}"
            ok=false
        fi
    done < <(grep -oE '\.claude/hooks/[A-Za-z0-9_.-]+\.py' "${ROOT}/.claude/settings.json" | sort -u)

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
        "${ROOT}/.claude" 2>/dev/null | sort -u || true)
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
            "${ROOT}/.claude" "${ROOT}/README.md" 2>/dev/null; then
            echo "  Bundled script is not documented in any markdown: ${rel}"
            ok=false
        fi
    done < <(find "${ROOT}/.claude/skills" -type f \( -name '*.py' -o -name '*.sh' \) | sort)

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
