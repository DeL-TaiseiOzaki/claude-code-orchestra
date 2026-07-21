# .agents/ Registry (non-normative index)

## Ownership Boundary

| Directory   | Owns                                                        |
|-------------|-------------------------------------------------------------|
| `.agents/`  | Shared policy/capabilities plus project docs, logs, checkpoints, and state |
| `.claude/`  | Claude Code native configuration only                         |
| `.codex/`   | Codex native configuration only                               |

## Entries

| Item                          | Status                | Canonical File                                | Notes                              |
|-------------------------------|-----------------------|-----------------------------------------------|------------------------------------|
| Root agent contract           | normative             | `AGENTS.md`                                  | Mission, routing, catalogs, execution, quality, language, ownership |
| Tier definitions              | normative             | `.agents/rules/tiers.md`                            | 3-tier hierarchy (default/sol/fable) |
| CLI executor extension        | normative             | `.agents/rules/cli-execution.md`                           | Response, handoff, and verification rules |
| Shared rules                  | normative             | `.agents/rules/`                              | Coding, testing, security, routing, and state rules |
| Shared skills                 | normative             | `.agents/skills/`                             | Workflow and deterministic helper implementations |
| Agent definitions             | normative             | `.agents/agents/`                             | Model-specific executor definitions |
| Shared hooks                  | normative             | `.agents/hooks/`                              | Called directly from `.claude/settings.json` |
| Mutable agent state           | project-owned         | `.agents/STATE.md`                            | Repository identity and cross-session working state |
| Main-agent change runbook     | normative             | `.agents/change_main.md`                      | On-demand procedure for changing the main runtime |
| Project documentation        | project-owned         | `.agents/docs/`                               | Design, research, reviews, and library notes |
| Antigravity workflows         | experimental/inactive | `.agents/workflows/antigravity/`              | Future multi-agent orchestration   |
| Consistency checker           | tooling               | `.agents/check.sh`                            | Validates cross-file coherence     |

## Related Canonical Files (outside .agents/)

- **Model configuration**: `.claude/settings.json` (`env.CODEX_MODEL`) and `.codex/config.toml` (`model`)
- **Claude-to-Codex details**: `.agents/rules/codex-delegation.md`
- **Root bootstrap**: `AGENTS.md`; `CLAUDE.md` is a relative symlink to it
