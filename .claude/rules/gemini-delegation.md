# Gemini Delegation Rule

**Gemini CLI leverages its 1M context for large-scale analysis, research, and multimodal reading.**

## Three Roles of Gemini

### 1. Codebase & Repository Understanding (Codebase Analysis)

- Analyze overall project structure
- Identify key modules and their responsibilities
- Understand existing patterns and conventions
- Analyze dependencies

> Claude Code's context is **200K tokens** (effectively 140-150K).
> Delegate full codebase analysis to Gemini's **1M context**.

### 2. External Research & Survey (Research & Survey)

- Investigate latest documentation and API specifications
- Compare libraries and identify best practices
- Conduct technical surveys and trend research
- Investigate known issues and constraints

> Gemini CLI has built-in Google Search grounding, making it ideal for retrieving external information.

### 3. Multimodal File Reading (Multimodal Reading)

- Extract content from PDF, video, audio, and image files
- Detailed analysis of charts and diagrams
- Video summarization and timestamp extraction
- Audio transcription and summarization

## When to Use Gemini

| Situation | Examples |
|------|------|
| **Codebase analysis** | "Understand the whole project" "Analyze the structure" |
| **External research** | "Look this up" "Research this" "Latest documentation" |
| **Library investigation** | "Compare libraries" "What are the best practices?" |
| **Multimodal** | When PDF/video/audio/image files are encountered (auto-delegation) |

### Trigger Phrases (User Input)

| Phrase | English Equivalent |
|----------|---------|
| "Understand the codebase" "Look at overall structure" | "Understand the codebase" "Analyze structure" |
| "Look this up" "Research this" "Survey this" | "Research" "Investigate" "Survey" |
| "Compare libraries" "Best practices" | "Compare libraries" "Best practices" |
| "Read this PDF/video/image" | "Read this PDF/video/image" |

## When NOT to Use Gemini

- Simple file reading (Claude's Read tool is sufficient)
- Simple screenshot verification (Claude's Read tool can handle directly)
- Planning, design, architecture -- **Codex** handles these
- Debugging, error analysis -- **Codex** handles these
- Code implementation -- **Claude / subagent** handles these

## Supported File Extensions (Multimodal)

| Category | Extensions |
|----------|--------|
| PDF | `.pdf` |
| Video | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| Audio | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg` |
| Image (detailed analysis) | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg` |

## How to Use

### Codebase Analysis

```bash
# Analyze project structure (Gemini reads the workspace)
gemini -p "Analyze this codebase: directory structure, key modules, patterns, dependencies, and architecture" 2>/dev/null

# Detailed analysis of a specific file
gemini -p "Analyze this code: purpose, patterns, dependencies" < /path/to/file 2>/dev/null
```

### External Research

```bash
# Library investigation
gemini -p "Research: {library name}. Find latest version, key features, constraints, best practices, and common pitfalls" 2>/dev/null

# Best practices survey
gemini -p "Research best practices for {topic}. Include latest recommendations, common patterns, and anti-patterns" 2>/dev/null

# Technology comparison
gemini -p "Compare {A} vs {B} for {use case}. Include pros, cons, performance, and community support" 2>/dev/null
```

### Multimodal File Reading

```bash
# PDF -- Extract structure and content
gemini -p "Extract: {what information to extract}" < /path/to/file.pdf 2>/dev/null

# Video -- Summarize, key points, timestamps
gemini -p "Summarize: key concepts, decisions, timestamps" < /path/to/video.mp4 2>/dev/null

# Audio -- Transcription and summarization
gemini -p "Transcribe and summarize: decisions, action items" < /path/to/audio.mp3 2>/dev/null

# Image -- Detailed analysis of charts and diagrams
gemini -p "Analyze this diagram: components, relationships, data flow" < /path/to/diagram.png 2>/dev/null
```

## Context Management

| Situation | Recommended Method |
|------|----------|
| Short extraction or answer (~30 lines) | Direct call OK |
| Detailed analysis report | Via subagent |
| Research findings | Via subagent -- save to file |

### Subagent Pattern (For large output)

```
Task tool parameters:
- subagent_type: "gemini-explore"
- run_in_background: true (for parallel work)
- prompt: |
    {task description}

    gemini -p "{prompt}" 2>/dev/null

    Save results to .claude/docs/research/{topic}.md
    Return CONCISE summary (key findings + recommendations).
```

### Direct Call (Short questions and answers)

```bash
gemini -p "Brief question about {topic}" 2>/dev/null
```

## Auto-Trigger (Activates automatically without user instruction)

- PDF/video/audio files are referenced within a task
- User provides a file path with a multimodal-supported extension

## Language Protocol

1. Ask Gemini in **English**
2. Receive response in **English**
3. Execute based on findings
4. Report to user in **English**
