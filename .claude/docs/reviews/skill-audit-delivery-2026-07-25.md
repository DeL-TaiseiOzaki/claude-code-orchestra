# Skill Audit — delivery group

Scope: `.claude/skills/feature/SKILL.md` (+ `references/`), `.claude/skills/plan/SKILL.md`,
`.claude/skills/tdd/SKILL.md`. Audited against `.claude/skills/_shared/README.md`
(Automation Boundary, Shared Script Contract, Writer Safety Contract),
`AGENTS.md` (Cross-CLI Subagent Invocation, Guardrails) and
`.claude/rules/codex-delegation.md`. Read-only audit; every flag and exit code
cited below was verified by reading the script and running `--help`.

Reference points used as the "already good" baseline: `feature/SKILL.md:86-103`
(workspace resolution), `team-execute/SKILL.md:255-275` and `:489-503`
(work-log validation + workspace verify + quality gates), `spike/SKILL.md:418-419`
(validate_doc + workspace verify as a completion gate),
`troubleshoot/SKILL.md:540-552` (append_state_block dry-run then apply).

---

## feature

Strongest skill in the group on naming (Step 0-b is the canonical example of
rubric 3 done right) and on external-process invocation (every Codex call goes
through `codex_consult.py`, and the exit-code table at `:168-171` matches
`codex_consult.py:53-56` exactly — `EXIT_NOT_FOUND = 2`, `EXIT_FAILED = 3`).
Its weaknesses are all on the *output* side: documents it mutates by hand,
artifacts it never verifies, and delegated implementations it trusts.

| Severity | Rubric # | Location | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 5 | `feature/SKILL.md:184-202` | "DESIGN.md Update" tells the agent to write a `## Feature: {feature}` markdown block into `.claude/docs/DESIGN.md` by hand. `update_design.py` exists precisely for this and is used by `design-tracker/SKILL.md:76-78` and `init/SKILL.md:52`. A hand edit loses all four Writer Safety guarantees (`_shared/README.md:72-84`). This is not theoretical here: in MODE=greenfield the Architect teammate *also* writes DESIGN.md directly (`:458`) while the lead writes it in Phase 3 Step 3 (`:526-528`) — two writers, no concurrent-modification guard, silent lost update. | Replace the markdown block with a typed `decisions` / `section_updates` JSON input plus `python3 .claude/skills/_shared/update_design.py --input <file>` then `--apply`, mirroring `design-tracker/SKILL.md:76-78`. Verify `ok: true`; exit 3 = concurrent modification (`update_design.py:38-41`). Give the Architect the same instruction so both writers are serialized through the guard. |
| HIGH | 7 | `feature/SKILL.md:633-642` (Route B), `:644-648` (Route C) | Route A ends with `bash .claude/skills/_shared/verify.sh` (`:626-631`). Route B says only "**Run basic verification** (tests, linting)" — prose, no command, no JSON to read. Route C has no gate whatsoever. Yet B and C are the routes with *more* changed files, and B/C both run Codex at `--sandbox danger-full-access`. Completion is therefore declared on Codex's own summary (`:623`), which `AGENTS.md:86-89` and `.claude/rules/codex-delegation.md:65-86` explicitly forbid. | Make `bash .claude/skills/_shared/verify.sh` mandatory on all three routes with the same "read `overall`" wording already used at `:631`, and add the diff-inspection half of the Guardrails as an executable step (proposed script D). |
| HIGH | 7, 4 | `feature/SKILL.md:428-436`, `:465-474` | Both greenfield teammates are told to write a work log per `_shared/work-log-format.md`, but the skill never validates them. `validate_doc.py --contract work-log --dir` exists and `team-execute/SKILL.md:261` + `:493` call it on exactly these files. A teammate that dies mid-task, or writes a log missing `Issues Encountered`, is indistinguishable from success — and Phase 3 then synthesizes from an incomplete team run. | After "Wait for both teammates to complete" (`:476`), add `python3 .claude/skills/_shared/validate_doc.py --contract work-log --dir {paths.team_dir}` and gate on `files_failed == 0`, copying the `team-execute` wording. |
| HIGH | 9, 2 | `feature/SKILL.md:508-510` consumed vs `:530-536` gate | Phase 3 Step 1 reads `.claude/docs/research/{slug}.md` (Researcher) and `.claude/docs/libraries/{library}.md`. The gate at `:533` is `workspace.py --skill feature --slug {slug} --verify`, and `workspace.py:78` sets `REQUIRED_KEYS["feature"] = ("codebase_scan",)` — so in greenfield the gate verifies the one artifact the Opus scan wrote and *not* the Researcher artifact the phase actually consumes. The prose at `:536` ("do not present a plan built on a scan that was never written") reads as if it covered this. Library docs are never checked at all even though `validate_doc.py` has a `lib-doc` contract. | Extend `workspace.py` with `--require KEY` (repeatable) so greenfield can gate on `research` as well as `codebase_scan` (proposal A), and validate library docs with `validate_doc.py --contract lib-doc --dir .claude/docs/libraries/`. |
| HIGH | 9, 4 | `feature/SKILL.md:286-291`, `:379-383`; `references/brief-templates.md:4` | The Feature Brief / Project Brief is the primary cross-phase artifact: produced in Phase 1, consumed in Phase 2E Steps 1-3 (`:306`, `:328`, `:349`), in Phase 3 (`:507`), in the Route A prompt (`:601`) and handed to `/team-execute` (`:650-652`). It has **no path in `workspace.py:47-53`**, is never written to a file, and its "REQUIRED when the corresponding mode is active" sections (`brief-templates.md:4`) are never validated. Every downstream consumer interpolates it from conversation context, so a truncated or half-filled brief propagates into three Codex prompts and the team-execute handoff undetected. | Add a `brief` path to `PATH_TEMPLATES["feature"]` and a `feature-brief` contract to `validate_doc.py` (proposals A + B); require the brief file to exist before Phase 2E. |
| MED | 8 | `feature/SKILL.md:12`, `:636-641`, `:644-648` | The skill invokes another skill (`/team-execute`, `/team-execute --review-only`), while `_shared/README.md:4` states "Skills must never invoke other skills". One of the two documents is wrong. As written, the boundary rule that keeps `_shared/` the only dependency is silently violated by the highest-traffic delivery skill. | Decide explicitly: either soften the README rule to "skills may hand off to a sibling skill at a declared phase boundary, but must not inline another skill's procedure", or convert Route B/C into a documented user-facing handoff. Not a scripting problem — a contract that must be made consistent. |
| MED | 2 | `feature/SKILL.md:160-166`, `:589-596` | Prompt bodies are to be written to `.claude/logs/codex/prompt-{label}.md`, but nothing creates `.claude/logs/codex/`. `workspace.py --create` creates only the dirs implied by `PATH_TEMPLATES` (`workspace.py:47-53`, `:138-157`) — research, `.claude/logs`, team dir — not `logs/codex`. `codex_consult.py` mkdirs its log dir at `:244`, *after* reading the prompt file at `:222`. A heredoc write in a fresh clone fails; if the agent does not check that write, the subsequent consult reports `cannot read prompt file` (exit 1) or, worse, reads a stale prompt from a previous label. | Add a `codex_prompt_dir: ".claude/logs/codex/"` key to the shared `PATH_TEMPLATES` entries so `--create` provisions it (one-line extension, proposal E). |
| MED | 1 | `feature/SKILL.md:272`, `:284`, `:552-554`, `:582-586`; `references/brief-templates.md:26-30` | The complexity classification is *decided* by Codex (judgment — correctly prose), but it is then re-typed by hand into four places: the brief template, the STATE.md input JSON (`:224`), the plan presentation (`:552-554`) and the route selection (`:582`). Nothing ties them together, so a MODERATE assessment can be presented to the user and then routed as SIMPLE. | Record the decided classification once in the `state_input` JSON (already a machine-readable file at `paths.state_input`) and have the routing step read it from there. The *decision* stays prose; only its propagation becomes mechanical. |
| LOW | 8 | `feature/SKILL.md:650-654` | Claims that passing the slug to `/team-execute` makes "work logs and research/design files line up across phases". Research files do line up; work logs do not — `workspace.py:124-126` derives `team_name = f"{skill}-{slug}"`, so greenfield logs land in `agent-teams/feature-{slug}/` and team-execute's in `agent-teams/team-execute-{slug}/`. An agent trusting this sentence will look for Phase 2G logs in the wrong directory. | Correct the sentence: the slug is shared, the team dir is intentionally per-skill. |
| LOW | 2 | `feature/SKILL.md:77-84` | "if `PROGRESS.md` exists at the repository root, **read it** … If it is absent (fresh repo), skip this step" — textbook "if it exists" prose. Blast radius is small (lost context, not a wrong write), and `context-loader`/`load_context.py` already inventories repo state, so this is acceptable as prose *if* it points at that helper. | Optional: reference `context-loader/load_context.py` instead of an unchecked existence test. |

---

## plan

The weakest skill in the group by a wide margin. It is 76 lines of pure prose:
no shared helper, no artifact, no gate, no delegation. Everything it produces
lives only in the chat transcript, which makes it structurally unable to feed
the skills that are supposed to consume a plan.

| Severity | Rubric # | Location | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 3, 9 | `plan/SKILL.md:1-76` (whole file; output format `:42-68`) | No workspace resolution and no output path anywhere. The plan is never written to disk, has no slug, and carries no date. `team-execute/SKILL.md:70-83` resolves its workspace from a slug "reusing the same `slug` `/feature` resolved" and `feature/SKILL.md:650-654` hands a plan + slug to it — neither can be satisfied from `/plan`, so a `/plan` → `/team-execute` sequence has nothing to hand off and the executor re-derives its own slug. Cross-session resumption after `/checkpointing` loses the plan entirely. | Add `plan` to `workspace.py` `SKILL_CHOICES` + `PATH_TEMPLATES` (e.g. `plan: ".claude/docs/plans/plan-{slug}.md"`) and open the skill with a Step 0 workspace call in the exact shape of `feature/SKILL.md:92-103`. |
| HIGH | 4 | `plan/SKILL.md:42-68` | The Output Format declares a fixed section set (`Purpose`, `Scope`, `Implementation Steps`, `Risks & Considerations`, `Open Questions`) — a document contract with exactly one correct shape — and nothing validates it. `validate_doc.py --help` confirms the registry is `{bug-report, lib-doc, spike-report, work-log}`: there is no plan contract. A plan missing `Open Questions` (the section that surfaces blockers *before* implementation) is silently accepted. | Add a `plan-doc` contract to `validate_doc.py` (proposal B) and gate the skill's completion on it, as `spike/SKILL.md:418` does for its report. |
| HIGH | 7 | `plan/SKILL.md:70-76` ("Notes" is the last section) | The skill has no completion gate of any kind — no `validate_doc`, no `workspace --verify`, no Codex validation. Compare `feature/SKILL.md:344-369`, where Phase 2E Step 3 is a MANDATORY Codex plan validation returning `PASS / NEEDS_REVISION` and `:369` requires re-validation before proceeding. `/plan` produces the same artifact class with none of that scrutiny. | Add a validation gate: `validate_doc.py --contract plan-doc` for shape, plus a Codex validation consult reusing the `feature/SKILL.md:346-367` prompt body verbatim. |
| MED | 6-adjacent | `plan/SKILL.md:1-76` | `.claude/rules/codex-delegation.md:27-33` lists "You need a step-by-step implementation plan" and "Design/architecture decisions are involved" as explicit Codex triggers, and `:3` states "Codex CLI handles planning, design, and complex code implementation". The planning skill never consults Codex. Not a raw-external-process violation (nothing is invoked at all) but a direct routing-rule violation: the one skill named after the delegated activity omits the delegation. | Route step 3 (Break Down Implementation Steps) through `codex_consult.py --sandbox read-only`, following the established write-prompt-then-invoke pattern (`feature/SKILL.md:160-171`). |
| MED | 2 | `plan/SKILL.md:22-30` | "Current State Investigation" is a fenced *pseudo-list* ("Related existing code / Files affected / Libraries/patterns to use / Existing tests") — it looks like a code block but contains no commands, no tool calls and no delegation. Nothing records that the investigation happened, so a plan can be produced with zero codebase reading and be indistinguishable from a researched one. | Delegate to `general-purpose-opus` with a written artifact, as `feature/SKILL.md:115-151` does, and verify the artifact with `workspace.py --verify`. |
| LOW | 3 | `plan/SKILL.md:43` (`## Implementation Plan: {Title}`) | `{Title}` is hand-derived and no date is recorded, so two plans for the same feature overwrite or collide once a path exists. | Take the slug from `workspace.py` (`_slugify` at `workspace.py:102-121` is the single source of truth) and let the writer stamp the date, as `update_design.py` already does for decision rows. |

---

## tdd

Correctly delegates its final gate to `verify.sh` (`tdd/SKILL.md:84-90`, wording
matches `verify.sh:190-199` — `overall` ∈ `pass`/`fail`/`no_gates`, `log_file`).
Everything *inside* the Red-Green-Refactor loop, however, is prose with
unchecked commands, and the loop is where TDD can silently go wrong.

| Severity | Rubric # | Location | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 2 | `tdd/SKILL.md:50-53` ("Run test and **confirm failure**") | The central invariant of TDD — the test fails *for the right reason* — is asserted by prose with no exit-code handling. `pytest` exits 1 on assertion failure, 2 on internal error, 3 on interrupt, 4 on usage error and 5 on "no tests collected"; a typo in the test path, a missing import, or a file that was never written all present as "not passing" and satisfy a human reading "confirm failure". The Green step then writes code against a test that never ran. `verify.sh:125-129` already encodes exactly this distinction for exit 5 ("that is absence of a gate, not a failure"); nothing in `tdd` does. | Proposed script C: `run_tests.py --target <path> --expect fail`, exit 2 when the observed outcome is not the expected one, with `observed` naming `collection_error` / `no_tests_collected` separately from `failed`. |
| MED | 8, 1 | `tdd/SKILL.md:53`, `:65`, `:75`, `:95` | Four hardcoded `uv run pytest …` invocations, plus `--cov={module} --cov-report=term-missing` at `:95` which additionally requires `pytest-cov`. `verify.sh:114-124` guards each of these preconditions explicitly (`uv not available`, `pyproject.toml not found`, `pytest not configured in pyproject.toml`, `tests/ not found`) and reports them as *skipped* rather than passed. The skill bypasses all of that: on a non-uv or non-pytest project every command in the Red-Green-Refactor loop fails, and the failure appears as shell noise, not as a gate result. | Route per-cycle test runs through the same detection logic (proposal C, reusing `verify.sh`'s precondition checks) instead of hardcoding the toolchain in the SKILL.md. |
| MED | 7 | `tdd/SKILL.md:92-96` + `:105-114` | Coverage is measured but has no pass/fail semantics: no threshold, no parsed number, and the Report Format at `:108-109` just pastes `{Coverage report}`. Completion is therefore declared on a human glance at `term-missing` output, which is the "unparsed command output" failure mode. | Have `run_tests.py` return `coverage_percent` and accept `--min-coverage`, so the completion check has one correct answer; the *choice* of threshold stays a project decision. |
| MED | 4, 9 | `tdd/SKILL.md:31-36` (case list) vs `:98-114` (report) | The Phase 1 test-case checklist and the final report exist only in conversation context — neither is written to a file. After a context reset or `/checkpointing` compaction there is no record of which enumerated cases are still unimplemented, and the report's `[x]` marks are self-asserted against a list nobody can re-read. | Persist the case list to a resolved path (proposal A: a `tdd` entry in `workspace.py`) and have `run_tests.py` report `failed_tests[]` so the `[x]` marks are evidence-backed rather than self-asserted. |
| MED | 3 | `tdd/SKILL.md:43` (`tests/test_{module}.py`), `:53`, `:95` | `{module}` and the test path are hand-derived in three places, and `workspace.py:34` `SKILL_CHOICES = ("feature", "spike", "troubleshoot", "team-execute")` has no `tdd`, so there is no shared derivation to reuse. Test file and coverage target can drift apart within a single session. | Add `tdd` to `workspace.py` with `cases` / `report` paths; the module-under-test path itself should stay agent-chosen (see Keep as prose). |
| LOW | 2 | `tdd/SKILL.md:74-76` (Refactor step) | "Confirm still passes" — same unchecked-assertion pattern as the Red step, lower blast radius because the Phase 3 `verify.sh` gate eventually catches a broken refactor. | Covered incidentally by proposal C (`--expect pass`). |

---

## Proposed new or extended scripts

Ordered by value. Three of the five are extensions of existing helpers, per the
instruction to prefer extending over inventing.

### A. Extend `.claude/skills/_shared/workspace.py` (no new script)

- **Purpose**: cover the two delivery skills that currently have no deterministic
  naming, add the missing `feature` brief artifact, and make the required-artifact
  set mode-aware.
- **Changes**: add `"plan"` and `"tdd"` to `SKILL_CHOICES` (`workspace.py:34`) and
  to `PATH_TEMPLATES` (`:47`) — `plan: {plan: ".claude/docs/plans/plan-{slug}.md"}`,
  `tdd: {cases: ".claude/logs/tdd-{slug}-cases.json", report: ".claude/docs/research/tdd-{slug}.md"}`;
  add `brief: ".claude/docs/research/feature-{slug}-brief.md"` to the `feature`
  entry; add a repeatable `--require KEY` flag that overrides
  `REQUIRED_KEYS[skill]` (`:77-82`) for a `--verify` run.
- **Inputs**: unchanged (`--skill`, `--title`|`--slug`, `--create`, `--verify`,
  `--project-root`) plus `--require KEY`.
- **JSON output**: unchanged shape (`ok`, `skill`, `slug`, `team_name`, `paths`,
  `dirs`, `created`, `verify`), with the new keys appearing in `paths` and
  `verify.required` reflecting `--require`.
- **Exit codes**: unchanged — `0` resolved/created, `1` bad args or unknown
  `--require` key, `2` a required artifact missing or effectively empty.
- **Replaces**: `feature/SKILL.md:286-291`/`:379-383` (brief path),
  `:530-536` (greenfield gate), all of `plan/SKILL.md`'s missing Step 0,
  `tdd/SKILL.md:43`/`:95` hand-derived names.

### B. Extend `.claude/skills/_shared/validate_doc.py` (no new script)

- **Purpose**: give the two unvalidated document contracts in this group a
  registry entry, which is precisely the file's stated design ("document
  contracts live in a single registry rather than as a one-off validator per
  document type", `validate_doc.py:5-8`).
- **New contracts**: `feature-brief` — `Current State`, `Feature Goal`, `Scope`,
  `Complexity Classification`, `Integration Points`, `Risks`, `Success Criteria`
  (mirroring `references/brief-templates.md:11-42`; the existing whole-token-prefix
  matcher at `validate_doc.py:60-70` already handles `## Complexity
  Classification (from Codex)`). `plan-doc` — `Purpose`, `Scope`,
  `Implementation Steps`, `Risks & Considerations`, `Open Questions` (mirroring
  `plan/SKILL.md:42-68`).
- **Inputs / JSON / exit codes**: unchanged (`--contract`, `--file`|`--dir`,
  `--project-root`; `0` ok, `1` bad args or unreadable path, `2` missing section).
- **Note**: `tests/test_validate_doc.py` already validates each template against
  its contract, so adding the contracts also locks `brief-templates.md` and the
  plan output format against drift for free.
- **Replaces**: "following the … template in `references/brief-templates.md`"
  (`feature/SKILL.md:288`, `:381`) and the unenforced plan output format.

### C. New `.claude/skills/_shared/run_tests.py`

- **Purpose**: run the project's test command for a target and classify the
  outcome, so "confirm failure" / "confirm success" becomes an exit code.
- **Why new rather than an extension**: `verify.sh` intentionally runs the *whole*
  configured gate set and cannot express "expect this one target to fail".
  The precondition-detection logic (`verify.sh:114-124`) should be shared, not
  duplicated.
- **Inputs**: `--target PATH` (repeatable), `--expect fail|pass`,
  `--cov MODULE` (optional), `--min-coverage N` (optional), `--timeout SECONDS`,
  `--project-root DIR`.
- **JSON output**: `ok`, `expected`, `observed`
  (`passed` | `failed` | `collection_error` | `no_tests_collected` | `tool_missing`),
  `command`, `exit_code`, `summary`, `failed_tests` (list),
  `coverage_percent` (number or `null`), `log_file`, `error`.
- **Exit codes**: `0` observed matches expected; `1` bad arguments;
  `2` contract violation — observed ≠ expected, including red-for-the-wrong-reason
  and coverage below `--min-coverage`; `3` external failure — runner missing or
  timed out.
- **Replaces**: `tdd/SKILL.md:50-53`, `:63-65`, `:74-76`, `:92-96`.

### D. New `.claude/skills/_shared/check_delegated_diff.py` + promote `gather_diff.sh`

- **Purpose**: make the Guardrails completion verification
  (`AGENTS.md:107-131`, `.claude/rules/codex-delegation.md:65-82`) executable
  instead of prose, for every route that hands implementation to Codex or a team.
- **Prerequisite**: move `.claude/skills/team-execute/gather_diff.sh` to
  `_shared/gather_diff.sh` (a relocation, not a rewrite — it already resolves
  the repo root from its own location, `gather_diff.sh:17-18`). Today `feature`
  cannot reach it without reaching into another skill's directory, which is why
  its Guardrails step stayed prose.
- **Inputs**: `--base REF` (default `main`), `--allow-file PATH` (repeatable —
  the files the approved plan named), `--project-root DIR`.
- **JSON output**: `ok`, `diff_file`, `base`, `head`, `files_changed`,
  `deleted_files`, `out_of_scope` (changed files not in `--allow-file`),
  `suspect_hunks` (list of `{file, line, pattern}` for added
  `@pytest.mark.skip`, `except: pass`, bare `TODO`, `NotImplementedError`,
  and body-only `pass`), `error`.
- **Exit codes**: `0` nothing suspicious; `1` bad arguments; `2` contract
  violation — deletions, out-of-scope files, or suspect hunks found (meaning
  "read these hunks", not "reject": the interpretation stays with the agent);
  `3` external failure — not a git repo or base ref missing.
- **Replaces**: the missing verification in `feature/SKILL.md:633-642` and
  `:644-648`, and strengthens `:626-631`.

### E. Extend `PATH_TEMPLATES` with the Codex prompt directory (one line, no new script)

- **Purpose**: guarantee `.claude/logs/codex/` exists before a skill writes a
  prompt file there.
- **Change**: add `codex_prompt_dir: ".claude/logs/codex/"` to each
  `PATH_TEMPLATES` entry (or beside `_TEAM_DIR` at `workspace.py:45`) so
  `resolve_dirs`/`create_dirs` (`:138-157`) provision it on `--create`.
- **Replaces**: the unguarded prompt-file writes at `feature/SKILL.md:160-166`
  and `:589-596` (and the same pattern in `spike`/`troubleshoot`).

---

## Keep as prose

These steps have more than one defensible output and must not be scripted. A
proposal to automate any of them should be rejected.

- **Mode determination** — `feature/SKILL.md:41-62`. A signal table plus
  `AskUserQuestion` when signals conflict. This is exactly the "deciding the
  mode, route, or priority" column of the Automation Boundary
  (`_shared/README.md:12-17`). A heuristic script here would pick greenfield for
  a localized change and burn an Agent Team on it.
- **Complexity classification itself** — `feature/SKILL.md:272`, `:552-554`.
  File-count and LOC thresholds are stated, but the judgment ("does this
  3-file change carry cross-cutting risk?") is Codex's and the lead's. Only the
  *propagation* of the decided value should become mechanical (MED finding above).
- **Codex prompt bodies** — `feature/SKILL.md:263-282`, `:303-321`, `:325-342`,
  `:346-367`, `:598-621`. Composing the prompt content is authorship;
  `codex_consult.py` correctly owns only the invocation.
- **Interpretation of `NEEDS_REVISION`** — `feature/SKILL.md:369`. Deciding
  *how* to revise a plan cannot be scripted; only the re-validation loop's
  existence is a rule.
- **The user approval gate** — `feature/SKILL.md:538-580`. A script can check
  that the presentation has all its sections; it must never decide that the plan
  is good enough to proceed.
- **Step decomposition, risk articulation, open questions** —
  `plan/SKILL.md:32-38`, `:63-67`, and the `:70-76` Notes ("Don't over-detail").
  `validate_doc` can assert the sections are present; nothing can assert the
  steps are the right steps. Validating shape is not validating adequacy — the
  proposed `plan-doc` contract and the Codex validation consult are complements,
  not substitutes.
- **Test-case enumeration and edge-case selection** — `tdd/SKILL.md:25-36`.
  Which boundary values matter is domain reasoning.
- **Refactor timing and the "minimal code / hardcoding is OK" discipline** —
  `tdd/SKILL.md:56-61`, `:67-72`. A script that enforced a refactor after every
  green would break the cycle's intent.
- **Choice of the module under test** — `tdd/SKILL.md:43`. The *test-artifact*
  paths should come from `workspace.py`; where the production code belongs is a
  design decision that follows the project's existing layout.
