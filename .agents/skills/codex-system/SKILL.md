---
name: codex-system
description: |
  Codex CLI handles planning, design, and complex code implementation.
  Use for: architecture design, implementation planning, complex algorithms,
  debugging (root cause analysis), trade-off evaluation, code review.
  External research is NOT Codex's job — use general-purpose-opus instead.
  Explicit triggers: "plan", "design", "architecture", "think deeper",
  "analyze", "debug", "complex", "optimize".
metadata:
  short-description: Codex CLI — planning, design, and complex implementation
---

# Codex System — Planning, Design & Complex Implementation

**Codex CLI handles planning, design, and complex code implementation.**

> **Preflight (SSOT):** Update CLIs before each session — `claude update && npm install -g @openai/codex@latest`. Releases drift frequently (model names, flags, sandbox semantics). Other skills reference this line instead of repeating it.
> **Delegation policy (when to delegate)**: `.agents/rules/codex-delegation.md`

## Two Roles of Codex

### 1. Planning & Design

- Architecture design, module composition
- Implementation plan creation (step breakdown, dependency ordering)
- Trade-off evaluation, technology selection
- Code review (quality and correctness analysis)

### 2. Complex Implementation

- Complex algorithms, optimization
- Debugging with unknown root causes
- Advanced refactoring
- Multi-step implementation tasks

## When to Delegate

Delegation policy — when to consult, when NOT to, and trigger criteria — lives in `.agents/rules/codex-delegation.md` (SSOT). This skill covers *how* to consult.

## How to Consult

> Invoke Codex through the wrapper — `.agents/skills/_shared/codex_consult.py` — instead of calling `codex exec` directly. `codex exec` itself waits for stdin EOF and hangs indefinitely when stdin is left open (e.g. background shells); the wrapper always runs it with stdin closed, so callers never need `< /dev/null`. It also passes the prompt as a single argv element (no shell, so nested quotes in the prompt body never break it), captures stdout/stderr to timestamped files under `.agents/logs/codex/`, and reports one JSON result instead of silently discarding stderr.

```
python3 .agents/skills/_shared/codex_consult.py (--prompt-file PATH | --prompt-stdin) [--label L] [--sandbox {read-only,workspace-write,danger-full-access}] [--model M] [--timeout N] [--cwd DIR] [--skip-git-repo-check] [--config KEY=VALUE]
```

- Write the prompt body (Objective / Constraints / Relevant files / Acceptance checks / Output format) to a file and pass it via `--prompt-file`; use `--prompt-stdin` to pipe a short prompt instead. Any path works — the ad-hoc snippets below use `mktemp`, while skills write to `.agents/logs/codex/prompt-{label}.md` so the prompt sits next to the response the wrapper writes for it, which is what makes a disappointing answer diagnosable afterwards.
- `--sandbox` defaults to `read-only`. Pass `--sandbox danger-full-access` explicitly for implementation calls — see Sandbox Modes below.
- `--model` defaults to `$CODEX_MODEL`, else `gpt-5.6-sol`. `--label` is a `[a-z0-9-]+` slug used in the log filenames (default `consult`). `--timeout` defaults to 600 seconds. `--skip-git-repo-check` covers the non-Git working directory case — see `references/troubleshooting.md`.
- `--config KEY=VALUE` (repeatable) forwards a Codex config override, e.g. `--config model_reasoning_effort=low` for a cheap question. Keys naming a sandbox or approval setting are refused: `--sandbox` must stay the single visible statement of what Codex is allowed to touch.
- The wrapper prints exactly one JSON object: `{ok, exit_code, model, sandbox, write_access, timed_out, duration_sec, response_file, stderr_file, response_chars, response_head, error}`. `response_head` is only a ~400-char preview — read the file at `response_file` for the full response, and `stderr_file` (non-null whenever Codex wrote to stderr) when diagnosing a failure.
- Exit codes: `0` succeeded · `1` bad args or unreadable prompt file · `2` `codex` not on PATH · `3` codex exited non-zero or timed out.

### Subagent Pattern (Recommended)

```
Task tool parameters:
- subagent_type: "general-purpose-opus"
- run_in_background: true (optional)
- prompt: |
    Consult Codex about: {topic}

    Write the prompt body below to a file, then run the wrapper against it:

    Objective: {single-sentence objective}
    Constraints:
    - {constraint 1}
    Relevant files:
    - {file paths}
    Acceptance checks:
    - {commands}
    Output format:
    ## Analysis
    ## Recommendation
    ## Implementation Plan
    ## Risks
    ## Next Steps

    python3 .agents/skills/_shared/codex_consult.py --prompt-file {prompt_path} --label {short-slug} --sandbox read-only

    Parse the JSON result; when ok is true, read response_file for the full analysis.
    Return CONCISE summary (key recommendation + rationale).
```

### Direct Call (short questions, responses up to ~50 lines)

```bash
echo "Objective: {brief question}" | python3 .agents/skills/_shared/codex_consult.py --prompt-stdin --label quick-question --sandbox read-only
```

### Having Codex Implement Code

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << 'EOF'
Objective: Implement {detailed implementation task}
Constraints:
- Follow existing project conventions
- Keep diffs minimal
Relevant files:
- {file paths}
Acceptance checks:
- {commands}
Output format:
## Changes Made
## Validation
## Remaining Risks
EOF
python3 .agents/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label implement --sandbox danger-full-access
```

### Sandbox Modes

| Mode | Sandbox | Use Case |
|------|---------|----------|
| Analysis | `read-only` | Design review, debugging, trade-off analysis |
| Implementation | `danger-full-access` | Implementation, fixes, refactoring |

The wrapper's own default is `read-only`, so pass `--sandbox danger-full-access` explicitly for every implementation call. This is intentionally stricter than a bare `codex exec` invocation: `codex exec` alone would inherit the project's `.codex/config.toml` default of `danger-full-access` when no `--sandbox` flag is given, but the wrapper always sends an explicit `--sandbox` value and never lets that config default apply silently.

## Task Templates

### Implementation Planning

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << 'EOF'
Create an implementation plan for: {feature}

Context: {relevant architecture/code}

Provide:
1. Step-by-step plan with dependencies
2. Files to create/modify
3. Key design decisions
4. Risks and mitigations
EOF
python3 .agents/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label plan --sandbox read-only
```

### Design Review

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << 'EOF'
Review this design approach for: {feature}

Context: {relevant code or architecture}

Evaluate:
1. Is this approach sound?
2. Alternative approaches?
3. Potential issues?
4. Recommendations?
EOF
python3 .agents/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label design-review --sandbox read-only
```

### Debug Analysis

```bash
prompt_file="$(mktemp)"
cat > "${prompt_file}" << 'EOF'
Debug this issue:

Error: {error message}
Code: {relevant code}
Context: {what was happening}

Analyze root cause and suggest fixes.
EOF
python3 .agents/skills/_shared/codex_consult.py --prompt-file "${prompt_file}" --label debug --sandbox read-only
```

## Language Protocol

See `.agents/rules/language.md` (SSOT): ask Codex in English, receive in English, report to the user per that rule.

## Codex Plugin Commands (codex-plugin-cc)

When the `openai/codex-plugin-cc` plugin is installed, these slash commands are available:

> Plugin source: https://github.com/openai/codex-plugin-cc

### Code Review

```bash
/codex:review                    # Review current uncommitted changes
/codex:review --base main        # Review branch diff against main
/codex:review --background       # Run review in background
/codex:review --wait             # Synchronous: block until review finishes
```

### Adversarial Review

```bash
/codex:adversarial-review                           # Challenge design decisions
/codex:adversarial-review --base main               # Branch-level adversarial review
/codex:adversarial-review --background look for race conditions
```

### Task Delegation (Rescue)

```bash
/codex:rescue investigate why the tests started failing
/codex:rescue fix the failing test with the smallest safe patch
/codex:rescue --resume apply the top fix from the last run
/codex:rescue --model gpt-5.5-mini --effort medium investigate flaky test
/codex:rescue --background investigate the regression
```

### Job Management

```bash
/codex:status                    # Check progress of background jobs
/codex:result                    # Show finished job output
/codex:cancel                    # Cancel active background job
```

### Setup

```bash
/codex:setup                     # Check if Codex is installed and authenticated
/codex:setup --enable-review-gate   # Enable auto-review gate (use with caution)
/codex:setup --disable-review-gate  # Disable review gate
```

### When to Use Plugin vs Direct CLI

| Scenario | Use |
|----------|-----|
| Pre-ship code review | `/codex:review` |
| Challenge design | `/codex:adversarial-review` |
| Delegate investigation/fix | `/codex:rescue` |
| Background work + tracking | Plugin `--background` |
| Ad-hoc design question | `codex_consult.py` (direct) |
| Unrestricted implementation | `codex_consult.py --sandbox danger-full-access` |
| Subagent delegation | `codex_consult.py` via general-purpose-opus |

## Why Codex?

- **Deep reasoning**: Complex analysis and problem-solving
- **Planning expertise**: Architecture and implementation strategies
- **Code mastery**: Complex algorithms, optimization, debugging

## References

Detailed templates and patterns in `references/`:

- [agent-prompts.md](references/agent-prompts.md) — Prompt templates for specialized review agents (Architect, etc.)
- [code-review-task.md](references/code-review-task.md) — Prompt template for delegating code review to Codex
- [delegation-patterns.md](references/delegation-patterns.md) — Delegation decision flowchart and detailed patterns
- [refactoring-task.md](references/refactoring-task.md) — Prompt template for delegating refactoring to Codex
- [troubleshooting.md](references/troubleshooting.md) — Codex CLI troubleshooting (installation, auth, common errors)
