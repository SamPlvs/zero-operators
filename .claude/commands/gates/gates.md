---
description: Display all gates for a project with their current status
argument-hint: <project-name>
---

# /gates — Gate Status Overview

You are displaying the full gate status table for a Zero Operators project.

## Steps

1. **Read the project plan** (`targets/{project-name}.target.md` or the project's plan file). Extract all gate definitions:
   - Gate number/ID
   - Associated phase
   - Gate type (auto = oracle-evaluated, blocking = requires human approval)
   - Pass criteria

2. **Read STATE.md** (`memory/{project-name}/STATE.md`). Extract:
   - Current phase and status
   - Which gates have been passed, which are pending

3. **Read DECISION_LOG.md** (`memory/{project-name}/DECISION_LOG.md`). Extract:
   - All gate-related entries (approved, rejected, oracle pass/fail)
   - Timestamps and notes for each gate event

4. **Display a table** with all gates:

   ```
   Gate Status: {project-name}
   Current Phase: {phase} ({status})

   | # | Phase | Gate Name | Type | Status | Date | Notes |
   |---|-------|-----------|------|--------|------|-------|
   | 1 | Phase 1 | ... | blocking | passed | 2026-04-05 | Human approved |
   | 2 | Phase 2 | ... | auto | passed | 2026-04-07 | Oracle: 0.92 >= 0.85 |
   | 3 | Phase 3 | ... | blocking | PENDING | - | Awaiting human review |
   | 4 | Phase 4 | ... | auto | - | - | Not yet reached |
   ```

5. **Highlight** the current/next gate clearly (mark it as PENDING or NEXT).

6. If any gates have failed previously, show the failure history beneath the table with rejection reasons and dates.
