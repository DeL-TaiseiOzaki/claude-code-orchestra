# Diagnosis Report Template

Template contract for the Phase 3 user-facing diagnosis presentation.
All sections are REQUIRED. OPTIONAL sections are marked explicitly.
`{placeholder}` tokens are filled by the orchestrator from Phase 2 teammate outputs and the Opus plan validation.

---

```markdown
## Diagnosis Report: {issue}

### Error Reproduction
{Reproduction result -- confirmed / partially confirmed / could not reproduce}

### Root Cause (Root Cause Analyst)
- **Defect**: {description of the underlying defect}
- **Location**: `{file}:{line}`
- **Trigger**: {conditions under which the error occurs}
- **Evidence**: {key evidence supporting this conclusion}
- **Confidence**: {assessment of root cause certainty}

### Impact Assessment (Impact Investigator)
- **Blast radius**: {affected code paths and features}
- **Introducing commit**: {hash and description, if identified}
- **External context**: {known issues, upstream fixes if any}
- **Regression risk**: {what could break during fix}
- **Risk assessment**: {regression risk verdict from the risk analysis protocol}

### Fix Plan ({N} tasks) -- Opus Validated: {PASS / NEEDS_REVISION}
1. Write failing test to reproduce the bug
2. {Fix task -- the core fix}
3. {Additional fix tasks from blast radius}
4. {Additional test cases recommended by the validation}
5. Run full test suite for regression check

### Alternative Approaches Considered
- **Approach A**: {description} -- {why chosen / not chosen}
- **Approach B**: {description} -- {why chosen / not chosen}

### Next Steps
1. Shall we proceed with this fix plan?
2. After approval, start fix implementation and regression review with `/team-execute`

---
Shall we proceed with this fix plan?
```
