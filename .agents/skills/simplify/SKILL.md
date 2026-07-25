---
name: simplify
description: Simplify and refactor code while preserving functionality and library constraints.
disable-model-invocation: true
---

# Simplify Code

Simplify and refactor $ARGUMENTS.

This skill edits source code while promising not to change behaviour and not to
widen its own scope. Both promises are checked rather than asserted: Step 0
records a gate baseline and the declared target set, and Step 5 compares against
it. A refactor whose baseline was never recorded cannot be reported as verified.

## Declared Scope

Resolve `$ARGUMENTS` into a concrete list of files and/or directories **before
editing anything**, and pass each one as a `--scope` entry in Step 0. That list
is the answer to "was this a refactor or a rewrite" — anything else that changes
is reported as `out_of_scope_files` and fails Step 5.

## Simplification Principles

1. **Single Responsibility** - 1 function = 1 thing
2. **Short Functions** - Target under 20 lines
3. **Shallow Nesting** - Early return, depth ≤ 2
4. **Clear Naming** - Clear enough to not need comments
5. **Type Hints Required** - On all functions

## Steps

### 0. Record the Baseline (mandatory, before any edit)

```bash
python3 .agents/skills/simplify/simplify_gate.py --phase before \
  --scope {target file or dir} [--scope {another}] [--base main]
```

It runs `_shared/verify.sh` and `_shared/gather_diff.py` and writes
`.agents/logs/simplify-baseline.json`: the gate status of every tool **as it is
now**, the current HEAD, the declared scope, and any file that was already
modified before you started. Without this, a gate that was red the whole time is
indistinguishable from a regression this refactor introduced.

Read the JSON:

- `overall_before` — `pass` / `fail` / `no_gates`. On `fail`, note which tools
  are in the baseline as failing; Step 5 will report them as
  `pre_existing_failures` rather than blaming your refactor.
- `pre_existing_changes[]` — dirty files you did not touch, excluded from the
  scope check later.
- `baseline_file`, `artifacts[]`.

Exit codes: `0` baseline recorded · `1` bad arguments, or `--scope` missing —
without a declared target set "no scope creep" cannot be checked · `2` **no gate
could run at all**, so the refactor would be unverifiable · `3` verify.sh /
gather_diff.py failed, or the baseline could not be written.

`--baseline PATH` moves the record elsewhere (default
`.agents/logs/simplify-baseline.json`); pass the same value to both phases when
two refactors are in flight. `--project-root DIR` relocates the repository root.

On exit `2`, stop. Either configure the project's gates, or agree with the user
on the exact commands that will verify this refactor, run them, record each
command with its exit code, and re-run with `--allow-no-gates` so the payload
carries `allow_no_gates: true`. Do not edit code first and decide how to verify
it afterwards.

### 1. Analyze Target Code

- Read the file(s) to understand current structure
- Identify complexity hotspots (deep nesting, long functions)
- List functions/classes to simplify

### 2. Check Library Constraints

- Identify libraries used in target code
- Check constraints in `.agents/docs/libraries/`
- Web search for unclear library behaviors

### 3. Plan Refactoring

For each complexity issue:
- What change to make
- Why it improves readability
- Verify it doesn't break library usage

### 4. Execute Refactoring

Apply changes following these patterns:

**Early Return:**
```python
# Before
def process(value):
    if value is not None:
        if value > 0:
            return do_something(value)
    return None

# After
def process(value):
    if value is None:
        return None
    if value <= 0:
        return None
    return do_something(value)
```

**Extract Function:**
```python
# Before
def main():
    # 50 lines of mixed concerns
    ...

# After
def main():
    data = load_data()
    result = process_data(data)
    save_result(result)
```

### 5. Verify Against the Baseline

```bash
python3 .agents/skills/simplify/simplify_gate.py --phase after
```

The scope and base ref are read back from the baseline, so they cannot drift
between the two phases; `--scope` may be repeated here to narrow them further.
It re-runs the gates, re-collects the changed files, and attributes every
failure:

- `regressions[]` — a gate that passed (or was skipped) before and fails now.
  **This is the only list your refactor is responsible for.** Fix it.
- `pre_existing_failures[]` — red before, red after. Report, do not fix here.
- `fixed[]` — red before, green now.
- `gates` — `{tool: {before, after}}` for every gate; quote it rather than
  re-typing statuses, so `skipped` is never reported as `pass`.
- `changed_files[]` / `in_scope_files[]` / `out_of_scope_files[]` — the diff this
  run produced. `out_of_scope_files` is non-empty only when a file outside
  `--scope` changed and was not already dirty at baseline.
- `verify_log`, `diff_file` — full gate output and the full patch, for reading
  rather than for context.
- `warnings[]` — includes "no file changed" and "HEAD moved between the two
  phases".

Exit codes: `0` no regression and no scope creep · `1` no readable baseline (run
`--phase before` first) · `2` a gate regressed, a file outside `--scope` changed,
or no gate could run · `3` verify.sh / gather_diff.py failed.

Then self-review `diff_file` yourself: the gate proves the tests still pass and
the scope held, not that the result is *simpler*. That judgment is yours.

## Notes

- Always preserve library features/constraints
- Web search for unclear points
- Don't change behavior (refactoring only) — `regressions[]` is the evidence
- Run `--phase after` again after each significant change; it is idempotent
- The "under 20 lines" and "depth ≤ 2" targets are guidance, not thresholds to
  enforce mechanically. No bundled script measures them, deliberately: a rule
  that split every 20-line function would produce worse code than it found.
  Judge each hotspot on whether the extraction has a name worth having.
