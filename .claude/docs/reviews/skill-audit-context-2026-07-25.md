# Skill Audit — context group

Scope: `catchup`, `checkpointing`, `context-loader` (SKILL.md + bundled scripts +
references). Audited against `.claude/skills/_shared/README.md` (Automation
Boundary, Shared Script Contract, Writer Safety Contract), `AGENTS.md`,
`.claude/rules/agent-state.md`, `.claude/STATE.md`.

Read-only audit. No SKILL.md or script was modified. All reproductions were run
against fixture directories under the session scratchpad via `--project-root`.

## Method note — what was verified, not inferred

- `--help` run on `validate_doc.py`, `append_state_block.py`, `update_design.py`,
  `workspace.py`, `verify.sh`, `load_context.py`, `checkpoint.py`,
  `refresh_guard.py`, `collect_repo_state.py`.
- `collect_repo_state.py` run against the real repo (frontmatter finding).
- `refresh_guard.py --mode compose/verify` and `checkpoint.py` run against
  fixtures (data-loss and Progress-Tracker-loop findings).
- `pathlib.Path.glob("*.md")` dotfile behaviour verified empirically.

### Already covered by tests — deliberately NOT reported as findings

`tests/test_shared_script_contract.py` already pins, for all three scripts:
module docstring `Usage:`/`Exit codes:`, `--help` exit 0 documenting
`--project-root`, unknown-flag → single JSON `{"ok": false}` + exit 1, no bare
`except:`, no `shell=True`, no `2>/dev/null`, no direct `codex exec`.
`tests/test_load_context.py` pins `load_context.py`'s rule ordering, graceful
degradation, exit 2 on missing rules/STATE, placeholder detection against the
real template, library substring matching, run-to-run determinism, and
single-JSON-line stdout. I was going to report "`checkpoint.py` and
`refresh_guard.py` have no dedicated tests" — the *contract* is covered by the
rglob-based test, so the finding below (CHK-14) is narrowed to behavioural tests
only.

---

## checkpointing

`checkpoint.py` is 873 lines with **zero dedicated behavioural tests**, writes
two user-owned documents (`PROGRESS.md`, `.claude/STATE.md`) with none of the
four Writer Safety guarantees, and its success path cannot distinguish "nothing
happened this session" from "every collector failed". `refresh_guard.py` is
advisory only and actively destroys unrecognised state sections.

| Sev | Rubric | Location | What breaks in practice | Proposed fix |
|-----|--------|----------|--------------------------|--------------|
| HIGH | 2, 7 | `checkpoint.py:806-809` | A missing `--summary-file` prints `Warning: summary file not found` to stdout and **exits 0** with a checkpoint whose five Japanese subsections all read `(no summary file provided)`. Reproduced: `--summary-file does-not-exist.md` → exit 0, checkpoint + PROGRESS.md written. The agent's hand-written Japanese summary — the entire user-facing value of the checkpoint — is silently discarded, and `PROGRESS.md` is regenerated with the empty version. | Missing/empty `--summary-file` must be exit 2 (contract violation) with a JSON error and **no** files written. Keep auto-generation only when the flag is absent entirely. |
| HIGH | 4 | `checkpoint.py:48-54` vs `references/formats.md:19-35` | `SUMMARY_SUBSECTIONS` is defined and **never referenced anywhere in the file** (verified by grep: single hit at line 48). The five-part Japanese contract that `SKILL.md:29-31` and `formats.md:21-34` both declare REQUIRED is therefore enforced nowhere. A summary file with three of five sections, or with `##` instead of `###`, is embedded verbatim and propagated into `PROGRESS.md`. | Register a `checkpoint-summary` contract in `validate_doc.py` `CONTRACTS` (a one-line addition per `validate_doc.py:97-99`) and gate the embed on it; exit 2 on violation. |
| HIGH | 5 | `checkpoint.py:678-711` (write at `:710`) | `regenerate_progress_md` **fully overwrites** the git-tracked, user-owned `PROGRESS.md` with a plain `write_text`: no `--apply`/dry-run, no preview file, no `os.replace` temp-file swap, no content-hash concurrent-modification guard. Contrast `append_state_block.py:213,276-287,309`, which has all four for the same class of document. An interrupted write leaves a truncated `PROGRESS.md`; a concurrent edit is clobbered without warning. | Apply the Writer Safety Contract: preview under `.claude/logs/` by default, `--apply` for the real write, temp-file + `os.replace`, hash check before replace, exit 3 on concurrent modification. |
| HIGH | 5 | `checkpoint.py:714-733` (write at `:730-732`) | `ensure_progress_link` mutates `.claude/STATE.md` with the same unguarded `write_text`, and its presence check is the substring `"## Progress Tracker" in content` (`:722`). Two Progress Tracker headings → returns `True`, no complaint, while `refresh_guard.py:117-121` would call that same state invalid (exit 2). The two scripts disagree on what "one Progress Tracker block" means. | Delegate the STATE.md write to `append_state_block.py`-style guarded logic, and count headings (`== 1`) rather than testing substring presence; exit 2 on 0 or ≥2. |
| HIGH | 9 | `checkpoint.py:725-732` + `refresh_guard.py:144-155` | **Reproduced Progress-Tracker destruction loop.** `ensure_progress_link` appends the block at the *end* of STATE.md. `compose_state` sets `base = lines[:first_work_index]` (`:149`) and then re-emits **only** `## Current *` blocks — so a Progress Tracker appended after a work block is silently dropped. Running `SKILL.md` Full Checkpoint step 7 → Compact Phase on such a state produced a composed state with `progress_tracker: 0`, and `--mode verify` exited 2. The next `checkpoint.py` run re-appends at the end, and the loop repeats every session. | `compose_state` must preserve every non-`## Current *` section in document order, not just the prefix before the first work block; and `ensure_progress_link` must insert at the canonical position rather than append. |
| HIGH | 5 | `refresh_guard.py:144-155`; report at `:113-141` | **Reproduced silent data loss.** A fixture STATE.md containing `## My Manual Notes` after `## Current Feature` produced a composed state with that section **deleted**, and the report said `blocks_pruned: []`. `agent-state.md:13` explicitly sanctions "manual notes" as working-block content, and `SKILL.md:48-49` promises only that Main Agent / Repository Identity / Progress Tracker are preserved — so an agent reviewing `composed-state.md` per `SKILL.md:62` has no signal that anything else vanished. | Preserve unknown sections; report every dropped section in a `sections_dropped` field; exit 2 if any non-work-block section would be lost. |
| HIGH | 5, 6, 7 | `SKILL.md:63-70` | The compact phase has **no apply path at all**. `refresh_guard.py` only writes `.claude/logs/composed-state.md` (`:180-184`); the actual replacement of `.claude/STATE.md` is left to the agent as prose ("After approved edits"). So the single most destructive operation in the skill — replacing shared state — is hand-executed with no atomic replace, no hash guard, and no dry-run, and `--mode verify` afterwards checks only two heading counts. | Add `refresh_guard.py --mode apply [--apply]` implementing the full Writer Safety Contract, and make `--mode verify` compare the on-disk state against the composed candidate (see proposals). |
| HIGH | 8, 2 | `refresh_guard.py:26-29` vs `:166` | **`--project-root` is only half-honoured.** `STATE_MD`, `RESEARCH_DIR`, `ARCHIVE_DIR` are module constants bound to the script's own location; only `main()` re-derives `state_md`. `collect_research_notes` (`:96-110`) and `move_plan` (`:134-140`) therefore always read **the real repository's** `.claude/docs/research/`, whatever `--project-root` says. Verified: `RESEARCH_DIR = /home/user/claude-code-orchestra/.claude/docs/research` under a fixture root, and a fixture-only research note was reported as `research_notes: []`. Consequence: `move_plan` can propose real-repo source and destination paths while the agent believes it is inspecting a fixture — and the archive step in `SKILL.md:63-65` acts on those paths. | Thread `root` through `build_report`/`collect_research_notes`; delete the module-level path constants. |
| HIGH | 3 | `checkpoint.py:430` and `:834` | **Two independent `datetime.now(UTC)` calls.** Line 834 derives the filename timestamp; line 430 derives the in-file `# Checkpoint {ts}` header and the `*Generated ... at {ts}*` footer. Across a second boundary the header does not match the filename, while `PROGRESS.md` links by filename stem (`:703-704`) — so header, footer, filename and link disagree. There is also no injectable clock, which makes every generated artifact untestable, and a same-second re-run **silently overwrites** the previous checkpoint (`:849` unguarded `write_text`; reproduced — two runs printed the identical path). | Add `--now ISO8601` (default `datetime.now(UTC)`), compute the timestamp once in `main()`, pass it into `generate_checkpoint`, and refuse to overwrite an existing checkpoint file (exit 3). |
| HIGH | 6 | `SKILL.md:32-37` | The step-4 command hard-codes `--summary-file .claude/checkpoints/.pending-summary.md`, and nothing deletes that file afterwards. If the agent runs step 4 without rewriting step 3's draft, the **previous session's summary** is silently embedded in the new checkpoint and propagated to `PROGRESS.md`. No freshness check, no cleanup, no "already checkpointed" guard — running the skill twice simply produces two near-identical checkpoints, both of which occupy slots in the 5-entry `PROGRESS.md`. | Have the script consume-and-remove the pending summary on success, and reject a summary file older than the newest existing checkpoint (exit 2). |
| MED | 2 | `checkpoint.py:82-96`, and callers `:136-137`, `:172-174`, `:210-212`, `:334` | `run_git_command` collapses non-zero exit, timeout, and a missing `git` binary into `None`; every caller then returns an empty list/dict (`if not output: return changes`). "git failed" is indistinguishable from "no activity". Reproduced on a non-git fixture: `Git: 0 commits, 0 files`, exit 0, checkpoint claiming no file changes. On a shallow clone the `HEAD~10` fallbacks (`:170`, `:208`, `:327`) also fail this way. | Return a `(ok, output, error)` triple; record per-collector failures in a `collector_errors` list written into the checkpoint and reported on stdout; exit 3 if any collector failed. |
| MED | 2, 8 | `checkpoint.py:108` | `datetime.fromisoformat(since)` is uncaught. Reproduced: `--since "30 days ago"` with a `cli-tools.jsonl` present → `ValueError` traceback on stderr, **no JSON on stdout**, exit 1 — violating "exactly one JSON object on stdout ... on every error path". Note the cross-skill trap: `catchup/SKILL.md:58` documents `--since "30 days ago"` as valid for its own collector. | Validate `--since` in `main()` before any collection; emit JSON and exit 1. |
| MED | 2 | `checkpoint.py:698-702` | In `regenerate_progress_md`, an unreadable checkpoint (`except OSError: continue`) and a checkpoint with no PROGRESS-SUMMARY markers (`if summary is None: continue`) are both skipped without any counter or warning. `PROGRESS.md` can be regenerated **completely empty** (heading + blurb only) while the run prints `Progress summary: ...` and exits 0. `regenerate_progress_md` also `return True` unconditionally (`:711`), so main's `if regenerate_progress_md(...)` at `:860` is a no-op check. | Return counts `{written, skipped_unreadable, skipped_no_marker}`; exit 2 if checkpoints exist but zero entries were written. |
| MED | 2 | `checkpoint.py:717-719`, `:865-866` | `ensure_progress_link` returns `False` when `.claude/STATE.md` is absent; `main()` merely skips the print. A missing shared-state file — a hard stop for `load_context.py` (exit 2) — is **completely silent** here, exit 0. | Exit 2 when `.claude/STATE.md` is absent. |
| MED | 8 | `references/formats.md:44` vs `checkpoint.py:487`; `formats.md:42` vs `:478`; `formats.md:121` vs `:609`; `formats.md:124-136` | `formats.md` claims (line 3-4) to describe "what the script already generates". It does not: `## Git History` vs emitted `## Git Activity`; `- **Tasks completed**: 8/10` vs emitted `- **Tasks**: 8/10 completed`; `## Design Decisions (New)` vs emitted `## Design Decisions (Changes)`; and `## Skill Pattern Suggestions` is never written into the checkpoint at all — it goes to the separate `.analyze-prompt.md` (`:854`). Anyone validating a checkpoint against this reference gets false failures. | Either regenerate the reference from the script's heading constants, or promote the headings to named constants consumed by both the writer and a `validate_doc.py` contract. |
| MED | 8 | `checkpoint.py:16`, `:863`, `:864` and `:716` var name `agents_md` | Docstring step 4 says "Ensure a **Zone-C-safe** PROGRESS.md link exists in **AGENTS.md**", and the inline comment repeats it, while the code writes `.claude/STATE.md`. `agent-state.md:15-17` states that boundary markers are legacy and "new bootstraps must not contain boundary markers", and `AGENTS.md:112-113` confirms `CLAUDE.md`/`AGENTS.md` are never written. Stale prose pointing at an immutable file invites an agent to edit the bootstrap. | Correct docstring, comment, and variable name to `.claude/STATE.md`; drop "Zone-C". |
| LOW | 2 | `checkpoint.py:661-675`; same bug at `collect_repo_state.py:225-233` | `pathlib.Path.glob("*.md")` **does** match dotfiles (verified). `.pending-summary.md` — which `SKILL.md:32` instructs the agent to place in `.claude/checkpoints/` — is therefore treated as a checkpoint. It sorts last under `reverse=True` (`.` < digits) and `[:5]` is applied *before* the marker filter (`:684`, `:700-701`), so with fewer than five real checkpoints `PROGRESS.md` silently shows one entry fewer. | Filter to the `YYYY-MM-DD-HHMMSS` filename pattern, or keep the pending summary under `.claude/logs/`. |
| LOW | 2 | `checkpoint.py:124`, `:265`, `:269` | `except (json.JSONDecodeError, KeyError): continue` / `except (json.JSONDecodeError, OSError): pass` drop malformed CLI-log lines and unreadable team configs with no count. A corrupted `cli-tools.jsonl` reads as "no CLI consultations". | Count skipped records and surface the counts in the run report. |
| LOW | 1, 7 | `SKILL.md:39-40` | Step 5 ("Confirm ... `.claude/STATE.md` still contains exactly one Progress Tracker block") is prose, yet `refresh_guard.py --mode check` computes exactly this (`:117-121`) — `agent-state.md:19` even names it the mechanical check. The one deterministic verification in the Full Checkpoint sequence is left to agent discretion. | Make step 5 an explicit `refresh_guard.py --mode check` invocation, or fold it into the checkpoint script's own exit code. |
| LOW | 14 | (no file) | Neither `checkpoint.py` nor `refresh_guard.py` has behavioural tests; only the generic rglob contract test applies. Every finding above is a regression waiting to recur. `--now` injection (CHK `datetime` finding) is the precondition for writing them. | Add `tests/test_checkpoint.py` and `tests/test_refresh_guard.py` in the style of `tests/test_load_context.py`. |

---

## catchup

The collector is clean and honest about degradation, but **the GUIDE.md
template asks for data the collector never gathers**, and Phase 3 has no writer
and no validator at all. The result is that the skill's only artifact is
entirely hand-assembled.

| Sev | Rubric | Location | What breaks in practice | Proposed fix |
|-----|--------|----------|--------------------------|--------------|
| HIGH | 2, 4 | `collect_repo_state.py:135` and `:174` | **Reproduced against the real repo: all 15 skills report `short_description: ""`.** `parse_frontmatter` skips any line starting with a space (`:135`), so nested `metadata:` → `short-description:` is unreachable; `:137`'s `.strip("|")` additionally guts every `description: |` block scalar. `guide-template.md:44` asks for a "Table: command — purpose, from skills/ frontmatter" — that column is structurally always empty, and the failure looks like a legitimately empty field, not a parse error. | Parse one level of nesting (or read `metadata.short-description` explicitly) and fall back to `description`; report a `frontmatter_errors` list and exit 2 if a `SKILL.md` yields neither name nor description. |
| HIGH | 1, 4 | `guide-template.md:33` and `:23`, `:55`, `:67` vs `collect_repo_state.py:199-207`, `:141-151` | Four template sections cannot be filled from the collector's output: §4 wants "Top 5 design decisions from DESIGN.md with rationale" but `collect_docs` returns only `design_present: bool`; §2 wants the `## Current Project` section but `collect_identity` returns only `first_line`; §7 wants setup commands but `pyproject.toml` likewise yields only `first_line`; §8 wants Agent Teams sessions, which the collector never scans (`checkpoint.py:239-273` does). `SKILL.md:83` simultaneously forbids re-reading the sources. So the agent must either violate the skill or invent content. | Extend the collector: `docs.design` = presence + placeholder flag + Key Decisions table rows; `identity.state` = the `## Current Project/Feature/Bug Fix` blocks; `env` = detected setup/lint/test commands; `agent_teams` = the scan already implemented in `checkpoint.py`. |
| HIGH | 1, 3, 7 | `SKILL.md:90-97`, `guide-template.md:12` | Phase 3 is pure prose: the agent writes `GUIDE.md`, hand-derives the `_Generated by /catchup on {YYYY-MM-DD}_` date, hand-decides which of eight sections to omit, and hand-reports "the file path and line count" (`SKILL.md:94`). Nothing verifies the file was written, that its heading structure matches the template, or that no `{placeholder}` token survived — despite `guide-template.md:79` ("Do not leave placeholder text") and `SKILL.md:86` being explicit contracts. | Add a `guide` contract to `validate_doc.py` (all-optional-sections contracts need a variant resolver) plus a `write_guide.py` that stamps the date, assembles from a JSON body, and rejects residual `{...}` tokens. |
| MED | 2, 8 | `collect_repo_state.py:37`, `:53-55`, `:295`; `SKILL.md:60-62` | Exit 1 means *both* "bad arguments" and "not a git repository", so a caller cannot tell them apart. Worse, the two paths have different stdout shapes: the argparse path emits `{"ok": false, ...}` (`:54`) while the success and non-git paths emit the state document with **no `ok` field at all** (`:294`). An agent that checks `.ok` sees `undefined` on the normal path. Per the shared vocabulary, "not a git repository" is a contract violation (exit 2), not bad arguments. | Add a top-level `ok` plus `errors` to the state document; move non-git to exit 2; keep 1 for argument errors. |
| MED | 2 | `collect_repo_state.py:58-72` and `:80-97` | Every git subcommand collapses failure into `None` → `_lines(None)` → `[]`, and `recent_stat` becomes `""` (`:92`). A git timeout, a shallow clone, or a broken index renders as "clean tree, no recent work, no stashes" — and `SKILL.md:60-61` reinforces this reading by promising graceful degradation. GUIDE.md §2/§3, the sections a returning contributor trusts most, then confidently describe a state that was never measured. | Distinguish `null` (command failed) from `[]` (genuinely empty) per subcommand, and add a `git.errors` list; exit 3 when a subcommand fails for a directory that *is* a git repo. |
| MED | 2 | `collect_repo_state.py:107-117` | `first_line` returns `None` for an absent **and** for an unreadable file (`except OSError: return None`, `:115-116`), and `""` for a file with no non-empty line. Three distinct states, two indistinguishable. This feeds `rules`, `docs`, `checkpoints`, and `identity`. | Return a small dict (`{present, first_line, error}`) or a sentinel for the unreadable case. |
| MED | 8 | `SKILL.md:108` vs `:50-52` | "Phase 1 runs in a subagent so the orchestrator never loads raw logs" contradicts lines 50-52, which state the script *replaced* the subagent scan. An agent following the Tips section spawns an unnecessary subagent. | Delete the stale Tip. |
| LOW | 8 | `guide-template.md:23`, `:57`, `:75` | The template still sources current focus "from AGENTS.md" and lists `AGENTS.md` in its Sources footer, but `agent-state.md:1-5` makes `AGENTS.md` an immutable bootstrap and puts working state in `.claude/STATE.md` (which the collector does read, `:144`). | Retarget the template at `.claude/STATE.md`. |
| LOW | 2 | `collect_repo_state.py:240-265` | `collect_cli_tools` returns the string `"not present"` both when the log is absent (`:244`) and when it is unreadable (`:246-247`), and drops malformed lines silently (`:255-256`). Also only `tool == "codex"` records are kept, while `SKILL.md:73` describes the key as "recent Codex consultation topics" — accurate, but it silently hides `cli_consult.py` (Claude/Gemini) activity that `guide-template.md:70` ("Frequent CLI consultations") implies is included. | Report absent vs unreadable distinctly; include all tools with a `tool` field. |
| LOW | 6 | `SKILL.md:109`, `.gitignore` | `GUIDE.md` is declared "idempotent — regenerated from sources each run", but it is LLM-authored prose, so successive runs produce different text, and it is **not** gitignored (verified) — every `/catchup` run yields a noisy diff on a tracked root file. | Either gitignore `GUIDE.md` or state plainly that regeneration is not byte-stable. |

---

## context-loader

The strongest skill in the group: `load_context.py` is deterministic,
well-tested, and its degradation semantics match the shared contract. Findings
are about coverage, not correctness.

| Sev | Rubric | Location | What breaks in practice | Proposed fix |
|-----|--------|----------|--------------------------|--------------|
| HIGH | 1, 4 | `load_context.py:215-223`, `:175-178`; `SKILL.md:34-39` | **`PROGRESS.md` is reported but never added to `read_order`.** `read_order` is built from rules + STATE + DESIGN + matched libraries only; `build_progress_info` computes presence and nothing consumes it. Yet `AGENTS.md:83` lists `PROGRESS.md` as the rolling progress record, and `checkpointing/references/formats.md:167-169` calls it "the first thing `/feature` reads on the next session". So the skill whose entire purpose is "one deterministic read order" (`:2-9`) structurally omits the one document carrying session-to-session continuity, and `SKILL.md:34-39`'s enumeration of what `read_order` covers omits it too — the gap is invisible to the reader. | Append `PROGRESS.md` to `read_order` when present (after STATE.md, before DESIGN.md or last — pick one and pin it in a test), and document it in `SKILL.md:34-39`. If the omission is deliberate, say so explicitly in the docstring. |
| MED | 2, 4 | `load_context.py:142-148`, `:47` | Placeholder detection keys on the English marker `"Background & Purpose"`. `_extract_section_body` returns `None` when no `## ` heading contains it, and `_is_design_placeholder` then returns **`False`** — i.e. a DESIGN.md whose heading was renamed (or which has no such section at all) is reported as *initialised* however empty it is, with no warning. `tests/test_load_context.py:170-188` pins the shipped template, so template drift is caught; a user edit is not. | Treat "marker heading absent" as a distinct third state (`placeholder: null` + a warning), not as "initialised". |
| MED | 2 | `load_context.py:80-86`, `:151-160`, `:225-233` | `_safe_read` maps *missing* and *unreadable/undecodable* to the same `None`, so a permission-denied or non-UTF-8 `.claude/STATE.md` is reported as `present: false` and listed in `missing` → exit 2 with a message that steers the agent to `/init` instead of to a filesystem problem. | Split the two cases; add an `unreadable` list; keep exit 2 but with an accurate cause. |
| MED | 4 | `load_context.py:151-160`; `.claude/STATE.md:3-5`; `.claude/docs/change_main.md:37-38` | `main_agent` is returned as an unvalidated free string. The set of legitimate values is finite and enumerable (`Claude Code`, `Codex`, `Antigravity`, plus any former main per `change_main.md:37-38`), and routing depends on it, but a typo yields `ok: true` and an arbitrary value. | Validate against a known set; unknown value → warning (not exit 2, since `change_main.md` allows new mains). |
| MED | 4 | `load_context.py:175-178` | Presence of `PROGRESS.md` is checked with `is_file()` and nothing more. A `PROGRESS.md` truncated by the unguarded write in `checkpoint.py:710` — or one containing only the heading and blurb — reports `present: true`. The two skills' failure modes compound. | Validate the `# PROGRESS` heading and at least one `## [timestamp](...)` entry; report `entries: N`. |
| LOW | 8 | `SKILL.md:68-76` | "Key Rules to Remember" restates five principles (uv-only, type hints, etc.) that live in `.claude/rules/` — the very files `read_order` enumerates. Verified accurate today against `dev-environment.md:5-7`, but it is a hand-maintained duplicate of authoritative content, which is exactly the drift the script exists to prevent. | Replace with a pointer to the rule files; let the read order carry the content. |
| LOW | 1, 7 | `SKILL.md:41-59`, `:84-89` | The skill's confirmation ("Rules loaded / Design document status / Ready") is a prose self-report. Nothing distinguishes "read the read_order" from "ran the script and skipped the reads". This is largely irreducible (see Keep as prose), but the *reportable* half — which paths existed, which were missing, which warnings fired — is already in the JSON and could be echoed verbatim. | Have `SKILL.md` require the `missing`/`warnings` arrays to be quoted verbatim in the confirmation, rather than paraphrased. |

---

## Proposed new or extended scripts

Ordered by value. All follow the Shared Script Contract (single JSON object on
stdout, `--project-root`, shared exit vocabulary, stdlib only) and — where they
touch `PROGRESS.md`, `.claude/STATE.md`, or `GUIDE.md` — the Writer Safety
Contract.

### 1. Extend `.claude/skills/_shared/validate_doc.py` (highest value, smallest change)

- **Purpose**: enforce the document shapes that are currently only *described*.
- **Inputs**: existing `--contract {…}` / `--file` / `--dir` / `--project-root`,
  plus three new contracts.
  - `checkpoint-summary` → required `["何をしたのか", "どういうやり取りをユーザーと行ったのか",
    "どうやったのか", "途中でどういう課題が起こったのか", "将来のアクション"]`
    (mirrors `references/formats.md:21-34`). A fixed heading list is a one-line
    registry addition per `validate_doc.py:97-99`.
  - `progress` → required `["PROGRESS"]` plus a structural rule "≥1
    `## [ts](.claude/checkpoints/ts.md)` entry, ≤5 entries".
  - `guide` → the eight `guide-template.md` sections, all optional, plus the
    hard rule "no residual `{placeholder}` token".
- **JSON output**: unchanged shape (`ok`, `contract`, `variant`,
  `sections_found`, `sections_missing`).
- **Exit codes**: `0` valid · `1` bad args/unreadable · `2` contract violation.
- **Replaces**: `checkpointing/SKILL.md:29-31` (five-part summary asserted in
  prose), `SKILL.md:39-40` (hand-confirmation), `catchup/SKILL.md:86` and
  `guide-template.md:79` (omit-don't-placeholder, asserted in prose).

### 2. `.claude/skills/checkpointing/checkpoint.py` — hardening (no new file)

- **Purpose**: make the existing generator deterministic, fail-loud, and safe
  against concurrent edits.
- **New inputs**: `--now ISO8601` (single injected clock, default
  `datetime.now(UTC)`), `--apply` (dry-run by default, preview under
  `.claude/logs/`), `--require-summary` behaviour by default.
- **JSON output** (a `--json` mode alongside the sanctioned human report):
  `{ok, checkpoint_path, progress_path, progress_entries, state_updated,
  summary_validated, collector_errors[], skipped_records{}, warnings[]}`.
- **Exit codes**: `0` ok/preview · `1` bad args (including an invalid
  `--since`, fixing `:108`) · `2` missing or invalid summary file, missing
  `.claude/STATE.md`, 0 or ≥2 Progress Tracker headings · `3` collector
  subprocess failure, write failure, timestamp collision, concurrent
  modification of `PROGRESS.md`/`STATE.md`.
- **Replaces / fixes**: `SKILL.md:39-40` step 5, and findings at
  `checkpoint.py:108`, `:430`/`:834`, `:661-675`, `:698-711`, `:717-719`,
  `:722`, `:730-732`, `:806-809`.

### 3. `.claude/skills/checkpointing/refresh_guard.py` — hardening + `--mode apply`

- **Purpose**: make the compact phase lossless, root-honest, and transactional.
- **Inputs**: existing `--mode {check,plan,compose,verify}` plus
  `--mode apply --apply` and `--expect-hash SHA256`.
- **JSON output**: existing report plus `{ok, sections_preserved[],
  sections_dropped[], blocks_pruned[], composed_state, applied,
  state_hash_before, state_hash_after}`.
- **Exit codes**: `0` ok/preview · `1` bad args · `2` invalid structure **or a
  non-work-block section would be dropped** · `3` unreadable state, write
  failure, concurrent modification.
- **Also fix**: thread `root` into `build_report`/`collect_research_notes` and
  delete the module-level `STATE_MD`/`RESEARCH_DIR`/`ARCHIVE_DIR` constants
  (`:26-29`); make `verify` genuinely distinct — compare on-disk state against
  the composed candidate and assert the Progress Tracker survived. Today
  `check`, `plan`, and `verify` are byte-identical code paths (`:174-188`),
  which is contract drift against `SKILL.md:51-70`.
- **Replaces**: `SKILL.md:63-65` (hand-applied replacement of shared state).

### 4. `.claude/skills/catchup/collect_repo_state.py` — extend to cover the template

- **Purpose**: gather every input `guide-template.md` actually asks for, so
  Phase 2 synthesises rather than invents.
- **New JSON fields**: `ok`, `errors[]`, `frontmatter_errors[]`,
  `git.errors[]`, `docs.design{present, placeholder, key_decisions[]}`,
  `identity.state{current_project, current_feature, current_bug_fix}`,
  `env{setup_commands[], lint, test, run}`, `agent_teams[]` (reuse
  `checkpoint.py:239-305`).
- **Exit codes**: `0` ok/degraded · `1` bad args · `2` not a git repository, or
  a `SKILL.md`/agent frontmatter that cannot be parsed · `3` git subcommand
  failed inside a real repo.
- **Replaces**: the unfillable template sections `guide-template.md:23`, `:33`,
  `:55`, `:67`, and the empty slash-command purpose column at `:44`.

### 5. `.claude/skills/catchup/write_guide.py` (new)

- **Purpose**: stamp, assemble, and validate `GUIDE.md` from an
  agent-authored JSON body, so only the *prose* is hand-written.
- **Inputs**: `--input body.json` (`{section_id: markdown}` for the eight
  template sections), `--now ISO8601`, `--apply`, `--project-root`.
- **JSON output**: `{ok, guide_path, preview_path, sections_written[],
  sections_omitted[], line_count, residual_placeholders[], applied}`.
- **Exit codes**: `0` ok/preview · `1` bad args/unreadable input · `2` unknown
  section id, or a residual `{placeholder}` token · `3` write failure or
  concurrent modification of `GUIDE.md`.
- **Replaces**: `catchup/SKILL.md:92-97` in full — the date stamp, the
  omit-empty-sections rule, the section ordering, and the "report path and line
  count" step.

### 6. `.claude/skills/context-loader/load_context.py` — small extensions

- Add `PROGRESS.md` to `read_order`; add `progress.entries`;
  split `unreadable` from `missing`; add `state.main_agent_known: bool`;
  make `design.placeholder` tri-state (`true`/`false`/`null` + warning).
- **Exit codes**: unchanged (`0`/`1`/`2`), with the new `unreadable` cases
  reported as exit 2 with an accurate cause.
- **Replaces**: nothing in prose — this closes the coverage gaps above and
  extends `tests/test_load_context.py`.

### 7. `tests/test_checkpoint.py`, `tests/test_refresh_guard.py`,
`tests/test_collect_repo_state.py` (new)

- **Purpose**: pin every finding above as a regression. Preconditions: the
  injected `--now` clock (#2) and the threaded `root` (#3). Model on
  `tests/test_load_context.py`, which already demonstrates the fixture-root
  pattern these scripts' `--project-root` flags were built for.

---

## Keep as prose

These steps have more than one defensible output and must not be scripted. The
user's "script everything" instinct is right about *mechanics* and wrong here.

- **`checkpointing/SKILL.md:26-31` — writing the five-part Japanese summary.**
  This is the irreducible judgment in the whole skill: what mattered this
  session, what the user actually decided, which problems were real. A script
  can enforce that the five headings exist and are non-empty (proposal #1); it
  can never decide what belongs under them. `checkpoint.py:365-414`'s
  auto-generated fallback is precisely what the degraded version looks like —
  commit counts standing in for meaning — which is why the missing-summary path
  should become an error (finding at `:806-809`) rather than a better generator.
- **`checkpointing/SKILL.md:41` step 6 — whether a decision belongs in
  DESIGN.md.** Durability is a judgment call; `/design-tracker` already owns
  the mechanical write via `update_design.py`.
- **`checkpointing/SKILL.md:63-65` — the approval decision itself.** Automate
  the *apply mechanism* (proposal #3), never the consent. Destructive moves of
  research notes must stay gated on an explicit human yes.
- **`catchup/SKILL.md:80-86` Phase 2, and `guide-template.md:29` — "3–7
  thematic bullets grouping recent commits".** Grouping 100 commits into
  themes, ranking the top five design decisions, and judging which sections are
  worth including for *this* reader is synthesis. Proposal #5 deliberately takes
  the assembled prose as input rather than generating it.
- **`context-loader/SKILL.md:61-66` step 3 and the confirmation at `:84-89`.**
  Whether the loaded rules were actually *understood* and applied cannot be
  asserted by a subprocess. Scripting the read order (already done) is the
  correct boundary; scripting the reading is theatre. Only the mechanical half
  of the confirmation — echoing `missing`/`warnings` verbatim — should be
  tightened.
- **`refresh_guard.py:96-110` `active` heuristic for research notes.** Deciding
  a research thread is finished is human judgment; the current
  stem-appears-in-STATE.md heuristic is a *suggestion generator* and should be
  labelled as such in the JSON rather than made authoritative. Note that with
  the real repo's empty research directory this path is currently untested in
  practice (verified: `research_notes: []`).
