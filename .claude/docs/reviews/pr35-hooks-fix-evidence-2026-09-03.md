# PR #35 hook fixes — executed evidence (2026-09-03)

Companion to `.agents/docs/reviews/pr35-hooks-codex-review-2026-09-03.md`.
Branch `claude/resolve-pr-conflicts-agkoey`; merge `9d93caf` is not reverted.

**Codex was not consulted**: the egress proxy answers 403 to CONNECT for
`api.openai.com`, so every judgment call below rests on executed evidence only.
Explicitly unarbitrated: the D2 delete-vs-repair choice, the D10 doubling rule,
and the decision to match router triggers with an optional plural `s`.

## D2 — the captured real PostToolUse payload

`post-bash-check.py` was temporarily patched to append its raw stdin to
`/tmp/hookpayload-capture.jsonl`, several Bash commands were run in a live
Claude Code session, and the patch was reverted (`git diff` for that file is
empty). Two findings, both fatal to the exit-code branch:

1. `tool_response` carries **no exit status under any spelling**. Every captured
   payload has exactly these keys:

```
top-level:      agent_id, agent_type, cwd, duration_ms, effort, hook_event_name,
                permission_mode, prompt_id, scratchpad_dir, session_id,
                tool_input, tool_name, tool_response, tool_use_id, transcript_path
tool_response:  interrupted, isImage, noOutputExpected, stderr, stdout
```

Representative captured object (a successful `cp`+patch command):

```json
{"session_id":"c862d471-...","cwd":"/home/user/claude-code-orchestra",
 "hook_event_name":"PostToolUse","tool_name":"Bash",
 "tool_input":{"command":"cp .agents/hooks/post-bash-check.py ... "},
 "tool_response":{"stdout":"patched","stderr":"","interrupted":false,
                  "isImage":false,"noOutputExpected":false},
 "tool_use_id":"toolu_01P9S4GwpLVnAKBDG5ueyG63","duration_ms":64}
```

2. **A failing Bash command does not reach the hook at all.** Four genuinely
   failing commands were run while the capture patch was live —
   `printf 'alpha...'; exit 7`, `printf 'Traceback...'; exit 1`,
   `wc -l ...; false`, `printf 'CAPTURE_FAILING_CASE'; exit 3` — and **none**
   produced a capture line, while every exit-0 command in the same window did.
   This independently reproduces the review's L2 observation.

**Decision: delete, not repair.** There is no field to key off, and even a
correctly-keyed branch would be unreachable because the hook is not invoked on
failure. `_exit_code()` and the `elif exit_code:` branch are removed;
`build_context` restores `if not errors: return None`.

The fixture `bash_hook_input(..., exit_code=...)` in
`tests/test_post_bash_check.py` is **kept**, because `log-cli-tools.py:201,222,260`
also reads `tool_response["exit_code"]` and four existing tests assert its
`success` field — deleting the fixture parameter would delete those tests, which
the brief forbids. Its docstring now records the captured contract.

**Flagged, out of scope**: `log-cli-tools.py` derives `success` from the same
absent `exit_code`, so its `success` is effectively always `True` for bare
`codex exec` calls (wrapper calls degrade gracefully via the JSON `ok` field).
That hook is not in this task's scope and was not changed.

## Reproductions — now quiet

```
R1 green pytest -v  -> post-test-analysis: None
R1 green pytest -v  -> error-to-codex   : None
R2 diff exit1 loud  -> error-to-codex   : None
```

## Reproductions — still firing (the fix does not silence real failures)

```
R4 red pytest       -> [Codex Debug Suggestion] Multiple failures detected (5 issues). ...
R5 real traceback   -> [Error Detected] 2 error pattern(s) found in command output. ...
```

## agent-router corpus

Of the 18 non-design prompts the review recorded as firing, 6 still fire:

```
('codex', 'error')    <- the function returns an error string, wrap it
('codex', 'what if')  <- what if I just delete the file
('codex', 'why is')   <- why is the log empty
('codex', 'should i') <- should I use tabs or spaces
('codex', 'review')   <- review the changelog wording
('codex', '設計')      <- テスト設計は後で
```

All six come from triggers the brief told me to **keep**: `what if`, `why is`,
`should i` are on the keep list, and `error`, `review`, `設計` predate PR #35.
The 12 that stopped firing are exactly the removed ambiguous words.

Still routing correctly:

```
('codex', '設計')                 <- 設計                (the D9 case the length gate skipped)
('codex', 'design')             <- how should we design this module?
('codex', 'why does')           <- why does this fail?
('opus-research', 'research')   <- research the latest version
('codex-plugin', 'review this') <- review this code
('fable', 'stuck')              <- I am stuck on the design
```

## check-codex-before-write end-to-end (stdin)

```
Edit, /repo/docs/notes.md, 210 chars      -> (no output)
Edit, /repo/__pycache__/x.pyc             -> (no output)
Write, /repo/tools/helper.py, 630 chars   -> [Codex Consultation Reminder] Creating new file with substantial content ...
```

## Acceptance checks

```
OK agent-router.py / check-codex-before-write.py / error-to-codex.py /
   post-test-analysis.py / post-implementation-review.py        (py_compile)

bash .agents/check.sh   -> Results: 8 passed, 0 failed

python3 .agents/skills/_shared/run_tests.py --expect pass --target tests/ --label pr35-hookfix
{"expected":"passed","observed":"passed","runner":"uv","exit_code":0,
 "summary":"994 passed in 88.66s (0:01:28)","failed_tests":[],"ok":true}
```

## Residual risks

- `post-test-analysis.FAILURE_PATTERNS` is now matched **case-sensitively**
  (`re.findall(pattern, output)` without `re.IGNORECASE`). A runner that prints
  a lowercase `failed:` verdict at line start is no longer detected; the
  anchored `^(?:FAILED|ERROR)\b`, `^E\s`, `^FAIL\b`, `\b\d+\s+failed\b` and
  `^\s*\w*(?:Error|Exception):\s` cover pytest, cargo, go and node.
- `post-implementation-review` re-arm doubles from the last firing size
  (2 -> 4 -> 8 files, 50 -> 100 -> 200 lines). A state file written by the old
  code lacks `suggested_at_*`, so the hint may fire once more in a session that
  spans the upgrade. Harmless.
- `agent-router` EN matching adds an optional plural `s` (`\berrors?\b`) so the
  word-boundary change does not silently drop plural forms that the old
  substring match caught.
