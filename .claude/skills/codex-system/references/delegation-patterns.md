# Delegation Pattern Details

## Delegation Decision Flowchart

```
Task received
    |
    v
+---------------------------+
| Explicit Codex request?   |
+-----------+---------------+
    +-------+-------+
    | Yes          | No
    v              v
  Delegate   +---------------------------+
             | Complexity check           |
             +-----------+---------------+
             +-----------+-----------+
             | Yes                   | No
             v                       v
           Delegate         +---------------------------+
                            | Failure check (2+ times)  |
                            +-----------+---------------+
                            +-----------+-----------+
                            | Yes                   | No
                            v                       v
                          Delegate         +---------------------------+
                                           | Quality / security req?   |
                                           +-----------+---------------+
                                           +-----------+-----------+
                                           | Yes                   | No
                                           v                       v
                                         Delegate         Execute in Claude Code
```

## Execution Examples by Pattern

### Pattern 1: Architecture Review

```bash
codex exec \
  --model gpt-5-codex \
  --config model_reasoning_effort="high" \
  --sandbox read-only \
  --full-auto \
  "Review the architecture of src/auth/ module. Focus on:
   1. Single Responsibility adherence
   2. Dependency direction (should flow inward)
   3. Interface design clarity
   4. Extensibility for future auth providers

   Related files: src/auth/**/*.py
   Constraints: Must maintain backward compatibility" 2>/dev/null
```

### Pattern 2: Failure-Based Delegation

```bash
codex exec \
  --model gpt-5-codex \
  --config model_reasoning_effort="high" \
  --sandbox read-only \
  --full-auto \
  "This bug has resisted 2 fix attempts:

   Symptom: Race condition in user session handling

   Previous attempts:
   1. Added mutex lock → Deadlock in high concurrency
   2. Switched to RWLock → Still intermittent failures

   Please analyze from fresh perspective:
   - What root cause might we be missing?
   - Are there architectural issues causing this?
   - What alternative approaches should we consider?" 2>/dev/null
```

### Pattern 3: Performance Optimization

```bash
codex exec \
  --model gpt-5-codex \
  --config model_reasoning_effort="xhigh" \
  --sandbox read-only \
  --full-auto \
  "Optimize the algorithm in src/data/aggregator.py:

   Current: O(n²) nested loops for data aggregation
   Target: O(n log n) or better

   Constraints:
   - Must handle 100K+ records
   - Memory limit: 512MB
   - Cannot change public API

   Provide:
   1. Optimized implementation
   2. Complexity analysis
   3. Benchmark comparison approach" 2>/dev/null
```

### Pattern 4: Security Audit

```bash
codex exec \
  --model gpt-5-codex \
  --config model_reasoning_effort="xhigh" \
  --sandbox read-only \
  --full-auto \
  "Security audit of src/api/auth.py:

   Check for:
   - SQL injection vulnerabilities
   - XSS attack vectors
   - CSRF protection
   - Proper input validation
   - Secure password handling
   - Session management issues

   Output format:
   - CRITICAL: Must fix immediately
   - HIGH: Fix before release
   - MEDIUM: Address in next sprint
   - LOW: Tech debt" 2>/dev/null
```

## Cases Not to Delegate

| Case | Reason |
|------|--------|
| Simple CRUD operations | Routine work, no deep analysis needed |
| Small bug fixes (first attempt) | Try in Claude Code first |
| Documentation-only updates | Accuracy over creativity |
| Formatting / lint fixes | Mechanical processing |
