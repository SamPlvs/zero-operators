# caveman skill (vendored — reference copy)

This directory vendors the [caveman](https://github.com/JuliusBrussee/caveman) Claude Code skill — an ultra-compressed communication mode that cuts agent prose token usage ~65–75% while keeping all technical substance intact.

## How ZO uses caveman (read this first)

**ZO does NOT rely on Claude Code auto-loading this `SKILL.md` file.** Caveman's always-on activation in Claude Code comes from upstream's SessionStart and UserPromptSubmit hooks (`hooks/install.sh` in their repo) which copy hook scripts into `~/.claude/hooks/` and patch `~/.claude/settings.json`. We deliberately do not run that installer — modifying the user's global Claude Code config is too invasive for an opt-in cost-saving feature.

Instead, when `--low-token` is active (and `caveman` is not opted out), the orchestrator inlines the caveman rules directly into the Lead Orchestrator's prompt — `src/zo/orchestrator.py:_prompt_low_token_overrides()` appends a "Token Efficiency: Caveman-Style Prose" subsection that contains the rules verbatim. The lead is instructed to pass the same rules to every sub-agent it spawns. The savings come from agents adopting the style as instructed; no skill or hook system is required.

This `SKILL.md` file is kept here as:
1. A **reference copy** of the canonical rules — useful if a developer wants to read the upstream spec without leaving the repo.
2. A **forward-compatible artifact** — if a future Claude Code release adds proper project-level skill auto-loading, this file is already in the right place to be picked up.
3. A **reference for users who install caveman properly** — anyone who runs upstream's `install.sh` separately gets the full hook-based always-on enforcement, and this file is a convenient way to confirm version alignment.

## Why caveman is safe to apply across the team

The skill explicitly preserves:

- Code blocks (verbatim)
- Quoted error strings (verbatim)
- Tool inputs (Write/Edit args — caveman only compresses chat prose, not tool calls)
- Structured artifacts (`metrics.jsonl`, `result.md`, `training_status.json`, agent contracts) — these go through Write/Edit, not chat

It also auto-disables itself for security warnings, irreversible-action confirmations, and any multi-step sequence where dropped articles/conjunctions could create ambiguity.

## Source

- Upstream: https://github.com/JuliusBrussee/caveman
- License: MIT (`LICENSE` in this directory — Copyright (c) 2026 Julius Brussee)
- Source-of-truth path upstream: `skills/caveman/SKILL.md`
- Auto-generated mirror at upstream root: `caveman/SKILL.md` (identical content)
- Vendored: 2026-05-05
- Intensity: full (default)

## Updating

To re-sync from upstream's source-of-truth:

```bash
gh api repos/JuliusBrussee/caveman/contents/skills/caveman/SKILL.md --jq '.content' | base64 -d \
  > .claude/skills/caveman/SKILL.md
```

Then verify the YAML frontmatter and `## Persistence` / `## Rules` / `## Intensity` / `## Auto-Clarity` / `## Boundaries` sections are intact, and re-check whether the inlined rules in `src/zo/orchestrator.py:_prompt_low_token_overrides()` need updating to match material changes.

## Activation summary

1. User runs `zo build --low-token` (or sets `low_token: true` in plan frontmatter).
2. The `--low-token` preset includes `caveman: True` (default; opt out via `--no-caveman` CLI flag or `caveman: false` plan field).
3. The Lead Orchestrator's prompt gains a "Token Efficiency: Caveman-Style Prose" subsection containing the rules inline.
4. Lead adopts the style; sub-agents receive the same rules in their spawn prompts and follow them too.

See `docs/concepts/low-token-mode.mdx` and `docs/reference/cost-benchmark.mdx` for measured impact (target: +10–20pp savings on top of the measured ~30% baseline from the lead Opus→Sonnet swap).
