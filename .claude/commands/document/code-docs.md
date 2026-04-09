---
description: Generate or update documentation for the delivery repo code
---

# /code-docs — Code Documentation Generator

You are generating and updating documentation for the delivery repo associated with the current Zero Operators project.

## Steps

1. **Detect the delivery repo**. Read STATE.md or the project plan to identify the delivery repo path. If working within a target project directory, use that. If unclear, ask the user.

2. **Scan all Python files** in the delivery repo:
   ```bash
   find {delivery-repo} -name "*.py" -not -path "*/__pycache__/*" -not -path "*/venv/*"
   ```

3. **For each Python file**, check documentation quality:
   - Does the module have a module-level docstring?
   - Do all public functions and classes have Google-style docstrings?
   - Are type hints present on public function signatures?
   - Are parameters documented in the docstring?
   - Are return values documented?

4. **Fix missing docstrings**. For each gap found:
   - Read the function/class to understand its purpose
   - Write a Google-style docstring:
     ```python
     def function_name(param1: str, param2: int) -> bool:
         """Brief description of what this function does.

         Args:
             param1: Description of param1.
             param2: Description of param2.

         Returns:
             Description of return value.

         Raises:
             ValueError: When invalid input is provided.
         """
     ```
   - Add module-level docstrings where missing

5. **Generate API reference** if the project has a clear public interface:
   - List all public modules with one-line descriptions
   - List key functions and classes with signatures
   - Write to `docs/api_reference.md` in the delivery repo (only if a `docs/` directory exists or the project warrants it)

6. **Commit the changes** using conventional commit format:
   ```
   docs: add missing docstrings and update code documentation
   ```

7. **Report** to the user:
   - Number of files scanned
   - Number of docstrings added or updated
   - Any files that need manual attention (complex logic needing human-written docs)
