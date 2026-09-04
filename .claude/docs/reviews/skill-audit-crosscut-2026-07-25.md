# Skill Audit — shared runtime and cross-skill patterns

Scope: `.claude/skills/_shared/*`, the Shared Script Contract in
`.claude/skills/_shared/README.md`, the contract-enforcing tests under `tests/`,
and grep-level recurring patterns across all 15 `SKILL.md` files. Read-only
audit; no script or `SKILL.md` was modified.

All flags below were confirmed by running `--help` on each shared script, and
every failure mode marked "reproduced" was executed against a throwaway fixture
root.

---

## Recurring mechanical steps

| Operation | Skills + file:line where it recurs | Proposed shared helper |
|---|---|---|
| Derive the Codex prompt-file path from a label, then invoke the wrapper | 23 hand-typed `.claude/logs/codex/prompt-{label}.md` paths in 5 skills: `codex-system/SKILL.md:49`; `feature/SKILL.md:164,455,593`; `spike/SKILL.md:131,257,277,298,319,410`; `troubleshoot/SKILL.md:138,221,240,261,281,367,388,482`; `team-execute/SKILL.md:408` | `codex_consult.py`: when `--prompt-file` is omitted, default it to `.claude/logs/codex/prompt-{label}.md`; always copy the resolved prompt to `{timestamp}-{label}.prompt.md` next to the response and report `prompt_file` in the JSON. Today `codex-system/SKILL.md:49` *promises* "the prompt sits next to the response" but nothing in the wrapper enforces it — with `--prompt-stdin` the prompt is never persisted at all (`codex_consult.py:224-225`). |
| Resolve a workspace artifact path | Three coexisting conventions for the same thing: `{paths.x}` placeholders (`spike/SKILL.md:193,321,415,485-489`; `troubleshoot/SKILL.md:112,283,390,529,566-568`), literal repeated paths (`team-execute/SKILL.md:384,421,455,510-512`; `feature/SKILL.md:149,420,669-670`), and a table mixing both (`troubleshoot/SKILL.md:566-572`) | Keep one convention: every artifact reference is `{paths.<key>}` from `workspace.py`, and every "Output Files" table is generated from `PATH_TEMPLATES`. Add a test that greps each `SKILL.md` for `.claude/docs/research/...{slug}...` literals and fails if the path is not present in `workspace.py:PATH_TEMPLATES`. `troubleshoot`'s bug report (`SKILL.md:147,150,569`, `.claude/docs/research/troubleshoot-{slug}-bug-report.md`) is *not* in `workspace.py:61-67` at all — the one path the skill hand-types is the one path that can drift, and it is also the only troubleshoot artifact excluded from `--verify` (`workspace.py:80`). |
| Derive a teammate work-log path and validate the log | Path hand-written in 4 skills: `feature/SKILL.md:249-251,429-431,466-468`; `spike/SKILL.md:201-203,329-331`; `troubleshoot/SKILL.md:291-293`; `team-execute/SKILL.md:177-179,205-207,387-389,424-426,458-460`. Validation exists in only one: `team-execute/SKILL.md:261,493` | Add `work_log` to `workspace.py` path templates (`{team_dir}/{teammate}.md`), and make the post-team step one line in every team-spawning skill: `validate_doc.py --contract work-log --dir {paths.team_dir}`. Three of four skills that produce work logs never validate them, so a teammate that omits `## Issues Encountered` is caught in `/team-execute` and silently accepted in `/feature`, `/spike`, `/troubleshoot`. |
| Run the quality gates and interpret the result | Verbatim-identical 5 times: `feature/SKILL.md:625-631`; `simplify/SKILL.md:78-84`; `tdd/SKILL.md:84-90`; `team-execute/SKILL.md:268-274`; `troubleshoot/SKILL.md:507-513` | Already one script (`verify.sh`); the duplicated *prose* is interpretation and belongs in markdown (see "What NOT to script"). The real fix is smaller: bring `verify.sh` onto the shared JSON/exit-code contract so the three-way `pass`/`fail`/`no_gates` branch is `ok` + `overall` and the exit code distinguishes "gates failed" (3) from "bad args" (1). Today both are exit 1 (`verify.sh:22,27,204`). |
| Write a typed JSON input file for a writer script, dry-run, review, apply | Schema and the dry-run/apply pair re-described twice with near-identical prose: `feature/SKILL.md:217-243`; `troubleshoot/SKILL.md:529-554`; a third variant in `design-tracker/SKILL.md:76-78` | Ship the input schema as a machine-checkable artifact: `append_state_block.py --print-schema` / `update_design.py --print-schema`, and let both writers accept `--emit-input` to write a skeleton the agent fills in. Also stop instructing agents to verify a field that cannot be false: both skills say `Verify "progress_tracker_preserved": true` (`feature/SKILL.md:240`, `troubleshoot/SKILL.md:552`) but that field is a hard-coded literal at `append_state_block.py:236,270,326` — it is never computed, so the instruction is assurance theater. |
| Report "here is the file I wrote / read" | Six different field names for the same concept — see the Inconsistencies table | One clause + one helper: every script reports `artifacts: [{"path": <repo-relative>, "action": "wrote"\|"replaced"\|"read"}]` in addition to any legacy field. |

---

## Shared contract gaps

| Proposed clause | Failure mode it removes | Scripts that violate it today |
|---|---|---|
| **Success-path discriminator.** Every JSON object on stdout — success or failure — carries a top-level boolean `ok`. | A caller that branches on `payload.ok` reads `undefined` from a *successful* run and treats success as failure. This is the single most likely caller bug in the whole runtime. | `verify.sh:196-200` (uses `overall`, no `ok`); `gather_diff.sh:111-120`; `refresh_guard.py:178-186`; `init/detect_stack.py` and `catchup/collect_repo_state.py` success payloads (verified by running both against a fixture root); `checkpointing/checkpoint.py` (human text, excused at `README.md:49-51`). |
| **Every filesystem write is guarded and its failure is reported as JSON.** No unhandled `OSError` may reach the interpreter. | **Reproduced:** `python3 workspace.py --skill spike --slug x --create --project-root R` where `R/.agents` is a regular file prints a `NotADirectoryError` traceback with *no JSON at all* and exits 1 — which the exit-code table reads as "bad arguments". `README.md:46-51` claims one JSON object "on every error path without exception". | `workspace.py:156` (mkdir); `codex_consult.py:244,293,296`; `cli_consult.py:321,374,377`; `append_state_block.py:255,261`; `update_design.py:320,325`; `refresh_guard.py:180-183`; `checkpoint.py:710,730,849,855`. Only `validate_doc.py:154-157,169-170` handles read failure correctly. |
| **Verified success path.** A script that writes a structured document re-reads what it wrote and validates it before reporting `ok: true`; the JSON says which validation ran. | A structurally broken document is reported as a success and is discovered a phase later, after other artifacts were derived from it. | `update_design.py:361-363` — writes the temp file and `os.replace()`s it with **no** validation, even though `README.md:81-82` states the writer contract as "writes to a temp file …, validates structure, then `os.replace()`". `append_state_block.py:302-308` is the only script that honours this. Also `codex_consult.py:293` / `cli_consult.py:374` never confirm the response file is non-empty, so "Codex answered" and "we saved the answer" are not the same claim. |
| **Re-run safety.** Running a script twice with the same input must not duplicate content; the JSON reports `result: applied\|no-op\|preview`. | Re-running a phase after an interruption silently doubles user-owned content. | `update_design.py:210-231` — `section_updates` have **no** dedup at all: the same input applied twice appends the same block twice. `update_design.py:188,192` — decision dedup keys on `(decision, date)` with `date` defaulting to *today*, so the identical decision re-applied the next day is appended as a second row. `checkpoint.py:710` rewrites `PROGRESS.md` wholesale every run (idempotent by construction, but see the Writer Safety section). |
| **Injectable clock.** Any script whose output embeds a date or timestamp accepts `--now ISO8601` (or honours a single documented env override). | Timestamped output is untestable and unpinnable, and time-derived dedup keys (above) cannot be exercised. | `append_state_block.py:259`; `update_design.py:294,323`; `codex_consult.py:245`; `cli_consult.py:322`; `checkpoint.py:834`. None accept a clock override. |
| **Collision-free log filenames.** Response/log filenames must be unique per invocation, not per second. | Two consults with the same `--label` inside the same second silently overwrite each other's response file; with the default `--label consult` and parallel subagents this is likely, not theoretical. | `codex_consult.py:245-247` and `cli_consult.py:322-324` both build `{%Y%m%dT%H%M%SZ}-{label}.md`. |
| **Machine-readable touch list.** Every script reports `artifacts: [...]` naming every path it created, replaced, or read. | On the `--apply` path neither writer reports *any* path (`append_state_block.py:319-328`, `update_design.py:372-380`), so "which file did you just change?" cannot be answered from the JSON — only the *preview* path is reported. A caller cannot log, diff, or roll back what it cannot name. | Both writers on apply; `checkpoint.py` (paths only in human text); `validate_doc.py` (reports `file`/`dir`, no unified list). |
| **Paths are repo-relative POSIX strings.** | A caller cannot compare paths across two scripts' outputs, and absolute fixture paths leak into documents and logs. | `append_state_block.py:268`, `update_design.py:333`, `validate_doc.py:157,206,220`, `refresh_guard.py:184` emit `str(path)` as given (absolute by default). `codex_consult.py:76-81` / `cli_consult.py:117-122` / `workspace.py` already do this right — `_repo_relative` should move into the contract. |
| **Standard-library-only is machine-checked.** | `README.md:69-70` states it; nothing verifies it, so the first `import yaml` lands unnoticed. | No violation today; the clause is simply unenforced (an `ast`-based import check over the same `rglob` set is ~10 lines). |
| **`--help` and the exit-code vocabulary apply to `.sh` helpers too.** | `bash verify.sh --help` prints `{"error":"unknown argument: --help"}` and exits 1 (reproduced) — the one command a caller tries first. `gather_diff.sh` / `repro.sh` likewise have no `--help`. | `verify.sh:19-31`; `gather_diff.sh:23-27`; `repro.sh:29-30`. |

---

## Inconsistencies among shared scripts

| Concept | Site A | Site B | Proposed single form |
|---|---|---|---|
| Error envelope | `{"ok": false, "error": …}` — `workspace.py:98`, `validate_doc.py:136`, `append_state_block.py:62`, `update_design.py:54`, `codex_consult.py:72`, `cli_consult.py:113` | `{"error": …}` with no `ok` — `verify.sh:22,27`, `gather_diff.sh:25`, `repro.sh:29`, `refresh_guard.py:171` | `{"ok": false, "error": …}` everywhere, `.sh` included. |
| JSON formatting | compact one-liner — `workspace.py:87`, `append_state_block.py:51`, `update_design.py:43`, `codex_consult.py:61`, `cli_consult.py:103` | `indent=2` — `validate_doc.py:136,269`, `verify.sh:201`, `gather_diff.sh:121`, `refresh_guard.py:186` | Pick one (compact reads better in a transcript; `test_validate_doc.py:508` currently *pins* indent=2, so the choice must be made deliberately, not silently). |
| "The file I produced" | `response_file` — `codex_consult.py:312`, `cli_consult.py:398` | `preview_file` — `append_state_block.py:268`, `update_design.py:333`; `log_file` — `verify.sh:199`; `diff_file` — `gather_diff.sh:119`; `composed_state` — `refresh_guard.py:184`; `file` — `validate_doc.py:157` (a file it *read*) | Keep the domain-specific field, add the uniform `artifacts` list. |
| Grant of write access | `--sandbox {read-only,workspace-write,danger-full-access}` — `codex_consult.py:143-147` | `--write-access` boolean — `cli_consult.py:216-219` | Both already normalise to a reported `write_access` boolean; accept `--write-access` in `codex_consult.py` as an alias for `--sandbox workspace-write` so callers have one spelling for the common case. |
| Preview vs applied signalling | `result: preview\|applied\|no-op` — `append_state_block.py:231,263,320`, `update_design.py:310,328,374` | No `result` field and no dry-run concept — every other script; `refresh_guard.py --mode compose` writes a preview file (`:180-183`) but reports it as `composed_state` with no `result` | `result` becomes a contract field for any script with a preview mode. |
| "Optional tool absent" | `status: "skipped"` + `reason` — `verify.sh:51-55,171-174` | `{"ok": false, "issues": null, "note": "ruff not available"}` — `gather_diff.sh:107` | `verify.sh`'s form. `gather_diff.sh:107` reports a *missing* linter as `ok: false`, which a reviewer reads as "lint failed" — a direct violation of the graceful-degradation clause (`README.md:67-68`). |
| Exit code for "the work failed" | 3 = external failure — `codex_consult.py:57`, `cli_consult.py:98`, `append_state_block.py:46`, `update_design.py:39` | 1 = at least one gate failed — `verify.sh:11,204` | `verify.sh` should return 3 for gate failure and reserve 1 for bad args. |
| Swallowed read errors | `except OSError` → JSON + non-zero — `validate_doc.py:154-157` | `except OSError` → `return []` / `continue`, no field, exit 0 — `gather_diff.sh:92-93`, `verify.sh:156-157`, `checkpoint.py:698-702` (an unreadable or marker-less checkpoint is silently dropped from `PROGRESS.md`) | Degradation must be *reported*: a `skipped`/`warnings` list, never an invisible `continue`. |
| Stale identifier in a user-facing message | `append_state_block.py:280` reports `cannot re-read AGENTS.md` | The file is `.claude/STATE.md` (`:206`) | Name the real path; a wrong path in an error message sends the reader to the wrong file. |

---

## Enforcement coverage

`tests/test_shared_script_contract.py` auto-discovers via `rglob` (`:24-26`), so
new scripts are pulled in automatically. What it actually enforces:

| Contract clause (`README.md`) | Machine-enforced? | Where |
|---|---|---|
| Module docstring documents `Usage:` and `Exit codes:` | Yes | `test_shared_script_contract.py:78-86` (Python only) |
| `--help` exits 0 and documents `--project-root` (`:52-55`) | Yes, Python only | `:92-100` — checks the string appears in `--help`; does **not** check the flag is honoured (only `test_workspace.py:474` proves paths stay relative, for one script) |
| Argparse-level failure stays on JSON + exit 1 with `ok: false` (`:46-51`) | Yes, Python only, unknown-flag path only | `:106-119` |
| No bare `except:`, no `shell=True`, no `2>/dev/null` in Python (`:56-57`) | Yes | `:125-138` |
| Codex reached only through the wrapper | Yes | `:141-149` |
| One JSON object on **runtime** error paths (`:46-51`) | **No** | Reproduced violation at `workspace.py:156`; unhandled write failures listed above |
| `ok` present on the **success** path | **No** — and the contract does not even require it | five scripts lack it (see gaps table) |
| Shared exit-code vocabulary (`:58-66`) | **No** | `verify.sh:204` returns 1 for gate failure |
| Graceful degradation → `null`/empty, exit 0 (`:67-68`) | **No** | `gather_diff.sh:107` |
| Standard library only (`:69-70`) | **No** | no violation yet |
| `--help` / JSON / exit vocabulary for `.sh` helpers | **No** — `.sh` files are exercised only by the two source-text checks (`:125,141`) | `verify.sh --help` exits 1 |
| Writer Safety: typed input, dry-run default, atomic replace **with validation**, hash guard (`:72-84`) | **No — zero coverage.** There is no `tests/test_append_state_block.py` and no `tests/test_update_design.py`. | The two scripts that mutate `.claude/STATE.md` and `.claude/docs/DESIGN.md` are the only shared scripts with no dedicated test file, and `update_design.py:361-363` already diverges from the documented contract as a result. |

Priority: the highest-value new test is a `pytest.mark.parametrize` over the same
`rglob` set asserting (a) `ok` present on a successful run, (b) a forced write
failure still yields one JSON object with a non-zero exit, (c) `.sh` helpers
answer `--help` with exit 0 — plus a real test file for each writer.

---

## `validate_doc.py` registry gaps

Registered contracts (`validate_doc.py:99-122`): `work-log`, `lib-doc`,
`spike-report`, `bug-report`. `test_validate_doc.py:566` enforces that every
registered contract has a pinned reference template — but **not** the reverse:
nothing requires a produced document type to have a contract.

Document types produced by the skills with **no** registered contract:

| Document type | Produced at | Current validation |
|---|---|---|
| Diagnosis report (`troubleshoot/references/diagnosis-template.md`, 7 required sections) | `troubleshoot/SKILL.md:558` | none — presented to the user unvalidated |
| `GUIDE.md` (`catchup/references/guide-template.md`, 8 numbered sections) | `catchup/SKILL.md:92` | none — written to the repository root |
| Review reports ×3 (security / quality / tests) | `team-execute/SKILL.md:384,421,455` | length only (`workspace.py:174`, ≥20 chars) |
| Codebase scan, research notes | `feature/SKILL.md:149,420` | length only |
| Spike research + feasibility notes | `spike/SKILL.md:193,321` | length only |
| Troubleshoot context / root-cause / impact notes | `troubleshoot/SKILL.md:112,283,390` | length only |
| Feature / Project brief (`feature/references/brief-templates.md`) and Spike brief (`spike/references/brief-template.md`) | Codex prompt bodies | none (arguably correct — these are prompts, not deliverables) |
| Checkpoint file + `PROGRESS.md` (`checkpointing/references/formats.md`) | `checkpoint.py:849,710` | generated by code, but a checkpoint whose `PROGRESS-SUMMARY` markers are missing is silently dropped from `PROGRESS.md` (`checkpoint.py:700-702`) |
| Implementation plan (`plan/SKILL.md:43-68`, 5 required sections) | `plan/SKILL.md` | none — but it is a chat response, not a file |

Recommended additions, in value order: `review-report` (three consumers,
`team-execute` gates fix priorities on it), `diagnosis-report` (already has a
pinned template — a one-line registry entry per `validate_doc.py:98`),
`guide-doc`, and a shared `research-note` contract (e.g. `Summary`, `Findings`,
`Sources`) to replace the ≥20-char length check for the seven research
artifacts. Each is a one-line `_static([...])` addition plus a template pin, and
`test_validate_doc.py:553` then validates the template automatically.

---

## Writer Safety gaps

`README.md:72-84` grants the four guarantees to `append_state_block.py` and
`update_design.py` only. Scripts that mutate user-owned documents **without**
them:

1. **`checkpointing/checkpoint.py` — the serious one.** `:710` rewrites
   `PROGRESS.md` (repository root, user-owned) with a bare `write_text` on every
   run: no `--apply` gate, no temp-file + `os.replace()`, no content-hash guard,
   no post-write validation, and no JSON result. An interrupted write truncates
   `PROGRESS.md`; a concurrent edit is lost without a word. `:730` appends the
   Progress Tracker block to `.claude/STATE.md` the same way — the exact file
   `append_state_block.py` guards carefully. `README.md:49-51` excuses this
   script from the JSON contract because "it generates files", but that
   rationale covers the *report format*, not the absence of write safety.
2. **`update_design.py` — three of four guarantees.** Typed input ✓, dry-run ✓,
   hash guard ✓, but the atomic replace at `:361-363` skips the structure
   validation the contract text requires, so a malformed Key Decisions table is
   published and reported as `ok: true`.
3. **`checkpointing/refresh_guard.py`** writes `.claude/logs/composed-state.md`
   (`:180-183`) — agent-owned, so unguarded writing is acceptable — but the
   actual replacement of `.claude/STATE.md` is done *by hand* by the agent
   (`checkpointing/SKILL.md:63-65`). The one genuinely destructive step in the
   compact phase has no atomic write, no hash guard, and no rollback: it is
   prose plus an approval prompt. Either `refresh_guard.py` gains
   `--mode apply` under the writer contract, or `SKILL.md` should say plainly
   that this edit is unguarded.
4. **`catchup/SKILL.md:92`** overwrites root `GUIDE.md` via the agent's own file
   tools — no preview, no hash guard. Lower stakes (regenerable), but it is the
   fourth place a user-owned root document is replaced by hand.

---

## What NOT to script

The user's premise is right about mechanics and wrong at three specific
boundaries. Being concrete about where it stops paying off:

- **The verify.sh interpretation paragraph should stay prose.** It is duplicated
  verbatim five times (`feature:631`, `simplify:84`, `tdd:90`, `team-execute:274`,
  `troubleshoot:513`), which looks like a consolidation target, but the content
  is *what to do about a failure* — inspect the log, or fall back to the
  project's own commands. Wrapping that in a `handle_gate_result.py` would
  produce a script whose only output is advice the agent must still act on. The
  duplication is identical, so it carries no drift risk; a shared prose
  fragment in `_shared/` referenced by five skills is the most it needs.
- **Do not script prompt composition.** `feature/references/brief-templates.md`,
  `spike/references/brief-template.md`, and the seven Codex prompt bodies in
  `troubleshoot` are judgment content. A `render_prompt.py --template feature-brief`
  would force the agent to fill in fields it cannot always fill, and a
  half-filled template reads as authoritative in a way a half-written paragraph
  does not. `README.md:12-20` already draws this line correctly.
- **Do not add a validate_doc contract for chat-only deliverables.**
  `plan/SKILL.md:43-68` and the diagnosis report as *presented* are messages, not
  files. Only register a contract once the document is written to a path a later
  phase reads.
- **Beware of validation that cannot fail.** `progress_tracker_preserved`
  (`append_state_block.py:236,270,326`) is a constant that two skills instruct
  the agent to check. This is the failure mode more scripting invites: a field
  named like a guarantee that never carries one. Every clause proposed above is
  written so that it can *fail* — that is the acceptance test for adding one.
- **Do not chase the `indent=2` vs compact split for its own sake.** It is real
  (see Inconsistencies) but it hurts no caller, since `json.loads` handles both;
  and `test_validate_doc.py:508` pins the current behaviour. Fix it only if a
  shared `_emit` helper lands anyway.

Ranked by robustness gained per line of new code: (1) a real test file for each
writer script plus the missing post-write validation in `update_design.py`;
(2) guarded filesystem writes across all nine sites, so a failed write is never
a bare traceback; (3) `ok` on every success payload; (4) write safety for
`checkpoint.py`'s `PROGRESS.md` rewrite; (5) `--now` injectable clocks, which
unblock testing the two idempotency bugs in `update_design.py`.
