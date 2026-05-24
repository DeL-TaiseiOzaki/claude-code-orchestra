---
name: init
description: Analyze project structure and populate the "Repository Identity" section of CLAUDE.md (Zone B) plus AGENTS.md.
disable-model-invocation: true
---

# Initialize Project Configuration

Analyze this project and populate the **Repository Identity (Zone B)** section of `CLAUDE.md`, and mirror the same information into the project-specific sections of `AGENTS.md`.

## CLAUDE.md 3-zone layout (recap)

```
Zone A — Orchestra concept & template base (template-owned)
# @orchestra:template-boundary
Zone B — Repository Identity  ← this skill writes here
# @orchestra:repo-boundary
Zone C — Working state (sessions, features, design pointers)
```

## Important

- Touch ONLY Zone B of `CLAUDE.md`. Never modify Zone A (above `@orchestra:template-boundary`) or Zone C (below `@orchestra:repo-boundary`).
- For `AGENTS.md`, do NOT modify the "Extensions" section and below — only update the top project-specific sections.
- If `CLAUDE.md` lacks the 3-zone markers (legacy layout), ask the user to run `./scripts/update.sh` first. Do not hand-insert markers.

## Steps

### 1. Project Analysis

Find these files to identify the tech stack:

- `package.json` → Node.js/TypeScript project
- `pyproject.toml` / `setup.py` / `requirements.txt` → Python project
- `Cargo.toml` → Rust project
- `go.mod` → Go project
- `Makefile` / `Dockerfile` → Build/deploy config
- `.github/workflows/` → CI/CD config

Also detect:

- npm scripts / poe tasks / make targets → Common commands
- Major libraries/frameworks

### 2. Ask User

Use AskUserQuestion tool to ask:

1. **Project overview**: What does this project do? (1-2 sentences)
2. **Code language**: English or Japanese for comments/variable names?
3. **Additional rules**: Any other coding conventions to follow?

### 3. Update CLAUDE.md Zone B

First verify the 3-zone markers exist:

```bash
grep -q "@orchestra:template-boundary" CLAUDE.md && grep -q "@orchestra:repo-boundary" CLAUDE.md
```

If either marker is missing, stop and ask the user to run `./scripts/update.sh` to migrate the file; the updater auto-migrates legacy single-boundary layouts.

Replace the content **between** the two markers with the following template (keep the marker lines and their ━ separators intact). Use the Edit tool by anchoring on the full block between the two boundary box lines.

```markdown
## Repository Identity

<!-- Managed by /init. Re-run /init to refresh. -->

### Project Overview

{User's answer to "what does this project do"}

### Language Settings

- **Thinking/Reasoning**: English
- **Code**: {Based on analysis — English or Japanese}
- **User Communication**: Japanese

### Tech Stack

- **Language**: {Detected language}
- **Package Manager**: {Detected tools}
- **Dev Tools**: {Detected tools}
- **Main Libraries**: {Detected libraries}

### Common Commands

```bash
{npm run dev / poe test / make build etc.}
```
```

### 4. Partial Update of AGENTS.md

Mirror the same information into `AGENTS.md` so Codex sees it. Update only the top section (up to the first `---`) with this format:

```markdown
# Project Overview

{User's answer}

## Language Settings

- **Thinking/Reasoning**: English
- **Code**: {Based on analysis - English or Japanese}
- **User Communication**: Japanese

## Tech Stack

- **Language**: {Detected language}
- **Package Manager**: {Detected tools}
- **Dev Tools**: {Detected tools}
- **Main Libraries**: {Detected libraries}

## Common Commands

```bash
{Detected commands}
```
```

### 5. Check Unnecessary Rules

Check rules in `.claude/rules/` and suggest removing unnecessary ones:

- Non-Python project → `dev-environment.md` (uv/ruff/ty) may not be needed
- No-test project → `testing.md` may not be needed

### 6. Report Completion

Report to user (in Japanese):

- Detected tech stack
- Files updated (`CLAUDE.md` Zone B, `AGENTS.md`)
- Recommended rules to remove (if any)
