# Response-Style Surface Audit

Read-only audit of every place that already governs *how an agent talks to the
user*: language, tone, verbosity, and response structure. Purpose: add a
"natural Japanese + concise-but-complete" rule in **one** place instead of a
seventh.

Baseline at audit time: `bash scripts/check.sh` → **exit 0** (8 passed, 0
failed). `uv run pytest tests/test_orchestration_contract.py
tests/test_load_context.py -q` → 31 passed.

---

## Current language/verbosity surface

### Tier A — auto-loaded contracts (no skill invocation needed)

| File:line | What it says | Who reads it, when |
|-----------|--------------|--------------------|
| `CLAUDE.md:116-120` — `## Language Protocol` | The 3-line normative split: think in English / write code+docs in English / **communicate with the user in Japanese**. No tone, no length, no register. | Claude Code main agent, auto-loaded every session. Declared SSOT by `.claude/rules/language.md`. |
| `CLAUDE.md:88-89` (tail of `## Execution Patterns`) | "Lead user-facing output with the conclusion, then rationale and next actions. For implementation, report changed files, commands run, test results, and risks." | Same. **The only user-facing response-shape rule in the Claude path.** Specifies *order*, never *length*. |
| `CLAUDE.md:14-16` (`## Mission`) | "Protect conversation quality and main-agent context"; "State assumptions, uncertainty, failures, and remaining risks explicitly." | Same. Nearest thing to a completeness rule; framed as mission, not as an output constraint. |
| `AGENTS.md:23-46` — `## Required Response Structure` | Mandatory 6-section template: TL;DR (≤3 lines) / Analysis / Plan / Patch Strategy / Validation / Risks. The `## TL;DR` "3 lines or fewer" is the **only hard numeric verbosity bound in the repository**. | Every CLI runtime auto-loads root `AGENTS.md` (`AGENTS.md:3`; asserted again in `CLAUDE.md:7-8`): Codex, Antigravity, Grok, opencode — and Claude Code as a caller. |
| `AGENTS.md:48-55` — `## Handoff Rules` | "Compress key points needed for decision-making, not lengthy raw data"; "Return procedures that are directly executable as-is"; "Separate unverified items as TODOs". | Same. Closest existing conciseness statement, but scoped to *handoff between agents*, not to the user-facing reply. |
| `AGENTS.md` (whole file) | **Contains no language statement at all.** `grep -i language AGENTS.md` → no match. | Consequence: a Codex or Antigravity run learns the response *structure* from its auto-load but must follow the router table (`AGENTS.md:13`) into `CLAUDE.md` to learn it should answer in Japanese. |
| `README.md:519-524` — `## Language Rules` | Fourth restatement: code/thinking English, responses to users Japanese, technical docs English, "README, etc.: Japanese permitted". | Humans. Not loaded by any runtime, but it is a maintenance surface that drifts. |

### Tier B — machine settings

| File:line | What it says | Who reads it, when |
|-----------|--------------|--------------------|
| `.claude/settings.json:3` | `"language": "japanese"` | Claude Code runtime, every session. |
| `.claude/settings.json` (whole file) | **No `outputStyle`. No `statusLine`.** Top-level keys are exactly: `$schema`, `language`, `effortLevel`, `fastMode`, `alwaysThinkingEnabled`, `hooks`, `permissions`, `env`. `grep -rn 'outputStyle\|statusLine'` across the repo → zero matches. | — |
| `.codex/config.toml:48-49` | `# Response style` / `verbosity = "medium"` | Codex CLI only. **The only machine-level verbosity dial that exists anywhere in the repo**, and it governs a non-Claude runtime. |
| `.claude/settings.json:196` | `CLAUDE_CODE_SUBAGENT_MODEL: sonnet` | Routing, not style — listed because it is the only other output-shaping env key. |

### Tier C — pointer / deferral files

| File:line | What it says | Who reads it, when |
|-----------|--------------|--------------------|
| `.claude/rules/language.md:1-8` (entire file, 8 lines) | Pointer only: "The normative language policy lives in `CLAUDE.md` under `## Language Protocol`. Every runtime must apply that shared policy to its conversation, agents, skills, hooks, and generated documents. This rule does not override or duplicate the shared contract." | Loaded by `context-loader` (`.claude/skills/context-loader/load_context.py:47-56`, `PREFERRED_RULE_ORDER` position 4). `CLAUDE.md:71` makes context-loader mandatory ("Always start with `context-loader`"); `.codex/config.toml:40-42` enables the same skill for Codex. |
| `.claude/rules/codex-delegation.md:131-134` — `## Language Protocol` | "See root `AGENTS.md` section 'Language Protocol': ask Codex in English and report to the user in Japanese." | **Broken reference.** Root `AGENTS.md` has no such section, and per `tests/test_orchestration_contract.py:107-108` it may never have one. |
| `.claude/skills/codex-system/SKILL.md:219-221` — `## Language Protocol` | "See `.claude/rules/language.md` (SSOT)". | **Conflicting SSOT claim**: language.md itself says it is *not* the SSOT and defers to CLAUDE.md. |
| `.claude/rules/delegation.md:31` | Self-Handle item 5 ends "…and the final Japanese report." | Fifth restatement of the Japanese rule. |
| `.claude/rules/delegation.md:84-85, 89-93` | Context-discipline clause: "return only decision-relevant findings; write long output to `.claude/docs/…`"; "Long logs, large files, and full search dumps never enter the main agent's context." | Verbosity control — but **inward** (subagent → main agent), never outward (main agent → user). |

### Tier D — agent definitions (`.claude/agents/`)

All four restate language and/or verbosity locally. **Yes, individual agent definitions restate the rules.**

| File:line | What it says |
|-----------|--------------|
| `codex-debugger.md:94-95` — `### 5. Concise Output` | "Return actionable results, not raw Codex dumps." |
| `codex-debugger.md:97-101` — `## Language Rules` | Codex queries / Thinking / Output to main: English ×3. |
| `codex-debugger.md:103-123` | Fixed `## Output Format` template. |
| `fable-advisor.md:87` | "Keep the review note under ~100 lines." (only other numeric bound in the repo) |
| `fable-advisor.md:89-91` | "Return a **3-5 bullet summary** as your final message to the orchestrator. The orchestrator reports to the user in Japanese per `.claude/rules/language.md`; your output is in English." |
| `fable-advisor.md:93-97` — `## Language Rules` | Thinking / identifiers / output to orchestrator: English ×3. |
| `general-purpose-opus.md:64` | "Return a concise result rather than raw research or logs." |
| `general-purpose-opus.md:71` | "Code and technical documentation: English" |
| `general-purpose-opus.md:73-92` | Fixed `## Output Format` template (6 sections). |
| `general-purpose-sonnet.md:44` | "Report concise results and any evidence-backed escalation need." |
| `general-purpose-sonnet.md:52` | "Code and technical documentation must be English." |
| `general-purpose-sonnet.md:54-70` | Fixed `## Output Format` template (5 sections). |

Note the asymmetry: every "concise" in this tier means *concise back to the
orchestrator*. None of it constrains what the orchestrator then says to the user.

### Tier E — skills (`.claude/skills/**/SKILL.md`)

Skills that prescribe **language** to the user:

| File:line | What it says |
|-----------|--------------|
| `context-loader/SKILL.md:110-118` | "After loading context, briefly confirm **in Japanese**:" + 5 required bullets, including arrays "**quoted verbatim** … not paraphrased, not summarised as 'no issues'". A rare *anti*-conciseness constraint. |
| `init/SKILL.md:144-147` | "Report the evidence you used and the evidence you rejected, the two updated files, any `warnings`, and your recommendations **in Japanese**." |
| `update-lib-docs/SKILL.md:158-164` — `## Report` | "After updating, report to user (**in Japanese**):" + 3 bullets. |
| `checkpointing/SKILL.md:34-36` | "Write a **Japanese** five-part summary containing: 何をしたのか / どういうやり取りをユーザーと行ったのか / どうやったのか / 途中でどういう課題が起こったのか / 将来のアクション." Enforced by `checkpoint.py:141` (fixed Japanese subsection headings) and `checkpoint.py:1425`. |
| `checkpointing/SKILL.md:165-166` | "Report the checkpoint path, state blocks pruned, sections preserved, research notes archived, validation result, and remaining risks **in Japanese**." |
| `catchup/SKILL.md:174-176` | "`GUIDE.md` content follows the project's user-facing language convention (**Japanese** for this repository), while code identifiers and command names stay in English." |
| `design-tracker/SKILL.md:152-157` — `## Language Rules` | "**Report**: follow the surrounding session's language." **Contradicts** the unconditional CLAUDE.md rule. |
| `codex-system/SKILL.md:219-221` | Defers to `.claude/rules/language.md`. |

Skills that prescribe **report format** (no language statement — they inherit,
or fail to):

| File:line | Shape imposed |
|-----------|---------------|
| `tdd/SKILL.md:239-...` — `## Report Format` | `## TDD Complete: {name}` + Test Cases / Coverage / Quality Gates. |
| `team-execute/SKILL.md:708-...` — `## Step 2-4: Report to User` | `## Review Results: {feature}` + Summary / Critical-High Findings, with per-finding File/Issue fields. |
| `plan/SKILL.md:123-127` | 5 `###` sections, enforced as the `plan-doc` contract. |
| `design-tracker/SKILL.md:145-150` — `## Output Format` | "When recording, report **concisely**:" + 3 bullets. |
| `research-lib/SKILL.md:74`, `feature/SKILL.md:150`, `troubleshoot/SKILL.md:139`, `codex-system/SKILL.md:88` | "Return concise summary (5-7 key findings)" / "Return CONCISE summary" — all **subagent→lead**, not lead→user. |
| `feature:861`, `spike:552`, `troubleshoot:630` — `## Output Files` | Artifact paths, not prose style. |

### Tier F — hooks (`.claude/hooks/`, wired in `.claude/settings.json:7-101`)

Nine hook scripts exist. **None injects any language, tone, or verbosity
instruction.** Full inventory of what each one injects:

| Event (settings.json line) | Hook | What it injects into context |
|---|---|---|
| `UserPromptSubmit` (14) | `agent-router.py` (345 L) | `additionalContext` at 4 branch points (276-335): a routing hint naming Fable / Codex plugin / Codex CLI / Opus subagent, chosen from JA+EN keyword lists. |
| `PreToolUse: Edit\|Write` (26) | `check-codex-before-write.py` (227 L) | `[Codex Consultation Reminder] {reason}` when the path or content looks design-bearing (201-216). |
| `TeammateIdle` (37) | inline `echo` | Fixed `feedback` string: check the shared task list, write the work log to `.claude/logs/agent-teams/…` with 6 named sections, report to the team lead. |
| `TaskCompleted` (47) | `log-cli-tools.py` (295 L) | Appends to `.claude/logs/cli-tools.jsonl`; `additionalContext` at 286-287 reports the logged CLI call. |
| `PreCompact: auto` (59) | inline `echo` | Fixed `additionalContext`: names `CLAUDE.md`, `.claude/STATE.md`, `.claude/rules/`, `.claude/docs/DESIGN.md`, `AGENTS.md` as key context to retain. **Style is not among them.** |
| `PostToolUse: Task` (70) | `check-codex-after-plan.py` (85 L) | `[Codex Review Suggestion] {reason}` (65-75). |
| `PostToolUse: Bash` (80) | `post-bash-check.py` (99 L) | Dispatcher; joins the hints from `log-cli-tools`, `post-test-analysis`, `error-to-codex` into one `additionalContext` (88-93), de-duplicating the generic error hint against the targeted test hint. |
| ↳ in-process | `post-test-analysis.py` (172 L) | `[Codex Debug Suggestion] {reason}` on test/build failure text. |
| ↳ in-process | `error-to-codex.py` (210 L) | `[Error Detected] N error pattern(s)` → route to `codex-debugger`. Known false-positive source: matches output text, and only ever sees *successful* commands. |
| `PostToolUse: Edit\|Write` (90, 95) | `lint-on-save.py` (125 L) | Nothing — runs ruff/ty, emits no context. |
| `PostToolUse: Edit\|Write` (95) | `post-implementation-review.py` (185 L) | `[Code Review Suggestion] {reason}` after 2+ files / 50+ lines (163-175). |

### Tier G — non-Claude runtime reach

| File:line | Relevance |
|-----------|-----------|
| `.codex/AGENTS.md:3-6` | "The common CLI-agent contract … is the root `AGENTS.md`, which Codex loads automatically. Read that first." No language statement of its own. |
| `.codex/AGENTS.md:43-51` | Lists `.claude/rules/` as referenceable — not as required reading. |
| `.codex/config.toml:40-46` | Enables exactly two skills for Codex: `context-loader` and `design-tracker`. **`context-loader` is the transport that carries `.claude/rules/language.md` into a Codex run.** |
| `.agents/AGENTS.md:3-9` | Same deferral for Antigravity: root `AGENTS.md` first, tiers from `.claude/rules/tiers.md`. No language statement. `.agents/` contains only this one file. |
| `.agents/check.sh` | **Does not exist.** `CLAUDE.md:133-135` claims `.agents/` holds `tiers.md`, `INDEX.md`, `change_main.md`, `check.sh`, and `workflows/`; the directory in fact holds `AGENTS.md` only, and `scripts/check.sh:364-371` + `tests/test_orchestration_contract.py:150-155` actively *forbid* anything else. Pre-existing doc drift, unrelated to this task — do not "fix" it by adding files. |

---

## Duplication and gaps

### Said more than once

1. **The Japanese/English split is stated in at least six places**:
   `CLAUDE.md:116-120` (normative), `README.md:519-524`, `.claude/rules/delegation.md:31`,
   `.claude/rules/codex-delegation.md:133`, plus per-agent `## Language Rules`
   blocks in `codex-debugger.md:97-101` and `fable-advisor.md:93-97`, plus
   `general-purpose-{opus,sonnet}.md` ("Code and technical documentation: English").
2. **"Report in Japanese" is re-stated per-skill** in six SKILL.md files
   (`context-loader:110`, `init:147`, `update-lib-docs:160`, `checkpointing:34`
   and `:166`, `catchup:174`). Every one of these would be redundant under a
   single style rule, and each is an independent drift site.
3. **"Return a concise summary" appears in six skills and two agents**
   (`research-lib:74`, `feature:150`, `troubleshoot:139`, `codex-system:88`,
   `design-tracker:147`, `general-purpose-opus.md:64`,
   `general-purpose-sonnet.md:44`, `codex-debugger.md:94`) — all inward-facing.
4. **Three mutually inconsistent SSOT claims for language**:
   - `.claude/rules/language.md:3-4` → SSOT is `CLAUDE.md ## Language Protocol`.
   - `.claude/skills/codex-system/SKILL.md:221` → SSOT is `.claude/rules/language.md`.
   - `.claude/rules/codex-delegation.md:133` → SSOT is root `AGENTS.md` section
     "Language Protocol", **which does not exist and cannot be created**
     (`tests/test_orchestration_contract.py:107-108`).
5. **One outright contradiction**: `design-tracker/SKILL.md:157` — "**Report**:
   follow the surrounding session's language" — against `CLAUDE.md:120`'s
   unconditional "Communicate with the user in Japanese".

### Said nowhere (the gaps)

1. **Verbosity of the user-facing reply is entirely unspecified.** Confirmed:
   the suspicion is correct. `CLAUDE.md:88-89` fixes the *order* (conclusion
   first) and never the length. The only numeric bounds in the repo are
   `AGENTS.md:29` ("`## TL;DR` — Conclusion in 3 lines or fewer", which binds
   the *CLI-contract* response template, not the Japanese conversational reply)
   and `fable-advisor.md:87` ("review note under ~100 lines", an artifact, not a
   message). Nothing says how long a normal answer to the user should be.
2. **"Concise **but complete**" has no expression at all.** Everything that
   says "concise" says only "shorter"; the only completeness pressure lives in
   `CLAUDE.md:16` ("state assumptions, uncertainty, failures, and remaining
   risks explicitly"), `CLAUDE.md:114` ("Report the cause and blast radius of
   every failed or unrun check"), and `context-loader/SKILL.md:113-114` (quote
   arrays verbatim, never summarise as "no issues"). The two pressures are never
   reconciled in one place, so an agent choosing between them has no rule.
3. **"Natural Japanese" is nowhere.** The word "Japanese" always appears as a
   language *selector*. There is no guidance on translationese, register /
   politeness level, katakana-vs-English term handling, or mixed-script
   formatting — even though `checkpointing` and `design-tracker` hard-code
   Japanese headings and `catchup:174-176` splits Japanese prose from English
   identifiers.
4. **Root `AGENTS.md` carries no language rule**, so the file that "every CLI
   agent loads automatically" is silent on the one policy every runtime must
   apply. Codex and Antigravity get the *structure* (`## Required Response
   Structure`) with no language binding, and the rule that was supposed to point
   them at it (`codex-delegation.md:133`) points at a section that does not exist.
5. **No `outputStyle`.** Claude Code's native mechanism for exactly this is
   unused, and (see Insertion point D) largely unusable here.
6. **No hook injects style.** Nine hooks, all routing/QA hints; the `PreCompact`
   reminder lists five context files and style is not among them, so response
   style is silently the first thing lost across a compaction.

---

## Insertion points

### A. `CLAUDE.md` — extend `## Language Protocol`

- **File**: `/home/user/claude-code-orchestra/CLAUDE.md`
- **Anchor**: insert after **line 120** (`- Communicate with the user in Japanese.`),
  before the blank line 121 and `## Native Runtime Boundary` at line 122.
- **Reach**: Claude Code main agent only. Subagents launched via Task do not
  auto-load it; Codex/Antigravity reach it only by following `AGENTS.md:13`.
- **What would break**:
  - **Hard 150-line cap, twice.** `scripts/check.sh:260-263` (`wc -l > 150` →
    FAIL "CLAUDE.md exceeds 150 lines") and `tests/test_orchestration_contract.py:51`
    (`len(content.splitlines()) <= 150`). The file is **147 lines today —
    exactly 3 lines of headroom for heading, blank line, and content combined.**
    A 3-bullet addition consumes all of it and leaves the file permanently at
    the cliff edge.
  - `## Language Protocol` must remain a verbatim line, exactly once:
    `check.sh:186` (`grep -Fxq`) and `test:44-45` (`content.count(...) == 1`).
    Do not rename it, do not add a second occurrence anywhere in the file.
  - The literal string `Japanese` must survive (`check.sh:271`, `test:60`).
  - No `@orchestra:` marker may be introduced (`check.sh:275-278`, `test:64`).

### B. `.claude/rules/language.md` — add a `## Response Style` section  ← recommended

- **File**: `/home/user/claude-code-orchestra/.claude/rules/language.md`
- **Anchor**: append after **line 8** (end of file; the file is 8 lines total).
  If the new content is to be normative, **line 7-8** ("This rule does not
  override or duplicate the shared contract.") must be reworded, since it
  currently declares the file non-normative.
- **Reach**: every runtime that runs `context-loader` — which `CLAUDE.md:71`
  makes mandatory for the main agent and `.codex/config.toml:40-42` enables for
  Codex. `load_context.py:47-56` lists `language` as the 4th preferred rule, so
  it is loaded deterministically and early. Already cited by name as the
  language authority by `fable-advisor.md:90` and `codex-system/SKILL.md:221`.
- **What would break**: **nothing mechanical.**
  - Not referenced by any assertion in `scripts/check.sh`.
  - Not referenced by any test (`grep -rn 'language.md' tests/` → no match).
  - No line cap.
  - `.claude/rules` is a whole-directory `SAFE_DIR` in `scripts/install.sh:8`
    and `scripts/update.sh:29-30`, so it is installed and rsynced wholesale — no
    manifest entry to add.
  - `.claude/docs/INDEX.md:21` already registers `.claude/rules/` generically as
    normative, so no INDEX edit is needed and `check.sh:28-52` stays green.
  - Caveat, not a breakage: it is loaded *by a skill*, not auto-loaded. An agent
    that skips `context-loader` never sees it. Mitigate with one pointer line in
    `CLAUDE.md ## Language Protocol` (costs 1 of the 3 remaining lines).

### C. Root `AGENTS.md` — new section after `## Handoff Rules`

- **File**: `/home/user/claude-code-orchestra/AGENTS.md`
- **Anchor**: insert at **line 56** — after line 55
  (`- Include a migration plan whenever compatibility may break`) and before
  line 57 (`## Cross-CLI Subagent Invocation`).
- **Reach**: broadest of all. `AGENTS.md:3` and `CLAUDE.md:7-8` both assert every
  runtime auto-loads it, main agent included. It already owns the two adjacent
  concerns (`## Required Response Structure`, `## Handoff Rules`).
- **What would break**:
  - **The heading must NOT be `## Language Protocol`** — nor any of the other
    nine `REQUIRED_HEADINGS` from `tests/test_orchestration_contract.py:16-27`.
    Line 107-108 of that test asserts `policy_heading not in content` for all
    ten. `## Response Style`, `## Output Style`, `## Reporting Style` are all safe.
  - The four self-contained sections at `check.sh:290-296` / `test:90-96` and
    the four routes at `check.sh:297-304` / `test:99-105` must remain intact and
    verbatim; insertion between sections does not disturb them.
  - No line cap applies to `AGENTS.md` (222 lines today).
  - Side effect to accept: this splits the policy — language would live in
    `CLAUDE.md`, style in `AGENTS.md` — unless the language rule moves too, which
    the forbidden-heading test blocks.

### D. `.claude/settings.json` — `outputStyle`

- **File**: `/home/user/claude-code-orchestra/.claude/settings.json`, anchor
  line 3-6 (alongside `"language"`, `"effortLevel"`).
- **What would break**: adding the key itself is safe —
  `check.sh:376-380` only requires `.claude/hooks/` to be referenced and
  `.agents/hooks/` to be absent. **But a custom output style needs a
  `.claude/output-styles/` directory, and that directory is forbidden**: the
  `.claude/` top-level whitelist in `check.sh:349-357` accepts only
  `settings.json | settings.local.json | settings.orchestra.json |
  orchestra-version | agents | skills | rules | hooks | docs | logs |
  checkpoints | STATE.md`, and `tests/test_orchestration_contract.py` enforces
  the same shape. Adding the directory turns check 7 red.
  → Only a **built-in** outputStyle value is viable, and it reaches Claude Code
  only. Not a home for a written rule.

### E. New file `.claude/rules/response-style.md`

- **What would break**: nothing mechanical (same SAFE_DIR and INDEX reasoning
  as B; `load_context.py:130` appends unlisted rule stems alphabetically, so it
  would load automatically).
- **Why it is still the wrong choice**: it is precisely the "seventh place" the
  objective exists to avoid. It would leave language in `CLAUDE.md`, the
  language pointer in `language.md`, and style in a third file — three hops for
  one policy.

### F. A hook (`agent-router.py`, `UserPromptSubmit`)

- **File**: `/home/user/claude-code-orchestra/.claude/hooks/agent-router.py`,
  anchor lines 276-335 (the four existing `additionalContext` emit sites).
- **What would break**: nothing structurally. But the hook currently emits
  *conditionally* on keyword match; an unconditional style reminder would fire
  on every prompt, spending tokens each turn, and it reaches Claude Code only
  (hooks are wired in `.claude/settings.json`, which Codex and Antigravity never
  read). Useful later as *reinforcement* after a compaction; wrong as the
  *definition*.

---

## Guardrails

What the mechanical checks would reject. `bash scripts/check.sh` currently
exits **0** (8 passed, 0 failed).

### `scripts/check.sh` — the eight checks and what each forbids

| # | Check (line) | Rejects |
|---|---|---|
| 1 | `check_index_links` (28) | Any backticked-relative or parenthesised path in `.claude/docs/INDEX.md` that does not resolve on disk. Adding an INDEX row for a file you did not create → FAIL. |
| 2 | `check_tier_ids` (58) | Loss of `` `default` ``, `` `sol` ``, `` `fable` `` from `tiers.md`. Not touched by this work. |
| 3 | `check_model_coherence` (80) | `CODEX_MODEL` in `settings.json` ≠ `model` in `config.toml`. **Relevant only as a warning: if you edit `.codex/config.toml` to change `verbosity`, do not disturb lines 5 or the `${CODEX_MODEL:-…}` fallbacks.** |
| 4 | `check_safe_dirs` (152) | A template-owned runtime dir missing from `update.sh` SAFE_DIRS. `.claude/rules` is already covered. |
| 5 | `check_root_contract` (171) | `CLAUDE.md` missing/symlinked; **any of the 10 `##` headings absent** (exact-line match, `grep -Fxq`, list at 179-190, includes `## Language Protocol`); any agent or skill name not present as `` `name` ``; existence of `.claude/rules/orchestration.md`; INDEX's "Root agent contract" row not marked `normative`. |
| 6 | `check_bootstrap_references` (257) | **`CLAUDE.md` > 150 lines** (260-263; now 147 → 3 free); loss of any of the six required path strings (266-274); loss of the literal `Japanese` (271) or a case-insensitive `verify` (272); any `@orchestra:` marker (275-278); **root `AGENTS.md`** missing any of its 4 self-contained `##` sections (290-296) or any of its 4 routes (297-304). |
| 7 | `check_native_boundaries` (314) | A canonical `.claude/*` dir missing or symlinked; any of 8 contract files being a symlink; runtime content duplicated into `.agents/`/`.codex/`; **any unexpected top-level entry under `.claude/` (349-357), `.codex/` (358-363), or `.agents/` (364-371)** — this is what blocks `.claude/output-styles/`; settings not referencing `.claude/hooks/`; Codex config not referencing the two canonical skill paths. |
| 8 | `check_skill_scripts` (397) | A `.claude/skills/**.py|.sh` path named in shared markdown that does not exist, and any bundled script documented nowhere. Markdown-only edits are unaffected; note `research/` and `reviews/` are excluded from the doc scope (405-410), so **this audit file itself is exempt.** |

Dead code worth knowing: `check_ordered_references` is defined at
`scripts/check.sh:236` and **never called**. Reference ordering in `CLAUDE.md`
is therefore not actually enforced by check.sh today.

### `validate_doc.py` — rejects nothing here

`.claude/skills/_shared/validate_doc.py:163-281` registers exactly six
contracts: `work-log`, `feature-brief`, `lib-doc`, `plan-doc`, `design-doc`,
`state-doc`. **None covers `CLAUDE.md`, `AGENTS.md`, `.claude/rules/*.md`, or a
research note.** There is no `--contract` that would validate a response-style
rule file, and none that this change could violate. Structure for `CLAUDE.md`
and `AGENTS.md` is enforced only by `scripts/check.sh` checks 5-6 and by
`tests/test_orchestration_contract.py`.

### `tests/test_orchestration_contract.py` — the binding assertions

| Line | Asserts |
|---|---|
| 16-27 | `REQUIRED_HEADINGS` = the 10 `CLAUDE.md` `##` sections, incl. `## Language Protocol`. |
| 44-45 | Each appears in `CLAUDE.md` **exactly once**. |
| 51 | `len(CLAUDE.md.splitlines()) <= 150`. |
| 60-63 | `CLAUDE.md` contains `Japanese`, `.claude/docs/change_main.md`, `Claude Code`, `verify` (lowercased), and no `@orchestra:`. |
| 68-80 | Every `.claude/agents/*.md` stem and every `.claude/skills/*/SKILL.md` dir name appears in `CLAUDE.md` as `` `name` ``. |
| 90-105 | Root `AGENTS.md` has its 4 sections exactly once and its 4 routes present. |
| **107-108** | **Root `AGENTS.md` contains none of the 10 `CLAUDE.md` headings.** This is the single assertion that decides insertion point C's heading name. |
| 150-158 | `.agents/` entries == `{AGENTS.md}`; `.codex/` entries == `{config.toml, AGENTS.md}`. |

### Installer / updater

No manifest work is needed for a `.claude/rules/` change: `scripts/install.sh:8`
lists `.claude/rules` among owned paths and `scripts/update.sh:29-30` lists it in
`SAFE_DIRS`, both of which sync the directory wholesale. A *new* top-level file
or directory anywhere else would need both a manifest entry and a check-7
whitelist change.

---

## Recommendation

Put the rule in **`.claude/rules/language.md`** (insertion point B), and spend
**one** of `CLAUDE.md`'s three remaining lines on a pointer to it from
`## Language Protocol` (line 120).

Rationale in one paragraph: it is the only file in the repo whose stated
purpose is already "the shared language rule every runtime applies", it is
8 lines long with no cap, it has **zero** mechanical guards, it is already
loaded deterministically by `context-loader` for both Claude and Codex, and two
existing documents (`fable-advisor.md:90`, `codex-system/SKILL.md:221`) already
cite it as the authority — so the change *removes* an SSOT contradiction rather
than adding a seventh location. Adding it to `CLAUDE.md` instead would fit only
by exhausting the entire 150-line budget; adding it to root `AGENTS.md` reaches
more runtimes but is forbidden the `## Language Protocol` heading and splits
language from style.

Two cleanups that should ride along, since they are the actual duplication:
fix `.claude/rules/codex-delegation.md:133`'s pointer to a nonexistent
`AGENTS.md` section, and reconcile `design-tracker/SKILL.md:157`'s
"follow the surrounding session's language" with the unconditional rule.
