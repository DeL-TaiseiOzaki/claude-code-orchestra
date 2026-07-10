# Workflow: Troubleshoot (Antigravity)

```
status:   experimental/inactive
tiers:    default, sol, fable (escalation)
trigger:  /troubleshoot (future Antigravity integration)
handoff:  .claude/docs/DESIGN.md, PROGRESS.md, git diff
```

> **NOT executable yet.** Full Antigravity support is a future phase.
> This skeleton documents the intended phase mapping only.

## Phases

1. **Reproduction & Context** (tiers: default + sol) -- reproduce the
   issue, gather logs, identify affected components.
   See `.claude/skills/troubleshoot/SKILL.md` Phase 1.

2. **Parallel Diagnosis** (tier: sol-driven) -- root cause analysis
   and impact assessment run concurrently.
   See `.claude/skills/troubleshoot/SKILL.md` Phase 2.

3. **Fix Plan Synthesis & Approval** (tier: sol) -- propose fix,
   validate against acceptance criteria.
   See `.claude/skills/troubleshoot/SKILL.md` Phase 3.

4. **Escalation** (tier: fable) -- if diagnosis is stuck or fix
   attempts fail, escalate to Tier 3 for arbitration and unblocking.
