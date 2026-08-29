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
| Antigravity | `python3 .agents/skills/_shared/cli_consult.py --cli antigravity --prompt-file <path>` | Wraps `agy -p`; text output is captured verbatim and the exit code is the success signal. Its headless mode auto-approves every tool call, so it cannot be confined from the caller and refuses `--read-only` |

Both wrappers share one contract: prompt via `--prompt-file`/`--prompt-stdin`
as a single argv element (no shell), stdin closed, a timeout, stdout and stderr
captured under `.agents/logs/<cli>/`, and exactly one JSON object on stdout
(`ok`, `exit_code`, `response_file`, `response_head`, `error`, …) with exit
codes `0` ok / `1` bad args / `2` CLI not on PATH / `3` failed or timed out.

Rules:

- **Access is unrestricted by default, stated explicitly, and restricted by
  opt-in.** The wrapper default matches what the callee's own configuration
  already grants — `.codex/config.toml` sets `sandbox_mode =
  "danger-full-access"` — so the access an agent has no longer depends on
  which of the two paths reached it. A wrapper that substituted something
  stricter than the CLI a caller would have run by hand made the two disagree,
  and the disagreement was invisible from the call site.

  The flag is still always sent explicitly, so what was granted is readable in
  the command rather than inherited from a config file, and it can never be
  widened *or narrowed* by a passthrough argument:

  | Callee | Default (unrestricted) | Read-only opt-in |
  |--------|------------------------|------------------|
  | Claude Code | `--permission-mode bypassPermissions` | `cli_consult.py --read-only` → `--permission-mode plan` |
  | Codex | `codex_consult.py` default `--sandbox danger-full-access` | `--sandbox read-only` (or `workspace-write` for a middle ground) |
  | Antigravity | headless auto-approves every tool call; nothing to pass | **not supported** — `--read-only` is refused rather than accepted and ignored |

  Planning, design, and review consultations should still pass the read-only
  opt-in where the callee supports it. Unrestricted is the default because it
  is the truth about the environment, not because every call needs it.

- **Every run records what it edited.** Because the default is unrestricted,
  the question that matters is no longer "what was it allowed to touch?" but
  "what did it touch?". Both wrappers bracket the call with
  `.agents/skills/_shared/edit_provenance.py` and report an `edits` object
  naming the files the callee created, changed, or deleted — including files
  it committed — alongside `caller` and `label`. Pass `--caller <your agent
  name>` (or export `ORCHESTRA_CALLER`) so the log answers *which subagent*
  made a change, not only *which CLI*. Work already uncommitted in the tree
  when the call starts is excluded, so it is never misattributed to the
  callee.

- Pin the model with `--model` when the tier matters (Codex reads `CODEX_MODEL`;
  omitting `--model` for a peer CLI keeps that CLI's own default).
- Bound the call: keep the wrapper's timeout, and cap agentic turns for
  long-running peers where the callee supports it (e.g.
  `--cli-arg --max-turns --cli-arg 8` for Claude Code). With no sandbox in the
  way, the turn cap and the timeout are what bound a run that goes wrong.
- The caller MUST independently verify the callee's result per the Guardrails
  below — a delegated CLI is never trusted on its self-report. This applies in
  both directions: a Codex main agent verifies a `claude -p` result exactly as a
  Claude main agent verifies a `codex exec` result.
- Every wrapper call is appended to `.agents/logs/cli-tools.jsonl` by the
  `log-cli-tools.py` hook, so any runtime can read what was delegated, what
  came back, and which files it changed (`caller`, `label`, `access`, `edits`).
  A direct `codex exec` is logged too, but with all four of those fields
  `null` — the missing provenance is the reason the wrapper is mandated.
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
`approval_policy` is `"never"` and the wrappers default to unrestricted
access, verification is the *only* control on a delegated run — nothing stops
the edit, so everything depends on catching it afterwards. The `edits` object
in the wrapper's own payload tells you which files to look at; the guardrails
below tell you what to look for in them.

### (a) Independent Verification of Completion Reports

The caller MUST run the acceptance checks from the original prompt AND inspect
the delegated run's diff for:
- Unapproved deletions (files or significant code blocks removed without
  justification in the prompt).
- Stub or placeholder completions (e.g. `pass`, `TODO`, `NotImplementedError`
  left where real logic was requested).
- Out-of-scope changes (files modified that were not mentioned in the task).

Collecting that evidence is mechanical, so it is scripted — reading these three
paragraphs and doing it by hand is exactly what gets skipped when the run looks
successful:

```bash
python3 .agents/skills/_shared/verify_delegation.py \
  --base HEAD --expect-files src/a.py --forbid-outside src --forbid-outside tests \
  --label implement
```

`--base` is the ref the delegated work started from (default `HEAD`, i.e.
uncommitted work); `--expect-files PATH` (repeatable) names a path the task was
supposed to change; `--forbid-outside PATH` (repeatable) restricts the change to
those paths. The full diff — uncommitted and untracked work included — is written
under `.agents/logs/delegation/` and named by `diff_file`.

The payload reports `deletions`, `placeholders`, `weakened_tests`,
`out_of_scope_files` and `missing_expected_files`, plus `changed_files`,
`untracked_files`, `unreadable_files`, `scope_empty`, `findings_total`,
`actionable_total` and `expectations_violated`. Exit codes: `0` nothing
actionable and no violated expectation · `1` bad arguments or an unresolvable
`--base` · `2` an actionable finding (`placeholders`, `weakened_tests`) or a
violated expectation · `3` git failed or the diff could not be written.

**Deletions do not drive the exit code.** Any removed non-blank line counts as
one, so a real diff almost always has some; letting them decide the exit status
made `2` the routine outcome, and a check that fails routinely teaches callers
that its failure is noise — a worse state than the unverified delegation it
replaced. Deletions are reported in full in every payload and are covered by
`verdict`, not by the exit code.

**Exit `0` is not an accept.** `verdict` is `needs-review` on every path and
there is deliberately no `clean` branch: the pattern list is heuristic, a
legitimate test deletion exists, and only the agent that wrote the prompt knows
what the task authorised. `ok` reports whether *collection* succeeded. The
`not_automated` field names what no heuristic detects — hard-coded return values
substituted for real logic (b3 below) — instead of pretending full coverage. Read
the diff and decide.

### (b) Cheating Detection

Reject completion if any of the following are detected:
- b1: Tests were deleted, skipped (`@pytest.mark.skip`), or weakened (assertions
  removed or loosened) to make the suite pass. → `weakened_tests`
- b2: Exceptions silently swallowed (bare `except: pass` or equivalent) to hide
  failures. → `placeholders`
- b3: Hardcoded return values substituted for real implementation logic. → not
  detected by any script; the reviewer's own judgment on the diff, which is why
  the script never accepts.

### (c) False Completion Response Protocol

When verification fails:
1. Report the specific failure(s) with evidence.
2. Re-delegate ONCE with the original prompt plus failure context appended.
3. If the second attempt also fails verification, halt and require explicit
   user approval before proceeding.
