---
description: Launch an agent team to execute a project plan
argument-hint: <project-name>
---

# /launch — Launch agent team for a project

You are launching the ZO agent team for project `$ARGUMENTS`.

If no argument is provided, check for active projects in `plans/` and ask the user which one to launch.

## 1. Validate the plan

Read and validate the plan file:

```bash
!ls "$(git rev-parse --show-toplevel)/plans/$ARGUMENTS.md" 2>/dev/null || echo "NOT FOUND"
```

If the plan does not exist, tell the user to run `/project/plan` or `/project/import` first.

Read the plan file and verify all 8 required sections are present:
1. Project Identity (YAML frontmatter with project_name, version, status)
2. Objective
3. Oracle Definition (primary metric, ground truth, evaluation method, threshold, frequency)
4. Workflow Configuration (mode, gates)
5. Data Sources
6. Domain Context and Priors
7. Agent Configuration
8. Constraints

If any required section is missing or contains only TODO placeholders, halt and tell the user which sections need to be completed.

## 2. Validate the target file

```bash
!ls "$(git rev-parse --show-toplevel)/targets/$ARGUMENTS.target.md" 2>/dev/null || echo "NOT FOUND"
```

If the target file does not exist, tell the user to run `/project/connect` first.

Read the target and verify `target_repo` points to a valid directory:

```bash
!test -d "$(git rev-parse --show-toplevel)/../{target_repo_basename}" && echo "EXISTS" || echo "NOT FOUND"
```

## 3. Initialize memory

Check if memory is already initialized:

```bash
!ls "$(git rev-parse --show-toplevel)/memory/$ARGUMENTS/STATE.md" 2>/dev/null || echo "NOT INITIALIZED"
```

If not initialized, run init:

```bash
!cd "$(git rev-parse --show-toplevel)" && python -m zo.cli init $ARGUMENTS
```

## 4. Decompose the plan

Read the plan and break it into execution phases based on the workflow mode:

- **classical_ml**: Phase 1 (Data) -> Phase 2 (Features) -> Phase 3 (Model) -> Phase 4 (Training) -> Phase 5 (Validation) -> Phase 6 (Packaging)
- **deep_learning**: Same phases but Phase 2 shifts to input representations, Phase 3 expands architecture
- **research**: Adds Phase 0 (Literature Review) before Phase 1

Identify:
- Which phase to start with (read STATE.md for current progress)
- Which agents are needed for the first phase
- What the gate criteria are

## 5. Build the lead prompt

Construct the Lead Orchestrator prompt containing:
- Full plan content
- Target configuration
- Current state from STATE.md
- Relevant priors from PRIORS.md
- Recent decisions from DECISION_LOG.md
- Phase-specific instructions from the workflow

## 6. Launch via zo build

Execute the build command in supervised mode:

```bash
!cd "$(git rev-parse --show-toplevel)" && python -m zo.cli build "plans/$ARGUMENTS.md" --gate-mode supervised
```

If the CLI is not available or fails, explain to the user what the command would do and offer to launch manually by constructing the claude command directly.

## 7. Report to user

Display:
- Project name and plan summary
- Workflow mode and phases
- Active agents for the first phase
- Gate mode (supervised)
- How to monitor progress: `zo status {project-name}`
- How to continue after interruption: `zo continue {project-name}`
