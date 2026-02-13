# Claude Code Agent Teams Research

**Research Date**: 2026-02-08
**Feature Status**: Experimental (requires opt-in)
**Launched**: February 2026 with Claude Opus 4.6

---

## 1. What are Agent Teams? (概要)

Agent teams enable coordination of multiple Claude Code instances working together as a collaborative unit. Key characteristics:

- **Team Lead**: One Claude Code session that creates the team, spawns teammates, and coordinates work
- **Teammates**: Separate, fully independent Claude Code instances, each with their own context window
- **Shared Infrastructure**: Task list for work coordination and mailbox for inter-agent messaging
- **Direct Communication**: Unlike subagents, teammates can message each other directly without going through the lead

**Key Distinction**: Agent teams are multiple independent Claude instances collaborating, NOT multiple agents within a single session.

---

## 2. Architecture & How it Works (アーキテクチャ)

### Components

| Component | Role |
|-----------|------|
| **Team Lead** | Main Claude Code session that creates team, spawns teammates, coordinates work |
| **Teammates** | Separate Claude Code instances working on assigned tasks |
| **Task List** | Shared list of work items (`~/.claude/tasks/{team-name}/`) |
| **Mailbox** | Messaging system for inter-agent communication |

### Task Management

- **Task States**: pending → in progress → completed
- **Dependencies**: Tasks can depend on other tasks; blocked tasks auto-unblock when dependencies complete
- **Task Claiming**: File locking prevents race conditions when multiple teammates claim same task
- **Assignment Methods**: Lead can assign explicitly, or teammates self-claim available tasks

### Communication Flow

- **Automatic Delivery**: Messages sent by teammates are delivered automatically to recipients
- **Idle Notifications**: Teammates notify lead when they finish and stop
- **Broadcast**: Send messages to all teammates (use sparingly due to cost scaling)

### Storage

- Team config: `~/.claude/teams/{team-name}/config.json`
- Task list: `~/.claude/tasks/{team-name}/`
- Config contains `members` array with each teammate's name, agent ID, and agent type

---

## 3. Configuration & Setup (設定方法)

### Enable Agent Teams

**Method 1: Environment Variable**
```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

**Method 2: settings.json**
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### Display Modes

**In-Process Mode** (default for non-tmux terminals):
- All teammates run inside main terminal
- Shift+Up/Down to select teammate
- Type to message selected teammate
- Enter to view teammate's session
- Escape to interrupt current turn
- Ctrl+T to toggle task list
- Works in any terminal, no setup required

**Split-Panes Mode** (default when already in tmux):
- Each teammate in own pane
- Click pane to interact directly
- See all output simultaneously
- Requires tmux or iTerm2

**Configure Display Mode:**
```json
{
  "teammateMode": "in-process"  // or "auto" or "tmux"
}
```

Or via CLI flag:
```bash
claude --teammate-mode in-process
```

### Requirements for Split-Panes

- **tmux**: Install via system package manager
- **iTerm2**: Install `it2` CLI + enable Python API in preferences
- **Not Supported**: VS Code integrated terminal, Windows Terminal, Ghostty

---

## 4. When to Use (使用すべき場面)

### Best Use Cases

✅ **Research and Review**
- Multiple teammates investigate different aspects simultaneously
- Share and challenge each other's findings
- Example: Parallel code review with security, performance, test coverage reviewers

✅ **New Modules or Features**
- Teammates own separate pieces
- Minimal file conflicts
- Independent work units

✅ **Debugging with Competing Hypotheses**
- Test different theories in parallel
- Teammates actively try to disprove each other's theories
- Scientific debate structure to avoid anchoring bias

✅ **Cross-Layer Coordination**
- Changes spanning frontend, backend, tests
- Each layer owned by different teammate
- Clear boundaries between components

### When NOT to Use

❌ **Sequential Tasks**: Where steps must happen in order
❌ **Same-File Edits**: Risk of overwrites and conflicts
❌ **Tasks with Many Dependencies**: Coordination overhead exceeds benefit
❌ **Simple, Straightforward Tasks**: Single session more cost-effective

### Starter Tasks for Newcomers

Start with tasks that have clear boundaries and don't require writing code:
- Reviewing a PR
- Researching a library
- Investigating a bug

These show value of parallel exploration without coordination challenges.

---

## 5. Agent Teams vs Subagents (比較)

|                   | Subagents | Agent Teams |
|:------------------|:----------|:------------|
| **Context**       | Own context window; results return to caller | Own context window; fully independent |
| **Communication** | Report results back to main agent only | Teammates message each other directly |
| **Coordination**  | Main agent manages all work | Shared task list with self-coordination |
| **Best for**      | Focused tasks where only result matters | Complex work requiring discussion and collaboration |
| **Token cost**    | Lower: results summarized back to main context | Higher: each teammate is separate Claude instance |

**Decision Rule**:
- Use **subagents** when you need quick, focused workers that report back
- Use **agent teams** when teammates need to share findings, challenge each other, and coordinate on their own

**Context Management**:
- For tasks exceeding context window or needing sustained parallelism: Agent teams
- For many detailed results that consume context: Subagents can also be expensive

---

## 6. Best Practices (ベストプラクティス)

### Give Teammates Enough Context

Teammates load project context automatically (CLAUDE.md, MCP servers, skills) but NOT lead's conversation history.

**Good spawn prompt example:**
```
Spawn a security reviewer teammate with the prompt: "Review the authentication module
at src/auth/ for security vulnerabilities. Focus on token handling, session
management, and input validation. The app uses JWT tokens stored in
httpOnly cookies. Report any issues with severity ratings."
```

### Size Tasks Appropriately

- **Too small**: Coordination overhead exceeds benefit
- **Too large**: Teammates work too long without check-ins, increasing wasted effort risk
- **Just right**: Self-contained units producing clear deliverable (function, test file, review)

**Guideline**: 5-6 tasks per teammate keeps everyone productive and allows lead to reassign work if someone gets stuck.

### Avoid File Conflicts

Break work so each teammate owns different set of files. Two teammates editing same file leads to overwrites.

### Monitor and Steer

- Check in on teammates' progress
- Redirect approaches that aren't working
- Synthesize findings as they come in
- Don't let team run unattended too long

### Wait for Teammates

If lead starts implementing instead of waiting:
```
Wait for your teammates to complete their tasks before proceeding
```

### Use Delegate Mode

Prevents lead from implementing tasks itself. Lead restricted to:
- Spawning teammates
- Messaging
- Shutting down teammates
- Managing tasks

Enable: Start team, then Shift+Tab to cycle into delegate mode.

### Quality Gates with Hooks

- `TeammateIdle`: Runs when teammate about to go idle. Exit code 2 sends feedback and keeps teammate working.
- `TaskCompleted`: Runs when task being marked complete. Exit code 2 prevents completion and sends feedback.

---

## 7. Limitations (制限事項)

### Known Limitations

⚠️ **No Session Resumption with In-Process Teammates**
- `/resume` and `/rewind` do not restore in-process teammates
- After resuming, lead may attempt to message non-existent teammates
- Solution: Spawn new teammates

⚠️ **Task Status Can Lag**
- Teammates sometimes fail to mark tasks as completed
- Blocks dependent tasks
- Solution: Check if work actually done, update manually or nudge teammate

⚠️ **Shutdown Can Be Slow**
- Teammates finish current request/tool call before shutting down

⚠️ **One Team Per Session**
- Lead can only manage one team at a time
- Must clean up current team before starting new one

⚠️ **No Nested Teams**
- Teammates cannot spawn their own teams
- Only lead can manage the team

⚠️ **Lead is Fixed**
- Session that creates team is lead for lifetime
- Cannot promote teammate to lead or transfer leadership

⚠️ **Permissions Set at Spawn**
- All teammates start with lead's permission mode
- Can change individual teammate modes after spawning
- Cannot set per-teammate modes at spawn time

⚠️ **Split Panes Platform Limitations**
- Not supported in VS Code integrated terminal, Windows Terminal, Ghostty
- Requires tmux or iTerm2

### Cleanup Warning

⚠️ **Always use lead to clean up team**
- Teammates' team context may not resolve correctly
- Can leave resources in inconsistent state

---

## 8. Key Considerations (重要な考慮点)

### Token Usage & Cost

**Cost Scaling**:
- Each teammate = separate Claude instance with own context window
- 5-person team ≈ 5x tokens of single session
- Only worthwhile for tasks where parallel exploration adds real value

**Real-World Example**:
- 16 agents writing Rust-based C compiler for Linux kernel
- 2,000+ Claude Code sessions
- $20,000 in API costs
- Result: 100,000-line compiler

**Recommendation**: For research, review, and new feature work, extra tokens usually worthwhile. For routine tasks, single session more cost-effective.

### Permission Management

- Teammate permission requests bubble up to lead
- Can create friction with many prompts
- **Solution**: Pre-approve common operations in permission settings before spawning teammates

### How Teams Get Started

**Two Methods**:
1. **Explicit Request**: You ask Claude to create agent team
2. **Claude Proposes**: Claude suggests team if task would benefit from parallel work

**You stay in control**: Claude won't create team without approval.

### Context Loading

Teammates receive at spawn:
- Same project context as regular session (CLAUDE.md, MCP servers, skills)
- Spawn prompt from lead
- **NOT**: Lead's conversation history

---

## Use Case Examples

### Parallel Code Review
```
Create an agent team to review PR #142. Spawn three reviewers:
- One focused on security implications
- One checking performance impact
- One validating test coverage
Have them each review and report findings.
```

**Why it works**: Single reviewer gravitates toward one issue type. Splitting criteria into independent domains ensures thorough attention to all aspects simultaneously.

### Competing Hypotheses Investigation
```
Users report the app exits after one message instead of staying connected.
Spawn 5 agent teammates to investigate different hypotheses. Have them talk to
each other to try to disprove each other's theories, like a scientific
debate. Update the findings doc with whatever consensus emerges.
```

**Why it works**: Debate structure prevents anchoring bias. Theory that survives adversarial testing more likely to be actual root cause.

### CLI Tool Design Exploration
```
I'm designing a CLI tool that helps developers track TODO comments across
their codebase. Create an agent team to explore this from different angles: one
teammate on UX, one on technical architecture, one playing devil's advocate.
```

**Why it works**: Three roles are independent and can explore problem without waiting on each other.

---

## Troubleshooting

### Teammates Not Appearing
- May already be running (press Shift+Down to cycle)
- Task may not be complex enough for team
- Check tmux installed and in PATH: `which tmux`
- For iTerm2: verify `it2` CLI installed, Python API enabled

### Too Many Permission Prompts
- Pre-approve common operations in permission settings before spawning

### Teammates Stopping on Errors
- Check output (Shift+Up/Down or click pane)
- Give additional instructions directly
- Spawn replacement teammate

### Lead Shuts Down Before Work Done
- Tell lead to keep going
- Instruct lead to wait for teammates before proceeding

### Orphaned tmux Sessions
```bash
tmux ls
tmux kill-session -t <session-name>
```

---

## Sources

- [Orchestrate teams of Claude Code sessions - Official Docs](https://code.claude.com/docs/en/agent-teams)
- [Anthropic releases Opus 4.6 with new 'agent teams' | TechCrunch](https://techcrunch.com/2026/02/05/anthropic-releases-opus-4-6-with-new-agent-teams/)
- [AddyOsmani.com - Claude Code Swarms](https://addyosmani.com/blog/claude-code-agent-teams/)
- [Claude Code Agent Teams: Setup Guide (Experimental) | Marco Patzelt](https://www.marc0.dev/en/blog/claude-code-agent-teams-multiple-ai-agents-working-in-parallel-setup-guide-1770317684454)
- [Claude Opus 4.6 Agent Teams Tutorial | NxCode](https://www.nxcode.io/resources/news/claude-agent-teams-parallel-ai-development-guide-2026)
- [Claude Code's Hidden Multi-Agent System | Paddo.dev](https://paddo.dev/blog/claude-code-hidden-swarm/)
- [Anthropic Documentation - Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)
