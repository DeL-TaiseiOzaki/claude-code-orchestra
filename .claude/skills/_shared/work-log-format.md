# Agent Teams Work Log — Shared Format (SSOT)

Canonical work-log template for every Agent Teams teammate. Skill prompts
reference this file instead of inlining the template.

## Contract

- **When**: written once, when ALL of the teammate's assigned tasks are complete.
- **Where**: `.claude/logs/agent-teams/{team-name}/{teammate-name}.md`
  (e.g. `researcher.md`, `architect.md`, `security-reviewer.md`).
- **Naming**: use the same `{team-name}` as the skill that spawned the team so
  logs line up across phases; `/checkpointing` embeds these logs verbatim.

## Template (5 core sections)

```markdown
# Work Log: {teammate role / name}
## Summary
(1-2 sentence summary of what you accomplished)
## Tasks Completed
- [x] {task}: {brief description of what was done / findings}
{role-specific sections go here — defined by the spawning skill's prompt}
## Communication with Teammates
- → {recipient}: {summary of message sent}
- ← {sender}: {summary of message received}
(If none, write 'None')
## Issues Encountered
- {issue}: {how it was resolved}
(If none, write 'None')
```

## Rules

1. The 5 core sections (`Summary`, `Tasks Completed`, `Communication with
   Teammates`, `Issues Encountered`, plus the role-specific block between
   `Tasks Completed` and `Communication with Teammates`) are mandatory.
2. **Reviewer roles** (e.g. in `/team-review`) replace `## Tasks Completed`
   with `## Review Scope` (files reviewed + focus areas) and `## Findings`
   (`- [{severity}] {file}:{line} — {issue summary}`).
3. Role-specific extra sections (e.g. `## Codex Consultations`,
   `## Files Modified`, `## Key Decisions`, `## Sources Consulted`) are listed
   inline in each skill's teammate prompt — keep them in the stated order.
4. Sections with nothing to report say `None`; never omit a core section.
