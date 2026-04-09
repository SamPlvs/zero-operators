---
description: Show a combined timeline of sessions, commits, and decisions for a project
argument-hint: <project-name>
---

# /history — Project History Timeline

You are building a comprehensive chronological history of a Zero Operators project.

## Steps

1. **Read all session summaries** from `memory/{project-name}/sessions/`. For each session file, extract:
   - Session date/timestamp
   - Phase worked on
   - Key accomplishments
   - Blockers encountered
   - Decisions made

2. **Read git log** from the delivery repo (if identifiable from the plan or STATE.md). Run:
   ```bash
   git log --oneline --since="project start date" --format="%h %ad %s" --date=short
   ```
   Extract commit hashes, dates, and messages.

3. **Read DECISION_LOG.md** (`memory/{project-name}/DECISION_LOG.md`). Extract key decisions with timestamps.

4. **Combine into a unified chronological timeline**:

   ```
   Project History: {project-name}
   Started: {earliest date} | Last activity: {latest date}
   Sessions: {count} | Commits: {count} | Decisions: {count}

   DATE         TYPE       SUMMARY
   ───────────────────────────────────────────────────────────
   2026-04-01   session    Session 1: Project setup, plan approved
   2026-04-01   commit     abc1234 feat: initial data pipeline
   2026-04-01   decision   Feature list approved by human
   2026-04-02   session    Session 2: Data profiling, quality issues found
   2026-04-02   commit     def5678 fix: handle NaN in sensor data
   2026-04-02   decision   Exclude Sensor 12 Q3 data
   2026-04-03   session    Session 3: Model training, first oracle eval
   2026-04-03   gate       Gate 2: Oracle RMSE 0.042 PASS
   2026-04-03   commit     ghi9012 feat: LSTM model v1
   ```

5. **Group by phase** if the timeline is long (more than 30 entries). Show phase boundaries clearly.

6. **Report** at the bottom:
   - Total elapsed time
   - Phases completed vs remaining
   - Current status
