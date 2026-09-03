# Workflow: Feature (Antigravity)

```
status:   experimental/inactive
tiers:    default, sol, fable (optional)
trigger:  /feature (future Antigravity integration)
handoff:  .agents/docs/DESIGN.md, PROGRESS.md, git branch
```

> **NOT executable yet.** Full Antigravity support is a future phase.
> This skeleton documents the intended phase mapping only.

## Phases

1. **Mode Determination** -- existing project vs greenfield.
   See `.agents/skills/feature/SKILL.md` Phase 1.

2. **Analysis** (tier: default, Opus research) -- codebase analysis,
   dependency mapping, convention discovery.
   See `.agents/skills/feature/SKILL.md` Phase 2.

3. **Design & Plan** (tier: sol) -- architecture, implementation plan,
   patch strategy.
   See `.agents/skills/feature/SKILL.md` Phase 3.

4. **User Approval** -- present plan, wait for confirmation.
   See `.agents/skills/feature/SKILL.md` Phase 4.

5. **Complexity Routing**:
   - SIMPLE: sol direct implementation.
   - MODERATE: sol implementation + review.
   - COMPLEX: team-execute (parallel workers + reviewers).
   See `.agents/skills/feature/SKILL.md` Phase 5.

6. **Optional Fable Final Review** (tier: fable) -- for large or
   high-stakes changes, escalate to Tier 3 for final judgment.
