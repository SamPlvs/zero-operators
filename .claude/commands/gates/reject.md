---
description: Reject the current pending gate with a reason, triggering rework
argument-hint: <reason>
---

# /reject — Gate Rejection

You are executing a human gate rejection for the current Zero Operators project. The argument provided is the rejection reason.

## Steps

1. **Read STATE.md** in the project's memory directory (`memory/{project}/STATE.md`). Identify:
   - The current phase and its status
   - Which gate is pending
   - If no gate is pending, report that and stop

2. **Log the rejection to DECISION_LOG.md** (`memory/{project}/DECISION_LOG.md`). Append:
   ```markdown
   ## Gate Rejected: {gate name}
   **Timestamp**: {ISO 8601 now}
   **Decided by**: human
   **Phase**: {phase that was gated}
   **Outcome**: rejected
   **Reason**: $ARGUMENTS
   **Action**: Phase set back to ACTIVE for rework
   ```

3. **Update STATE.md**:
   - Set the current phase status to `BLOCKED` with the rejection reason
   - Then immediately set it back to `ACTIVE` to trigger rework
   - Add a `blocker_history` entry recording the rejection
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
     "result": "fail",
     "notes": "$ARGUMENTS"
   }
   ```

5. **Report** to the user:
   - What gate was rejected and why
   - The phase is now set back to ACTIVE for rework
   - What the agents need to address based on the rejection reason
   - Suggest next steps (re-run the phase, modify approach, etc.)
