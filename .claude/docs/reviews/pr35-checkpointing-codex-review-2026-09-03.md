# PR #35 (merge `9d93caf`) — post-merge review: checkpointing fast retrieval + codex-delegation rewrite

Date: 2026-09-03
Reviewer: `general-purpose-opus`.
**Codex could not be consulted — see section 6.** The caller required Codex as reviewer
of record; that requirement is unmet and this report is not a substitute for it. Every
judgment below is therefore backed by a *mechanical* check (PyYAML round-trip,
end-to-end runs against the real script, the repo's own test suite) rather than by a
second model's opinion.
Scope reviewed: `.agents/skills/checkpointing/{SKILL.md,checkpoint.py,references/formats.md,refresh_guard.py}`,
`tests/test_checkpoint.py`, `.agents/rules/codex-delegation.md`.
Explicitly out of scope: `.agents/hooks/**` (owned by a parallel review).

**Verdict: defects found** (1 medium cross-skill regression, 1 medium doc/behaviour
mismatch, 3 low correctness/robustness items, 1 test-coverage gap). Nothing found is a
data-loss or corruption bug in the happy path; the feature works and is idempotent.

---

## 1. What landed

`checkpoint.py` gained a "fast retrieval" layer:

- `_slugify` / `derive_slug` (`checkpoint.py:543,554`) — session slug from `--label`,
  else dominant conventional-commit type + top keywords, else `session`.
- `_sanitize_tag` / `derive_tags` (`:595,600`) — semantic tags from commit types,
  top-level directories touched, `testing`/`skills`/`hooks`/`rules` markers, `codex`,
  `agent-teams`, `team-{name}`.
- `derive_headline` (`:640`) — first 3 commit subjects, whitespace-collapsed.
- `_yaml_quote` / `build_frontmatter` / `parse_frontmatter` (`:651,657,691`).
- `_escape_table_cell` / `_index_row` / `compose_index_md` (`:716,721,749`).
- `generate_checkpoint` now prepends the frontmatter; `main` composes and writes
  `.agents/checkpoints/INDEX.md` under the atomic-replace + content-hash guard.

`refresh_guard.py` was **not** touched by `9d93caf` (`git show 9d93caf --stat` lists no
such path) and operates exclusively on `.agents/STATE.md` — see its module docstring
and `STATE_HEADING`/`CURRENT_BLOCK_RE` at `refresh_guard.py:63-66`. It never reads a
checkpoint file, so "consistency with the new frontmatter format" is a non-question:
it is out of the blast radius by construction.

`codex-delegation.md` gained a "when in doubt, ask Codex" principle plus an explicit
reconciliation note with `delegation.md`, five new consult triggers, and a
"Hook-Detected Triggers" table.

---

## 2. Acceptance checks (verbatim)

### 2.1 `python3 -m py_compile`

```
$ for f in .agents/skills/checkpointing/checkpoint.py .agents/skills/checkpointing/refresh_guard.py; do python3 -m py_compile "$f" && echo "OK $f"; done
OK .agents/skills/checkpointing/checkpoint.py
OK .agents/skills/checkpointing/refresh_guard.py
```

### 2.2 `bash .agents/check.sh`

```
PASS: INDEX.md links resolve
PASS: Tier IDs present in tiers.md
PASS: Model coherence
PASS: .agents template paths in SAFE_DIRS
PASS: Root orchestration contract
PASS: Bootstrap references
PASS: Native runtime boundaries
PASS: Skill scripts and docs in sync

Results: 8 passed, 0 failed
```

### 2.3 Checkpointing tests

Exact command (`pytest` is not importable by the bare `python3`; the repo's own runner
resolves it through `uv`):

```
$ python3 .agents/skills/_shared/run_tests.py --expect pass \
    --target tests/test_checkpoint.py \
    --target tests/test_collect_repo_state.py \
    --target tests/test_refresh_guard.py --label pr35-review
{"expected": "passed", "observed": "passed", "runner": "uv",
 "command": ["uv", "run", "pytest", "-p", "no:cacheprovider", "tests/test_checkpoint.py",
             "tests/test_collect_repo_state.py", "tests/test_refresh_guard.py"],
 "exit_code": 0, "summary": "75 passed in 13.88s", "failed_tests": [],
 "coverage_percent": null, "min_coverage": null,
 "log_file": ".agents/logs/pr35-review.log", "ok": true}
```

### 2.4 End-to-end run in a scratch repository

Scratch root: `/tmp/claude-0/-home-user-claude-code-orchestra/c862d471-81ee-5414-86f0-bd5b6c5db4a1/scratchpad/e2e`.
The real `.agents/checkpoints/` was never written to.

Run 1, commit subject `feat(core): add "quoted" | piped: colon thing`:

```
{"ok": true, "result": "applied",
 "checkpoint_path": ".agents/checkpoints/2026-07-25-100000.md",
 "index_path": ".agents/checkpoints/INDEX.md",
 "slug": "feature-core-quoted-piped", "tags": ["feature"], ...}
```

Frontmatter written:

```yaml
---
id: feature-core-quoted-piped-2026-07-25-100000
timestamp: 2026-07-25-100000
branch: "feature/adversarial"
slug: feature-core-quoted-piped
summary: "add \"quoted\" | piped: colon thing"
tags: [feature]
commits: 1
files_changed: 0
codex_consultations: 0
agent_teams: 0
---
```

Run 2, `--label 'weird | label: "x"'` and a >72-char commit subject containing `|`,
`:` and `"`:

```yaml
---
id: weird-label-x-2026-07-26-100000
timestamp: 2026-07-26-100000
branch: "feature/adversarial"
slug: weird-label-x
summary: "second | commit: with \"quotes\" and a very long subject line that goes on and on and on beyond seventy two characters for truncation; add \"quoted\" | piped: colon thing"
tags: [bugfix, feature]
commits: 2
...
---
```

Resulting `INDEX.md`:

```markdown
| Timestamp | Checkpoint | Branch | Tags | Stats | Summary |
|---|---|---|---|---|---|
| 2026-07-26-100000 | [weird-label-x](2026-07-26-100000.md) | feature/adversarial | bugfix, feature | 2c/0f | second \| commit: with "quotes" and a very long subject line that goes... |
| 2026-07-25-100000 | [feature-core-quoted-piped](2026-07-25-100000.md) | feature/adversarial | feature | 1c/0f | add "quoted" \| piped: colon thing |
```

Idempotency, regenerating twice and comparing with what `--apply` wrote:

```
recompose stable: True
matches disk    : True
```

So `|` escaping, `"` escaping, truncation and byte-stable regeneration all hold for
the stated adversarial summary. **This part is clean.**

---

## 3. Answers to the framed questions

### Q1. Is the emitted YAML guaranteed well-formed for adversarial input?

**No — but only through the `tags:` flow sequence.** Verified with PyYAML against
`build_frontmatter` output:

| Input | Emitted | `yaml.safe_load` |
|---|---|---|
| commit subject with `"`, `:`, `|`, leading `-`, newline, very long | `summary: "…"` (escaped, newline collapsed by `derive_headline`) | **ok** |
| branch `fix/"weird"\path` | `branch: "fix/\"weird\"\\path"` | **ok**, round-trips exactly |
| zero commits / empty repo | `summary: "no commits"`, `tags: []`, `commits: 0` | **ok** |
| Japanese-only / emoji-only summary or label | slug falls back to `session` | **ok** |
| tag `#weird` (e.g. a top-level directory named `#weird`) | `tags: [feature, #weird]` | **FAIL** — `while parsing a flow sequence`; `, #` starts a YAML comment and the sequence is never closed |
| tags `&anchor`, `*alias` | `tags: [&anchor, *alias]` | **FAIL** — `found undefined alias 'alias'` |
| tag `team-a: b` (from an Agent Teams `name`) | `tags: [team-a: b]` | parses, but as `[{'team-a': 'b'}]` — a mapping, not the string |
| tag `{x}` | `tags: [{x}]` | parses as `[{'x': None}]` |
| `--label No` | `slug: no` | parses as `slug: False` (YAML 1.1 boolean) |

`_yaml_quote` / `parse_frontmatter` round-trip correctly for backslash/quote
combinations (`a\"`, `\\`, `"\`, `\\"` all verified) — the ordering of the two
`.replace()` calls happens to be safe.

### Q2. Is `INDEX.md` regeneration idempotent and non-lossy?

**Idempotent: yes**, verified byte-identical (above). Fully regenerated from disk, so a
deleted checkpoint disappears (pinned by `test_the_index_is_rebuilt_not_appended`).

**Non-lossy: mostly.** A frontmatter-less checkpoint still gets a row keyed on its stem
(pinned by test). A hand-edited `INDEX.md` is *not* silently overwritten — the
`atomic_replace` content-hash guard aborts with exit 3; but see defect D4 for the
ordering consequence.

**Malformed frontmatter is not handled.** A checkpoint whose frontmatter opens with
`---` and never closes makes `parse_frontmatter` (`checkpoint.py:703-704` — the loop
only `break`s on a closing fence, and falls through to the end of file otherwise) read
the entire document body as key/value pairs. Reproduced:

```
| 2026-01-01-000000 | [broken] (x.md](2026-01-01-000000.md) | a\|b | a, b, c, d, e | 999c/0f | injected \| row |
```

`|` is correctly escaped everywhere, including in the link label — but `]`, `[` and `(`
are not, so the markdown link is destroyed and the label leaks into the cell (D3).
Row count is preserved; nothing is dropped.

### Q3. Slug/tag collision in the same timestamp bucket?

**No, and no silent overwrite.** `main` (`checkpoint.py:1515-1524`) refuses to proceed
when `.agents/checkpoints/{timestamp}.md` already exists, emitting
`"… already exists; pass a distinct --now"` and exiting 3 before anything is written.
The slug is metadata only; `id: {slug}-{timestamp}` is unique via the timestamp; slugs
are never used as a dict key or a filename. The `pending`-wins-over-disk merge in
`compose_index_md` (`:757-759`) is only reachable after that collision check passed,
i.e. when no on-disk file exists for that stem.

### Q4. Does `codex-delegation.md` contradict `delegation.md`?

**No hard contradiction.** The merge explicitly reconciled them: `codex-delegation.md:9-14`
subordinates itself to `delegation.md` ("it does not override that file's Self-Handle
List or its over-delegation anti-pattern — a known one-line edit stays a one-line
edit"), and its "Do NOT delegate to Codex" list (`:57-67`) routes routine work to
`general-purpose-sonnet` and analysis/research to `general-purpose-opus`, matching
`delegation.md`'s Route Selection table.

Two soft tensions, neither introduced by this PR and neither worth a fix commit:

- `codex-delegation.md:29` "Default to Codex-first delegation for development tasks."
  is broader than `delegation.md`'s route table, which sends implementation to
  `general-purpose-sonnet` / `general-purpose-opus` and reserves Codex for
  "Architecture, planning, decomposition, complex algorithms, code review". Present
  verbatim in the pre-merge baseline (`git show 31ef837:.agents/rules/codex-delegation.md`
  line 29) — pre-existing, and the "Do NOT delegate" list below it resolves it in
  practice.
- The scope note says "a known one-line edit"; `delegation.md`'s Self-Handle List item 2
  says "roughly 20 lines or fewer". Narrower phrasing, not a conflicting rule.

The new hook table's thresholds were checked against the real hooks:
`post-implementation-review.py:57-58` has `MIN_FILES_FOR_REVIEW = 2` and
`MIN_LINES_FOR_REVIEW = 50`, matching the "2+ files or 50+ lines" row; all six named
hook files exist in `.agents/hooks/`. One row is wrong — see D2.

### Q5. Is `refresh_guard.py` consistent with the new frontmatter?

**Out of scope by construction, so trivially consistent.** It was not modified by
`9d93caf`, it reads and writes only `.agents/STATE.md`, and it contains no checkpoint
path, glob, or frontmatter handling. `tests/test_refresh_guard.py` passes unchanged.

### Q6. Downstream regressions from prepending frontmatter?

**Yes — one, in the catchup skill.** See D1.
`.agents/skills/context-loader/load_context.py:69` keys on the `PROGRESS.md` entry
header regex, not the checkpoint body, and is unaffected.
`get_checkpoint_files` (`checkpoint.py:1043-1047`) filters on `CHECKPOINT_STEM_RE`, so
`INDEX.md` is correctly never treated as a checkpoint and never enters `PROGRESS.md`
(pinned by `test_the_index_is_never_mistaken_for_a_checkpoint`).

### Q7. Do the docs match the code?

Yes, on every checked point:

- Key list and **order** in `references/formats.md:31-43` matches `build_frontmatter`
  (`checkpoint.py:671-686`) exactly, including the conditional `since:`.
- `--label`, the four preview files, and the `--json` payload keys in `SKILL.md` match.
- "~14 lines" matches the 14-line maximum block.
- `formats.md:214-217` claims for `INDEX.md` only "preview by default, `--apply`,
  atomic replace, and a content-hash concurrent-modification guard" — deliberately
  omitting the *validation* callback that `PROGRESS.md` and `STATE.md` get. That is
  accurate; considered and dismissed as a defect.
- `formats.md:200-201`'s claim that "`|` is escaped so a value cannot break out of its
  column" is true; the claim does not extend to `]`/`(` (D3).

---

## 4. Defects

### D1 — medium — `.agents/skills/catchup/collect_repo_state.py:559-575` (with `:130-148`)

`collect_checkpoints` returns `file_info(path)`, whose contract is "first non-empty
line". Since `9d93caf` every checkpoint's first non-empty line is the frontmatter fence
`---`, so the catchup collector now reports a constant, information-free string for
every checkpoint. Reproduced against the scratch repo:

```json
{"present": true, "items": [
  {"file": "2026-07-26-100000.md", "present": true, "first_line": "---", "error": null},
  {"file": "2026-07-25-100000.md", "present": true, "first_line": "---", "error": null}]}
```

`.agents/skills/catchup/SKILL.md:82` still documents this field as
"`checkpoints` — newest 5 (file + first heading)". The whole point of the field — give
`/catchup` a one-glance name for each recent session — is silently dead, and the new
frontmatter contains a *better* answer (`summary`, `slug`) that is not used.
`tests/test_collect_repo_state.py:334-344` does not catch it because its fixture writes
a frontmatter-less checkpoint.

**Minimal fix**: in `collect_checkpoints`, skip a leading frontmatter block before
taking the first heading — e.g. read the file, and if it starts with `---`, prefer
`checkpoint.parse_frontmatter`-style `summary`/`slug`, else take the first line after
the closing fence. A ~10-line local helper in `collect_repo_state.py`; do not import
`checkpoint.py`. Add a regression test with a frontmatter-bearing checkpoint.

### D2 — medium — `.agents/rules/codex-delegation.md:77` (and the paragraph at `:69-70`)

The row `| Any Bash error or non-zero exit | error-to-codex.py | codex-debugger |`
misdescribes the hook. `error-to-codex.py` fires on *output pattern matching*
independently of the exit code: `_detect_errors` (`error-to-codex.py:144-158`) returns
a hint on one `STRONG_ERROR_PATTERNS` match or `MIN_WEAK_SIGNALS = 2` weak matches,
and `main` (`:195-199`) reports `"N error pattern(s) found in command output"` before
it ever looks at the exit code. During this review the hook fired three times on
successful (exit 0) read-only commands — `git show` of a diff, `cat` of a rules file,
`--help` output — purely because the *text being read* contained the words
`error`/`Error:`/`FAIL`.

Combined with `:69-70` ("treat each hint as a prompt to route, not as noise to
dismiss"), the rule now instructs the agent to escalate to `codex-debugger` on hints
that routinely fire when nothing failed. That is a real cost: an unnecessary Codex
round trip per false positive.

**Minimal fix**: change the row's Situation cell to "Bash output matches error
patterns, or a non-zero exit", and append one sentence to `:69-70`: "Confirm the
command actually failed (non-zero exit, or a real error in the output rather than a
quoted one) before routing; the Bash hook matches text and fires on read-only commands
that merely display error-shaped output." Doc-only, no hook change (hooks are out of
scope).

### D3 — low — `.agents/skills/checkpointing/checkpoint.py:595-597` and `:740`

Two related escaping gaps.

(a) `_sanitize_tag` strips only `[`, `]`, `|`, `,` and whitespace. A tag reaching
`tags: [...]` through a top-level directory name (`derive_tags`, `:614-616`) or an
Agent Teams `team-{name}` (`:634-637`) can still contain `#`, `&`, `*`, `:`, `{`, `}`,
which respectively break the flow sequence, become an undefined alias, or silently turn
the tag into a mapping — see the Q1 table. The repo's own `parse_frontmatter` never
notices, so the damage is confined to any external YAML reader and to a human reading
the block, which is exactly the audience the frontmatter was added for.

(b) `_index_row:740` builds the link cell as `f"[{_escape_table_cell(slug)}]({stem}.md)"`.
`_escape_table_cell` escapes `|` and newlines only, so a `slug` containing `]` or `(` —
reachable only from a malformed/hand-edited frontmatter — destroys the markdown link.

**Minimal fix**: (a) widen the `_sanitize_tag` character class to
`r"[^A-Za-z0-9._/-]+"` (allow-list rather than deny-list) and re-strip leading/trailing
`-`; (b) at `:740`, pass the slug through the same allow-list, or fall back to `stem`
when the slug contains `[]()`.

### D4 — low — `.agents/skills/checkpointing/checkpoint.py:1648-1651` (ordering)

The `INDEX.md` write sits *between* the `PROGRESS.md` write and the `STATE.md` Progress
Tracker insert. `INDEX.md` is fully derivable from the checkpoints, yet a failed
content-hash guard on it (a hand-edited or concurrently written index) returns exit 3
and skips the `STATE.md` update, leaving the repository with a new checkpoint and
`PROGRESS.md` entry but no tracker link — a worse end state than a stale index.

**Minimal fix**: move the `INDEX.md` `atomic_replace` call to *after* the `STATE.md`
block, or keep the position and downgrade its failure to a `payload["warnings"]` entry
(the index is regenerated on the next run anyway, which is the stated design).

### D5 — low — `.agents/skills/checkpointing/checkpoint.py:691-714` (`parse_frontmatter`)

An unterminated frontmatter block (opening `---`, no closing fence) makes the loop read
the whole document, so ordinary body lines containing a colon become fields. Reproduced
above: a body line `commits: 999` and `summary: injected | row` were both promoted into
the index row. The docstring promises only that a *missing* block yields `{}`; a
*malformed* one silently yields garbage.

**Minimal fix**: scan for the closing fence first and return `{}` when there is none
(two extra lines: find the index of the next `---` in `lines[1:]`, return `{}` if
absent, iterate only up to it).

### D6 — low — `tests/test_checkpoint.py` (coverage gap)

Of the ten new functions, `derive_tags`, `_sanitize_tag`, `derive_headline`,
`_escape_table_cell` and `_index_row` have no direct test (`grep` over the file finds
only `compose_index_md` at `:669,679`). Nothing pins: the `|`-escaping that
`references/formats.md:211` advertises, the tag derivation rules that
`references/formats.md:31-38` documents, the 72-char truncation, the 5-tag cap, or the
byte-stable regeneration that the design depends on. `.agents/rules/testing.md`
("Edge cases: … special characters") asks for exactly these.

**Minimal fix**: add three tests —
`test_a_pipe_in_the_summary_stays_inside_its_index_column`,
`test_regenerating_the_index_is_byte_identical`, and
`test_tags_name_the_commit_types_and_directories_touched`.

---

## 5. Non-defects considered and dismissed

- `INDEX.md` mistaken for a checkpoint — correctly excluded by `CHECKPOINT_STEM_RE`
  in both `checkpoint.py:1043-1047` and `collect_repo_state.py:565`. Verified.
- `--label` with punctuation/non-ASCII — `_slugify` + `or DEFAULT_SLUG` handles it;
  `'weird | label: "x"'` → `weird-label-x`, verified end to end.
- Commit subject containing `"`, `\`, `:`, newline, leading `-`, or a very long line —
  correctly quoted/escaped/collapsed; PyYAML round-trips it.
- `_yaml_quote` / `parse_frontmatter` escape-order bug — checked four adversarial
  backslash/quote combinations; the round trip is exact.
- Same-second checkpoint collision — refused with exit 3 before any write.
- `formats.md`'s "same Writer Safety Contract as `PROGRESS.md`" claim — the parenthesis
  enumerates only the four guarantees the index actually gets, omitting the validation
  callback. Accurate as written.
- `refresh_guard.py` — untouched, and structurally unable to see a checkpoint file.
- The "Hook-Detected Triggers" table's six hook filenames and the 2-file/50-line
  threshold — all verified against `.agents/hooks/`.
- Frontmatter-less legacy checkpoints — still get an index row (pinned by test,
  re-verified in the scratch repo).

---

## 6. Codex consultation record — BLOCKED

Codex was invoked as required and **could not complete**. Two independent failures:

1. First attempt returned
   `{"ok": false, "error": "codex CLI not found on PATH; install with `npm install -g @openai/codex@latest`"}`.
   The CLI was then installed: `npm install -g @openai/codex@latest` → `codex-cli 0.153.0`
   at `/opt/node22/bin/codex`.

2. Second attempt, with the CLI present:

   ```
   python3 .agents/skills/_shared/codex_consult.py \
     --prompt-file <scratchpad>/codex/prompt.md \
     --label pr35-checkpointing-review --caller general-purpose-opus \
     --sandbox read-only --timeout 1400
   ```

   Result after 1400 s:

   ```json
   {"ok": false, "exit_code": null, "model": "gpt-5.6-sol", "caller": "general-purpose-opus",
    "sandbox": "read-only", "timed_out": true, "duration_sec": 1400.01,
    "response_chars": 0, "response_head": "",
    "error": "codex exec timed out after 1400s"}
   ```

   Root cause: this environment's egress proxy denies Codex's API host by policy.
   `curl -sS "$HTTPS_PROXY/__agentproxy/status"` reports repeated
   `connect_rejected` / `gateway answered 403 to CONNECT (policy denial or upstream
   failure)` for `api.openai.com:443` (and `ab.chatgpt.com:443`), 90 such failures
   during the run. `codex exec` started, printed its banner and the prompt, and then
   hung with no model output.

   The wrapper's `edits.created_files` for that run lists
   `.agents/docs/reviews/pr35-checkpointing-codex-review-2026-09-03.md`. That is **this
   report**, written by me while the consult was blocked, not a Codex edit — the
   provenance tracker attributes any tree change during the call window to the callee.
   Codex ran `--sandbox read-only` and produced zero bytes.

A third label (`pr35-codex-ping`) confirms the same zero-byte outcome, so this is
environmental and not prompt-specific. Codex is unavailable here until the proxy allows
`api.openai.com`; re-running the consult is the correct follow-up once it does. The
prompt is preserved verbatim at
`.agents/logs/codex/20260903T190614Z-pr35-checkpointing-review.prompt.md` and can be
replayed unchanged.

## 7. What replaced Codex's judgment

Because Codex was unavailable, each question that would have been Codex's call was
turned into an executable check instead:

| Question | Substitute check |
|---|---|
| Q1 YAML well-formedness | `yaml.safe_load` (PyYAML) run over `build_frontmatter` output for 9 adversarial inputs — table in section 3 |
| Q2 idempotency / losslessness | two `compose_index_md` calls compared byte-for-byte against what `--apply` wrote, plus a hand-crafted malformed-frontmatter checkpoint |
| Q3 collision | read of `main`'s pre-write existence guard, `checkpoint.py:1515-1524` |
| Q4 rule conflict | line-by-line diff of both rule files against the `31ef837` baseline, plus verification of the hook table against `.agents/hooks/` |
| Q5 `refresh_guard.py` | `git show 9d93caf --stat` (not in the diff) plus a grep for checkpoint/frontmatter handling (none) |
| Q6 downstream | `collect_repo_state.py` run against the scratch repo containing new-format checkpoints |
| Q7 doc/code | key-by-key comparison of `references/formats.md` and `SKILL.md` against `build_frontmatter` and `main` |

These establish the *facts* in section 4 conclusively. What they cannot supply is the
second opinion on severity and on the right minimal fix; treat the severities as mine
alone.
