# PR #35 follow-up — fix evidence (D1–D6)

Date: 2026-09-03. Author: `general-purpose-opus`. Branch: `claude/resolve-pr-conflicts-agkoey`.
Companion to `.agents/docs/reviews/pr35-checkpointing-codex-review-2026-09-03.md`.
`9d93caf` was **not** reverted; the frontmatter/INDEX feature is intact. No test was
weakened, skipped or deleted. Nothing under `.agents/hooks/**` was touched.
Codex was again unreachable (proxy denies CONNECT to `api.openai.com`), so every claim
below is backed by an executable check.

## 1. Changes, per defect

### D1 — `.agents/skills/catchup/collect_repo_state.py`, `.agents/skills/catchup/SKILL.md`
New module-local helpers `_first_meaningful_line`, `_unquote_frontmatter_value` and
`checkpoint_info`; `collect_checkpoints` now calls `checkpoint_info` instead of
`file_info`. Precedence: frontmatter `summary` → `slug` → first non-empty body line.
`checkpoint.py` is **not** imported — the reader is 25 lines and knows two keys, so the
two skills stay decoupled. `file_info` is unchanged and still serves rules/skills/agents.
`SKILL.md` now states what the field holds instead of "first heading".

An *unterminated* block is treated as "no frontmatter" (first non-empty line, i.e. the
fence). That is deliberate and mirrors the D5 decision in `checkpoint.py`: with no
closing fence there is no way to tell a field from a body line. It is pinned by the test
so the behaviour is a decision, not an accident.

### D2 — `.agents/rules/codex-delegation.md`
Situation cell → "Bash output matches error patterns, or a non-zero exit"; one sentence
added to the paragraph above the table requiring confirmation of an actual failure
before routing to `codex-debugger`. Doc-only.

**Integration conflict to resolve before merge**: the parallel agent's uncommitted edit
to `.agents/hooks/error-to-codex.py` *deletes* the exit-code path entirely (`_exit_code`
removed, `build_context` returns `None` when no pattern matches) and raises
`MIN_WEAK_SIGNALS` 2 → 3. If that lands, the tail "or a non-zero exit" becomes false and
the cell should read just "Bash output matches error patterns". I left the wording the
task specified because the hook is outside my scope and may still change.

### D3 — `.agents/skills/checkpointing/checkpoint.py`
(a) New module constant `TAG_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._/-]+")`; `_sanitize_tag`
uses it (allow-list) and still re-strips `-`. (b) `_index_row` builds the link label from
`_sanitize_tag(fields.get("slug", "")) or stem`, so `]`/`(`/`[` can no longer escape the
markdown link, and an emptied slug falls back to the stem.

### D4 — `.agents/skills/checkpointing/checkpoint.py`
The `INDEX.md` `atomic_replace` moved below the `STATE.md` block, with a comment naming
the reason. Order is now checkpoint+prompt → `PROGRESS.md` → `STATE.md` → `INDEX.md`.
`payload["artifacts"]` is unchanged (it is a set of paths, not an order).

### D5 — `.agents/skills/checkpointing/checkpoint.py`
`parse_frontmatter` locates the closing fence first and returns `{}` when there is none,
iterating only `lines[1:closing]`. Docstring extended to state the malformed case.

### D6 — `tests/`
Seven tests added (six for D6/D3/D5/D4, one for D1):

- `tests/test_checkpoint.py::test_tags_name_the_commit_types_and_directories_touched`
- `…::test_a_tag_cannot_break_the_frontmatter_flow_sequence`
- `…::test_a_pipe_in_the_summary_stays_inside_its_index_column`
- `…::test_a_bracket_in_the_slug_cannot_break_the_index_link`
- `…::test_an_unterminated_frontmatter_block_yields_no_fields`
- `…::test_regenerating_the_index_is_byte_identical`
- `…::test_a_failed_index_write_does_not_orphan_the_state_tracker`
- `tests/test_collect_repo_state.py::test_a_checkpoint_is_named_by_its_frontmatter_not_by_the_fence`

The D4 test is the only in-process one: it monkeypatches `cp.atomic_replace` to fail for
`INDEX.md` only and `sys.argv`, then calls `cp.main()`. A subprocess run cannot reach the
ordering, because making `INDEX.md` unreadable aborts earlier, at the pre-write read
(`checkpoint.py:1557-1564`).

## 2. Acceptance checks (verbatim)

### 2.1 py_compile

```
OK .agents/skills/catchup/collect_repo_state.py
OK .agents/skills/checkpointing/checkpoint.py
OK tests/test_checkpoint.py
OK tests/test_collect_repo_state.py
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

### 2.3 Full suite

```
$ python3 .agents/skills/_shared/run_tests.py --expect pass --target tests/ --label pr35-ckptfix
{"expected": "passed", "observed": "passed", "runner": "uv",
 "command": ["uv", "run", "pytest", "-p", "no:cacheprovider", "tests/"],
 "exit_code": 0, "summary": "975 passed in 89.14s (0:01:29)", "failed_tests": [],
 "coverage_percent": null, "min_coverage": null,
 "log_file": ".agents/logs/pr35-ckptfix.log", "ok": true}
```

975 includes the parallel agent's hook tests (`tests/test_post_bash_check.py`,
untracked `tests/test_hook_thresholds.py`); none failed.

One intermediate red, worth recording: the first run reported
`1 failed … test_a_failed_index_write_does_not_orphan_the_state_tracker`, asserting
`STAMP in state`. The *fix* was working — the tracker block was inserted — but the
tracker is a link to `PROGRESS.md`, not a timestamp. The assertion, not the code, was
wrong; it now checks the checkpoint file, the `PROGRESS.md` entry and the
`## Progress Tracker` block.

## 3. Reproductions, before and after

Scratch repo: `<scratchpad>/fix/e2e`. The real `.agents/checkpoints/` was never written.
"before" runs use `git show HEAD:` copies of both scripts.

### D1 — `first_line` for a frontmatter-bearing checkpoint

Checkpoint written by the real script from commit
`feat(core): add "fast" retrieval | catalog`:

```yaml
---
id: feature-core-fast-retrieval-2026-07-25-100000
timestamp: 2026-07-25-100000
branch: "master"
slug: feature-core-fast-retrieval
summary: "add \"fast\" retrieval | catalog"
tags: [feature]
...
---
```

```
before: {"present": true, "items": [{"file": "2026-07-25-100000.md", "present": true,
         "first_line": "---", "error": null}]}
after : {"present": true, "items": [{"file": "2026-07-25-100000.md", "present": true,
         "first_line": "add \"fast\" retrieval | catalog", "error": null}]}
```

### D3a — tags from `#weird/`, `&anchor/`, `*alias/`, `{brace}/` and team `a: b`

before:

```
tags: [#weird, &anchor, *alias, agent-teams, brace, team-a: b, weird]
yaml.parser.ParserError: while parsing a flow sequence
  in "<unicode string>", line 7, column 7: expected ',' or ']', but got ':'
```

after:

```
tags   : ['agent-teams', 'alias', 'anchor', 'brace', 'team-a-b', 'weird']
emitted: tags: [agent-teams, alias, anchor, brace, team-a-b, weird]
yaml.safe_load: ok
     tags parsed: ['agent-teams', 'alias', 'anchor', 'brace', 'team-a-b', 'weird']
```

### D3b — slug `broken] (x`

after: `| 2026-01-01-000000 | [broken-x](2026-01-01-000000.md) | - |  | 0c/0f | s |`
(before: `| [broken] (x](2026-01-01-000000.md) |` — link destroyed.)

### D5 — unterminated frontmatter

Input: `---\nslug: broken] (x\ntags: [a, b, c, d, e]\n\n# Body\n\ncommits: 999\nsummary: injected | row\n`

```
after: parse_frontmatter: {}
       index row        : | 2026-01-01-000000 | [2026-01-01-000000](2026-01-01-000000.md) | - |  | 0c/0f | - |
```

Before, `commits: 999` and `summary: injected | row` were promoted out of the body and
into the index row.

## 4. Judgment calls that went unreviewed

Codex could not be consulted, so these are mine alone:

1. Unterminated frontmatter yields `{}` (metadata lost) rather than a best-effort parse.
   Losing metadata on a malformed file is safer than promoting body text, but it does
   mean a truncated write shows an empty row instead of a partial one.
2. `_sanitize_tag` is now applied to the *slug* in the index link. The slug is already
   slugified on the write path, so this only affects hand-edited or foreign frontmatter,
   but it does mean the link label can differ from the `slug:` field in that case.
3. D4 was fixed by reordering rather than by downgrading to a warning. Reordering keeps
   the failure loud; a stale index still aborts the run with exit 3 after `STATE.md` is
   written, so the operator still learns about it.
4. The D2 wording, given the parallel hook rework (section 1, D2).
