# Skill Audit — project group

Scope: `init`, `design-tracker`, `codex-system`.
Standard audited against: `.claude/skills/_shared/README.md` (Automation Boundary,
Shared Script Contract, Writer Safety Contract), `.claude/rules/agent-state.md`,
`.claude/rules/codex-delegation.md`, `.agents/AGENTS.md`.

All behavioural claims below were reproduced against fixture directories under the
session scratchpad, never against the real project. Reproduction commands are quoted
inline.

---

## init

Files: `.claude/skills/init/SKILL.md`, `.claude/skills/init/detect_stack.py`.

| Severity | Rubric # | Location | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 2 | `detect_stack.py:173-178` (`_safe_read`) | `except OSError` does not catch `UnicodeDecodeError` (a `ValueError`). A single non-UTF-8 manifest crashes the tool with a Python traceback, **no JSON on stdout**, exit `1`. `SKILL.md:31-32` documents exit `1` as "bad arguments" and only exit `2` as "stop and repair", so the agent sees a stack trace at a step whose contract says stdout is JSON. Reproduced: fixture `pyproject.toml` written as `b'[project]\nname="caf\xe9"\nruff\n'` → `UnicodeDecodeError ... exit=1`. Same hole in `_npm_scripts` is closed (`:107-110` catches `ValueError`), so this is an inconsistency, not a deliberate choice. | Catch `(OSError, UnicodeDecodeError)` in `_safe_read`; surface the unreadable path as a `warnings` entry in the JSON rather than aborting. |
| HIGH | 5, 4 | `SKILL.md:39-52` (DESIGN.md) and `SKILL.md:54-62` (STATE.md) | Both user-owned documents are written by hand with Edit/Write. That forfeits all four Writer Safety guarantees (`_shared/README.md:72-83`): no typed input, no dry-run preview, no atomic replace, no concurrent-modification hash guard. `/init` is the *only* writer of `## Repository Identity` per `.claude/rules/agent-state.md:11`, and no helper exists for it: `append_state_block.py` only appends `## Current *` blocks (`:250-251`) and its `validate_structure` (`:97-103`) checks only `# Agent State` and `## Progress Tracker` — `## Repository Identity` and `## Main Agent` are never validated by anything. So `/init` can silently drop or duplicate the sections `SKILL.md:56-57` tells it to preserve, and design-tracker running concurrently (it is declared PROACTIVE) can be clobbered. | Add a typed writer for the identity body (new `init/write_identity.py`, or a `--section repository-identity` replace mode on `append_state_block.py`) and route step 3's DESIGN.md population through `update_design.py --input` once the typed table support below exists. |
| HIGH | 8 | `SKILL.md:31-32` vs `detect_stack.py:159-170` | SKILL.md states exit `2` means "the root bootstrap, **Claude discovery symlink**, or shared state is invalid". `detect_agent_bootstrap` checks only `CLAUDE.md -> AGENTS.md`. The discovery symlinks that AGENTS.md:114-119 calls load-bearing — `.claude/agents` and `.claude/skills` — are verified only by `scripts/check.sh:317-322`, which `/init` never runs. A dangling `.claude/skills` link disables *all* native skill auto-discovery (including design-tracker's proactive activation), yet `detect_stack.py` reports `agent_bootstrap` all-true and exits `0`, and `/init` reports success. | Extend `detect_agent_bootstrap` with `claude_agents_link` / `claude_skills_link` checks mirroring `check.sh:317-322`, or have step 1 also run `scripts/check.sh`. Until then, correct the SKILL.md sentence — it currently overstates the check. |
| MED | 2 | `detect_stack.py:206` and `:181-195` | The success path prints a report with **no `ok` field**, while every error path prints `{"ok": false, ...}` (`:44`). The exit-`2` path prints the same shape with no `error` field either. `_shared/README.md:56-57` requires that "a failure surfaces as a JSON field *and* a non-zero exit code"; here the only machine-readable failure signal is nested booleans under `agent_bootstrap`. A caller doing the uniform `ok` check every other helper supports reads `None` and cannot distinguish success from bootstrap failure. | Emit `ok`, and on the exit-2 path an `error` naming the failed marker(s). |
| MED | 2 | `detect_stack.py:202` (`--project-root`, no validation) | `--project-root` is never existence-checked, so a typo'd path, a nonexistent path, and a path pointing at a *regular file* all produce the identical "everything absent / everything false" report with exit `2`. Reproduced: `--project-root <missing dir>` and `--project-root <a file>` gave byte-identical output. Contrast `codex_consult.py:206-209`, which validates `--cwd` up front precisely so "a bad path is never misread" as a different failure. | Validate `--project-root.is_dir()` and return exit `1` with an `error` field. |
| MED | 2 | `detect_stack.py:93-94` | `if "ty" in text` is a bare substring test over the whole manifest, so any pyproject containing `typing`, `types-`, `stability`, … fabricates the command `uv run ty check src/`. Reproduced: `dependencies = ["typing-extensions"]` → `{'typecheck': 'uv run ty check src/'}`. `SKILL.md:30` instructs the agent to "use its … commands" fields, so a command that does not exist in the project is copied into DESIGN.md as fact. | Match tool names on word boundaries / dedicated table keys (`[tool.ty]`, `[dependency-groups]` entries) instead of substring containment. |
| MED | 2 | `detect_stack.py:133` and `:141` | `re.search(r"dependencies\s*=\s*\[(.*?)\]", ..., DOTALL)` is non-greedy, so the match ends at the **first** `]` in the list. A dependency with an extras marker truncates everything after it. Reproduced: `["fastapi", "uvicorn[standard]", "httpx"]` → `["fastapi", "uvicorn"]`; `httpx` is silently lost and nothing in the JSON says the list is partial. The same regex also matches `optional-dependencies`/`[dependency-groups]` when either precedes `[project].dependencies`. | Parse with `tomllib` (stdlib since 3.11, so the standard-library-only rule holds) and read `project.dependencies` by key. |
| MED | 2 | `detect_stack.py:96` | `if package_json.exists() and not commands` — in a Python+Node repo, any Python command found first suppresses **all** npm commands. Reproduced: with `ruff` in pyproject, a `package.json` carrying `lint`/`test` scripts yielded only the `uv run ruff …` pair; removing `ruff` made the npm pair appear. A polyglot repo silently gets half its quality gates recorded. | Merge under namespaced keys (`lint`, `lint_js`, …) rather than skipping. |
| MED | 7 | `SKILL.md:64-68` (step 5) | Completion is declared by a prose report. Nothing re-validates that DESIGN.md still has its fixed headings, that STATE.md still has `## Main Agent` / `## Progress Tracker` / `## Repository Identity`, or that `detect_stack.py` now exits `0`. Both documents were just edited freehand (finding 2), which is exactly when a structural check is worth the most. | Add a closing gate: `validate_doc.py --contract design-doc --file .claude/docs/DESIGN.md`, the same for a `state-doc` contract, plus a re-run of `detect_stack.py`. Report the JSON verdicts. |
| LOW | 8 | `SKILL.md:56-62` vs `.claude/STATE.md:9` | SKILL.md says "Keep the body to one identity sentence plus this pointer". The live file's body also contains `<!-- Managed by /init. Re-run /init to refresh. -->`, which the literal instruction deletes. | Include the marker in the prescribed body, or have the typed writer preserve it. |
| LOW | 2 | `detect_stack.py:57`, `:189` | `BUILD_MANIFESTS` (`Makefile`, `Dockerfile`) is detected and then unused — no command inference, and `:189` filters `manifests` to present-only entries, so "checked and absent" is indistinguishable from "not checked". | Either use them for command inference or drop them; keep all checked keys in the output with explicit `false`. |

---

## design-tracker

File: `.claude/skills/design-tracker/SKILL.md`. No bundled script.

**Is "no bundled script" correct?** Mostly yes — the skill correctly delegates its
one mechanical step to `_shared/update_design.py`, and its judgment steps (is this a
decision? which section?) must stay prose. But the delegation is incomplete: the
topic table promises typed table targets the script does not implement, and the
success check the skill prescribes does not distinguish "written" from "nothing
happened". Both are below.

| Severity | Rubric # | Location | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 2 | `SKILL.md:84` ("Verify `"ok": true`") vs `update_design.py:305-316` | `result: "no-op"` returns `ok: true` and exit `0`. So the prescribed success check passes when **nothing was written**: a duplicate decision (skipped at `:191-196`), or a `section_updates` entry whose `content` is empty (skipped at `:212-213`). Reproduced: re-applying the same decision → `{"ok": true, "result": "no-op", "skipped_duplicates": 1}`, exit 0; empty content → `{"ok": true, "result": "no-op"}`, exit 0. The agent then reports "recorded to Key Decisions" per `SKILL.md:86-90` while DESIGN.md is unchanged. The script is contract-compliant (`_shared/README.md:60` defines `0` as `ok / preview / no-op`); the SKILL.md verification instruction is the defect. | Change the gate to: `result == "applied"` **and** (`decisions_appended > 0` or `sections_updated` non-empty); report `skipped_duplicates` explicitly. Optionally add `--require-change` to `update_design.py` so a no-op exits non-zero when the caller expected a write. |
| HIGH | 1 | `SKILL.md:49-52` vs `update_design.py:197-199` and `:208-231` | The topic table routes four topics to *tables* — 機能要件 (ID/要件/優先度/備考), 非機能要件 (カテゴリ/要件/指標), Agent Roles, 技術選定 (領域/採用技術/理由/代替案) — but only `Key Decisions` has a typed path. The other four must go through free-text `section_updates.content`, where the agent hand-writes the pipes. Two concrete corruptions, both reported as `ok: true, result: "applied"`: (a) **no cell escaping** — `_escape_cell` is applied to decisions only (`:197-199`); a hand-written row `\| FR-2 \| Support A\|B routing \| High \| note \|` splits into 5 cells (reproduced); (b) **wrong insertion point** — `_find_section_range` returns the next `## ` heading (`:151-155`) and content is inserted immediately before it (`:229-230`), so with the template's trailing blank line the new row lands *after* a blank line, orphaned from the table it belongs to, and the following `## 非機能要件` heading is left with no preceding blank line. Reproduced output: `\| FR-1 \| \| \| \|` / blank / `\| FR-2 …\|` / `## 非機能要件` on the next line. This is a determinism gap of exactly the kind `_shared/README.md:19-20` names: one correct output shape, currently produced by prose. | Extend `update_design.py` with typed keys (`requirements`, `nfr`, `tech_choices`, `agent_roles`) that reuse the decisions path: locate the table by its header row, escape every cell, insert after the last row. Then remove the hand-written-row instruction from the topic table. Separately, make the section-append path skip trailing blank lines and guarantee one blank line before the following heading. |
| HIGH | 9 | `SKILL.md:3` and `:19-25` vs `.claude/hooks/agent-router.py:52-53, 76-78` | The skill's core promise ("PROACTIVELY … Do NOT wait for user to ask") is enforced by nothing but the description-based model invocation. No hook references design-tracker anywhere in the repo (`grep -rn design-tracker` finds only README, AGENTS.md:60, catchup, checkpointing, check.sh, DESIGN.md:4 — no hook, no settings entry). Worse, the *same trigger words* are claimed by a competing route: `agent-router.py` puts `設計` / `design` / `architecture` in `CODEX_TRIGGERS` and, on a UserPromptSubmit match, injects "this task may benefit from Codex CLI" (`:238-251`). And `check-codex-before-write.py:32` lists `DESIGN.md` as a design indicator, so editing DESIGN.md produces a *Codex* nudge (`:119-135`) — never a design-tracker nudge, and never a block on the freehand edit. So the observable effect of a design conversation is a push toward Codex, not toward recording the decision. | Add a design-tracker branch to `agent-router.py` (checked before the broad Codex triggers, in the same way `CODEX_PLUGIN_TRIGGERS` is ordered ahead of them at `:186-194`) that names the skill and the `update_design.py` path. Separately, make `check-codex-before-write.py` (or a dedicated PreToolUse matcher) *deny* direct Edit/Write on `.claude/docs/DESIGN.md` and `.claude/STATE.md` with a message pointing at the writer scripts — that is what turns the Writer Safety Contract from opt-in into enforced. |
| MED | 3 | `SKILL.md:60` and `:76-78` | The input JSON path is the hard-coded global `.claude/logs/design-input.json`. For a skill explicitly declared to run proactively — i.e. concurrently with other work, possibly in a subagent — two overlapping recordings overwrite each other's input file, and `update_design.py`'s hash guard (`:345-352`) protects DESIGN.md but not the input. `workspace.py:34` `SKILL_CHOICES` has no `design-tracker` entry, so there is no deterministic per-invocation path to use instead, and the skill derives the path by prose. | Add a `design-tracker` entry to `workspace.py` (e.g. `design_input: ".claude/logs/design-input-{slug}.json"`) and have the skill resolve it, exactly as `feature`/`troubleshoot` do for `state_input`. |
| MED | 4 | `validate_doc.py:99-122` | DESIGN.md's structure is unvalidated. The `CONTRACTS` registry has `work-log`, `lib-doc`, `spike-report`, `bug-report` — no `design-doc`. `update_design.py` spot-checks only the Key Decisions header (`:103-125`) and the single heading being targeted (`:138-155`); a DESIGN.md that has lost 背景・目的, スコープ, or 制約 entirely is never reported by anything. The file's own comment says adding a fixed-heading contract "is a one-line addition here" (`:98`). | Add `design-doc` (the nine `## ` headings of `.claude/docs/DESIGN.md`) and `state-doc` (`Main Agent`, `Repository Identity`, `Progress Tracker`) contracts, and have design-tracker run the `design-doc` check as its closing gate. |
| LOW | 8 | `SKILL.md:29` vs `_shared/README.md:4` | `_shared/README.md` states "Skills must never invoke other skills", yet `.claude/docs/DESIGN.md:4` and `.claude/skills/checkpointing/SKILL.md:42` both describe design-tracker as invoked from `/checkpointing`. design-tracker's own documented trigger surface therefore includes a path the shared contract forbids. | Reword the checkpointing/DESIGN.md references to "records decisions via `update_design.py`" rather than skill-to-skill invocation, or relax the README rule deliberately. |
| LOW | 1 | `SKILL.md:35` (step 1 "Read existing DESIGN.md") | Reading the whole document into context is unnecessary for the mechanical append — `update_design.py` locates the table and heading itself — and it costs main-agent context on every proactive activation. | Keep the read only for the judgment step (has this already been decided?), or replace it with a targeted grep of the Key Decisions table. |

**Correctly scripted, do not change:** the decision *date*. `SKILL.md`'s example JSON
omits `date`, and `update_design.py:188` fills it from `datetime.now(tz=UTC)`. This is
exactly the hand-derived-date failure (rubric 3) already closed.

---

## codex-system

Files: `.claude/skills/codex-system/SKILL.md`, `references/*.md`. No bundled script —
**correct**: the skill's mechanical step is invoking an external process, and that is
owned by `_shared/codex_consult.py`, which every reference file calls (`agent-prompts.md:4`,
`delegation-patterns.md:38,54,75,98,122`, `code-review-task.md:90`, `refactoring-task.md:86`,
`troubleshooting.md:3,48`). No reference shells out to `codex exec` directly.

**Priority check — documented contract vs. `codex_consult.py` reality.** I diffed
`SKILL.md:46-54` against `python3 .claude/skills/_shared/codex_consult.py --help` and
the source. Result: the flag list, the three sandbox values, all twelve JSON fields
(`ok, exit_code, model, sandbox, write_access, timed_out, duration_sec, response_file,
stderr_file, response_chars, response_head, error` — `codex_consult.py:303-318`), the
`~400`-char `response_head` preview (`:315`), the `[a-z0-9-]+` label rule (`:42`), the
600 s timeout default (`:40`), the `$CODEX_MODEL` → `gpt-5.6-sol` fallback (`:39, :229-230`),
the `--config` sandbox/approval denylist (`:50-51, :106-110`), and all four exit codes
(`:53-56`) **match exactly**. `scripts/check.sh:131-143` additionally pins
`DEFAULT_MODEL` to `settings.json`'s `CODEX_MODEL`. One omission only, below.

| Severity | Rubric # | Location | What breaks in practice | Proposed fix |
|---|---|---|---|---|
| HIGH | 7 | `SKILL.md:93-112` ("Having Codex Implement Code") and `:56-85` (Subagent Pattern) | The Guardrails are absent from the one document that is the SSOT for *how* to consult (`codex-delegation.md:59` designates this skill for exactly that). The implementation recipe grants `--sandbox danger-full-access` and ends at the wrapper call: no acceptance-check execution, no `git diff --stat` / `git diff` inspection, no cheating-pattern rejection list, no re-delegate-once-then-halt protocol — all of which `cli-execution.md:107-137` and `codex-delegation.md:65-89` declare mandatory. The Subagent Pattern is worse than silent: `SKILL.md:83-84` instructs "when ok is true, read response_file … Return CONCISE summary", i.e. accept the callee's self-report and summarise it — precisely what `cli-execution.md:86-89` forbids ("a delegated CLI is never trusted on its self-report"). Note `ok: true` from the wrapper means only that `codex exec` exited 0 (`codex_consult.py:299`); it says nothing about whether the change is correct. | Add a "Verify Before Trusting" section immediately after the implementation recipe: run `bash .claude/skills/_shared/verify.sh`, inspect `git diff --stat` and `git diff`, screen for the three cheating patterns, and on failure follow the re-delegate-once protocol. Link `cli-execution.md#guardrails-completion-verification` from `SKILL.md:39` so the delegation-policy pointer and the verification pointer sit together. Amend `:83-84` to require verification before the summary. |
| MED | 6, 8 | `SKILL.md:181-240` (plugin commands) | Thirteen `/codex:*` slash commands are documented with concrete flags (`--effort medium`, `--model gpt-5.5-mini`, `--enable-review-gate`) for an external plugin (`openai/codex-plugin-cc`) with no version pin, and nothing in the repo verifies it is installed — `grep -rn` finds no reference to the plugin outside this SKILL.md. Two consequences: the decision table at `:230-240` routes real work (pre-ship review, investigation, background jobs) to commands that may not exist in the session; and every such command runs Codex **outside** the wrapper, so there is no `.claude/logs/codex/` response/stderr capture and no `cli-tools.jsonl` entry — `log-cli-tools.py:26` keys on the wrapper filenames (`WRAPPER_CLI = {"codex_consult.py": "codex", "cli_consult.py": None}`), so plugin-driven delegations are invisible to the audit trail that `cli-execution.md:90-92` promises "any runtime can read". | State the availability precondition once ("run `/codex:setup` first; if the plugin is absent, use `codex_consult.py`"), and note in the decision table that plugin routes are not captured in `.claude/logs/` or `cli-tools.jsonl`. Prefer wrapper routes wherever both work. |
| MED | 8 | `SKILL.md:46` (usage synopsis) | `--project-root` is missing from the documented invocation, though the script implements it (`codex_consult.py:180-185`) and `_shared/README.md:59-61` mandates it on *every* bundled helper precisely so a skill can be exercised against a fixture directory. An agent auditing or testing the wrapper from this skill cannot discover the flag. | Add `[--project-root DIR]` to the synopsis line. |
| MED | 6 | `SKILL.md` (whole file) — no mention of `cli_consult.py` | `cli_consult.py` was added after this SKILL.md was written. The cross-CLI story now lives in `.agents/AGENTS.md:42-95` and `AGENTS.md:123-126` only. But `cli-execution.md:59` points *back* at `codex-system/SKILL.md` as the SSOT for wrapper "flags and exit codes", so the skill is the natural landing place — and an agent that opens it to learn "how to consult another agent" finds only Codex, with no signpost. Keeping Codex's sandbox/`--config` semantics in a Codex-specific skill is right; having no pointer is not. | One line under "How to Consult": peer CLIs (Claude Code, Gemini) go through `_shared/cli_consult.py --cli {claude,gemini}`, read-only unless `--write-access`; rules in `.agents/AGENTS.md`. Verified against `cli_consult.py --help`: `--cli {claude,gemini}`, `--write-access`, `--resume` (claude only, `:287-294`), `--cli-arg`, 900 s default (`:50`), same four exit codes. |
| LOW | 7 | `SKILL.md:18` (Preflight) | "Update CLIs before each session — `claude update && npm install -g @openai/codex@latest`" is an unbounded, network-mutating global install prescribed as a routine step, with no verification of the outcome and no fallback if it fails mid-session. Declared SSOT for other skills, so the cost is repeated. | Downgrade to a version *check* (`codex --version` compared against a recorded floor) and make the upgrade conditional and explicitly user-approved. |
| LOW | 8 | `.claude/rules/codex-delegation.md:55` | Cited as "Detailed templates: `@.claude/docs/CODEX_HANDOFF_PLAYBOOK.md`". The file exists (`.claude/docs/CODEX_HANDOFF_PLAYBOOK.md`), so this is not drift — but the skill's own `## References` list (`SKILL.md:248-257`) omits it, splitting the template set across two documents. | Add the playbook to the skill's References, or fold its templates into `references/`. |

---

## Proposed new or extended scripts

1. **Extend `_shared/update_design.py` with typed table writers.** New input keys
   `requirements`, `nfr`, `tech_choices`, `agent_roles`, each locating its table by
   header row and inserting escaped cells after the last row — the same code path
   `decisions` already uses. Justification: eliminates the highest-impact determinism
   gap in this group; four of design-tracker's nine documented targets currently
   require hand-written markdown and demonstrably corrupt the document.
2. **Extend `_shared/update_design.py`: correct section-append placement and add
   `--require-change`.** Skip trailing blank lines when computing the insertion point,
   guarantee one blank line before the following heading, and let the caller declare
   that a no-op is a failure. Justification: closes both the orphaned-row corruption
   and the `ok: true` / nothing-written silent success.
3. **Extend `_shared/validate_doc.py` with `design-doc` and `state-doc` contracts.**
   Justification: DESIGN.md and STATE.md are the two documents this group mutates and
   the only skill deliverables with no structural validator; the registry is designed
   for one-line additions (`validate_doc.py:98`).
4. **New typed writer for `## Repository Identity`** (`init/write_identity.py`, or a
   `--section` replace mode on `append_state_block.py`). Justification: `/init` is the
   sole writer of a user-owned section and currently reaches it with Edit/Write, which
   is the one document mutation in this group with no dry-run, no atomic replace, and
   no concurrent-modification guard.
5. **Harden `init/detect_stack.py`**: validate `--project-root`; emit `ok` and `error`;
   catch `UnicodeDecodeError`; word-boundary tool detection; `tomllib` for dependencies;
   merge npm commands instead of skipping them; verify the `.claude/agents` and
   `.claude/skills` discovery links. Justification: every one of these is a reproduced
   silent failure or fabricated output feeding straight into DESIGN.md.
6. **Add a `design-tracker` entry to `_shared/workspace.py`.** Justification: the skill
   runs concurrently by design and currently derives one global input path by prose.
7. **New `_shared/verify_delegation.py`** (or a `--delegation` mode on `verify.sh`):
   after any write-access Codex/peer-CLI call, run the quality gates, capture
   `git diff --stat` and `git diff`, and grep the diff for the enumerated cheating
   patterns (deleted/skipped tests, weakened assertions, bare `except: pass`,
   `NotImplementedError`/`TODO` stubs), emitting one JSON evidence bundle. Justification:
   the Guardrails are currently unexecutable prose spread over two rule files; this makes
   the *evidence collection* deterministic and gives codex-system something to gate on.
8. **Add a design-tracker branch to `.claude/hooks/agent-router.py`, and a PreToolUse
   deny for direct Edit/Write on `DESIGN.md` / `STATE.md`.** Justification: the skill's
   proactive promise is enforced by nothing today and its trigger words are actively
   claimed by the Codex route; the deny is what makes the Writer Safety Contract binding
   rather than advisory.

---

## Keep as prose

- **Whether something *is* a design decision** (design-tracker `SKILL.md:19-25`). Novel,
  contextual judgment; a keyword rule would both over- and under-fire. Only the
  *recording* has one correct shape.
- **The conversation-topic → DESIGN.md section mapping** (`SKILL.md:45-55`). The table is
  the right artefact: it constrains the choice without pretending the choice is mechanical.
  Script the row *rendering*, not the routing.
- **Prompt body composition** for Codex (`SKILL.md:49`, `:56-85`, all of `references/`).
  Objective / Constraints / Relevant files / Acceptance checks / Output format is content,
  explicitly on the markdown side of the Automation Boundary (`_shared/README.md:16`).
- **Mode, sandbox, and route selection** (`SKILL.md:114-121`, `:230-240`; `codex-delegation.md:23-46`).
  Deciding read-only vs. danger-full-access is the security judgment the wrapper exists to
  make *visible*, not to make for the caller.
- **Interpreting Codex's answer, and the final accept/reject verdict on a delegated
  change.** `verify_delegation.py` should collect evidence and never auto-accept: the
  cheating-pattern list is heuristic, and a legitimate test deletion exists.
- **`/init` step 2 (asking the user for purpose and conventions) and step 5's judgment
  about which `.claude/rules/` are irrelevant** (`SKILL.md:34-37`, `:66-67`). Both are
  irreducibly interactive; step 5 correctly forbids acting without approval.
- **Counter-check on the user's premise:** `detect_stack.py` is where "script it" has
  already been taken one step too far. The false `uv run ty check src/` command
  (`:93`) and the truncated dependency list (`:133`) are a script *guessing* and being
  believed, which is worse than prose because the output looks authoritative in JSON.
  The fix is less inference, not more: report the evidence found (which manifest, which
  key, which line) and let the agent decide what to write. Determinism is only valuable
  where a correct answer exists; where it does not, a script converts uncertainty into a
  confident wrong fact.
