# Agent Registry (non-normative index)

## Ownership Boundary

| Directory  | Owns                                                                          |
|------------|-------------------------------------------------------------------------------|
| `.claude/` | Main agent runtime: rules, skills, agents, hooks, docs, logs, checkpoints, state, settings |

## Entries

| Item                          | Status                | Canonical File                                | Notes                              |
|-------------------------------|-----------------------|-----------------------------------------------|------------------------------------|
| Root agent contract           | normative             | `AGENTS.md`                                   | Mission, routing, catalogs, execution, quality, language, ownership |
| Subagent contract             | normative             | `AGENTS.md`                                   | Same file, second half: response, handoff, completion guardrails |
| Tier definitions              | normative             | `.claude/rules/tiers.md`                            | 3-tier hierarchy (default/deep/fable) |
| Delegation-first policy       | normative             | `.claude/rules/delegation.md`                       | Self-handle list, mandatory and deep-reasoning triggers, route table, subagent prompt contract |
| Shared rules                  | normative             | `.claude/rules/`                              | Coding, testing, security, routing, and state rules |
| Shared skills                 | normative             | `.claude/skills/`                             | Workflow and deterministic helper implementations |
| Agent definitions             | normative             | `.claude/agents/`                             | Model-specific executor definitions |
| Shared hooks                  | normative             | `.claude/hooks/`                              | Called directly from `.claude/settings.json` |
| Mutable agent state           | project-owned         | `.claude/STATE.md`                            | Repository identity and cross-session working state |
| Project documentation        | project-owned         | `.claude/docs/`                               | Design, research, reviews, and library notes |
| Approved plans                | project-owned         | `.claude/docs/plans/`                         | `/plan` output, consumed by `/team-execute` |
| Consistency checker           | tooling               | `scripts/check.sh`                            | Validates cross-file coherence     |

## Related Canonical Files (outside .claude/docs/)

- **Model configuration**: `.claude/settings.json` (`env.CLAUDE_CODE_SUBAGENT_MODEL`) and the `model:` frontmatter of each agent definition under `.claude/agents/`
- **Root bootstrap**: `AGENTS.md` is the single root contract Claude Code loads; no `CLAUDE.md` and no symlinks are involved
