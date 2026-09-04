# .claude/docs/reviews/ — Review Notes and Audit Records

Durable review output: Fable (Tier 3) arbitration and final-review notes, and
audit records produced by a review sweep. Project-owned, so the updater never
overwrites this directory.

## What belongs here

| Kind | Naming | Written by |
|------|--------|-----------|
| Fable review note | `{topic}-{YYYY-MM-DD}.md` | `fable-advisor` (its only sanctioned write target) |
| Audit findings | `{scope}-audit-{group}-{YYYY-MM-DD}.md` | a review sweep, one note per group |
| Audit plan / interface spec | `{scope}-audit-{YYYY-MM-DD}-{PLAN,INTERFACE}.md` | the orchestrator of that sweep |

## Retention

Findings notes and plans have different lifetimes, and conflating them is how a
reviews directory rots into a pile of stale line numbers.

- **Findings notes are evidence, not documentation.** Their value is the
  `file:line` references that justify a fix — and the fix invalidates them. Once
  every finding in a note is fixed and the decision is recorded in
  `TEMPLATE_DESIGN_LOG.md`, the note is **prunable**. Delete it in a commit that
  names the design-log entry that supersedes it; do not "update" it, because a
  findings note edited after the fact is no longer a record of what was found.
- **Plans and interface specs are design record.** They explain why the
  resulting shape is the shape, which stays true after the fix. Keep them.
- **Fable notes are judgment record.** Keep them: a later reviewer needs to know
  what was already arbitrated and on what grounds.
- A note that still has unfixed findings is not prunable, whatever its age. If
  it is stale *and* unfixed, that is a backlog item, not a cleanup.

## Excluded from two repo checks

`scripts/check.sh` check 8 and
`tests/test_orchestration_contract.py::test_shared_runtime_docs_use_canonical_agents_paths`
skip this directory, for the same reason they skip `logs/`, `checkpoints/`, and
`research/`: a finding has to be able to quote the legacy path it is about, and a
proposal has to be able to name a script that does not exist yet. Nothing here is
loaded at runtime, so a stale path in a note cannot mislead an agent mid-task —
it can only mislead a reader, which the retention rule above addresses.

This exclusion is not a licence for runtime content to hide here. Rules, skills,
and helper scripts belong in `.claude/rules/`, `.claude/skills/`, and
`.claude/skills/_shared/`, where the checks apply.
