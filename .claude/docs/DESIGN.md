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
| | | | |
| _shared/ is a bundled runtime, not a skill: skills may depend on _shared/, never on each other | Preserves skill independence while deduplicating deterministic helpers; update.sh syncs skills dir atomically | Per-skill script duplication; cross-skill imports | 2026-07-10 |
| Document writers (Zone C append, DESIGN.md update) are scripts with typed-JSON input, dry-run default, --apply, atomic replace, stable-ID idempotency | Mis-writes to CLAUDE.md/DESIGN.md are the top risk of mechanized writes; structure validation + no-op/conflict semantics contain it | LLM edits documents directly from prose templates (re-interpretation risk) | 2026-07-10 |
| Embedded SKILL.md output templates moved to per-skill references/ as content contracts, not scaffold scripts | Templates are contracts, not computation; avoids generator API/test/empty-file debt (Codex recommendation, user-approved) | Scaffolder scripts pre-filling deterministic fields; keep templates inline | 2026-07-10 |
| codex exec invocations always append < /dev/null (and prefer timeout) | codex exec waits for stdin EOF and hangs indefinitely when stdin is left open — observed 27-minute hang in background shell | Leave stdin handling to callers (repeated hangs) | 2026-07-10 |

## TODO / Open Questions

- [ ] 

- [ ] update.sh rsync of SAFE_DIRS is not strictly atomic; consider stage-and-swap or post-sync self-check if interruption tolerance is needed
