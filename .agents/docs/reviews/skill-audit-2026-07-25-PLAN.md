# Skill Robustness Audit — Integrated Fix Plan (2026-07-25)

Synthesis of six parallel audits of all 15 bundled skills and the shared runtime.
Per-group evidence lives in `skill-audit-{delivery,investigation,context,project,library,crosscut}-2026-07-25.md`;
this file deduplicates them into defect classes and a priority order. 52 HIGH
findings came from the five skill groups plus the structural findings from the
shared-runtime group. Findings marked **(reproduced)** were executed, not
inferred.

## The dominant defect class: empty or missing input reported as success

This one pattern accounts for more HIGH findings than any other, and it is the
mechanism by which every skill in the repo can produce a confident wrong result.

| Site | Empty/missing state | Reported as |
|------|--------------------|-------------|
| `gather_diff.sh:47-51` | uncommitted teammate work → `changed_files: []` | exit 0; 3 reviewers review nothing and pass the change **(reproduced)** |
| `validate_doc.py --dir` on a fresh team dir | no teammate wrote a log | `ok:true, files_checked:0`, exit 0 **(reproduced)** |
| `checkpoint.py:806-809` | `--summary-file` omitted | exit 0, all five sections `(no summary file provided)`, PROGRESS.md regenerated from the empty version **(reproduced)** |
| `lib_inventory.py:151-153` | malformed manifest → `[]` | exit 0 = "everything current" |
| `lib_inventory.py:127-130` | unreadable doc → `text=""` | indistinguishable from a doc with no metadata |
| `update_design.py:305-316` | duplicate or empty decision | `ok:true`, `result:"no-op"`, nothing written; SKILL.md:84 says report "recorded" **(reproduced)** |
| `verify.sh:115-138` | uv/pytest/tests absent | `no_gates`, exit 0 — a code-editing skill declares done with zero checks executed |

**Fix shape**: an empty result is a distinct state, never success. Add explicit
expectations at the call sites (`--expect-files N`, `--require-change`,
`scope_empty`, `--expect fail|pass`) so the caller states what it requires and
the script fails when reality differs.

## Defect classes, deduplicated

### A. Data loss and state corruption (highest severity — active, every session)

1. `checkpoint.py:725-732` + `refresh_guard.py:144-155` — STATE.md link appended
   at the end, then dropped by `compose`, then `verify` exits 2, then re-appended
   next run: an infinite loop, every session **(reproduced)**.
2. `refresh_guard.py:144-155` — a user's `## My Manual Notes` block is silently
   deleted and reported as `blocks_pruned: []`, while `agent-state.md:13`
   explicitly sanctions manual notes **(reproduced)**.
3. `refresh_guard.py:26-29` — `RESEARCH_DIR`/`ARCHIVE_DIR` are module constants,
   so `--project-root` is ignored and a fixture run proposes moving **real
   repository** files **(reproduced)**.
4. `update_design.py:197-231` — hand-written table rows get no cell escaping
   (`A|B` splits cells) and are inserted after the section's trailing blank line,
   orphaning the row and removing the blank line before the next heading — all
   reported `ok:true, applied` **(reproduced)**.

### B. Writer Safety applied to the safe writes and skipped on the destructive ones

`append_state_block.py` and `update_design.py` have dry-run + atomic replace +
hash guard. The more destructive writes do not:

- `checkpoint.py:710` rewrites git-tracked root `PROGRESS.md` with a bare
  `write_text`; `:730` appends to `.agents/STATE.md` the same way.
- `checkpointing/SKILL.md:63-65` — the actual STATE.md replacement (the single
  most destructive operation in the repo) is hand-executed prose with no apply path.
- `catchup/SKILL.md:92` overwrites `GUIDE.md` by hand.
- `init/SKILL.md:39-62` writes DESIGN.md and STATE.md `## Repository Identity`
  with raw Edit/Write; no typed writer for that section exists.
- `feature/SKILL.md:184-202` — DESIGN.md by hand, and in greenfield both the
  Architect (`:458`) and the lead (`:526`) write it → lost update.
- `update_design.py:361-363` replaces without the pre-replace validation
  `_shared/README.md:81-82` requires; `append_state_block.py:302-308` is the only
  compliant site.

**Root cause of that drift**: `append_state_block.py` and `update_design.py` are
the only shared scripts with **no test file**. The Writer Safety Contract is
entirely unenforced by the suite.

### C. Skills instruct documents their own validators reject

- `troubleshoot/SKILL.md:150-153` — bug-report sections: 3 of 5 names differ from
  `validate_doc.py:113-121`.
- `spike/SKILL.md:415-422` — spike-report: cites `Evidence Summary`/`Next Steps`;
  contract requires `Success Criteria Evaluation`/`Recommendation`.
- `troubleshoot:290-296`, `:397-403`, `spike:328-332` — teammates told role
  sections *replace* `## Tasks Completed`; a log written exactly as instructed
  fails validation with exit 2 **(reproduced)**.
- `research-lib/SKILL.md:67-117` vs `lib_inventory.py:38-41` — the doc template
  records the version as `- **Version**:` inside `## Overview`; the inventory only
  reads `> **Version Checked**:`. Every research-lib doc is born invisible to
  update-lib-docs: neither stale nor undocumented, permanently unreachable.

### D. Cross-phase artifacts that exist only in the transcript

| Artifact | Consumed by | Status |
|----------|-------------|--------|
| the plan | `/team-execute` (`team-execute:70-83`) | `plan/SKILL.md` defines no path, slug, or output file at all — the handoff is unsatisfiable and the plan is lost at checkpoint |
| Feature/Project Brief | 3 Codex prompts + team-execute handoff | never written to a file (`feature:286-291`), no workspace key, sections never validated |
| Spike Brief (success criteria) | Phase 3 scoring (`spike:136-140`) | never written to a file; Phase 3 scores against criteria that live only in the Lead's context |
| bug report | `troubleshoot` phases 2-3 | the one hand-typed path; absent from `workspace.py:61-67` and from `--verify` |

### E. Claimed automation that does not exist

- `team-execute/SKILL.md:242-248` claims `TeammateIdle`/`TaskCompleted` hooks run
  ruff/pytest/ty. `.claude/settings.json:32-49`: one is an `echo` reminder, the
  other a logger. **No hook runs any gate.**
- `design-tracker/SKILL.md:3,19-25` claims proactive activation. No hook
  references design-tracker; its trigger words are claimed by `CODEX_TRIGGERS`
  (`agent-router.py:52-53`) and produce a Codex nudge instead.

### F. Guardrails documented but not executable

Every `danger-full-access` Codex call in the repo is accepted on its self-report:

- `feature:633-648` — Route B says only "run basic verification" (no command);
  Route C has no gate at all.
- `spike:300-319` — `prototype_dir` is not in `workspace.py:79` `REQUIRED_KEYS`,
  and no diff inspection follows.
- `codex-system/SKILL.md:93-112` — the invocation SSOT omits the Guardrails
  entirely and tells the subagent to summarise on `ok: true`, which only means
  `codex exec` exited 0.
- `team-execute:32,306-330` — `--review-only` takes "all tests passing" as prose.
- `simplify:76-84` — `verify.sh` runs only *after* the edits: no baseline, so a
  pre-existing failure is indistinguishable from a regression introduced by the skill.

### G. Three conventions for paths; 23 hand-typed Codex prompt paths

`{paths.x}` (spike, troubleshoot) vs literals (`team-execute:384,421,455`,
`feature:669`) vs a mixed table (`troubleshoot:566`). The Codex prompt path is
hand-typed 23 times across 5 skills. Work-log paths are hand-written in 4 skills
and validated in only one.

### H. The `.sh` exemption hid three real defects

`test_shared_script_contract.py:78-119` applies the JSON / `--project-root` /
docstring clauses to `PYTHON_SCRIPTS` only, and no test invokes either shell
script. Consequences, all verified: `gather_diff.sh 'no"such"ref'` and
`repro.sh true '--we"ird'` emit **invalid JSON**; `repro.sh:72` runs
`bash -c "$REPRO_CMD"` with **no timeout**; `repro.sh:53-57` documents and parses
`--bisect-good` and then **never uses it**.

`_shared/README.md:53-55` justifies the exemption by saying those scripts
self-resolve their root — but `verify.sh` is also shell and *does* accept
`--project-root`, so the carve-out is an omission dressed as a rationale.

### I. Shared-contract gaps (each currently violated)

| Proposed clause | Violated today at |
|-----------------|-------------------|
| `ok` on every success payload | `verify.sh:196`, `gather_diff.sh:111`, `refresh_guard.py:178`, `detect_stack.py`, `collect_repo_state.py` |
| Guarded filesystem writes | `workspace.py --create` against a root where `.agents` is a file → traceback, no JSON **(reproduced)**; same class at `codex_consult:244,293`, `cli_consult:321,374`, `append_state_block:255,261`, `update_design:320,325`, `checkpoint:710,730` |
| Verified success path | `update_design.py:361-363` |
| Re-run safety | `update_design.py:210-231` (no dedup of `section_updates`), `:188,192` (decision dedup keyed on today's date) |
| Injectable clock (`--now`) | `append_state_block:259`, `update_design:294,323`, `codex_consult:245`, `cli_consult:322`, `checkpoint:430,834` (header/footer can disagree with the filename) |
| Machine-readable `artifacts` list | on `--apply` neither writer reports a path (`append_state_block:319-328`, `update_design:372-380`) |
| Collision-free log names | `codex_consult:245`, `cli_consult:322` — second granularity + default label; parallel consults silently overwrite |

Naming inconsistencies that most hurt callers: `{"error"}` without `ok` in the
shell paths vs `{"ok":false,"error"}` in the Python ones; **six** names for "the
file I produced" (`response_file`/`preview_file`/`log_file`/`diff_file`/
`composed_state`/`file`); "tool absent" as `status:"skipped"` (`verify.sh:51`) vs
`ok:false` (`gather_diff.sh:107` — a missing linter reads as a lint failure);
exit 1 for gate failure (`verify.sh:204`) vs 3 for external failure everywhere else.

### J. `validate_doc.py` registry gaps

Registered: work-log, lib-doc, spike-report, bug-report. Unregistered document
types the skills produce: diagnosis report (template exists → one-line add),
`GUIDE.md`, PROGRESS.md, checkpoint summary, plan, feature brief, spike brief,
the three review reports, and seven research notes validated only by
`workspace.py:174`'s ≥20-character check.

## Where more scripting makes things WORSE

Four independent agents converged on the same boundary, with concrete evidence.
These are reductions, not additions:

1. **`detect_stack.py` already over-reaches.** `if "ty" in text` (`:93`) turns
   `typing-extensions` into a confident `uv run ty check src/`, and the non-greedy
   dependency regex (`:133`) silently drops everything after `uvicorn[standard]`.
   Both then land in DESIGN.md as fact because `init/SKILL.md:30` says to use the
   fields. A script that guesses is worse than prose: it converts uncertainty into
   an authoritative-looking JSON claim. Fix = **less** inference; report which
   manifest and which key the evidence came from and let the agent decide.
2. **`checkpoint.py:365-414` auto-generates a summary from commit counts** when
   none is supplied — meaning substituted by metrics. That fallback is the bug;
   the missing-summary path must become an error, not a better generator.
3. **`progress_tracker_preserved` is a hard-coded `True`**
   (`append_state_block.py:236,270,326`) that two skills instruct agents to
   verify. A field named like a guarantee that carries none is worse than no field.
4. **Judgment must stay prose**: complexity routing (`feature:272`), TDD case
   selection (`tdd:25-36`), team design and Sonnet/Opus routing (`team-execute:127`
   explicitly forbids routing by file count — the only rule a script could apply),
   prompt composition, GO/NO-GO and CONFIRMED/ELIMINATED verdicts, whether a
   simplification is worth making, and what a breaking change means here.

Governing principle for every fix below: **script the mechanics, gate the shape,
and let the narrative fail loudly rather than degrade quietly.** A script may
validate a plan's *shape*; it can never validate its *adequacy*, so new document
contracts are added alongside the Codex validation and user-approval gates, never
as replacements.

## Trap to avoid during consolidation

Unifying the library doc-path derivation naively **creates** a bug:
`workspace.py:117` `_slugify` collapses `.` to `-`, while
`lib_inventory.py:107-122` `normalize_dep_name` preserves it. `ruamel.yaml` would
get `ruamel-yaml.md` and be reported undocumented forever. The two normalizations
must be merged *before* the path derivation is scripted.

## Priority order

### P0 — active data loss and confidently wrong results (small, mechanical)

1. `refresh_guard.py`: fix the STATE.md link loop; preserve unknown user blocks
   and report `sections_dropped[]`; thread `--project-root` through
   `RESEARCH_DIR`/`ARCHIVE_DIR`.
2. `checkpoint.py`: missing `--summary-file` → exit 2 (delete the commit-count
   fallback); enforce `SUMMARY_SUBSECTIONS` (currently defined and never
   referenced); single injectable `--now`.
3. `gather_diff.sh`: include uncommitted work; add an explicit `scope_empty`
   failure state.
4. `validate_doc.py`: `--expect-files N` so an empty directory cannot pass.
5. `update_design.py`: `--require-change` so `no-op` is not reported as recorded.
6. Section-name drift: correct `troubleshoot:150-153`, `spike:415-422`, and the
   "role sections replace Tasks Completed" instruction in both skills
   (documentation-only fix).
7. `research-lib` ↔ `lib_inventory` metadata format: one format, both sides.
8. `repro.sh`: add a timeout; implement or remove `--bisect-good`.

### P1 — write safety and its missing tests

9. `tests/test_append_state_block.py` + `tests/test_update_design.py`, and the
   missing pre-replace validation in `update_design.py` (the absent tests are why
   it drifted).
10. Writer Safety (dry-run + atomic replace + hash guard) for `PROGRESS.md`,
    `.agents/STATE.md` in `checkpoint.py`, `GUIDE.md`, and STATE.md
    `## Repository Identity`.
11. Typed table writers in `update_design.py` (`requirements`, `nfr`,
    `tech_choices`, `agent_roles`) with cell escaping and correct placement.
12. Guarded writes + `ok` on every success payload + one exit-code vocabulary +
    one name for "the file I produced", across all shared scripts.

### P2 — structure and consolidation

13. Port `gather_diff.sh` → `gather_diff.py` (move to `_shared/`) and
    `repro.sh` → `repro.py`; extend the contract test to cover shell scripts;
    delete the `.sh` exemption from `_shared/README.md`.
14. `workspace.py`: add `plan`, `feature brief`, `spike brief`, `bug_report`,
    `work_log`, `research-lib` entries; merge the two slug normalizations first;
    add `--require KEY` for mode-aware verification.
15. `validate_doc.py` registry: `plan-doc`, `feature-brief`, `spike-brief`,
    `diagnosis`, `progress`, `guide`, `checkpoint-summary`, and the `lib-doc`
    metadata block.
16. `codex_consult.py`: default `--prompt-file` from `--label`, always persist the
    prompt, report `prompt_file`, and make log names collision-free.
17. New `_shared/verify_delegation.py` (collects Guardrail evidence, never
    auto-accepts), `team-execute/check_ownership.py`, `_shared/run_tests.py`
    (`--expect fail|pass` for the TDD invariant), `simplify/simplify_gate.py`
    (`--phase before|after` baseline vs post gates).
18. `collect_repo_state.py`: fix frontmatter parsing (all 15 skills currently
    report an empty description); add the four datasets `guide-template.md` asks
    for and the collector never gathers.
19. `load_context.py`: add `PROGRESS.md` to `read_order`.
20. Contract amendments in `_shared/README.md`: success `ok`, guarded writes,
    verified success path, re-run safety, injectable clock, `artifacts` list,
    shell scripts not exempt.

### P3 — deliberate reductions

21. `detect_stack.py`: report evidence (which manifest, which key), stop
    inferring; validate `--project-root`; catch `UnicodeDecodeError`.
22. Remove `progress_tracker_preserved` or make it carry a real check.
23. `team-execute:242-248` and `design-tracker:3,19-25`: either implement the
    claimed hook automation or delete the claim. Both are currently false
    statements in a normative document.
