# Spike Report Template

Template contract for the Phase 3 Spike Report artifact (saved to `.agents/docs/research/spike-{topic}.md`).
All sections are REQUIRED unless marked OPTIONAL.
`{placeholder}` tokens are filled by the orchestrator from Phase 2 teammate outputs and Codex final evaluation.

---

```markdown
# Spike Report: {topic}

## Question
{The original spike question}

## Verdict: {GO / NO-GO / INCONCLUSIVE}
**Confidence**: {HIGH / MEDIUM / LOW}
**Decisive factor**: {one-sentence summary of why}

## Investigation Parameters
- Time budget: {duration}
- Mode: {RESEARCH-ONLY / PROTOTYPE}
- Date: {date}

## Success Criteria Evaluation
| Criterion | Evidence | Met? |
|-----------|----------|------|
| {criterion 1} | {evidence summary} | {YES / NO / PARTIAL} |
| {criterion 2} | {evidence summary} | {YES / NO / PARTIAL} |

## Sub-question Findings
### {Sub-question 1}
- Finding: {description}
- Evidence: {sources and data}
- Assessment: {FEASIBLE / NOT_FEASIBLE / UNKNOWN}

### {Sub-question 2}
- Finding: {description}
- Evidence: {sources and data}
- Assessment: {FEASIBLE / NOT_FEASIBLE / UNKNOWN}

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| {risk 1} | {H/M/L} | {H/M/L} | {strategy} |

## Prototype Results (if applicable)
- Tested: {what was tested}
- Result: {VALIDATED / INVALIDATED / INCONCLUSIVE}
- Evidence: {observations}

## Architecture Compatibility
- Assessment: {COMPATIBLE / REQUIRES_CHANGES / INCOMPATIBLE}
- Required changes: {list, if any}

## Alternatives Considered
| Alternative | Pros | Cons | Verdict |
|-------------|------|------|---------|
| {alt 1} | {pros} | {cons} | {recommendation} |

## Recommendation
{GO / NO-GO / INCONCLUSIVE with detailed reasoning}

### If GO
- Next step: {/feature — existing or greenfield mode}
- Key constraints to carry forward: {list}
- Risks to monitor: {list}

### If NO-GO
- Decisive blocker: {description}
- Suggested alternatives: {list}

### If INCONCLUSIVE
- Missing evidence: {what we still need}
- Suggested follow-up: {description}
```
