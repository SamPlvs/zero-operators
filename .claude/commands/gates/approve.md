---
description: Approve the current pending gate and advance to the next phase
---

# /approve — Gate Approval

You are executing a human gate approval for the current Zero Operators project.

## Steps

1. **Read STATE.md** in the project's memory directory (`memory/{project}/STATE.md`). Identify:
   - The current phase and its status
   - Which gate is pending (look for `status: PENDING_GATE` or similar)
   - If no gate is pending, report that and stop

2. **Log the approval to DECISION_LOG.md** (`memory/{project}/DECISION_LOG.md`). Append an entry:
   ```markdown
   ## Gate Approved: {gate name}
   **Timestamp**: {ISO 8601 now}
   **Decided by**: human
   **Phase**: {phase that was gated}
   **Outcome**: approved
   **Notes**: Human approved gate via /approve command
   ```

3. **Update STATE.md** to advance to the next phase:
   - Set the current phase status to `COMPLETED`
   - Set the next phase status to `ACTIVE`
   - Update `last_updated` timestamp

4. **Log gate event to comms JSONL** (`logs/comms/{YYYY-MM-DD}.jsonl`). Append:
   ```json
   {
     "timestamp": "{ISO 8601}",
     "session_id": "manual",
     "event_type": "gate",
     "agent": "human",
     "project": "{project-name}",
     "gate_id": "{gate-id}",
     "gate_name": "{gate-name}",
     "result": "pass",
     "notes": "Human approved via /approve command"
   }
   ```

5. **Report** to the user:
   - What gate was approved
   - What phase just completed
   - What phase is now active
   - Any relevant next steps from the plan
