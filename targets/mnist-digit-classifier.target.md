---
project: "mnist-digit-classifier"
target_repo: "/Users/samtukra/Documents/code/personal/mnist-delivery"
target_branch: "main"
worktree_base: "/tmp/zo-worktrees/mnist-digit-classifier"

git_author_name: "Zero Operators Agent"
git_author_email: "agents@zero-operators.local"

agent_working_dirs:
  lead_orchestrator: "."
  data_engineer: "data/"
  model_builder: "src/"
  oracle_qa: "reports/"
  code_reviewer: "."
  test_engineer: "tests/"

zo_only_paths:
  - ".claude/"
  - "CLAUDE.md"
  - "STATE.md"
  - ".zo/"
  - "memory/"
  - "logs/"
  - "zero-operators/"

enforce_isolation: true
---
