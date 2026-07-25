# AGENTS.md -- CLI Executor Extension

Root `AGENTS.md` is the shared orchestration contract. Read it and
`.agents/rules/tiers.md` first. This file adds only the response, handoff, and
verification rules required of CLI executors such as Codex, Antigravity, and
Grok.

## Required Response Structure

Always respond in the following order.

```markdown
## TL;DR
- Conclusion in 3 lines or fewer

## Analysis
- Problem decomposition, assumptions, constraints

## Plan
1. Implementation step
2. Implementation step

## Patch Strategy
- Which files to change and what to change in each

## Validation
- Tests/verification commands to run

## Risks
- Impact of failure and mitigation strategies
```

## Handoff Rules

- Return procedures that are directly executable as-is
- Compress key points needed for decision-making, not lengthy raw data
- Separate unverified items as TODOs
- State assumptions before implementing ambiguous requirements
- Prefer incremental, minimal diffs for large changes
- Include a migration plan whenever compatibility may break

## Cross-CLI Subagent Invocation

Any CLI agent can drive any other as a subagent through its non-interactive
(headless) mode. All runtimes read the shared `AGENTS.md` contract and the
canonical `.agents/` capabilities, so a delegated call inherits the same
mission, routing, and guardrails regardless of which CLI runs it.

**Always call a peer CLI through its shared wrapper — never shell out to the
CLI directly.** A hand-written invocation reintroduces four failure modes the
wrappers exist to remove: an open stdin blocks on EOF (observed as multi-minute
hangs in background shells), redirected-away stderr makes a crashed CLI look
like an empty answer, a prompt containing quotes breaks the shell command, and
a stalled call has no deadline.

| Callee | Invocation | Notes |
|--------|-----------|-------|
| Claude Code | `python3 .agents/skills/_shared/cli_consult.py --cli claude --prompt-file <path>` | Wraps `claude -p --output-format json`; returns the envelope's `result` as the response and its `session_id` for chaining via `--resume` |
| Codex | `python3 .agents/skills/_shared/codex_consult.py --prompt-file <path>` | Wraps `codex exec`; sandbox modes and `--config` overrides are validated there. Flags and exit codes: `.agents/skills/codex-system/SKILL.md` |
| Gemini CLI | `python3 .agents/skills/_shared/cli_consult.py --cli gemini --prompt-file <path>` | Wraps `gemini -p`; Gemini's own `--output-format json` has known gaps (google-gemini/gemini-cli #9009, #9281), so text output is captured verbatim and the exit code is the success signal |

Both wrappers share one contract: prompt via `--prompt-file`/`--prompt-stdin`
as a single argv element (no shell), stdin closed, a timeout, stdout and stderr
captured under `.agents/logs/<cli>/`, and exactly one JSON object on stdout
(`ok`, `exit_code`, `response_file`, `response_head`, `error`, …) with exit
codes `0` ok / `1` bad args / `2` CLI not on PATH / `3` failed or timed out.

Rules:

- **Access is read-only by default and granted explicitly.** Each wrapper maps
  one flag onto the callee's native permission surface, so the granted access
  is always visible in the call and can never be widened by a passthrough
  argument:

  | Callee | Read-only (default) | Write access |
  |--------|--------------------|--------------|
  | Claude Code | `--permission-mode plan` | `cli_consult.py --write-access` → `--permission-mode acceptEdits` |
  | Codex | `codex_consult.py --sandbox read-only` | `--sandbox workspace-write` / `danger-full-access` |
  | Gemini CLI | `--approval-mode default` (a tool call needing confirmation errors out) | `cli_consult.py --write-access` → `--approval-mode yolo` |

- Pin the model with `--model` when the tier matters (Codex reads `CODEX_MODEL`;
  omitting `--model` for a peer CLI keeps that CLI's own default).
- Bound the call: keep the wrapper's timeout, and cap agentic turns for
  long-running peers where the callee supports it (e.g.
  `--cli-arg --max-turns --cli-arg 8` for Claude Code).
- The caller MUST independently verify the callee's result per the Guardrails
  below — a delegated CLI is never trusted on its self-report. This applies in
  both directions: a Codex main agent verifies a `claude -p` result exactly as a
  Claude main agent verifies a `codex exec` result.
- Every wrapper call is appended to `.agents/logs/cli-tools.jsonl` by the
  `log-cli-tools.py` hook, so any runtime can read what was delegated and what
  came back.
- Prefer the project's own delegation skills (`codex-system`,
  `general-purpose-opus`) over an ad-hoc wrapper call when one already covers
  the task.

## Internal Context References

Refer to the following as needed:

- `.agents/docs/DESIGN.md`
- `.agents/docs/research/`
- `.agents/rules/`
- `.agents/skills/`
- `.agents/logs/cli-tools.jsonl`

## Guardrails (Completion Verification)

Applies to any long-duration executor (Tier 2 `sol` and above). Because
`approval_policy` is `"never"`, verification replaces approval.

### (a) Independent Verification of Completion Reports

The caller MUST run the acceptance checks from the original prompt AND inspect
`git diff` for:
- Unapproved deletions (files or significant code blocks removed without
  justification in the prompt).
- Stub or placeholder completions (e.g. `pass`, `TODO`, `NotImplementedError`
  left where real logic was requested).
- Out-of-scope changes (files modified that were not mentioned in the task).

### (b) Cheating Detection

Reject completion if any of the following are detected:
- Tests were deleted, skipped (`@pytest.mark.skip`), or weakened (assertions
  removed or loosened) to make the suite pass.
- Exceptions silently swallowed (bare `except: pass` or equivalent) to hide
  failures.
- Hardcoded return values substituted for real implementation logic.

### (c) False Completion Response Protocol

When verification fails:
1. Report the specific failure(s) with evidence.
2. Re-delegate ONCE with the original prompt plus failure context appended.
3. If the second attempt also fails verification, halt and require explicit
   user approval before proceeding.
