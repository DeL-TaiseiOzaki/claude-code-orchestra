# Library Research Task for Gemini

When delegating library research to Gemini, use this prompt template.

## Prompt Template

```
Research the library "{library_name}" comprehensively.

Use Google Search to find:
- Official documentation
- GitHub README, Issues, Discussions
- PyPI / npm pages
- Latest blog posts, tutorials (2024-2025)

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

```bash
# Basic library research
gemini -p "Research the library 'httpx' comprehensively.

Use Google Search to find:
- Official documentation
- GitHub README, Issues, Discussions
- PyPI pages
- Latest blog posts, tutorials (2024-2025)

[Template structure as above...]
" 2>/dev/null

# Research with specific focus
gemini -p "Research 'pydantic' v2 with focus on:
- Migration from v1 to v2
- Performance improvements
- New validation patterns
- Breaking changes

[Template structure as above...]
" 2>/dev/null
```

## Workflow

1. **Run Gemini research** (background)
   ```bash
   gemini -p "Research: {library}" 2>/dev/null
   ```

2. **Save output to docs**
   - Claude saves Gemini's output to `.claude/docs/libraries/{library}.md`

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

After Gemini researches a library:
1. Documentation is saved to `.claude/docs/libraries/`
2. Codex can reference this when reviewing code or refactoring
3. Ensures library constraints are respected across all agents
