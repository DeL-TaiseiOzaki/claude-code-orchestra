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

**Understandable on the first read.** The reader should not have to re-read a
sentence or reconstruct missing context to act on it. Keep the subject and the
outcome in the same sentence and one idea per sentence. Name the same thing the
same way throughout the reply. Expand an internal term or acronym the first
time it appears in the session. Prefer the concrete path, command, number, or
error string over an abstract description of it. Reach for a list or a table
only when it removes reading effort — a two-row table is overhead, and a
six-way comparison buried in a paragraph is worse. Close with what the reader
does next, or say plainly that nothing is required.

**Never compressed away.** Brevity is never a reason to drop any of these:

- every check that failed or was not run, and why;
- anything in the requested scope that was not done;
- assumptions made in place of an answer you did not get;
- risks, and the blast radius of the change;
- confirmation prompts for destructive or outward-facing actions;
- security-relevant findings.
