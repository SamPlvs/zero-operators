---
description: Load full project context — the "catch me up" command for new sessions
argument-hint: <project-name>
---

# /prime — Context briefing for a new session

You are preparing a context briefing for project `$ARGUMENTS`. This is the "catch me up" command — read everything relevant and present a concise summary of where we are.

If no argument is provided, detect the active project from memory or ask the user.

## 1. Read STATE.md

```bash
!cat "$(git rev-parse --show-toplevel)/memory/$ARGUMENTS/STATE.md" 2>/dev/null || echo "NO STATE"
```

If STATE.md does not exist, tell the user the project is not initialized and suggest running `/project/connect` or `zo init`.

Extract and note:
- Current mode (build / continue / maintain)
- Current phase
- Last completed subtask
- Active blockers
- Next steps
- Active agents
- Git HEAD commit

## 2. Read recent session summaries

```bash
!ls -t "$(git rev-parse --show-toplevel)/memory/$ARGUMENTS/sessions/" 2>/dev/null | head -3
```

Read the last 3 session summaries. For each, note:
- What was accomplished
- Decisions made (with DECISION_LOG references)
- Blockers hit
- Recommended next steps

## 3. Query relevant decisions

Read `memory/{project-name}/DECISION_LOG.md` and extract decisions related to the current phase. If the semantic index exists, use it:

```bash
!cd "$(git rev-parse --show-toplevel)" && python -c "
from zo.semantic import SemanticIndex
from pathlib import Path
idx = SemanticIndex(Path('memory/$ARGUMENTS/index.db'))
results = idx.query('current phase decisions and blockers', top_k=5)
for r in results:
    print(f'[{r.score:.2f}] {r.text[:200]}')
idx.close()
" 2>/dev/null || echo "No semantic index available"
```

Otherwise, read the last 5-10 entries from DECISION_LOG.md directly.

## 4. Read domain priors

Read `memory/{project-name}/PRIORS.md` in full. Note all accumulated domain knowledge, especially:
- High-confidence priors
- Recently added priors
- Any superseded priors (indicates learning/correction)

## 5. Check delivery repo activity

Find the target repo path from the target file:

```bash
!grep "target_repo" "$(git rev-parse --show-toplevel)/targets/$ARGUMENTS.target.md" 2>/dev/null
```

Check recent git activity in the delivery repo:

```bash
!cd "$(git rev-parse --show-toplevel)/../{target-repo}" && git log --oneline -10 2>/dev/null || echo "Target repo not accessible"
```

## 6. Present context briefing

Format the briefing as a concise, scannable summary:

```
## Context Briefing: {project-name}
**Date**: {today}

### Where We Are
- **Mode**: {mode}
- **Phase**: {phase}
- **Last completed**: {last subtask}
- **Blockers**: {list or "none"}

### What Happened Recently
{2-3 bullet summary from most recent session}
{2-3 bullet summary from second most recent session}

### Key Decisions
{List the 3-5 most relevant recent decisions with one-line summaries}

### What We Know (Domain Priors)
{List key priors, grouped by category if multiple exist}
- {prior 1}
- {prior 2}

### Delivery Repo Activity
{Recent commits in the target repo, or "no activity"}

### What's Next
{Next steps from STATE.md, prioritized}
1. {next step 1}
2. {next step 2}
3. {next step 3}

### Open Blockers
{Any unresolved blockers that need attention}
```

Keep the briefing to one screenful if possible. The goal is to get the human (or a new agent session) fully oriented in under 30 seconds of reading.
