# PR #82 (Cross-CLI Invocation + Skill Robustness Audit Fixes) -- Fable Review

## Context

Final pre-merge review of ~60 files / +12k/-1.1k lines produced by nine
implementation agents and six audit agents against a frozen interface spec.
Suite green (929 tests), `check.sh` 8/8. This review judges architectural
coherence, not defect presence; I am the first reviewer outside the framing.

## Analysis

**Principle consistency.** "Script the mechanics, gate the shape, fail loudly"
is applied consistently, not stretched. I looked for a shape gate doing
judgment's work and did not find one: `run_tests.py --expect`, `--expect-files`,
`scope_empty`, `check_ownership.py`, and `simplify_gate.py` all encode facts the
caller already knows (dispatch count, red/green intent, ownership lists,
baseline), not judgments. The "must stay prose" list (routing, verdicts, prompt
composition) survived implementation intact. The reverse failure -- judgment
demoted to prose while a script quietly decides -- is guarded by
`verify_delegation.py`'s `not_automated` field, which names what the heuristics
cannot see instead of implying coverage. That is unusually honest design.

**Expectation gates and the routing-around risk.** The gates are well-grounded:
`team-execute/SKILL.md` derives `{N}` from "the number of teammates you actually
dispatched" and explains in-line why the flag exists. Gaming it requires
actively lying about a value with an obvious ground truth. One place does have a
habituation risk: `verify_delegation.py` counts *any* removed non-blank line as
a finding, so `ok: false` + exit 2 will occur on virtually every real diff.
Since `verdict` is always `needs-review` regardless, `ok` carries little signal
here and agents will learn that exit 2 from this one script is routine. That is
tolerable because the script's contract is "read the diff", not "pass" -- but it
is the one gate whose failure state is the common case, and it should be watched.

**`_shared/` size.** Growth from 6 to 10 helpers is earned: each maps to one
verb, there are no cross-script imports, and the one deliberate duplication (two
slug normalizations) is pinned by `test_slug_agreement.py`. The contract now has
two documented carve-outs (`checkpoint.py` human report, `lib_inventory.py
--today`). Two is fine; the pattern of "documented exception" must not become
the release valve for every future inconvenience.

**The three reductions.** Correct, and the line is in the right place. The user
asked for "as much as possible in .py" as a *means*; the stated *end* was
robustness. `detect_stack.py` still runs and still reports -- it stopped
authoring conclusions. A wrong `uv run ty check` landing in DESIGN.md as fact is
strictly less robust than prose. Deleting the commit-count summary fallback is
the same call: metrics substituting for meaning. This is a principled refusal of
the letter in service of the intent, and it is recorded in the design log where
the user can overrule it.

**Coherence across 15 SKILL.md files.** One dialect, not six: the frozen
interface spec worked. Exit vocabulary, `{paths.x}` references, and expectation
flags are cited uniformly; a new contributor can pattern-match from any two
existing skills. `validate_doc.py`'s 13 contracts stay honest because every
list is pinned to its template by a test -- the registry cannot silently rot
without a test failure.

**The scoped skepticism items.** The no-`clean`-verdict design is principled,
not theater: the source-grep test guards the *interface property* (no automated
accept path exists to be cited), which is exactly what makes the Guardrails
non-bypassable. The `.claude/docs/reviews/` exclusion is self-serving in origin
but correct in substance -- review notes are evidence records that must quote
legacy paths, the same rationale as the logs/research exclusions, and the
directory is inert at runtime. The ~170KB of audit notes: the PLAN and INTERFACE
docs are durable design record; the six per-group notes carry file:line
references already invalidated by the fixes they motivated. Clutter, but
contained (the installer ships only `.gitkeep`, not this repo's notes).

## Recommendation

**Merge as is.** No blocking changes. Two follow-ups to file, not to gate the
merge on: (1) monitor whether `verify_delegation.py`'s always-exit-2-in-practice
behavior trains agents to skim; if so, split "evidence present" from "violated
expectation" in its exit codes without adding an accept verdict. (2) Add a
retention rule for `.claude/docs/reviews/`: per-group evidence notes may be
pruned once their findings are fixed and logged; PLAN/INTERFACE-class documents
stay.

## Risks & Mitigations

- **Expectation fatigue**: a wrong `{N}` fails a correct run. Mitigated by
  grounding every expectation in caller-known facts; keep that discipline a
  review criterion for future gates.
- **Contract accretion**: 13 clauses + 2 exceptions. Mitigated by the
  machine-enforced core in `test_shared_script_contract.py`; require any third
  exception to justify itself in the design log.
- **Spec-frozen wrong names**: the interface froze names before implementation;
  any latent misfit is now load-bearing. Mitigated by the template-pinning
  tests, which make renames a visible test change.

## Dissenting Considerations

- The user explicitly asked for more `.py`; the reductions deliver less in three
  places. If the user weighs the letter of the request over the recorded
  rationale, decision 54 in `TEMPLATE_DESIGN_LOG.md` is the overrule point.
- A `clean` verdict for trivially empty-finding diffs would cut real friction;
  the team chose principle over convenience. I concur, but it is a genuine cost
  paid on every delegated run forever.
- Committing 170KB of point-in-time audit evidence sets a precedent; the next
  audit should not assume the repo is its archive.
