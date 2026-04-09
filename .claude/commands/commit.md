---
description: Stage and commit changes with a conventional commit message
---

# /commit — Conventional Commit

You are creating a git commit for the current changes following Zero Operators conventions.

## Steps

1. **Run git status** to see all changed, staged, and untracked files:
   ```bash
   git status
   ```

2. **Run git diff** to see the actual changes (both staged and unstaged):
   ```bash
   git diff
   git diff --staged
   ```

3. **Check recent commit messages** for style consistency:
   ```bash
   git log --oneline -10
   ```

4. **Analyze the changes** and determine:
   - What type of change is this? Use conventional commit types:
     - `feat` — new feature or capability
     - `fix` — bug fix
     - `docs` — documentation only
     - `test` — adding or updating tests
     - `refactor` — code change that neither fixes a bug nor adds a feature
     - `chore` — maintenance, dependencies, configs
     - `style` — formatting, whitespace, no logic change
   - What scope is affected? (e.g., `orchestrator`, `memory`, `oracle`, `agents`)
   - What is the concise subject? (imperative mood, lowercase, no period)

5. **Stage relevant files**. Do NOT stage:
   - `.env` files
   - Credential files, API keys, tokens
   - Large binary files (unless intentional)
   - `__pycache__/` or `.pyc` files
   - IDE config files (`.vscode/`, `.idea/`)

   Stage everything else that is part of the logical change:
   ```bash
   git add {specific files}
   ```

6. **Create the commit** with the conventional format:
   ```
   type(scope): subject

   Body explaining what changed and why (if non-obvious).
   ```

7. **Report** to the user:
   - The commit message used
   - Files committed
   - The commit hash
   - Any files that were intentionally excluded and why
