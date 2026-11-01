# Delegation-First Rule

**The main agent's default answer to "who does this work?" is *not me*.**

This rule is normative and tool-neutral. It governs *whether* to delegate and
*to whom*, including when work escalates to deep reasoning (Tier 2 `deep`);
`.claude/rules/tiers.md` defines the tiers; this file is the one that decides
that delegation happens at all.

## Default Posture

Delegate by default. Direct execution by the main agent is the **exception**,
and every exception must be justified by the Self-Handle List below. The main
agent's scarce resource is context and judgment, not tokens: work it performs
itself is work whose intermediate output permanently occupies the conversation.

## Self-Handle List (closed)

The main agent does the work itself **only** when the whole task is one of:

1. Answering from context already loaded this session — no new file reading.
2. A single-file edit of roughly 20 lines or fewer, in a file whose exact
   location and current contents are already known.
3. Running a named command or gate and reporting its result:
   `.claude/skills/_shared/verify.sh`, `.claude/skills/_shared/run_tests.py`,
   `scripts/check.sh`, `git status` / `diff` / `commit` / `push`.
4. Deterministic skill-bundled scripts a `SKILL.md` explicitly assigns to the
   lead (`workspace.py`, `validate_doc.py`, `update_design.py`,
   `append_state_block.py`, `checkpoint.py`, `collect_repo_state.py`, …).
5. User interaction: clarifying questions, approvals, routing decisions,
   integration of returned results, and the final report to the user, whose
   language and style follow `.claude/rules/language.md`.

The list is closed. "It would be faster to just do it myself" is not on it, and
neither is "the task is small enough that delegating feels like overhead."

## Mandatory Delegation Triggers

Delegate as soon as **any** of these holds — do not investigate first and then
decide:

- Three or more files must be read, **or** any file must be read whose contents
  are not already in this session's context.
- The expected output exceeds roughly 30 lines of code or prose.
- Locations are unknown and finding them needs a codebase-wide search sweep.
- Current external information must be verified (docs, APIs, releases).
- A command failed and its root cause is not already proven by evidence in hand.
- Design, step decomposition, trade-off evaluation, or complex implementation is
  involved.
- Two or more independent workstreams exist in the request.

## Route Selection

| Work | Route |
|------|-------|
| Routine, well-scoped implementation with clear acceptance criteria | `general-purpose-sonnet` |
| Ambiguous, cross-cutting, security / concurrency / data-integrity / migration-sensitive implementation | `general-purpose-opus` |
| Codebase-wide investigation, large-context analysis, external research | `general-purpose-opus` |
| Unknown root cause, failing tests or builds, unexpected behaviour | `debugger` |
| Architecture, planning, decomposition, complex algorithms, code review | `general-purpose-opus` (built-in `Plan` agent for a read-only plan) |
| Repeated failure, conflicting proposals, final review of a large change | `fable-advisor` (rare) |

Escalate rather than retry: a `general-purpose-sonnet` task that comes back
wrong or under-specified goes to `general-purpose-opus`, not back to
the same tier with the same prompt.

## Deep-Reasoning Triggers

**When in doubt, get a deep-reasoning pass.** One `general-purpose-opus`
consult costs one round trip; proceeding on an unverified assumption costs the
rework, the review, and the re-review. This resolves *uncertainty*; it does not
override the Self-Handle List or the over-delegation anti-pattern — a known
one-line edit stays a one-line edit.

Route to Tier 2 (`general-purpose-opus`, or `debugger` for failures) when
**any** of these apply:

- Design/architecture decisions are involved.
- The change spans 2+ files with behavior impact.
- The root cause is unclear (→ `debugger`).
- The user requests comparison/trade-off analysis.
- A step-by-step implementation plan is needed.
- You are about to introduce or reshape a seam other code depends on
  (new module or class, shared/core code, public interface).
- The change is security-sensitive: auth, input validation, crypto, permissions.
- The code is concurrent or asynchronous, where the failure modes are non-local.
- You are writing error handling, retry, or cache invalidation logic.
- Two or more fix attempts have already failed (→ consider `fable-advisor`).

Uncertainty is itself a trigger. "I think this is right" is a reason to
consult; "I know this is right, and here is the evidence" is a reason not to.

### Hook-Detected Triggers

Repository hooks surface these automatically; treat each hint as a prompt to
route, not as noise to dismiss. Confirm the command actually failed before
routing to `debugger`: the Bash hook only ever sees successful commands (the
runtime does not invoke it for a failing one) and matches on output text, so it
fires on read-only commands that merely display error-shaped output.

| Situation | Hook | Suggested route |
|-----------|------|-----------------|
| Prompt contains design / debug / review / uncertainty keywords | `agent-router.py` | `general-purpose-opus`, `debugger`, or `fable-advisor` |
| Write/Edit touching design-related or structural code | `check-design-before-write.py` | `general-purpose-opus` design review |
| Planning subagent finished | `check-plan-after-task.py` | `general-purpose-opus` plan validation |
| Test or build failure | `post-test-analysis.py` | `debugger` |
| Bash output matches error patterns | `error-to-debugger.py` | `debugger` |
| 2+ files or 50+ lines changed this session | `post-implementation-review.py` | `general-purpose-opus` code review |

A hint is advisory: the routing decision stays with the agent.

## Parallel by Default

When two or more delegable units are independent, launch them **in a single
message** so they run concurrently. Sequential delegation is reserved for
genuine data dependency — when the next prompt cannot be written without the
previous result. Typical parallel splits: investigation vs. external research,
implementation vs. test authoring, per-module ownership, review dimensions
(security / quality / test coverage).

## Subagent Prompt Contract

Every delegation carries all six, in the delegating message:

1. **Objective** — one sentence, the decision the result must enable.
2. **Scope** — what is in, what is explicitly out, what must not be touched.
3. **Inputs** — explicit file paths, plus the rules the subagent must load.
4. **Acceptance checks** — the exact commands that prove the work is done.
5. **Output shape** — the sections required in the reply.
6. **Context discipline** — "return only decision-relevant findings; write long
   output to `.claude/docs/…` or `.claude/logs/…` and return the path."

A subagent that had to guess any of the six was under-specified by the caller.

## Context Discipline

Long logs, large files, and full search dumps never enter the main agent's
context. Delegate the reading, have the subagent persist the durable artifact,
and take back the summary plus the path.

## Verification Stays With the Caller

Delegation transfers the work, never the accountability. Before reporting any
delegated result as done:

- run the acceptance checks from the prompt contract yourself;
- inspect the diff (`.claude/skills/_shared/verify_delegation.py`,
  `git diff --stat`) for out-of-scope edits, deletions, and placeholders;
- apply the guardrails in root `AGENTS.md` section "Guardrails
  (Completion Verification)" — weakened or skipped tests, swallowed exceptions,
  and hardcoded return values are rejections, not completions.

Report a delegated result as verified only when you ran the check that proves it.

## Anti-Patterns

- Investigating "just enough to understand it" and then delegating nothing —
  the investigation *was* the delegable work.
- Splitting one delegable task into a long chain of main-agent tool calls.
- Reading a file in the main agent so the subagent prompt can quote it; pass the
  path instead.
- Over-delegation: one subagent per trivial edit, or a delegation whose prompt
  takes longer to write than the edit would. Item 2 of the Self-Handle List
  exists for exactly these.
- Delegating a decision that is the user's to make.
