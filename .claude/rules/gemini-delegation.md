# Gemini Delegation Rule

**Gemini CLI is specialized for multimodal file processing (PDF, video, audio, image).**

> Opus/Sonnet now support 1M context. Research and codebase analysis are handled by Opus subagents (general-purpose).
> Gemini is used exclusively for multimodal content extraction that Claude cannot process directly.

## Role: Multimodal File Processing

- Extract content from PDF, video, audio, and image files
- Detailed analysis of charts and diagrams
- Video summarization and timestamp extraction
- Audio transcription and summarization

## When to Use Gemini

| Situation | Examples |
|------|------|
| **PDF content extraction** | "Extract API specs from this PDF" |
| **Video analysis** | "Summarize this tutorial video" |
| **Audio transcription** | "Transcribe this meeting recording" |
| **Diagram/chart analysis** | "Analyze this architecture diagram" |

## When NOT to Use Gemini

- **Research and investigation** → Opus subagent (general-purpose) with WebSearch/WebFetch
- **Codebase analysis** → Opus subagent (general-purpose) with Read/Grep/Glob
- **Planning, design, architecture** → Codex CLI
- **Debugging, error analysis** → Codex CLI
- **Code implementation** → Claude / subagent
- **Simple file reading** → Claude's Read tool
- **Simple screenshot inspection** → Claude's Read tool

## Supported File Extensions (Multimodal)

| Category | Extensions |
|----------|--------|
| PDF | `.pdf` |
| Video | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| Audio | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg` |
| Image (detailed analysis) | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg` |

## How to Use

### Multimodal File Reading

```bash
# PDF -- Extract structure and content
gemini -p "Extract: {what information to extract} @/path/to/file.pdf" 2>/dev/null

# Video -- Summarize, key points, timestamps
gemini -p "Summarize: key concepts, decisions, timestamps @/path/to/video.mp4" 2>/dev/null

# Audio -- Transcription and summarization
gemini -p "Transcribe and summarize: decisions, action items @/path/to/audio.mp3" 2>/dev/null

# Image -- Detailed analysis of charts and diagrams
gemini -p "Analyze this diagram: components, relationships, data flow @/path/to/diagram.png" 2>/dev/null
```

## Context Management

| Situation | Recommended Method |
|------|----------|
| Short extraction or answer (~30 lines) | Direct call OK |
| Detailed analysis report | Via gemini-explore subagent |

### Subagent Pattern (For large output)

```
Task tool parameters:
- subagent_type: "gemini-explore"
- run_in_background: true (for parallel work)
- prompt: |
    {task description}

    gemini -p "{prompt} @/path/to/file" 2>/dev/null

    Return CONCISE summary (key findings + extracted content).
```

### Direct Call (Short extractions)

```bash
gemini -p "Extract: {specific content} @/path/to/file" 2>/dev/null
```

## Auto-Trigger (Activates automatically without user instruction)

- PDF/video/audio files are referenced within a task
- User provides a file path with a multimodal-supported extension

## Language Protocol

1. Ask Gemini in **English**
2. Receive response in **English**
3. Execute based on findings
4. Report to user in **English**
