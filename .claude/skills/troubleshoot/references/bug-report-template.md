# Bug Report Template

Template contract for the Phase 1 Bug Report artifact.
All sections are REQUIRED unless marked otherwise.
`{placeholder}` tokens are filled by the orchestrator from error details, Opus subagent analysis, and Codex initial hypotheses.

---

```markdown
## Bug Report: {issue}

### Error
- Message: {error message}
- Location: {file:line}
- Stack trace: {key frames}

### Reproduction
- Steps: {numbered list}
- Reproducibility: {always / intermittent / environment-specific}

### Immediate Context
- Failing code: {file:line and surrounding logic}
- Call chain: {caller -> ... -> failing function}
- Recent changes: {relevant git commits}

### Affected Area
- Files involved: {list}
- Related tests: {list with pass/fail status}

### Initial Hypotheses (informed by Codex analysis)
1. {Hypothesis A}: {brief reasoning} -- Codex confidence: {high/medium/low}
2. {Hypothesis B}: {brief reasoning} -- Codex confidence: {high/medium/low}
3. {Hypothesis C}: {brief reasoning} -- Codex confidence: {high/medium/low}

### Codex Pattern Recognition
- Error pattern: {Codex's classification of the error type}
- Known similar patterns: {any patterns Codex identified}
- Recommended investigation priority: {Codex's suggested order}
```
