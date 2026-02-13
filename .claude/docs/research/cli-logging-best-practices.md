# CLI Tool Logging Best Practices

Research on logging Codex/Gemini CLI input/output in multi-agent system.

**Date**: 2026-01-26

## Problem Statement

Users cannot easily see:
- What prompts were sent to Codex/Gemini
- What responses were received
- Timeline of AI agent interactions

Both tools are called via Bash tool, so output is visible in Claude Code UI, but:
- Hard to track across multiple conversations
- No persistent history
- Difficult to debug multi-agent workflows

## Recommended Approach: PostToolUse Hook + JSONL Logging

### Why This Approach?

1. **Leverage Existing Infrastructure**: PostToolUse hook already exists for Bash tool
2. **Non-Intrusive**: No need to modify CLI tools or create wrapper scripts
3. **Simple**: File-based append-only logging
4. **Queryable**: JSONL format is both human-readable and machine-parseable
5. **Low Overhead**: Async append operation, minimal performance impact

### Architecture

```
┌──────────────────────────────────────────────────┐
│  Claude Code calls Bash tool                     │
│  → codex exec ... "prompt" 2>/dev/null           │
│  → gemini -p "prompt" 2>/dev/null                │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│  PostToolUse Hook (Bash matcher)                 │
│  → Receives: tool_input, tool_output             │
│  → Detects: codex/gemini commands                │
│  → Extracts: prompt, response                    │
│  → Logs: to .claude/logs/cli-tools.jsonl        │
└──────────────────────────────────────────────────┘
```

## Implementation Details

### 1. Log Format: JSON Lines (JSONL)

Each line is a complete JSON object:

```json
{"timestamp": "2026-01-26T10:30:45+00:00", "tool": "codex", "model": "gpt-5.3-codex", "prompt": "How should I design...", "response": "I recommend...", "success": true, "exit_code": 0}
{"timestamp": "2026-01-26T10:32:12+00:00", "tool": "gemini", "model": "gemini-3-pro-preview", "prompt": "Research best practices...", "response": "Based on...", "success": true, "exit_code": 0}
```

**Fields**:
- `timestamp`: ISO 8601 format with timezone
- `tool`: "codex" or "gemini"
- `model`: Model name used
- `prompt`: Input prompt (truncated to 2000 chars if longer)
- `response`: Output response (truncated to 2000 chars if longer)
- `success`: Whether the call succeeded (exit_code == 0 and output exists)
- `exit_code`: Exit code from CLI command

**Benefits**:
- One log entry per line = easy to append
- Valid JSON = easy to parse with `jq`, Python, etc.
- Human-readable with proper formatting
- No need for log rotation (JSONL scales well)

### 2. Hook Implementation: `log-cli-tools.py`

```python
#!/usr/bin/env python3
"""
PostToolUse hook: Log Codex/Gemini CLI input/output.
"""

import json
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path(__file__).parent.parent / "logs" / "cli-tools.jsonl"

def extract_codex_prompt(command: str) -> dict | None:
    """Extract prompt from codex command."""
    # Match: codex exec --model MODEL --sandbox SANDBOX --full-auto "PROMPT"
    match = re.search(
        r'codex\s+exec\s+.*?--model\s+([^\s]+).*?--sandbox\s+([^\s]+).*?--full-auto\s+["\'](.+?)["\']',
        command,
        re.DOTALL
    )
    if match:
        return {
            "tool": "codex",
            "model": match.group(1),
            "sandbox": match.group(2),
            "prompt": match.group(3).strip()
        }
    return None

def extract_gemini_prompt(command: str) -> dict | None:
    """Extract prompt from gemini command."""
    # Match: gemini -p "PROMPT"
    match = re.search(r'gemini\s+.*?-p\s+["\'](.+?)["\']', command, re.DOTALL)
    if match:
        return {
            "tool": "gemini",
            "prompt": match.group(1).strip()
        }
    return None

def log_cli_call(log_data: dict):
    """Append log entry to JSONL file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_data, ensure_ascii=False) + "\n")

def main():
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")

        # Only process Bash tool
        if tool_name != "Bash":
            sys.exit(0)

        tool_input = data.get("tool_input", {})
        tool_output = data.get("tool_output", "")
        command = tool_input.get("command", "")

        # Try to extract Codex or Gemini prompt
        extracted = None
        if "codex" in command:
            extracted = extract_codex_prompt(command)
        elif "gemini" in command:
            extracted = extract_gemini_prompt(command)

        if extracted:
            # Build log entry
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **extracted,
                "response": tool_output.strip(),
                "success": "error" not in tool_output.lower()[:200]
            }
            log_cli_call(log_entry)

        sys.exit(0)

    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)

if __name__ == "__main__":
    main()
```

### 3. Configuration: `.claude/settings.json`

Add to `PostToolUse` hooks:

```json
{
  "matcher": "Bash",
  "hooks": [
    {
      "type": "command",
      "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/log-cli-tools.py\"",
      "timeout": 5
    }
  ]
}
```

**Note**: Multiple hooks can match the same tool, so this can coexist with `post-test-analysis.py`.

### 4. Log Storage Location

```
.claude/
├── logs/
│   └── cli-tools.jsonl      # Main log file
├── hooks/
│   └── log-cli-tools.py     # Hook implementation
└── settings.json
```

**Why `.claude/logs/`?**
- Consistent with `.claude/` convention
- Easy to add to `.gitignore` (logs are local-only)
- Separate from documentation/rules

### 5. Querying Logs

**View recent calls:**
```bash
tail -20 .claude/logs/cli-tools.jsonl | jq '.'
```

**Filter by tool:**
```bash
jq 'select(.tool == "codex")' .claude/logs/cli-tools.jsonl
```

**Count calls per tool:**
```bash
jq -r '.tool' .claude/logs/cli-tools.jsonl | sort | uniq -c
```

**Search prompts:**
```bash
jq 'select(.prompt | contains("design"))' .claude/logs/cli-tools.jsonl
```

**Failed calls only:**
```bash
jq 'select(.success == false)' .claude/logs/cli-tools.jsonl
```

## Alternative Approaches Considered

### ❌ Approach 1: Bash Wrapper Scripts

Create `codex-logged` and `gemini-logged` wrapper scripts.

**Pros**: Clean separation
**Cons**:
- Requires changing all call sites
- Easy to forget and call unwrapped version
- More complex to maintain

### ❌ Approach 2: PreToolUse Hook

Log before the tool executes.

**Pros**: Captures input even if tool fails
**Cons**:
- Can't capture output
- Can't measure duration
- Need both Pre and Post hooks

### ❌ Approach 3: Custom Logger Class

Create Python logger that agents import.

**Pros**: More structured, better error handling
**Cons**:
- Requires modifying all calling code
- Couples logging to implementation
- Not transparent to Claude Code

### ✅ Approach 4: PostToolUse Hook (RECOMMENDED)

Current recommendation combines best of all approaches.

## Performance Considerations

### File I/O Impact

- **Append-only writes**: ~1ms per log entry
- **No locks needed**: Single writer (hook process)
- **JSONL format**: No parsing entire file on append

### Log File Size

Estimated growth:
- Average entry: ~500 bytes (prompt + response)
- 100 calls/day: ~50 KB/day
- 30 days: ~1.5 MB/month

**Rotation strategy** (if needed):
```bash
# Manual rotation
mv .claude/logs/cli-tools.jsonl .claude/logs/cli-tools-$(date +%Y%m).jsonl
```

### Hook Timeout

Set to 5 seconds (same as other hooks):
- Allows for file I/O on slow systems
- Prevents hanging on filesystem issues
- Non-blocking (Claude continues even if hook fails)

## Security Considerations

### 1. Sensitive Data in Prompts

Prompts may contain:
- API keys (if user accidentally includes)
- User data
- Proprietary code

**Mitigation**:
```python
# .gitignore
.claude/logs/
```

**Alternative**: Redact sensitive patterns before logging:
```python
def redact_sensitive(text: str) -> str:
    # Redact potential API keys
    text = re.sub(r'[A-Za-z0-9]{32,}', '[REDACTED]', text)
    return text
```

### 2. Log File Permissions

Ensure logs are user-readable only:
```python
LOG_FILE.chmod(0o600)  # rw------- (user only)
```

## Future Enhancements

### 1. Structured Logging with Metadata

Add context:
```json
{
  "timestamp": "...",
  "tool": "codex",
  "prompt": "...",
  "response": "...",
  "context": {
    "conversation_id": "abc123",
    "user_prompt": "original user request",
    "agent_type": "general-purpose"
  }
}
```

### 2. Log Viewer UI

Simple Python script:
```bash
python .claude/tools/view-logs.py
# → Opens TUI for browsing logs
```

### 3. Metrics Dashboard

Track:
- Calls per day
- Average response time
- Success rate
- Most common prompts

### 4. Export to SQLite

For complex queries:
```bash
python .claude/tools/export-logs-to-db.py
# → Creates cli-tools.db
```

## Implementation Checklist

- [ ] Create `.claude/logs/` directory
- [ ] Add `.claude/logs/` to `.gitignore`
- [ ] Create `log-cli-tools.py` hook
- [ ] Update `.claude/settings.json` (PostToolUse → Bash)
- [ ] Test with sample codex/gemini call
- [ ] Verify JSONL format with `jq`
- [ ] Document for team (add to DESIGN.md or README)

## Testing Plan

### Unit Tests
```python
def test_extract_codex_prompt():
    cmd = 'codex exec --model gpt-5.3-codex --sandbox read-only --full-auto "test prompt"'
    result = extract_codex_prompt(cmd)
    assert result["tool"] == "codex"
    assert result["prompt"] == "test prompt"
```

### Integration Tests
1. Make actual codex/gemini call
2. Check log file exists
3. Verify entry matches expected format
4. Test with edge cases (multiline prompts, special chars)

## Conclusion

**Recommended implementation**: PostToolUse hook with JSONL logging

**Key benefits**:
- ✅ Zero code changes to call sites
- ✅ Transparent to agents
- ✅ Simple file-based storage
- ✅ Easy to query with jq
- ✅ Low performance overhead
- ✅ Leverages existing hook infrastructure

**Next steps**:
1. Implement hook (30 minutes)
2. Test with real calls (15 minutes)
3. Add to documentation (15 minutes)

Total implementation time: ~1 hour
