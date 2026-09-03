# PR #35 hook review — merge 9d93caf (2026-09-03)

Scope: the five hooks under `.agents/hooks/` touched by merge commit `9d93caf`
(`agent-router.py`, `check-codex-before-write.py`, `error-to-codex.py`,
`post-test-analysis.py`, `post-implementation-review.py`) plus their only test,
`tests/test_post_bash_check.py`. Out of scope and untouched:
`.agents/skills/checkpointing/**`, `.agents/rules/codex-delegation.md`.

**Verdict: defects found (11).**

## 0. Codex could not be reached — the mandated reviewer of record is missing

The review was to be arbitrated by Codex. It could not be:

```
$ python3 .agents/skills/_shared/codex_consult.py \
    --prompt-file .agents/logs/codex/prompt-pr35-hooks-review.md \
    --label pr35-hooks-review --caller general-purpose-opus \
    --sandbox read-only --timeout 840
{"ok": false, "exit_code": null, "model": "gpt-5.6-sol", "caller": "general-purpose-opus",
 "label": "pr35-hooks-review", "sandbox": "read-only", "write_access": false,
 "timed_out": true, "duration_sec": 840.027, "response_chars": 0,
 "error": "codex exec timed out after 840s"}
```

Cause, from `.agents/logs/codex/20260903T190734Z-pr35-hooks-review.err.log`:

```
ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket:
  URL error: Proxy connection failed: HTTP CONNECT failed with status 403,
  url: wss://api.openai.com/v1/responses
warning: Falling back from WebSockets to HTTPS transport. stream disconnected before completion
ERROR: Reconnecting... waiting for network   (repeated until the 840s deadline)
```

`curl -sS "$HTTPS_PROXY/__agentproxy/status"` confirms the egress proxy is denying
the destination, not that the invocation was malformed:

```
"recentRelayFailures": [ { "kind": "connect_rejected",
  "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
  "host": "api.openai.com:443" }, ... ]
```

Reproduced with a one-word prompt ("Reply with the single word: ONLINE"), so it is
not prompt size:

```
{'ok': False, 'error': 'codex exec timed out after 150s', 'response_chars': 0, 'duration_sec': 150.05}
```

Consequence for the reader: everything below is *my* analysis, backed by executed
evidence rather than by Codex's judgment. The prompt that Codex would have answered
is preserved verbatim at
`.agents/logs/codex/20260903T190734Z-pr35-hooks-review.prompt.md`; re-run the command
above from an environment with egress to `api.openai.com` to get the arbitration this
review is missing. Two judgment calls I flag as *unarbitrated*: whether D10
(post-implementation-review thresholds) is a defect or a taste call, and whether D2
should be deleted or repaired.

## 1. Acceptance checks

### py_compile

```
$ for f in agent-router check-codex-before-write error-to-codex post-test-analysis post-implementation-review; do
    python3 -m py_compile ".agents/hooks/$f.py" && echo "OK $f.py"; done
OK agent-router.py
OK check-codex-before-write.py
OK error-to-codex.py
OK post-test-analysis.py
OK post-implementation-review.py
```

### .agents/check.sh

```
$ bash .agents/check.sh
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

### Test suite

`python3 -m pytest` is not available (`No module named pytest`); the project runs
tests through `uv`.

```
$ uv run pytest tests/ -q
...
tests/test_write_guide.py ...................                            [100%]
======================= 967 passed in 104.62s (0:01:44) ========================
```

The only test touching these five hooks is `tests/test_post_bash_check.py` (8 tests,
all green). It covers `error-to-codex` and `post-test-analysis` through the
dispatcher only. There is **no test at all** for `agent-router.py`,
`check-codex-before-write.py`, or `post-implementation-review.py`.

```
$ uv run pytest tests/test_post_bash_check.py -v
tests/test_post_bash_check.py::test_traceback_output_triggers_debugging_hint PASSED [ 12%]
tests/test_post_bash_check.py::test_pytest_failure_dedups_generic_error_hint PASSED [ 25%]
tests/test_post_bash_check.py::test_codex_exec_command_logs_jsonl_and_confirms PASSED [ 37%]
tests/test_post_bash_check.py::test_codex_wrapper_call_logs_jsonl PASSED [ 50%]
tests/test_post_bash_check.py::test_peer_cli_wrapper_call_logs_its_callee PASSED [ 62%]
tests/test_post_bash_check.py::test_wrapper_help_call_is_not_logged PASSED [ 75%]
tests/test_post_bash_check.py::test_benign_output_produces_no_hint PASSED [ 87%]
tests/test_post_bash_check.py::test_malformed_stdin_does_not_crash PASSED [100%]
============================== 8 passed in 0.30s ===============================
```

That green run is itself evidence — see D1: the hook fired on it.

## 2. Live evidence collected inside a real Claude Code session

These are not simulations; they are hook outputs observed in this session.

**L1 — a fully green test run reported as a failure.** The `-v` run above printed
`8 passed` and zero failures. The session then received:

```
[Codex Debug Suggestion] Test failure with error details (2 issues). Use the
`codex-debugger` subagent before attempting a manual fix ...
```

The "2 issues" are the substring `error` inside the test *names*
`test_pytest_failure_dedups_generic_error_hint` and
`test_traceback_output_triggers_debugging_hint` — matched by the bare
`r"ERROR"`/`r"Error:"` patterns under `re.IGNORECASE`.

**L2 — the error hook is blind on the failing commands it exists for.**

```
$ printf 'Traceback (most recent call last):\n  x\n'; true      # exit 0
-> [Error Detected] 1 error pattern(s) found in command output. ...   (FIRED)

$ printf 'Traceback (most recent call last):\n  x\n'; exit 1     # byte-identical output, exit 1
-> (no hook output at all)

$ printf 'alpha beta gamma delta epsilon\n'; exit 7
-> (no hook output at all)
```

Identical stdout, identical patterns; the only difference is the exit status. On a
non-zero exit the hook emits nothing, so in the real runtime the payload does not
expose the output under `stdout`/`content` (or the hook is not reached at all). The
new "fire on non-zero exit" branch therefore never runs in production — it is green
only because `tests/test_post_bash_check.py:34-39` invents the payload shape
`{"stdout": ..., "exit_code": 1}`.

**L3 — cry-wolf on successful commands.** `git show 9d93caf -- .agents/hooks/`
(exit 0, a successful read of the very diff under review) produced:

```
[Error Detected] 8 error pattern(s) found in command output. ...
```

A later successful `grep`+`python3 -c` combination produced
`[Error Detected] 2 error pattern(s) found in command output.` Both commands
succeeded. The words `deprecated`, `timeout`, `Error:`, `FAILED` in ordinary
*content* are enough.

## 3. Offline harness (pure `build_context` / `should_suggest_codex` calls)

Harness: `/tmp/.../scratchpad/harness.py` and `router.py`; both load the hooks by
path and call their pure functions.

### error-to-codex.py

```
quiet | grep no match (exit 1, empty stdout)
quiet | grep -c no match (exit 1, stdout "0")
FIRE  | diff a.txt b.txt with differences (exit 1) -> "command exited with code 1 - likely a silent failure"
quiet | git diff --quiet (exit 1, empty)
quiet | test -f nope (exit 1, empty)
quiet | [ 1 -eq 2 ] (exit 1, empty)
FIRE  | python3 -c 'print("maybe")'; exit 1 -> "command exited with code 1 - likely a silent failure"
FIRE  | pip install output w/ "deprecated" + "Could not" (exit 0) -> 2 error pattern(s)
FIRE  | curl output "timed out, retrying" + "Unable to" (exit 0) -> 2 error pattern(s)
FIRE  | real traceback (exit 1) -> 2 error pattern(s)          [correct]
quiet | "Build complete in 3s" (exit 0)                        [correct]
```

The benign *silent* non-zero exits (`grep` no-match, `test`, `[`, `git diff --quiet`)
are saved by the pre-existing empty-output guard at line 177, not by the new logic.
The benign *loud* non-zero exits (`diff` with differences) fire.

### post-test-analysis.py

```
FIRE  | GREEN pytest, test name contains "error" -> "Test failure with error details (1 issue)"
quiet | GREEN pytest plain ("8 passed in 0.30s")
quiet | GREEN ruff ("All checks passed!")
FIRE  | GREEN mypy "Success: no issues found in 1 source file (src/errors.py)" -> "Test failure with error details (1 issue)"
FIRE  | 1 real failure (FAILED + AssertionError) -> "Multiple failures detected (4 issues)"   [fires correctly, count inflated 4x from one failure]
```

### check-codex-before-write.py

```
quiet | one-line docs edit ("Fix a typo in the sentence.")
FIRE  | 210 chars of plain docs text -> "Creating new file with meaningful content"
quiet | README.md (SIMPLE_EDIT_PATTERNS)
FIRE  | /repo/__pycache__/x.pyc -> "File path contains 'cache' - likely a design decision"
FIRE  | .agents/hooks/agent-router.py -> "File path contains 'router' - likely a design decision"
FIRE  | prose "we should design later" in notes.txt -> "Content contains 'design'"
FIRE  | "typedef struct A A;\ntypedef struct B B;\n" -> "2 definitions in one write - structural change"
FIRE  | "#ifdef FOO\n#ifdef BAR\n#endif\n#endif\n" -> "2 definitions in one write - structural change"
FIRE  | "The def of the term.\nAnother def of it.\n" -> "2 definitions in one write - structural change"
quiet | empty new_string
```

End-to-end via stdin confirms the same for the real hook process:

```
$ echo '{"tool_name":"Edit","tool_input":{"file_path":"/repo/docs/notes.md","new_string":"Fix typo."}}' \
    | python3 .agents/hooks/check-codex-before-write.py
(no output)
$ ... same path, new_string = 210 x "a" ...
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
 "[Codex Consultation Reminder] Creating new file with meaningful content. You SHOULD consult Codex ..."}}
```

### agent-router.py — quantification

47-prompt corpus (10 conversational, 16 mechanical asks, 6 genuine design/debug,
15 ordinary asks that should not route). Result: **24/47 routed (51%)**. Excluding
the 6 prompts that *should* route, **18 of 41 non-design prompts fired (44%)**.

```
FIRE [codex] 'option'      <- add a --dry-run option
FIRE [codex] 'option'      <- add an optional flag to the CLI
FIRE [codex] 'error'       <- the function returns an error string, wrap it
FIRE [codex] 'improve'     <- improve the wording of this sentence
FIRE [codex] 'what if'     <- what if I just delete the file
FIRE [codex] 'why is'      <- why is the log empty
FIRE [codex] 'should i'    <- should I use tabs or spaces
FIRE [codex] 'dependency'  <- add a dependency on requests
FIRE [codex] 'pattern'     <- explain this regex pattern
FIRE [codex] 'review'      <- review the changelog wording
FIRE [codex] 'security'    <- print a security notice in the README
FIRE [opus-research] 'docs'<- make the docstring better
FIRE [codex] '依存関係'     <- この関数の依存関係を図にして
FIRE [codex] '改善'        <- 改善点を1つだけ挙げて
FIRE [codex] 'パターン'     <- パターンマッチを使って書き直して
FIRE [codex] '設計'        <- テスト設計は後で
FIRE [codex] 'セキュリティ' <- セキュリティヘッダーを追加して
FIRE [codex] '相談'        <- 相談なんだけど昼食は?
```

`thanks`, `ok`, `lgtm`, `ありがとう`, `了解` and the mechanical asks stay quiet — the
10→3 length change is largely inert on its own. The damage is from the widened
keyword list, matched as bare substrings.

### post-implementation-review.py

```
$ echo '{"tool_name":"Edit","session_id":"revsess1","cwd":"/tmp/fakeproj",
        "tool_input":{"file_path":"/tmp/fakeproj/a.py","new_string":"x = 1\n"}}' | python3 .agents/hooks/post-implementation-review.py
(no output)
$ ... same session, b.py, "y = 2\n" ...
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
 "[Code Review Suggestion] 2 files modified in this session. You SHOULD have Codex review ..."}}
```

Two one-line edits — 2 meaningful lines total — spend the session's single review
nudge, which the `review_suggested` latch then disables for the rest of the session.

### Regex audit

No catastrophic backtracking: every new pattern is a flat alternation or literal with
no nested quantifier over an overlapping alternation, so all are linear. Anchoring is
where the problems are (D1, D4), plus one pattern that silently misses its own target:

```
$ python3 -c "import re; ..."
'exit code: 1'  exitpat= False      <- the common formatting is NOT matched
'exit code 1'   exitpat= True
'exit status 3' exitpat= True
'FAILURE'       failpat= False
'FAILED'        failpat= True
```

## 4. Defects

### D1 — `post-test-analysis.py:31-49, 87-97`: a green test run is reported as a failure

`FAILURE_PATTERNS` contains the bare tokens `r"ERROR"`, `r"failed"`, `r"Error:"`,
`r"error:"`, matched with `re.IGNORECASE` and `re.findall`, and the threshold dropped
to `failure_count >= 1`. Any *word* containing `error` or `failed` anywhere in the
output — a test name, a filename, a docstring — is now a "failure". Proven live (L1)
on `8 passed`, and offline on a clean `mypy` run whose only sin is a source file named
`errors.py`. A debug hint that fires on a green suite is worse than no hint: the
operator learns to skim past it, and it will be skimmed past on the run that is
actually red.

Minimal fix — anchor the generic tokens instead of raising the threshold back:

```python
r"(?m)^(?:FAILED|ERROR)\b",     # replaces bare r"FAILED", r"ERROR", r"FAIL:"
r"(?m)^E\s",                    # pytest's failure-line prefix
r"\b\d+\s+failed\b",            # replaces bare r"failed"
```

and drop the bare `r"Error:"` / `r"error:"` in favour of `r"(?m)^\s*\w*Error:\s"`.
Keep `MIN_FAILURES_FOR_MULTIPLE`/`>= 1` as they are.

### D2 — `error-to-codex.py:97-112, 195-201`: the new exit-code branch is dead in production

`_exit_code` reads `tool_response["exit_code"]` / `["exitCode"]`. L2 shows that on a
non-zero exit the hook emits nothing even when the output contains a strong pattern
that fires identically at exit 0 — so the real payload does not deliver what this
branch needs, and the branch has never fired. It is green only because the test
fixture at `tests/test_post_bash_check.py:34-39` constructs the payload itself.
The PR's headline behaviour ("fire on non-zero exit code") does not exist.

Minimal fix — one of, not both:
- **Delete** `_exit_code` (lines 97-112) and the `elif exit_code:` branch (lines
  198-201), restoring `if not errors: return None`; or
- **Repair**: capture one real failing-Bash PostToolUse payload (temporarily log
  `json.dumps(data)` from `post-bash-check.py` to a file, run a failing command, read
  it back), key `_exit_code` off the field that actually exists, and replace the
  invented fixture with the captured payload. Do not ship the branch until a test
  built from a captured payload fails without it.

### D3 — `error-to-codex.py:189-201`: the branch contradicts its own rationale

The comment says the case is "the command failed and said nothing quotable about
why", but the code fires on *any* non-zero exit with ≥5 chars of output, however
loud. `diff a.txt b.txt` with differences (exit 1, four lines of legitimate output)
yields "command exited with code 1 - likely a silent failure". If D2 is repaired
rather than deleted, this fires on every `diff`, `grep -c`, `cmp`, `pgrep` and
`git diff --exit-code` that produces output.

Minimal fix — make the code match the comment, and exempt exit-status-as-answer
commands:

```python
BENIGN_NONZERO_PREFIXES = ("grep", "rg", "diff", "cmp", "test ", "[ ", "pgrep",
                           "git diff --quiet", "git diff --exit-code")
...
elif exit_code and len(tool_output) < QUIET_FAILURE_MAX_CHARS \
        and not command.strip().startswith(BENIGN_NONZERO_PREFIXES):
```

### D4 — `error-to-codex.py:45-54`: the new weak patterns co-occur in successful output

`\bdeprecated\b`, `(?:Deprecation|Future)Warning`, `(?:timeout|timed out)`,
`returned non-zero`, `exit (?:code|status)\s*[1-9]` are added to a list that already
contains `(?:Cannot|Could not|Unable to)\s`. `MIN_WEAK_SIGNALS` is 2, and warnings
travel in pairs: verified `pip install` output ("DEPRECATION" + "Could not") and
`curl` output ("timed out, retrying" + "Unable to") both fire at exit 0, and L3 shows
a successful `git show` scoring 8. A deprecation warning is by definition not an
error; putting it in an error-pattern list guarantees false positives on healthy
builds.

Minimal fix: delete `r"(?:Deprecation|Future)Warning"` and `r"\bdeprecated\b"`
(lines 50-51) outright — warnings belong in a lint hook, not an error hook — and
raise `MIN_WEAK_SIGNALS` to 3 (line 58) now that the list has 12 entries instead of 5.

### D5 — `check-codex-before-write.py:123-124`: 200 chars of any edit, described as a file creation

`content` is `tool_input["content"] or tool_input["new_string"]` (line 156), so the
`NEW_FILE_CONTENT_THRESHOLD` gate applies to **Edit** as well as Write. 200 characters
is roughly three lines. A 210-character prose edit to `docs/notes.md` fires with the
message "Creating new file with meaningful content" — it is neither a creation nor a
file. The hook is wired to `Edit|Write` in `.claude/settings.json`, so this is the
dominant firing path for the whole hook.

Minimal fix: gate the threshold on the tool that was actually used, and tell the
truth in the message.

```python
def should_suggest_codex(file_path, content=None, is_new_file=False):
    ...
    if content and is_new_file and len(content) > NEW_FILE_CONTENT_THRESHOLD:
        return True, "Creating new file with substantial content"
```

with `is_new_file = data.get("tool_name") == "Write"` at the call site, and
`NEW_FILE_CONTENT_THRESHOLD` restored to a value that means "substantial" (500).

### D6 — `check-codex-before-write.py:136`: `count("def ")` is a substring count, not a definition count

`content.count("class ") + content.count("def ")` counts the `def ` inside
`typedef `, `#ifdef `, `#ifndef `, and inside English prose. All three verified
firing. The `class ` half is additionally near-unreachable, because `"class "` is
already in `DESIGN_INDICATORS` and returns at line 128 first — so in practice this
branch counts only `def `-like substrings.

Minimal fix:

```python
import re
DEFINITION_RE = re.compile(r"(?m)^\s*(?:async\s+)?def\s+\w|^\s*class\s+\w")
...
definition_count = len(DEFINITION_RE.findall(content))
```

### D7 — `check-codex-before-write.py:47-61`: role words matched against the whole path

`indicator.lower() in filepath_lower` (line 117) with the new entries `cache`,
`router`, `handler`, `service`, `manager`, `provider`, `signal`, `registry`. Verified:
`/repo/__pycache__/x.pyc` fires on `cache`; `.agents/hooks/agent-router.py` fires on
`router`. Every build artefact directory and a large share of ordinary filenames now
"contain a design decision", and the reason string is confidently wrong.

Minimal fix: compare tokens of the basename, not substrings of the full path, and
keep concept words (`cache`, `signal`, `retry`) out of the *path* list.

```python
PATH_ROLE_INDICATORS = {...}   # split from the content indicators
tokens = set(re.split(r"[^a-z0-9]+", Path(file_path).name.lower()))
if tokens & PATH_ROLE_INDICATORS: ...
```

### D8 — `agent-router.py:96-146`: 44% of non-design prompts are routed, and the wording became a mandate

Bare-substring keywords `option`, `pattern`, `improve`, `approach`, `dependency`,
`security`, `advice`, `error`, `review`, `docs`, and JA `相談`, `改善`, `パターン`,
`複雑`, `セキュリティ` route 18 of 41 non-design prompts in the corpus above.
`option` matches `optional`; `docs` matches `docstring`. At the same time lines
288-294 escalated the wording from "may benefit from / Consider" to "MUST go through
Codex". A signal that fires on "add a --dry-run option" and calls itself MUST is a
signal the operator has to start ignoring, which costs exactly the cases the PR
wanted to catch.

Minimal fix, two parts:
1. Delete the ambiguous single words from the EN list — `pattern`, `approach`,
   `improve`, `option`, `alternative`, `dependency`, `security`, `advice` — and from
   the JA list `パターン`, `改善`, `依存関係`, `セキュリティ`, `相談`, `意見`, `複雑`.
   Keep the unambiguous multi-word phrases already added (`best practice`,
   `better way`, `test strategy`, `not sure`, `should i`, `should we`).
2. Match the EN list on word boundaries so what remains cannot match inside a longer
   word:
   `if re.search(rf"\b{re.escape(trigger)}\b", prompt_lower)` (JA has no word
   boundaries; keep `in` for the JA list).

### D9 — `agent-router.py:262`: the length gate is character-based and still skips short JA triggers

`len(prompt) < 3` skips `設計` (2 characters) — a prompt the comment on lines 260-261
explicitly claims to want to route — while admitting every 3-character noise prompt.
The gate now buys nothing and costs a real case.

Minimal fix: delete the gate (lines 260-263). `detect_agent` on an empty or
one-character prompt matches nothing anyway.

### D10 — `post-implementation-review.py:56-57` vs the one-shot latch at 92-93, 143

`MIN_FILES_FOR_REVIEW = 2` interacts badly with `review_suggested`, which permanently
disables the hint after the first fire. Verified: two one-line edits (2 meaningful
lines) trigger it, and the session's only review nudge is then spent — the 400-line
refactor an hour later gets nothing. The threshold change and the latch were designed
against each other. *(Unarbitrated: this is the one item where reasonable reviewers
could disagree about whether 2/50 is simply the intended aggressiveness.)*

Minimal fix — re-arm instead of latching:

```python
last_files = state.get("suggested_at_files", 0)
if files_count >= MIN_FILES_FOR_REVIEW and files_count >= last_files * 2:
    ...
    state["suggested_at_files"] = files_count
```

(keeping `review_suggested` only as a within-threshold debounce), or leave the latch
and restore `MIN_FILES_FOR_REVIEW = 3`.

### D11 — test coverage does not cover the behaviour that changed

`tests/test_post_bash_check.py` is the only test touching these hooks. It has no
negative case for any lowered threshold, and its `bash_hook_input` helper
(lines 34-39) asserts a payload contract that L2 shows production does not provide.
`agent-router.py`, `check-codex-before-write.py` and `post-implementation-review.py`
have no tests at all, despite all three changing behaviour in this merge. Under
`.agents/rules/testing.md` (Test Case Coverage: normal / boundary / error cases) a
threshold change is precisely a boundary change and should arrive with the boundary
tests.

Minimal fix: add to `tests/test_post_bash_check.py`
`test_green_pytest_output_produces_no_hint` (the `8 passed` + `..._error_hint PASSED`
output) and `test_benign_nonzero_exit_produces_no_hint` (`diff` with differences),
plus a new `tests/test_hook_thresholds.py` covering `should_suggest_codex`,
`detect_agent` and `should_suggest_review` with one fire and one no-fire case each.

## 5. What is NOT wrong

- All five files compile; `.agents/check.sh` is 8/8; the suite is 967 green.
- No catastrophic backtracking in any new or existing pattern (all flat alternations).
- `^error\[\w+\]` and the errno alternation `\b(?:ECONNREFUSED|...)\b` are correctly
  anchored and escaped, and the strong-pattern additions
  (`OutOfMemoryError`, `undefined reference to`, `too many open files`) are specific
  enough to belong in the strong list.
- `_exit_code`'s `isinstance(value, bool): continue` guard is correct (`bool` is an
  `int` subclass, and `True` would otherwise read as exit 1).
- Keeping the noise-prone patterns as *weak* signals rather than promoting them, as
  the merge commit message claims, is the right call — the defect is that 12 weak
  signals with a threshold of 2 is no longer weak.
- `post-test-analysis`'s dedup against `error-to-codex` in `post-bash-check.py` still
  works (verified by the existing green test).

## 6. Files touched by this review

None. `.agents/hooks/` and `tests/` are unmodified; `git status --porcelain` shows
only this report and the parallel agent's checkpointing report. Artefacts written:
this file, and under `.agents/logs/codex/` the prompt, empty response and error log
of the failed consult.
