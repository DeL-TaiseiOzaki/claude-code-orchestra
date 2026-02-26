# Troubleshooting

## Codex CLI Not Found

```bash
# Check installation
which codex
codex --version

# Install
npm install -g @openai/codex
```

## Authentication Error

```bash
# Re-authenticate
codex login

# Check status
codex login status
```

## Timeout

| reasoning_effort | Recommended timeout |
|-----------------|---------------------|
| low             | 60s                 |
| medium          | 180s                |
| high            | 600s                |
| xhigh           | 900s                |

Configure in config.toml:
```toml
[mcp_servers.codex]
tool_timeout_sec = 600
```

## Git Repository Error

```bash
# Run outside of a Git repository
codex exec --skip-git-repo-check ...
```

## Excessive Reasoning Output

```bash
# Suppress stderr
codex exec ... 2>/dev/null

# Or configure in config.toml
hide_agent_reasoning = true
```

## Cannot Continue Session

```bash
# List recent sessions
codex sessions list

# Show details for a specific session
codex sessions show {SESSION_ID}
```

## Sandbox Permission Error

| Error | Cause | Solution |
|-------|-------|----------|
| Permission denied | Write attempted in read-only mode | Change to workspace-write |
| Network blocked | Sandbox restriction | Use danger-full-access (with caution) |

## Out of Memory

When analyzing large codebases:
1. Narrow down the target files
2. Analyze in stages
3. Adjust with `--config context_limit=...`
