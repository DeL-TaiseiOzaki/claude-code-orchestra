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
doc's `> **Last Updated**` / `> **Version Checked**` metadata and cross-checks
declared project dependencies:

```bash
python3 .agents/skills/update-lib-docs/lib_inventory.py [--stale-days N]
```

Emits `{ok, libraries_dir, stale_days, libraries:[...], counts, undocumented,
declared_dependencies}`. Each entry in `libraries` carries `file`, `name`,
`last_updated`, `version_checked`, `age_days`, `stale`, `has_metadata`.
`undocumented` lists declared dependencies (from `pyproject.toml` /
`package.json`) that have no doc file at all. Default staleness threshold is
90 days; pass `--stale-days` to change it.

This run's scope is exactly two sets from that output: entries with
`stale: true`, and every name in `undocumented`. Everything else is already
current — skip it.

### 2. Web Search for Latest Info

For each `stale` library and each `undocumented` dependency, search for:

- Latest version
- Breaking changes
- Deprecated features
- New features
- Security updates

### 3. Update Documents

For each stale library, update its existing doc; for each undocumented
dependency, create a new doc following the same template (see
`research-lib`'s documentation template for the full section layout):

1. Update version information
2. Add new features/constraints
3. Mark deprecated APIs
4. Update code examples if needed
5. Record update date at the top

### 4. Validate Updated Documents

After updating or creating a doc, validate it against the `lib-doc` contract:

```bash
python3 .agents/skills/_shared/validate_doc.py --contract lib-doc --file .agents/docs/libraries/{library}.md
```

Exit 0 means `## Overview`, `## Core Features`, `## Constraints & Notes`, and
`## References` are all present. A non-zero exit means the JSON's
`sections_missing` lists what's absent — fill those sections in before moving
on; do not report the update as complete with sections still missing.

### 5. Check Impact on Code

After updating docs, verify:

- Using any deprecated APIs?
- Any breaking change impacts?
- Need to update project dependencies?

## Key Items to Check

| Category | What to Look For |
|----------|------------------|
| Security | CVEs, security patches |
| Breaking | API changes, removed features |
| Deprecated | APIs marked for removal |
| Performance | Optimization improvements |
| New Features | Useful additions |

## Update Format

Add update notice at top of file:

```markdown
# {Library Name}

> **Last Updated**: {Date}
> **Version Checked**: {version}

## Recent Changes

- {Change 1}
- {Change 2}

---

{Rest of documentation}
```

## Report

After updating, report to user (in Japanese):

- Which libraries were updated
- Significant changes found
- Any action items for the project
