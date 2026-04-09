---
description: Create a new agent definition file interactively
argument-hint: <agent-name>
---

# /create-agent — Agent Definition Creator

You are creating a new Zero Operators agent definition file.

## Steps

1. **Get agent name** from `$ARGUMENTS`. Validate it is a valid kebab-case identifier (e.g., `domain-evaluator`, `report-writer`).

2. **Ask the user** for the following (if not already provided):
   - **Role description**: What does this agent do? (one paragraph)
   - **Model tier**: opus (complex reasoning, orchestration), sonnet (most tasks), or haiku (simple formatting, infrastructure)
   - **Team**: project (project delivery team) or platform (platform build team)

3. **Generate the agent definition file** at `.claude/agents/$ARGUMENTS.md` following this template:

   ```markdown
   ---
   name: {agent-name}
   model: {opus|sonnet|haiku}
   description: {one-line description}
   team: {project|platform}
   status: {launch|phase-in}
   ---

   # {Agent Display Name}

   **Model tier**: {tier}
   **Team**: {project delivery | platform build}
   **Role**: {role description}

   ## Ownership
   {Directories and files this agent owns and can write to}
   - `{path}/`: {purpose}

   ## Off-Limits
   {Directories and files this agent must NOT modify}
   - `{path}/`: Managed by {other-agent}

   ## Contract Produced
   {What outputs this agent creates}
   - File: `{path}`
     Format: {description}

   ## Contract Consumed
   {What inputs this agent requires from other agents}
   - File: `{path}`
     From: {source-agent}
     Validation: {how to verify input is valid}

   ## Coordination Rules
   - Message Orchestrator if {blocker condition}
   - Request from {agent} if {dependency condition}
   - Escalate to Orchestrator if {conflict condition}

   ## Validation Checklist
   Before reporting done, verify:
   - [ ] All outputs exist at specified paths
   - [ ] Output schema matches contract
   - [ ] All inputs consumed and validated
   - [ ] No off-limits files were modified
   - [ ] Logs document any errors or assumptions

   ## What This Agent Must NOT Do
   - {Explicit prohibition 1}
   - {Explicit prohibition 2}
   ```

4. **Fill in reasonable defaults** based on the role description. Leave placeholders marked with `{TODO}` for anything that requires project-specific knowledge.

5. **Log the creation** to DECISION_LOG.md (if it exists for the current project):
   ```markdown
   ## Agent Created: {agent-name}
   **Timestamp**: {ISO 8601}
   **Decided by**: human (via /create-agent)
   **Model tier**: {tier}
   **Team**: {team}
   **Role**: {one-line description}
   ```

6. **Report** to the user:
   - Path to the created file
   - Summary of the agent definition
   - Remind them to review and fill in any `{TODO}` placeholders
   - Suggest running `/agents` to see the updated roster
