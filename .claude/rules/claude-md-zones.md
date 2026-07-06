# CLAUDE.md 3-Zone Contract (SSOT)

Canonical description of the CLAUDE.md zone structure. Skills reference this
rule instead of restating it.

## Layout and Markers

```
Zone A — Orchestra concept & template base (orchestrator contract)
# ━━━ box ━━━
# @orchestra:template-boundary
# ━━━ box ━━━
Zone B — Repository Identity (thin identity line + pointer to DESIGN.md)
# ━━━ box ━━━
# @orchestra:repo-boundary
# ━━━ box ━━━
Zone C — Working state (Progress Tracker link, Current Project/Feature/Bug Fix blocks)
```

The two markers, each wrapped in a `━` separator box, are the load-bearing
anchors: `@orchestra:template-boundary` and `@orchestra:repo-boundary`.
(A legacy single-marker layout used `@orchestra:local-boundary`;
`scripts/update.sh` auto-migrates it to the 3-zone layout.)

## Zone Ownership (who writes where)

| Zone | Owner / writers | Content |
|------|-----------------|---------|
| **A** | Template — replaced wholesale by `scripts/update.sh` | Orchestrator contract (Mission, Routing, etc.). Never edited by skills. |
| **B** | `/init` only | Thin Repository Identity + pointer to `.claude/docs/DESIGN.md`. |
| **C** | `/feature`, `/troubleshoot` (append work blocks); `/checkpointing` (idempotent `## Progress Tracker` link; its Compact Phase / `--compact-only` prunes stale blocks); manual notes | Cross-session working state. |

Additional invariants:

- The Zone C `## Progress Tracker` block (link to `PROGRESS.md`) is owned by
  `/checkpointing` and must survive every Zone C rewrite verbatim.
- Marker lines and their `━` boxes are never edited, moved, or duplicated.
- No skill writes outside its own zone.

## Markers Missing → run `scripts/update.sh`

If either marker is absent (legacy or hand-edited file), **stop and ask the
user to run `./scripts/update.sh`**. The updater migrates legacy layouts
automatically (content below the legacy marker becomes Zone C; Zone B is reset
to the placeholder for `/init`). Never hand-insert markers.

Mechanical checks: `.claude/skills/checkpointing/refresh_guard.py --mode check`
(exit `2` = markers missing) and `.claude/skills/init/detect_stack.py`
(`claude_md_markers` field, exit `2` = markers missing).
