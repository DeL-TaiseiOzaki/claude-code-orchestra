# Changing the Main Agent

Read this runbook only when the user explicitly asks to change the main agent.
Claude Code is the initial default. The active selection is recorded in
`.claude/STATE.md` under `## Main Agent`.

## Meaning of Main Agent

The main agent owns user interaction, task decomposition, routing, approval
boundaries, result integration, and the final response. Other runtimes remain
available as executors or advisors when their capabilities fit the task.

## Invariants

- `.claude/` remains the physical source for rules, skills, agent definitions,
  hooks, state, and docs, whichever runtime is main.
- Root `AGENTS.md` remains the CLI-agent contract every runtime auto-loads, and
  `CLAUDE.md` the main-agent contract. `.agents/AGENTS.md` and `.codex/AGENTS.md`
  stay short per-runtime adapters. All are real files.
- Rules, skills, agent definitions, hooks, state, and docs are not copied into
  `.agents/` or `.codex/`; those directories reference `.claude/` by path.
- Machine-readable native settings remain in each product's required path and
  are not symlinked across incompatible products.
- Changing the main agent must not silently broaden permissions or remove a
  working fallback runtime.

## Change Procedure

1. Confirm the requested runtime and the scope: repository-only or template
   default for future installations. Treat an unqualified request as
   repository-only.
2. Verify that the target runtime is installed and can read root `AGENTS.md`,
   the contract it routes to, `.claude/STATE.md`, relevant `.claude/rules/`, and
   its supported skills.
3. Inspect the target runtime's current native discovery/configuration
   requirements. Add only the minimum native config needed and point it directly
   to root `AGENTS.md`, `CLAUDE.md`, or `.agents/` where supported; do not
   invent integration
   surfaces in advance for runtimes that are not being activated.
4. Update only the `## Main Agent` value in `.claude/STATE.md`.
5. Map main-agent responsibilities to the target runtime. Keep Claude Code,
   Codex, Antigravity, or any former main available as an executor when its
   native runtime remains installed.
6. Translate hooks, model selection, permissions, and sandbox settings only
   where the target runtime requires machine-readable configuration. Preserve
   least privilege and document any unavoidable semantic difference.
7. Update the default statement in `CLAUDE.md`, the `.claude/STATE.md`
   seed, and installer/updater manifests only when the user requested a new
   template default. A repository-only switch changes only `.claude/STATE.md`
   and must survive updates without modifying template-owned bootstrap files.
8. Record the decision in the appropriate design log and run the validation
   below.

For an unsupported future runtime, first establish its official discovery and
configuration paths. Keep the new native surface minimal and point its
human-readable discovery path back to root `AGENTS.md` or the canonical
`.claude/` content whenever the runtime supports that model.

## Validation

- Start the target runtime in a disposable session and confirm it identifies
  itself as the main agent from `.claude/STATE.md`.
- Confirm it can invoke one shared skill and route one executor without
  duplicating shared files into its native directory.
- Run `bash scripts/check.sh` and the full test suite.
- Inspect symlink targets, native permission settings, and the final diff.

## Rollback

Restore the previous `## Main Agent` value in `.claude/STATE.md`, restore the
previous native config from version control or backup, and rerun the validation
checks.
