# _shared/ — Bundled Runtime for Skills

`_shared/` is **NOT a skill** — it is a bundled runtime library of deterministic
helpers. Skills must never invoke other skills, but **MAY** depend on `_shared/`
scripts and format documents.

## Automation Boundary

Skills are markdown because most of what they describe is judgment. Scripts
exist because some of what they describe is not. The split is deliberate:

| Belongs in a script | Stays in `SKILL.md` |
|---------------------|---------------------|
| Deriving names, slugs, and artifact paths | Deciding the mode, route, or priority |
| Reading, writing, and validating document structure | Writing briefs, reports, and prose |
| Invoking external processes | Composing the prompt *content* |
| Collecting inventories and running quality gates | Interpreting the results |

The test: **if a step has exactly one correct output for a given input, it is a
script.** Everything else stays markdown, where an agent can reason about it.

Scripting a judgment step makes the skill rigid and wrong in new situations.
Leaving a mechanical step in prose makes it silently inconsistent — two phases
derive different slugs, a required section is quietly omitted, an error is
swallowed. Both failure modes are worse than the split.

## Contents

| File | Description |
|------|-------------|
| `work-log-format.md` | Canonical work-log template for Agent Teams teammates (format doc, not a script). |
| `workspace.py` | Resolve, create, and verify a skill's slug, team name, and artifact paths. Single source of truth for cross-phase naming. |
| `codex_consult.py` | Invoke the Codex CLI safely: prompt from `--prompt-file`, stdin, or the label's default path; stdin closed; prompt, stdout, and stderr captured to `.claude/logs/codex/` under a collision-free stem; `--sandbox` defaults to the project's own `danger-full-access` and is always sent explicitly; full diagnostics as JSON. |
| `cli_consult.py` | Invoke a peer CLI agent (Claude Code, Antigravity) as a subagent under the same contract, unrestricted unless `--read-only`. Cross-CLI rules: root `AGENTS.md`. |
| `edit_provenance.py` | Snapshot the repository's dirty set before a delegated run and diff it afterwards, so the consult wrappers can report the files the callee actually created, changed, or deleted — committed work included, pre-existing dirt excluded. |
| `validate_doc.py` | Validate a markdown document (work log, lib doc, plan, brief, diagnosis, guide, checkpoint summary, PROGRESS, spike/bug report) against a named `## ` section contract; `--expect-files N` makes "nobody wrote one" a failure. |
| `append_state_block.py` | Typed writers for `.claude/STATE.md`: `--type feature\|bug-fix\|project` appends a `## Current …` work block, `--type repository-identity` replaces the `## Repository Identity` body `/init` owns. Writer Safety Contract. |
| `update_design.py` | Typed writers for `.claude/docs/DESIGN.md`: rows for Key Decisions, requirements, NFRs, tech choices, and agent roles, plus named section appends. Idempotent; `--require-change` makes a `no-op` exit `2`. Writer Safety Contract. |
| `gather_diff.py` | Collect the review scope of a change — changed files, the full patch, and a lint snapshot of the changed Python files. Includes uncommitted work; an empty scope is `scope_empty: true` + exit `2`, never a clean review. |
| `run_tests.py` | Run one test target and compare the observed outcome against `--expect fail\|pass`, so the TDD Red/Green invariant is an exit code. Distinguishes `failed` from `collection_error` and `no_tests_collected`. |
| `verify_delegation.py` | Collect Guardrail evidence about a delegated run's diff (deletions, placeholders, weakened tests, out-of-scope files). Reports; never accepts — `verdict` is always `needs-review`. |
| `verify.sh` | Run the configured quality gates (ruff check, ruff format, ty, pytest) and report one JSON summary. A failed gate is exit `2`; "no gate could run" is a failure unless `--allow-no-gates`. |

## Shared Script Contract

Every script in `_shared/` follows these conventions, and skill-bundled helpers
follow them too, so callers can handle all of them identically:

- **Exactly one JSON object on stdout** — on every error path without
  exception, including argument errors, which are reported as JSON rather than
  as `argparse` usage text on stderr; and on the success path of every helper
  whose result the caller consumes. Long output goes to a file whose path is
  reported inside that JSON. (`checkpoint.py` is the one helper whose success
  path prints a human-readable report instead: it generates files, and the
  report says what it wrote.)
- **`--project-root DIR`** on every bundled helper, **shell included**, to
  relocate the repository root so the script can be exercised against a fixture
  directory without touching the real project. Every path the script touches
  honours it; no module-level constant may bake in a directory. There is no
  `.sh` carve-out: the old exemption said `gather_diff.sh` and `repro.sh`
  "resolve the root from their own location", but `verify.sh` was shell too and
  accepted the flag, so the carve-out was an omission dressed as a rationale —
  and because no test could invoke those two against a fixture, three real
  defects (invalid JSON on a quoted argument, an empty review scope reported as
  a clean review, and a parsed-then-ignored `--bisect-good`) stayed invisible.
  Both are now `.py`; `verify.sh` is the only remaining shell helper and answers
  `--help` with exit `0` like the rest.
- **`"ok"` on every payload, success included.** Every JSON object on stdout
  carries a top-level boolean `ok`. Without it a caller that branches on
  `payload.ok` reads `None` from a *successful* run and reports success as
  failure — the most likely caller bug in the runtime, and one that five
  scripts used to invite by reporting only `overall`, `issues`, or a bare
  result field.
- **Errors are never swallowed.** A failure surfaces as a JSON field *and* a
  non-zero exit code. Silence always means success.
- **Every filesystem write is guarded.** `mkdir`, `write_text`, and
  `os.replace` are wrapped; an `OSError` becomes `{"ok": false, "error": …}`
  with exit `3`, never a traceback. An unwritable log directory used to print a
  `NotADirectoryError` with *no JSON at all* and exit `1` — which this table
  reads as "bad arguments", sending the caller to fix its own command line.
- **Verified success path.** A script that writes a document or a captured
  response re-reads it and checks it before reporting `ok: true`, and the
  payload says so (`response_verified`, or the named validation the writers
  run). Otherwise a structurally broken document is reported as a success and
  discovered a phase later, after other artifacts were derived from it —
  "Codex answered" and "we saved the answer" are two different claims.
- **Re-run safety.** Running a script twice with the same input must not
  duplicate content; the payload reports `result: applied | no-op | preview`,
  and a log-file name that already exists is never overwritten. Without this,
  re-running a phase after an interruption silently doubles user-owned content
  or destroys a parallel run's evidence.
- **`--now ISO8601`** on every script whose output embeds a date or a
  timestamp, defaulting to the real clock, parsed with
  `datetime.fromisoformat`, unparseable → exit `1`. The clock is read **once
  per run**, so a filename cannot disagree with the header inside it. Without an
  injected clock, timestamped output is untestable and time-derived dedup keys
  cannot be exercised at all. One documented exception:
  `update-lib-docs/lib_inventory.py` keeps `--today YYYY-MM-DD`, because it
  stamps nothing — the date is only compared against a doc's `Last Updated`
  for staleness — and that strict format is pinned by its tests. The exception
  is written down here on purpose; an undocumented carve-out is what the
  `--project-root` clause above is about.
- **`"artifacts": [...]`** — repo-relative POSIX paths of every file the run
  created or modified, `[]` when none. Additive: the domain-specific field
  (`response_file`, `preview_file`, `diff_file`, `log_file`, …) stays as it is
  and keeps its current absolute-or-relative form; `artifacts` is the one
  uniform answer to "which file did you just change?", which on the `--apply`
  path used to be unanswerable from the JSON. A caller cannot log, diff, or
  roll back what it cannot name.
- **Shared exit-code vocabulary**:

  | Code | Meaning |
  |------|---------|
  | `0` | ok / preview / no-op |
  | `1` | bad arguments or unreadable input |
  | `2` | contract violation — missing artifact, invalid structure, missing required section, a failed quality gate, or a violated `--expect-*` expectation |
  | `3` | external failure — subprocess failed or timed out, write failure, concurrent modification |

- **Graceful degradation**: an absent optional path is reported as `null` or an
  empty list and stays exit `0`. Only genuinely broken states are errors.
- **Empty is not success.** "Nothing found" is either an explicit expectation
  failure (`--expect-files`, `--expect fail|pass`, `scope_empty`) or a distinctly
  named state in the payload. It is never a silent exit `0` that reads as "all
  clear" — that single pattern produced a review of nothing reported as a clean
  review, and a validator that passed because no file existed to validate.
- **Standard library only.** No third-party imports, so the scripts run wherever
  `python3` does. A sibling module inside `_shared/` is not a third-party
  dependency and is allowed: Python puts a script's own directory on
  `sys.path`, so the portability this clause protects is unaffected, and the
  alternative — copying a helper into both consult wrappers — is exactly the
  drift the bundled runtime exists to prevent. The sibling must still satisfy
  every other clause here, so it cannot become a back door for an unchecked
  helper.

### Carve-outs

Exactly two clauses have a documented exception:

| Clause | Exception | Why |
|--------|-----------|-----|
| Exactly one JSON object on stdout | `checkpointing/checkpoint.py`'s success path prints a human-readable report | It generates files, and the report says what it wrote. `--json` gives callers the machine-readable form. |
| Injectable clock `--now ISO8601` | `update-lib-docs/lib_inventory.py` keeps `--today YYYY-MM-DD` | It stamps nothing; the date is an *input* it compares against, and the strict format is pinned by its tests. |

**A third carve-out requires a `TEMPLATE_DESIGN_LOG.md` entry**, in the same
commit, naming the clause, the script, and the failure mode the exception does
not reintroduce. This is not ceremony: the `--project-root` exemption for the two
shell scripts was justified in this file by a rationale that was simply untrue of
a sibling shell script, and that undocumented-in-substance carve-out is what kept
three real defects — invalid JSON output, a `bash -c` with no timeout, and a
documented-but-dead flag — untestable and therefore invisible for as long as it
stood. An exception argued in a commit message is forgotten; one argued in the
design log is reviewable.

### What is machine-enforced

`tests/test_shared_script_contract.py` discovers every `.py` and `.sh` helper
under `.claude/skills/` by `rglob` and enforces: the module docstring's `Usage:`
and `Exit codes:`, `--help` exit `0` documenting `--project-root`, one JSON
object with `ok: false` and exit `1` on an unknown flag, one JSON object with a
boolean `ok` that agrees with the exit code on a real invocation, no traceback,
documented exit codes inside the shared vocabulary, `artifacts` present in any
script that creates files, `--now` on any script that reads the clock (exactly
one reading), stdlib-only imports, no bare `except:` / `shell=True` /
`2>/dev/null`, and `codex exec` only through the wrapper. Every script must
also register a success invocation there or name the test file that covers its
success path.

Three clauses stay prose because a generic test of them would pass vacuously:
the *verified success path*, *re-run safety*, and *graceful degradation* are
asserted in each script's own test file, where the input that makes them
meaningful exists. The rule for adding a clause here is that it must be able to
fail: a field named like a guarantee that never carries one is worse than no
field at all.

## Writer Safety Contract

`append_state_block.py`, `update_design.py`, `checkpointing/checkpoint.py`
(root `PROGRESS.md` and the `## Progress Tracker` link),
`checkpointing/refresh_guard.py --mode apply` (compacted `.claude/STATE.md`),
and `catchup/write_guide.py` (root `GUIDE.md`) mutate documents that the user
owns, so they add four guarantees on top of the shared contract:

- **Structured input from a file, never prose from argv.** `--input <file>` holds
  typed JSON for `append_state_block.py`, `update_design.py`, and
  `write_guide.py`; `checkpoint.py` takes the agent-written summary as
  `--summary-file` and validates it against the `checkpoint-summary` contract
  before embedding it; `refresh_guard.py` applies the candidate it composed.
- **Dry-run by default**: without `--apply`, produces a preview file under
  `.claude/logs/` and changes nothing.
- **Atomic replace** on `--apply`: writes to a temp file in the same directory,
  validates the *composed result*, then `os.replace()` over the original. The
  validation is not optional: a writer that replaced first and validated never
  published a malformed table and reported `ok: true`.
- **Concurrent-modification guard**: the content hash is checked before
  replacing; if the file changed since load, the script exits without writing.

Writing a user-owned document by hand with Edit/Write instead of through one of
these writers skips all four guarantees at once. That is why the destructive
steps of `/checkpointing` and `/catchup` are scripts now rather than prose plus
an approval prompt.
