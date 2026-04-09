---
description: Clone a repo, analyze the codebase, and draft a full plan.md
argument-hint: <github-url>
---

# /import — Point at a repo and go

You are importing a new project into Zero Operators. This is the full onboarding command: clone, scaffold, analyze, and draft a plan.

## 1. Run /connect first

Execute all the steps from the `/project/connect` command using `$ARGUMENTS` as the GitHub URL. This clones the repo, creates the target file, and initializes the memory scaffold. Do all of those steps now before proceeding.

## 2. Analyze the codebase

Navigate to the cloned repo and perform a thorough analysis.

### 2a. Structure analysis

```bash
!find "../{project-name}" -type f -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/__pycache__/*' -not -path '*/.venv/*' | head -200
```

Note the top-level directory structure, primary language, and organization pattern.

### 2b. Dependency analysis

Look for dependency files and read them:
- `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg` (Python)
- `package.json` (Node.js)
- `Cargo.toml` (Rust)
- `go.mod` (Go)

From the dependencies, determine:
- **Workflow mode**: `deep_learning` if torch/tensorflow/jax present, `classical_ml` if sklearn/xgboost/lightgbm present, `research` if paper/latex/arxiv references found, otherwise `classical_ml`
- **Key frameworks**: list the major libraries
- **Data sources**: look for data loading code, CSV/parquet references, API clients

### 2c. README and docs

Read the README and any docs/ directory. Extract:
- Project purpose and description
- Any existing success metrics or evaluation criteria
- Known constraints or requirements
- Domain context

### 2d. Existing tests

```bash
!find "../{project-name}" -type f -name "test_*" -o -name "*_test.*" -o -name "*.test.*" | head -50
```

Note the testing framework and coverage.

### 2e. Existing code analysis

Read the main source files (entry points, core modules). Understand:
- What the code currently does
- What state it is in (prototype, production, broken)
- Architecture patterns used

## 3. Draft the plan

Create `plans/{project-name}.md` following the 8-section schema from `specs/plan.md`. Use everything gathered from the analysis.

### Required sections

**1. Project Identity** (YAML frontmatter):
- `project_name`: from the repo name
- `version`: "0.1.0"
- `created`: today's date
- `last_modified`: today's date
- `status`: active
- `owner`: "Sam"

**2. Objective**: Synthesize from README and code analysis. Be specific about the deliverable.

**3. Oracle Definition**: If metrics exist in the code (loss functions, eval scripts), extract them. Otherwise, propose reasonable metrics based on the project type and mark them as needing review.

**4. Workflow Configuration**: Set `mode` based on dependency analysis. Configure default gates.

**5. Data Sources**: Document any data files, data loading code, or API connections found.

**6. Domain Context and Priors**: Extract domain knowledge from README, comments, and docstrings. Note any assumptions or constraints mentioned in the code.

**7. Agent Configuration**: Default team unless the project clearly needs specific agents.

**8. Constraints**: Extract from the codebase (Python version, framework requirements, etc.).

### Optional sections

Include Milestones, Delivery Specification, Dependencies, and Open Questions as appropriate.

## 4. Present for review

Display the full drafted plan to the user. Highlight:
- Any sections marked TODO or needing human input
- Auto-detected workflow mode and rationale
- Proposed oracle metrics and whether they need refinement
- Open questions discovered during analysis

Ask the user to review and approve before saving. Save only after confirmation.
