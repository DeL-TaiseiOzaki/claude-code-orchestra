# .agents/ Registry (non-normative index)

## Ownership Boundary

| Directory   | Owns                                                        |
|-------------|-------------------------------------------------------------|
| `.claude/`  | Main agent (Claude Code orchestrator) spec and configuration |
| `.agents/`  | CLI subagent spec (tool-neutral: Codex, Antigravity, Grok, ...) |
| `.codex/`   | Codex-specific adapter (config, skills, prompt overrides)    |

## Entries

| Item                          | Status                | Canonical File                                | Notes                              |
|-------------------------------|-----------------------|-----------------------------------------------|------------------------------------|
| Tier definitions              | normative             | `.agents/tiers.md`                            | 3-tier hierarchy (default/sol/fable) |
| Common subagent contract      | normative             | `.agents/AGENTS.md`                           | Rules for all CLI subagents        |
| Antigravity workflows         | experimental/inactive | `.agents/workflows/antigravity/`              | Future multi-agent orchestration   |
| Consistency checker           | tooling               | `.agents/check.sh`                            | Validates cross-file coherence     |

## Related Canonical Files (outside .agents/)

- **Model configuration**: `.claude/settings.json` (`env.CODEX_MODEL`) and `.codex/config.toml` (`model`)
- **Delegation rules**: `.claude/rules/codex-delegation.md` (when to delegate to CLI subagents)
- **Routing policy**: `CLAUDE.md` section 3 (Routing Policy)
- **Root pointer**: `AGENTS.md` (repo root, thin redirect to `.agents/AGENTS.md`)
