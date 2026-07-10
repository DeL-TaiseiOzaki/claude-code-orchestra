# _shared/ — Bundled Runtime for Skills

`_shared/` is **NOT a skill** — it is a bundled runtime library of deterministic
helpers. Skills must never invoke other skills, but **MAY** depend on `_shared/`
scripts and format documents.

## Contents

| File | Description |
|------|-------------|
| `work-log-format.md` | Canonical work-log template for Agent Teams teammates (format doc, not a script). |
| `validate_work_log.py` | Validate a teammate work log against the `work-log-format.md` contract. |
| `append_zone_c_block.py` | Append a `## Current Feature/Bug Fix/Project` block to CLAUDE.md Zone C. |
| `update_design.py` | Append Key Decisions rows and/or section content to `.claude/docs/DESIGN.md`. |

## Writer Safety Contract

Both Python scripts follow the same safety contract:

- **Typed JSON input** via `--input <file>` (never raw markdown from argv).
- **Dry-run by default**: without `--apply`, produces a preview file under `.claude/logs/` and changes nothing.
- **Atomic replace** on `--apply`: writes to a temp file in the same directory, validates structure, then `os.replace()` over the original.
- **Concurrent-modification guard**: content hash is checked before replacing; if the file changed since load, the script exits without writing.
- **Exit codes**: `0` = preview/applied/no-op, `1` = bad args/input-schema, `2` = document-structure invalid, `3` = ID conflict/concurrent modification/write failure.
- **Single JSON object** printed to stdout on every exit.
