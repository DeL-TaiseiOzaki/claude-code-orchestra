# Code Review Task for Codex

When delegating code review to Codex, use this prompt template.

## Prompt Template

```
Review the following code changes for quality and correctness.

## Changes
{git diff output or code snippet}

## Libraries Used
{list of libraries}

## Library Constraints
{content from .claude/docs/libraries/ or "None documented"}

---

Review Checklist:

### 1. Simplicity
- Functions are short and single-responsibility
- Nesting is shallow (uses early return)
- No unnecessary complexity
- Names clearly express intent

### 2. Correct Library Usage
- Follows documented library constraints
- Uses library's recommended patterns
- No deprecated APIs
- Proper error handling

### 3. Type Safety
- All functions have type hints
- Optional/Union used appropriately
- No Any abuse

### 4. LLM/Agent Specific (if applicable)
- Token consumption considered
- Rate limit handling in place
- Timeout settings configured
- Prompts not hardcoded

### 5. Security
- No hardcoded API keys
- User input validated
- No sensitive info in logs

---

Provide feedback in this format:

### 🔴 Critical (Must Fix)
Security issues, bugs, library misuse

### 🟡 Warning (Should Fix)
Lack of simplicity, best practice violations

### 🟢 Suggestion (Consider)
Better approach proposals

### ✅ Good
Well-implemented points
```

## Example Invocation

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
Review this code change:

## Changes
$(git diff HEAD~1)

## Libraries Used
- httpx (async HTTP client)
- pydantic (validation)

## Library Constraints
- httpx: Always use async client, set timeout explicitly
- pydantic: Use Field() for validation, avoid root validators

[Review checklist as above...]
" 2>/dev/null
```

## When to Use

- After completing a feature implementation
- Before committing significant changes
- When user says "レビューして", "コードを確認して", "review this"
- Proactively after modifying critical code paths
