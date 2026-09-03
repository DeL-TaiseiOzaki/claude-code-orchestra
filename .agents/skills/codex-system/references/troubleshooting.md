# Troubleshooting

Entries below assume Codex is invoked through the wrapper (`.agents/skills/_shared/codex_consult.py`) described in `../SKILL.md`, except where noted.

## Codex CLI Not Found

The wrapper checks `PATH` before running and exits `2` with an actionable `error` field when `codex` is missing — no separate detection step is needed. To fix it directly:

```bash
# Check installation
which codex
codex --version

# Install
npm install -g @openai/codex@latest
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

Pass `--timeout <sec>` to the wrapper to match the table above (default: 600s). For the underlying MCP server integration, configure in config.toml:
```toml
[mcp_servers.codex]
tool_timeout_sec = 600
```

## Git Repository Error

Codex refuses to run outside a Git repository. Prefer `git init` in the target directory so the work stays reviewable; when that is genuinely not appropriate, pass the flag through the wrapper:

```bash
python3 .agents/skills/_shared/codex_consult.py \
  --prompt-file <path> --sandbox read-only --skip-git-repo-check
```

## Excessive Reasoning Output

The wrapper never prints raw stderr to the console — it captures stderr to a `{label}.err.log` file next to the response (its path is reported as `stderr_file` in the JSON result) instead of discarding or inlining it, so a verbose or crashed run is never mistaken for a quiet success. To reduce the volume Codex itself produces, configure in config.toml:
```toml
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
| Permission denied | Write attempted while the wrapper defaulted to `--sandbox read-only` | Pass `--sandbox workspace-write` or `--sandbox danger-full-access` explicitly — the wrapper always defaults to `read-only` and never falls back to the project's `.codex/config.toml` default |
| Network blocked | Sandbox restriction | Pass `--sandbox danger-full-access` explicitly (with caution) |

## Out of Memory

When analyzing large codebases:
1. Narrow down the target files
2. Analyze in stages
3. Raise the per-call budget with `--config context_limit=<value>`, or scope the prompt and file list down
