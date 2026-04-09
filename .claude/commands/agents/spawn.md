---
description: Spawn an agent in the current session with full context
argument-hint: <agent-name>
---

# /spawn — Agent Spawner

You are spawning a Zero Operators agent into the current session context.

## Steps

1. **Read the agent definition** from `.claude/agents/$ARGUMENTS.md`. If the file does not exist, report available agents (list `.claude/agents/`) and stop.

2. **Read current project context**:
   - Read `STATE.md` from the active project's memory directory to understand current phase and status
   - Read the project plan (`targets/{project}.target.md`) for objectives and constraints
   - Read DECISION_LOG.md for recent decisions and context

3. **Validate the spawn**:
   - Is this agent appropriate for the current phase? (e.g., do not spawn XAI Agent during data profiling phase)
   - Are the agent's input dependencies met? (e.g., Model Builder needs DataLoaders to exist)
   - If validation fails, report why and suggest what needs to happen first

4. **Construct the spawn context**. From the agent definition, assemble:
   - Role description
   - Ownership (directories and files this agent owns)
   - Off-limits (what it must not touch)
   - Contract produced (expected outputs)
   - Contract consumed (required inputs)
   - Coordination rules
   - Validation checklist

5. **Log the spawn** to comms JSONL (`logs/comms/{YYYY-MM-DD}.jsonl`):
   ```json
   {
     "timestamp": "{ISO 8601}",
     "session_id": "{current session}",
     "event_type": "message",
     "agent": "lead-orchestrator",
     "project": "{project-name}",
     "message_type": "broadcast",
     "subject": "Spawning agent: $ARGUMENTS",
     "body": "Agent $ARGUMENTS spawned for phase {current-phase}"
   }
   ```

6. **Activate the agent**. Present the full agent instructions and context, then begin operating as that agent within the delivery repo. The agent should:
   - Acknowledge its role and current task
   - Verify its input dependencies are available
   - Begin working on its assigned phase/task
   - Follow its validation checklist before reporting done
