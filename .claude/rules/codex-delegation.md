# Codex Delegation Rule

**Codex CLI handles planning, design, and complex code implementation.**

> Scope: this rule decides *when Codex specifically*. Whether the main agent may
> keep a task at all is decided first by `.claude/rules/delegation.md`, whose
> default is to delegate.

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
- **Routine, well-scoped implementation** → `general-purpose-sonnet`
- **Difficult implementation** (ambiguous architecture, cross-cutting invariants,
  security/concurrency/data-integrity risk, or repeated failure) → `general-purpose-opus`
- **Codebase analysis** → `general-purpose-opus` (Opus 1M context)
- **External information retrieval / web research** → `general-purpose-opus` (WebSearch/WebFetch)

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

## Sol Guardrails

When a Codex (Sol-tier) delegation reports completion, the orchestrator or
delegating subagent **MUST verify before trusting it**:

1. **Run acceptance checks** -- execute every validation command from the
   original prompt contract and confirm they pass.
2. **Inspect the diff** -- review `git diff --stat` / `git diff` for:
   - Unapproved deletions (files or significant code removed without
     justification).
   - Out-of-scope changes (files modified that were not part of the task).
   - Stub or placeholder completions (`pass`, `TODO`, `NotImplementedError`
     left where real logic was requested).
3. **Watch for cheating patterns** -- reject completion if:
   - Tests were deleted, skipped (`@pytest.mark.skip`), or weakened
     (assertions removed/loosened) to make the suite pass.
   - Exceptions silently swallowed (bare `except: pass` or equivalent).
   - Hardcoded return values substituted for real implementation logic.

**On failure**: report the specific failure(s) with evidence to the user,
then re-delegate at most once with the original prompt plus failure context.
If the second attempt also fails, halt and require explicit user approval.

Canonical definition: root `AGENTS.md` section "Guardrails (Completion
Verification)".

## Language Protocol

See `CLAUDE.md` section "Language Protocol": ask Codex in English and
report to the user in Japanese.
