---
description: Watch a running ZO session or show last known state
argument-hint: <project-name>
---

# /watch — Live Session Monitor

You are checking the current status of a Zero Operators project session.

## Steps

1. **Check if a ZO session is currently running**:
   - Look for running Claude processes: `ps aux | grep claude`
   - Check for active team files: `ls ~/.claude/teams/` for any team directories related to the project
   - Check for active task files: `ls ~/.claude/tasks/` for any task directories related to the project

2. **If a session is running**:
   - Read the team config from `~/.claude/teams/{team-name}/config.json` to get agent list and statuses
   - Display each agent's current state: name, type, status (active/idle/blocked)
   - Read the task list from `~/.claude/tasks/{team-name}/` to show current task assignments and progress
   - Read the most recent JSONL comms log (`logs/comms/{latest-date}.jsonl`) and display the last 10 events in a readable format:
     ```
     TIME       AGENT              EVENT     SUMMARY
     14:32:15   model-builder      message   Requested updated DataLoader
     14:35:00   data-engineer      status    DataLoader ready, 3 splits produced
     14:36:12   oracle-qa          gate      Tier 1: 0.92 >= 0.85 PASS
     ```

3. **If no session is running**:
   - Read `memory/{project-name}/STATE.md` and display the last known state
   - Show: current phase, phase status, last updated timestamp, any blockers
   - Show the most recent session summary from `memory/{project-name}/sessions/`
   - Report: "No active session detected. Showing last known state."

4. **Always show** at the bottom:
   - Project name
   - Current/last phase
   - Time since last activity
