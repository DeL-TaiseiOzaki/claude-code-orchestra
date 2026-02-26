# Codex Delegation Rule

**Codex CLI handles planning, design, and complex code implementation.**

## Two Roles of Codex

### 1. Planning & Design

- Architecture design, module structure
- Implementation planning (step decomposition, dependency ordering)
- Trade-off evaluation, technology selection
- Code review (quality and correctness analysis)

### 2. Complex Code Implementation

- Complex algorithms, optimization
- Debugging with unknown root causes
- Advanced refactoring
- Multi-step implementation tasks

## When to Consult Codex

| Situation | Examples |
|------|------|
| **Planning needed** | "How to design?" "Create a plan" "Architecture" |
| **Complex implementation** | Complex logic, optimization, performance improvements |
| **Debugging** | "Why doesn't this work?" "What caused the error?" (after initial failure) |
| **Comparison and trade-off analysis** | "Which is better, A or B?" "What are the trade-offs?" |
| **Code review** | "Review this" "Quality check" |

### Trigger Phrases (User Input)

| Phrase | English Equivalent |
|----------|---------|
| "How should I design/implement?" | "How should I design/implement?" |
| "Create a plan" "Architecture" | "Create a plan" "Architecture" |
| "Why doesn't this work?" "What caused it?" "There's an error" | "Why doesn't this work?" "Error" |
| "Which is better?" "Compare" "Trade-offs?" | "Which is better?" "Compare" |
| "Think about this" "Analyze" "Think deeper" | "Think" "Analyze" "Think deeper" |

## When NOT to Consult

- Simple file edits (typo fixes, small changes)
- Tasks that simply follow explicit user instructions
- Standard operations (git commit, running tests)
- Tasks with a single clear solution
- File search and reading
- **Codebase analysis** -- Claude handles directly (1M context)
- **External information retrieval** -- Subagent (WebSearch/WebFetch) handles
- **Multimodal processing** -- Gemini handles

## Context Management

| Situation | Recommended Method |
|------|----------|
| Short question and answer (~50 lines) | Direct call OK |
| Detailed design or planning | Via subagent |
| Debug analysis | Via subagent |
| Complex code implementation | Via subagent (workspace-write) |

## How to Consult

### Subagent Pattern (Recommended)

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: true (for parallel work)
- prompt: |
    Consult Codex about: {topic}

    codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "
    {question for Codex}
    " 2>/dev/null

    Return CONCISE summary (key recommendation + rationale).
```

### Direct Call (Short questions, ~50 line responses)

```bash
codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "Brief question" 2>/dev/null
```

### Having Codex Implement Code

```bash
codex exec --model gpt-5.3-codex --sandbox workspace-write --full-auto "
Implement: {detailed implementation task}

Requirements:
- {requirement 1}
- {requirement 2}

Files to create/modify:
- {file paths}
" 2>/dev/null
```

### Sandbox Modes

| Mode | Sandbox | Use Case |
|------|---------|----------|
| Analysis | `read-only` | Design review, debugging, trade-off analysis |
| Implementation | `workspace-write` | Implementation, fixes, refactoring |

## Language Protocol

1. Ask Codex in **English**
2. Receive response in **English**
3. Execute based on advice
4. Report to user in **English**
