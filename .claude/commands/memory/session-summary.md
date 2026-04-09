---
description: Write a session summary and update all memory files — the "wrap up cleanly" command
---

# /session-summary — End-of-session wrap-up

You are writing a session summary and updating all memory artifacts for the current project. This is the clean wrap-up command.

## 1. Detect current project

```bash
!find "$(git rev-parse --show-toplevel)/memory" -name "STATE.md" -type f 2>/dev/null
```

If multiple projects exist, determine which one was actively worked on this session by checking recent git changes and file modifications. If ambiguous, ask the user.

## 2. Collect session information

### What was accomplished

Review the current conversation and session activity. Identify:
- Tasks completed
- Files created or modified
- Features implemented or bugs fixed
- Experiments run and their results

### Decisions made

Identify any decisions made during this session:
- Architecture choices
- Tool or library selections
- Approach changes
- Trade-offs evaluated

### Files changed

```bash
!cd "$(git rev-parse --show-toplevel)" && git diff --name-only HEAD~5 2>/dev/null || git diff --name-only 2>/dev/null
```

Also check the target repo for changes:

```bash
!grep "target_repo" "$(git rev-parse --show-toplevel)/targets/{project-name}.target.md" 2>/dev/null
```

```bash
!cd "{target-repo-path}" && git diff --name-only HEAD~5 2>/dev/null || echo "No target repo changes"
```

### Blockers hit

Note any issues encountered:
- Errors or failures
- Missing dependencies or data
- Unclear requirements
- Blocked on human input

## 3. Write session summary

Create the session summary file:

```bash
!date +%Y-%m-%d-%H%M%S
```

Write to `memory/{project-name}/sessions/session-{timestamp}.md`:

```markdown
# Session Summary: {date}
**Date**: {YYYY-MM-DD}
**Duration**: {estimated duration}
**Mode**: {build | continue | maintain}
**Agent**: orchestrator

## Accomplished
- {task 1}
- {task 2}

## Decisions Made
- {decision 1} (see DECISION_LOG entry: {short title})
- {decision 2}

## Blockers Hit
- {blocker 1, status: resolved | open}

## Next Steps
- {action 1}
- {action 2}

## Files Changed
- {filename}: {brief description of change}

## Context Handoff
- Estimated completion: {estimate or "blocked"}
- Open questions: {list}
- Recommended next phase: {recommendation}
```

## 4. Update STATE.md

Read the current STATE.md and update it:

```markdown
# STATE
timestamp: {now in ISO 8601}
mode: {current mode}
phase: {current phase, advance if phase completed}
last_completed_subtask: {most recent completed subtask}
active_blockers: [{list of open blockers}]
next_steps: [{prioritized list of next actions}]
active_agents: [{agents that were active}]
git_head: {current commit hash}
context_window_usage: "not tracked in v1"
```

Get the current git HEAD:

```bash
!cd "$(git rev-parse --show-toplevel)" && git rev-parse HEAD
```

## 5. Append to DECISION_LOG.md

For each decision identified in step 2, append an entry to `memory/{project-name}/DECISION_LOG.md`:

```markdown
## Decision: {short title}
**Timestamp**: {ISO 8601}
**Context**: {brief description of the situation}
**Decision**: {what was decided}
**Rationale**: {why this decision was made}
**Alternatives Considered**: {other options and why rejected}
**Outcome**: {result or "pending"}
**Confidence**: {high | medium | low}
---
```

Remember: DECISION_LOG is append-only. Never edit or remove existing entries.

## 6. Rebuild semantic index

If the semantic index infrastructure is available:

```bash
!cd "$(git rev-parse --show-toplevel)" && python -c "
from zo.semantic import SemanticIndex
from zo.memory import MemoryManager
from pathlib import Path
mm = MemoryManager(project_dir=Path('.'), project_name='{project-name}')
idx = SemanticIndex(mm.memory_root / 'index.db')
decisions = mm.read_decisions()
priors = mm.read_priors()
if decisions:
    idx.index_decisions(decisions)
if priors:
    idx.index_priors(priors)
idx.close()
print('Semantic index rebuilt.')
" 2>/dev/null || echo "Semantic index rebuild skipped (not available)"
```

## 7. Confirm

Report to the user:
- Session summary file path
- STATE.md updated (show key fields: phase, next steps)
- Number of decisions logged
- Whether semantic index was rebuilt
- Reminder of next steps for the following session
