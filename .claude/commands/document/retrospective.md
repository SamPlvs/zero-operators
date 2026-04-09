---
description: Run a retrospective analyzing failures, evolutions, and lessons learned
argument-hint: <project-name>
---

# /retrospective — Project Retrospective

You are running the evolution engine's retrospective protocol for a Zero Operators project, as defined in specs/evolution.md.

## Steps

1. **Scan DECISION_LOG.md** (`memory/{project-name}/DECISION_LOG.md`). Extract all entries tagged or categorized as:
   - `failure` — any failure entry with root cause analysis
   - `evolution` — any rule update entry
   - Gate rejections and re-evaluations

2. **Categorize failures by root cause**. For each failure, identify its category:
   - `missing_rule` — no rule existed to prevent this
   - `incomplete_rule` — rule existed but did not cover this case
   - `ignored_rule` — rule existed but agent did not follow it
   - `novel_case` — genuinely new situation not covered by priors
   - `regression` — a previously fixed issue recurring

3. **Identify patterns**. Look for clustering:
   - Are failures concentrated in a specific phase?
   - Is one agent responsible for multiple failures?
   - Is there a domain area that keeps causing issues?
   - Are there recurring themes (data quality, contract violations, metric drift)?

4. **Propose systemic updates**. Based on patterns:
   - If 3+ failures relate to the same area, propose a structural change
   - Suggest new mandatory subtasks, stronger gates, or new agent skills
   - Reference specific spec files that should be updated

5. **Generate the retrospective report**:

   ```markdown
   # Project Retrospective: {project-name}
   **Date**: {today}
   **Sessions completed**: {count from session files}
   **Total failures**: {count}
   **Total rule updates**: {count}

   ## Failure Distribution
   | Category | Count | Example |
   |----------|-------|---------|
   | missing_rule | ... | ... |
   | incomplete_rule | ... | ... |
   | ignored_rule | ... | ... |
   | novel_case | ... | ... |
   | regression | ... | ... |

   ## Patterns Identified
   {Description of recurring failure patterns}

   ## Rule Updates Made
   {List of evolution entries — what was updated and why}

   ## Recommended Systemic Updates
   {Specific changes to specs, agents, or workflow — for human approval}

   ## Lessons for Future Projects
   {Domain-agnostic insights that apply to all ZO projects}
   ```

6. **Present findings for human review**. Do NOT automatically apply systemic updates. Present them as recommendations and wait for approval.

7. **Report** to the user:
   - Key findings summary
   - Number of failures analyzed
   - Most impactful recommended changes
   - Ask if they want to approve any of the recommended systemic updates
