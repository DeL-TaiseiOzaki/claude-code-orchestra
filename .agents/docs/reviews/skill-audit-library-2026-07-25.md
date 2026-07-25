# Skill Audit — library group

Audit date: 2026-07-25. Scope: `research-lib`, `update-lib-docs` (+ `lib_inventory.py`),
`simplify`. Normative standard: `.agents/skills/_shared/README.md` (Automation Boundary,
Shared Script Contract, lines 7-70).

Method: every helper cited below was executed (`--help` and real runs of
`lib_inventory.py`), and `tests/test_lib_inventory.py`, `tests/test_validate_doc.py`,
`tests/test_shared_script_contract.py` were read so that already-tested behaviour is
not reported as a missing test.

Already covered — NOT findings:

- `lib-doc` **is** registered in the contract registry (`validate_doc.py:101-103`) and
  both skills call it (`research-lib/SKILL.md:124`, `update-lib-docs/SKILL.md:61`).
  Rubric 4 is satisfied at the section level.
- research-lib's inline template is **not** un-pinned: `tests/test_validate_doc.py:532-537`
  extracts `## Documentation Template` from `research-lib/SKILL.md` and asserts the
  `lib-doc` contract accepts it, and `:566` forbids a contract without a pinned template.
  I was about to report "template lives in prose, undrifted-from-nothing" — withdrawn.
- `lib_inventory.py` satisfies the mechanical parts of the Shared Script Contract
  (single JSON line, `--project-root`, JSON argparse errors, no bare `except`,
  no `shell=True`); `tests/test_shared_script_contract.py:78-149` and
  `tests/test_lib_inventory.py:242-264` already enforce that. Absent
  `pyproject.toml` / absent `libraries/` dir are genuinely absent-optional paths and
  correctly degrade to exit 0 (`lib_inventory.py:187-200`, tests `:67-99`).

---

## research-lib

`.agents/skills/research-lib/SKILL.md`, 131 lines, no bundled script.

| Severity | Rubric # | Location file:line | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 1, 5 | `research-lib/SKILL.md:67-117` vs `update-lib-docs/lib_inventory.py:38-41` | The canonical template records the version as `- **Version**: {version}` inside `## Overview`. `lib_inventory.py` only reads `> **Last Updated**:` / `> **Version Checked**:` blockquote lines. So every doc research-lib creates is born with `has_metadata: false`, `last_updated: null`, therefore `age_days: null` and `stale: false` (`lib_inventory.py:132-144`). It is not `undocumented` either (the file exists). `update-lib-docs/SKILL.md:33-35` scopes a run to exactly `stale` + `undocumented` and says "Everything else is already current — skip it": a research-lib doc is therefore **permanently invisible to the maintenance loop**. The drift test at `tests/test_validate_doc.py:532-537` pins this metadata-less template as correct. | Add the two metadata lines to the template (they then flow into the pinned contract test), and add a `metadata_present` requirement — either a `lib-doc` contract extension in `validate_doc.py` or a `--require-metadata` mode on `lib_inventory.py`. |
| HIGH | 3 | `research-lib/SKILL.md:24` vs `:63` and `:124` | Two different derivations of the same path inside one file: the delegated subagent is told to write `.agents/docs/libraries/{library}.md`, while the lead's output location and the validation command use `.agents/docs/libraries/$ARGUMENTS.md`. `$ARGUMENTS` is the user's raw wording ("FastAPI", "fastapi 0.115", "@scope/pkg"). The subagent writes `FastAPI.md`; the lead validates `fastapi.md`; `validate_doc.py:203-209` returns exit 1 "file does not exist" and the run looks like a validation failure rather than a naming split — or worse, two docs for one library accumulate. No `workspace.py` entry exists for this skill (`workspace.py:34`, `:47-75` have no `research-lib` key), so there is no scripted path to use. | Add a `research-lib` entry to `workspace.py` PATH_TEMPLATES (`lib_doc`, plus `research` if a note is produced) and make both the subagent prompt and the validation command consume `paths.lib_doc` verbatim, exactly as `spike/SKILL.md:88-91` does. |
| HIGH | 1 | `research-lib/SKILL.md:22`, `:34-36`, `:72` | Nothing resolves the version **this project actually uses**. The prompt asks for "latest version" from the web, so `## Overview → Version` documents the newest release, not the pinned/locked one. Resolving the declared version from `pyproject.toml`/`package.json` and the resolved version from `uv.lock`/`package-lock.json` has exactly one correct answer per input and is currently absent from both prose and script (`lib_inventory.py:148-181` reads names only and discards the PEP 508 version specifier at `:120-122`). Result: a lib doc that confidently states a version the codebase does not run. | Extend `lib_inventory.py` (or a new `resolve_version.py`) with `--library NAME` returning `{declared_spec, locked_version, source_file, ecosystem}`; make the template's Version field come from that JSON, with the latest-upstream version recorded as a separate field. |
| MED | 2, 8 | `research-lib/SKILL.md:127-131` | The skill describes only one non-zero outcome: "A non-zero exit means the JSON's `sections_missing` lists which of those are absent". `validate_doc.py` exit 1 (file missing / unreadable, `:203-209`) carries **no** `sections_missing` key at all. An agent following the prose reads a missing-file failure as "fill in the sections" and can loop or hand-edit the wrong path. Same wording in `update-lib-docs/SKILL.md:64-67`. | State both codes: 1 = the doc was never written (the delegated subagent failed — re-delegate), 2 = sections missing. Mirror the exit-code sentence style of `spike/SKILL.md:134`. |
| MED | 2 | `research-lib/SKILL.md:17-26` | The delegation block has no completion gate of its own: the subagent is asked to write the file and "Return concise summary". A subagent that returns a plausible summary without writing anything is only caught incidentally by the later `validate_doc.py` call, and only if the agent actually runs it (step is prose, at the end, and not marked mandatory). | Make the validate call a hard gate ("do not report completion until exit 0"), or add a `workspace.py --skill research-lib --verify` step so an existing-but-trivial doc (`workspace.py:174` MIN_NONEMPTY_CHARS) also fails. |
| LOW | 9 | whole file | "research-lib must not implement" is nowhere stated. The skill has write access to `.agents/docs/libraries/` by convention only; nothing in the SKILL.md bounds the delegated Opus subagent to research. | Add a one-line scope clause ("produces documentation only; never edits source or dependency manifests") — enforceable because the only artifact path is scripted (see fix above). |
| LOW | 6 | `research-lib/SKILL.md:17-26`, `:28-36` | Delegation goes through the native Agent tool, which is correct per `.agents/rules/cli-execution.md:56-60` (that rule governs *cross-CLI* shell-outs). No raw `codex exec` / package-manager call anywhere. Noted as compliant; the only residual is that the "Fallback: WebSearch/WebFetch" path has no record of what was searched, so a research note is unauditable. | Optional: persist the source list into the `## References` section, which the contract already requires. |

## update-lib-docs

`.agents/skills/update-lib-docs/SKILL.md` (114 lines) + `lib_inventory.py` (257 lines).

| Severity | Rubric # | Location file:line | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 5 | `lib_inventory.py:134-135`, `:202-204`; `SKILL.md:15-17` | Staleness is **age-only**. `stale = age_days > stale_days`. `version_checked` is extracted (`:133`) and then never compared with anything; the declared dependency list keeps names only, because `normalize_dep_name` (`:107-122`) throws the version specifier away. So a doc updated yesterday that says `Version Checked: 1.4.0` against a manifest pinning `>=2.0` is reported as current, and the skill — whose entire purpose is currency — skips it (`SKILL.md:33-35`). Version drift, the most actionable staleness signal, is neither scripted nor even eyeballed: the JSON gives the agent nothing to compare against. | Emit per-library `declared_spec` / `locked_version` alongside `version_checked` and a derived `version_drift: true/false/unknown`; make `stale` the OR of age and drift. Add `--reason` in the entry so the report can say *why* it is stale. |
| HIGH | 2 | `lib_inventory.py:127-130` | `scan_library` catches `OSError`/`UnicodeDecodeError` and substitutes `text = ""`. A corrupt, permission-denied or non-UTF-8 doc is then indistinguishable from a doc that merely lacks metadata: `name` falls back to the stem, `has_metadata: false`, `stale: false`, report `ok: true`, exit 0. A library whose doc is unreadable is silently reported as "documented and current". This is a genuinely broken state hidden, not an absent optional path — the exemption in `_shared/README.md:66-68` does not cover it. | Add `"read_error": "<message>"` to the entry, a `counts.read_errors`, set top-level `ok: false` and exit `3` (external/read failure) per the shared vocabulary (`README.md:58-64`). |
| HIGH | 2 | `lib_inventory.py:151-153` and `:169-171` (tests `test_lib_inventory.py:222-239`) | A malformed `pyproject.toml` or `package.json` returns `[]`. `declared` becomes empty, `undocumented` becomes empty, `counts` all zero, `ok: true`, exit 0 — and `SKILL.md:33-35` then computes an empty scope and the skill reports "everything current". A broken manifest is exactly equivalent to a project with no dependencies. Note this is **not** an untested gap: `test_malformed_pyproject_does_not_crash:222` and `test_malformed_package_json_does_not_crash:233` assert this behaviour. The finding is that the tests lock in a contract violation — "errors are never swallowed" (`README.md:56-57`) — not that the behaviour is unverified. | Return the parse error, not `[]`: add `manifest_errors: [{file, error}]`, set `ok: false`, exit `2` (unreadable/invalid input). Update both tests to assert the error field + non-zero exit; keep exit 0 only for the *absent* manifest case already tested at `:67-99`. |
| MED | 2 | `lib_inventory.py:154-156` | Dependencies are read only from `[project]`. A Poetry project (`[tool.poetry.dependencies]`), a PEP 735 project (`[dependency-groups]`), or a uv project using `[tool.uv] dev-dependencies` yields `project` present-but-without-`dependencies` or a non-`[project]` layout → silently zero declared dependencies, so `undocumented` is empty and the whole cross-check no-ops with `ok: true`. Unknown-ecosystem is reported as "nothing to document". | Report the ecosystems actually parsed: `sources: [{file, table, dependency_count}]`, and emit `warnings: ["pyproject.toml has no [project].dependencies; Poetry/PEP-735 tables are not read"]` so an empty `undocumented` can never be read as "clean". |
| MED | 2 | `lib_inventory.py:228` (verified by run: `--project-root /nope/nope` → `ok: true`, exit 0; test `test_lib_inventory.py:90-99`) | A non-existent `--project-root` produces a fully clean, all-empty inventory at exit 0. A typo'd root — the single most likely operator error when this is invoked from another repository — reads as "every library is current". Per the shared vocabulary this is bad input (exit 1), not graceful degradation. | Validate that `--project-root` is an existing directory; exit 1 with `{"ok": false, "error": "project root does not exist: ..."}`. Amend `test_nonexistent_project_root_degrades_gracefully` accordingly. |
| MED | 1 | `SKILL.md:33-35` vs `lib_inventory.py:207-211` | `counts.missing_metadata` is computed but the *names* are never emitted, and the skill's scope rule excludes them. The one signal that would catch the research-lib metadata hole (HIGH above) is a bare integer the skill is told to ignore. | Emit `missing_metadata: [names]` next to `undocumented`, and make the skill's scope the union of the three lists. |
| MED | 8 | `SKILL.md:20` vs `--help` output | The documented invocation is `lib_inventory.py [--stale-days N]`. The real interface also has `--project-root` and `--today` (`lib_inventory.py:228-234`), and the skill never states the exit codes (0 / 1) or what to do when `ok` is `false` — unlike `spike/SKILL.md:134`, which is the house style. Not a wrong flag, but an incomplete contract: an agent has no instruction for a non-zero exit, so it will proceed with an empty scope. | Document `--project-root`/`--today`, the 0/1 (soon 0/1/2/3) codes, and an explicit "if `ok` is false, stop and report — do not treat an empty scope as success". |
| LOW | 7 | `SKILL.md:69-75` | Step 5 "Check Impact on Code" ends the skill on three prose questions ("Need to update project dependencies?"). If the answer leads to a manifest edit, no gate runs — `verify.sh` is never invoked by this skill (confirmed: the only `verify.sh` callers are tdd, troubleshoot, team-execute, feature, simplify). | If step 5 results in any file change outside `.agents/docs/libraries/`, require `bash .agents/skills/_shared/verify.sh` before the report. |
| LOW | 4 | `SKILL.md:88-105` | The "Update Format" block (the metadata lines `lib_inventory.py` depends on) is *not* one of the pinned reference templates in `tests/test_validate_doc.py:524-537`; only research-lib's template is pinned. The two templates in the group therefore disagree about metadata with only the wrong one under test. | Once the metadata lines are added to the research-lib template, this collapses into a single pinned template shared by both skills. |

## simplify

`.agents/skills/simplify/SKILL.md`, 92 lines, no bundled script. This skill **edits
source code**, which raises the bar per rubric 7.

| Severity | Rubric # | Location file:line | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 7 | `SKILL.md:76-84` | `verify.sh` runs **once, after** the refactor. There is no baseline run before step 4, so a gate that was already failing is indistinguishable from a regression the refactor introduced, and `overall: fail` gives the agent no way to attribute the failure. For a skill whose sole promise is "Don't change behavior" (`:89`), post-hoc-only verification cannot support that claim. | Run `verify.sh` before step 4 and store the baseline (it already writes `.agents/logs/verify.log`), then compare. Best done in a bundled `simplify_gate.py --phase before|after` that persists and diffs the two JSON summaries. |
| HIGH | 2, 7 | `SKILL.md:84` and `verify.sh:115-138`, `:189-194` | The `no_gates` escape hatch: "fall back to the project's own verification commands and confirm manually". `verify.sh` exits 0 with `overall: no_gates` whenever `uv` is absent, `pyproject.toml` is absent, pytest is unconfigured, or no tests are collected (exit 5, `:127-130`). On such a project `simplify` can rewrite code and declare success with **zero executed checks**, satisfying its own SKILL.md. "Confirm manually" is prose where a machine answer exists. | Treat `no_gates` as a blocking condition for a code-editing skill: require an explicit, recorded command list and its exit codes, or refuse to apply changes. At minimum, make "no tests exercised the touched files" a stated stop condition rather than a fallback. |
| HIGH | 1, 9 | `SKILL.md:9`, `:21-23`; contrast `team-execute/gather_diff.sh:47`, `:96`, `:111-120` | Nothing enumerates the changed files. Scope is `$ARGUMENTS` prose, and the skill never records what it touched, so the mandated self-review of the complete diff (`AGENTS.md:99-100`) has no input, and the scope boundary ("refactoring only", `:89`) is unverifiable: an out-of-scope file or a behavioural edit smuggled into a "simplification" leaves no artifact. `gather_diff.sh` already produces `changed_files`, `diffstat` and a `diff_file` and is **not** reused — the diff is not even re-derived by hand, it is simply never derived. | Reuse `gather_diff.sh` (it resolves its own repo root, `:17-18`) or add `simplify`-specific handling: capture the pre-edit `git status`/HEAD, and after the refactor emit `changed_files` + diffstat, failing when a file outside the agreed target set was modified. |
| MED | 1 | `SKILL.md:14-16` | "Target under 20 lines" and "Shallow Nesting — depth ≤ 2" are numeric thresholds with exactly one correct answer per function, left to eyeballing in step 1 ("Identify complexity hotspots"). The repo's ruff config selects only `E,W,F,I,B,UP` (`pyproject.toml [tool.ruff.lint]`) — no `C901`/complexity rule — so no configured gate measures either threshold. Two runs of `simplify` on the same file will disagree about which functions are hotspots. | Bundle a `complexity_scan.py` (stdlib `ast`) reporting per-function line count, max nesting depth, and missing annotations as JSON, and make step 1 consume it. Judging *which* hotspots are worth fixing stays prose. |
| MED | 1, 2 | `SKILL.md:26-30` | "Check constraints in `.agents/docs/libraries/`" with no scripted lookup. `.agents/docs/libraries/` is currently **empty** (verified), and the prose has no failure branch: an agent that finds nothing there simply proceeds, and the step silently becomes a no-op indistinguishable from "checked, no constraints". Mapping imports in the target file to doc filenames is mechanical (the normalization already exists as `lib_inventory.normalize_dep_name`, `:107-122`). | Extend `lib_inventory.py` with `--for-file PATH` (or add the lookup to the proposed `complexity_scan.py`): return `{imports, docs_found, docs_missing}`, so "no library docs exist for these imports" is an explicit reported state. |
| MED | 3 | `SKILL.md` (no artifact path anywhere) | `simplify` produces no durable record — no report path, no `workspace.py` entry (`workspace.py:34`). Its outcome exists only in the conversation, so a later reviewer cannot tell which quality gates ran or what was intentionally left alone. Contrast every other delivery skill in the group, which owns a doc path. | Either add a `simplify` entry to `workspace.py` for a short report under `.agents/docs/reviews/`, or explicitly document that this skill is intentionally artifact-free (a decision, not an omission). |
| LOW | 8 | `SKILL.md:81-84` | Verified correct: the path, `bash` invocation, and the `overall` / `log_file` / `pass`/`fail`/`no_gates` vocabulary all match `verify.sh:8`, `:189-200`. The only omission is the exit code (0 for pass *and* no_gates, 1 for fail, `:204`), which matters precisely because of the `no_gates` finding above. | State the exit codes alongside the JSON fields. |

---

## Proposed new or extended scripts

1. **Extend `workspace.py`** with a `research-lib` skill entry (`lib_doc:
   .agents/docs/libraries/{slug}.md`), so the doc path is derived once and consumed by
   both the delegated subagent and the validation call.
   *Design constraint discovered during the audit:* `workspace._slugify`
   (`workspace.py:117`) collapses `.` to `-`, while `lib_inventory.normalize_dep_name`
   (`:107-122`) preserves `.` via `PACKAGE_NAME_RE` (`:47`). A naive reuse would name
   `ruamel.yaml`'s doc `ruamel-yaml.md`, whose stem normalizes to `ruamel-yaml` and
   would never match the declared dependency `ruamel.yaml` — the library would be
   reported `undocumented` forever. The two normalizations must be unified (one
   function, one place) *before* the path is scripted, or the fix introduces a new
   silent mismatch.

2. **Extend `lib_inventory.py`** (single script, three additions):
   - version resolution: `--library NAME` → `{declared_spec, locked_version, source_file,
     ecosystem}`, reading `uv.lock` / `poetry.lock` / `package-lock.json`; also emitted
     per entry so `version_drift` can be computed. Closes the only genuinely mechanical
     gap in *both* library skills (research-lib rubric 1, update-lib-docs rubric 5).
   - honest error surface: `read_error` per entry, `manifest_errors`, `sources`,
     `warnings`, `missing_metadata` name list; `ok: false` plus exit 2/3 for a broken
     manifest or unreadable doc, exit 1 for a non-existent `--project-root`. Turns five
     silent-degradation paths into reported states.
   - `--for-file PATH`: imports → library-doc lookup, reusing the existing
     normalization, so `simplify`'s step 2 stops being an unfalsifiable prose step.

3. **New `simplify/complexity_scan.py`** (stdlib `ast`): per-function line count, max
   nesting depth, missing type annotations, as JSON. Makes "under 20 lines" and
   "depth ≤ 2" measured rather than eyeballed, and gives step 1 a reproducible hotspot
   list. Deliberately does not decide what to change.

4. **New `simplify/simplify_gate.py`** (or reuse `gather_diff.sh` + a thin wrapper):
   `--phase before` records the baseline `verify.sh` summary and git HEAD/status;
   `--phase after` re-runs the gates, diffs the two summaries, lists changed files, and
   fails on (a) a gate that regressed, (b) `no_gates`, (c) a file changed outside the
   declared target set. This is the single highest-value addition in the group: it is the
   only thing that would make simplify's "don't change behavior" and "don't widen scope"
   promises checkable.

5. **`validate_doc.py`: extend the `lib-doc` contract** to require the
   `> **Last Updated**` / `> **Version Checked**` metadata block (or add a sibling
   `lib-doc-metadata` check). Today no validator enforces the exact metadata that
   `lib_inventory.py` depends on, which is the root of the HIGH cross-skill hole.
   Because `tests/test_validate_doc.py:532-537` pins the contract to research-lib's
   inline template, updating template and contract together is self-enforcing.

## Keep as prose

- **Whether a simplification is worth making.** Extracting a function, choosing the
  seam, and naming it are judgment calls; a script that mandated "split every function
  over 20 lines" would produce worse code than it found. `complexity_scan.py` should
  report, never prescribe (`_shared/README.md:19-25`).
- **Reading and synthesizing library documentation** — deciding which constraints
  matter for this project, what belongs in `## Constraints & Notes`, and which
  anti-pattern is worth warning about. Only the *shape* of the document (sections,
  metadata, path) is mechanical, and that part is already or should be scripted.
- **Web research itself**: which sources to trust, how to weigh a release note against
  a GitHub issue. The native WebSearch/WebFetch tools are the right instrument; the
  scriptable part is recording the resulting version and references, not the judgment.
- **Deciding what a breaking change means for this codebase** (`update-lib-docs`
  step 5). Detecting *candidate* deprecated-API call sites is grep-able and could be
  assisted, but the impact assessment is not.
- **Choosing the staleness threshold.** `--stale-days` is correctly an operator input
  with a default, not a computed value.

### Cross-group note (outside this audit's scope, reported for the owning group)

`spike/SKILL.md:422` states the `spike-report` contract requires
`Question, Verdict, Evidence Summary, Risks, Next Steps`. The registry
(`validate_doc.py:105-112`) requires `Question, Verdict, Success Criteria Evaluation,
Risks, Recommendation`. Two of the five names in that sentence do not exist in the
contract — contract drift in the spike group.
