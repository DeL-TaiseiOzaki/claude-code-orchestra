# Skill Audit Fixes — Frozen Interface Spec (2026-07-25)

Implementation contract for the fixes in `skill-audit-2026-07-25-PLAN.md`. Work
is split across parallel agents with disjoint file ownership; this file freezes
every name that crosses an ownership boundary so an agent can code and document
against an interface another agent implements, without waiting for it.

**These names are frozen. Do not rename, and do not invent a variant.** If a
frozen name turns out to be wrong, report it instead of changing it locally.

## Governing principle

Script the mechanics, gate the shape, let the narrative fail loudly rather than
degrade quietly. A script may validate an artifact's *shape*; it never validates
its *adequacy*, so a new document contract is always added **alongside** the
existing Codex-validation and user-approval gates, never as a replacement.

Corollary, from four independent audit findings: a script that **guesses** is
worse than prose, because it converts uncertainty into an authoritative-looking
JSON claim. Where evidence is ambiguous, report the evidence and let the agent
decide.

## 1. Shared script conventions (all scripts, all waves)

1. **Success payloads carry `"ok": true`.** Every JSON object on stdout has an
   `ok` boolean, on success and on failure alike.
2. **`"artifacts": [...]`** — repo-relative POSIX paths of every file the run
   created or modified, `[]` when none. Additive: existing specific fields
   (`response_file`, `diff_file`, `preview_file`, …) stay as they are.
3. **Exit vocabulary** — `0` ok / `1` bad arguments or unreadable input /
   `2` contract violation (including a failed gate and a violated expectation) /
   `3` external failure (subprocess, timeout, write failure).
4. **Guarded writes** — every filesystem write is wrapped; `OSError` becomes
   `{"ok": false, "error": "..."}` with exit `3`, never a traceback.
5. **`--now ISO8601`** on every script that stamps a date or timestamp, defaulting
   to the real clock. Parsed with `datetime.fromisoformat`; an unparseable value
   is exit `1`. One call per run — a script must never read the clock twice.
6. **`--project-root DIR`** is honoured by *every* path the script touches. No
   module-level constant may bake in a directory (this is the
   `refresh_guard.py:26-29` defect).
7. **Empty is not success.** A result of "nothing found" is either an explicit
   expectation failure (see `--expect-*` flags) or a distinctly named state in the
   payload. It is never a silent exit `0` that reads as "all clear".
8. Shell scripts are **not** exempt from any of the above, including `--help` and
   valid JSON on every path.

## 2. `_shared/workspace.py` (owner: shared-writers agent)

### New `--skill` values

| Skill | Path keys | Required keys for `--verify` |
|-------|-----------|------------------------------|
| `plan` | `plan_doc` = `.agents/docs/plans/{slug}.md` | `plan_doc` |
| `research-lib` | `lib_doc` = `.agents/docs/libraries/{slug}.md` | `lib_doc` |

`.agents/docs/plans/` is a new project-owned directory: add `.gitkeep`, an
`INDEX.md` row, and extend the `AGENTS.md` ownership line to
`.agents/docs/{research,libraries,plans,reviews}/` (one-word edit — the file's
140-line cap must hold).

### New path keys on existing skills

| Skill | Key | Template |
|-------|-----|----------|
| `feature` | `brief` | `.agents/docs/research/feature-{slug}-brief.md` |
| `spike` | `brief` | `.agents/docs/research/spike-{slug}-brief.md` |
| `troubleshoot` | `bug_report` | `.agents/docs/research/troubleshoot-{slug}-bug-report.md` |

`brief` and `bug_report` join `REQUIRED_KEYS` for their skills.

### New flags

- `--teammate NAME` — adds `work_log` = `.agents/logs/agent-teams/{team_name}/{NAME}.md`
  to the resolved paths. `NAME` is constrained by `SLUG_RE`.
- `--require KEY` (repeatable) — with `--verify`, treat these keys as required in
  addition to `REQUIRED_KEYS`, so a mode-specific artifact (greenfield `research`,
  spike `prototype_dir`) is checkable without weakening the default.

### Package-name slugs — the trap

`_slugify` collapses `.` to `-`; `lib_inventory.py`'s `normalize_dep_name`
preserves it. Unifying the library doc path naively would map `ruamel.yaml` to
`ruamel-yaml.md` and report it undocumented forever.

Frozen resolution: `workspace.py` gains a **second, documented normalization**
used only for `--skill research-lib`: lowercase, `_` → `-`, `.` preserved,
matching `normalize_dep_name`. Add `PACKAGE_SLUG_RE = ^[a-z0-9][a-z0-9._-]{0,63}$`
for validating an explicit `--slug` in that mode. The two implementations stay in
their own scripts (stdlib-only, no cross-script imports) and are kept honest by a
new `tests/test_slug_agreement.py` asserting they agree on a fixture list that
includes `ruamel.yaml`, `Django`, `typing_extensions`, `uvicorn[standard]`.

## 3. `_shared/validate_doc.py` (owner: validation-gates agent)

### New flag

- `--expect-files N` (int ≥ 0, only with `--dir`) — when `files_checked != N`,
  exit `2` with `error: "expected N files, found M"`. This is the fix for
  "no teammate wrote a log" being indistinguishable from "all logs valid".

### New contracts

Registry additions. **Take each required section list verbatim from the template
or SKILL.md that already declares it** — do not invent section names, and if the
skill and its template disagree, that disagreement is a finding to report:

| Contract | Source of truth |
|----------|-----------------|
| `plan-doc` | `plan/SKILL.md` declared section set |
| `feature-brief` | `feature/references/brief-templates.md` |
| `spike-brief` | `spike/references/brief-template.md` |
| `diagnosis` | `troubleshoot/references/diagnosis-template.md` |
| `checkpoint-summary` | `checkpointing/references/formats.md` five-part summary |
| `progress` | `checkpointing/references/formats.md` PROGRESS.md shape |
| `guide` | `catchup/references/guide-template.md` |

Also extend `lib-doc` to require the version-metadata block (see §7).

Every new contract must be pinned by the existing template-pinning test pattern
in `tests/test_validate_doc.py`, so a contract that rejects a document produced by
following its own template is a test failure, not a runtime surprise.

## 4. `_shared/verify.sh` (owner: validation-gates agent)

- Add `--help` (exit `0`) and honour the exit vocabulary: **gate failure is exit
  `2`**, not `1`. Every SKILL.md that cites `verify.sh` must say exit `2`.
- `no_gates` (no uv / no pytest / no tests) becomes `ok: false` + exit `2` unless
  `--allow-no-gates` is passed explicitly. A code-editing skill must not be able
  to declare done with zero checks executed by accident.

## 5. New shared helpers

| Path | Purpose | Key flags | Owner |
|------|---------|-----------|-------|
| `_shared/gather_diff.py` | Port of `team-execute/gather_diff.sh`. Includes **uncommitted** work; `scope_empty: true` + exit `2` when the diff is empty | `--base`, `--include-uncommitted` (default on), `--out` | diff-skills agent |
| `_shared/run_tests.py` | Makes the TDD red/green invariant an exit code | `--expect fail\|pass`, `--target`; payload `observed` ∈ `passed`/`failed`/`collection_error`/`no_tests_collected`; mismatch → exit `2` | delivery agent |
| `_shared/verify_delegation.py` | Collects Guardrail evidence after a delegated run. **Reports, never auto-accepts** | `--base`, `--expect-files`, `--forbid-outside`; payload `deletions`, `placeholders`, `weakened_tests`, `out_of_scope_files`, `verdict: "needs-review"` always | project agent |
| `team-execute/check_ownership.py` | File-ownership overlap preflight + post-run reconcile against git | `--assignment <json>`, `--mode preflight\|reconcile`; overlap → exit `2` | diff-skills agent |
| `simplify/simplify_gate.py` | Baseline vs post gates so a pre-existing failure is not read as a regression | `--phase before\|after`, `--baseline <json>`; regression or out-of-scope file → exit `2` | diff-skills agent |
| `catchup/write_guide.py` | Assembles GUIDE.md from collected JSON + agent-written prose; rejects residual `{placeholder}` | `--input`, `--apply`, `--now` | context agent |
| `troubleshoot/repro.py` | Port of `repro.sh` | `--timeout` (required, default 120), `--expect-exit N`, `--label`; implements or drops `--bisect-good` | investigation agent |

`_shared/run_tests.py` and `simplify_gate.py` must not duplicate `verify.sh`'s
gate logic — they express *expectations* about a run; `verify.sh` runs the gates.

## 6. Writer Safety Contract — extended coverage

Dry-run by default, `--apply` to write, atomic `os.replace`, content-hash
concurrent-modification guard, and **validation of the composed result before
replacing** (the clause `update_design.py:361-363` currently skips):

| Document | New writer / change | Owner |
|----------|--------------------|-------|
| root `PROGRESS.md` | `checkpoint.py` gains `--apply` + the four guarantees | context agent |
| `.agents/STATE.md` (checkpoint link, compaction) | same, plus the compact phase gets a real apply path | context agent |
| `GUIDE.md` | `catchup/write_guide.py` | context agent |
| `.agents/STATE.md` `## Repository Identity` | typed writer (extend `append_state_block.py`) | shared-writers agent |
| `.agents/docs/DESIGN.md` tables | typed writers in `update_design.py` for `requirements`, `nfr`, `tech_choices`, `agent_roles`, with cell escaping (`\|`) and correct insertion placement | shared-writers agent |

`--require-change` is added to `update_design.py`: with it, a `no-op` result
(duplicate or empty decision) is exit `2`, so "recorded" can no longer be reported
when nothing was written.

Missing tests are part of this work, not follow-up:
`tests/test_append_state_block.py`, `tests/test_update_design.py`,
`tests/test_checkpoint.py`, `tests/test_refresh_guard.py`,
`tests/test_collect_repo_state.py`, `tests/test_gather_diff.py`,
`tests/test_repro.py`, `tests/test_slug_agreement.py`.

## 7. Library metadata format (owner: library agent)

One format, both sides. Frozen: the machine-readable block stays the
`> **Last Updated**:` / `> **Version Checked**:` blockquote that
`lib_inventory.py:38-41` already parses; `research-lib`'s template is corrected to
emit it, and the `- **Version**:` line inside `## Overview` is removed so there is
exactly one place a version lives.

`lib_inventory.py` additions: resolve the **declared/locked** version (not the
latest upstream), report `version_drift` by comparing it against
`version_checked`, and replace silent degradation with honest states —
`read_error`, `manifest_errors`, `sources`, and exit `1`/`2`/`3` per §1.7. The
existing tests that lock in the silent-`[]` behaviour must be updated, and the
update must be visible in the diff as an intentional contract change.

## 8. Deliberate reductions (P3)

1. `init/detect_stack.py` — stop inferring. Remove substring tool detection
   (`if "ty" in text` → `typing-extensions`) and the non-greedy dependency regex
   that drops everything after `uvicorn[standard]`. Report `evidence`: which
   manifest and which key each fact came from, and let the agent decide. Also:
   validate `--project-root`, catch `UnicodeDecodeError`, emit `ok`.
2. `checkpointing/checkpoint.py` — delete the commit-count summary fallback.
   A missing `--summary-file` is exit `2`, never a generated substitute.
3. `_shared/append_state_block.py` — remove `progress_tracker_preserved` (a
   hard-coded `True` that two skills instruct agents to verify) or make it carry a
   real check. A field named like a guarantee must carry one.
4. `team-execute/SKILL.md:242-248` and `design-tracker/SKILL.md:3,19-25` — either
   implement the claimed hook automation or delete the claim. Both are currently
   false statements in a normative document. Deleting the claim is acceptable and
   preferred over a hook that half-works.

## 9. Must stay prose — do not script

Complexity routing (`feature:272`), TDD case selection, team design and
Sonnet/Opus routing (`team-execute:127` explicitly forbids routing by file count),
prompt composition, GO/NO-GO and CONFIRMED/ELIMINATED verdicts, whether a
simplification is worth making, which library constraints matter, and what a
breaking change means for this codebase. `complexity_scan`-style measurement may
**report** a metric; it must never prescribe a refactor.

## 10. Definition of done (every agent, every wave)

- `python3 -m pytest -q` passes in full — not just your new tests.
- `bash .agents/check.sh` → 8/8 (or more, if you added a check).
- `ruff check .` and `ruff format --check .` clean.
- Every script you touched: `--help` exits `0`, an unknown flag exits `1` with one
  JSON object, and a real invocation was executed at least once.
- Every SKILL.md you changed cites flags, exit codes, and JSON fields that you
  verified against the actual script — the audit's most common finding was a
  SKILL.md describing a contract the script does not have.
