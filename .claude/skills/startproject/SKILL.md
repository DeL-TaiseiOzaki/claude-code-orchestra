---
name: startproject
description: |
  Start a new project/feature implementation session. Analyzes repository structure,
  gathers requirements from user, consults Codex for planning, and creates a
  comprehensive task list for tracking progress.
metadata:
  short-description: Project kickoff with repo analysis and task planning
---

# Start Project — Comprehensive Project Kickoff

**Use this skill at the beginning of any significant implementation work.**

## Overview

This skill orchestrates a complete project kickoff:

1. **Repository Analysis** — Understand codebase structure using subagents
2. **Requirements Gathering** — Interview user for clear scope definition
3. **Codex Consultation** — Get expert input on implementation strategy
4. **Task List Creation** — Build comprehensive task list with TodoWrite

## Workflow

### Phase 1: Repository Understanding (Parallel Execution)

Launch Explore subagent to analyze the codebase:

```
Use Task tool with subagent_type=Explore:
- Codebase structure and architecture
- Key modules and their responsibilities
- Existing patterns and conventions
- Related files for the feature area (if specified)
```

**Also check:**
- `.claude/docs/DESIGN.md` for existing design decisions
- `.claude/docs/libraries/` for library constraints
- Recent git history for context

### Phase 2: Requirements Gathering

Ask user these questions (in Japanese):

1. **目的**: 何を達成したいですか？（1-2文で）
2. **スコープ**: 含めるもの・除外するものは？
3. **制約**: 技術的制約、依存関係、期限は？
4. **成功基準**: 完了の判断基準は何ですか？
5. **優先度**: 最も重要な部分はどこですか？

**Important:** Don't proceed until you have clear answers. Ask follow-up questions if needed.

### Phase 3: Codex Consultation

Consult Codex for implementation strategy (run in background):

```bash
codex exec --model gpt-5.2-codex --sandbox read-only --full-auto "
Analyze and plan implementation for: {feature description}

Context:
- Repository structure: {summary from Phase 1}
- User requirements: {summary from Phase 2}

Provide:
1. Recommended implementation approach
2. Key components/modules to create or modify
3. Suggested order of implementation
4. Potential risks and mitigations
5. Estimated complexity (low/medium/high) for each step
" 2>/dev/null
```

### Phase 4: Task List Creation

Based on all gathered information, create comprehensive task list using TodoWrite:

**Task Breakdown Guidelines:**

1. **Granularity**: Each task should be completable in 15-30 minutes
2. **Testability**: Each task should have clear completion criteria
3. **Dependencies**: Order tasks by dependency (independent tasks first)
4. **Categories**: Group tasks logically:
   - Setup/Preparation
   - Core Implementation
   - Integration
   - Testing
   - Documentation (if needed)

**Task Format:**

```
content: "Implement {specific feature}" (imperative form)
activeForm: "Implementing {specific feature}" (present continuous)
status: "pending"
```

### Phase 5: Confirmation and Kickoff

Present to user (in Japanese):

```markdown
## プロジェクト計画

### 概要
{1-2 sentences summarizing the project}

### スコープ
- 新規作成: {files to create}
- 変更: {files to modify}
- 依存関係: {dependencies}

### タスクリスト
{Number} タスクを作成しました。

#### 準備
- [ ] Task 1
- [ ] Task 2

#### コア実装
- [ ] Task 3
...

### リスクと注意点
- {Risks from Codex analysis}

### 次のステップ
最初のタスク「{first task}」から開始します。よろしいですか？
```

**Wait for user confirmation before starting implementation.**

## Tips

- Use `Ctrl+T` to toggle task list visibility during implementation
- Tasks persist across context compactions
- Update task status immediately upon completion
- Only have ONE task `in_progress` at a time
- Ask Codex again if you encounter unexpected complexity

## Example Usage

User: `/startproject ユーザー認証機能を追加したい`

Claude will:
1. Explore the codebase for auth-related patterns
2. Ask clarifying questions about OAuth, sessions, etc.
3. Consult Codex for auth implementation strategy
4. Create 10-15 specific tasks covering the full implementation
5. Present plan and wait for confirmation
