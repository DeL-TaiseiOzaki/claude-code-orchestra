# _shared/ — Bundled Runtime for Skills

`_shared/` is **NOT a skill** — it is a bundled runtime library of deterministic
helpers. Skills must never invoke other skills, but **MAY** depend on `_shared/`
scripts and format documents.

## Automation Boundary

Skills are markdown because most of what they describe is judgment. Scripts
exist because some of what they describe is not. The split is deliberate:

| Belongs in a script | Stays in `SKILL.md` |
|---------------------|---------------------|
| Deriving names, slugs, and artifact paths | Deciding the mode, route, or priority |
| Reading, writing, and validating document structure | Writing briefs, reports, and prose |
| Invoking external processes | Composing the prompt *content* |
| Collecting inventories and running quality gates | Interpreting the results |

The test: **if a step has exactly one correct output for a given input, it is a
script.** Everything else stays markdown, where an agent can reason about it.

Scripting a judgment step makes the skill rigid and wrong in new situations.
Leaving a mechanical step in prose makes it silently inconsistent — two phases
derive different slugs, a required section is quietly omitted, an error is
swallowed. Both failure modes are worse than the split.

## Contents

| File | Description |
|------|-------------|
| `work-log-format.md` | Canonical work-log template for Agent Teams teammates (format doc, not a script). |
| `workspace.py` | Resolve, create, and verify a skill's slug, team name, and artifact paths. Single source of truth for cross-phase naming. |
| `codex_consult.py` | Invoke the Codex CLI safely: prompt via file or stdin, stdin closed, stdout/stderr captured to `.agents/logs/codex/`, full diagnostics as JSON. |
| `cli_consult.py` | Invoke a peer CLI agent (Claude Code, Gemini CLI) as a subagent under the same contract, read-only unless `--write-access`. Cross-CLI rules: `.agents/rules/cli-execution.md`. |
| `validate_doc.py` | Validate a markdown document (work log, lib doc, spike/bug/review report) against a named `## ` section contract. |
| `append_state_block.py` | Append a `## Current Feature/Bug Fix/Project` block to `.agents/STATE.md`. |
| `update_design.py` | Append Key Decisions rows and/or section content to `.agents/docs/DESIGN.md`. |
| `verify.sh` | Run the configured quality gates (ruff check, ruff format, ty, pytest) and report one JSON summary. |

## Shared Script Contract

Every script in `_shared/` follows these conventions, and skill-bundled helpers
follow them too, so callers can handle all of them identically:

- **Exactly one JSON object on stdout** — on every error path without
  exception, including argument errors, which are reported as JSON rather than
  as `argparse` usage text on stderr; and on the success path of every helper
  whose result the caller consumes. Long output goes to a file whose path is
  reported inside that JSON. (`checkpoint.py` is the one helper whose success
  path prints a human-readable report instead: it generates files, and the
  report says what it wrote.)
- **`--project-root DIR`** on every bundled Python helper, to relocate the
  repository root so the script can be exercised against a fixture directory
  without touching the real project. (`gather_diff.sh` and `repro.sh` resolve
  the root from their own location instead.)
- **Errors are never swallowed.** A failure surfaces as a JSON field *and* a
  non-zero exit code. Silence always means success.
- **Shared exit-code vocabulary**:

  | Code | Meaning |
  |------|---------|
  | `0` | ok / preview / no-op |
  | `1` | bad arguments or unreadable input |
  | `2` | contract violation — missing artifact, invalid structure, missing required section |
  | `3` | external failure — subprocess failed or timed out, write failure, concurrent modification |

- **Graceful degradation**: an absent optional path is reported as `null` or an
  empty list and stays exit `0`. Only genuinely broken states are errors.
- **Standard library only.** No third-party imports, so the scripts run wherever
  `python3` does.

## Writer Safety Contract

`append_state_block.py` and `update_design.py` mutate documents that the user
owns, so they add four guarantees on top of the shared contract:

- **Typed JSON input** via `--input <file>` (never raw markdown from argv).
- **Dry-run by default**: without `--apply`, produces a preview file under
  `.agents/logs/` and changes nothing.
- **Atomic replace** on `--apply`: writes to a temp file in the same directory,
  validates structure, then `os.replace()` over the original.
- **Concurrent-modification guard**: the content hash is checked before
  replacing; if the file changed since load, the script exits without writing.
