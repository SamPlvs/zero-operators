---
description: Display recent comms log events for a project
argument-hint: <project-name> [--type <event_type>] [--agent <agent-name>]
---

# /logs — Comms Log Viewer

You are displaying the structured JSONL communication logs for a Zero Operators project.

## Steps

1. **Find JSONL log files** in `logs/comms/`. List available files sorted by date.

2. **Read the most recent log file** (`logs/comms/{YYYY-MM-DD}.jsonl`). Parse each line as JSON.

3. **Apply filters** if provided in the arguments:
   - `--type <event_type>`: Filter to only events matching that type (message, decision, gate, error, checkpoint)
   - `--agent <agent-name>`: Filter to only events from that agent
   - If no filters, show all events

4. **Display events** in a readable table format. Show the last 20 events by default:

   ```
   Comms Log: {project-name} ({date})
   Showing: {filter description or "all events"}

   TIMESTAMP    AGENT              TYPE        SUMMARY
   ─────────────────────────────────────────────────────────
   14:32:15     model-builder      message     Requested updated DataLoader from data-engineer
   14:35:00     data-engineer      status      DataLoader ready with 3 splits
   14:36:12     oracle-qa          gate        Gate 3: RMSE 0.042 <= 0.05 PASS
   14:40:00     lead-orchestrator  decision    Proceed to Phase 4
   14:50:00     data-engineer      error       Sensor 12 data 45% NaN in Q3
   ```

5. **For each event type, extract the most useful summary**:
   - `message`: Show subject or first line of body
   - `decision`: Show title and outcome
   - `gate`: Show metric, value, threshold, and pass/fail
   - `error`: Show description and severity
   - `checkpoint`: Show phase, progress, and current metric

6. **Show metadata** at the bottom:
   - Total events in log file
   - Events shown (after filtering)
   - Date range of log file
   - Available log files if more than one exists
