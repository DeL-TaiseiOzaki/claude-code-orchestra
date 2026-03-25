# Debug Patterns Reference

Common patterns for effective error/bug diagnosis and fix planning.

## Diagnosis Strategy

### 1. Reproduce First

Always confirm the error before diagnosing:

```bash
# Run the failing command/test
uv run pytest tests/test_failing.py -v

# Capture full output
uv run python script.py 2>&1 | tee error_output.txt
```

If the error is **not reproducible**, investigate:
- Environment differences (versions, OS, config)
- Timing / race conditions
- Data-dependent behavior

### 2. Narrow the Scope

Use binary search to isolate the problem:

```bash
# Git bisect — find the introducing commit
git bisect start
git bisect bad HEAD
git bisect good <known-good-commit>
# Test at each step, then:
git bisect reset

# Minimal reproduction — strip away unrelated code
# Start with the failing test case and remove dependencies one by one
```

### 3. Hypothesize, Then Verify

For each hypothesis:

| Step | Action |
|------|--------|
| State | "I think X causes Y because Z" |
| Predict | "If X is the cause, then changing A should produce B" |
| Test | Make the change, observe the result |
| Conclude | Confirmed → proceed / Eliminated → next hypothesis |

## Fix Task Categories

### 1. Test First (TDD for Bugs)

Write a failing test that captures the bug:

```python
def test_parse_config_missing_key_raises_error():
    """Regression test for bug: parse_config returns None on missing key."""
    # Arrange
    config = {"other_key": "value"}

    # Act & Assert
    with pytest.raises(KeyError):
        parse_config(config, "missing_key")
```

### 2. Root Cause Fix

Fix the underlying defect, not the symptom:

```python
# Bad: Suppress the symptom
def process(value):
    try:
        return transform(value)
    except TypeError:
        return None  # Hides the real problem

# Good: Fix the root cause
def process(value):
    if value is None:
        raise ValueError("value must not be None")
    return transform(value)
```

### 3. Blast Radius Fix

Address collateral damage from the root cause:

```
1. [Root cause] Fix parse_config() to raise KeyError
2. [Blast radius] Update caller_a() error handling
3. [Blast radius] Update caller_b() error handling
4. [Regression] Run full test suite
```

### 4. Regression Guard

Ensure the fix doesn't break other things:

```bash
# Run full test suite
uv run pytest -v

# Run with coverage to check affected areas
uv run pytest --cov=src --cov-report=term-missing

# Run type checker
uv run ty check src/
```

## Fix Task Granularity

### Too Coarse (Bad)
```
- Fix the authentication bug
```

### Too Fine (Bad)
```
- Add None check on line 42
- Change return type on line 43
- Update docstring on line 40
```

### Just Right (Good)
```
- Write failing test for auth token expiry edge case
- Fix token validation to handle expired tokens gracefully
- Update token refresh logic to prevent race condition
- Run auth test suite and verify all tests pass
```

## Common Bug Categories

### 1. State Mutation Bugs
- **Symptom**: Intermittent failures, order-dependent behavior
- **Diagnosis**: Track variable state through execution flow
- **Fix pattern**: Use immutable data, explicit state transitions

### 2. Boundary / Edge Case Bugs
- **Symptom**: Fails on specific inputs (None, empty, max values)
- **Diagnosis**: Test with boundary values
- **Fix pattern**: Input validation, early returns

### 3. Concurrency Bugs
- **Symptom**: Race conditions, deadlocks, intermittent failures
- **Diagnosis**: Analyze shared state access patterns
- **Fix pattern**: Locks, queues, immutable shared state

### 4. Dependency / Integration Bugs
- **Symptom**: Works locally, fails in CI or production
- **Diagnosis**: Check version differences, API changes
- **Fix pattern**: Pin versions, add integration tests

### 5. Type / Contract Bugs
- **Symptom**: TypeError, AttributeError, unexpected None
- **Diagnosis**: Trace type flow through call chain
- **Fix pattern**: Type hints, runtime validation, strict contracts

## Severity Classification

| Severity | Criteria | Response |
|----------|----------|----------|
| **Critical** | Data loss, security breach, system down | Immediate fix required |
| **High** | Core feature broken, no workaround | Fix before next release |
| **Medium** | Feature degraded, workaround exists | Schedule fix |
| **Low** | Minor annoyance, cosmetic issue | Fix when convenient |

## When to Escalate

Re-analyze or seek additional input when:

1. **Multiple hypotheses remain** — Cannot narrow down the root cause
2. **Fix introduces new failures** — The change has unexpected side effects
3. **Scope expansion** — Bug is deeper than initially thought
4. **External dependency** — Root cause is in a third-party library
