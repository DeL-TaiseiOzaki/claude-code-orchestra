---
name: startproject
description: |
  Start a new project/feature implementation session with multi-agent collaboration.
  Gemini analyzes repository and libraries, Claude gathers requirements and drafts plan,
  Codex reviews and refines the plan, then Claude creates the final task list.
metadata:
  short-description: Project kickoff with multi-agent collaboration
---

# Start Project — Multi-Agent Project Kickoff

**Use this skill at the beginning of any significant implementation work.**

## Overview

This skill orchestrates a complete project kickoff using three AI agents.

### Context Management (CRITICAL)

**All Codex/Gemini work runs through subagents** to preserve main orchestrator context.

```
┌─────────────────────────────────────────────────────────────────┐
│  Main Claude Code (Orchestrator)                                │
│  → Minimal context usage                                        │
│  → User interaction only                                        │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Subagent: Gemini Research                                 │ │
│  │  → Calls Gemini CLI                                        │ │
│  │  → Returns concise summary                                 │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Subagent: Codex Review                                    │ │
│  │  → Calls Codex CLI                                         │ │
│  │  → Returns key recommendations                             │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow Phases

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Subagent → Gemini (Research)                          │
│  → Repository analysis & library investigation                  │
│  → Output: .claude/docs/research/{feature}.md                   │
├─────────────────────────────────────────────────────────────────┤
│  Phase 2: Main Claude (Planning)                                │
│  → Read subagent's summary                                      │
│  → Gather requirements from user                                │
│  → Draft implementation plan                                    │
├─────────────────────────────────────────────────────────────────┤
│  Phase 3: Subagent → Codex (Review)                             │
│  → Read research + draft plan                                   │
│  → Deep review and refinement                                   │
│  → Returns key recommendations                                  │
├─────────────────────────────────────────────────────────────────┤
│  Phase 4: Main Claude (Execution)                               │
│  → Synthesize subagent summaries                                │
│  → Create comprehensive task list                               │
│  → Get user confirmation and start                              │
└─────────────────────────────────────────────────────────────────┘
```

## Workflow

### Phase 1: Subagent → Gemini Research (Background)

**Use Task tool with subagent_type=general-purpose** to run Gemini research.
This preserves main context while getting comprehensive research.

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true
- prompt: |
    Research for implementing: {feature}

    1. Call Gemini CLI:
       gemini -p "Analyze this repository for implementing: {feature}

       Provide:
       1. Repository Structure (architecture, key modules, data flow)
       2. Relevant Existing Code (related files, patterns to follow)
       3. Library Investigation (current deps, recommended libs)
       4. Technical Considerations (integration points, security)
       5. Recommendations (approach, files to create/modify)
       " --include-directories . 2>/dev/null

    2. Save full output to: .claude/docs/research/{feature}.md

    3. Return CONCISE summary (5-7 bullet points) of key findings
       to preserve main orchestrator context.
```

**Key principle:** Subagent consumes its own context. Main orchestrator only receives the summary.

### Phase 2: Requirements Gathering (Claude Code)

While waiting for Gemini (or after), Claude gathers requirements from user.

**Read Gemini's research first** (if available):
```
Read .claude/docs/research/{feature-name}.md
```

**Ask user these questions (in Japanese):**

1. **目的**: 何を達成したいですか？（1-2文で）
2. **スコープ**: 含めるもの・除外するものは？
3. **技術的要件**: 特定のライブラリ、パターン、制約は？
4. **成功基準**: 完了の判断基準は何ですか？
5. **優先度**: 最も重要な部分はどこですか？

**Don't proceed until you have clear answers.** Ask follow-up questions based on Gemini's research.

**Draft Implementation Plan:**

Based on Gemini research + user requirements, create draft plan:

```markdown
# Implementation Plan Draft: {feature}

## Overview
{1-2 sentences}

## Approach
{Based on Gemini's recommendations + user requirements}

## Components
1. {Component 1}: {description}
2. {Component 2}: {description}
...

## File Changes
- Create: {list}
- Modify: {list}

## Dependencies
- {library}: {purpose}

## Open Questions
- {Any uncertainties for Codex to address}
```

### Phase 3: Subagent → Codex Deep Review (Background)

**Use Task tool with subagent_type=general-purpose** to get Codex review.
Pass the draft plan and Gemini research summary.

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true
- prompt: |
    Review implementation plan for: {feature}

    ## Context
    - Gemini research: .claude/docs/research/{feature}.md
    - Draft plan: {Claude's draft plan from Phase 2}
    - User requirements: {summary}

    1. Read the Gemini research file

    2. Call Codex CLI:
       codex exec --model gpt-5.2-codex --sandbox read-only --full-auto "
       Review this implementation plan:

       {Include draft plan and key research points}

       Analyze:
       1. Plan Assessment (sound approach? better alternatives?)
       2. Risk Analysis (technical risks, complexity hotspots)
       3. Implementation Order (optimal sequence, parallelizable work)
       4. Refinements (improvements, additional/removable tasks)
       5. Complexity Estimates (Low/Medium/High per component)
       " 2>/dev/null

    3. Return CONCISE summary:
       - Top 3-5 recommendations
       - Key risks identified
       - Suggested task order
       - Any blocking concerns

       Keep response brief for main context preservation.
```

**Key principle:** Full Codex analysis stays in subagent. Main orchestrator gets actionable summary.

### Phase 4: Task List Creation (Main Claude)

Synthesize **subagent summaries** and create the final task list.

**Inputs to synthesize (all concise summaries):**
1. Gemini subagent summary (5-7 bullet points from Phase 1)
2. User requirements (from Phase 2 conversation)
3. Codex subagent summary (key recommendations from Phase 3)

**Note:** Full details are in `.claude/docs/research/{feature}.md` if needed,
but summaries should be sufficient for task creation.

**Create tasks using TodoWrite:**

```python
# Task structure
{
    "content": "Implement {specific feature}",     # Imperative
    "activeForm": "Implementing {specific feature}", # Present continuous
    "status": "pending"
}
```

**Task Breakdown Guidelines:**

| Category | Examples |
|----------|----------|
| Setup | Install dependencies, create directories, config files |
| Core | Business logic, data models, main features |
| Integration | Connect components, wire dependencies, APIs |
| Testing | Unit tests, integration tests, manual verification |

**Ordering:**
1. Independent tasks first
2. Then dependent tasks in order
3. Testing interleaved or at end (based on TDD preference)

### Phase 5: Confirmation and Kickoff

Present final plan to user (in Japanese):

```markdown
## プロジェクト計画: {feature}

### 調査結果 (Gemini)
{Key findings from research - 3-5 bullet points}

### 設計方針 (Codex レビュー済み)
{Approach with Codex's refinements}

### タスクリスト ({N}個)

#### 準備
- [ ] {Task 1}
- [ ] {Task 2}

#### コア実装
- [ ] {Task 3}
- [ ] {Task 4}
...

#### テスト
- [ ] {Task N-1}
- [ ] {Task N}

### リスクと注意点
{From Codex analysis}

### 参考資料
- 調査レポート: `.claude/docs/research/{feature}.md`

---
この計画で進めてよろしいですか？
```

**Wait for user confirmation before starting implementation.**

## Tips

### Context Management
- **All Codex/Gemini work through subagents** — never call directly from main
- **Subagents return concise summaries** — full output saved to files
- **Read files only if summary insufficient** — avoid loading large content into main context

### Task Tracking
- **Ctrl+T**: Toggle task list visibility
- **`/todos`**: Show all current tasks
- Tasks persist across context compactions
- Update task status immediately upon completion
- Only have ONE task `in_progress` at a time
- Re-consult Codex (via subagent) if unexpected complexity arises

## Output Files

| File | Purpose | Created By |
|------|---------|------------|
| `.claude/docs/research/{feature}.md` | Repository & library analysis | Gemini |
| Task list (internal) | Progress tracking | Claude (TodoWrite) |

## Example Usage

**User:** `/startproject ユーザー認証機能を追加したい`

**Claude will:**
1. Launch Gemini to analyze repo and auth libraries (background)
2. Ask user about OAuth vs session, password requirements, etc.
3. Draft plan based on Gemini research + user answers
4. Submit to Codex for deep review (background)
5. Create 10-15 specific tasks from all inputs
6. Present plan with research reference and wait for confirmation
