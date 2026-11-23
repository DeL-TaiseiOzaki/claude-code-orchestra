# Project — Agent Instructions

Root instructions that every agent runtime loads automatically (Claude Code,
Codex, Antigravity, and other CLIs that read `AGENTS.md`). This file belongs to
the project: `/start-project` converts it once, and template updates never
rewrite it afterwards. Template policy lives under `.claude/` and is listed in
Orchestra References.

## Project

_Not initialized — run `/start-project` to convert this file into the
project's own instructions._

## Commands

_Not initialized — `/start-project` lists only the commands the repository
declares._

## Conventions

- Think and reason in English.
- Write code, identifiers, comments, commands, and technical documents in English.
- Communicate with the user in Japanese.

## Agent Roles

- **Main agent**: the runtime named in `.claude/STATE.md` `## Main Agent`, in
  a user-facing session. It follows `.claude/rules/orchestration.md` and, when
  it calls another CLI, `.claude/rules/cli-contract.md`.
- **Delegated executor**: any run started through
  `.claude/skills/_shared/cli_consult.py` or `codex_consult.py`. The wrapper
  sets `ORCHESTRA_ROLE=executor` and places
  `.claude/skills/_shared/executor_contract.md` before the task; that contract
  takes precedence over main-agent routing. An executor does the delegated
  task, replies in the contract's structure, and does not delegate further
  unless the prompt allows it.
- Neither role runs Claude Code's built-in `/init` or creates a `CLAUDE.md`:
  it would stop Claude Code from loading this file.

## Orchestra References

| Need | Read |
|------|------|
| Main-agent operating contract | `.claude/rules/orchestration.md` |
| Calling another CLI, completion guardrails | `.claude/rules/cli-contract.md` |
| Executor contract (injected by the wrappers) | `.claude/skills/_shared/executor_contract.md` |
| Delegation policy and tiers | `.claude/rules/delegation.md`, `.claude/rules/tiers.md` |
| Shared standards | `.claude/rules/` |
| Active main agent and working state | `.claude/STATE.md` |
| Macro requirements and design | `.claude/docs/DESIGN.md` |
| Runtime adapters | `.agents/AGENTS.md` (Antigravity), `.codex/AGENTS.md` (Codex, reference only) |
| Registry, changing the main agent | `.claude/docs/INDEX.md`, `.claude/docs/change_main.md` |
