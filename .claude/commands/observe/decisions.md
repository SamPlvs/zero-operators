---
description: Display all decisions from the project decision log
argument-hint: <project-name> [search-term]
---

# /decisions — Decision Log Viewer

You are displaying the parsed decision log for a Zero Operators project.

## Steps

1. **Read DECISION_LOG.md** from `memory/{project-name}/DECISION_LOG.md`. If the file does not exist, report that no decisions have been logged yet and stop.

2. **Parse all decision entries**. Each entry is a markdown section (## heading) with structured fields. Extract:
   - Entry number (sequential)
   - Timestamp
   - Title (from heading)
   - Category (decision, gate, failure, evolution)
   - Outcome (approved, rejected, proceed, blocked, etc.)
   - Confidence (if present)
   - Decided by (agent name or human)

3. **Apply search filter** if a search term is provided after the project name:
   - Filter entries where the title, description, or any field contains the search term (case-insensitive)
   - Report: "Filtered to entries matching: '{search-term}'"

4. **Display as a numbered list**:

   ```
   Decision Log: {project-name}
   Total: {count} entries | {date-range}

   #  | TIMESTAMP            | TITLE                          | BY               | OUTCOME    | CONFIDENCE
   ───┼──────────────────────┼────────────────────────────────┼──────────────────┼────────────┼───────────
   1  | 2026-04-05 10:00:00  | Feature list approved          | human            | approved   | high
   2  | 2026-04-05 14:30:00  | Use LSTM over Transformer      | lead-orchestrator| proceed    | medium
   3  | 2026-04-06 09:15:00  | Gate 2: Oracle threshold met   | oracle-qa        | pass       | high
   4  | 2026-04-06 11:00:00  | Data quality failure Sensor 12 | data-engineer    | escalated  | -
   ```

5. **Show summary stats** at the bottom:
   - Total decisions
   - By category breakdown (decisions / gates / failures / evolutions)
   - Date range (earliest to latest)
