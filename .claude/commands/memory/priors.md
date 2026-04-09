---
description: Display all accumulated domain priors for a project
argument-hint: <project-name>
---

# /priors — View domain priors

You are displaying the accumulated domain priors for project `$ARGUMENTS`.

If no argument is provided, detect the active project from memory or ask the user.

## 1. Locate the priors file

```bash
!cat "$(git rev-parse --show-toplevel)/memory/$ARGUMENTS/PRIORS.md" 2>/dev/null || echo "NO PRIORS FILE"
```

If the file does not exist, tell the user the project is not initialized and suggest running `zo init {project-name}`.

## 2. Parse and display priors

Read the full PRIORS.md file. Parse each prior entry which follows this schema:

```
## Prior: {category}
**Statement**: {factual claim}
**Evidence**: {case or reference}
**Confidence**: high | medium | low
**Superseded By**: {reference or empty}
```

## 3. Format the display

Group priors by category and display with clear formatting:

```
## Domain Priors: {project-name}
**Domain**: {domain from file header}
**Last Updated**: {timestamp from file header}
**Total Priors**: {count}

### {Category 1}

1. **{Statement}**
   - Evidence: {evidence}
   - Confidence: {high/medium/low}

2. **{Statement}**
   - Evidence: {evidence}
   - Confidence: {low}
   - SUPERSEDED BY: {reference}

### {Category 2}
...
```

Highlight:
- High-confidence priors (these are well-established facts)
- Low-confidence priors (these need more evidence)
- Superseded priors (mark clearly that these have been updated)

## 4. Handle empty priors

If the PRIORS.md exists but contains no prior entries (only the header), display:

```
## Domain Priors: {project-name}

No priors accumulated yet. Domain priors are learned as the project progresses:

- The domain evaluator adds priors when resolving QUESTIONABLE cases
- Priors capture domain-specific knowledge that agents would not discover from data alone
- They compound over iterations: first session has none, later sessions benefit from accumulated knowledge

Priors will appear here after the first domain evaluation cycle.
```

## 5. Summary statistics

At the end, show:
- Total prior count
- Breakdown by confidence level (high / medium / low)
- Number of superseded priors
- Most recent prior added (date and statement)
