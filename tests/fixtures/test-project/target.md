---
project: "churn-prediction"
target_repo: "../delivery/churn-prediction"
target_branch: "main"
worktree_base: "/tmp/zo-worktrees/churn-prediction"
git_author_name: "ZO Churn Agent"
git_author_email: "agents@zero-operators.local"
agent_working_dirs:
  lead_orchestrator: "."
  data_engineer: "data/"
  model_builder: "src/models/"
  oracle_qa: "eval/"
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

# Churn Prediction Target

Delivery repository for the customer churn prediction project.
Agents write code and artefacts here; ZO internals stay in the ZO repo.
