# Project Design Document

> This document tracks design decisions made during conversations.
> Updated automatically by the `design-tracker` skill.

## Overview

Claude Code Orchestra is a multi-agent collaboration framework that orchestrates Claude Code (1M context), Codex CLI (deep reasoning), and Gemini CLI (external research + multimodal) to accelerate development. With Opus 4.6, the framework leverages Agent Teams for parallel work.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Claude Code Lead (Opus 4.6 — 1M context)                       │
│  Role: Orchestration, codebase analysis, user interaction        │
│                                                                   │
│  ┌──────────────────────┐  ┌──────────────────────┐             │
│  │ Agent Teams           │  │ Subagents             │             │
│  │ (parallel + comms)    │  │ (isolated + results)  │             │
│  │                       │  │                       │             │
│  │ Researcher ←→ Archit. │  │ Codex consultation    │             │
│  │ Implementer A/B/C     │  │ Gemini research       │             │
│  │ Security/Quality Rev. │  │ Error analysis        │             │
│  └──────────────────────┘  └──────────────────────┘             │
│                                                                   │
│  External CLIs:                                                   │
│  ├── Codex CLI (gpt-5.3-codex) — deep reasoning, design          │
│  └── Gemini CLI (gemini-3-pro) — web search, multimodal          │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Patterns & Approaches

| Pattern | Purpose | Notes |
|---------|---------|-------|
| Agent Teams | Parallel work with inter-agent communication | /startproject, /team-implement, /team-review |
| Subagents | Isolated tasks returning results | Codex/Gemini consultation when teams not needed |
| Skill Pipeline | `/startproject` → `/team-implement` → `/team-review` | Separation of concerns across skills |

### Libraries & Roles

| Library | Role | Version | Notes |
|---------|------|---------|-------|
| Codex CLI | Deep reasoning partner | gpt-5.3-codex | Design, debug, trade-offs |
| Gemini CLI | External information + multimodal | gemini-3-pro | Web search, PDF/video/audio |

### Key Decisions

| Decision | Rationale | Alternatives Considered | Date |
|----------|-----------|------------------------|------|
| Claude handles codebase analysis directly | Opus 4.6 has 1M context, no need to delegate to Gemini | Keep Gemini for codebase analysis | 2026-02-08 |
| Gemini role narrowed to external info + multimodal | Claude's 1M context makes Gemini's codebase analysis redundant; Gemini's unique value is Google Search and multimodal | Keep broad Gemini role | 2026-02-08 |
| /startproject split into 3 skills | Separation of Plan/Implement/Review gives user control gates | Single monolithic skill | 2026-02-08 |
| Agent Teams for Research ↔ Design | Bidirectional communication enables iterative refinement | Sequential subagents (old approach) | 2026-02-08 |
| Agent Teams for parallel implementation | Module-based ownership avoids file conflicts | Single-agent sequential implementation | 2026-02-08 |
| Subagent threshold relaxed to ~50 lines | 1M context can absorb more direct output | Keep 10-line threshold | 2026-02-08 |

## TODO

- [ ] Update gemini-system and codex-system skills to match new delegation rules
- [ ] Test Agent Teams workflow end-to-end with a real project
- [ ] Evaluate if gemini-explore agent should be removed or repurposed
- [ ] Update hooks for Agent Teams quality gates

## Open Questions

- [ ] Optimal team size for /team-implement (2-3 vs 4-5 teammates)?
- [ ] Should /team-review be mandatory or optional?
- [ ] How to handle Compaction in long Agent Teams sessions?

## Changelog

| Date | Changes |
|------|---------|
| 2026-02-08 | Major redesign for Opus 4.6: 1M context, Agent Teams, skill pipeline |
| | Initial |
