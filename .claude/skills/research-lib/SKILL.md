---
name: research-lib
description: Research a library and create comprehensive documentation in .claude/docs/libraries/.
disable-model-invocation: true
---

# Research Library

Research $ARGUMENTS and create documentation in `.claude/docs/libraries/`.

**Scope**: this skill produces documentation only. It never edits source code
and never edits a dependency manifest or lockfile — if the research implies a
version bump, report it as an action item instead of making it.

## 1. Resolve the Document Path

Derive the path once, from the script, and reuse the value everywhere below.
`$ARGUMENTS` is raw user wording (`FastAPI`, `ruamel.yaml`, `@scope/pkg`); the
script normalizes it the same way `lib_inventory.py` normalizes a declared
dependency, so the doc filename and the dependency name always match.

```bash
python3 .claude/skills/_shared/workspace.py --skill research-lib \
  --title "$ARGUMENTS" --create
```

Emits `{ok, skill, slug, paths: {lib_doc}, dirs, created, artifacts, verify}`.
Exit 0 on success, 1 on a bad argument. Use `paths.lib_doc` verbatim from here
on — never re-derive it by hand, and never substitute `$ARGUMENTS.md`.

## 2. Resolve the Version This Project Uses

The declared and locked versions are facts with one correct answer, so read
them instead of asking the web:

```bash
python3 .claude/skills/update-lib-docs/lib_inventory.py --library "$ARGUMENTS"
```

The `dependencies` array carries `{name, declared_spec, declared_in,
locked_version, locked_in, ecosystem}`. `> **Version Checked**:` records
`locked_version` when a lockfile pins one, otherwise the version satisfying
`declared_spec`. If `dependencies` is empty the library is not (yet) a
dependency of this project — record the version you are documenting against and
say so in `## Constraints & Notes`.

Exit codes: 0 ok, 1 bad argument, 2 a manifest could not be parsed
(`manifest_errors`), 3 a library doc could not be read (`read_error`). On a
non-zero exit, stop and report — do not fill the version in from a web search.

Newer upstream releases are research findings, not the project's version: note
them under `## Constraints & Notes` as an upgrade consideration. The blockquote
is the only place a version number lives.

## Research Items

### Primary Tool: General-Purpose Subagent (Opus)

Use `general-purpose-opus` with WebSearch/WebFetch for comprehensive library
research. Pass the resolved path and version into the prompt:

```
Agent tool:
  subagent_type: "general-purpose-opus"
  prompt: |
    Research: {library}. Find official documentation, key features,
    constraints, best practices, known issues, and usage patterns.
    Use WebSearch and WebFetch to gather information.
    The version this project uses is {locked_version or declared_spec};
    document against that version, and note newer releases separately.
    Save results to {paths.lib_doc} using the template in
    .claude/skills/research-lib/SKILL.md.
    List every URL you consulted under ## References.
    Return concise summary.
```

### Fallback: WebSearch/WebFetch

If the subagent is unavailable, verify via manual web search:

- Official documentation
- GitHub README
- PyPI / npm page
- Latest release notes

Record every source you used in `## References`; a research note whose sources
are only in the conversation cannot be audited later.

### Content to Document

1. **Basic Information**
   - Official name, license
   - Official URL
   - Installation command

2. **Core Features**
   - Main features
   - Basic usage (code examples)

3. **Constraints & Notes**
   - Known limitations
   - Conflicts with other libraries
   - Performance characteristics
   - Async/sync considerations

4. **Usage Patterns in This Project**
   - Recommended usage
   - Patterns to avoid

5. **Troubleshooting**
   - Common errors and solutions

## Output Location

`paths.lib_doc` from step 1 — the only derivation of this path.

## Documentation Template

```markdown
# {Library Name}

> **Last Updated**: {YYYY-MM-DD}
> **Version Checked**: {declared or locked version in this project}

## Overview

- **License**: {license}
- **Official URL**: {url}
- **Installation**: `{install command}`

## Core Features

{Description of main features}

## Basic Usage

```python
{Code example}
```

## Constraints & Notes

- {Limitation 1}
- {Limitation 2}

## Recommended Patterns

### Do

```python
{Good pattern}
```

### Don't

```python
{Anti-pattern}
```

## Troubleshooting

### {Error message}

**Cause**: {cause}
**Solution**: {solution}

## References

- [Official Docs]({url})
- [GitHub]({url})
```

The `> **Last Updated**` / `> **Version Checked**` blockquote is mandatory, not
decoration: `lib_inventory.py` parses exactly those two lines, and a doc without
them is invisible to `update-lib-docs` — never stale, never undocumented, never
maintained.

## Validate the Document

Both checks are gates. Do not report completion until both exit 0.

```bash
python3 .claude/skills/_shared/validate_doc.py --contract lib-doc \
  --file <paths.lib_doc>
python3 .claude/skills/_shared/workspace.py --skill research-lib \
  --slug <slug> --verify
```

`validate_doc.py` exit codes:

- **1** — the file does not exist or could not be read. The delegated subagent
  did not write it (or wrote it elsewhere); the payload has no
  `sections_missing`. Re-delegate with `paths.lib_doc`; do not hand-edit a
  different path.
- **2** — the file exists but violates the contract. `sections_missing` lists
  absent `## ` sections (`Overview`, `Core Features`, `Constraints & Notes`,
  `References`) and `metadata_missing` lists absent metadata lines
  (`Last Updated`, `Version Checked`). Fill those in and re-run.

`workspace.py --verify` exit 2 with `verify.empty` containing `lib_doc` means
the file exists but is a stub (under 20 non-whitespace characters) — a summary
was returned without real content.
