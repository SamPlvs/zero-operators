---
description: List all defined agents with their roles, tiers, and teams
---

# /agents — Agent Roster

You are listing all agent definitions in the Zero Operators system.

## Steps

1. **Find all agent definition files** in `.claude/agents/`. List all `.md` files:
   ```bash
   ls .claude/agents/*.md
   ```

2. **Parse each agent file**. Read the YAML frontmatter from each file and extract:
   - `name` — agent display name
   - `model` or model tier (opus, sonnet, haiku)
   - `description` — one-line role description
   - Team membership (project delivery vs platform build)
   - Any other frontmatter fields (tools, tier, etc.)

3. **Read the role section** from each agent's markdown body. Extract a one-line summary of their role.

4. **Display as a grouped table**:

   ```
   ZO Agent Roster
   ═══════════════

   Project Delivery Team — Launch Agents
   ┌──────────────────┬────────┬─────────────────────────────────────────┬────────┐
   │ Name             │ Model  │ Role                                    │ Status │
   ├──────────────────┼────────┼─────────────────────────────────────────┼────────┤
   │ lead-orchestrator│ opus   │ Coordinates pipeline, gates, checkpoints│ launch │
   │ data-engineer    │ sonnet │ Data pipeline, cleaning, profiling      │ launch │
   │ model-builder    │ sonnet │ Architecture, training, iteration       │ launch │
   │ oracle-qa        │ sonnet │ Hard oracle, metric evaluation, gating  │ launch │
   │ code-reviewer    │ sonnet │ Code quality gate                       │ launch │
   │ test-engineer    │ sonnet │ Test coverage and correctness            │ launch │
   └──────────────────┴────────┴─────────────────────────────────────────┴────────┘

   Project Delivery Team — Phase-In Agents
   ┌──────────────────┬────────┬─────────────────────────────────────────┬──────────┐
   │ Name             │ Model  │ Role                                    │ Status   │
   │ xai-agent        │ sonnet │ Explainability analysis                 │ phase-in │
   │ ...              │ ...    │ ...                                     │ ...      │
   └──────────────────┴────────┴─────────────────────────────────────────┴──────────┘

   Platform Build Team
   ┌──────────────────┬────────┬─────────────────────────────────────────┐
   │ ...              │ ...    │ ...                                     │
   └──────────────────┴────────┴─────────────────────────────────────────┘
   ```

5. **Show summary** at the bottom:
   - Total agents defined
   - Breakdown by team and status (launch vs phase-in)
   - Any agents referenced in specs but not yet defined as files
