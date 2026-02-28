# CLAUDE.md Best Practices — Comprehensive Research

> Research date: 2026-02-26
> Sources: Anthropic official docs, community blogs, GitHub repos, practitioner experiences

---

## Table of Contents

1. [What is CLAUDE.md](#1-what-is-claudemd)
2. [Official Anthropic Guidance](#2-official-anthropic-guidance)
3. [Memory Hierarchy & File Locations](#3-memory-hierarchy--file-locations)
4. [Recommended Structure & Sections](#4-recommended-structure--sections)
5. [What to Include vs Exclude](#5-what-to-include-vs-exclude)
6. [Length & Brevity Guidelines](#6-length--brevity-guidelines)
7. [Progressive Disclosure & Modular Rules](#7-progressive-disclosure--modular-rules)
8. [Formatting & Emphasis Best Practices](#8-formatting--emphasis-best-practices)
9. [Anti-Patterns & Common Mistakes](#9-anti-patterns--common-mistakes)
10. [Advanced Features](#10-advanced-features)
11. [CLAUDE.md vs AGENTS.md vs .cursorrules](#11-claudemd-vs-agentsmd-vs-cursorrules)
12. [How Anthropic Teams Use CLAUDE.md](#12-how-anthropic-teams-use-claudemd)
13. [Community Examples & Templates](#13-community-examples--templates)
14. [Self-Improving CLAUDE.md Workflow](#14-self-improving-claudemd-workflow)
15. [Key Recommendations Summary](#15-key-recommendations-summary)

---

## 1. What is CLAUDE.md

CLAUDE.md is a special Markdown file that Claude Code reads at the start of every conversation. It provides persistent context that Claude cannot infer from code alone — bash commands, coding conventions, testing procedures, workflow rules, and project-specific instructions.

The filename is **case-sensitive**: it must be exactly `CLAUDE.md` (uppercase CLAUDE, lowercase .md).

**Key insight**: Claude Code injects a system reminder with your CLAUDE.md: *"IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task."* This means Claude may ignore contents it deems irrelevant, which has significant implications for how you write the file.

---

## 2. Official Anthropic Guidance

### From code.claude.com/docs/en/best-practices:

- Run `/init` to generate a starter CLAUDE.md based on your project structure, then refine over time
- There is **no required format** — keep it short and human-readable
- Include Bash commands, code style, and workflow rules
- CLAUDE.md is loaded every session, so only include things that apply broadly
- For domain knowledge or workflows only relevant sometimes, use **skills** instead
- Keep it concise: for each line, ask *"Would removing this cause Claude to make mistakes?"* — if not, cut it
- **Bloated CLAUDE.md files cause Claude to ignore your actual instructions**
- Check CLAUDE.md into git so your team can contribute
- The file compounds in value over time

### From code.claude.com/docs/en/memory:

- Be specific: "Use 2-space indentation" beats "Format code properly"
- Use structure to organize: bullet points grouped under descriptive markdown headings
- Review periodically: update memories as your project evolves

### Anthropic's Include/Exclude Table (Official):

| Include | Exclude |
|---------|---------|
| Bash commands Claude can't guess | Anything Claude can figure out by reading code |
| Code style rules that differ from defaults | Standard language conventions Claude already knows |
| Testing instructions and preferred test runners | Detailed API documentation (link to docs instead) |
| Repository etiquette (branch naming, PR conventions) | Information that changes frequently |
| Architectural decisions specific to your project | Long explanations or tutorials |
| Developer environment quirks (required env vars) | File-by-file descriptions of the codebase |
| Common gotchas or non-obvious behaviors | Self-evident practices like "write clean code" |

---

## 3. Memory Hierarchy & File Locations

Claude Code supports a sophisticated hierarchy of memory files:

| Memory Type | Location | Purpose | Sharing |
|-------------|----------|---------|---------|
| **Managed policy** | `/etc/claude-code/CLAUDE.md` (Linux) | Organization-wide instructions | All users |
| **Project memory** | `./CLAUDE.md` or `./.claude/CLAUDE.md` | Team-shared project instructions | Team (git) |
| **Project rules** | `./.claude/rules/*.md` | Modular, topic-specific rules | Team (git) |
| **User memory** | `~/.claude/CLAUDE.md` | Personal preferences (all projects) | Just you |
| **Project local** | `./CLAUDE.local.md` | Personal project-specific prefs | Just you |
| **Auto memory** | `~/.claude/projects/<project>/memory/` | Claude's automatic notes | Just you |

### Discovery behavior:
- Starting from cwd, Claude recurses **up** to (but not including) `/` and reads any CLAUDE.md or CLAUDE.local.md files
- CLAUDE.md in **child** directories load **on demand** when Claude reads files in those directories
- More specific instructions take precedence over broader ones
- All `.md` files in `.claude/rules/` are automatically loaded with same priority as `.claude/CLAUDE.md`
- CLAUDE.local.md files are automatically added to `.gitignore`

---

## 4. Recommended Structure & Sections

Based on synthesis of official docs, community best practices, and well-crafted examples:

### Minimal Effective Structure (~30-60 lines)

```markdown
# Project Name

Brief one-paragraph description of the project and tech stack.

## Commands

- Build: `npm run build`
- Test: `npm test`
- Test single: `npm test -- path/to/test`
- Lint: `npm run lint`
- Type check: `npx tsc --noEmit`

## Code Style

- Use ES modules (import/export), not CommonJS (require)
- Destructure imports when possible
- Use TypeScript strict mode
- Prefer named exports over default exports

## Workflow

- Always typecheck after making code changes
- Run single test files for performance, not the whole suite
- Create feature branches, not commits to main

## Architecture

- [Key architectural decisions specific to this project]
- [Non-obvious module relationships]

## Gotchas

- [Project-specific warnings and non-obvious behaviors]
```

### Extended Structure (for larger projects, still < 200 lines)

```markdown
# Project Name

[One-paragraph summary]

## Commands
[Build, test, lint, deploy commands]

## Code Style & Conventions
[Formatting preferences, naming conventions, import ordering]

## Architecture
[Key decisions, module structure, data flow]

## Testing
[Test framework, patterns, fixture locations]

## Workflow & Git Conventions
[Branch naming, commit messages, PR process]

## Environment
[Required env vars, setup quirks, platform-specific notes]

## Gotchas & Warnings
[Non-obvious behaviors, known issues, common pitfalls]

## Compaction Instructions (optional)
[What to preserve when context is compacted]
```

---

## 5. What to Include vs Exclude

### MUST Include:
1. **Build/test/lint commands** — Claude will use these exact commands
2. **Code style rules that differ from defaults** — only non-obvious preferences
3. **Project-specific architectural decisions** — things Claude can't infer
4. **Testing conventions** — preferred runners, patterns, fixture locations
5. **Common gotchas** — non-obvious behaviors specific to your project
6. **Environment requirements** — required env vars, setup quirks

### MUST Exclude:
1. **Anything Claude can infer from code** — don't describe what it can read
2. **Standard language conventions** — Claude already knows them
3. **Detailed API documentation** — link to docs instead, or use @imports
4. **Information that changes frequently** — becomes stale quickly
5. **Long explanations or tutorials** — move to skills or separate docs
6. **File-by-file codebase descriptions** — let Claude explore
7. **Self-evident practices** — "write clean code" wastes tokens
8. **Linter rules** — use actual linters; "Never send an LLM to do a linter's job"

---

## 6. Length & Brevity Guidelines

### Community Consensus:
- **Target: < 300 lines** (general consensus)
- **Ideal: < 100 lines** (many practitioners)
- **HumanLayer example: < 60 lines** for root CLAUDE.md
- **Anthropic recommendation: no official limit**, but "keep it short and human-readable"

### Why Brevity Matters:
1. Claude injects a system reminder saying it may ignore irrelevant content
2. The more irrelevant content in the file, the more likely Claude ignores everything
3. CLAUDE.md goes into every single session — any bloat is multiplied
4. Long files cause important rules to get lost in noise
5. Context window is the most important resource to manage

### The Brevity Test:
For each line in your CLAUDE.md, ask:
- "Would removing this cause Claude to make mistakes?" — if no, cut it
- "Is this universally applicable to every session?" — if no, move to skills
- "Can Claude figure this out by reading code?" — if yes, remove it
- "Does a deterministic tool handle this better?" — if yes, use hooks/linters

---

## 7. Progressive Disclosure & Modular Rules

### The Principle
Instead of putting everything in root CLAUDE.md, use progressive disclosure:
- **Root CLAUDE.md**: Universal rules only (commands, core style, architecture overview)
- **`.claude/rules/*.md`**: Topic-specific rules (testing.md, security.md, api-design.md)
- **Skills (`.claude/skills/`)**: Domain knowledge loaded on-demand
- **Child directory CLAUDE.md**: Context specific to subdirectories
- **@imports**: Reference separate docs when needed

### Scoped Rules with Frontmatter
Rules can be scoped to specific files using YAML frontmatter:

```markdown
---
paths:
  - "src/api/**/*.ts"
---

# API Development Rules
- All API endpoints must include input validation
- Use the standard error response format
```

Rules without a `paths` field are loaded unconditionally.

### Directory Organization Example:

```
your-project/
├── CLAUDE.md                     # Core project rules (< 100 lines)
├── CLAUDE.local.md               # Personal prefs (gitignored)
├── .claude/
│   ├── CLAUDE.md                 # Alternative location for project rules
│   ├── settings.json             # Permissions, hooks config
│   ├── rules/
│   │   ├── code-style.md         # Formatting, naming conventions
│   │   ├── testing.md            # Test patterns, fixtures
│   │   ├── security.md           # Security requirements
│   │   ├── frontend/
│   │   │   ├── react.md          # React-specific rules
│   │   │   └── styles.md         # CSS conventions
│   │   └── backend/
│   │       ├── api.md            # API design rules
│   │       └── database.md       # DB conventions
│   ├── skills/
│   │   ├── fix-issue/SKILL.md    # On-demand workflow
│   │   └── api-conventions/SKILL.md
│   └── agents/
│       └── security-reviewer.md  # Specialized subagent
```

### Best Practices for `.claude/rules/`:
- Keep rules **focused**: each file covers one topic
- Use **descriptive filenames**: the name should indicate what rules cover
- Use **conditional rules sparingly**: only when rules truly apply to specific file types
- **Organize with subdirectories**: group related rules (frontend/, backend/)
- Files are discovered **recursively**
- **Symlinks** are supported for sharing rules across projects

---

## 8. Formatting & Emphasis Best Practices

### Structure:
- Use **bullet points** for individual instructions
- Group related items under **descriptive markdown headings**
- Use **code blocks** for commands and examples
- Keep individual items **actionable and specific**

### Emphasis for Critical Rules:
- Use "IMPORTANT" or "YOU MUST" to improve adherence for critical rules
- Use **bold** for key terms
- But use emphasis sparingly — if everything is "IMPORTANT", nothing is

### Effective Rule Writing:
```markdown
# Good: Specific and actionable
- Use 2-space indentation for TypeScript files
- Run `pnpm test -- path/to/test` for single tests (not full suite)
- IMPORTANT: Always run `pnpm type-check` after modifying TypeScript files

# Bad: Vague and generic
- Format code properly
- Write good tests
- Follow best practices
```

### Provide Alternatives, Not Just Negatives:
```markdown
# Bad: Negative-only constraint
- Never use the --foo-bar flag

# Good: Provides alternative
- Use --baz instead of --foo-bar (--foo-bar is deprecated)
```

---

## 9. Anti-Patterns & Common Mistakes

### 1. The Over-Specified CLAUDE.md
**Problem**: Too long, Claude ignores important rules lost in noise.
**Fix**: Ruthlessly prune. If Claude already does it correctly without the instruction, delete it.

### 2. The Kitchen Sink Session
**Problem**: Mixing unrelated tasks, context fills with irrelevant info.
**Fix**: `/clear` between unrelated tasks.

### 3. Ghost Context
**Problem**: Assuming Claude remembers previous conversations without CLAUDE.md.
**Fix**: Persist important context in CLAUDE.md. 60% of support tickets stem from this.

### 4. Correcting Over and Over
**Problem**: Context polluted with failed approaches.
**Fix**: After two failed corrections, `/clear` and write a better prompt.

### 5. Stale CLAUDE.md
**Problem**: Outdated instructions (e.g., references to old test frameworks).
**Fix**: Treat CLAUDE.md like any config file — update when things change.

### 6. Replacing Linters with CLAUDE.md Rules
**Problem**: Using LLM instructions for what deterministic tools handle better.
**Fix**: Use actual linters/formatters; use hooks for enforcement.

### 7. Negative-Only Constraints
**Problem**: "Never use X" without providing alternative — agent gets stuck.
**Fix**: Always provide the alternative action.

### 8. Too Much MCP Context
**Problem**: >20k tokens of MCP definitions leaves minimal room for actual work.
**Fix**: Minimize MCP servers; use only what you need.

### 9. Not Iterating
**Problem**: Writing CLAUDE.md once and never updating.
**Fix**: Run `/insights` weekly. Review and refine based on Claude's actual behavior.

### 10. Including Information Claude Can Infer
**Problem**: Describing code structure that Claude can read directly.
**Fix**: Only include what Claude genuinely can't figure out from the code.

---

## 10. Advanced Features

### @imports
CLAUDE.md files can import additional files:
```markdown
See @README.md for project overview and @package.json for available commands.

# Additional Instructions
- Git workflow: @docs/git-instructions.md
- Personal: @~/.claude/my-project-instructions.md
```

- Both relative and absolute paths allowed
- Relative paths resolve relative to the file containing the import
- Imported files can recursively import (max depth 5)
- Imports in code blocks/spans are not evaluated
- First-time imports require approval dialog

### Compaction Instructions
You can customize what survives context compaction:
```markdown
## Compaction
When compacting, always preserve the full list of modified files and any test commands.
```

### Auto Memory
Claude automatically saves learnings to `~/.claude/projects/<project>/memory/`:
- `MEMORY.md` — index (first 200 lines loaded per session)
- Topic files loaded on-demand
- You can tell Claude to "remember that we use pnpm, not npm"
- Editable via `/memory` command

### Skills vs CLAUDE.md
- **CLAUDE.md**: Always loaded, for universal rules
- **Skills**: Loaded on-demand, for domain knowledge and workflows
- Skills are invokable via `/skill-name`
- Skills can have `disable-model-invocation: true` for manual-only workflows

### Hooks vs CLAUDE.md
- **CLAUDE.md**: Advisory ("should do")
- **Hooks**: Deterministic ("must do") — run scripts at specific points
- Use hooks for actions that must happen every time with zero exceptions

---

## 11. CLAUDE.md vs AGENTS.md vs .cursorrules

### Comparison Table

| Feature | CLAUDE.md | AGENTS.md | .cursorrules |
|---------|-----------|-----------|-------------|
| Tool | Claude Code | Vendor-neutral | Cursor |
| Auto-loaded | Yes | Most tools | Yes |
| Nested/subdirectory | Yes | Yes | Yes |
| Adoption | Anthropic only | Most tools except Claude | Cursor only |
| Format | Markdown | Markdown | Text/rules |
| Created by | Anthropic | Sourcegraph (Amp) | Cursor/Anysphere |
| Scoped rules | Yes (frontmatter) | Varies | Yes |

### The AGENTS.md Standard (July 2025)
- Created by Sourcegraph's Amp team as vendor-neutral standard
- "One file, any agent" — every tool except Claude Code has adopted it
- Claude Code still requires its own CLAUDE.md

### Multi-Tool Sync Strategy
For teams using multiple tools, the recommended approach:
1. Maintain a single `AGENTS.md` as the master source
2. Create a CLAUDE.md that imports it: `See @AGENTS.md`
3. Configure other tools to read AGENTS.md
4. Keep Claude-specific instructions (commands, hooks) in CLAUDE.md

### Security Warning
Security researchers have identified "Rules File Backdoor" attacks using Unicode characters and evasion techniques in instruction files. Since these files get injected into system prompts, they create an attack vector.

---

## 12. How Anthropic Teams Use CLAUDE.md

### Data Infrastructure Team
- **Top tip**: "The better you document your workflows, tools, and expectations in CLAUDE.md files, the better Claude Code performs"
- Made Claude excel at routine tasks like setting up new data pipelines with existing patterns
- Use CLAUDE.md for codebase navigation and onboarding new team members

### Security Engineering Team
- Created markdown runbooks and troubleshooting guides as CLAUDE.md context
- These condensed documents became debugging context for production issues

### End-of-Session Documentation Pattern
- Ask Claude to summarize completed work and suggest CLAUDE.md improvements
- Creates continuous improvement loop where documentation refines itself

### Knowledge Consolidation
- Technical docs scattered across wikis, comments, and team members' heads
- Claude consolidates via MCP and CLAUDE.md into accessible formats

---

## 13. Community Examples & Templates

### Trail of Bits (github.com/trailofbits/claude-code-config)
- Global `~/.claude/CLAUDE.md` template
- Three foundational principles: no speculative features, no premature abstraction, replace don't deprecate
- Measurable constraints: function length limits, complexity thresholds, line width
- Language-specific toolchains (Python: uv/ruff/ty, Node: oxlint/vitest, Rust: clippy)

### ChrisWiles/claude-code-showcase
- Complete example with hooks, skills, agents, commands, and GitHub Actions
- Covers stack details, test/lint commands, key directories, code style rules

### HumanLayer
- Root CLAUDE.md under 60 lines
- Demonstrates that extremely short files can be highly effective

### Full Sample (gist.github.com/scpedicini)
- Emphasizes checking existing patterns for consistency
- Always asks for clarification on complex tasks before coding
- Mandates running format/lint/type-check after every task

### Context Engineering Kit (Vlad Goncharov)
- Advanced context engineering techniques
- Minimal token footprint patterns
- Focused on improving agent result quality

---

## 14. Self-Improving CLAUDE.md Workflow

### The Feedback Loop
1. **Work with Claude** — observe behavior, note mistakes
2. **Run `/insights` weekly** — analyzes recent sessions for patterns
3. **Reflect**: What went wrong? What general pattern does this represent?
4. **Abstract**: Generalize the specific fix into a reusable rule
5. **Write to CLAUDE.md**: Add the new rule or update existing ones
6. **Prune**: Remove rules that are no longer needed

### The # Key
Use the `#` key during sessions to add instructions you find yourself repeating. These additions accumulate into a CLAUDE.md that genuinely reflects how your team works.

### End-of-Session Pattern
Ask Claude: "Summarize what we did and suggest CLAUDE.md improvements." This creates a continuous improvement loop.

### Treat It Like Code
- Review CLAUDE.md when things go wrong
- Prune regularly
- Test changes by observing whether Claude's behavior actually shifts
- Check into version control
- Iterate based on team feedback

---

## 15. Key Recommendations Summary

### The Golden Rules

1. **Keep it short** — Target < 100 lines for root CLAUDE.md, < 300 lines absolute max
2. **Be specific** — "Use 2-space indentation" not "Format code properly"
3. **Only include what Claude can't infer** — Don't describe what code already shows
4. **Universally applicable only** — Move conditional content to rules/ or skills/
5. **Start with /init, then prune** — Deleting is easier than creating from scratch
6. **Use progressive disclosure** — Root for universal, rules/ for specific, skills/ for on-demand
7. **Use hooks for enforcement** — CLAUDE.md is advisory, hooks are deterministic
8. **Iterate continuously** — Run /insights weekly, refine based on actual behavior
9. **Version control it** — The file compounds in value over time with team contributions
10. **Treat it like code** — Review, prune, test, update

### Priority Order for Content
1. **Commands** (build, test, lint, deploy) — highest value
2. **Non-obvious code style** — only rules that differ from defaults
3. **Architecture decisions** — things Claude genuinely can't infer
4. **Workflow rules** — branch naming, PR conventions, commit patterns
5. **Gotchas** — project-specific warnings
6. **Environment quirks** — required env vars, setup notes

### The Litmus Test
For every line in your CLAUDE.md, ask yourself:
- Would Claude make a mistake without this? → Keep it
- Can Claude figure this out from the code? → Remove it
- Does this apply to every session? → Keep it in CLAUDE.md
- Does this apply only sometimes? → Move to skills or rules/
- Can a linter/formatter handle this? → Use that tool instead + hooks

---

## Sources

### Official Anthropic
- [Best Practices for Claude Code](https://code.claude.com/docs/en/best-practices)
- [Manage Claude's Memory](https://code.claude.com/docs/en/memory)
- [How Anthropic Teams Use Claude Code (Blog)](https://claude.com/blog/how-anthropic-teams-use-claude-code)
- [Using CLAUDE.MD Files (Blog)](https://claude.com/blog/using-claude-md-files)
- [Agent Skills Engineering Blog](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

### Community Guides & Blogs
- [Writing a Good CLAUDE.md — HumanLayer](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [How to Write a Good CLAUDE.md — Builder.io](https://www.builder.io/blog/claude-md-guide)
- [Maximising Claude Code: Building an Effective CLAUDE.md — Maxitect](https://www.maxitect.blog/posts/maximising-claude-code-building-an-effective-claudemd)
- [Creating the Perfect CLAUDE.md — Dometrain](https://dometrain.com/blog/creating-the-perfect-claudemd-for-claude-code/)
- [From Chaos to Control — Brandon Casci](https://www.brandoncasci.com/2025/07/30/from-chaos-to-control-teaching-claude-code-consistency.html)
- [How I Use Every Claude Code Feature — Shrivu Shankar](https://blog.sshh.io/p/how-i-use-every-claude-code-feature)
- [Claude Code Best Practices (Aggregated) — Rosmur](https://rosmur.github.io/claudecode-best-practices/)
- [Keep Your AGENTS.md in Sync — Kaushik Gopal](https://kau.sh/blog/agents-md/)

### GitHub Repositories
- [Trail of Bits Claude Code Config](https://github.com/trailofbits/claude-code-config)
- [Claude Code Showcase](https://github.com/ChrisWiles/claude-code-showcase)
- [Awesome Claude Code (Curated List)](https://github.com/hesreallyhim/awesome-claude-code)
- [Claude Code Best Practices](https://github.com/awattar/claude-code-best-practices)
- [CLAUDE.md Examples](https://github.com/ArthurClune/claude-md-examples)
- [Claude Code Everything You Need to Know](https://github.com/wesammustafa/Claude-Code-Everything-You-Need-to-Know)
- [CLAUDE.md Templates (Claude Flow)](https://github.com/ruvnet/claude-flow/wiki/CLAUDE-MD-Templates)
- [Full CLAUDE.md Sample (Gist)](https://gist.github.com/scpedicini/179626cfb022452bb39eff10becb95fa)
- [GitHub Topics: claude-md](https://github.com/topics/claude-md)
