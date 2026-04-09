---
description: Search project memory for decisions and priors matching a query
argument-hint: <query>
---

# /recall — Search project memory

You are searching the ZO memory system for information related to: `$ARGUMENTS`

If no argument is provided, ask the user what they want to search for.

## 1. Detect current project

Find the active project by checking STATE.md files:

```bash
!find "$(git rev-parse --show-toplevel)/memory" -name "STATE.md" -type f 2>/dev/null
```

If multiple projects exist, list them and ask the user which one to search. If only one exists, use it. If none exist, tell the user no projects are initialized.

## 2. Try semantic index first

Check if a semantic index exists for the project:

```bash
!ls "$(git rev-parse --show-toplevel)/memory/{project-name}/index.db" 2>/dev/null || echo "NO INDEX"
```

If the index exists, query it using the Python semantic search:

```bash
!cd "$(git rev-parse --show-toplevel)" && python -c "
from zo.semantic import SemanticIndex
from pathlib import Path
idx = SemanticIndex(Path('memory/{project-name}/index.db'))
results = idx.query('$ARGUMENTS', top_k=5)
for r in results:
    print(f'--- Score: {r.score:.3f} ---')
    print(f'Source: {r.source}')
    print(r.text)
    print()
idx.close()
"
```

If this succeeds, format and display the results. Skip to step 4.

## 3. Fall back to text search

If no semantic index or the query fails, search the memory files directly.

### Search DECISION_LOG.md

Read `memory/{project-name}/DECISION_LOG.md` and search for entries matching the query. Look for keyword matches in the Decision, Context, and Rationale fields.

### Search PRIORS.md

Read `memory/{project-name}/PRIORS.md` and search for entries matching the query. Look for keyword matches in Statement, Evidence, and Category fields.

### Search session summaries

```bash
!find "$(git rev-parse --show-toplevel)/memory/{project-name}/sessions" -name "*.md" -type f 2>/dev/null | sort -r | head -10
```

Read the most recent session summaries and search for relevant content.

## 4. Format results

Present the top 5 results clearly:

```
## Recall Results for: "{query}"

### 1. {title or first line}
- **Source**: DECISION_LOG / PRIORS / session-{date}
- **Timestamp**: {date if available}
- **Relevance**: {score if semantic, "keyword match" if grep}

{Full text of the decision, prior, or relevant session excerpt}

---

### 2. {title or first line}
...
```

If no results are found, say so and suggest:
- Broadening the search terms
- Checking if the project has accumulated enough history
- Listing what is available: number of decisions, priors, and sessions on file
