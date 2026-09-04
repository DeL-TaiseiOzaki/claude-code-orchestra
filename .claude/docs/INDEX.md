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
| Root agent contract           | normative             | `CLAUDE.md`                                   | Mission, routing, catalogs, execution, quality, language, ownership |
| CLI agent contract            | normative             | `AGENTS.md`                                   | Auto-loaded by every CLI runtime: response, handoff, cross-CLI invocation, guardrails |
| Tier definitions              | normative             | `.claude/rules/tiers.md`                            | 3-tier hierarchy (default/sol/fable) |
| Delegation-first policy       | normative             | `.claude/rules/delegation.md`                       | Self-handle list, mandatory triggers, route table, subagent prompt contract |
| Antigravity adapter           | normative             | `.agents/AGENTS.md`                           | Headless behaviour, why `--read-only` is refused |
| Codex adapter                 | normative             | `.codex/AGENTS.md`                            | Codex model config, sandbox discipline, enabled skills |
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
- **Root bootstrap**: `AGENTS.md` is the CLI-agent contract itself and routes the main agent to `CLAUDE.md`; no symlinks are involved
