---
name: tdd
description: Implement features using Test-Driven Development (TDD) with Red-Green-Refactor cycle.
disable-model-invocation: true
---

# Test-Driven Development

Implement $ARGUMENTS using Test-Driven Development (TDD).

## TDD Cycle

```
Repeat: Red → Green → Refactor

1. Red:    Write a failing test
2. Green:  Write minimal code to pass the test
3. Refactor: Clean up code (tests still pass)
```

Which test cases matter, and when to refactor, is judgment. The one thing that
is *not* judgment is whether a run came out the way you expected: every test run
in this skill goes through `.claude/skills/_shared/run_tests.py`, which turns
"confirm failure" / "confirm success" into an exit code.

## Who Does What (delegation-first)

Per `.claude/rules/delegation.md`, the lead does not write the cycles by hand.
The split is fixed:

| Work | Owner |
|------|-------|
| Requirement clarification, test-case list, boundary values | Lead (judgment, Self-Handle List item 5) |
| Writing the tests and the production code, cycle by cycle | `general-purpose-sonnet` |
| Cycles with ambiguous design, cross-cutting invariants, or security / concurrency / data-integrity risk | `general-purpose-opus` |
| A Red that is red for the wrong reason, or a Green that will not go green after one retry | `codex-debugger` |
| Every `run_tests.py` / `verify.sh` gate and the final report | Lead — verification never delegates |

Only a *single trivial cycle* on a file already open in context stays with the
lead (Self-Handle List item 2). Two or more cycles, or a module the lead has not
read, is delegated. Independent modules are delegated **in parallel in one
message**; they share no test file, so nothing serializes them.

## The Red/Green Invariant

```bash
python3 .claude/skills/_shared/run_tests.py \
  --target tests/test_{module}.py --expect fail --label red-1
```

`--expect fail|pass` (required) and `--target PATH` (repeatable, at least one)
are the whole interface; `--label` names the log file under `.claude/logs/`
(default `run-tests`), so a later cycle does not overwrite an earlier log.

Read `observed` in the JSON — a non-zero exit is **not** all the same red:

| `observed` | pytest exit | What it actually means |
|-----------|-------------|------------------------|
| `failed` | 1 | The test ran and failed. This is the only valid Red. |
| `passed` | 0 | Nothing new is being asserted — the test cannot drive any code. |
| `collection_error` | 2 | The file did not import (syntax error, bad fixture, missing import): red for the wrong reason. Fix the test, not the production code. |
| `no_tests_collected` | 5 | Nothing was selected — the test was never written, or the name does not match the discovery pattern. |

Exit codes: `0` `observed` matches `--expect`; `1` bad arguments — including a
`--target` that does not exist (the mistyped path, caught before pytest runs)
and a pytest usage error (exit 4, e.g. an unknown `::node` id); `2` `observed`
does not match `--expect`, or coverage is below `--min-coverage`; `3` external
failure — no pytest runner available, a timeout (`--timeout`, default 600s), or
a pytest internal error. On `1` and `3` the payload's `observed` is `null`: the
script reports that it has no observation rather than guessing one.

Other payload fields: `expected`, `runner`, `command`, `exit_code`, `summary`,
`failed_tests` (node ids from the short summary), `coverage_percent`,
`min_coverage`, `log_file`, `artifacts`, `error`.

The runner is resolved, not hardcoded: `uv run pytest` when `uv` and a
`pyproject.toml` are present, otherwise `pytest` from PATH, otherwise
`python -m pytest` (probed for importability first). `--runner` pins one
explicitly. If none is available the result is exit `3`, never a silent pass.

## Implementation Steps

### Phase 1: Test Design

1. **Confirm Requirements**
   - What is the input
   - What is the output
   - What are the edge cases

2. **List Test Cases** — record them with TodoWrite (one todo per case), so the
   remaining cases survive a context reset instead of living only in this
   conversation:
   ```
   - [ ] Happy path: Basic functionality
   - [ ] Happy path: Boundary values
   - [ ] Error case: Invalid input
   - [ ] Error case: Error handling
   ```

Which cases to write, and which boundary values matter, is domain reasoning —
never delegate it to a script.

### Phase 2: Red-Green-Refactor

#### Step 0: Hand the Cycles Off

Delegate the Red-Green-Refactor loop with the six-element prompt contract from
`.claude/rules/delegation.md`. One delegation per module, all launched together:

```
Task tool:
  subagent_type: "general-purpose-sonnet"   # or general-purpose-opus, see the table above
  prompt: |
    Objective: Implement {module} by strict TDD, one test case at a time.

    Scope:
    - Write only tests/test_{module}.py and src/{module}.py. Touch nothing else.
    - Do not modify existing tests, and never skip, delete, or weaken an assertion.

    Inputs:
    - Test cases to implement, in this order: {the Phase 1 list}
    - Read .claude/rules/coding-principles.md and .claude/rules/testing.md first.
    - Existing conventions to follow: {paths of comparable modules}

    Acceptance checks — run these yourself, per cycle, and never skip Red:
      python3 .claude/skills/_shared/run_tests.py \
        --target tests/test_{module}.py --expect fail --label red-{n}
      python3 .claude/skills/_shared/run_tests.py \
        --target tests/test_{module}.py --expect pass --label green-{n}
    A Red that exits 2 with observed=passed/collection_error/no_tests_collected
    is not a Red: fix the test, not the production code, and re-run.

    Output shape:
    ## Cycles completed (case -> red label -> green label)
    ## Files changed
    ## Deviations from the requested test cases, and why
    ## Anything that did not go green

    Context discipline: return this summary only; the run logs stay in
    .claude/logs/ and are referenced by label, not pasted.
```

Then verify rather than trust: re-run `run_tests.py --expect pass` yourself and
read the diff. A reported cycle with no matching `run_tests.py` exit `0` did not
happen. If a cycle came back unfinished, escalate it (`general-purpose-opus` or
`codex-debugger`) instead of re-sending the same prompt to the same tier.

The steps below are the contract the delegate follows — and what the lead runs
directly in the single-trivial-cycle case.

#### Step 1: Write First Test (Red)

```python
# tests/test_{module}.py
def test_{function}_basic():
    """Test the most basic case"""
    result = function(input)
    assert result == expected
```

Confirm the test is red **for the right reason**:

```bash
python3 .claude/skills/_shared/run_tests.py \
  --target tests/test_{module}.py --expect fail --label red-{n}
```

Exit `0` means it genuinely failed. Do not proceed to Green on any other exit
code: on exit `2` read `observed` (see the table above), on exit `1`/`3` read
`error` and `log_file`.

#### Step 2: Implementation (Green)

Write **minimal** code to pass the test:
- Don't aim for perfection
- Hardcoding is OK
- Just make the test pass

Confirm success:

```bash
python3 .claude/skills/_shared/run_tests.py \
  --target tests/test_{module}.py --expect pass --label green-{n}
```

Exit `0` means the test now passes. Exit `2` with `observed: failed` means the
implementation is not there yet — read `failed_tests`.

#### Step 3: Refactoring (Refactor)

Improve while tests still pass:
- Remove duplication
- Improve naming
- Clean up structure

```bash
python3 .claude/skills/_shared/run_tests.py \
  --target tests/test_{module}.py --expect pass --label refactor-{n}
```

When to refactor, and how far, stays a judgment call.

#### Step 4: Next Test

Return to Step 1 with the next test case from the Phase 1 list.

### Phase 3: Completion Check

Run the full quality gates:

```bash
bash .claude/skills/_shared/verify.sh
```

Read the JSON: `overall` is `pass` / `fail` / `no_gates`. Exit `0` means
`overall: pass`; exit `2` means a gate failed **or** no gate could run at all —
inspect `log_file` and `tools`. `no_gates` is a failure by default because a
code-editing session must not be able to declare done with zero checks
executed; if the project genuinely has no configured gates, re-run with
`--allow-no-gates` and verify manually with the project's own commands, and say
in the report that you did so. Exit `1` is bad arguments, `3` the log file could
not be written.

Then check coverage — with a threshold, so the answer is a gate and not a glance
at `term-missing` output:

```bash
python3 .claude/skills/_shared/run_tests.py \
  --target tests/test_{module}.py --expect pass \
  --cov {module} --min-coverage {N} --label coverage
```

`--cov MODULE` (repeatable) requires the `pytest-cov` plugin; without it pytest
reports a usage error and `run_tests.py` exits `1` pointing at `log_file`.
Coverage below `--min-coverage` is exit `2`; `--cov` with no coverage total in
the output is exit `3`, never a silent pass. `--min-coverage` requires `--cov`.
Choosing the threshold is a project decision.

## Report Format

```markdown
## TDD Complete: {Feature Name}

### Test Cases
- [x] {test1}: {description}
- [x] {test2}: {description}
...

### Coverage
- {coverage_percent}% (threshold {min_coverage}%) — from run_tests.py, label `coverage`

### Quality Gates
- verify.sh: {overall} — `{log_file}`

### Implementation Files
- `src/{module}.py`: {description}
- `tests/test_{module}.py`: {N} tests
```

Every `[x]` above must correspond to a `run_tests.py --expect pass` run that
exited `0`; mark nothing complete on the strength of having written it.

## Notes

- Write tests **first** (not after)
- Keep each cycle **small**
- Refactor **after** tests pass
- Prioritize **working code** over perfection
- Where the production code belongs follows the project's existing layout — that
  is a design decision, not a derived path
