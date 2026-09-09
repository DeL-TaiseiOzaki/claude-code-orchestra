# Shared Language Rule

The normative language policy lives in `CLAUDE.md` under
`## Language Protocol`. Every runtime must apply that shared policy to its
conversation, agents, skills, hooks, and generated documents. This file neither
overrides nor duplicates it.

Response style is the other half, and it is normative **here**: the section
below owns how the user-facing reply reads and how long it runs. Other files
reference that section instead of restating it.

## Response Style

This governs the **orchestrator → user** reply. The "return a concise result"
lines in `.claude/agents/` and `.claude/skills/` govern **subagent →
orchestrator** returns, which stay in English — a different axis, and neither
one relaxes the other.

**Natural Japanese.** The reply must read as Japanese a person wrote, not as
translated English: no translationese, no literal rendering of English idiom,
no switching politeness register mid-reply. Technical terms, code identifiers,
paths, commands, and log excerpts stay verbatim in their original form.

**Concise but complete.** Lead with the conclusion — that ordering is already
fixed in `CLAUDE.md` `## Execution Patterns` — then give only what changes the
reader's next action. Cut preamble, restatement of the request, narration of
what you are about to do, and options you did not take. When the user asks for
detail, answer in full: conciseness is the default length, not a cap.

**Never compressed away.** Brevity is never a reason to drop any of these:

- every check that failed or was not run, and why;
- anything in the requested scope that was not done;
- assumptions made in place of an answer you did not get;
- risks, and the blast radius of the change;
- confirmation prompts for destructive or outward-facing actions;
- security-relevant findings.
