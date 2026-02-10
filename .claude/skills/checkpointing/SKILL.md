---
name: checkpointing
description: |
  Save full session context: git history, CLI consultations, Agent Teams activity,
  and discover reusable skill patterns — all in one run. No flags needed.
  Run at session end, after major milestones, or when you want to capture learnings.
metadata:
  short-description: Full session checkpoint with skill pattern discovery
---

# Checkpointing — セッションの全記録とパターン発見

**セッションの全活動を記録し、再利用可能なパターンを発見する。毎回全部やる。**

## What It Does (Every Time)

```
/checkpointing
    ↓
┌─────────────────────────────────────────────────────────────┐
│  1. Collect Everything                                       │
│     ├── git log (commits, file changes, line stats)          │
│     ├── CLI logs (Codex/Gemini consultations)                │
│     ├── Agent Teams activity (tasks, teammates, messages)    │
│     └── Design decisions (.claude/docs/DESIGN.md changes)    │
│                                                              │
│  2. Generate Slug & Tags (for fast retrieval)                │
│     ├── Auto-slug from commit messages (or --label)          │
│     └── Semantic tags from file paths, CLI usage, teams      │
│                                                              │
│  3. Generate Checkpoint (with YAML frontmatter)              │
│     → .claude/checkpoints/YYYY-MM-DD-HHMMSS-{slug}.md       │
│                                                              │
│  4. Update INDEX.md Catalog                                  │
│     → .claude/checkpoints/INDEX.md (one-file lookup)         │
│                                                              │
│  5. Update Session History                                   │
│     → CLAUDE.md (cross-session persistence)                  │
│                                                              │
│  6. Discover Skill Patterns                                  │
│     → Subagent analyzes checkpoint                           │
│     → Suggests reusable skills                               │
│     → User reviews and approves                              │
└─────────────────────────────────────────────────────────────┘
```

## Usage

```bash
# Everything. No flags needed.
/checkpointing

# Optional: custom label for the checkpoint
/checkpointing --label "auth-module-redesign"

# Optional: only look at recent work
/checkpointing --since "2026-02-08"

# Both
/checkpointing --label "agent-teams-integration" --since "2026-02-08"
```

## What Gets Captured

### Git Activity

- Commits (hash, message, date)
- File changes (created, modified, deleted + line counts)
- Branch information

### CLI Consultations

- Codex consultations (prompt, success/failure)
- Gemini researches (prompt, success/failure)

### Agent Teams Activity

- Team composition (Lead + Teammates, roles)
- Shared task list state (completed, in-progress, pending)
- File ownership per teammate
- Communication patterns (who messaged whom, about what)
- Team effectiveness signals (tasks completed vs stuck, file conflicts)

### Design Decisions

- Changes to `.claude/docs/DESIGN.md` since last checkpoint
- New entries in Key Decisions table

## Fast Retrieval System

Claude Code can efficiently find relevant checkpoints using three layers:

### Layer 1: INDEX.md (Read one file, find everything)

`.claude/checkpoints/INDEX.md` is a table cataloging all checkpoints:

```markdown
| Timestamp | Checkpoint | Branch | Tags | Stats | Summary |
|---|---|---|---|---|---|
| 2026-02-08-153000 | [feature-agent-teams](2026-02-08-153000-feature-agent-teams.md) | main | feature, agent-teams, .claude | 12c/15f/3cx/2gm/1tm | redesign startproject for Opus 4.6; add team-implement skill |
| 2026-02-07-120000 | [bugfix-auth-flow](2026-02-07-120000-bugfix-auth-flow.md) | fix/auth | bugfix, src, testing | 5c/8f/1cx | fix token refresh race condition |
```

**How Claude uses it**: Read INDEX.md → scan tags/summary columns → open only the relevant checkpoint file.

### Layer 2: YAML Frontmatter (Quick scan without full parse)

Each checkpoint starts with structured metadata:

```yaml
---
id: feature-agent-teams-2026-02-08-153000
timestamp: 2026-02-08-153000
branch: main
slug: feature-agent-teams
summary: "redesign startproject for Opus 4.6; add team-implement skill"
tags: [feature, agent-teams, .claude, codex, gemini]
commits: 12
files_changed: 15
codex_consultations: 3
gemini_researches: 2
agent_teams: 1
---
```

**How Claude uses it**: Read first 15 lines of a checkpoint → decide if it's relevant without parsing the full document.

### Layer 3: Meaningful Filenames

Filenames include an auto-generated slug from commit messages:

```
2026-02-08-153000-feature-agent-teams.md     (auto from "feat:" commits)
2026-02-07-120000-bugfix-auth-flow.md        (auto from "fix:" commits)
2026-02-06-090000-auth-module-redesign.md    (from --label)
```

**Slug generation priority**: `--label` flag > conventional commit type + keywords > "session"

## Checkpoint Format

```markdown
---
id: feature-agent-teams-2026-02-08-153000
timestamp: 2026-02-08-153000
branch: main
slug: feature-agent-teams
summary: "redesign startproject for Opus 4.6; add team-implement skill"
tags: [feature, agent-teams, .claude, codex, gemini]
commits: 12
files_changed: 15
codex_consultations: 3
gemini_researches: 2
agent_teams: 1
---

# Checkpoint: 2026-02-08 15:30:00 UTC

## Summary
- **Commits**: 12
- **Files changed**: 15 (10 modified, 4 created, 1 deleted)
- **Codex consultations**: 3
- **Gemini researches**: 2
- **Agent Teams sessions**: 1 (3 teammates)
- **Tasks completed**: 8/10

## Git History

### Commits
- `abc1234` feat: redesign startproject for Opus 4.6
- `def5678` feat: add team-implement skill
...

### File Changes
**Created:**
- `.claude/skills/team-implement/SKILL.md` (+180)
...

**Modified:**
- `CLAUDE.md` (+40, -25)
...

## CLI Consultations

### Codex (3 consultations)
- ✓ Design: Architecture for Agent Teams integration
- ✓ Debug: Task dependency resolution
- ✗ Review: (timeout)

### Gemini (2 researches)
- ✓ Research: Agent Teams best practices
- ✓ Research: Library comparison for httpx vs aiohttp

## Agent Teams Activity

### Team: project-planning
**Composition:**
- Lead: Claude (orchestration)
- Researcher: Gemini-powered (external research)
- Architect: Codex-powered (design decisions)

**Task List:**
- [x] Research library options (Researcher)
- [x] Design module architecture (Architect)
- [x] Validate API constraints (Researcher)
- [x] Finalize implementation plan (Architect)

**Communication Patterns:**
- Researcher → Architect: 3 messages (library constraints)
- Architect → Researcher: 2 messages (additional research requests)

**Effectiveness:**
- All tasks completed
- No file conflicts
- 2 design iterations triggered by research findings

## Design Decisions (New)
- Agent Teams for Research ↔ Design (bidirectional)
- Gemini role narrowed to external info + multimodal

## Skill Pattern Suggestions

### Pattern 1: Research-Design Iteration (Confidence: 0.85)
**Evidence:** Researcher and Architect exchanged findings 5 times, each
exchange refined the design. This back-and-forth is a repeatable pattern.

**Suggested skill:** Already captured as /startproject Phase 2.

### Pattern 2: Parallel File-Isolated Implementation (Confidence: 0.75)
**Evidence:** 3 implementers worked on separate modules with zero conflicts.
Module boundaries were defined by directory ownership.

**Suggested skill:** Already captured as /team-implement.

---
*Generated by checkpointing skill*
```

## Session History Update

Each checkpoint also appends a concise summary to CLAUDE.md:

```markdown
## Session History

### 2026-02-08
- 12 commits, 15 files changed
- Codex: 3 consultations (design, debug, review)
- Gemini: 2 researches (agent teams, library comparison)
- Agent Teams: 1 session (3 teammates, 8/10 tasks completed)
- New skills: /team-implement, /team-review
- Key decisions: Agent Teams for parallel work, Gemini role narrowed
```

This persists across sessions — new sessions load CLAUDE.md and see what happened before.

## Skill Pattern Discovery

The checkpoint is automatically analyzed to find reusable patterns:

**What it looks for:**
- Sequences of commits forming logical workflows
- File change patterns (e.g., test + implementation together)
- CLI consultation sequences (research → design → implement)
- Agent Teams coordination patterns (team composition, task sizing)
- Multi-step operations that could be templated

**Output:** Skill suggestions with confidence scores. High-confidence patterns (>= 0.8) that don't match existing skills are presented to the user for approval.

## Execution Flow

```
/checkpointing [--label "name"] [--since "YYYY-MM-DD"]
    │
    ├─ 1. Run checkpoint.py (collects git + CLI + teams data)
    │
    ├─ 2. Generate slug (from commits or --label) and semantic tags
    │
    ├─ 3. Write checkpoint with YAML frontmatter
    │     → .claude/checkpoints/YYYY-MM-DD-HHMMSS-{slug}.md
    │
    ├─ 4. Update INDEX.md catalog (newest first)
    │     → .claude/checkpoints/INDEX.md
    │
    ├─ 5. Update CLAUDE.md with session summary
    │
    └─ 6. Spawn subagent for skill pattern analysis
          → Reads checkpoint file
          → Identifies reusable patterns
          → Reports suggestions to user
          → User approves → new skills created in .claude/skills/
```

## When to Run

| Timing | Why |
|--------|-----|
| セッション終了前 | 全活動を記録、次セッションへの引き継ぎ |
| `/team-implement` 完了後 | チーム活動パターンを捕捉 |
| `/team-review` 完了後 | レビューパターンを捕捉 |
| 大きな設計決定後 | 決定のコンテキストを永続化 |
| 繰り返しパターンを感じた時 | スキル化の発見チャンス |

## Notes

- チェックポイントは `.claude/checkpoints/` に蓄積される（`.gitignore` 済み）
- `INDEX.md` を読むだけで全チェックポイントのタグ・要約を検索可能
- 各ファイルの先頭 YAML frontmatter で、フルパースせずに内容を判定可能
- `--label` で任意のスラグを指定可能（省略時はコミットメッセージから自動生成）
- ログファイル自体は変更されない（読み取りのみ）
- スキル提案は必ずユーザーがレビューしてから採用すること
- Agent Teams のデータは `~/.claude/teams/` と `~/.claude/tasks/` から収集
