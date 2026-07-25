---
name: update-lib-docs
description: Update library documentation in .agents/docs/libraries/ with latest information from web search.
disable-model-invocation: true
---

# Update Library Documentation

Update documentation in `.agents/docs/libraries/` with latest information.

## Steps

### 1. Inventory Library Docs

Run `lib_inventory.py` instead of eyeballing the directory — it scans each
doc's `> **Last Updated**` / `> **Version Checked**` metadata, resolves the
version the project declares and locks, and cross-checks declared
dependencies:

```bash
python3 .agents/skills/update-lib-docs/lib_inventory.py \
  [--stale-days N] [--today YYYY-MM-DD] [--library NAME] [--project-root DIR]
```

Emits `{ok, libraries_dir, stale_days, today, library, libraries, counts,
missing_metadata, undocumented, declared_dependencies, dependencies, sources,
manifest_errors, warnings, artifacts}`.

| Field | Meaning |
|-------|---------|
| `libraries[]` | `file`, `name`, `last_updated`, `version_checked`, `age_days`, `stale`, `stale_reasons`, `has_metadata`, `read_error`, `declared_spec`, `declared_in`, `locked_version`, `locked_in`, `ecosystem`, `version_drift`, `version_drift_basis`, `version_drift_note` |
| `counts` | `total`, `stale`, `missing_metadata`, `read_errors`, `version_drift`, `drift_unknown` |
| `missing_metadata` | Doc filenames with no `Last Updated` / `Version Checked` blockquote — invisible to staleness until fixed |
| `undocumented` | Declared dependencies with no doc file at all |
| `dependencies` | Version resolution per package: `declared_spec` + `locked_version` and where each came from |
| `sources` | Every dependency table actually parsed: `file`, `table`, `ecosystem`, `kind` (`manifest`/`lock`), `dependency_count` |
| `manifest_errors` | `{file, error}` for a manifest or lockfile that failed to parse |
| `warnings` | e.g. a manifest with no readable dependency table, or no lockfile found |

`stale` is the OR of two signals, and `stale_reasons` says which fired:

- `age` — `age_days > --stale-days` (default 90).
- `version_drift` — `version_checked` disagrees with `locked_version`, with a
  pinned `declared_spec`, or falls below the spec's lower bound.
  `version_drift` is `true`/`false` only when the comparison is decidable;
  `null` plus `version_drift_note` means it is not (no lockfile behind an open
  range, a non-numeric version). `null` is not "clean" — read the note.

Exit codes: **0** ok, **1** bad argument (`--today` not `YYYY-MM-DD`,
`--library` not a package name, `--project-root` missing), **2** a manifest or
lockfile could not be parsed, **3** a library doc could not be read. If `ok` is
`false`, stop and report the `manifest_errors` / `read_error` entries — an empty
scope from a broken manifest is not success.

This run's scope is the union of three lists from that output: entries with
`stale: true`, every doc in `missing_metadata`, and every name in
`undocumented`. Everything else is already current — skip it.

### 2. Web Search for Latest Info

For each library in scope, search for:

- Breaking changes
- Deprecated features
- New features
- Security updates
- Newer upstream releases (an upgrade consideration, not the version recorded
  in the doc — `> **Version Checked**:` is the version *this project* uses,
  which the inventory already resolved)

### 3. Update Documents

Derive each doc path from the same authority research-lib uses, so an update
and a creation can never disagree about the filename:

```bash
python3 .agents/skills/_shared/workspace.py --skill research-lib \
  --title "{library}" --create
```

Then, for each stale library, update `paths.lib_doc`; for each undocumented
dependency, create it following the same template (see `research-lib`'s
documentation template for the full section layout):

1. Update `> **Version Checked**:` to the inventory's `locked_version`
   (or the version satisfying `declared_spec` when nothing is locked)
2. Update `> **Last Updated**:` to today
3. Add new features/constraints
4. Mark deprecated APIs
5. Update code examples if needed

### 4. Validate Updated Documents

After updating or creating a doc, validate it against the `lib-doc` contract:

```bash
python3 .agents/skills/_shared/validate_doc.py --contract lib-doc \
  --file <paths.lib_doc>
```

Exit 0 means the four required `## ` sections (`Overview`, `Core Features`,
`Constraints & Notes`, `References`) *and* the `Last Updated` / `Version
Checked` metadata lines are all present. Exit 1 means the file does not exist
or could not be read (there is no `sections_missing` on that path — check the
path before editing anything). Exit 2 means the doc violates the contract:
`sections_missing` lists absent sections, `metadata_missing` lists absent
metadata lines. Fill both in; do not report the update as complete with either
non-empty.

Re-running step 1 is the completion check: a doc you updated must no longer
appear in `stale`, `missing_metadata`, or `undocumented`.

### 5. Check Impact on Code

After updating docs, verify:

- Using any deprecated APIs?
- Any breaking change impacts?
- Need to update project dependencies?

Editing a manifest or source file is outside this skill's documentation scope.
If step 5 leads to any change outside `.agents/docs/libraries/`, run the gates
before reporting:

```bash
bash .agents/skills/_shared/verify.sh
```

Exit 0 means the gates passed; exit 2 means a gate failed or no gates ran. Do
not report completion on a non-zero exit.

## Key Items to Check

| Category | What to Look For |
|----------|------------------|
| Security | CVEs, security patches |
| Breaking | API changes, removed features |
| Deprecated | APIs marked for removal |
| Performance | Optimization improvements |
| New Features | Useful additions |

## Update Format

There is one library-doc template, in `research-lib/SKILL.md` under
`## Documentation Template`, and it is the version pinned by
`tests/test_validate_doc.py` against the `lib-doc` contract. Do not keep a
second copy here: a template that no test pins is how the two skills came to
disagree about the metadata block in the first place.

An update edits the existing document in place:

- Refresh the `> **Last Updated**` / `> **Version Checked**` blockquote that
  already sits directly under the H1 — it is the only place a version lives, so
  do not add a second version line anywhere.
- Optionally add a `## Recent Changes` list after the blockquote; it is not a
  contract section, so keep the four required sections intact.

## Report

After updating, report to user (in Japanese):

- Which libraries were updated
- Significant changes found
- Any action items for the project
