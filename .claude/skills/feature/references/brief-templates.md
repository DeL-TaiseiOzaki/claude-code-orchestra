# Feature / Project Brief Templates

Template contracts for the MODE=existing Feature Brief and MODE=greenfield Project Brief.
Both sections are REQUIRED when the corresponding mode is active.
`{placeholder}` tokens are filled by the orchestrator from user requirements, Opus codebase scan, and Codex scope assessment.

---

## Feature Brief (MODE=existing)

```markdown
## Feature Brief: {feature}

### Current State
- Architecture: {existing architecture in affected area}
- Relevant files: {key files and modules}
- Patterns: {existing patterns to follow}

### Feature Goal
{User's desired outcome in 1-2 sentences}

### Scope
- Include: {list}
- Exclude: {list}

### Complexity Classification (from Codex)
- Classification: {SIMPLE / MODERATE / COMPLEX}
- Estimated files: {count}
- Estimated LOC: {range}
- Implementation route: {Codex direct / Codex + review / team-execute}

### Integration Points
- {Integration point 1}: {how the feature connects}
- {Integration point 2}: {how the feature connects}

### Risks
- {Risk 1}: {mitigation}
- {Risk 2}: {mitigation}

### Success Criteria
- {measurable criteria}
```

---

## Project Brief (MODE=greenfield)

```markdown
## Project Brief: {feature}

### Current State
- Architecture: {existing architecture summary}
- Relevant code: {key files and modules}
- Patterns: {existing patterns to follow}

### Goal
{User's desired outcome in 1-2 sentences}

### Scope
- Include: {list}
- Exclude: {list}

### Constraints
- {technical constraints}
- {library requirements}

### Success Criteria
- {measurable criteria}
```
