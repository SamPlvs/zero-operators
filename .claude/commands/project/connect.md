---
description: Clone a repo and scaffold a ZO project target for it
argument-hint: <github-url>
---

# /connect — Clone repo and create ZO project target

You are connecting a new repository to Zero Operators. Follow these steps precisely.

## 1. Parse the GitHub URL

Extract the repo name from the argument `$ARGUMENTS`. The project name is the repo name (e.g., `https://github.com/user/my-project` becomes `my-project`).

If no argument is provided, ask the user for a GitHub URL.

## 2. Clone the repository

Clone to a sibling directory of the ZO root (one level up from the zero-operators directory).

```bash
!cd "$(git rev-parse --show-toplevel)/.." && git clone $ARGUMENTS
```

Verify the clone succeeded and that the directory is a valid git repo:

```bash
!cd "$(git rev-parse --show-toplevel)/../{project-name}" && git rev-parse --is-inside-work-tree
```

## 3. Detect the default branch

```bash
!cd "$(git rev-parse --show-toplevel)/../{project-name}" && git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'
```

Store this as `target_branch`.

## 4. Create the target file

Create `targets/{project-name}.target.md` with this structure:

```yaml
---
project: "{project-name}"
target_repo: "../{project-name}"
target_branch: "{detected-branch}"
worktree_base: ".worktrees"
git_author_name: "ZO Agent"
git_author_email: "zo-agent@zero-operators.dev"
agent_working_dirs:
  data-engineer: "data/"
  model-builder: "src/"
  oracle-qa: "reports/"
  test-engineer: "tests/"
zo_only_paths:
  - "memory/"
  - "logs/"
  - ".claude/"
  - ".zo/"
  - "CLAUDE.md"
  - "STATE.md"
enforce_isolation: true
---
```

Adjust `agent_working_dirs` based on the actual directory structure found in the cloned repo. If `src/` exists, use it. If `lib/` exists, use that instead. Adapt to what is actually present.

## 5. Initialize memory scaffold

Run the ZO init command to create the memory directory structure:

```bash
!cd "$(git rev-parse --show-toplevel)" && python -m zo.cli init {project-name}
```

If `zo.cli` is not available, create the scaffold manually:

- `memory/{project-name}/STATE.md`
- `memory/{project-name}/DECISION_LOG.md`
- `memory/{project-name}/PRIORS.md`
- `memory/{project-name}/sessions/` (empty directory)

## 6. Report

Print a summary of everything created:

- Target file path and key fields
- Memory directory structure
- Cloned repo location and default branch
- Next steps: suggest running `/project/import` to analyze the codebase and draft a plan
