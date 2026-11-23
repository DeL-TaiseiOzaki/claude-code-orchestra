# Agent Registry (non-normative index)

## Ownership Boundary

| Directory  | Owns                                                                          |
|------------|-------------------------------------------------------------------------------|
| `.claude/` | Main agent runtime: rules, skills, agents, hooks, docs, logs, checkpoints, state, settings |
| `.agents/` | Antigravity's native directory: its runtime adapter                            |
| `.codex/`  | Codex's native directory: adapter contract and native configuration            |

## Entries

| Item                          | Status                | Canonical File                                | Notes                              |
|-------------------------------|-----------------------|-----------------------------------------------|------------------------------------|
| Root bootstrap                | project-owned         | `AGENTS.md`                                   | Single always-loaded file: project facts, conventions, agent roles, pointers into `.claude/`; converted once by `/start-project` |
| Main-agent contract           | normative             | `.claude/rules/orchestration.md`              | Mission, routing, catalogs, execution, quality, language, ownership; main agent only |
| CLI contract (caller side)    | normative             | `.claude/rules/cli-contract.md`               | Cross-CLI invocation through the wrappers, completion guardrails |
| Executor contract (callee side) | normative           | `.claude/skills/_shared/executor_contract.md` | Prepended by both consult wrappers with `ORCHESTRA_ROLE=executor`: role, response structure, handoff |
| Project setup                 | normative             | `.claude/skills/start-project/`               | `/start-project`: converts `AGENTS.md` (`write_agents_md.py`), DESIGN.md, identity pointer |
| Tier definitions              | normative             | `.claude/rules/tiers.md`                            | 3-tier hierarchy (default/sol/fable) |
| Delegation-first policy       | normative             | `.claude/rules/delegation.md`                       | Self-handle list, mandatory triggers, route table, subagent prompt contract |
| Antigravity adapter           | normative             | `.agents/AGENTS.md`                           | Headless behaviour, read-only deny rules, three routed uses |
| Codex adapter                 | reference             | `.codex/AGENTS.md`                            | Reference only (Codex does not auto-load it): model config, sandbox discipline, enabled skills |
| Shared rules                  | normative             | `.claude/rules/`                              | Coding, testing, security, routing, and state rules |
| Shared skills                 | normative             | `.claude/skills/`                             | Workflow and deterministic helper implementations |
| Agent definitions             | normative             | `.claude/agents/`                             | Model-specific executor definitions |
| Shared hooks                  | normative             | `.claude/hooks/`                              | Called directly from `.claude/settings.json` |
| Mutable agent state           | project-owned         | `.claude/STATE.md`                            | Repository identity and cross-session working state |
| Main-agent change runbook     | normative             | `.claude/docs/change_main.md`                      | On-demand procedure for changing the main runtime |
| Project documentation        | project-owned         | `.claude/docs/`                               | Design, research, reviews, and library notes |
| Approved plans                | project-owned         | `.claude/docs/plans/`                         | `/plan` output, consumed by `/team-execute` |
| Consistency checker           | tooling               | `scripts/check.sh`                            | Validates cross-file coherence     |

## Related Canonical Files (outside .claude/docs/)

- **Model configuration**: `.claude/settings.json` (`env.CODEX_MODEL`) and `.codex/config.toml` (`model`)
- **Claude-to-Codex details**: `.claude/rules/codex-delegation.md`
- **Root bootstrap**: `AGENTS.md` is the only root instruction file; there is no `CLAUDE.md` (a CLAUDE.md, CLAUDE.local.md, or .claude/CLAUDE.md file makes Claude Code skip `AGENTS.md`); no symlinks are involved
