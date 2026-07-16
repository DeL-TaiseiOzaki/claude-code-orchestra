# Design Document — 要件定義書 (Requirements & Macro Design)

> **Role:** Macro-level requirements and design — *what* this project builds and *why*.
> Written at `/init`, kept current by `/design-tracker` (also invoked from `/checkpointing`).
>
> **Document map:** Orchestrator contract → [CLAUDE.md](../../CLAUDE.md) ·
> Micro work progress (latest 5 checkpoints) → [PROGRESS.md](../../PROGRESS.md)

## 背景・目的 (Background & Purpose)

<!-- Why does this project exist? What problem does it solve, for whom?
     State the business/technical context and the goal in a few sentences. -->

## スコープ (Scope)

### In Scope

<!-- What this project explicitly delivers. -->

- 

### Out of Scope

<!-- What is explicitly NOT covered, to prevent scope creep. -->

- 

## 機能要件 (Functional Requirements)

<!-- What the system must do. Each requirement gets a stable ID (FR-1, FR-2, ...). -->

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | | | |

## 非機能要件 (Non-Functional Requirements)

<!-- Quality attributes: performance, availability, security, maintainability, etc.
     Prefer measurable targets in the Metric column. -->

| Category | Requirement | Metric / Target |
|----------|-------------|-----------------|
| Performance | | |
| Availability | | |
| Security | | |
| Maintainability | | |

## アーキテクチャ (Architecture)

<!-- High-level architecture: components, data flow, boundaries.
     Add a diagram or description here. -->

### Agent Roles

| Agent | Role | Responsibilities |
|-------|------|------------------|
| | | |

## 技術選定 (Tech Stack & Rationale)

<!-- Chosen technologies and why. Record alternatives considered. -->

| Area | Technology | Rationale | Alternatives Considered |
|------|------------|-----------|-------------------------|
| | | | |

## 制約 (Constraints)

<!-- Technical, organizational, regulatory, or resource constraints. -->

- 

## Key Decisions

<!-- Durable architectural/design decisions. Append-only log. -->

| Decision | Rationale | Alternatives Considered | Date |
|----------|-----------|------------------------|------|
| 3-tier agent hierarchy (default/sol/fable) redefined in repo terms | Maps vault's Sonnet/Sol/Fable onto orchestrator-direct + subagents / Codex / rare advisor without renaming existing machinery | Import vault terminology as-is (mismatch with Opus orchestrator design) | 2026-07-10 |
| Sol = gpt-5.6-sol at xhigh effort, bumped only at central points (settings.json env.CODEX_MODEL, .codex/config.toml) + fallback sweep | Single-point model management preserved; template self-consistency (SAFE_DIRS files are overwritten wholesale on update) | Per-file hardcoding; leaving stale prior-model fallbacks | 2026-07-10 |
| Keep approval_policy="never"; safety via completion-verification guardrails | Non-interactive hooks/Agent-Teams flows must not block; writes already require caller's explicit --sandbox workspace-write | Strict read-only default with approval escalation (blocks autonomous template flows) | 2026-07-10 |
| .agents/ = canonical spec for CLI subagents; .claude/ = main-agent spec; .codex/ = adapter | .codex-centric layout hindered adding other CLI subagents (Antigravity, Grok); user decision | Full centralization incl. .claude (drift risk without a generator); no neutral layer | 2026-07-10 |
| Tier-1 model norm: implementation subagents on Sonnet, research/large analysis on Opus 1M | Cost/perf split per task type; user decision | All-Opus (costly); all-Sonnet (loses 1M-ctx analysis) | 2026-07-10 |
| Fable = rare escalation advisor, differentiated from team-execute Phase 2 reviewers and /codex:adversarial-review | Scarcity keeps signal high; read-only + reviews/ output enforces "never implements" | Fable as routine reviewer (duplicates ship-gate reviews) | 2026-07-10 |
| _shared/ is a bundled runtime, not a skill: skills may depend on _shared/, never on each other | Preserves skill independence while deduplicating deterministic helpers; update.sh syncs skills dir atomically | Per-skill script duplication; cross-skill imports | 2026-07-10 |
| Document writers (Zone C append, DESIGN.md update) are scripts with typed-JSON input, dry-run default, --apply, atomic replace, stable-ID idempotency | Mis-writes to CLAUDE.md/DESIGN.md are the top risk of mechanized writes; structure validation + no-op/conflict semantics contain it | LLM edits documents directly from prose templates (re-interpretation risk) | 2026-07-10 |
| Embedded SKILL.md output templates moved to per-skill references/ as content contracts, not scaffold scripts | Templates are contracts, not computation; avoids generator API/test/empty-file debt (Codex recommendation, user-approved) | Scaffolder scripts pre-filling deterministic fields; keep templates inline | 2026-07-10 |
| codex exec invocations always append < /dev/null (and prefer timeout) | codex exec waits for stdin EOF and hangs indefinitely when stdin is left open — observed 27-minute hang in background shell | Leave stdin handling to callers (repeated hangs) | 2026-07-10 |
| Existing-project installation uses a conflict-aware installer with opt-in replacement backups | A template must not silently overwrite project-owned Claude/Codex configuration; default abort, Zone C preservation, settings merge candidates, and symlink escape checks make first-time installation reviewable | README cp -r one-liner; unconditional overwrite; updater-only bootstrap | 2026-07-16 |
| Store downstream Orchestra version state in .claude/orchestra-version and never update the downstream root VERSION | Root VERSION commonly belongs to the application receiving the template, so namespacing prevents template updates from corrupting the application's release version | Continue treating root VERSION as template-owned; omit installed-version tracking | 2026-07-16 |
| /init updates DESIGN.md and CLAUDE.md Zone B but never modifies root AGENTS.md | Root AGENTS.md is a template-owned discovery pointer to the canonical .agents contract and is fully replaced by template updates; project identity already has durable homes in DESIGN.md and CLAUDE.md Zone B | Store project identity in root AGENTS.md; make AGENTS.md a hybrid merged file | 2026-07-16 |
| Split the former single Claude execution agent into general-purpose-sonnet (default implementation) and general-purpose-opus (research, analysis, difficult implementation, and Codex delegation) | Task-based routing preserves Sonnet cost and speed for well-scoped work while allowing Opus for ambiguity, cross-system invariants, high-risk domains, or failed attempts; file count alone is not a capability signal | Single Opus agent for all tasks; single Sonnet agent for all tasks; route only by file count | 2026-07-16 |

## TODO / Open Questions

- [ ] Promote .agents/ to full SSOT only when: deterministic generator with --check, update.sh migration tests from old VERSIONs, and a proven Antigravity adapter exist
- [x] agent-router.py: bare 「レビュー」/"review" in CODEX_TRIGGERS shadows CODEX_PLUGIN_TRIGGERS review entries — fixed 2026-07-11 (plugin triggers checked before broad Codex triggers)
- [ ] Full Antigravity support (workflows are experimental skeletons; not executable yet)
- [ ] update.sh rsync of SAFE_DIRS is not strictly atomic; consider stage-and-swap or post-sync self-check if interruption tolerance is needed
