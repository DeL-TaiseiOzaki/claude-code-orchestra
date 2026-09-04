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

Each pattern: write the prompt body to a file, then call the wrapper (`.claude/skills/_shared/codex_consult.py`; see `../SKILL.md` for flags, JSON result, and exit codes). Reasoning effort follows the project's `.codex/config.toml` default (`model_reasoning_effort = "xhigh"`); override it per call with `--config model_reasoning_effort=<low|medium|high|xhigh>`.

### Pattern 1: Architecture Review

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << 'EOF'
Review the architecture of src/auth/ module. Focus on:
1. Single Responsibility adherence
2. Dependency direction (should flow inward)
3. Interface design clarity
4. Extensibility for future auth providers

Related files: src/auth/**/*.py
Constraints: Must maintain backward compatibility
EOF
python3 .claude/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label arch-review --sandbox read-only
```

### Pattern 2: Failure-Based Delegation

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << 'EOF'
This bug has resisted 2 fix attempts:

Symptom: Race condition in user session handling

Previous attempts:
1. Added mutex lock → Deadlock in high concurrency
2. Switched to RWLock → Still intermittent failures

Please analyze from fresh perspective:
- What root cause might we be missing?
- Are there architectural issues causing this?
- What alternative approaches should we consider?
EOF
python3 .claude/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label bug-analysis --sandbox read-only
```

### Pattern 3: Performance Optimization

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << 'EOF'
Optimize the algorithm in src/data/aggregator.py:

Current: O(n²) nested loops for data aggregation
Target: O(n log n) or better

Constraints:
- Must handle 100K+ records
- Memory limit: 512MB
- Cannot change public API

Provide:
1. Optimized implementation
2. Complexity analysis
3. Benchmark comparison approach
EOF
python3 .claude/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label perf-optimize --sandbox read-only
```

### Pattern 4: Security Audit

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << 'EOF'
Security audit of src/api/auth.py:

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
- LOW: Tech debt
EOF
python3 .claude/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label security-audit --sandbox read-only
```

## Cases Not to Delegate

| Case | Reason |
|------|--------|
| Simple CRUD operations | Routine work, no deep analysis needed |
| Small bug fixes (first attempt) | Try in Claude Code first |
| Documentation-only updates | Accuracy over creativity |
| Formatting / lint fixes | Mechanical processing |
