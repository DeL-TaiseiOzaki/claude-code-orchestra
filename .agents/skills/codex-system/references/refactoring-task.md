# Refactoring Task for Codex

When delegating refactoring to Codex, use this prompt template.

## Prompt Template

```
Refactor the following code for improved readability and maintainability.

## Target Code
{file path and content}

## Libraries Used
{list of libraries with constraints from .agents/docs/libraries/}

## Refactoring Goals
{specific goals or "General simplification"}

---

Core Principles:

### Pursuit of Simplicity
- Readable code over complex code
- 1 function = 1 responsibility
- Keep nesting shallow (early return)
- Eliminate magic numbers/strings

### Preserving Library Functionality
- Maintain all library constraints
- Don't change library usage patterns unless necessary
- Verify async/sync requirements

---

Refactoring Patterns to Apply:

### Extract Function
- Break long functions into smaller, focused functions
- Each function should do one thing

### Early Return
- Replace nested if-else with guard clauses
- Return early for error/edge cases

### Add Type Hints
- Add type annotations to all functions
- Use Optional, Union appropriately

### Remove Duplication
- Extract common logic to shared functions
- Use appropriate abstractions (but don't over-abstract)

---

Provide:
1. Refactored code
2. Explanation of changes
3. Verification that library constraints are preserved
```

## Example Invocation

Write the filled-in prompt template to a file, then call the wrapper (flags, JSON result, and exit codes are documented in `../SKILL.md`):

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << EOF
Refactor this code for simplicity:

## Target Code
File: src/services/llm_client.py
$(cat src/services/llm_client.py)

## Libraries Used
- openai: async client, retry with exponential backoff
- tenacity: use @retry decorator

## Refactoring Goals
- Reduce function length
- Add proper error handling
- Improve naming

[Principles and patterns as above...]
EOF
python3 .agents/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label refactor --sandbox danger-full-access
```

## Checklist

### Before Refactoring
- [ ] Tests exist and all pass
- [ ] Library constraints understood
- [ ] Impact scope identified

### During Refactoring
- [ ] Proceed in small steps
- [ ] Run tests at each step
- [ ] Verify library usage unchanged

### After Refactoring
- [ ] `bash .agents/skills/_shared/verify.sh` → exit `0` (`overall: "pass"`; exit `2` is a failed gate *or* no gate executed)
- [ ] `python3 .agents/skills/_shared/verify_delegation.py --forbid-outside {scope}` evidence read — `verdict` is always `needs-review`
- [ ] Behavior unchanged, and no test was deleted, skipped, or weakened to get there
- [ ] Code is simpler
- [ ] Type hints appropriate

This is a `danger-full-access` call, so the full protocol in
`codex-system/SKILL.md` → *Verify Before Trusting* applies, including the
re-delegate-once-then-halt rule.

## When to Use

- When code becomes hard to read/maintain
- When user says "refactor this", "simplify this", "clean up this code"
- Before adding new features to complex code
- When code review identifies complexity issues
