# Library Research Task

When delegating library research, use a general-purpose subagent (Opus) with WebSearch/WebFetch.

> Gemini CLI is specialized for multimodal processing only. For research tasks, use general-purpose subagent.

## Prompt Template

When assigning library research to a general-purpose subagent, include these research items:

```
Research the library "{library_name}" comprehensively.

Use WebSearch to find:
- Official documentation
- GitHub README, Issues, Discussions
- PyPI / npm pages
- Latest blog posts, tutorials (2025-2026)

---

Provide documentation in this structure:

## Basic Information
- Library name, current version, license
- Official documentation URL
- Installation method (pip, npm, etc.)
- Python/Node version requirements

## Core Features
- Main features and primary use cases
- Basic usage with code examples
- Key APIs and their purposes

## Important Constraints & Notes
- Known limitations
- Conflicts with other libraries
- Performance characteristics
- Breaking changes in recent versions
- Async/sync requirements
- Thread-safety considerations

## Common Patterns
- Recommended initialization patterns
- Error handling patterns
- Configuration best practices
- Testing approaches

## Troubleshooting
- Common errors and solutions
- Debugging methods
- Where to find help (Discord, GitHub Issues, etc.)

---

Output in markdown format suitable for saving to .claude/docs/libraries/{library_name}.md
Output documentation content in English.
```

## Example Invocation

```
# Via general-purpose subagent (recommended)
Agent tool:
  subagent_type: "general-purpose"
  prompt: |
    Research the library "httpx" comprehensively.
    Use WebSearch and WebFetch to gather information from official docs,
    GitHub, PyPI, and recent blog posts.

    Save results to .claude/docs/libraries/httpx.md
    Return concise summary (key features, constraints, recommendations).
```

## Workflow

1. **Launch general-purpose subagent** (background)
   - Subagent uses WebSearch/WebFetch for research

2. **Save output to docs**
   - Subagent saves findings to `.claude/docs/libraries/{library}.md`

3. **Update existing docs**
   - If documentation already exists, compare and update

## Output Location

All library documentation should be saved to:
```
.claude/docs/libraries/{library-name}.md
```

## When to Use

- Introducing a new library to the project
- Checking library specifications before implementation
- Updating outdated library documentation
- Investigating library conflicts or issues
- When user says "research this library", "look into this library"

## Integration with Codex

After research is complete:
1. Documentation is saved to `.claude/docs/libraries/`
2. Codex can reference this when reviewing code or refactoring
3. Ensures library constraints are respected across all agents
