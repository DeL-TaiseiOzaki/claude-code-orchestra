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

Delegation policy — when to consult, when NOT to, and trigger criteria — lives in `.agents/rules/codex-delegation.md` (SSOT). This skill covers *how* to consult. The other half of "how" is **how to verify what came back**: `.agents/rules/cli-execution.md` → *Guardrails (Completion Verification)* is mandatory for every write-access call, and [Verify Before Trusting](#verify-before-trusting) below is its executable form. A delegated CLI is never trusted on its self-report.

## How to Consult

> Invoke Codex through the wrapper — `.agents/skills/_shared/codex_consult.py` — instead of calling `codex exec` directly. `codex exec` itself waits for stdin EOF and hangs indefinitely when stdin is left open (e.g. background shells); the wrapper always runs it with stdin closed, so callers never need `< /dev/null`. It also passes the prompt as a single argv element (no shell, so nested quotes in the prompt body never break it), captures stdout/stderr to timestamped files under `.agents/logs/codex/`, and reports one JSON result instead of silently discarding stderr.

```
python3 .agents/skills/_shared/codex_consult.py (--prompt-file PATH | --prompt-stdin) [--label L] [--caller AGENT] [--sandbox {read-only,workspace-write,danger-full-access}] [--model M] [--timeout N] [--cwd DIR] [--project-root DIR] [--skip-git-repo-check] [--config KEY=VALUE]
```

> **Consulting a peer CLI instead of Codex.** Claude Code and Antigravity go through `.agents/skills/_shared/cli_consult.py --cli {claude,antigravity} --prompt-file PATH`, unrestricted unless `--read-only` — which Antigravity refuses, because its headless mode auto-approves every tool call and the restriction cannot be enforced from the caller (`--resume SESSION` is Claude-only; `--cli-arg` forwards a native flag; default timeout 900 s; same four exit codes as below). Never shell out to a CLI directly — the wrapper-only rule and the per-callee permission mapping live in `.agents/rules/cli-execution.md`. Codex's sandbox and `--config` semantics stay here because they are Codex-specific; everything cross-CLI is in that rule file.

- Write the prompt body (Objective / Constraints / Relevant files / Acceptance checks / Output format) to a file and pass it via `--prompt-file`; use `--prompt-stdin` to pipe a short prompt instead. Any path works — the ad-hoc snippets below use `mktemp`, while skills write to `.agents/logs/codex/prompt-{label}.md` so the prompt sits next to the response the wrapper writes for it, which is what makes a disappointing answer diagnosable afterwards.
- `--sandbox` defaults to `danger-full-access`, matching `.codex/config.toml`. Pass `--sandbox read-only` explicitly for planning and review calls — see Sandbox Modes below.
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

    Parse the JSON result. ok: true means only that codex exec exited 0 — it is
    not a completion report. Read response_file for the full analysis, and judge
    it yourself: state which claims you verified and which you could not.
    Return CONCISE summary (key recommendation + rationale + what is unverified).
```

For a **write-access** subagent call, add the Verify Before Trusting steps to the delegated prompt as well, and require the subagent to return the `verify.sh` and `verify_delegation.py` verdicts. A subagent that summarises Codex's self-report without them has not verified anything, and its summary must not be treated as a completion.

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

The call is **not** finished here. Continue with the next section.

### Verify Before Trusting

Mandatory after every `workspace-write` / `danger-full-access` call (Codex or a peer CLI), per `.agents/rules/cli-execution.md` → *Guardrails*. `ok: true` from the wrapper means only that `codex exec` exited `0`; it says nothing about whether the change is correct, complete, or honest.

**1. Run the acceptance checks from your own prompt**, plus the project gates:

```bash
bash .agents/skills/_shared/verify.sh
```

Exit `0` = `overall: "pass"`. Exit **`2`** = a gate failed, **or** no gate ran at all (`overall: "no_gates"`) — a delegated code change must never be accepted with zero checks executed. Exit `1` bad arguments, `3` the log file could not be written. Read `log_file` for the full output.

**2. Collect the Guardrail evidence from the diff**, naming the scope the prompt actually authorised:

```bash
python3 .agents/skills/_shared/verify_delegation.py --base HEAD \
  --expect-files {file the task was supposed to change} \
  --forbid-outside {directory the task was scoped to}
```

It reports `deletions`, `placeholders`, `weakened_tests`, `out_of_scope_files`, `missing_expected_files`, `scope_empty`, and the captured diff at `diff_file`. Exit `0` = nothing actionable and no violated expectation — deletions alone land here, reported but not actionable on their own, and exit `0` is still not an accept. Exit **`2`** = an actionable finding (`placeholders`, `weakened_tests`) or a violated expectation (`out_of_scope_files`, `missing_expected_files`, `scope_empty`). Use `--base <pre-delegation ref>` when Codex committed its work; the default `HEAD` covers the usual uncommitted case.

**3. Read the diff and decide.** `verdict` is always `needs-review` and there is no verdict that means "accepted" — deliberately. The pattern list is heuristic (a legitimate test deletion exists, and a `TODO` in a docstring is not a stub), and only you know what the prompt authorised. Reject the completion when the diff shows any of:

- tests deleted, skipped (`@pytest.mark.skip`), or weakened (assertions removed or loosened) to make the suite pass;
- exceptions silently swallowed (`except: pass` or equivalent) to hide failures;
- hard-coded return values substituted for real logic — the one Guardrail item no script screens for, so it is listed under `not_automated` and only your read of the diff catches it;
- stub or placeholder completions where real logic was requested;
- files changed that the task never mentioned, or unapproved deletions.

**4. On failure, follow the re-delegate-once protocol** (`cli-execution.md` (c)): report the specific failures with evidence, re-delegate **once** with the original prompt plus the failure context appended, and if the second attempt also fails verification, **halt** and require explicit user approval before proceeding. Never patch over a failed delegation silently.

### Sandbox Modes

| Mode | Sandbox | Use Case |
|------|---------|----------|
| Analysis | `read-only` (explicit opt-in) | Design review, debugging, trade-off analysis |
| Implementation | `danger-full-access` (default) | Implementation, fixes, refactoring |

The wrapper's own default is `danger-full-access`, the same value `.codex/config.toml` sets, so an implementation call needs no flag and an analysis call must pass `--sandbox read-only` explicitly. The wrapper used to default to `read-only` — deliberately stricter than a bare `codex exec` — which meant the access Codex had depended on whether it was reached through the wrapper or directly, and neither call site said so. Aligning the two removes that divergence; what has *not* changed is that the wrapper always sends `--sandbox` explicitly, so the granted access is readable in the command rather than inherited from a config file, and `--config` keys naming a sandbox or approval setting stay refused.

Because the default is unrestricted, every call is bracketed by an edit snapshot and the JSON result carries an `edits` object naming the files Codex created, changed, or deleted, plus `caller` and `label`. Pass `--caller <your agent name>` so `.agents/logs/cli-tools.jsonl` records *which subagent* asked for a change, not only which CLI made it.

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

**Availability precondition:** run `/codex:setup` first. Nothing in this repository verifies the plugin is installed, so if the commands are absent, use `codex_consult.py` instead of assuming a route exists. **Audit-trail caveat:** plugin commands run Codex *outside* the wrapper, so they produce no `.agents/logs/codex/` response or stderr capture and no `.agents/logs/cli-tools.jsonl` entry (`log-cli-tools.py` keys on the wrapper filenames). Prefer the wrapper wherever both work, and note the gap when you use a plugin route for work that needs a record.

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
| Unrestricted implementation | `codex_consult.py` (the default) + [Verify Before Trusting](#verify-before-trusting) |
| Subagent delegation | `codex_consult.py` via general-purpose-opus |
| Consulting Claude Code or Antigravity | `cli_consult.py --cli {claude,antigravity}` |

Plugin routes (the first four rows) leave no wrapper log, no `cli-tools.jsonl` entry, and no record of which files they changed; the `codex_consult.py` routes leave all three. Whichever route made the change, an unrestricted run is verified the same way.

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

Also `.agents/docs/CODEX_HANDOFF_PLAYBOOK.md` — the handoff templates `.agents/rules/codex-delegation.md` points at, kept there because they are shared with non-Codex handoffs.
