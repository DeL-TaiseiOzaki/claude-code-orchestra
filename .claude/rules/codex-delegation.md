# Codex Delegation Rule

**Codex CLI handles planning, design, and complex code implementation.**

> Preflight: ensure codex CLI is current (see codex-system skill).

## Two Roles of Codex

### 1. Planning & Design

- Architecture design, module structure
- Implementation planning (step decomposition, dependency ordering)
- Trade-off evaluation, technology selection
- Code review (quality and correctness analysis)

### 2. Complex Code Implementation

- Complex algorithms, optimization
- Debugging with unknown root causes
- Advanced refactoring
- Multi-step implementation tasks

## Delegation Decision

Default to Codex-first delegation for development tasks.

Consult Codex when **any** of these apply (recommended default):

- Design/architecture decisions are involved.
- Change spans 2+ files with behavior impact.
- Root cause is unclear.
- User requests comparison/trade-off analysis.
- You need a step-by-step implementation plan.
- You are unsure and want a safe implementation direction.

Do NOT delegate to Codex when:

- Obvious one-file tiny edits, typo fixes
- Tasks that simply follow explicit user instructions
- git commit, test execution, lint
- **Codebase analysis** → general-purpose subagent (Opus 1M context)
- **External information retrieval / web research** → general-purpose subagent (Opus, WebSearch/WebFetch)

## Prompt Contract (Always Include)

1. Objective (single sentence)
2. Constraints (style, limits, forbidden approaches)
3. Relevant files (explicit paths)
4. Acceptance checks (commands)
5. Output format (structured markdown sections)

Detailed templates: `@.claude/docs/CODEX_HANDOFF_PLAYBOOK.md`

## How to Consult

Exec syntax, subagent/direct patterns, implementation calls, and the sandbox-modes table: see the **codex-system skill** (`.claude/skills/codex-system/SKILL.md`) — this rule covers only *when* to delegate.

## Codex Plugin for Claude Code (codex-plugin-cc)

Plugin slash commands (`/codex:review`, `/codex:rescue`, job management) and plugin-vs-CLI guidance: see the codex-system skill.

## Language Protocol

See `.claude/rules/language.md` (SSOT): ask Codex in English; report to the user per that rule.
