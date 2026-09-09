# Response Style Practices: Language and Conciseness Enforcement

Research question: what mechanism does the Claude Code / AI-coding-agent
community actually use to make an agent (a) reply in natural Japanese and
(b) reply concisely but completely — and what is the *smallest* mechanism that
holds, rather than more prose appended to an instruction file.

Date: 2026-09-09. Verified against Claude Code v2.1.267 (the version installed
in this repository).

> **Repository finding that reframes the question.**
> `/home/user/claude-code-orchestra/.claude/settings.json` already contains
> `"language": "japanese"`. The native, system-prompt-level Japanese mechanism
> is *already installed*. `CLAUDE.md` line 120 ("Communicate with the user in
> Japanese") and `.claude/rules/language.md` are a **second, weaker copy of the
> same instruction**, not the thing that makes Japanese work. No `outputStyle`
> key is set, and no `.claude/output-styles/` directory exists at project or
> user level — so conciseness currently has **no** mechanism at all beyond
> prose in the contract files.

---

## Mechanisms

Ordered by how close they sit to the model's system prompt (strongest first).
"Cost" is context/token cost plus operational cost.

| Mechanism | Where configured | Scope | Persistence | Portability | Failure / drift mode |
|---|---|---|---|---|---|
| **`language` setting** | `settings.json` (`language: "japanese"`), any scope: user / project / local / managed | Main conversation. **Subagent propagation undocumented** (see below) | **Survives `/compact`** — system prompt is not part of message history | Claude Code only. Not read by Codex, Cursor, or any AGENTS.md consumer | Long-session dialect/script drift is still reported (issues #51686, #46846); it lowers the drift rate, it does not eliminate it |
| **Output style** (built-in `Concise`, `Proactive`, `Explanatory`, `Learning`, or custom `.md`) | `outputStyle` key in any settings file; files in `~/.claude/output-styles/`, `.claude/output-styles/`, or managed policy dir | Main conversation **only** — explicitly *not* subagents | **Survives `/compact`** (system prompt) | Claude Code only | (1) Silently does nothing for subagents. (2) A custom style **drops Claude Code's built-in software-engineering instructions** unless `keep-coding-instructions: true`. (3) In the terminal, style files are read at startup — edits mid-session need a restart. (4) Switching mid-session rebuilds the prompt cache once |
| **`--append-system-prompt` / `--append-system-prompt-file`** | CLI flag, per invocation | That one process, main conversation | Survives `/compact` (system prompt) | Flag is Claude-Code-specific; the *text* is portable | Must be passed every invocation. Anthropic explicitly calls it "better suited to scripts and automation than interactive use." Invisible to anyone reading the repo |
| **`--system-prompt` / `--system-prompt-file`** | CLI flag, per invocation | Replaces the **entire** system prompt | n/a | n/a | Destroys all built-in coding behaviour. Never appropriate for a style tweak |
| **`CLAUDE.md`** (project `./CLAUDE.md` or `./.claude/CLAUDE.md`, user `~/.claude/CLAUDE.md`, `CLAUDE.local.md`, managed policy) | Markdown in repo / home / managed path | Every session, additive across the whole ancestor chain; **also loaded by subagents** (except built-in Explore/Plan) | Project-root CLAUDE.md is **re-injected from disk** after compaction | Portable in spirit via `@AGENTS.md` import or symlink; Claude Code reads `CLAUDE.md`, *not* `AGENTS.md` | Delivered as a **user message after the system prompt, not as part of it** — "no guarantee of strict compliance." Adherence falls as the file grows; Anthropic's own target is **under 200 lines** and "longer files consume more context and reduce adherence" |
| **`.claude/rules/*.md`** (unscoped) | `.claude/rules/`, `~/.claude/rules/` | Loaded at launch with the **same priority as `.claude/CLAUDE.md`** | Unscoped rules re-injected after compaction | Claude-Code-specific directory | Same weak-instruction failure mode as CLAUDE.md, plus dilution: every extra rule file competes for the same instruction budget |
| **`.claude/rules/*.md` with `paths:` frontmatter** | Same, plus YAML `paths:` | Loads only when Claude reads a matching file | **Does NOT survive compaction reliably** — reloads only when a matching file is read again | Claude-Code-specific | Wrong tool for a style rule: a response-language rule has no path to scope to. Docs: "If a rule must persist across compaction, drop the `paths:` frontmatter" |
| **`UserPromptSubmit` hook → `hookSpecificOutput.additionalContext`** | `.claude/settings.json` hooks block + a script | Injected once per turn, before Claude sees the prompt | Injected fresh every turn, but earlier injections are **summarized away** by compaction | Concept portable; JSON schema is Claude-Code-specific | Costs real tokens **every turn, forever** (30s timeout, synchronous — delays every prompt). Open bugs report `additionalContext` **accumulating in history instead of being ephemeral** (#40216) and being injected multiple times (#14281) |
| **`SessionStart` hook, matcher `compact`** | Same hooks block | Runs after compaction, output added to the compacted context | Purpose-built for post-compaction re-injection | Claude-Code-specific | Only useful for things that *don't* already survive compaction. Redundant for anything living in the system prompt |
| **Auto memory** (`~/.claude/projects/<project>/memory/MEMORY.md`) | Written by Claude, toggled with `autoMemoryEnabled` | Per repo, machine-local, first 200 lines / 25KB | Re-injected from disk after compaction | Not portable, not shareable, not in version control | Claude decides what to save. It explicitly "skips anything your CLAUDE.md files already say," so it will not reinforce an existing rule. Not a control surface |
| **Subagent definition** (`.claude/agents/*.md`) | Markdown agent file | That subagent's **own system prompt** | n/a — fresh context each spawn | Mirrored by `.agents/` adapters for other CLIs in this repo | The **only** lever for subagent output style, because output styles do not reach subagents. Each agent file must carry its own language/verbosity line |
| **Skills** (`SKILL.md`) | `.claude/skills/` | On demand | Re-injected after compaction, capped 5k tokens/skill, 25k total, oldest dropped first | `.codex/config.toml` points at the same paths in this repo | Wrong granularity for an always-on style rule; loads only when invoked or judged relevant |
| **`AGENTS.md` convention** | Repo root | Whatever tool reads it | File on disk | The portable option — Codex, and via `@AGENTS.md` import or symlink, Claude Code | The spec covers dev setup, testing, and PR instructions. It says **nothing about response language, tone, or verbosity**, and defines no enforcement. It is a file convention, not a control mechanism |
| **Managed `claudeMd` key** | `managed-settings.json` only | Every session on the machine | Loads before user and project CLAUDE.md, **cannot be excluded** | Enterprise-only | Honored *only* in managed/policy settings; setting it in user/project/local has no effect. Overkill for one repo |

### Two hard boundaries that decide the answer

1. **Instructions vs. enforcement.** Anthropic states it plainly: "Both are
   loaded at the start of every conversation. Claude treats them as context,
   **not enforced configuration**." And: "An instruction like 'never edit
   `.env`' in CLAUDE.md or a skill is a request, not a guarantee." There is no
   hook event that can enforce *response prose* — hooks gate tools, not text.
   So for style, the realistic ceiling is "raise the probability," and the
   ranking is by *how close to the system prompt* the instruction sits.

2. **Subagents do not inherit output styles.** From the subagents doc: "a
   subagent runs its own system prompt, so your output style doesn't shape its
   responses." Subagents *do* inherit the full CLAUDE.md hierarchy including
   `.claude/rules/`. A fork is the sole exception, inheriting the parent's full
   system prompt. Whether the `language` setting reaches a subagent's system
   prompt is **not documented**; observed in this session, a
   `general-purpose-opus` subagent received the Japanese instruction only via
   the CLAUDE.md project-instructions block, with no separate
   "always respond in japanese" line in its system prompt. Treat as
   **unverified but likely: `language` does not propagate to subagents.**

---

## What the community actually does

**Response language — the settled answer is the `language` settings key.**
It was not always so. The key adds the value *verbatim to the system prompt* as
an instruction to always respond in that language, accepts any language name
without validation, and also drives voice dictation and auto-generated session
titles. Japanese-language write-ups converged on this from ~v2.1.0 onward,
describing `"language": "japanese"` in `settings.json` as the way to get
"consistent Japanese responses throughout all sessions"
([digital-gorilla](https://digital-gorilla.co.jp/ai-lab/claude-code-%E6%97%A5%E6%9C%AC%E8%AA%9E/),
[fyve.co.jp](https://fyve.co.jp/claude-code/articles/claude-code-japanese-guide);
both retrieved via search summary — the sites themselves were unreachable
through this environment's egress proxy, so treat the paraphrase as
**unverified secondary**). Anthropic's own settings reference is the primary
source and is verified.

**The pre-`language` convention was a one-line CLAUDE.md rule, and it persists
in the wild.** The dominant Japanese-community pattern is: write the *rule
itself* in English ("Always respond in Japanese") while the surrounding project
documentation may be Japanese — English instruction text is reported to be
followed more reliably. This repository's `CLAUDE.md` line 120 is exactly this
pattern. It is now a **belt-and-braces duplicate** of the `language` key, not
the load-bearing mechanism.

**Conciseness — the community moved from prose to the built-in `Concise`
output style.** Before it existed, teams hand-wrote custom output styles
(the curated collection
[awesome-claude-code-output-styles-that-i-really-like](https://github.com/hesreallyhim/awesome-claude-code-output-styles-that-i-really-like)
is the community index; note that most entries there are persona experiments
— Zen Master, Tabloid Journalist — which tells you the feature's *cultural*
centre of gravity is voice, not discipline). Anthropic then shipped `Concise`
as a built-in in **v2.1.237**: "Claude leads with the result, skips preamble
and narration, and keeps responses short by default, **while doing the
engineering work as thoroughly as in the Default style**. When you ask for an
explanation or more detail, Claude answers in full. Claude always keeps the
complete content of error reports, security warnings, and confirmations for
destructive actions."

That last sentence is the whole reason to prefer it over a hand-written rule:
`Concise` is *the "concisely but completely" contract, already written and
already carved out for the cases where truncation is dangerous*. A hand-rolled
"be brief" line in CLAUDE.md has none of those carve-outs and will happily
truncate an error report.

At least one Japanese measurement study claims `Concise` cut output text and
cost by ~40% across 40 runs of 5 styles with no loss of correctness
([note.com](https://note.com/ai_hack_dx/n/ne06b92115661)) — **unverified**,
the domain is blocked by this environment's egress proxy; cited only as a
community signal, not as evidence.

**Custom output styles are what teams reach for when they need both axes at
once**, because a single style file can say "respond in Japanese, lead with the
conclusion" and it lands in the system prompt rather than in a user message.
The critical convention: set `keep-coding-instructions: true`, or the style
silently strips Claude Code's built-in software-engineering instructions.

**The AGENTS.md standard deliberately does not cover this.** It specifies dev
environment tips, testing instructions, and PR instructions. Response language,
tone, and verbosity are out of scope. Anything cross-CLI therefore has to be
duplicated per runtime — there is no portable style primitive, only portable
*text*.

**Bug-tracker signal on drift.** Multiple open/closed-as-stale reports describe
the same shape:
[#51686](https://github.com/anthropics/claude-code/issues/51686) (Spanish
dialect leaks in long sessions, instructions layered in global CLAUDE.md +
project CLAUDE.md + auto memory, all three ignored),
[#46846](https://github.com/anthropics/claude-code/issues/46846) (Traditional
Chinese instruction in CLAUDE.md, Claude answers in Japanese/Korean after
English-only tool output like `git push`, and even *apologizes in Japanese*),
plus [#24941](https://github.com/anthropics/claude-code/issues/24941) and
[#57212](https://github.com/anthropics/claude-code/issues/57212) (language
switching mid-response; listed from search, not individually read).

Reporter diagnosis in #51686, worth quoting in substance: it "works at first,
drifts later" — instructions are deprioritized as context grows, **regardless of
how many layers restate them**, and the drift is worst on long, expensive
responses (complex refactors, architecture analyses) precisely because those are
the ones the user will not regenerate. Both issues were closed as not planned,
with no maintainer workaround. #46846 shows the trigger clearly: **English-only
tool output pulls the response language toward English.** For an orchestrator
repo that runs English-language subagents and Codex handoffs continuously, that
is the exact operating condition.

---

## Anti-patterns

**Restating the rule in more places.** #51686 is the controlled experiment:
three independent layers (user CLAUDE.md, project CLAUDE.md, persistent memory)
all stating the same rule, and it still drifted. Layer count is not the
variable; **distance from the system prompt** and **total instruction budget**
are. Adding a fourth restatement measurably *hurts*, because it consumes the
budget that makes the other rules stick.

This repository is already one restatement past the line: `settings.json`
`language` + `CLAUDE.md` §Language Protocol + `.claude/rules/language.md`
(which is a pointer file whose entire content is "the normative policy lives in
CLAUDE.md") = three artifacts for one rule, only one of which is enforced at
system-prompt level.

**Burying a style rule deep in a long instruction file.** Official guidance:
target under 200 lines per CLAUDE.md; "longer files consume more context and
reduce adherence"; `/doctor` now proposes trims. This repo's `CLAUDE.md` puts
`## Language Protocol` at **line 116 of ~145**, immediately before
`## Native Runtime Boundary`. Combined with five always-loaded
`.claude/rules/*.md` files, the effective instruction budget is far past the
recommended size, and the language rule sits near the bottom of it.

**Vague style prose.** "Be concise," "reply naturally," "keep it short" fail the
official specificity test ("Use 2-space indentation" beats "format code
nicely"). Worse, unqualified brevity instructions have no carve-out for error
reports and destructive-action confirmations — which is exactly the safety
property built-in `Concise` provides for free.

**Contradictory instructions.** "If two rules contradict each other, Claude may
pick one arbitrarily." A `language` key saying `japanese`, a CLAUDE.md saying
"Communicate with the user in Japanese," and agent files whose Output Format
templates are all English section headers is a live low-grade contradiction.

**A `UserPromptSubmit` reminder hook for style.** The obvious "just re-inject
the rule every turn" fix is the worst trade in the table: permanent per-turn
token cost, synchronous latency on every prompt, and two open bugs about
`additionalContext` accumulating in history rather than staying ephemeral
([#40216](https://github.com/anthropics/claude-code/issues/40216),
[#14281](https://github.com/anthropics/claude-code/issues/14281)). It buys
nothing that the system prompt does not already give for free — the system
prompt is re-sent on every request *and* survives compaction.

**Path-scoped rules for a style rule.** `.claude/rules/` files with `paths:`
frontmatter do not survive compaction and only reload when a matching file is
read. A response-language rule has no file path to attach to.

**Assuming a custom output style keeps coding behaviour.** Default for
`keep-coding-instructions` is `false`. Omitting it strips the built-in
software-engineering instructions — how to scope changes, write comments, and
verify work — while the author believes they only changed the tone.

**Expecting an output style to reach subagents.** It will not. In a repo whose
entire contract is "delegate by default," a main-conversation-only style
mechanism governs a *minority* of the produced text.

**Relying on auto memory to reinforce a rule.** It explicitly skips anything
CLAUDE.md already says.

---

## Recommendation for a minimal implementation

### Option 1 (recommended) — keep `language`, add `outputStyle: "Concise"`, delete the duplicates

Net change: **one settings key added, prose removed.** No new file.

1. Add to `.claude/settings.json` (project scope, committed, next to the
   `language` key that is already there):
   ```json
   { "language": "japanese", "outputStyle": "Concise" }
   ```
   Available on v2.1.267 (`Concise` needs ≥2.1.237; live `outputStyle` edits
   need ≥2.1.251 — both satisfied). This puts *both* axes in the system prompt,
   where they survive compaction at zero recurring context cost, and it buys the
   built-in carve-outs for error reports, security warnings, and destructive-
   action confirmations that a hand-written brevity rule would not have.
2. Reduce `CLAUDE.md` §Language Protocol to the two lines that are **not**
   covered by the `language` key — "think and reason in English" and "write
   code, identifiers, comments, commands, and technical documents in English."
   Drop "Communicate with the user in Japanese": the settings key does that
   from the system prompt, and the CLAUDE.md copy is the weaker duplicate.
   Consider deleting `.claude/rules/language.md`, which is a pointer to a
   pointer and costs context every session for zero instruction content.
3. Verify empirically before trusting it, because subagent propagation is
   undocumented: run `/context` to confirm what loaded, then check whether a
   `general-purpose-sonnet` return message comes back Japanese. If it does not,
   apply step 4.
4. **Subagent coverage (the part no settings key can do).** Because output
   styles never reach subagents and `language` propagation is unverified, add
   one line to each `.claude/agents/*.md` — e.g. "Return the final summary in
   Japanese; keep code, paths, and commands in English." Their `## Output
   Format` templates already exist; this is one line per agent file, in the
   only place that reaches a subagent's own system prompt.

**Cost**: one JSON key; a net *reduction* in always-loaded prose.
**Risk**: `Concise` changes the main agent's voice globally, including for
work that genuinely needs length. It is reversible in one edit, and it answers
in full when asked for detail.

### Option 2 — one custom output style, if `Concise` is too blunt

Create `.claude/output-styles/orchestra-ja.md` (project-scoped, committable,
shareable):

```markdown
---
name: Orchestra JA
description: Japanese, conclusion-first, delegation-report shaped
keep-coding-instructions: true
---
Respond to the user in Japanese. Keep code, identifiers, file paths,
commands, and log excerpts in English verbatim.
Lead with the conclusion, then rationale, then next action.
For implementation reports, state changed files, commands run, test
results, and remaining risks — never omit a failed or unrun check.
```

`keep-coding-instructions: true` is mandatory, not optional. This is the only
mechanism that expresses *both* axes and this repo's specific report shape in a
single system-prompt-level artifact. Costs a file plus its tokens in the system
prompt on every request; drifts nowhere, because it is not in message history.
Remember the terminal reads style files **at startup** — restart after editing.
Still does not reach subagents; step 4 above still applies.

### Option 3 (not recommended) — status quo plus better placement

If no configuration change is acceptable, the only remaining lever is to move
`## Language Protocol` to the **top** of `CLAUDE.md` and make it specific
("Reply in Japanese; lead with the conclusion; keep code and commands in
English"). This keeps the rule in a user message, where the bug tracker shows
it drifts in exactly this repo's operating conditions — long sessions, heavy
English tool output, continuous English subagent returns. Do this only as a
stopgap.

---

## Sources

Official (verified by direct fetch):
- https://code.claude.com/docs/en/output-styles
- https://code.claude.com/docs/en/memory
- https://code.claude.com/docs/en/settings-reference
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/context-window
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/features-overview
- https://code.claude.com/docs/en/cli-reference
- https://code.claude.com/docs/ja/output-styles (Japanese mirror)

Community (issue bodies verified by direct fetch unless marked):
- https://github.com/anthropics/claude-code/issues/51686
- https://github.com/anthropics/claude-code/issues/46846
- https://github.com/anthropics/claude-code/issues/24941 (search listing only)
- https://github.com/anthropics/claude-code/issues/57212 (search listing only)
- https://github.com/anthropics/claude-code/issues/40216 (search listing only)
- https://github.com/anthropics/claude-code/issues/14281 (search listing only)
- https://github.com/hesreallyhim/awesome-claude-code-output-styles-that-i-really-like
- https://github.com/openai/agents.md (agents.md itself is egress-blocked here)

Unverified secondary (egress-blocked; paraphrased from search summaries only):
- https://zenn.dev/tokium_dev/articles/claude-code-output-styles-action-first
- https://note.com/ai_hack_dx/n/ne06b92115661
- https://digital-gorilla.co.jp/ai-lab/claude-code-%E6%97%A5%E6%9C%AC%E8%AA%9E/
- https://fyve.co.jp/claude-code/articles/claude-code-japanese-guide
