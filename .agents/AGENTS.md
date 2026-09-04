# AGENTS.md -- Antigravity Adapter

This file is the **Antigravity-specific adapter**. The contract every CLI agent
follows -- response structure, handoff rules, cross-CLI subagent invocation, and
the completion-verification guardrails -- is the root [`AGENTS.md`](../AGENTS.md),
which Antigravity loads automatically. Read that first.

Antigravity operates as a **Tier 1 (`default`) executor** unless a task routes it
elsewhere. See [`.claude/rules/tiers.md`](../.claude/rules/tiers.md).

## Headless Behaviour and Limits

`agy -p` is the non-interactive mode the shared wrapper drives:

```bash
python3 .claude/skills/_shared/cli_consult.py --cli antigravity --prompt-file <path>
```

- **Headless auto-approves every tool call.** There is no caller-side flag that
  confines a run, which is why `cli_consult.py --read-only` is *refused* for this
  callee rather than accepted and silently ignored. A read-only Antigravity
  consultation is not available; use Codex with `--sandbox read-only` instead.
- Text output is captured verbatim; the exit code is the only success signal
  (there is no JSON envelope as with `claude -p`).
- `--resume` is not supported, so a multi-turn consultation must re-send its own
  context in the next prompt.
- Because nothing confines the run, the wrapper's `edits` object and
  `.claude/logs/cli-tools.jsonl` are the record of what it changed. Pass
  `--caller <your agent name>` so a change traces back to the agent that asked
  for it.

## Internal Context References

- `.claude/docs/DESIGN.md` -- macro requirements and design decisions
- `.claude/rules/` -- coding standards, delegation, and tier rules
- `.claude/skills/` -- workflow skills and deterministic helpers
- `.claude/STATE.md` -- active main agent and cross-session working state
