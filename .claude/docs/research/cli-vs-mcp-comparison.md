# CLI vs MCP: Codex/Gemini Integration Comparison

## Executive Summary

**Current Approach (CLI via Bash)** is simpler and sufficient for the current use case.
**MCP** offers benefits for complex integrations but adds overhead not needed for basic AI tool delegation.

**Recommendation**: Keep CLI approach for now. Consider MCP when:
- Streaming becomes critical
- Need bi-directional communication
- Want standardized multi-tool integration
- Building public tool ecosystem

---

## Detailed Comparison

### 1. Invocation Overhead

| Aspect | CLI via Bash | MCP Server |
|--------|-------------|------------|
| **Process model** | New process per call (`codex exec`) | Long-running server process |
| **Startup time** | ~100-500ms (process spawn + CLI init) | ~10-50ms (JSON-RPC call to existing server) |
| **Serialization** | String construction + shell escaping | JSON serialization/deserialization |
| **Memory** | Isolated process (clean slate each time) | Persistent server (state management needed) |
| **Pros** | ✅ Isolated, no state leaks<br>✅ CLI handles all lifecycle | ✅ Faster repeated calls<br>✅ Can maintain session context |
| **Cons** | ❌ Higher per-call overhead<br>❌ No connection pooling | ❌ Server lifecycle management<br>❌ Potential memory leaks |

**For this use case**: CLI overhead acceptable since calls are infrequent (design/research decisions, not hot path).

---

### 2. Output Handling

| Aspect | CLI via Bash | MCP Server |
|--------|-------------|------------|
| **Format** | Plain text (stdout/stderr) | Structured JSON (JSON-RPC response) |
| **Streaming** | Line-buffered stdout | Server-Sent Events (SSE) via HTTP transport |
| **Parsing** | Regex extraction (see `log-cli-tools.py`) | Native JSON parsing |
| **Structure** | Unstructured (relies on CLI output format) | Typed schemas (tools, resources, prompts) |
| **Pros** | ✅ Human-readable logs<br>✅ No parsing overhead | ✅ Structured data<br>✅ True streaming support<br>✅ Rich metadata |
| **Cons** | ❌ Brittle regex patterns<br>❌ No true streaming (wait for completion) | ❌ JSON overhead<br>❌ Requires SSE setup for streaming |

**For this use case**: Current approach works fine. Subagents handle long outputs. True streaming not critical.

---

### 3. Error Handling

| Aspect | CLI via Bash | MCP Server |
|--------|-------------|------------|
| **Mechanism** | Exit codes (0 = success) + stderr | JSON-RPC error objects with codes |
| **Error detail** | Text messages in stderr | Structured error objects (`code`, `message`, `data`) |
| **Handling code** | `if exit_code != 0: ...` | `try: call_tool() except MCPError: ...` |
| **Pros** | ✅ Universal Unix convention<br>✅ Simple boolean check | ✅ Rich error context<br>✅ Standardized error codes<br>✅ Typed exceptions |
| **Cons** | ❌ Limited error context<br>❌ Text parsing for details | ❌ Protocol complexity<br>❌ Need error code registry |

**Current implementation**: Checks `exit_code == 0` and `bool(output)` for success. Simple and effective.

---

### 4. Context Passing

| Aspect | CLI via Bash | MCP Server |
|--------|-------------|------------|
| **Input format** | String (with shell escaping) | JSON objects |
| **Escaping** | Shell metacharacters (`"`, `'`, `$`, backticks) | JSON escaping (automatic via stdlib) |
| **Multiline** | Heredocs or escaped newlines | Native JSON strings |
| **Files** | Stdin redirect (`< file.pdf`) | Base64 encoding or file paths in JSON |
| **Pros** | ✅ Shell primitives (pipes, redirects)<br>✅ No serialization for text | ✅ No escaping concerns<br>✅ Structured context objects |
| **Cons** | ❌ Shell escaping pitfalls<br>❌ Heredoc verbosity | ❌ Large file encoding overhead<br>❌ No native stdin/pipe |

**Current approach**: Uses shell escaping carefully. Works well for text prompts.

---

### 5. Logging/Observability

| Aspect | CLI via Bash | MCP Server |
|--------|-------------|------------|
| **Implementation** | PostToolUse hook (`.claude/hooks/log-cli-tools.py`) | Protocol-level logging (MCP SDK feature) |
| **Log format** | JSONL (`.claude/logs/cli-tools.jsonl`) | Depends on MCP server implementation |
| **What's logged** | Timestamp, tool, model, prompt, response, success | Could include protocol metadata (request_id, timing) |
| **Access** | All agents read same JSONL file | Depends on server logging setup |
| **Pros** | ✅ Simple append-only log<br>✅ Easy to query with `jq`<br>✅ Human-readable | ✅ Built-in to protocol<br>✅ Can include request tracing |
| **Cons** | ❌ Manual hook implementation<br>❌ Regex-based extraction | ❌ Need to configure logging<br>❌ Potential complexity |

**Current approach**: Clean JSONL logs. Easy to inspect and debug.

---

### 6. Subagent Integration

| Aspect | CLI via Bash | MCP Server |
|--------|-------------|------------|
| **Pattern** | Task tool → spawns subagent → `Bash("codex exec ...")` | Task tool → spawns subagent → ??? |
| **Context flow** | Subagent calls CLI, processes full output, returns summary | Subagent calls MCP tool, processes response, returns summary |
| **Isolation** | Full process isolation (each call independent) | Depends on MCP server design |
| **Pros** | ✅ Already working<br>✅ No changes needed<br>✅ Subagent can save raw CLI output | ✅ Could pass structured context<br>✅ Subagent could use MCP resources |
| **Cons** | ❌ Text-based handoff | ❌ Need to design subagent-MCP integration<br>❌ Unclear how Task tool would invoke MCP |

**Critical question**: How would Claude Code Task tool invoke MCP? Would need SDK integration.

---

### 7. Developer Experience

| Aspect | CLI via Bash | MCP Server |
|--------|-------------|------------|
| **Setup complexity** | Install CLI tools (`codex`, `gemini`) | Install MCP SDK + implement server + register with Claude |
| **Development** | No code (just call CLI) | Write MCP server code (tools, resources, prompts) |
| **Debugging** | Shell command testing, `echo` output | JSON-RPC debugging, protocol inspection |
| **Documentation** | CLI `--help`, man pages | MCP spec, SDK docs |
| **Pros** | ✅ Zero code (just config)<br>✅ Standard shell tools<br>✅ Familiar to all devs | ✅ IDE support (if SDK mature)<br>✅ Type safety (Python/TS SDKs) |
| **Cons** | ❌ String manipulation<br>❌ Shell escaping gotchas | ❌ Protocol learning curve<br>❌ More moving parts |

**Current approach**: Minimal code. PreToolUse hooks guide usage.

---

### 8. Future Extensibility

| Aspect | CLI via Bash | MCP Server |
|--------|-------------|------------|
| **Adding new tools** | Install new CLI, update hooks | Implement MCP tool, register capability |
| **Capability discovery** | Static (documented in `.claude/rules/`) | Dynamic (MCP `tools/list` request) |
| **Versioning** | CLI version flags | MCP protocol versioning |
| **Ecosystem** | Ad-hoc (each CLI different) | Standardized (MCP registry) |
| **Pros** | ✅ Flexibility (any CLI works)<br>✅ No protocol lock-in | ✅ Standardized discovery<br>✅ Growing ecosystem<br>✅ Future Claude Code native support |
| **Cons** | ❌ No standard interface<br>❌ Manual integration each time | ❌ Requires MCP adoption by tool authors<br>❌ Protocol evolution risk |

**Long-term**: MCP is the future. But CLI works today.

---

## Use Case Analysis: This Project

### Current Requirements
- Infrequent calls (design decisions, research)
- Subagent pattern (preserve main context)
- Logging for audit trail
- Simple integration

### CLI Strengths for This Use Case
1. **Already working** - Hooks, subagents, logging all in place
2. **Simple** - No server lifecycle, no protocol complexity
3. **Flexible** - Can call any CLI tool (not just Codex/Gemini)
4. **Debuggable** - Shell commands easy to test independently

### MCP Strengths for Future
1. **Standardization** - If many tools adopt MCP
2. **Streaming** - If real-time output becomes critical
3. **Discovery** - If tool catalog grows large
4. **Integration** - If Claude Code adds native MCP support

---

## Recommendation

### ✅ Keep CLI Approach (Short Term)

**Reasons:**
1. Works well with current subagent pattern
2. Simple, debuggable, maintainable
3. No protocol overhead for infrequent calls
4. JSONL logging is clear and queryable

### 🔮 Consider MCP Migration When:

1. **Claude Code natively supports MCP tools**
   - Task tool can invoke MCP servers directly
   - No need for Bash wrapper

2. **Streaming becomes critical**
   - Real-time output display needed
   - Interactive multi-turn conversations with tools

3. **Tool ecosystem grows**
   - Many MCP servers available
   - Dynamic discovery valuable

4. **Standardization matters**
   - Publishing tools for others to use
   - Need interoperability across AI platforms

### 🛠️ Migration Path (When Ready)

```python
# Phase 1: Implement MCP server wrapper
# Expose codex/gemini as MCP tools
class CodexMCPServer:
    @mcp.tool()
    async def consult_codex(prompt: str, model: str) -> str:
        # Call codex CLI internally
        # Return structured response
        pass

# Phase 2: Update Claude Code to use MCP
# Replace Bash calls with MCP tool invocations
# Update logging to capture MCP protocol

# Phase 3: Remove CLI dependency
# Implement Codex/Gemini as native MCP servers
```

---

## Sources

- [Introducing the Model Context Protocol](https://www.anthropic.com/news/model-context-protocol)
- [Model Context Protocol - Wikipedia](https://en.wikipedia.org/wiki/Model_Context_Protocol)
- [Architecture overview - Model Context Protocol](https://modelcontextprotocol.io/docs/learn/architecture)
- [Why Model Context Protocol uses JSON-RPC](https://medium.com/@dan.avila7/why-model-context-protocol-uses-json-rpc-64d466112338)
- [MCP - Protocol Mechanics and Architecture](https://pradeepl.com/blog/model-context-protocol/mcp-protocol-mechanics-and-architecture/)
- [Model Context Protocol (MCP): Architecture, Components & Workflow](https://www.kubiya.ai/blog/model-context-protocol-mcp-architecture-components-and-workflow)
