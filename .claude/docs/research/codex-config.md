# Codex CLI Configuration Reference

Research date: 2026-03-07

## File Locations

- **User-level**: `~/.codex/config.toml`
- **Project-level**: `.codex/config.toml` (loaded only for trusted projects)
- **JSON Schema**: `codex-rs/core/config.schema.json` (in the openai/codex repo)
- **Precedence**: CLI flags > Project config (closest wins) > User config > Defaults

## All Known Top-Level Keys

### Model Settings

| Key | Type | Valid Values | Default | Notes |
|-----|------|-------------|---------|-------|
| `model` | string | Any model ID | Recommended model | e.g. `"gpt-5.3-codex"`, `"gpt-5.2-codex"`, `"gpt-5-pro"` |
| `model_provider` | string | Provider name from `[model_providers]` | `"openai"` | |
| `model_context_window` | integer | Token count | Model default | Override context window size |
| `model_compaction_threshold` | integer | Token count | Model default | Triggers automatic history compaction |
| `model_catalog_json` | string (path) | File path | None | Path to JSON model catalog |
| `model_instructions_file` | string (path) | File path | None | Replacement for built-in instructions (instead of `AGENTS.md`) |
| `model_verbosity` | string | `"low"`, `"medium"`, `"high"` | `"medium"` | Responses API only; Chat Completions ignores this |
| `model_supports_reasoning_summaries` | bool | `true`, `false` | Auto-detected | Force reasoning summary support |

### Reasoning Settings

| Key | Type | Valid Values | Default | Notes |
|-----|------|-------------|---------|-------|
| `model_reasoning_effort` | string | `"minimal"`, `"low"`, `"medium"`, `"high"`, `"xhigh"` | `"medium"` | `"xhigh"` only on gpt-5.1-codex-max, gpt-5.2-codex, gpt-5.3-codex |
| `model_reasoning_summary` | string | `"auto"`, `"concise"`, `"detailed"`, `"none"` | `"auto"` | Controls reasoning summary output |
| `model_reasoning_summary_format` | string | `"experimental"` | None | UI formatting of reasoning summaries |
| `plan_mode_reasoning_effort` | string | Same as `model_reasoning_effort` + `"none"` | `"medium"` | Plan-mode-specific override; `"none"` disables reasoning |

### Approval & Sandbox

| Key | Type | Valid Values | Default | Notes |
|-----|------|-------------|---------|-------|
| `approval_policy` | string or table | `"suggest"`, `"on-request"`, `"never"` | `"suggest"` | Also supports granular reject: `{ reject = { ... } }` |
| `sandbox_mode` | string | `"read-only"`, `"workspace-write"`, `"danger-full-access"` | `"read-only"` | |
| `allow_login_shell` | bool | `true`, `false` | `false` | |

**Note on `approval_policy`:**
- `"suggest"` — Suggests actions, requires confirmation (default interactive mode)
- `"on-request"` — Requires approval on each request
- `"never"` — Full automation, no approval prompts
- `"on-failure"` — **DEPRECATED**, use `"on-request"` instead
- Granular reject policy: `approval_policy = { reject = { sandbox = true, execpolicy = true, mcp_elicitations = true } }`

### Web Search

| Key | Type | Valid Values | Default | Notes |
|-----|------|-------------|---------|-------|
| `web_search` | string | `"disabled"`, `"cached"`, `"live"` | `"cached"` | |

- `"disabled"` — No web search
- `"cached"` — Serves results from web search cache (default)
- `"live"` — Fetches most recent data from the web

### Other Top-Level Keys

| Key | Type | Valid Values | Default | Notes |
|-----|------|-------------|---------|-------|
| `profile` | string | Profile name | None | Set default profile |
| `review_model` | string | Model ID | Current session model | Override model for `/review` |
| `oss_provider` | string | Provider name | None | Default provider for `--oss` flag |
| `project_root_markers` | array of strings | e.g. `[".git", ".hg", ".sl"]` | `[".git", ".hg", ".sl"]` | Set to `[]` for CWD as root |
| `tool_output_token_budget` | integer | Token count | Default | Budget for tool output in history |
| `state_dir` | string (path) | Directory path | Default | SQLite state DB location |
| `sqlite_home` | string (path) | Directory path | Default | Override with `CODEX_SQLITE_HOME` env var |
| `suppress_unstable_features_warning` | bool | `true`, `false` | `false` | Suppress feature flag warnings |
| `mcp_oauth_callback_port` | integer | Port number | Ephemeral | Fixed OAuth callback port |
| `mcp_oauth_credentials_store` | string | `"auto"`, `"file"`, `"keyring"` | `"auto"` | OAuth credentials storage method |
| `notify` | string/table | Varies | None | Notification hook when agent finishes a turn |

## Tables / Sections

### `[features]`

Toggle optional and experimental capabilities:

```toml
[features]
skills = true
unified_exec = true
shell_snapshot = true
multi_agent = true
steer = true
collaboration_modes = true
personality = true
```

Use `codex features enable <feature>` / `codex features disable <feature>` to manage.

### `[tui]`

TUI-specific options:

| Key | Type | Valid Values | Default |
|-----|------|-------------|---------|
| `tui.alternate_screen` | string | `"auto"`, etc. | `"auto"` |
| `tui.animations` | bool | `true`, `false` | `true` |
| `tui.notification_method` | string | `"auto"`, etc. | `"auto"` |
| `tui.notifications` | bool/table | `true`, `false`, or event types | Default |
| `tui.theme` | string | Theme name | Default | Use `/theme` to pick |

### `[sandbox_workspace_write]`

Options when `sandbox_mode = "workspace-write"`:

```toml
[sandbox_workspace_write]
exclude_tmpdir_env_var = false
exclude_slash_tmp = false
writable_roots = ["/path/to/additional/writable/dir"]
network_access = false
```

### `[profiles.<name>]`

Define named profiles:

```toml
[profiles.deep-review]
model = "gpt-5-pro"
model_reasoning_effort = "high"
approval_policy = "never"
model_reasoning_summary = "detailed"
model_catalog_json = "/path/to/catalog.json"
sandbox_mode = "workspace-write"
```

Activate with `codex --profile deep-review` or set `profile = "deep-review"` at top level.

### `[model_providers.<name>]`

Custom model provider configuration:

```toml
[model_providers.azure]
name = "Azure OpenAI"
base_url = "https://YOUR_RESOURCE.openai.azure.com/openai/v1"
env_key = "AZURE_OPENAI_API_KEY"
wire_api = "responses"               # "responses" or "chat"
requires_openai_auth = false
request_max_retries = 3
stream_max_retries = 3
stream_idle_timeout_ms = 30000
http_headers = { "Custom-Header" = "value" }
env_http_headers = { "X-Token" = "MY_TOKEN_ENV_VAR" }
query_params = { "api-version" = "2025-04-01-preview" }
# experimental_bearer_token = "..." # Discouraged; use env_key
```

### `[mcp_servers.<server-name>]`

MCP server configuration:

```toml
[mcp_servers.my-server]
command = "npx"
args = ["my-mcp-server@latest"]
enabled = true
startup_timeout_sec = 10
tool_timeout_sec = 60
bearer_token_env_var = "MY_TOKEN"
http_headers = {}
env_http_headers = {}
```

### `[agents]`

Multi-agent configuration:

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `agents.default_timeout` | integer (seconds) | 1800 | Per-worker timeout |
| `agents.max_depth` | integer | 1 | Max nesting depth |
| `agents.max_concurrent` | integer | Default | Max concurrent agent threads |

### `[[skills.config]]`

Per-skill overrides (array of tables):

```toml
[[skills.config]]
path = "/path/to/skill/SKILL.md"
enabled = true

[[skills.config]]
path = "/path/to/another-skill"
enabled = false
```

### `[notice]`

Stores "do not show again" flags for UI prompts. Generally auto-managed.

## Complete Example Configuration

```toml
# Model
model = "gpt-5.3-codex"
model_reasoning_effort = "high"
model_reasoning_summary = "auto"

# Policies
approval_policy = "on-request"
sandbox_mode = "workspace-write"

# Web search
web_search = "cached"

# Features
[features]
skills = true

# Skills
[[skills.config]]
path = ".codex/skills/my-skill"
enabled = true

# Sandbox options
[sandbox_workspace_write]
network_access = false

# TUI
[tui]
animations = true
```

## TOML Ordering Requirement

**IMPORTANT**: In TOML, root-level keys must appear BEFORE any tables (`[section]`).
Place all bare keys at the top of the file, then tables below.

## Sources

- https://developers.openai.com/codex/config-reference/
- https://developers.openai.com/codex/config-sample/
- https://developers.openai.com/codex/config-advanced/
- https://developers.openai.com/codex/config-basic/
- https://github.com/openai/codex/blob/main/docs/config.md
- https://github.com/openai/codex/issues/9104
- https://github.com/openai/codex/issues/2760
- https://developers.openai.com/codex/skills/
