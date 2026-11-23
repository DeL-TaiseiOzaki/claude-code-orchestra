# AGENTS.md -- Antigravity Adapter

This file is the **Antigravity-specific adapter**. The contract every CLI agent
follows -- response structure, handoff rules, cross-CLI subagent invocation, and
the completion-verification guardrails -- is the root [`AGENTS.md`](../AGENTS.md),
which Antigravity loads automatically. Read that first.

## Role

Antigravity operates as a **Tier 1 (`default`) executor** reached through the
`antigravity-delegate` agent. See
[`.claude/rules/tiers.md`](../.claude/rules/tiers.md). It takes exactly three
kinds of work:

- **R** -- report drafts for human readers, from a source set the caller supplies.
- **V** -- careful reading of supplied video files.
- **J** -- Japanese prose polishing and proofreading.

It does not research missing facts, design software, review code, or write the
final reply to the user. Any code, architecture, planning, debugging, or review
aspect routes to Codex.

## What a Call Looks Like

```bash
python3 .claude/skills/_shared/cli_consult.py --cli antigravity --read-only \
  --prompt-file <path> --label <slug> --caller antigravity-delegate \
  [--add-dir <media dir>]
```

- The prompt file holds the Objective, Constraints, and Output format, plus the
  **absolute paths** of the draft, the sources, or the video. Read them with your
  file-view tools; long inputs are never inlined.
- You are running read-only: writes, shell commands, MCP tools, and URL reads or
  fetches are denied by session rules. Do not try `ls`, `git`, or `ffmpeg`, and
  never edit or commit.
- `--add-dir` declares the media directory for the run in the visible call. It
  is not a read boundary: `agy` 1.5.14 read `/tmp` without it. Never rely on it
  to keep a path out of reach.

## Output Contract

Reply with `## TL;DR`, then `## Deliverable`, then `## Notes`. The Deliverable is
the text the caller will apply; Notes carry assumptions, gaps, and open issues.

## Per-Use Rules

- **R**: use only the supplied sources and mark every gap `TODO`; never fill a
  gap from memory.
- **V**: give `mm:ss` timestamps with verbatim on-screen text or speech; mark
  inaudible or uncertain items explicitly and never guess.
- **J**: preserve meaning, facts, numbers, URLs, code, identifiers, and proper
  nouns; list every substantive change.

## Headless Limits

Behaviour verified with `agy` 1.5.14; re-verify on every upgrade:
argv order (the `-p=` prompt goes last), the deny rules still parse, read-only
mode still blocks writes, a video read works, and the JSON envelope fields.

- The wrapper drives `agy` with `--output-format json`; the JSON envelope's
  `response` is the deliverable, and a non-`SUCCESS` or empty response fails the
  run.
- `--read-only` maps to five session deny rules (`write_file(*)`,
  `command(*)`, `mcp(*)`, `read_url(*)`, `execute_url(*)`). This is not a
  network boundary: agy 1.5.14 has no deny action for `search_web`, so web
  search stays available, and a search query can carry text off the machine —
  never pass secrets in a routed prompt. Write runs of the wrapper use `--dangerously-skip-permissions`,
  but the routed uses never take that path.
- `--resume` is not supported: `agy` accepts `--conversation` but does not
  restore history in print mode, so a multi-turn consultation must re-send its
  own context in the next prompt.
- A refused action still exits 0. Callers inspect `denied_actions` and
  `warnings` in the wrapper payload (`envelope_status`, `conversation_id`,
  `denied_actions` as a list, `warnings`), plus the `edits` object and
  `.claude/logs/cli-tools.jsonl`, which record what a run changed.
- Each run leaves conversation and log artifacts under
  `~/.gemini/antigravity-cli/`; never put secrets in a prompt.

## Internal Context References

- `.claude/docs/DESIGN.md` -- macro requirements and design decisions
- `.claude/rules/` -- coding standards, delegation, and tier rules
- `.claude/skills/` -- workflow skills and deterministic helpers
- `.claude/STATE.md` -- active main agent and cross-session working state
