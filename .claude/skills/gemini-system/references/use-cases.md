# Gemini CLI Use Cases — Multimodal Processing

> For research, codebase analysis, and documentation lookup, use a general-purpose subagent (Opus) instead.
> Gemini CLI is specialized for multimodal file processing only.

## Video Analysis

```bash
# Tutorial video analysis
gemini -p "Analyze this tutorial video:
- Summarize the main concepts taught
- List step-by-step instructions
- Note any important warnings or tips
- Identify timestamps for key sections
@tutorial.mp4" 2>/dev/null

# Code review video
gemini -p "Extract code patterns and best practices demonstrated in this video @code-review.mp4" 2>/dev/null
```

## Audio Analysis

```bash
# Meeting recording
gemini -p "Transcribe and summarize this technical discussion:
- Key decisions made
- Action items
- Open questions
- Technical terms mentioned
@meeting.mp3" 2>/dev/null

# Podcast/talk analysis
gemini -p "Extract technical insights from this talk about {topic} @conference-talk.mp3" 2>/dev/null
```

## PDF Analysis

```bash
# API documentation
gemini -p "Extract from this API documentation:
- All available endpoints
- Request/response schemas
- Authentication requirements
- Rate limiting rules
@api-spec.pdf" 2>/dev/null

# Technical specification
gemini -p "Summarize this technical specification:
- Core requirements
- Constraints
- Interface definitions
- Edge cases to handle
@spec.pdf" 2>/dev/null

# Research paper
gemini -p "Analyze this paper and explain:
- Problem being solved
- Proposed approach
- Key algorithms
- How to apply this in practice
@paper.pdf" 2>/dev/null
```

## Image / Diagram Analysis

```bash
# Architecture diagram
gemini -p "Analyze this architecture diagram:
- Components and their responsibilities
- Data flow between components
- External dependencies
@architecture.png" 2>/dev/null

# Chart analysis
gemini -p "Extract data and trends from this chart:
- Key metrics
- Trends over time
- Notable anomalies
@dashboard.png" 2>/dev/null
```

## When NOT to Use Gemini

| Task | Reason | Use Instead |
|------|--------|-------------|
| Research / investigation | Opus has 1M context + WebSearch | general-purpose subagent |
| Codebase analysis | Opus has 1M context + Read/Grep | general-purpose subagent |
| Design decisions | Requires deep reasoning | Codex |
| Code implementation | Codex has better code abilities | Codex |
| Debugging | Requires logical analysis | Codex |
| Simple file edits | Overkill | Claude Code directly |
| Running tests | Execution task | Claude Code directly |

## Output Handling

### Piping to Files

```bash
gemini -p "Extract all API schemas @api-spec.pdf" > docs/api-schemas.md 2>/dev/null
```

## Rate Limits

Free tier (personal Google account):
- 60 requests/minute
- 1,000 requests/day

Plan accordingly for large extraction tasks.
