---
description: Create or update a structured task plan for the current project
argument-hint: <task-description>
---

# /plan — Create or update a task plan

You are creating a structured task plan for the current ZO project. The task description is: `$ARGUMENTS`

If no argument is provided, ask the user what they want to plan.

## 1. Load context

### Read current state

Read `memory/*/STATE.md` to find the active project. If multiple projects exist, ask the user which one.

```bash
!find "$(git rev-parse --show-toplevel)/memory" -name "STATE.md" -type f 2>/dev/null
```

Read the STATE.md for the active project. Note:
- Current mode and phase
- Active blockers
- Next steps already queued

### Read priors

Read `memory/{project-name}/PRIORS.md` if it exists. These are accumulated domain facts that should inform planning.

### Read existing plan

Check if `plans/{project-name}.md` already exists. If it does, read it to understand:
- Current objective and oracle definition
- Active workflow configuration
- Existing constraints
- What has already been planned

### Read recent decisions

Read `memory/{project-name}/DECISION_LOG.md` for the last 5-10 decisions. These inform what has been tried and what was decided.

## 2. Analyze the codebase

Search for files relevant to the task description:

```bash
!git rev-parse --show-toplevel
```

Use grep and glob to find code related to the task. Understand what exists, what needs to change, and what is missing.

## 3. Write the task plan

Structure the plan as follows:

```markdown
## Task: {task-description}

**Date**: {today}
**Mode**: build | continue | maintain
**Estimated phases**: {number}

### Objective
{What this task aims to accomplish, specific and measurable}

### Approach
{High-level strategy for achieving the objective}

### Agents Needed
{Which agents are required and what each will do}
- **data-engineer**: {role in this task, or "not needed"}
- **model-builder**: {role in this task, or "not needed"}
- **oracle-qa**: {role in this task, or "not needed"}
- **test-engineer**: {role in this task, or "not needed"}

### Subtasks
{Ordered list of concrete subtasks with dependencies}

1. **{subtask-name}** — {description}
   - Agent: {assigned agent}
   - Input: {what this subtask needs}
   - Output: {what this subtask produces}
   - Depends on: {previous subtask or "none"}

2. **{subtask-name}** — {description}
   ...

### Acceptance Criteria
{Specific, verifiable criteria for task completion}
- [ ] {criterion 1}
- [ ] {criterion 2}
- [ ] {criterion 3}

### Risks and Mitigations
- **Risk**: {description} → **Mitigation**: {strategy}

### Phase Breakdown
- **Phase 1**: {description} → Gate: {gate type}
- **Phase 2**: {description} → Gate: {gate type}
```

## 4. Integrate with existing plan

If `plans/{project-name}.md` already exists:
- **Build mode**: This is a new project plan. Create fresh.
- **Continue mode**: Add the task as a new section within the existing plan, preserving all existing content.
- **Maintain mode**: Create a targeted maintenance plan that references the existing plan but scopes changes narrowly.

## 5. Present for review

Display the complete plan to the user. Ask for approval before writing to disk.

If approved:
- Write or update `plans/{project-name}.md`
- Log the planning decision to `memory/{project-name}/DECISION_LOG.md`
- Update `memory/{project-name}/STATE.md` with the new next_steps

Do not save until the user confirms.
