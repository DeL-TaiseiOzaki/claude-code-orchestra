---
name: gemini-system
description: |
  Gemini CLI leverages 1M context for three roles: codebase analysis,
  external research (Google Search grounding), and multimodal file reading.
  MUST use when PDF, video, audio, or image files need content extraction.
  Also use for large-scale codebase understanding and external research/survey.
  Auto-triggers: file extensions .pdf, .mp4, .mov, .mp3, .wav, .m4a.
  Planning/design → use Codex instead.
metadata:
  short-description: Gemini CLI — 1M context analysis, research & multimodal
---

# Gemini System — Analysis, Research & Multimodal

**Gemini CLI leverages 1M context for large-scale analysis, research, and multimodal file reading.**

> **Detailed rules**: `.claude/rules/gemini-delegation.md`

## Three Roles of Gemini

### 1. Codebase and Repository Understanding

Use Gemini's 1M context to analyze the entire project (when Claude's 200K is insufficient).

```bash
# Analyze project structure
gemini -p "Analyze this codebase: directory structure, key modules, patterns, dependencies, and architecture" 2>/dev/null

# Detailed analysis of specific files
gemini -p "Analyze this code: purpose, patterns, dependencies" < /path/to/file 2>/dev/null
```

### 2. External Research and Surveys

Use Gemini's Google Search grounding to research the latest information.

```bash
# Library research
gemini -p "Research: {library}. Latest version, features, constraints, best practices, pitfalls" 2>/dev/null

# Best practices research
gemini -p "Research best practices for {topic}. Latest recommendations, patterns, anti-patterns" 2>/dev/null

# Technology comparison
gemini -p "Compare {A} vs {B} for {use case}. Pros, cons, performance, community" 2>/dev/null
```

### 3. Multimodal File Reading

Extract content from PDF, video, audio, and image files.

```bash
# PDF
gemini -p "Extract: {what to extract}" < /path/to/file.pdf 2>/dev/null

# Video
gemini -p "Summarize: key concepts, timestamps" < /path/to/video.mp4 2>/dev/null

# Audio
gemini -p "Transcribe and summarize: decisions, action items" < /path/to/audio.mp3 2>/dev/null

# Image (diagrams, charts)
gemini -p "Analyze: components, relationships, data flow" < /path/to/diagram.png 2>/dev/null
```

| Target | Extensions |
|--------|------------|
| PDF | `.pdf` |
| Video | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| Audio | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg` |
| Images (advanced analysis) | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg` |

> Simple screenshot inspection can be done directly with Claude's Read tool.

## Auto-Trigger

When multimodal files appear in a task, automatically pass them to Gemini without waiting for user instructions.

## When NOT to Use Gemini

| Task | Correct Owner |
|------|---------------|
| Design and planning | **Codex** |
| Debugging | **Codex** |
| Code implementation | **Claude / Subagents** |

## How to Use

### Subagent Pattern (for large outputs)

```
Task tool parameters:
- subagent_type: "gemini-explore"
- prompt: |
    {task description}

    gemini -p "{prompt}" 2>/dev/null

    Save results to .claude/docs/research/{topic}.md
    Return CONCISE summary (5-7 bullet points).
```

### Direct Call (for short extractions)

```bash
gemini -p "{what to extract/research}" 2>/dev/null
```

## Language Protocol

1. Ask Gemini in **English**
2. Receive response in **English**
3. Report to user in **the user's language**
