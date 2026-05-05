# caveman skill (vendored)

This directory vendors the [caveman](https://github.com/JuliusBrussee/caveman) Claude Code skill — an ultra-compressed communication mode that cuts agent prose token usage ~75% while keeping all technical substance intact.

## Why this is here

ZO's `--low-token` preset auto-activates caveman by default for all spawned agents. It's the largest cost lever available without an SDK refactor (which would unlock prompt caching / Batch API / Files API).

Caveman is safe to apply across the team because it explicitly preserves:

- Code blocks (verbatim)
- Quoted error strings (verbatim)
- Tool inputs (Write/Edit are tool calls, not chat output — caveman only compresses chat prose)
- File writes including structured artifacts (`metrics.jsonl`, `result.md`, `training_status.json`) — these go through Write/Edit, not caveman

It also auto-disables itself for security warnings, irreversible-action confirmations, and any multi-step sequence where dropped articles/conjunctions could create ambiguity.

## Source

- Upstream: https://github.com/JuliusBrussee/caveman
- License: MIT (`LICENSE` in this directory — Copyright (c) 2026 Julius Brussee)
- Vendored from: `caveman/SKILL.md` at upstream main, fetched 2026-05-05
- Variant used: canonical (full intensity, default level)

## Updating

To re-sync from upstream:

```bash
gh api repos/JuliusBrussee/caveman/contents/caveman/SKILL.md --jq '.content' | base64 -d \
  > .claude/skills/caveman/SKILL.md
```

Then verify the YAML frontmatter and `## Persistence` / `## Rules` / `## Intensity` / `## Auto-Clarity` / `## Boundaries` sections are intact, and that no upstream-specific paths leaked in.

## How ZO activates this

1. User runs `zo build --low-token` (or sets `low_token: true` in plan frontmatter).
2. The `--low-token` preset includes `caveman: True` (default; can be opted out via `--no-caveman` CLI flag or `caveman: false` plan field).
3. The Lead Orchestrator's prompt gains a "Token efficiency mode" subsection (in `_prompt_low_token_overrides()`) that directs the lead and all spawned sub-agents to adopt caveman speech for prose responses.
4. Claude Code auto-loads this `SKILL.md` because of its presence in `.claude/skills/`. The lead's prompt directive ensures it stays active across sub-agent spawns.

See `docs/concepts/low-token-mode.mdx` and `docs/reference/cost-benchmark.mdx` for measured impact (target: +10–20pp savings on top of the measured ~30% baseline from the lead Opus→Sonnet swap).
